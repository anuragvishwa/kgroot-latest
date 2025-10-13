/**
 * RCA Routes
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { rcaService } from '../services/rca.service';
import { RCAQuery } from '../types';
import { ValidationError } from '../utils/errors';

export async function rcaRoutes(fastify: FastifyInstance) {
  // POST /rca - Perform RCA
  fastify.post('/rca', async (request: FastifyRequest, reply: FastifyReply) => {
    const body = request.body as RCAQuery;

    if (!body.event_id) {
      throw new ValidationError('event_id is required');
    }

    const result = await rcaService.performRCA(body);
    return reply.code(200).send(result);
  });

  // GET /rca/:event_id - Get RCA by event ID
  fastify.get<{ Params: { event_id: string } }>(
    '/rca/:event_id',
    async (request, reply) => {
      const { event_id } = request.params;

      const result = await rcaService.performRCA({ event_id });
      return reply.code(200).send(result);
    }
  );

  // POST /rca/resource - Get RCA by resource
  fastify.post<{
    Body: { resource_uid: string; time_window_hours?: number; severity?: string[] };
  }>('/rca/resource', async (request, reply) => {
    const { resource_uid, time_window_hours, severity } = request.body;

    if (!resource_uid) {
      throw new ValidationError('resource_uid is required');
    }

    const results = await rcaService.getRCAByResource(resource_uid, time_window_hours, severity);
    return reply.code(200).send({
      resource_uid,
      analysis_count: results.length,
      analyses: results,
    });
  });

  // POST /rca/bulk - Bulk RCA
  fastify.post<{ Body: { event_ids: string[]; min_confidence?: number } }>(
    '/rca/bulk',
    async (request, reply) => {
      const { event_ids, min_confidence } = request.body;

      if (!event_ids || !Array.isArray(event_ids)) {
        throw new ValidationError('event_ids must be an array');
      }

      const results = await rcaService.bulkRCA(event_ids, min_confidence);
      return reply.code(200).send({
        total: event_ids.length,
        results,
      });
    }
  );
}
