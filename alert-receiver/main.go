package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/IBM/sarama"
	"github.com/google/uuid"
)

// AlertmanagerWebhook represents the webhook payload from Alertmanager
type AlertmanagerWebhook struct {
	Version           string            `json:"version"`
	GroupKey          string            `json:"groupKey"`
	TruncatedAlerts   int               `json:"truncatedAlerts"`
	Status            string            `json:"status"`
	Receiver          string            `json:"receiver"`
	GroupLabels       map[string]string `json:"groupLabels"`
	CommonLabels      map[string]string `json:"commonLabels"`
	CommonAnnotations map[string]string `json:"commonAnnotations"`
	ExternalURL       string            `json:"externalURL"`
	Alerts            []Alert           `json:"alerts"`
}

type Alert struct {
	Status       string            `json:"status"`
	Labels       map[string]string `json:"labels"`
	Annotations  map[string]string `json:"annotations"`
	StartsAt     time.Time         `json:"startsAt"`
	EndsAt       time.Time         `json:"endsAt"`
	GeneratorURL string            `json:"generatorURL"`
	Fingerprint  string            `json:"fingerprint"`
}

// EventNormalized represents the normalized event format expected by graph-builder
type EventNormalized struct {
	EventID   string       `json:"event_id"`
	EventTime string       `json:"event_time"`
	ClientID  string       `json:"client_id,omitempty"`
	Etype     string       `json:"etype"`
	Severity  string       `json:"severity"`
	Reason    string       `json:"reason"`
	Message   string       `json:"message"`
	Subject   EventSubject `json:"subject"`
}

type EventSubject struct {
	Kind string `json:"kind"`
	UID  string `json:"uid"`
	NS   string `json:"ns"`
	Name string `json:"name"`
}

// KubernetesEvent represents the legacy Kubernetes event format (kept for backward compatibility)
type KubernetesEvent struct {
	Metadata         EventMetadata    `json:"metadata"`
	Reason           string           `json:"reason"`
	Message          string           `json:"message"`
	Source           EventSource      `json:"source"`
	FirstTimestamp   string           `json:"firstTimestamp"`
	LastTimestamp    string           `json:"lastTimestamp"`
	Count            int              `json:"count"`
	Type             string           `json:"type"`
	EventTime        *string          `json:"eventTime"`
	ReportingComp    string           `json:"reportingComponent"`
	ReportingInst    string           `json:"reportingInstance"`
	InvolvedObject   InvolvedObject   `json:"involvedObject"`
	ClientID         string           `json:"client_id,omitempty"`
}

type EventMetadata struct {
	Name              string    `json:"name"`
	Namespace         string    `json:"namespace"`
	UID               string    `json:"uid"`
	CreationTimestamp string    `json:"creationTimestamp"`
}

type EventSource struct {
	Component string `json:"component"`
	Host      string `json:"host,omitempty"`
}

type InvolvedObject struct {
	Kind       string            `json:"kind"`
	Namespace  string            `json:"namespace"`
	Name       string            `json:"name"`
	UID        string            `json:"uid,omitempty"`
	APIVersion string            `json:"apiVersion,omitempty"`
	Labels     map[string]string `json:"labels,omitempty"`
}

var (
	kafkaBrokers   []string
	kafkaTopic     string
	kafkaProducer  sarama.SyncProducer
	clientID       string
	port           string
)

func init() {
	// Parse environment variables
	brokersStr := os.Getenv("KAFKA_BROKERS")
	if brokersStr == "" {
		brokersStr = "localhost:9092"
	}
	kafkaBrokers = strings.Split(brokersStr, ",")

	kafkaTopic = os.Getenv("KAFKA_TOPIC")
	if kafkaTopic == "" {
		kafkaTopic = "events.normalized"
	}

	clientID = os.Getenv("CLIENT_ID")
	if clientID == "" {
		clientID = "unknown"
	}

	port = os.Getenv("PORT")
	if port == "" {
		port = "9093"
	}

	log.Printf("[alert-receiver] Configuration:")
	log.Printf("  - Kafka Brokers: %v", kafkaBrokers)
	log.Printf("  - Kafka Topic: %s", kafkaTopic)
	log.Printf("  - Client ID: %s", clientID)
	log.Printf("  - Port: %s", port)
}

func main() {
	// Initialize Kafka producer
	config := sarama.NewConfig()
	config.Producer.RequiredAcks = sarama.WaitForAll
	config.Producer.Retry.Max = 5
	config.Producer.Return.Successes = true
	config.Producer.Compression = sarama.CompressionSnappy

	var err error
	kafkaProducer, err = sarama.NewSyncProducer(kafkaBrokers, config)
	if err != nil {
		log.Fatalf("[alert-receiver] Failed to create Kafka producer: %v", err)
	}
	defer kafkaProducer.Close()

	log.Printf("[alert-receiver] Kafka producer initialized")

	// Setup HTTP server
	mux := http.NewServeMux()
	mux.HandleFunc("/webhook", webhookHandler)
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/metrics", metricsHandler)

	server := &http.Server{
		Addr:         ":" + port,
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	// Start server in goroutine
	go func() {
		log.Printf("[alert-receiver] Starting HTTP server on port %s", port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[alert-receiver] Server error: %v", err)
		}
	}()

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Printf("[alert-receiver] Shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(ctx); err != nil {
		log.Printf("[alert-receiver] Server shutdown error: %v", err)
	}
}

func webhookHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var webhook AlertmanagerWebhook
	if err := json.NewDecoder(r.Body).Decode(&webhook); err != nil {
		log.Printf("[alert-receiver] Failed to decode webhook: %v", err)
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}

	log.Printf("[alert-receiver] Received %d alerts (status: %s, receiver: %s)",
		len(webhook.Alerts), webhook.Status, webhook.Receiver)

	// Process each alert
	for _, alert := range webhook.Alerts {
		event := transformAlertToNormalizedEvent(alert, webhook)

		if err := publishNormalizedEvent(event); err != nil {
			log.Printf("[alert-receiver] Failed to publish event: %v", err)
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		log.Printf("[alert-receiver] Published alert: %s for %s/%s (client_id=%s)",
			alert.Labels["alertname"], event.Subject.NS, event.Subject.Name, event.ClientID)
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

func transformAlertToNormalizedEvent(alert Alert, webhook AlertmanagerWebhook) EventNormalized {
	now := time.Now().UTC().Format(time.RFC3339)
	eventID := uuid.New().String()

	// Extract resource information from labels
	namespace := alert.Labels["namespace"]
	if namespace == "" {
		namespace = "default"
	}

	// Determine resource kind and name
	kind := "Service" // Default
	name := ""
	uid := alert.Labels["uid"]

	// Try to extract from pod label
	if podName := alert.Labels["pod"]; podName != "" {
		kind = "Pod"
		name = podName
	} else if svcName := alert.Labels["service"]; svcName != "" {
		kind = "Service"
		name = svcName
	} else if deployment := alert.Labels["deployment"]; deployment != "" {
		kind = "Deployment"
		name = deployment
	} else if node := alert.Labels["node"]; node != "" {
		kind = "Node"
		name = node
	}

	// Get alert name
	alertname := alert.Labels["alertname"]
	if alertname == "" {
		alertname = "UnknownAlert"
	}

	// Map alert severity to normalized severity (uppercase)
	severity := strings.ToUpper(alert.Labels["severity"])
	switch severity {
	case "CRITICAL":
		severity = "CRITICAL"
	case "WARNING":
		severity = "WARNING"
	case "INFO":
		severity = "INFO"
	default:
		severity = "WARNING" // Default for alerts
	}

	// Build message from annotations
	message := alert.Annotations["description"]
	if message == "" {
		message = alert.Annotations["summary"]
	}
	if message == "" {
		message = fmt.Sprintf("Alert %s is %s", alertname, alert.Status)
	}

	// Create normalized event
	event := EventNormalized{
		EventID:   eventID,
		EventTime: now,
		ClientID:  clientID,
		Etype:     "prom.alert",
		Severity:  severity,
		Reason:    alertname,
		Message:   message,
		Subject: EventSubject{
			Kind: kind,
			UID:  uid,
			NS:   namespace,
			Name: name,
		},
	}

	return event
}

func publishNormalizedEvent(event EventNormalized) error {
	// Serialize event to JSON
	eventJSON, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal event: %w", err)
	}

	// Use client_id-prefixed event ID as message key for multi-tenancy
	messageKey := event.EventID
	if event.ClientID != "" {
		messageKey = fmt.Sprintf("%s::%s", event.ClientID, event.EventID)
	}

	// Create Kafka message with key
	msg := &sarama.ProducerMessage{
		Topic: kafkaTopic,
		Key:   sarama.StringEncoder(messageKey),
		Value: sarama.ByteEncoder(eventJSON),
	}

	// Send message
	partition, offset, err := kafkaProducer.SendMessage(msg)
	if err != nil {
		return fmt.Errorf("failed to send message to Kafka: %w", err)
	}

	log.Printf("[alert-receiver] Published to Kafka: topic=%s partition=%d offset=%d key=%s",
		kafkaTopic, partition, offset, messageKey)

	return nil
}

// Legacy function kept for backward compatibility
func publishEvent(event KubernetesEvent) error {
	// Serialize event to JSON
	eventJSON, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal event: %w", err)
	}

	// Use event UID as message key (this is critical!)
	messageKey := event.Metadata.UID

	// Create Kafka message with key
	msg := &sarama.ProducerMessage{
		Topic: kafkaTopic,
		Key:   sarama.StringEncoder(messageKey),
		Value: sarama.ByteEncoder(eventJSON),
	}

	// Send message
	partition, offset, err := kafkaProducer.SendMessage(msg)
	if err != nil {
		return fmt.Errorf("failed to send message to Kafka: %w", err)
	}

	log.Printf("[alert-receiver] Published to Kafka: topic=%s partition=%d offset=%d key=%s",
		kafkaTopic, partition, offset, messageKey)

	return nil
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

func metricsHandler(w http.ResponseWriter, r *http.Request) {
	// Basic metrics endpoint (can be expanded with Prometheus metrics)
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("# HELP alert_receiver_up Alert receiver is up\n# TYPE alert_receiver_up gauge\nalert_receiver_up 1\n"))
}
