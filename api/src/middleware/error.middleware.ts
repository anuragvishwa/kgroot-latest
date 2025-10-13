/**
 * Error Handling Middleware
 */

import { FastifyError, FastifyRequest, FastifyReply } from 'fastify';
import { APIError } from '../utils/errors';
import { logger } from '../utils/logger';

export async function errorHandler(
  error: FastifyError | APIError,
  request: FastifyRequest,
  reply: FastifyReply
) {
  // Handle custom API errors
  if (error instanceof APIError) {
    logger.warn(`API Error: ${error.code} - ${error.message}`, {
      code: error.code,
      statusCode: error.statusCode,
      path: request.url,
      method: request.method,
    });

    return reply.code(error.statusCode).send(error.toJSON());
  }

  // Handle Fastify validation errors
  if (error.validation) {
    logger.warn('Validation error:', {
      validation: error.validation,
      path: request.url,
      method: request.method,
    });

    return reply.code(400).send({
      error: {
        code: 'VALIDATION_ERROR',
        message: error.message,
        details: error.validation,
        timestamp: new Date().toISOString(),
      },
    });
  }

  // Handle unexpected errors
  logger.error('Unexpected error:', {
    error: error.message,
    stack: error.stack,
    path: request.url,
    method: request.method,
  });

  return reply.code(error.statusCode || 500).send({
    error: {
      code: 'INTERNAL_ERROR',
      message: 'An unexpected error occurred',
      timestamp: new Date().toISOString(),
    },
  });
}
