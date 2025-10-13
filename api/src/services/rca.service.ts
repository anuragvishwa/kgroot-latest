/**
 * Root Cause Analysis Service
 */

import { db } from '../config/database';
import { RCAQuery, RCAResult, Cause, ResourceInfo, Incident, TimelineEvent } from '../types';
import { NotFoundError } from '../utils/errors';
import { logger } from '../utils/logger';

export class RCAService {
  async performRCA(query: RCAQuery): Promise<RCAResult> {
    const session = db.getSession();

    try {
      const timeWindow = query.time_window_minutes || 15;
      const maxHops = query.max_hops || 3;
      const minConfidence = query.min_confidence || 0.4;

      const cypher = `
        MATCH (e:Episodic {eid: $eid})-[:ABOUT]->(subj:Resource)
        OPTIONAL MATCH (e)<-[pc:POTENTIAL_CAUSE]-(cause:Episodic)-[:ABOUT]->(causeRes:Resource)
        WHERE pc.confidence >= $minConfidence AND pc.hops <= $maxHops
        OPTIONAL MATCH (e)-[:PART_OF]->(inc:Incident)
        OPTIONAL MATCH (subj)-[*1..2]-(related:Resource)
        WHERE related <> subj
        WITH e, subj,
             collect(DISTINCT {
               event_id: cause.eid,
               event_time: toString(cause.event_time),
               reason: cause.reason,
               message: cause.message,
               severity: cause.severity,
               confidence: pc.confidence,
               hops: pc.hops,
               temporal_score: pc.temporal_score,
               distance_score: pc.distance_score,
               domain_score: pc.domain_score,
               subject_rid: causeRes.rid,
               subject_kind: causeRes.kind,
               subject_name: causeRes.name,
               subject_ns: causeRes.ns
             }) as causes,
             collect(DISTINCT {
               rid: related.rid,
               kind: related.kind,
               name: related.name,
               ns: related.ns
             }) as blast_radius,
             inc
        OPTIONAL MATCH (subj)<-[:ABOUT]-(timelineEvent:Episodic)
        WHERE timelineEvent.event_time >= datetime() - duration({minutes: $timeWindow})
          AND timelineEvent.event_time <= e.event_time
        WITH e, subj, causes, blast_radius, inc,
             collect(DISTINCT {
               event_time: toString(timelineEvent.event_time),
               reason: timelineEvent.reason,
               severity: timelineEvent.severity,
               message: timelineEvent.message,
               resource: timelineEvent.rid
             }) as timeline
        RETURN
          e.eid as event_id,
          toString(e.event_time) as event_time,
          e.reason as reason,
          e.severity as severity,
          e.message as message,
          subj.rid as subj_rid,
          subj.kind as subj_kind,
          subj.name as subj_name,
          subj.ns as subj_ns,
          subj.labels_json as subj_labels,
          causes,
          blast_radius,
          timeline,
          inc.incident_id as inc_id,
          inc.resource_id as inc_resource_id,
          toString(inc.window_start) as inc_window_start,
          toString(inc.window_end) as inc_window_end,
          inc.event_count as inc_event_count,
          inc.severity as inc_severity
      `;

      const result = await session.run(cypher, {
        eid: query.event_id,
        minConfidence,
        maxHops,
        timeWindow,
      });

      if (result.records.length === 0) {
        throw new NotFoundError('Event', query.event_id);
      }

      const record = result.records[0];

      const rcaResult: RCAResult = {
        event_id: record.get('event_id'),
        event_time: record.get('event_time'),
        reason: record.get('reason'),
        severity: record.get('severity'),
        message: record.get('message'),
        subject: {
          rid: record.get('subj_rid'),
          kind: record.get('subj_kind'),
          name: record.get('subj_name'),
          namespace: record.get('subj_ns'),
          labels: this.parseLabels(record.get('subj_labels')),
        },
        potential_causes: this.parseCauses(record.get('causes')),
        blast_radius: this.parseResources(record.get('blast_radius')),
        timeline: this.parseTimeline(record.get('timeline')),
      };

      // Add incident if exists
      const incId = record.get('inc_id');
      if (incId) {
        rcaResult.related_incident = {
          incident_id: incId,
          resource_id: record.get('inc_resource_id'),
          window_start: record.get('inc_window_start'),
          window_end: record.get('inc_window_end'),
          event_count: record.get('inc_event_count'),
          severity: record.get('inc_severity'),
        };
      }

      // Generate recommendation
      rcaResult.recommendation = this.generateRecommendation(rcaResult);

      logger.info(`RCA completed for event ${query.event_id}: ${rcaResult.potential_causes.length} causes found`);

      return rcaResult;
    } catch (error) {
      logger.error('RCA query failed:', error);
      throw error;
    } finally {
      await session.close();
    }
  }

  async getRCAByResource(resourceUid: string, timeWindowHours = 24, severities?: string[]): Promise<RCAResult[]> {
    const session = db.getSession();

    try {
      const cypher = `
        MATCH (r:Resource {uid: $resourceUid})<-[:ABOUT]-(e:Episodic)
        WHERE e.event_time >= datetime() - duration({hours: $timeWindowHours})
          ${severities && severities.length > 0 ? 'AND e.severity IN $severities' : ''}
        RETURN e.eid as event_id
        ORDER BY e.event_time DESC
        LIMIT 50
      `;

      const result = await session.run(cypher, { resourceUid, timeWindowHours, severities });

      const rcaResults: RCAResult[] = [];
      for (const record of result.records) {
        const eventId = record.get('event_id');
        try {
          const rca = await this.performRCA({ event_id: eventId });
          rcaResults.push(rca);
        } catch (error) {
          logger.warn(`Failed to get RCA for event ${eventId}:`, error);
        }
      }

      return rcaResults;
    } finally {
      await session.close();
    }
  }

  async bulkRCA(eventIds: string[], minConfidence = 0.6): Promise<RCAResult[]> {
    const results: RCAResult[] = [];

    for (const eventId of eventIds) {
      try {
        const rca = await this.performRCA({ event_id: eventId, min_confidence: minConfidence });
        results.push(rca);
      } catch (error) {
        logger.warn(`Failed to get RCA for event ${eventId}:`, error);
      }
    }

    return results;
  }

  private parseCauses(causesData: any[]): Cause[] {
    if (!Array.isArray(causesData)) return [];

    return causesData
      .filter(c => c.event_id != null)
      .map(c => ({
        event_id: c.event_id,
        event_time: c.event_time,
        reason: c.reason,
        message: c.message,
        severity: c.severity,
        confidence: parseFloat(c.confidence) || 0,
        hops: parseInt(c.hops) || 0,
        temporal_score: parseFloat(c.temporal_score) || 0,
        distance_score: parseFloat(c.distance_score) || 0,
        domain_score: parseFloat(c.domain_score) || 0,
        subject: {
          rid: c.subject_rid,
          kind: c.subject_kind,
          name: c.subject_name,
          namespace: c.subject_ns,
        },
        explanation: this.generateCauseExplanation(c),
      }))
      .sort((a, b) => b.confidence - a.confidence);
  }

  private parseResources(resourcesData: any[]): ResourceInfo[] {
    if (!Array.isArray(resourcesData)) return [];

    return resourcesData
      .filter(r => r.rid != null)
      .map(r => ({
        rid: r.rid,
        kind: r.kind,
        name: r.name,
        namespace: r.ns,
      }));
  }

  private parseTimeline(timelineData: any[]): TimelineEvent[] {
    if (!Array.isArray(timelineData)) return [];

    return timelineData
      .filter(t => t.event_time != null)
      .map(t => ({
        event_time: t.event_time,
        reason: t.reason,
        severity: t.severity,
        message: t.message,
        resource: t.resource,
      }))
      .sort((a, b) => new Date(a.event_time).getTime() - new Date(b.event_time).getTime());
  }

  private parseLabels(labelsJson: string): Record<string, string> {
    try {
      return labelsJson ? JSON.parse(labelsJson) : {};
    } catch {
      return {};
    }
  }

  private generateCauseExplanation(cause: any): string {
    const confidence = parseFloat(cause.confidence) || 0;
    const hops = parseInt(cause.hops) || 0;

    if (confidence >= 0.9) {
      return `High confidence: ${cause.reason} likely caused this issue (${hops} hop${hops !== 1 ? 's' : ''} away)`;
    } else if (confidence >= 0.7) {
      return `Moderate confidence: ${cause.reason} may have contributed (${hops} hop${hops !== 1 ? 's' : ''} away)`;
    } else {
      return `Possible cause: ${cause.reason} (${hops} hop${hops !== 1 ? 's' : ''} away)`;
    }
  }

  private generateRecommendation(rca: RCAResult): any {
    // Generate basic recommendations based on event reason
    const reason = rca.reason.toLowerCase();

    if (reason.includes('oom') || reason.includes('memory')) {
      return {
        type: 'resource_adjustment',
        action: 'Increase memory limits',
        details: {
          reason: 'Memory-related issue detected',
          suggested_action: 'Review memory usage patterns and increase limits if necessary',
        },
        confidence: 0.85,
        priority: 'high',
      };
    } else if (reason.includes('crash') || reason.includes('backoff')) {
      return {
        type: 'investigation',
        action: 'Investigate application logs',
        details: {
          reason: 'Application crash detected',
          suggested_action: 'Check application logs for errors and exceptions',
        },
        confidence: 0.75,
        priority: 'high',
      };
    } else if (reason.includes('image') || reason.includes('pull')) {
      return {
        type: 'configuration',
        action: 'Verify image configuration',
        details: {
          reason: 'Image pull issue detected',
          suggested_action: 'Check image name, registry credentials, and network connectivity',
        },
        confidence: 0.9,
        priority: 'high',
      };
    }

    return {
      type: 'investigation',
      action: 'Review event details',
      details: {
        reason: 'Event detected',
        suggested_action: 'Review event details and correlate with system state',
      },
      confidence: 0.5,
      priority: 'medium',
    };
  }
}

export const rcaService = new RCAService();
