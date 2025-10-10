package main

import (
	"net/http"
	"sync/atomic"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Prometheus metrics for production monitoring
var (
	// Message processing metrics
	messagesProcessed = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kg_messages_processed_total",
			Help: "Total number of Kafka messages processed by topic",
		},
		[]string{"topic", "status"}, // status: success, error, skipped
	)

	messageProcessingDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "kg_message_processing_duration_seconds",
			Help:    "Time taken to process a message",
			Buckets: prometheus.ExponentialBuckets(0.001, 2, 10), // 1ms to 1s
		},
		[]string{"topic"},
	)

	// Neo4j operation metrics
	neo4jOperations = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kg_neo4j_operations_total",
			Help: "Total number of Neo4j operations",
		},
		[]string{"operation", "status"}, // operation: upsert_resource, upsert_edge, etc.
	)

	neo4jQueryDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "kg_neo4j_query_duration_seconds",
			Help:    "Time taken to execute Neo4j queries",
			Buckets: prometheus.ExponentialBuckets(0.01, 2, 10), // 10ms to 10s
		},
		[]string{"operation"},
	)

	neo4jConnectionErrors = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "kg_neo4j_connection_errors_total",
			Help: "Total number of Neo4j connection errors",
		},
	)

	// Kafka consumer metrics
	consumerLag = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kg_kafka_consumer_lag",
			Help: "Current Kafka consumer lag by topic and partition",
		},
		[]string{"topic", "partition"},
	)

	consumerOffsetCurrent = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kg_kafka_consumer_offset_current",
			Help: "Current Kafka consumer offset",
		},
		[]string{"topic", "partition"},
	)

	// RCA-specific metrics
	rcaLinksCreated = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "kg_rca_links_created_total",
			Help: "Total number of RCA causal links created",
		},
	)

	severityEscalations = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kg_severity_escalations_total",
			Help: "Total number of severity escalations",
		},
		[]string{"from_severity", "to_severity"},
	)

	incidentsClustered = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "kg_incidents_clustered_total",
			Help: "Total number of incidents clustered",
		},
	)

	// Graph health metrics
	graphNodesTotal = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kg_graph_nodes_total",
			Help: "Total number of nodes in the knowledge graph by type",
		},
		[]string{"node_type"}, // Resource, Episodic, Incident, etc.
	)

	graphEdgesTotal = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kg_graph_edges_total",
			Help: "Total number of edges in the knowledge graph by type",
		},
		[]string{"edge_type"}, // SELECTS, RUNS_ON, POTENTIAL_CAUSE, etc.
	)

	// Anomaly detection metrics (for future ML integration)
	anomaliesDetected = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kg_anomalies_detected_total",
			Help: "Total number of anomalies detected",
		},
		[]string{"anomaly_type"}, // resource_churn, error_spike, etc.
	)

	// RCA Quality Metrics (A@K and MAR)
	rcaAccuracyAtK = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kg_rca_accuracy_at_k",
			Help: "RCA Accuracy at K - percentage of incidents where correct cause is in top-K",
		},
		[]string{"k"}, // k=1,3,5,10
	)

	rcaMeanAverageRank = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "kg_rca_mean_average_rank",
			Help: "Mean Average Rank (MAR) - average rank of correct root causes",
		},
	)

	rcaValidationIncidents = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "kg_rca_validation_incidents_total",
			Help: "Total number of incidents used for RCA validation",
		},
	)

	rcaConfidenceScoreDistribution = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "kg_rca_confidence_score",
			Help:    "Distribution of RCA confidence scores",
			Buckets: []float64{0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0},
		},
		[]string{"score_type"}, // temporal, distance, domain, final
	)

	rcaNullConfidenceLinks = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "kg_rca_null_confidence_total",
			Help: "Total number of RCA links created with NULL confidence (fallback used)",
		},
	)

	// Circuit breaker metrics
	circuitBreakerState = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kg_circuit_breaker_state",
			Help: "Circuit breaker state (0=closed, 1=open, 2=half-open)",
		},
		[]string{"component"},
	)

	// DLQ metrics
	dlqMessagesTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kg_dlq_messages_total",
			Help: "Total number of messages sent to dead letter queue",
		},
		[]string{"topic", "reason"},
	)

	// SLA Monitoring Metrics
	slaViolations = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "kg_sla_violations_total",
			Help: "Total number of SLA violations by operation type",
		},
		[]string{"operation", "severity"}, // severity: warning, critical
	)

	processingLatencyP95 = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kg_processing_latency_p95_seconds",
			Help: "95th percentile processing latency by operation",
		},
		[]string{"operation"},
	)

	processingLatencyP99 = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kg_processing_latency_p99_seconds",
			Help: "99th percentile processing latency by operation",
		},
		[]string{"operation"},
	)

	endToEndLatency = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "kg_end_to_end_latency_seconds",
			Help:    "End-to-end latency from Kafka message to Neo4j commit",
			Buckets: []float64{0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0},
		},
		[]string{"topic"},
	)

	rcaComputeTime = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "kg_rca_compute_time_seconds",
			Help:    "Time taken to compute RCA links for a single event",
			Buckets: []float64{0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0},
		},
	)
)

// MetricsCollector periodically collects graph health metrics
type MetricsCollector struct {
	graph          *Graph
	collectionInterval time.Duration
	stopChan       chan struct{}
}

func NewMetricsCollector(g *Graph, interval time.Duration) *MetricsCollector {
	return &MetricsCollector{
		graph:          g,
		collectionInterval: interval,
		stopChan:       make(chan struct{}),
	}
}

func (mc *MetricsCollector) Start() {
	ticker := time.NewTicker(mc.collectionInterval)
	go func() {
		for {
			select {
			case <-ticker.C:
				mc.collectGraphMetrics()
			case <-mc.stopChan:
				ticker.Stop()
				return
			}
		}
	}()
}

func (mc *MetricsCollector) Stop() {
	close(mc.stopChan)
}

func (mc *MetricsCollector) collectGraphMetrics() {
	// This would query Neo4j for graph health stats
	// For now, we'll implement a simple version
	// TODO: Implement actual Neo4j queries for graph health
}

// StartMetricsServer starts the Prometheus metrics HTTP server
func StartMetricsServer(addr string) error {
	http.Handle("/metrics", promhttp.Handler())
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	})
	http.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		// TODO: Check Neo4j and Kafka connectivity
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ready"))
	})
	return http.ListenAndServe(addr, nil)
}

// Helper functions for metrics tracking

var (
	resourceCountCache atomic.Int64
	episodicCountCache atomic.Int64
)

func trackMessageProcessing(topic string, duration time.Duration, err error) {
	status := "success"
	if err != nil {
		status = "error"
	}
	messagesProcessed.WithLabelValues(topic, status).Inc()
	messageProcessingDuration.WithLabelValues(topic).Observe(duration.Seconds())
}

func trackNeo4jOperation(operation string, duration time.Duration, err error) {
	status := "success"
	if err != nil {
		status = "error"
	}
	neo4jOperations.WithLabelValues(operation, status).Inc()
	neo4jQueryDuration.WithLabelValues(operation).Observe(duration.Seconds())
}

func trackRCALink() {
	rcaLinksCreated.Inc()
}

func trackSeverityEscalation(from, to string) {
	severityEscalations.WithLabelValues(from, to).Inc()
}

func trackIncidentClustering() {
	incidentsClustered.Inc()
}

func trackDLQMessage(topic, reason string) {
	dlqMessagesTotal.WithLabelValues(topic, reason).Inc()
}

// SLA thresholds (configurable via env vars)
type SLAThresholds struct {
	MessageProcessingWarning  time.Duration // Warning if message takes > this
	MessageProcessingCritical time.Duration // Critical if message takes > this
	RCAComputeWarning         time.Duration // Warning if RCA takes > this
	RCAComputeCritical        time.Duration // Critical if RCA takes > this
	Neo4jQueryWarning         time.Duration // Warning if Neo4j query takes > this
	Neo4jQueryCritical        time.Duration // Critical if Neo4j query takes > this
}

var defaultSLAThresholds = SLAThresholds{
	MessageProcessingWarning:  500 * time.Millisecond,  // 500ms warning
	MessageProcessingCritical: 2 * time.Second,         // 2s critical
	RCAComputeWarning:         200 * time.Millisecond,  // 200ms warning
	RCAComputeCritical:        1 * time.Second,         // 1s critical
	Neo4jQueryWarning:         100 * time.Millisecond,  // 100ms warning
	Neo4jQueryCritical:        500 * time.Millisecond,  // 500ms critical
}

func trackSLACompliance(operation string, duration time.Duration, thresholds SLAThresholds) {
	var threshold time.Duration
	var warningThreshold time.Duration

	switch operation {
	case "message_processing":
		threshold = thresholds.MessageProcessingCritical
		warningThreshold = thresholds.MessageProcessingWarning
	case "rca_compute":
		threshold = thresholds.RCAComputeCritical
		warningThreshold = thresholds.RCAComputeWarning
		rcaComputeTime.Observe(duration.Seconds())
	case "neo4j_query":
		threshold = thresholds.Neo4jQueryCritical
		warningThreshold = thresholds.Neo4jQueryWarning
	default:
		return
	}

	if duration > threshold {
		slaViolations.WithLabelValues(operation, "critical").Inc()
	} else if duration > warningThreshold {
		slaViolations.WithLabelValues(operation, "warning").Inc()
	}
}

func trackEndToEndLatency(topic string, duration time.Duration) {
	endToEndLatency.WithLabelValues(topic).Observe(duration.Seconds())
}
