/**
 * Graph Routes
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { graphService } from '../services/graph.service';
import { GraphUpdate } from '../types';

export async function graphRoutes(fastify: FastifyInstance) {
  // GET /graph/stats - Get graph statistics
  fastify.get('/graph/stats', async (request, reply) => {
    const stats = await graphService.getStats();
    return reply.code(200).send(stats);
  });

  // GET /graph/topology/:uid - Get resource topology
  fastify.get<{ Params: { uid: string }; Querystring: { depth?: string } }>(
    '/graph/topology/:uid',
    async (request, reply) => {
      const { uid } = request.params;
      const depth = request.query.depth ? parseInt(request.query.depth) : 2;

      const topology = await graphService.getResourceTopology(uid, depth);
      return reply.code(200).send(topology);
    }
  );

  // GET /graph/events/:uid - Get resource events
  fastify.get<{
    Params: { uid: string };
    Querystring: {
      start_time?: string;
      end_time?: string;
      severity?: string;
      limit?: string;
    };
  }>('/graph/events/:uid', async (request, reply) => {
    const { uid } = request.params;
    const { start_time, end_time, severity, limit } = request.query;

    const severityArray = severity ? severity.split(',') : undefined;
    const limitNum = limit ? parseInt(limit) : 100;

    const result = await graphService.getResourceEvents(
      uid,
      start_time,
      end_time,
      severityArray,
      limitNum
    );

    return reply.code(200).send(result);
  });

  // GET /graph/timeline - Get system timeline
  fastify.get<{
    Querystring: {
      start_time: string;
      end_time: string;
      namespaces?: string;
      severity?: string;
      include_incidents?: string;
    };
  }>('/graph/timeline', async (request, reply) => {
    const { start_time, end_time, namespaces, severity, include_incidents } = request.query;

    const namespacesArray = namespaces ? namespaces.split(',') : undefined;
    const severityArray = severity ? severity.split(',') : undefined;
    const includeIncidentsBool = include_incidents === 'true';

    const timeline = await graphService.getTimeline(
      start_time,
      end_time,
      namespacesArray,
      severityArray,
      includeIncidentsBool
    );

    return reply.code(200).send({
      start_time,
      end_time,
      events: timeline,
      total: timeline.length,
    });
  });

  // POST /graph/updates - Apply graph updates
  fastify.post<{ Body: GraphUpdate }>('/graph/updates', async (request, reply) => {
    const update = request.body;

    const result = await graphService.applyGraphUpdate(update);
    return reply.code(200).send(result);
  });
}
