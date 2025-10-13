/**
 * Authentication Middleware
 */

import { FastifyRequest, FastifyReply } from 'fastify';
import { config } from '../config';
import { UnauthorizedError } from '../utils/errors';

export async function authMiddleware(request: FastifyRequest, reply: FastifyReply) {
  // Skip auth if disabled
  if (!config.auth.enabled) {
    return;
  }

  // Get API key from header
  const apiKey = request.headers[config.auth.apiKeyHeader.toLowerCase()] as string;

  if (!apiKey) {
    throw new UnauthorizedError('API key is required');
  }

  // Validate API key
  if (!config.auth.apiKeys.includes(apiKey)) {
    throw new UnauthorizedError('Invalid API key');
  }

  // Attach API key to request for logging/tracking
  (request as any).apiKey = apiKey;
}
