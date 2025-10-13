/**
 * Resources Service - Resource management and health monitoring
 */

import { db } from '../config/database';
import { ResourceInfo, ResourceHealth, HealthCheck, PaginationParams, PaginatedResponse } from '../types';
import { NotFoundError } from '../utils/errors';
import { logger } from '../utils/logger';

export interface ResourceFilters {
  kind?: string[];
  namespace?: string[];
  labels?: Record<string, string>;
  status?: string[];
  has_incidents?: boolean;
  has_recent_events?: boolean;
  time_window_hours?: number;
}

/**
 * Service for managing Kubernetes resources
 */
export class ResourcesService {
  /**
   * Get a single resource by UID
   * @param resourceUid - The resource UID
   * @returns The resource information
   */
  async getResourceById(resourceUid: string): Promise<ResourceInfo> {
    const session = db.getSession();

    try {
      const cypher = `
        MATCH (r:Resource {uid: $resourceUid})
        OPTIONAL MATCH (r)<-[:ABOUT]-(e:Episodic)
        WHERE e.event_time >= datetime() - duration({hours: 24})
        WITH r, count(e) as recent_events
        RETURN
          r.uid as uid,
          r.rid as rid,
          r.kind as kind,
          r.name as name,
          r.ns as namespace,
          r.labels_json as labels,
          r.status_json as status,
          r.spec_json as spec,
          toString(r.created_at) as created_at,
          toString(r.updated_at) as updated_at,
          recent_events
      `;

      const result = await session.run(cypher, { resourceUid });

      if (result.records.length === 0) {
        throw new NotFoundError('Resource', resourceUid);
      }

      const record = result.records[0];

      const resource: ResourceInfo = {
        uid: record.get('uid'),
        rid: record.get('rid'),
        kind: record.get('kind'),
        name: record.get('name'),
        namespace: record.get('namespace'),
        labels: this.parseJSON(record.get('labels')),
        status: this.parseJSON(record.get('status')),
        spec: this.parseJSON(record.get('spec')),
        created_at: record.get('created_at'),
        updated_at: record.get('updated_at'),
      };

      logger.info(`Retrieved resource ${resourceUid}`);

      return resource;
    } catch (error) {
      logger.error(`Failed to get resource ${resourceUid}:`, error);
      throw error;
    } finally {
      await session.close();
    }
  }

  /**
   * List resources with optional filters and pagination
   * @param filters - Filtering criteria
   * @param pagination - Pagination parameters
   * @returns Paginated list of resources
   */
  async listResources(
    filters: ResourceFilters = {},
    pagination: PaginationParams = {}
  ): Promise<PaginatedResponse<ResourceInfo>> {
    const session = db.getSession();

    try {
      const page = pagination.page || 1;
      const pageSize = pagination.page_size || 50;
      const sortField = pagination.sort || 'updated_at';
      const sortOrder = pagination.order || 'desc';

      // Build where clause dynamically
      const whereClauses: string[] = [];
      const params: any = {
        skip: (page - 1) * pageSize,
        limit: pageSize,
      };

      if (filters.kind && filters.kind.length > 0) {
        whereClauses.push('r.kind IN $kind');
        params.kind = filters.kind;
      }

      if (filters.namespace && filters.namespace.length > 0) {
        whereClauses.push('r.ns IN $namespace');
        params.namespace = filters.namespace;
      }

      if (filters.labels && Object.keys(filters.labels).length > 0) {
        // Check if resource has matching labels
        const labelChecks = Object.entries(filters.labels).map(
          ([key, value], index) => {
            params[`labelKey${index}`] = key;
            params[`labelValue${index}`] = value;
            return `r.labels_json CONTAINS '"${key}":"${value}"'`;
          }
        );
        whereClauses.push(`(${labelChecks.join(' AND ')})`);
      }

      // Add incident filter if specified
      let incidentMatch = '';
      if (filters.has_incidents) {
        incidentMatch = `
          OPTIONAL MATCH (r)<-[:AFFECTS]-(inc:Incident)
          WHERE inc.status IN ['open', 'acknowledged']
          WITH r, count(inc) as incident_count
          WHERE incident_count > 0
        `;
      }

      // Add recent events filter if specified
      let eventsFilter = '';
      if (filters.has_recent_events) {
        const timeWindowHours = filters.time_window_hours || 24;
        params.timeWindowHours = timeWindowHours;
        eventsFilter = `
          OPTIONAL MATCH (r)<-[:ABOUT]-(e:Episodic)
          WHERE e.event_time >= datetime() - duration({hours: $timeWindowHours})
          WITH r, count(e) as event_count
          WHERE event_count > 0
        `;
      }

      const whereClause = whereClauses.length > 0 ? `WHERE ${whereClauses.join(' AND ')}` : '';

      // Count total
      const countCypher = `
        MATCH (r:Resource)
        ${whereClause}
        ${incidentMatch}
        ${eventsFilter}
        RETURN count(DISTINCT r) as total
      `;

      const countResult = await session.run(countCypher, params);
      const totalCount = countResult.records[0]?.get('total').toNumber() || 0;

      // Get paginated results
      const dataCypher = `
        MATCH (r:Resource)
        ${whereClause}
        ${incidentMatch}
        ${eventsFilter}
        WITH DISTINCT r
        ORDER BY r.${sortField} ${sortOrder.toUpperCase()}
        SKIP $skip
        LIMIT $limit
        RETURN
          r.uid as uid,
          r.rid as rid,
          r.kind as kind,
          r.name as name,
          r.ns as namespace,
          r.labels_json as labels,
          r.status_json as status,
          toString(r.created_at) as created_at,
          toString(r.updated_at) as updated_at
      `;

      const dataResult = await session.run(dataCypher, params);

      const resources: ResourceInfo[] = dataResult.records.map(record => ({
        uid: record.get('uid'),
        rid: record.get('rid'),
        kind: record.get('kind'),
        name: record.get('name'),
        namespace: record.get('namespace'),
        labels: this.parseJSON(record.get('labels')),
        status: this.parseJSON(record.get('status')),
        created_at: record.get('created_at'),
        updated_at: record.get('updated_at'),
      }));

      const totalPages = Math.ceil(totalCount / pageSize);

      logger.info(
        `Listed ${resources.length} resources (page ${page}/${totalPages}, total: ${totalCount})`
      );

      return {
        data: resources,
        pagination: {
          page,
          page_size: pageSize,
          total_pages: totalPages,
          total_count: totalCount,
        },
      };
    } catch (error) {
      logger.error('Failed to list resources:', error);
      throw error;
    } finally {
      await session.close();
    }
  }

  /**
   * Get comprehensive health information for a resource
   * @param resourceUid - The resource UID
   * @returns Resource health assessment
   */
  async getResourceHealth(resourceUid: string): Promise<ResourceHealth> {
    const session = db.getSession();

    try {
      // Get resource with events and incidents
      const cypher = `
        MATCH (r:Resource {uid: $resourceUid})

        // Get recent events by severity
        OPTIONAL MATCH (r)<-[:ABOUT]-(e:Episodic)
        WHERE e.event_time >= datetime() - duration({hours: 24})
        WITH r, e

        // Get open incidents
        OPTIONAL MATCH (r)<-[:AFFECTS]-(inc:Incident)
        WHERE inc.status IN ['open', 'acknowledged']

        WITH r,
             collect(DISTINCT {
               severity: e.severity,
               event_time: e.event_time,
               reason: e.reason,
               message: e.message
             }) as events,
             collect(DISTINCT inc) as incidents

        // Count events by severity
        WITH r, events, incidents,
             size([e IN events WHERE e.severity = 'FATAL']) as fatal_count,
             size([e IN events WHERE e.severity = 'ERROR']) as error_count,
             size([e IN events WHERE e.severity = 'WARNING']) as warning_count,
             size([e IN events WHERE e.severity = 'INFO']) as info_count

        // Get most recent error
        WITH r, events, incidents,
             fatal_count, error_count, warning_count, info_count,
             [e IN events WHERE e.severity IN ['FATAL', 'ERROR'] | e][0] as last_error

        RETURN
          r.uid as uid,
          r.kind as kind,
          r.name as name,
          r.ns as namespace,
          r.status_json as status,
          fatal_count,
          error_count,
          warning_count,
          info_count,
          size(events) as total_events,
          size(incidents) as incident_count,
          last_error
      `;

      const result = await session.run(cypher, { resourceUid });

      if (result.records.length === 0) {
        throw new NotFoundError('Resource', resourceUid);
      }

      const record = result.records[0];

      const fatalCount = record.get('fatal_count').toNumber();
      const errorCount = record.get('error_count').toNumber();
      const warningCount = record.get('warning_count').toNumber();
      const infoCount = record.get('info_count').toNumber();
      const totalEvents = record.get('total_events').toNumber();
      const incidentCount = record.get('incident_count').toNumber();
      const lastError = record.get('last_error');

      // Calculate health score (0-100)
      let healthScore = 100;

      // Deduct for incidents
      healthScore -= incidentCount * 15;

      // Deduct for fatal events
      healthScore -= fatalCount * 20;

      // Deduct for errors
      healthScore -= errorCount * 10;

      // Deduct for warnings
      healthScore -= warningCount * 5;

      // Ensure score is between 0-100
      healthScore = Math.max(0, Math.min(100, healthScore));

      // Determine overall status
      let status: 'healthy' | 'degraded' | 'critical';
      if (healthScore >= 80) {
        status = 'healthy';
      } else if (healthScore >= 50) {
        status = 'degraded';
      } else {
        status = 'critical';
      }

      // Build health checks
      const checks: HealthCheck[] = [];

      // Incident check
      checks.push({
        name: 'Active Incidents',
        status: incidentCount === 0 ? 'ok' : incidentCount < 3 ? 'warning' : 'critical',
        value: incidentCount,
        threshold: 0,
        message: incidentCount > 0 ? `${incidentCount} active incident(s)` : 'No active incidents',
      });

      // Fatal events check
      checks.push({
        name: 'Fatal Events (24h)',
        status: fatalCount === 0 ? 'ok' : fatalCount < 5 ? 'warning' : 'critical',
        value: fatalCount,
        threshold: 0,
        message: fatalCount > 0 ? `${fatalCount} fatal event(s) in last 24h` : 'No fatal events',
      });

      // Error events check
      checks.push({
        name: 'Error Events (24h)',
        status: errorCount === 0 ? 'ok' : errorCount < 10 ? 'warning' : 'critical',
        value: errorCount,
        threshold: 10,
        message:
          errorCount > 0
            ? `${errorCount} error event(s) in last 24h`
            : 'No error events',
      });

      // Warning events check
      checks.push({
        name: 'Warning Events (24h)',
        status: warningCount === 0 ? 'ok' : warningCount < 20 ? 'warning' : 'critical',
        value: warningCount,
        threshold: 20,
        message:
          warningCount > 0
            ? `${warningCount} warning event(s) in last 24h`
            : 'No warning events',
      });

      // Event frequency check
      const eventFrequency = totalEvents;
      checks.push({
        name: 'Event Frequency (24h)',
        status: eventFrequency < 50 ? 'ok' : eventFrequency < 100 ? 'warning' : 'critical',
        value: eventFrequency,
        threshold: 50,
        message:
          eventFrequency > 50
            ? `High event frequency: ${eventFrequency} events`
            : `Normal event frequency: ${eventFrequency} events`,
      });

      const resourceHealth: ResourceHealth = {
        resource_uid: resourceUid,
        health_score: healthScore,
        status,
        checks,
        recent_incidents: incidentCount,
        last_error: lastError
          ? `${lastError.reason}: ${lastError.message || 'No message'}`
          : undefined,
      };

      logger.info(
        `Calculated health for resource ${resourceUid}: ${healthScore}/100 (${status})`
      );

      return resourceHealth;
    } catch (error) {
      logger.error(`Failed to get health for resource ${resourceUid}:`, error);
      throw error;
    } finally {
      await session.close();
    }
  }

  /**
   * Parse JSON string safely
   * @param jsonString - JSON string to parse
   * @returns Parsed object or empty object
   */
  private parseJSON(jsonString: string | null): Record<string, any> {
    if (!jsonString) return {};

    try {
      return JSON.parse(jsonString);
    } catch (error) {
      logger.warn('Failed to parse JSON:', error);
      return {};
    }
  }
}

export const resourcesService = new ResourcesService();
