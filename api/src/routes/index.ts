/**
 * Routes Index - Central route registration
 */

import { FastifyInstance } from 'fastify';
import { rcaRoutes } from './rca.routes';
import { searchRoutes } from './search.routes';
import { graphRoutes } from './graph.routes';

export async function registerRoutes(fastify: FastifyInstance) {
  // Register all API routes under /api/v1 prefix
  await fastify.register(
    async (fastify) => {
      await fastify.register(rcaRoutes);
      await fastify.register(searchRoutes);
      await fastify.register(graphRoutes);

      // Import and register other routes dynamically
      try {
        const { incidentsRoutes } = await import('./incidents.routes');
        await fastify.register(incidentsRoutes);
      } catch (err) {
        console.warn('incidents.routes not found, skipping');
      }

      try {
        const { resourcesRoutes } = await import('./resources.routes');
        await fastify.register(resourcesRoutes);
      } catch (err) {
        console.warn('resources.routes not found, skipping');
      }
    },
    { prefix: '/api/v1' }
  );

  // Register health routes (no prefix)
  try {
    const { healthRoutes } = await import('./health.routes');
    await fastify.register(healthRoutes);
  } catch (err) {
    console.warn('health.routes not found, skipping');
  }
}
