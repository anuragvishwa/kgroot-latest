/**
 * Resources Routes
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { resourcesService, ResourceFilters } from '../services/resources.service';
import { PaginationParams } from '../types';
import { ValidationError } from '../utils/errors';

export async function resourcesRoutes(fastify: FastifyInstance) {
  // GET /resources - List resources with filters
  fastify.get<{
    Querystring: {
      kind?: string;
      namespace?: string;
      labels?: string;
      has_incidents?: string;
      has_recent_events?: string;
      time_window_hours?: string;
      page?: string;
      page_size?: string;
      sort?: string;
      order?: string;
    };
  }>('/resources', async (request, reply) => {
    const query = request.query;

    // Parse filters
    const filters: ResourceFilters = {};

    if (query.kind) {
      filters.kind = query.kind.split(',');
    }

    if (query.namespace) {
      filters.namespace = query.namespace.split(',');
    }

    if (query.labels) {
      // Parse labels in format: key1=value1,key2=value2
      try {
        const labelPairs = query.labels.split(',');
        const labels: Record<string, string> = {};
        for (const pair of labelPairs) {
          const [key, value] = pair.split('=');
          if (!key || !value) {
            throw new ValidationError('labels must be in format: key1=value1,key2=value2');
          }
          labels[key] = value;
        }
        filters.labels = labels;
      } catch (error) {
        throw new ValidationError('labels must be in format: key1=value1,key2=value2');
      }
    }

    if (query.has_incidents) {
      filters.has_incidents = query.has_incidents === 'true';
    }

    if (query.has_recent_events) {
      filters.has_recent_events = query.has_recent_events === 'true';
    }

    if (query.time_window_hours) {
      const timeWindowHours = parseInt(query.time_window_hours, 10);
      if (isNaN(timeWindowHours) || timeWindowHours < 1) {
        throw new ValidationError('time_window_hours must be a positive integer');
      }
      filters.time_window_hours = timeWindowHours;
    }

    // Parse pagination
    const pagination: PaginationParams = {};

    if (query.page) {
      const page = parseInt(query.page, 10);
      if (isNaN(page) || page < 1) {
        throw new ValidationError('page must be a positive integer');
      }
      pagination.page = page;
    }

    if (query.page_size) {
      const pageSize = parseInt(query.page_size, 10);
      if (isNaN(pageSize) || pageSize < 1 || pageSize > 100) {
        throw new ValidationError('page_size must be between 1 and 100');
      }
      pagination.page_size = pageSize;
    }

    if (query.sort) {
      pagination.sort = query.sort;
    }

    if (query.order) {
      if (!['asc', 'desc'].includes(query.order)) {
        throw new ValidationError('order must be either asc or desc');
      }
      pagination.order = query.order as 'asc' | 'desc';
    }

    const result = await resourcesService.listResources(filters, pagination);
    return reply.code(200).send(result);
  });

  // GET /resources/:resource_uid - Get resource details
  fastify.get<{ Params: { resource_uid: string } }>(
    '/resources/:resource_uid',
    async (request, reply) => {
      const { resource_uid } = request.params;

      if (!resource_uid) {
        throw new ValidationError('resource_uid is required');
      }

      const resource = await resourcesService.getResourceById(resource_uid);
      return reply.code(200).send(resource);
    }
  );

  // GET /resources/:resource_uid/health - Get resource health
  fastify.get<{ Params: { resource_uid: string } }>(
    '/resources/:resource_uid/health',
    async (request, reply) => {
      const { resource_uid } = request.params;

      if (!resource_uid) {
        throw new ValidationError('resource_uid is required');
      }

      const health = await resourcesService.getResourceHealth(resource_uid);
      return reply.code(200).send(health);
    }
  );
}
