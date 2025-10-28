package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/IBM/sarama"
	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
	"github.com/neo4j/neo4j-go-driver/v5/neo4j"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"net/http"
)

// Configuration from environment
type Config struct {
	KafkaBrokers       []string
	Neo4jURI           string
	Neo4jUser          string
	Neo4jPass          string
	DockerNetwork      string
	HeartbeatTimeout   time.Duration
	CleanupTimeout     time.Duration
	ReconcileInterval  time.Duration
	GraphBuilderImage  string
	GraphBuilderMemory string
	GraphBuilderCPU    string
}

// ClusterInfo represents a registered cluster
type ClusterInfo struct {
	ClientID        string    `json:"client_id"`
	ClusterName     string    `json:"cluster_name"`
	Version         string    `json:"version"`
	RegisteredAt    time.Time `json:"registered_at"`
	LastHeartbeat   time.Time `json:"-"`
	Status          string    // "active", "stale", "dead"
	GraphBuilderID  string    // Docker container ID
	Metadata        map[string]interface{} `json:"metadata"`
}

// HeartbeatMessage from clusters
type HeartbeatMessage struct {
	ClientID  string                 `json:"client_id"`
	Timestamp time.Time              `json:"timestamp"`
	Status    string                 `json:"status"`
	Metrics   map[string]interface{} `json:"metrics"`
}

// ControlPlane manages dynamic consumer spawning
type ControlPlane struct {
	config    Config
	docker    *client.Client
	neo4j     neo4j.DriverWithContext
	kafka     sarama.Client

	mu        sync.RWMutex
	clusters  map[string]*ClusterInfo

	// Prometheus metrics
	clustersTotal     *prometheus.GaugeVec
	spawnOpsTotal     prometheus.Counter
	cleanupOpsTotal   prometheus.Counter
}

// NewControlPlane creates a new control plane instance
func NewControlPlane(cfg Config) (*ControlPlane, error) {
	// Initialize Docker client
	dockerClient, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		return nil, fmt.Errorf("failed to create docker client: %w", err)
	}

	// Initialize Neo4j driver
	neo4jDriver, err := neo4j.NewDriverWithContext(cfg.Neo4jURI, neo4j.BasicAuth(cfg.Neo4jUser, cfg.Neo4jPass, ""))
	if err != nil {
		return nil, fmt.Errorf("failed to create neo4j driver: %w", err)
	}

	// Initialize Kafka client
	kafkaConfig := sarama.NewConfig()
	kafkaConfig.Version = sarama.V3_6_0_0
	kafkaConfig.Consumer.Return.Errors = true
	kafkaClient, err := sarama.NewClient(cfg.KafkaBrokers, kafkaConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create kafka client: %w", err)
	}

	// Initialize Prometheus metrics
	clustersTotal := prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "kg_control_plane_clusters_total",
			Help: "Total number of clusters by status",
		},
		[]string{"status"},
	)
	spawnOpsTotal := prometheus.NewCounter(
		prometheus.CounterOpts{
			Name: "kg_control_plane_spawn_operations_total",
			Help: "Total number of graph-builder spawn operations",
		},
	)
	cleanupOpsTotal := prometheus.NewCounter(
		prometheus.CounterOpts{
			Name: "kg_control_plane_cleanup_operations_total",
			Help: "Total number of cleanup operations",
		},
	)

	prometheus.MustRegister(clustersTotal, spawnOpsTotal, cleanupOpsTotal)

	cp := &ControlPlane{
		config:          cfg,
		docker:          dockerClient,
		neo4j:           neo4jDriver,
		kafka:           kafkaClient,
		clusters:        make(map[string]*ClusterInfo),
		clustersTotal:   clustersTotal,
		spawnOpsTotal:   spawnOpsTotal,
		cleanupOpsTotal: cleanupOpsTotal,
	}

	return cp, nil
}

// Run starts the control plane
func (cp *ControlPlane) Run(ctx context.Context) error {
	log.Println("🚀 Starting Control Plane Manager")

	// Start registry watcher
	go cp.WatchRegistry(ctx)

	// Start heartbeat monitor
	go cp.WatchHeartbeats(ctx)

	// Start reconciliation loop
	ticker := time.NewTicker(cp.config.ReconcileInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Println("🛑 Shutting down control plane")
			return ctx.Err()
		case <-ticker.C:
			cp.Reconcile(ctx)
		}
	}
}

// WatchRegistry monitors cluster.registry topic
func (cp *ControlPlane) WatchRegistry(ctx context.Context) {
	log.Println("👀 Watching cluster.registry topic")

	config := sarama.NewConfig()
	config.Version = sarama.V3_6_0_0
	config.Consumer.Offsets.Initial = sarama.OffsetOldest

	consumer, err := sarama.NewConsumerGroupFromClient("control-plane-registry", cp.kafka)
	if err != nil {
		log.Printf("❌ Failed to create registry consumer: %v", err)
		return
	}
	defer consumer.Close()

	handler := &registryHandler{cp: cp}

	for {
		select {
		case <-ctx.Done():
			return
		default:
			if err := consumer.Consume(ctx, []string{"cluster.registry"}, handler); err != nil {
				log.Printf("❌ Registry consumer error: %v", err)
				time.Sleep(5 * time.Second)
			}
		}
	}
}

type registryHandler struct {
	cp *ControlPlane
}

func (h *registryHandler) Setup(_ sarama.ConsumerGroupSession) error   { return nil }
func (h *registryHandler) Cleanup(_ sarama.ConsumerGroupSession) error { return nil }

func (h *registryHandler) ConsumeClaim(session sarama.ConsumerGroupSession, claim sarama.ConsumerGroupClaim) error {
	for msg := range claim.Messages() {
		// Handle tombstone (cluster deregistration)
		if msg.Value == nil {
			clientID := string(msg.Key)
			log.Printf("🪦 Cluster deregistered: %s", clientID)
			h.cp.DeregisterCluster(clientID)
			session.MarkMessage(msg, "")
			continue
		}

		// Parse registration message
		var cluster ClusterInfo
		if err := json.Unmarshal(msg.Value, &cluster); err != nil {
			log.Printf("❌ Failed to parse registration: %v", err)
			session.MarkMessage(msg, "")
			continue
		}

		log.Printf("📝 Cluster registered: %s (name: %s, version: %s)",
			cluster.ClientID, cluster.ClusterName, cluster.Version)

		h.cp.RegisterCluster(&cluster)
		session.MarkMessage(msg, "")
	}
	return nil
}

// RegisterCluster adds or updates a cluster
func (cp *ControlPlane) RegisterCluster(cluster *ClusterInfo) {
	cp.mu.Lock()
	defer cp.mu.Unlock()

	existing, exists := cp.clusters[cluster.ClientID]
	if exists {
		// Update existing cluster
		cluster.GraphBuilderID = existing.GraphBuilderID
		cluster.LastHeartbeat = existing.LastHeartbeat
	} else {
		// New cluster
		cluster.LastHeartbeat = time.Now()
		cluster.Status = "active"
	}

	cp.clusters[cluster.ClientID] = cluster
	cp.updateMetrics()
}

// DeregisterCluster removes a cluster
func (cp *ControlPlane) DeregisterCluster(clientID string) {
	cp.mu.Lock()
	defer cp.mu.Unlock()

	cluster, exists := cp.clusters[clientID]
	if !exists {
		return
	}

	// Cleanup will be handled by reconciliation loop
	cluster.Status = "dead"
	cp.updateMetrics()
}

// WatchHeartbeats monitors cluster.heartbeat topic
func (cp *ControlPlane) WatchHeartbeats(ctx context.Context) {
	log.Println("💓 Watching cluster.heartbeat topic")

	config := sarama.NewConfig()
	config.Version = sarama.V3_6_0_0
	config.Consumer.Offsets.Initial = sarama.OffsetNewest

	consumer, err := sarama.NewConsumerGroupFromClient("control-plane-heartbeat", cp.kafka)
	if err != nil {
		log.Printf("❌ Failed to create heartbeat consumer: %v", err)
		return
	}
	defer consumer.Close()

	handler := &heartbeatHandler{cp: cp}

	for {
		select {
		case <-ctx.Done():
			return
		default:
			if err := consumer.Consume(ctx, []string{"cluster.heartbeat"}, handler); err != nil {
				log.Printf("❌ Heartbeat consumer error: %v", err)
				time.Sleep(5 * time.Second)
			}
		}
	}
}

type heartbeatHandler struct {
	cp *ControlPlane
}

func (h *heartbeatHandler) Setup(_ sarama.ConsumerGroupSession) error   { return nil }
func (h *heartbeatHandler) Cleanup(_ sarama.ConsumerGroupSession) error { return nil }

func (h *heartbeatHandler) ConsumeClaim(session sarama.ConsumerGroupSession, claim sarama.ConsumerGroupClaim) error {
	for msg := range claim.Messages() {
		var hb HeartbeatMessage
		if err := json.Unmarshal(msg.Value, &hb); err != nil {
			log.Printf("❌ Failed to parse heartbeat: %v", err)
			session.MarkMessage(msg, "")
			continue
		}

		h.cp.UpdateHeartbeat(hb.ClientID, hb.Timestamp)
		session.MarkMessage(msg, "")
	}
	return nil
}

// UpdateHeartbeat updates last heartbeat time
func (cp *ControlPlane) UpdateHeartbeat(clientID string, timestamp time.Time) {
	cp.mu.Lock()
	defer cp.mu.Unlock()

	cluster, exists := cp.clusters[clientID]
	if !exists {
		return
	}

	cluster.LastHeartbeat = timestamp
	if cluster.Status == "stale" {
		cluster.Status = "active"
		log.Printf("✅ Cluster recovered: %s", clientID)
	}
	cp.updateMetrics()
}

// Reconcile checks cluster health and spawns/cleans up graph-builders
func (cp *ControlPlane) Reconcile(ctx context.Context) {
	cp.mu.Lock()
	defer cp.mu.Unlock()

	for clientID, cluster := range cp.clusters {
		timeSinceHeartbeat := time.Since(cluster.LastHeartbeat)

		// Mark stale
		if timeSinceHeartbeat > cp.config.HeartbeatTimeout && cluster.Status == "active" {
			cluster.Status = "stale"
			log.Printf("⚠️  Cluster stale: %s (no heartbeat for %v)", clientID, timeSinceHeartbeat)
		}

		// Cleanup dead clusters
		if timeSinceHeartbeat > cp.config.CleanupTimeout || cluster.Status == "dead" {
			log.Printf("💀 Cleaning up dead cluster: %s", clientID)
			cp.cleanupCluster(ctx, clientID)
			delete(cp.clusters, clientID)
			continue
		}

		// Check if graph-builder exists
		if cluster.GraphBuilderID == "" {
			log.Printf("🔧 Spawning graph-builder for cluster: %s", clientID)
			if err := cp.spawnGraphBuilder(ctx, clientID); err != nil {
				log.Printf("❌ Failed to spawn graph-builder: %v", err)
			}
		} else {
			// Verify container is still running
			if !cp.isContainerRunning(ctx, cluster.GraphBuilderID) {
				log.Printf("⚠️  Graph-builder container stopped, respawning: %s", clientID)
				cluster.GraphBuilderID = ""
				if err := cp.spawnGraphBuilder(ctx, clientID); err != nil {
					log.Printf("❌ Failed to respawn graph-builder: %v", err)
				}
			}
		}
	}

	cp.updateMetrics()
}

// spawnGraphBuilder creates a new graph-builder container
func (cp *ControlPlane) spawnGraphBuilder(ctx context.Context, clientID string) error {
	containerName := fmt.Sprintf("kg-graph-builder-%s", clientID)

	// Check if container already exists (stopped)
	containers, err := cp.docker.ContainerList(ctx, types.ContainerListOptions{All: true})
	if err != nil {
		return fmt.Errorf("failed to list containers: %w", err)
	}

	for _, c := range containers {
		for _, name := range c.Names {
			if strings.TrimPrefix(name, "/") == containerName {
				// Container exists, remove it
				log.Printf("🗑️  Removing old container: %s", containerName)
				if err := cp.docker.ContainerRemove(ctx, c.ID, types.ContainerRemoveOptions{Force: true}); err != nil {
					log.Printf("⚠️  Failed to remove old container: %v", err)
				}
				break
			}
		}
	}

	// Create new container
	resp, err := cp.docker.ContainerCreate(ctx, &container.Config{
		Image: cp.config.GraphBuilderImage,
		Env: []string{
			fmt.Sprintf("CLIENT_ID=%s", clientID),
			fmt.Sprintf("KAFKA_GROUP=kg-builder-%s", clientID),
			fmt.Sprintf("KAFKA_BROKERS=%s", strings.Join(cp.config.KafkaBrokers, ",")),
			fmt.Sprintf("NEO4J_URI=%s", cp.config.Neo4jURI),
			fmt.Sprintf("NEO4J_USER=%s", cp.config.Neo4jUser),
			fmt.Sprintf("NEO4J_PASS=%s", cp.config.Neo4jPass),
		},
	}, &container.HostConfig{
		NetworkMode: container.NetworkMode(cp.config.DockerNetwork),
		RestartPolicy: container.RestartPolicy{
			Name: "unless-stopped",
		},
	}, nil, nil, containerName)

	if err != nil {
		return fmt.Errorf("failed to create container: %w", err)
	}

	if err := cp.docker.ContainerStart(ctx, resp.ID, types.ContainerStartOptions{}); err != nil {
		return fmt.Errorf("failed to start container: %w", err)
	}

	// Update cluster info
	cluster := cp.clusters[clientID]
	cluster.GraphBuilderID = resp.ID

	cp.spawnOpsTotal.Inc()
	log.Printf("✅ Spawned graph-builder-%s (container: %s)", clientID, resp.ID[:12])

	return nil
}

// isContainerRunning checks if a container is running
func (cp *ControlPlane) isContainerRunning(ctx context.Context, containerID string) bool {
	info, err := cp.docker.ContainerInspect(ctx, containerID)
	if err != nil {
		return false
	}
	return info.State.Running
}

// cleanupCluster stops graph-builder and deletes consumer group
func (cp *ControlPlane) cleanupCluster(ctx context.Context, clientID string) {
	cluster := cp.clusters[clientID]

	// Stop and remove container
	if cluster.GraphBuilderID != "" {
		log.Printf("🛑 Stopping container: %s", cluster.GraphBuilderID[:12])
		timeout := 10
		if err := cp.docker.ContainerStop(ctx, cluster.GraphBuilderID, container.StopOptions{Timeout: &timeout}); err != nil {
			log.Printf("⚠️  Failed to stop container: %v", err)
		}
		if err := cp.docker.ContainerRemove(ctx, cluster.GraphBuilderID, types.ContainerRemoveOptions{}); err != nil {
			log.Printf("⚠️  Failed to remove container: %v", err)
		}
	}

	// Delete consumer group using a separate Kafka connection
	groupName := fmt.Sprintf("kg-builder-%s", clientID)
	log.Printf("🗑️  Deleting consumer group: %s", groupName)

	// Create a separate Kafka config and client for admin operations
	// This prevents closing the shared client used by consumers
	adminConfig := sarama.NewConfig()
	adminConfig.Version = sarama.V3_6_0_0
	adminClient, err := sarama.NewClient(cp.config.KafkaBrokers, adminConfig)
	if err != nil {
		log.Printf("⚠️  Failed to create admin Kafka client: %v", err)
	} else {
		defer adminClient.Close() // Safe to close this one, it's separate

		admin, err := sarama.NewClusterAdminFromClient(adminClient)
		if err != nil {
			log.Printf("⚠️  Failed to create admin: %v", err)
		} else {
			defer admin.Close() // Safe to close since we're closing the client too

			if err := admin.DeleteConsumerGroup(groupName); err != nil {
				log.Printf("⚠️  Failed to delete consumer group: %v", err)
			}
		}
	}

	cp.cleanupOpsTotal.Inc()
	log.Printf("✅ Cleaned up cluster: %s", clientID)
}

// updateMetrics updates Prometheus metrics
func (cp *ControlPlane) updateMetrics() {
	statusCounts := map[string]int{"active": 0, "stale": 0, "dead": 0}
	for _, cluster := range cp.clusters {
		statusCounts[cluster.Status]++
	}
	for status, count := range statusCounts {
		cp.clustersTotal.WithLabelValues(status).Set(float64(count))
	}
}

// Close closes all connections
func (cp *ControlPlane) Close() error {
	if cp.docker != nil {
		cp.docker.Close()
	}
	if cp.neo4j != nil {
		cp.neo4j.Close(context.Background())
	}
	if cp.kafka != nil {
		cp.kafka.Close()
	}
	return nil
}

func main() {
	// Load configuration from environment
	config := Config{
		KafkaBrokers:       strings.Split(getEnv("KAFKA_BROKERS", "kafka:9092"), ","),
		Neo4jURI:           getEnv("NEO4J_URI", "neo4j://neo4j:7687"),
		Neo4jUser:          getEnv("NEO4J_USER", "neo4j"),
		Neo4jPass:          getEnv("NEO4J_PASS", "password"),
		DockerNetwork:      getEnv("DOCKER_NETWORK", "mini-server-prod_kg-network"),
		HeartbeatTimeout:   parseDuration(getEnv("HEARTBEAT_TIMEOUT", "2m")),
		CleanupTimeout:     parseDuration(getEnv("CLEANUP_TIMEOUT", "5m")),
		ReconcileInterval:  parseDuration(getEnv("RECONCILE_INTERVAL", "30s")),
		GraphBuilderImage:  getEnv("GRAPH_BUILDER_IMAGE", "anuragvishwa/kg-graph-builder:1.0.20"),
		GraphBuilderMemory: getEnv("GB_MEMORY_LIMIT", "256M"),
		GraphBuilderCPU:    getEnv("GB_CPU_LIMIT", "0.5"),
	}

	// Create control plane
	cp, err := NewControlPlane(config)
	if err != nil {
		log.Fatalf("Failed to create control plane: %v", err)
	}
	defer cp.Close()

	// Start metrics server
	http.Handle("/metrics", promhttp.Handler())
	go func() {
		log.Println("📊 Metrics server listening on :9090")
		if err := http.ListenAndServe(":9090", nil); err != nil {
			log.Printf("Metrics server error: %v", err)
		}
	}()

	// Setup signal handling
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)

	go func() {
		<-sigCh
		log.Println("Received shutdown signal")
		cancel()
	}()

	// Run control plane
	if err := cp.Run(ctx); err != nil && err != context.Canceled {
		log.Fatalf("Control plane error: %v", err)
	}

	log.Println("Control plane stopped")
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func parseDuration(s string) time.Duration {
	d, err := time.ParseDuration(s)
	if err != nil {
		log.Fatalf("Invalid duration: %s", s)
	}
	return d
}
