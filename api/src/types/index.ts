/**
 * Core Type Definitions for KG RCA API
 */

export interface ResourceInfo {
  rid: string;
  kind: string;
  name: string;
  namespace?: string;
  labels?: Record<string, string>;
  uid?: string;
  status?: Record<string, any>;
  spec?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface EventInfo {
  event_id: string;
  event_time: string;
  reason: string;
  message: string;
  severity: 'INFO' | 'WARNING' | 'ERROR' | 'FATAL';
  subject?: ResourceInfo;
  source?: string;
  count?: number;
  first_timestamp?: string;
  last_timestamp?: string;
}

export interface Cause {
  event_id: string;
  event_time: string;
  reason: string;
  message: string;
  severity: string;
  confidence: number;
  hops: number;
  subject: ResourceInfo;
  temporal_score?: number;
  distance_score?: number;
  domain_score?: number;
  explanation?: string;
}

export interface Incident {
  incident_id?: string;
  resource_id: string;
  window_start: string;
  window_end: string;
  event_count: number;
  severity: string;
  status?: 'open' | 'acknowledged' | 'resolved';
  assignee?: string;
  notes?: string;
  tags?: string[];
  created_at?: string;
  updated_at?: string;
}

export interface TimelineEvent {
  event_time: string;
  reason: string;
  severity: string;
  message: string;
  resource: string;
}

export interface Recommendation {
  id?: string;
  type: string;
  action: string;
  details: Record<string, any>;
  confidence: number;
  priority: 'low' | 'medium' | 'high' | 'critical';
  automated?: boolean;
  command?: string;
}

export interface RCAResult {
  event_id: string;
  event_time: string;
  reason: string;
  severity: string;
  message?: string;
  subject: ResourceInfo;
  potential_causes: Cause[];
  related_incident?: Incident;
  blast_radius: ResourceInfo[];
  timeline: TimelineEvent[];
  recommendation?: Recommendation;
}

export interface RCAQuery {
  event_id: string;
  resource_uid?: string;
  time_window_minutes?: number;
  max_hops?: number;
  min_confidence?: number;
  include_blast_radius?: boolean;
  include_timeline?: boolean;
}

export interface SemanticSearchQuery {
  query: string;
  top_k?: number;
  min_similarity?: number;
  time_window_days?: number;
  filters?: {
    severity?: string[];
    kind?: string[];
    namespace?: string[];
    has_incident?: boolean;
  };
}

export interface SemanticSearchResult {
  event_id: string;
  reason: string;
  message: string;
  severity: string;
  event_time: string;
  subject: ResourceInfo;
  similarity: number;
  root_causes?: string[];
  incident?: string;
  explanation?: string;
}

export interface CausalSearchQuery {
  query: string;
  max_chain_length?: number;
  min_confidence?: number;
}

export interface CausalChain {
  effect_id: string;
  effect_reason: string;
  effect_resource: string;
  chain_length: number;
  causal_path: CausalStep[];
  explanation: string;
  overall_confidence: number;
}

export interface CausalStep {
  step: number;
  event_id: string;
  reason: string;
  resource: string;
  confidence: number;
}

export interface GraphStats {
  timestamp: string;
  graph: {
    resources: {
      total: number;
      by_kind: Record<string, number>;
    };
    events: {
      total: number;
      by_severity: Record<string, number>;
    };
    incidents: {
      total: number;
      open: number;
      acknowledged: number;
      resolved: number;
    };
    edges: {
      total: number;
      by_type: Record<string, number>;
    };
  };
  performance?: {
    avg_rca_time_ms: number;
    avg_search_time_ms: number;
    kafka_lag?: Record<string, number>;
  };
  health?: Record<string, string>;
}

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  components: {
    neo4j: 'up' | 'down';
    kafka?: 'up' | 'down';
    embedding_service?: 'up' | 'down';
  };
  version: string;
  uptime?: number;
}

export interface ResourceHealth {
  resource_uid: string;
  health_score: number;
  status: 'healthy' | 'degraded' | 'critical';
  checks: HealthCheck[];
  recent_incidents: number;
  last_error?: string;
}

export interface HealthCheck {
  name: string;
  status: 'ok' | 'warning' | 'critical';
  value: number;
  threshold: number;
  message?: string;
}

export interface GraphUpdate {
  timestamp: string;
  resources?: ResourceUpdate[];
  edges?: EdgeUpdate[];
  events?: EventUpdate[];
}

export interface ResourceUpdate {
  action: 'CREATE' | 'UPDATE' | 'DELETE';
  kind: string;
  uid: string;
  namespace?: string;
  name: string;
  labels?: Record<string, string>;
  status?: Record<string, any>;
  spec?: Record<string, any>;
}

export interface EdgeUpdate {
  action: 'CREATE' | 'DELETE';
  from: string;
  to: string;
  type: string;
  properties?: Record<string, any>;
}

export interface EventUpdate {
  action: 'CREATE';
  event_id: string;
  event_time: string;
  severity: string;
  reason: string;
  message: string;
  subject_uid: string;
}

export interface PaginationParams {
  page?: number;
  page_size?: number;
  sort?: string;
  order?: 'asc' | 'desc';
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    page_size: number;
    total_pages: number;
    total_count: number;
  };
}

export interface APIError {
  error: {
    code: string;
    message: string;
    details?: Record<string, any>;
    timestamp: string;
  };
}

export interface WebhookConfig {
  url: string;
  events: string[];
  filters?: {
    severity?: string[];
    namespace?: string[];
  };
  secret?: string;
  enabled?: boolean;
}

export interface WebhookPayload {
  event_type: string;
  timestamp: string;
  data: Record<string, any>;
  signature?: string;
}

export type SeverityLevel = 'INFO' | 'WARNING' | 'ERROR' | 'FATAL';
export type IncidentStatus = 'open' | 'acknowledged' | 'resolved';
export type ResourceKind = 'Pod' | 'Service' | 'Deployment' | 'Node' | 'ReplicaSet' | 'StatefulSet' | 'DaemonSet' | 'Job' | 'CronJob' | 'Ingress' | 'ConfigMap' | 'Secret' | 'PersistentVolume' | 'PersistentVolumeClaim' | 'Namespace';
