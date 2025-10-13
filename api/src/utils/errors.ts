/**
 * Custom Error Classes
 */

export class APIError extends Error {
  constructor(
    public statusCode: number,
    public code: string,
    message: string,
    public details?: Record<string, any>
  ) {
    super(message);
    this.name = 'APIError';
    Error.captureStackTrace(this, this.constructor);
  }

  toJSON() {
    return {
      error: {
        code: this.code,
        message: this.message,
        details: this.details,
        timestamp: new Date().toISOString(),
      },
    };
  }
}

export class NotFoundError extends APIError {
  constructor(resource: string, identifier: string) {
    super(404, 'RESOURCE_NOT_FOUND', `${resource} '${identifier}' not found`);
  }
}

export class ValidationError extends APIError {
  constructor(message: string, details?: Record<string, any>) {
    super(400, 'VALIDATION_ERROR', message, details);
  }
}

export class UnauthorizedError extends APIError {
  constructor(message = 'Unauthorized') {
    super(401, 'UNAUTHORIZED', message);
  }
}

export class ForbiddenError extends APIError {
  constructor(message = 'Forbidden') {
    super(403, 'FORBIDDEN', message);
  }
}

export class RateLimitError extends APIError {
  constructor(message = 'Rate limit exceeded') {
    super(429, 'RATE_LIMIT_EXCEEDED', message);
  }
}

export class InternalServerError extends APIError {
  constructor(message = 'Internal server error', details?: Record<string, any>) {
    super(500, 'INTERNAL_ERROR', message, details);
  }
}

export class ServiceUnavailableError extends APIError {
  constructor(service: string) {
    super(503, 'SERVICE_UNAVAILABLE', `${service} is unavailable`);
  }
}
