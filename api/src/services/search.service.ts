/**
 * Search Service - Semantic and Causal Search
 */

import { db } from '../config/database';
import { SemanticSearchQuery, SemanticSearchResult, CausalSearchQuery, CausalChain } from '../types';
import { logger } from '../utils/logger';

export class SearchService {
  async semanticSearch(query: SemanticSearchQuery): Promise<{
    query: string;
    results: SemanticSearchResult[];
    total_results: number;
    execution_time_ms: number;
  }> {
    const startTime = Date.now();
    const session = db.getSession();

    try {
      const topK = query.top_k || 10;
      const minSimilarity = query.min_similarity || 0.6;
      const timeWindowDays = query.time_window_days || 7;

      // Build filter conditions
      const filters = [];
      const params: any = {
        topK,
        minSimilarity,
        timeWindowDays,
        queryText: query.query.toLowerCase(),
      };

      if (query.filters?.severity && query.filters.severity.length > 0) {
        filters.push('e.severity IN $severities');
        params.severities = query.filters.severity;
      }

      if (query.filters?.kind && query.filters.kind.length > 0) {
        filters.push('subj.kind IN $kinds');
        params.kinds = query.filters.kind;
      }

      if (query.filters?.namespace && query.filters.namespace.length > 0) {
        filters.push('subj.ns IN $namespaces');
        params.namespaces = query.filters.namespace;
      }

      if (query.filters?.has_incident) {
        filters.push('EXISTS((e)-[:PART_OF]->(:Incident))');
      }

      const filterClause = filters.length > 0 ? `AND ${filters.join(' AND ')}` : '';

      // Simplified text search (in production, use vector embeddings)
      const cypher = `
        MATCH (e:Episodic)-[:ABOUT]->(subj:Resource)
        WHERE e.event_time >= datetime() - duration({days: $timeWindowDays})
          AND (toLower(e.reason) CONTAINS $queryText OR toLower(e.message) CONTAINS $queryText)
          ${filterClause}
        OPTIONAL MATCH (e)<-[:POTENTIAL_CAUSE]-(rootCause:Episodic)
        OPTIONAL MATCH (e)-[:PART_OF]->(inc:Incident)
        WITH e, subj,
             collect(DISTINCT rootCause.eid) as root_causes,
             inc.incident_id as incident_id,
             CASE
               WHEN toLower(e.reason) CONTAINS $queryText THEN 0.9
               ELSE 0.7
             END as similarity
        WHERE similarity >= $minSimilarity
        RETURN
          e.eid as event_id,
          e.reason as reason,
          e.message as message,
          e.severity as severity,
          toString(e.event_time) as event_time,
          subj.rid as subj_rid,
          subj.kind as subj_kind,
          subj.name as subj_name,
          subj.ns as subj_ns,
          similarity,
          root_causes,
          incident_id
        ORDER BY similarity DESC, e.event_time DESC
        LIMIT $topK
      `;

      const result = await session.run(cypher, params);

      const results: SemanticSearchResult[] = result.records.map(record => ({
        event_id: record.get('event_id'),
        reason: record.get('reason'),
        message: record.get('message'),
        severity: record.get('severity'),
        event_time: record.get('event_time'),
        subject: {
          rid: record.get('subj_rid'),
          kind: record.get('subj_kind'),
          name: record.get('subj_name'),
          namespace: record.get('subj_ns'),
        },
        similarity: record.get('similarity'),
        root_causes: record.get('root_causes') || [],
        incident: record.get('incident_id'),
        explanation: this.generateExplanation(query.query, record.get('reason'), record.get('similarity')),
      }));

      const executionTime = Date.now() - startTime;

      logger.info(`Semantic search completed: ${results.length} results in ${executionTime}ms`);

      return {
        query: query.query,
        results,
        total_results: results.length,
        execution_time_ms: executionTime,
      };
    } finally {
      await session.close();
    }
  }

  async causalSearch(query: CausalSearchQuery): Promise<{
    query: string;
    causal_chains: CausalChain[];
  }> {
    const session = db.getSession();

    try {
      const maxChainLength = query.max_chain_length || 5;
      const minConfidence = query.min_confidence || 0.5;

      // Find causal chains using POTENTIAL_CAUSE relationships
      const cypher = `
        MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..${maxChainLength}]->(effect:Episodic)
        WHERE ALL(rel in relationships(path) WHERE rel.confidence >= $minConfidence)
          AND toLower(effect.reason) CONTAINS toLower($queryText)
        WITH path, effect,
             [rel in relationships(path) | rel.confidence] as confidences,
             length(path) as chain_length
        WHERE chain_length <= $maxChainLength
        MATCH (effect)-[:ABOUT]->(effectRes:Resource)
        UNWIND range(0, size(nodes(path)) - 1) as idx
        WITH effect, effectRes, path, confidences, chain_length,
             nodes(path)[idx] as stepNode,
             idx + 1 as step
        MATCH (stepNode)-[:ABOUT]->(stepRes:Resource)
        WITH effect, effectRes, confidences, chain_length,
             collect({
               step: step,
               event_id: stepNode.eid,
               reason: stepNode.reason,
               resource: stepRes.rid,
               confidence: confidences[step - 1]
             }) as steps
        RETURN
          effect.eid as effect_id,
          effect.reason as effect_reason,
          effectRes.rid as effect_resource,
          chain_length,
          steps,
          reduce(conf = 1.0, c in confidences | conf * c) as overall_confidence
        ORDER BY overall_confidence DESC, chain_length ASC
        LIMIT 10
      `;

      const result = await session.run(cypher, {
        queryText: query.query,
        maxChainLength,
        minConfidence,
      });

      const causalChains: CausalChain[] = result.records.map(record => {
        const steps = record.get('steps');
        return {
          effect_id: record.get('effect_id'),
          effect_reason: record.get('effect_reason'),
          effect_resource: record.get('effect_resource'),
          chain_length: record.get('chain_length'),
          causal_path: steps.sort((a: any, b: any) => a.step - b.step),
          explanation: this.generateChainExplanation(steps, record.get('effect_reason')),
          overall_confidence: record.get('overall_confidence'),
        };
      });

      return {
        query: query.query,
        causal_chains: causalChains,
      };
    } finally {
      await session.close();
    }
  }

  async similarEvents(eventId: string, topK = 10, timeWindowDays = 30): Promise<SemanticSearchResult[]> {
    const session = db.getSession();

    try {
      // Find event details first
      const eventResult = await session.run(
        'MATCH (e:Episodic {eid: $eventId}) RETURN e.reason as reason, e.message as message',
        { eventId }
      );

      if (eventResult.records.length === 0) {
        return [];
      }

      const reason = eventResult.records[0].get('reason');
      const message = eventResult.records[0].get('message');

      // Search for similar events
      return (await this.semanticSearch({
        query: `${reason} ${message}`,
        top_k: topK + 1, // +1 to exclude the original event
        time_window_days: timeWindowDays,
      })).results.filter(r => r.event_id !== eventId).slice(0, topK);
    } finally {
      await session.close();
    }
  }

  private generateExplanation(query: string, reason: string, similarity: number): string {
    const queryTerms = query.toLowerCase().split(/\s+/);
    const reasonLower = reason.toLowerCase();
    const matchedTerms = queryTerms.filter(term => reasonLower.includes(term));

    if (similarity >= 0.8) {
      return `Strong match: '${reason}' closely matches query terms: ${matchedTerms.join(', ')}`;
    } else if (similarity >= 0.6) {
      return `Partial match: '${reason}' contains: ${matchedTerms.join(', ')}`;
    } else {
      return `Weak match: '${reason}' has semantic similarity`;
    }
  }

  private generateChainExplanation(steps: any[], effectReason: string): string {
    const reasons = steps.map(s => s.reason);
    return `${reasons.join(' → ')} → ${effectReason}`;
  }
}

export const searchService = new SearchService();
