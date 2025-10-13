/**
 * Incidents Service - Incident management and tracking
 */

import { db } from '../config/database';
import { Incident, PaginationParams, PaginatedResponse, Recommendation } from '../types';
import { NotFoundError, ValidationError } from '../utils/errors';
import { logger } from '../utils/logger';

export interface IncidentFilters {
  status?: string[];
  severity?: string[];
  assignee?: string;
  namespace?: string[];
  resource_kind?: string[];
  tags?: string[];
  start_time?: string;
  end_time?: string;
}

/**
 * Service for managing incidents
 */
export class IncidentsService {
  /**
   * List all incidents with optional filters and pagination
   * @param filters - Filtering criteria
   * @param pagination - Pagination parameters
   * @returns Paginated list of incidents
   */
  async listIncidents(
    filters: IncidentFilters = {},
    pagination: PaginationParams = {}
  ): Promise<PaginatedResponse<Incident>> {
    const session = db.getSession();

    try {
      const page = pagination.page || 1;
      const pageSize = pagination.page_size || 20;
      const sortField = pagination.sort || 'window_start';
      const sortOrder = pagination.order || 'desc';

      // Build where clause dynamically
      const whereClauses: string[] = [];
      const params: any = {
        skip: (page - 1) * pageSize,
        limit: pageSize,
      };

      if (filters.status && filters.status.length > 0) {
        whereClauses.push('inc.status IN $status');
        params.status = filters.status;
      }

      if (filters.severity && filters.severity.length > 0) {
        whereClauses.push('inc.severity IN $severity');
        params.severity = filters.severity;
      }

      if (filters.assignee) {
        whereClauses.push('inc.assignee = $assignee');
        params.assignee = filters.assignee;
      }

      if (filters.namespace && filters.namespace.length > 0) {
        whereClauses.push('r.ns IN $namespace');
        params.namespace = filters.namespace;
      }

      if (filters.resource_kind && filters.resource_kind.length > 0) {
        whereClauses.push('r.kind IN $resource_kind');
        params.resource_kind = filters.resource_kind;
      }

      if (filters.tags && filters.tags.length > 0) {
        whereClauses.push('ANY(tag IN $tags WHERE tag IN inc.tags)');
        params.tags = filters.tags;
      }

      if (filters.start_time) {
        whereClauses.push('inc.window_start >= datetime($start_time)');
        params.start_time = filters.start_time;
      }

      if (filters.end_time) {
        whereClauses.push('inc.window_end <= datetime($end_time)');
        params.end_time = filters.end_time;
      }

      const whereClause = whereClauses.length > 0 ? `WHERE ${whereClauses.join(' AND ')}` : '';

      // Count total
      const countCypher = `
        MATCH (inc:Incident)-[:AFFECTS]->(r:Resource)
        ${whereClause}
        RETURN count(DISTINCT inc) as total
      `;

      const countResult = await session.run(countCypher, params);
      const totalCount = countResult.records[0]?.get('total').toNumber() || 0;

      // Get paginated results
      const dataCypher = `
        MATCH (inc:Incident)-[:AFFECTS]->(r:Resource)
        ${whereClause}
        WITH DISTINCT inc, r
        ORDER BY inc.${sortField} ${sortOrder.toUpperCase()}
        SKIP $skip
        LIMIT $limit
        RETURN
          inc.incident_id as incident_id,
          inc.resource_id as resource_id,
          toString(inc.window_start) as window_start,
          toString(inc.window_end) as window_end,
          inc.event_count as event_count,
          inc.severity as severity,
          inc.status as status,
          inc.assignee as assignee,
          inc.notes as notes,
          inc.tags as tags,
          toString(inc.created_at) as created_at,
          toString(inc.updated_at) as updated_at
      `;

      const dataResult = await session.run(dataCypher, params);

      const incidents: Incident[] = dataResult.records.map(record => ({
        incident_id: record.get('incident_id'),
        resource_id: record.get('resource_id'),
        window_start: record.get('window_start'),
        window_end: record.get('window_end'),
        event_count: record.get('event_count').toNumber(),
        severity: record.get('severity'),
        status: record.get('status') || 'open',
        assignee: record.get('assignee'),
        notes: record.get('notes'),
        tags: record.get('tags') || [],
        created_at: record.get('created_at'),
        updated_at: record.get('updated_at'),
      }));

      const totalPages = Math.ceil(totalCount / pageSize);

      logger.info(
        `Listed ${incidents.length} incidents (page ${page}/${totalPages}, total: ${totalCount})`
      );

      return {
        data: incidents,
        pagination: {
          page,
          page_size: pageSize,
          total_pages: totalPages,
          total_count: totalCount,
        },
      };
    } catch (error) {
      logger.error('Failed to list incidents:', error);
      throw error;
    } finally {
      await session.close();
    }
  }

  /**
   * Get a single incident by ID
   * @param incidentId - The incident ID
   * @returns The incident details
   */
  async getIncidentById(incidentId: string): Promise<Incident> {
    const session = db.getSession();

    try {
      const cypher = `
        MATCH (inc:Incident {incident_id: $incidentId})
        OPTIONAL MATCH (inc)-[:AFFECTS]->(r:Resource)
        RETURN
          inc.incident_id as incident_id,
          inc.resource_id as resource_id,
          toString(inc.window_start) as window_start,
          toString(inc.window_end) as window_end,
          inc.event_count as event_count,
          inc.severity as severity,
          inc.status as status,
          inc.assignee as assignee,
          inc.notes as notes,
          inc.tags as tags,
          toString(inc.created_at) as created_at,
          toString(inc.updated_at) as updated_at
      `;

      const result = await session.run(cypher, { incidentId });

      if (result.records.length === 0) {
        throw new NotFoundError('Incident', incidentId);
      }

      const record = result.records[0];

      const incident: Incident = {
        incident_id: record.get('incident_id'),
        resource_id: record.get('resource_id'),
        window_start: record.get('window_start'),
        window_end: record.get('window_end'),
        event_count: record.get('event_count').toNumber(),
        severity: record.get('severity'),
        status: record.get('status') || 'open',
        assignee: record.get('assignee'),
        notes: record.get('notes'),
        tags: record.get('tags') || [],
        created_at: record.get('created_at'),
        updated_at: record.get('updated_at'),
      };

      logger.info(`Retrieved incident ${incidentId}`);

      return incident;
    } catch (error) {
      logger.error(`Failed to get incident ${incidentId}:`, error);
      throw error;
    } finally {
      await session.close();
    }
  }

  /**
   * Update incident status and related fields
   * @param incidentId - The incident ID
   * @param status - New status (open, acknowledged, resolved)
   * @param assignee - Assignee username
   * @param notes - Additional notes
   * @param tags - Tags for categorization
   * @returns The updated incident
   */
  async updateIncidentStatus(
    incidentId: string,
    status?: string,
    assignee?: string,
    notes?: string,
    tags?: string[]
  ): Promise<Incident> {
    const session = db.getSession();

    try {
      // Validate status
      if (status && !['open', 'acknowledged', 'resolved'].includes(status)) {
        throw new ValidationError('Invalid status', {
          valid_statuses: ['open', 'acknowledged', 'resolved'],
        });
      }

      // Build update SET clause dynamically
      const updateFields: string[] = ['inc.updated_at = datetime()'];
      const params: any = { incidentId };

      if (status !== undefined) {
        updateFields.push('inc.status = $status');
        params.status = status;
      }

      if (assignee !== undefined) {
        updateFields.push('inc.assignee = $assignee');
        params.assignee = assignee;
      }

      if (notes !== undefined) {
        updateFields.push('inc.notes = $notes');
        params.notes = notes;
      }

      if (tags !== undefined) {
        updateFields.push('inc.tags = $tags');
        params.tags = tags;
      }

      const cypher = `
        MATCH (inc:Incident {incident_id: $incidentId})
        SET ${updateFields.join(',\n            ')}
        RETURN
          inc.incident_id as incident_id,
          inc.resource_id as resource_id,
          toString(inc.window_start) as window_start,
          toString(inc.window_end) as window_end,
          inc.event_count as event_count,
          inc.severity as severity,
          inc.status as status,
          inc.assignee as assignee,
          inc.notes as notes,
          inc.tags as tags,
          toString(inc.created_at) as created_at,
          toString(inc.updated_at) as updated_at
      `;

      const result = await session.run(cypher, params);

      if (result.records.length === 0) {
        throw new NotFoundError('Incident', incidentId);
      }

      const record = result.records[0];

      const incident: Incident = {
        incident_id: record.get('incident_id'),
        resource_id: record.get('resource_id'),
        window_start: record.get('window_start'),
        window_end: record.get('window_end'),
        event_count: record.get('event_count').toNumber(),
        severity: record.get('severity'),
        status: record.get('status') || 'open',
        assignee: record.get('assignee'),
        notes: record.get('notes'),
        tags: record.get('tags') || [],
        created_at: record.get('created_at'),
        updated_at: record.get('updated_at'),
      };

      logger.info(`Updated incident ${incidentId}`, { status, assignee, tags });

      return incident;
    } catch (error) {
      logger.error(`Failed to update incident ${incidentId}:`, error);
      throw error;
    } finally {
      await session.close();
    }
  }

  /**
   * Get AI-generated recommendations for an incident
   * @param incidentId - The incident ID
   * @returns List of recommendations
   */
  async getIncidentRecommendations(incidentId: string): Promise<Recommendation[]> {
    const session = db.getSession();

    try {
      // First, get the incident and related events
      const cypher = `
        MATCH (inc:Incident {incident_id: $incidentId})-[:AFFECTS]->(r:Resource)
        OPTIONAL MATCH (inc)<-[:PART_OF]-(e:Episodic)
        WITH inc, r, collect(DISTINCT {
          reason: e.reason,
          severity: e.severity,
          message: e.message,
          event_time: toString(e.event_time)
        }) as events
        ORDER BY events[0].event_time DESC
        RETURN
          inc.incident_id as incident_id,
          inc.severity as severity,
          r.kind as resource_kind,
          r.name as resource_name,
          r.ns as resource_ns,
          events
      `;

      const result = await session.run(cypher, { incidentId });

      if (result.records.length === 0) {
        throw new NotFoundError('Incident', incidentId);
      }

      const record = result.records[0];
      const events = record.get('events') || [];
      const resourceKind = record.get('resource_kind');
      const severity = record.get('severity');

      const recommendations: Recommendation[] = [];

      // Analyze events to generate recommendations
      const reasons = events.map((e: any) => e.reason?.toLowerCase() || '');
      const messages = events.map((e: any) => e.message?.toLowerCase() || '');
      const allText = [...reasons, ...messages].join(' ');

      // OOM / Memory issues
      if (allText.includes('oom') || allText.includes('memory') || allText.includes('oomkilled')) {
        recommendations.push({
          type: 'resource_adjustment',
          action: 'Increase memory limits',
          details: {
            resource_type: 'memory',
            current_issue: 'OOM (Out of Memory) detected',
            suggested_action: 'Increase memory requests and limits for the affected container',
            example_command: `kubectl set resources ${resourceKind.toLowerCase()}/${record.get('resource_name')} --limits=memory=2Gi --requests=memory=1Gi -n ${record.get('resource_ns')}`,
          },
          confidence: 0.9,
          priority: 'high',
          automated: false,
        });
      }

      // CPU throttling
      if (allText.includes('cpu') || allText.includes('throttl')) {
        recommendations.push({
          type: 'resource_adjustment',
          action: 'Adjust CPU limits',
          details: {
            resource_type: 'cpu',
            current_issue: 'CPU throttling or shortage detected',
            suggested_action: 'Increase CPU requests and limits for the affected container',
            example_command: `kubectl set resources ${resourceKind.toLowerCase()}/${record.get('resource_name')} --limits=cpu=2000m --requests=cpu=1000m -n ${record.get('resource_ns')}`,
          },
          confidence: 0.85,
          priority: 'high',
          automated: false,
        });
      }

      // CrashLoopBackOff
      if (allText.includes('crash') || allText.includes('backoff')) {
        recommendations.push({
          type: 'investigation',
          action: 'Investigate application logs and startup issues',
          details: {
            current_issue: 'Pod is crashing repeatedly',
            suggested_action: 'Check application logs, verify environment variables, and ensure dependencies are available',
            commands: [
              `kubectl logs ${record.get('resource_name')} -n ${record.get('resource_ns')} --previous`,
              `kubectl describe pod ${record.get('resource_name')} -n ${record.get('resource_ns')}`,
            ],
          },
          confidence: 0.8,
          priority: 'high',
          automated: false,
        });
      }

      // Image pull issues
      if (
        allText.includes('imagepull') ||
        allText.includes('image') ||
        allText.includes('pull')
      ) {
        recommendations.push({
          type: 'configuration',
          action: 'Fix image pull configuration',
          details: {
            current_issue: 'Unable to pull container image',
            suggested_action:
              'Verify image name, check registry credentials, ensure network connectivity',
            commands: [
              `kubectl describe pod ${record.get('resource_name')} -n ${record.get('resource_ns')}`,
            ],
          },
          confidence: 0.9,
          priority: 'high',
          automated: false,
        });
      }

      // Liveness/Readiness probe failures
      if (allText.includes('liveness') || allText.includes('readiness') || allText.includes('probe')) {
        recommendations.push({
          type: 'configuration',
          action: 'Review health check probes',
          details: {
            current_issue: 'Health probe failures detected',
            suggested_action:
              'Review liveness and readiness probe configuration, adjust timeouts if needed',
            commands: [
              `kubectl describe pod ${record.get('resource_name')} -n ${record.get('resource_ns')}`,
            ],
          },
          confidence: 0.75,
          priority: 'medium',
          automated: false,
        });
      }

      // Disk/Volume issues
      if (allText.includes('disk') || allText.includes('volume') || allText.includes('storage')) {
        recommendations.push({
          type: 'resource_adjustment',
          action: 'Check storage and volume configuration',
          details: {
            current_issue: 'Storage or volume-related issues detected',
            suggested_action: 'Verify PVC status, check disk space, ensure volumes are mounted correctly',
            commands: [
              `kubectl get pvc -n ${record.get('resource_ns')}`,
              `kubectl describe pod ${record.get('resource_name')} -n ${record.get('resource_ns')}`,
            ],
          },
          confidence: 0.8,
          priority: 'high',
          automated: false,
        });
      }

      // Network issues
      if (
        allText.includes('network') ||
        allText.includes('connection') ||
        allText.includes('timeout')
      ) {
        recommendations.push({
          type: 'investigation',
          action: 'Investigate network connectivity',
          details: {
            current_issue: 'Network connectivity issues detected',
            suggested_action: 'Check network policies, verify service endpoints, test connectivity',
            commands: [
              `kubectl get svc -n ${record.get('resource_ns')}`,
              `kubectl get networkpolicies -n ${record.get('resource_ns')}`,
            ],
          },
          confidence: 0.7,
          priority: 'medium',
          automated: false,
        });
      }

      // Default recommendation if nothing specific detected
      if (recommendations.length === 0) {
        recommendations.push({
          type: 'investigation',
          action: 'Review incident details and logs',
          details: {
            current_issue: `${severity} severity incident detected on ${resourceKind}`,
            suggested_action: 'Review event timeline, check resource status, and investigate root cause',
            commands: [
              `kubectl describe ${resourceKind.toLowerCase()} ${record.get('resource_name')} -n ${record.get('resource_ns')}`,
              `kubectl get events -n ${record.get('resource_ns')} --sort-by='.lastTimestamp'`,
            ],
          },
          confidence: 0.5,
          priority: severity === 'FATAL' || severity === 'ERROR' ? 'high' : 'medium',
          automated: false,
        });
      }

      logger.info(`Generated ${recommendations.length} recommendations for incident ${incidentId}`);

      return recommendations;
    } catch (error) {
      logger.error(`Failed to get recommendations for incident ${incidentId}:`, error);
      throw error;
    } finally {
      await session.close();
    }
  }
}

export const incidentsService = new IncidentsService();
