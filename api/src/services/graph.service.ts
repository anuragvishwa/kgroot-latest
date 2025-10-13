/**
 * Graph Service - Graph queries, topology, stats
 */

import { db } from '../config/database';
import { GraphStats, ResourceInfo, EventInfo, GraphUpdate } from '../types';
import { NotFoundError } from '../utils/errors';
import { logger } from '../utils/logger';

export class GraphService {
  async getStats(): Promise<GraphStats> {
    const session = db.getSession();

    try {
      // Get basic counts
      const countsResult = await session.run(`
        MATCH (r:Resource)
        WITH count(r) as resources
        MATCH (e:Episodic)
        WITH resources, count(e) as events
        MATCH (inc:Incident)
        WITH resources, events, count(inc) as incidents
        MATCH ()-[rel]->()
        WITH resources, events, incidents, count(rel) as edges
        RETURN resources, events, incidents, edges
      `);

      const countsRecord = countsResult.records[0];
      const totalResources = countsRecord.get('resources').toNumber();
      const totalEvents = countsRecord.get('events').toNumber();
      const totalIncidents = countsRecord.get('incidents').toNumber();
      const totalEdges = countsRecord.get('edges').toNumber();

      // Get resources by kind
      const resourcesByKindResult = await session.run(`
        MATCH (r:Resource)
        RETURN r.kind as kind, count(r) as count
        ORDER BY count DESC
      `);

      const resourcesByKind: Record<string, number> = {};
      resourcesByKindResult.records.forEach(record => {
        resourcesByKind[record.get('kind')] = record.get('count').toNumber();
      });

      // Get events by severity
      const eventsBySeverityResult = await session.run(`
        MATCH (e:Episodic)
        RETURN e.severity as severity, count(e) as count
      `);

      const eventsBySeverity: Record<string, number> = {};
      eventsBySeverityResult.records.forEach(record => {
        eventsBySeverity[record.get('severity')] = record.get('count').toNumber();
      });

      // Get edges by type
      const edgesByTypeResult = await session.run(`
        MATCH ()-[rel]->()
        RETURN type(rel) as rel_type, count(rel) as count
        ORDER BY count DESC
      `);

      const edgesByType: Record<string, number> = {};
      edgesByTypeResult.records.forEach(record => {
        edgesByType[record.get('rel_type')] = record.get('count').toNumber();
      });

      // Get incidents by status
      const incidentsByStatusResult = await session.run(`
        MATCH (inc:Incident)
        RETURN inc.status as status, count(inc) as count
      `);

      const incidentCounts = {
        total: totalIncidents,
        open: 0,
        acknowledged: 0,
        resolved: 0,
      };

      incidentsByStatusResult.records.forEach(record => {
        const status = record.get('status') || 'open';
        const count = record.get('count').toNumber();
        if (status in incidentCounts) {
          incidentCounts[status as keyof typeof incidentCounts] = count;
        }
      });

      return {
        timestamp: new Date().toISOString(),
        graph: {
          resources: {
            total: totalResources,
            by_kind: resourcesByKind,
          },
          events: {
            total: totalEvents,
            by_severity: eventsBySeverity,
          },
          incidents: incidentCounts,
          edges: {
            total: totalEdges,
            by_type: edgesByType,
          },
        },
      };
    } finally {
      await session.close();
    }
  }

  async getResourceTopology(resourceUid: string, depth = 2): Promise<any> {
    const session = db.getSession();

    try {
      const cypher = `
        MATCH (r:Resource {uid: $resourceUid})
        OPTIONAL MATCH path = (r)-[*1..${depth}]-(connected:Resource)
        WITH r, collect(DISTINCT {
          target: {
            uid: connected.uid,
            rid: connected.rid,
            kind: connected.kind,
            name: connected.name,
            namespace: connected.ns
          },
          path: [rel in relationships(path) | type(rel)]
        }) as relationships
        RETURN
          r.uid as uid,
          r.rid as rid,
          r.kind as kind,
          r.name as name,
          r.ns as namespace,
          relationships
      `;

      const result = await session.run(cypher, { resourceUid });

      if (result.records.length === 0) {
        throw new NotFoundError('Resource', resourceUid);
      }

      const record = result.records[0];

      return {
        resource: {
          uid: record.get('uid'),
          rid: record.get('rid'),
          kind: record.get('kind'),
          name: record.get('name'),
          namespace: record.get('namespace'),
        },
        relationships: record.get('relationships'),
        depth,
      };
    } finally {
      await session.close();
    }
  }

  async getResourceEvents(
    resourceUid: string,
    startTime?: string,
    endTime?: string,
    severity?: string[],
    limit = 100
  ): Promise<{ resource_uid: string; events: EventInfo[]; total_count: number }> {
    const session = db.getSession();

    try {
      const filters = [];
      const params: any = { resourceUid, limit };

      if (startTime) {
        filters.push('e.event_time >= datetime($startTime)');
        params.startTime = startTime;
      }

      if (endTime) {
        filters.push('e.event_time <= datetime($endTime)');
        params.endTime = endTime;
      }

      if (severity && severity.length > 0) {
        filters.push('e.severity IN $severity');
        params.severity = severity;
      }

      const filterClause = filters.length > 0 ? `AND ${filters.join(' AND ')}` : '';

      const cypher = `
        MATCH (r:Resource {uid: $resourceUid})<-[:ABOUT]-(e:Episodic)
        WHERE true ${filterClause}
        WITH e
        ORDER BY e.event_time DESC
        LIMIT $limit
        RETURN
          e.eid as event_id,
          toString(e.event_time) as event_time,
          e.reason as reason,
          e.message as message,
          e.severity as severity
      `;

      const result = await session.run(cypher, params);

      const events: EventInfo[] = result.records.map(record => ({
        event_id: record.get('event_id'),
        event_time: record.get('event_time'),
        reason: record.get('reason'),
        message: record.get('message'),
        severity: record.get('severity'),
      }));

      return {
        resource_uid: resourceUid,
        events,
        total_count: events.length,
      };
    } finally {
      await session.close();
    }
  }

  async applyGraphUpdate(update: GraphUpdate): Promise<{ status: string; updated: number }> {
    const session = db.getSession();
    let updateCount = 0;

    try {
      // Apply resource updates
      if (update.resources) {
        for (const res of update.resources) {
          if (res.action === 'CREATE' || res.action === 'UPDATE') {
            await session.run(
              `
              MERGE (r:Resource {uid: $uid})
              SET r.kind = $kind,
                  r.name = $name,
                  r.ns = $ns,
                  r.rid = $rid,
                  r.labels_json = $labels,
                  r.status_json = $status,
                  r.updated_at = datetime()
            `,
              {
                uid: res.uid,
                kind: res.kind,
                name: res.name,
                ns: res.namespace,
                rid: `${res.kind.toLowerCase()}:${res.namespace || 'default'}:${res.name}`,
                labels: JSON.stringify(res.labels || {}),
                status: JSON.stringify(res.status || {}),
              }
            );
            updateCount++;
          } else if (res.action === 'DELETE') {
            await session.run('MATCH (r:Resource {uid: $uid}) DETACH DELETE r', { uid: res.uid });
            updateCount++;
          }
        }
      }

      // Apply edge updates
      if (update.edges) {
        for (const edge of update.edges) {
          if (edge.action === 'CREATE') {
            await session.run(
              `
              MATCH (from:Resource {uid: $from})
              MATCH (to:Resource {uid: $to})
              MERGE (from)-[rel:${edge.type}]->(to)
            `,
              { from: edge.from, to: edge.to }
            );
            updateCount++;
          } else if (edge.action === 'DELETE') {
            await session.run(
              `
              MATCH (from:Resource {uid: $from})-[rel:${edge.type}]->(to:Resource {uid: $to})
              DELETE rel
            `,
              { from: edge.from, to: edge.to }
            );
            updateCount++;
          }
        }
      }

      logger.info(`Graph update applied: ${updateCount} changes`);

      return { status: 'ok', updated: updateCount };
    } finally {
      await session.close();
    }
  }

  async getTimeline(
    startTime: string,
    endTime: string,
    namespaces?: string[],
    severity?: string[],
    includeIncidents = false
  ): Promise<EventInfo[]> {
    const session = db.getSession();

    try {
      const filters = ['e.event_time >= datetime($startTime)', 'e.event_time <= datetime($endTime)'];
      const params: any = { startTime, endTime };

      if (namespaces && namespaces.length > 0) {
        filters.push('subj.ns IN $namespaces');
        params.namespaces = namespaces;
      }

      if (severity && severity.length > 0) {
        filters.push('e.severity IN $severity');
        params.severity = severity;
      }

      const cypher = `
        MATCH (e:Episodic)-[:ABOUT]->(subj:Resource)
        WHERE ${filters.join(' AND ')}
        ${includeIncidents ? 'OPTIONAL MATCH (e)-[:PART_OF]->(inc:Incident)' : ''}
        RETURN
          e.eid as event_id,
          toString(e.event_time) as event_time,
          e.reason as reason,
          e.message as message,
          e.severity as severity,
          subj.rid as subj_rid,
          subj.kind as subj_kind,
          subj.name as subj_name,
          subj.ns as subj_ns
          ${includeIncidents ? ', inc.incident_id as incident_id' : ''}
        ORDER BY e.event_time DESC
        LIMIT 1000
      `;

      const result = await session.run(cypher, params);

      return result.records.map(record => ({
        event_id: record.get('event_id'),
        event_time: record.get('event_time'),
        reason: record.get('reason'),
        message: record.get('message'),
        severity: record.get('severity'),
        subject: {
          rid: record.get('subj_rid'),
          kind: record.get('subj_kind'),
          name: record.get('subj_name'),
          namespace: record.get('subj_ns'),
        },
      }));
    } finally {
      await session.close();
    }
  }
}

export const graphService = new GraphService();
