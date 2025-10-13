/**
 * Health and Metrics Routes
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { db } from '../config/database';
import { graphService } from '../services/graph.service';
import { logger } from '../utils/logger';

// Track service start time for uptime calculation
const serviceStartTime = Date.now();

export async function healthRoutes(fastify: FastifyInstance) {
  // GET /healthz - Health check
  fastify.get('/healthz', async (request: FastifyRequest, reply: FastifyReply) => {
    try {
      // Check Neo4j connection
      const session = db.getSession();
      try {
        await session.run('RETURN 1');
      } finally {
        await session.close();
      }

      return reply.code(200).send({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        uptime_seconds: Math.floor((Date.now() - serviceStartTime) / 1000),
        components: {
          neo4j: 'up',
        },
      });
    } catch (error) {
      logger.error('Health check failed:', error);
      return reply.code(503).send({
        status: 'unhealthy',
        timestamp: new Date().toISOString(),
        components: {
          neo4j: 'down',
        },
        error: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  });

  // GET /readyz - Readiness check
  fastify.get('/readyz', async (request: FastifyRequest, reply: FastifyReply) => {
    try {
      // Check Neo4j connection and verify we can query
      const session = db.getSession();
      try {
        // Simple query to ensure the database is ready
        const result = await session.run('MATCH (n) RETURN count(n) as count LIMIT 1');
        const count = result.records[0]?.get('count').toNumber() || 0;

        return reply.code(200).send({
          status: 'ready',
          timestamp: new Date().toISOString(),
          components: {
            neo4j: 'ready',
          },
          info: {
            node_count: count,
          },
        });
      } finally {
        await session.close();
      }
    } catch (error) {
      logger.error('Readiness check failed:', error);
      return reply.code(503).send({
        status: 'not_ready',
        timestamp: new Date().toISOString(),
        components: {
          neo4j: 'not_ready',
        },
        error: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  });

  // GET /metrics - Prometheus metrics (simple text format)
  fastify.get('/metrics', async (request: FastifyRequest, reply: FastifyReply) => {
    try {
      // Get graph stats for metrics
      const stats = await graphService.getStats();

      // Build Prometheus-style metrics
      const metrics: string[] = [];

      // Help and type declarations
      metrics.push('# HELP kg_rca_resources_total Total number of resources in the knowledge graph');
      metrics.push('# TYPE kg_rca_resources_total gauge');
      metrics.push(`kg_rca_resources_total ${stats.graph.resources.total}`);
      metrics.push('');

      metrics.push('# HELP kg_rca_events_total Total number of events in the knowledge graph');
      metrics.push('# TYPE kg_rca_events_total gauge');
      metrics.push(`kg_rca_events_total ${stats.graph.events.total}`);
      metrics.push('');

      metrics.push('# HELP kg_rca_incidents_total Total number of incidents');
      metrics.push('# TYPE kg_rca_incidents_total gauge');
      metrics.push(`kg_rca_incidents_total ${stats.graph.incidents.total}`);
      metrics.push('');

      metrics.push('# HELP kg_rca_incidents_by_status Number of incidents by status');
      metrics.push('# TYPE kg_rca_incidents_by_status gauge');
      metrics.push(`kg_rca_incidents_by_status{status="open"} ${stats.graph.incidents.open}`);
      metrics.push(`kg_rca_incidents_by_status{status="acknowledged"} ${stats.graph.incidents.acknowledged}`);
      metrics.push(`kg_rca_incidents_by_status{status="resolved"} ${stats.graph.incidents.resolved}`);
      metrics.push('');

      metrics.push('# HELP kg_rca_edges_total Total number of edges in the knowledge graph');
      metrics.push('# TYPE kg_rca_edges_total gauge');
      metrics.push(`kg_rca_edges_total ${stats.graph.edges.total}`);
      metrics.push('');

      // Resources by kind
      metrics.push('# HELP kg_rca_resources_by_kind Number of resources by kind');
      metrics.push('# TYPE kg_rca_resources_by_kind gauge');
      Object.entries(stats.graph.resources.by_kind).forEach(([kind, count]) => {
        metrics.push(`kg_rca_resources_by_kind{kind="${kind}"} ${count}`);
      });
      metrics.push('');

      // Events by severity
      metrics.push('# HELP kg_rca_events_by_severity Number of events by severity');
      metrics.push('# TYPE kg_rca_events_by_severity gauge');
      Object.entries(stats.graph.events.by_severity).forEach(([severity, count]) => {
        metrics.push(`kg_rca_events_by_severity{severity="${severity}"} ${count}`);
      });
      metrics.push('');

      // Edges by type
      metrics.push('# HELP kg_rca_edges_by_type Number of edges by relationship type');
      metrics.push('# TYPE kg_rca_edges_by_type gauge');
      Object.entries(stats.graph.edges.by_type).forEach(([type, count]) => {
        metrics.push(`kg_rca_edges_by_type{type="${type}"} ${count}`);
      });
      metrics.push('');

      // Service uptime
      metrics.push('# HELP kg_rca_uptime_seconds Service uptime in seconds');
      metrics.push('# TYPE kg_rca_uptime_seconds counter');
      metrics.push(`kg_rca_uptime_seconds ${Math.floor((Date.now() - serviceStartTime) / 1000)}`);
      metrics.push('');

      // Return as plain text
      return reply
        .code(200)
        .header('Content-Type', 'text/plain; version=0.0.4')
        .send(metrics.join('\n'));
    } catch (error) {
      logger.error('Metrics collection failed:', error);
      return reply.code(500).send({
        error: 'Failed to collect metrics',
        message: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  });
}
