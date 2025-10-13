/**
 * Request Logging Middleware
 */

import { FastifyRequest, FastifyReply } from 'fastify';
import { logger } from '../utils/logger';

export async function loggingMiddleware(request: FastifyRequest, reply: FastifyReply) {
  const startTime = Date.now();

  reply.addHook('onResponse', (request, reply, done) => {
    const duration = Date.now() - startTime;

    logger.info({
      method: request.method,
      url: request.url,
      statusCode: reply.statusCode,
      duration,
      userAgent: request.headers['user-agent'],
      ip: request.ip,
    });

    done();
  });
}
