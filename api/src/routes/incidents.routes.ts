/**
 * Incidents Routes
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { incidentsService, IncidentFilters } from '../services/incidents.service';
import { PaginationParams } from '../types';
import { ValidationError } from '../utils/errors';

export async function incidentsRoutes(fastify: FastifyInstance) {
  // GET /incidents - List incidents with filters
  fastify.get<{
    Querystring: {
      status?: string;
      severity?: string;
      namespace?: string;
      assignee?: string;
      resource_kind?: string;
      tags?: string;
      start_time?: string;
      end_time?: string;
      page?: string;
      page_size?: string;
      sort?: string;
      order?: string;
    };
  }>('/incidents', async (request, reply) => {
    const query = request.query;

    // Parse filters
    const filters: IncidentFilters = {};

    if (query.status) {
      filters.status = query.status.split(',');
    }

    if (query.severity) {
      filters.severity = query.severity.split(',');
    }

    if (query.namespace) {
      filters.namespace = query.namespace.split(',');
    }

    if (query.assignee) {
      filters.assignee = query.assignee;
    }

    if (query.resource_kind) {
      filters.resource_kind = query.resource_kind.split(',');
    }

    if (query.tags) {
      filters.tags = query.tags.split(',');
    }

    if (query.start_time) {
      filters.start_time = query.start_time;
    }

    if (query.end_time) {
      filters.end_time = query.end_time;
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

    const result = await incidentsService.listIncidents(filters, pagination);
    return reply.code(200).send(result);
  });

  // GET /incidents/:incident_id - Get incident details
  fastify.get<{ Params: { incident_id: string } }>(
    '/incidents/:incident_id',
    async (request, reply) => {
      const { incident_id } = request.params;

      if (!incident_id) {
        throw new ValidationError('incident_id is required');
      }

      const incident = await incidentsService.getIncidentById(incident_id);
      return reply.code(200).send(incident);
    }
  );

  // PATCH /incidents/:incident_id - Update incident status
  fastify.patch<{
    Params: { incident_id: string };
    Body: {
      status?: 'open' | 'acknowledged' | 'resolved';
      assignee?: string;
      notes?: string;
      tags?: string[];
    };
  }>('/incidents/:incident_id', async (request, reply) => {
    const { incident_id } = request.params;
    const body = request.body;

    if (!incident_id) {
      throw new ValidationError('incident_id is required');
    }

    // Validate at least one field is provided
    if (
      body.status === undefined &&
      body.assignee === undefined &&
      body.notes === undefined &&
      body.tags === undefined
    ) {
      throw new ValidationError('At least one field (status, assignee, notes, tags) must be provided');
    }

    const updatedIncident = await incidentsService.updateIncidentStatus(
      incident_id,
      body.status,
      body.assignee,
      body.notes,
      body.tags
    );

    return reply.code(200).send(updatedIncident);
  });

  // GET /incidents/:incident_id/recommendations - Get recommendations
  fastify.get<{ Params: { incident_id: string } }>(
    '/incidents/:incident_id/recommendations',
    async (request, reply) => {
      const { incident_id } = request.params;

      if (!incident_id) {
        throw new ValidationError('incident_id is required');
      }

      const recommendations = await incidentsService.getIncidentRecommendations(incident_id);
      return reply.code(200).send({
        incident_id,
        recommendations,
        total: recommendations.length,
      });
    }
  );
}
