/**
 * Search Routes
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { searchService } from '../services/search.service';
import { SemanticSearchQuery, CausalSearchQuery } from '../types';
import { ValidationError } from '../utils/errors';

export async function searchRoutes(fastify: FastifyInstance) {
  // POST /search/semantic - Semantic search
  fastify.post<{ Body: SemanticSearchQuery }>(
    '/search/semantic',
    async (request, reply) => {
      const body = request.body;

      if (!body.query) {
        throw new ValidationError('query is required');
      }

      const result = await searchService.semanticSearch(body);
      return reply.code(200).send(result);
    }
  );

  // POST /search/causal - Causal search
  fastify.post<{ Body: CausalSearchQuery }>(
    '/search/causal',
    async (request, reply) => {
      const body = request.body;

      if (!body.query) {
        throw new ValidationError('query is required');
      }

      const result = await searchService.causalSearch(body);
      return reply.code(200).send(result);
    }
  );

  // POST /search/similar - Find similar events
  fastify.post<{ Body: { event_id: string; top_k?: number; time_window_days?: number } }>(
    '/search/similar',
    async (request, reply) => {
      const { event_id, top_k, time_window_days } = request.body;

      if (!event_id) {
        throw new ValidationError('event_id is required');
      }

      const results = await searchService.similarEvents(event_id, top_k, time_window_days);
      return reply.code(200).send({
        event_id,
        results,
        total: results.length,
      });
    }
  );
}
