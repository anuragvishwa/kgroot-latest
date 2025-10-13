/**
 * Main Server - Knowledge Graph RCA API
 * Production-ready TypeScript API server with Fastify
 */

import Fastify from 'fastify';
import cors from '@fastify/cors';
import helmet from '@fastify/helmet';
import rateLimit from '@fastify/rate-limit';
import swagger from '@fastify/swagger';
import swaggerUI from '@fastify/swagger-ui';

import { config } from './config';
import { db } from './config/database';
import { logger } from './utils/logger';
import { errorHandler } from './middleware/error.middleware';
import { registerRoutes } from './routes';

const startTime = Date.now();

async function buildServer() {
  const fastify = Fastify({
    logger: logger as any,
    requestIdHeader: 'x-request-id',
    requestIdLogLabel: 'reqId',
  });

  // Register plugins
  await fastify.register(cors, {
    origin: config.cors.origin,
    credentials: config.cors.credentials,
  });

  await fastify.register(helmet, {
    contentSecurityPolicy: false,
  });

  await fastify.register(rateLimit, {
    max: config.rateLimit.max,
    timeWindow: config.rateLimit.windowMs,
    errorResponseBuilder: () => ({
      error: {
        code: 'RATE_LIMIT_EXCEEDED',
        message: 'Rate limit exceeded. Please try again later.',
        timestamp: new Date().toISOString(),
      },
    }),
  });

  // Swagger documentation
  await fastify.register(swagger, {
    openapi: {
      info: {
        title: 'Knowledge Graph RCA API',
        description: 'Production-ready API for Root Cause Analysis, Semantic Search, and Graph Queries',
        version: '1.0.0',
      },
      servers: [
        {
          url: `http://localhost:${config.port}`,
          description: 'Development server',
        },
      ],
      components: {
        securitySchemes: {
          apiKey: {
            type: 'apiKey',
            name: 'X-API-Key',
            in: 'header',
          },
        },
      },
    },
  });

  await fastify.register(swaggerUI, {
    routePrefix: '/docs',
    uiConfig: {
      docExpansion: 'list',
      deepLinking: true,
    },
  });

  // Error handler
  fastify.setErrorHandler(errorHandler);

  // Register routes
  await registerRoutes(fastify);

  // Root endpoint
  fastify.get('/', async (request, reply) => {
    return reply.send({
      service: 'Knowledge Graph RCA API',
      version: '1.0.0',
      status: 'running',
      uptime: Math.floor((Date.now() - startTime) / 1000),
      endpoints: {
        docs: '/docs',
        health: '/healthz',
        api: '/api/v1',
      },
    });
  });

  return fastify;
}

async function start() {
  try {
    // Connect to database
    logger.info('🔌 Connecting to Neo4j...');
    await db.connect();

    // Build server
    const fastify = await buildServer();

    // Start server
    await fastify.listen({
      port: config.port,
      host: config.host,
    });

    logger.info('🚀 Knowledge Graph RCA API Server Started');
    logger.info(`📝 API Documentation: http://${config.host}:${config.port}/docs`);
    logger.info(`🏥 Health Check: http://${config.host}:${config.port}/healthz`);
    logger.info(`🌐 Environment: ${config.env}`);

    // Graceful shutdown
    const shutdown = async (signal: string) => {
      logger.info(`\n${signal} received, shutting down gracefully...`);

      try {
        await fastify.close();
        await db.close();
        logger.info('✅ Server shut down successfully');
        process.exit(0);
      } catch (err) {
        logger.error('Error during shutdown:', err);
        process.exit(1);
      }
    };

    process.on('SIGTERM', () => shutdown('SIGTERM'));
    process.on('SIGINT', () => shutdown('SIGINT'));
  } catch (error) {
    logger.error('❌ Failed to start server:', error);
    process.exit(1);
  }
}

// Start server if this is the main module
if (require.main === module) {
  start();
}

export { buildServer, start };
