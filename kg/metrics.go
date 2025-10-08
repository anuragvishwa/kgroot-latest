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
