package main

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"
)

// Anomaly detection for improved RCA accuracy
// Detects patterns like:
// - Resource churn (excessive create/delete cycles)
// - Error spikes (sudden increase in errors)
// - Cascading failures (multiple related resources failing)
// - Memory leaks (OOM events increasing over time)

type AnomalyDetector struct {
	mu sync.RWMutex

	// Time-series data for anomaly detection
	eventRates      map[string]*RateBucket // severity -> rate
	resourceChurn   map[string]*RateBucket // kind -> churn rate
	errorPatterns   map[string]int         // reason -> count
	lastResetTime   time.Time

	// Configuration
	windowDuration  time.Duration
	spikeThreshold  float64 // multiplier for spike detection
}

type RateBucket struct {
	count    int
	window   time.Duration
	lastSeen time.Time
}

func NewAnomalyDetector(windowDuration time.Duration, spikeThreshold float64) *AnomalyDetector {
	return &AnomalyDetector{
		eventRates:     make(map[string]*RateBucket),
		resourceChurn:  make(map[string]*RateBucket),
		errorPatterns:  make(map[string]int),
		lastResetTime:  time.Now(),
		windowDuration: windowDuration,
		spikeThreshold: spikeThreshold,
	}
}

// TrackEvent records an event for anomaly detection
func (ad *AnomalyDetector) TrackEvent(severity, reason string) {
	ad.mu.Lock()
	defer ad.mu.Unlock()

	now := time.Now()

	// Track event rate by severity
	if bucket, ok := ad.eventRates[severity]; ok {
		bucket.count++
		bucket.lastSeen = now
	} else {
		ad.eventRates[severity] = &RateBucket{
			count:    1,
			window:   ad.windowDuration,
			lastSeen: now,
		}
	}

	// Track error patterns
	if severity == "ERROR" || severity == "FATAL" {
		ad.errorPatterns[reason]++
	}

	// Check for anomalies
	ad.detectAnomalies(severity, reason, now)
}

// TrackResourceChurn records resource creation/deletion for churn detection
func (ad *AnomalyDetector) TrackResourceChurn(kind, operation string) {
	ad.mu.Lock()
	defer ad.mu.Unlock()

	now := time.Now()

	if bucket, ok := ad.resourceChurn[kind]; ok {
		bucket.count++
		bucket.lastSeen = now
	} else {
		ad.resourceChurn[kind] = &RateBucket{
			count:    1,
			window:   ad.windowDuration,
			lastSeen: now,
		}
	}

	// Check for excessive churn
	if bucket := ad.resourceChurn[kind]; bucket.count > 50 {
		log.Printf("[ANOMALY] High resource churn detected for %s: %d operations in %v",
			kind, bucket.count, ad.windowDuration)
		anomaliesDetected.WithLabelValues("resource_churn").Inc()
	}
}

// detectAnomalies checks for various anomaly patterns
func (ad *AnomalyDetector) detectAnomalies(severity, reason string, now time.Time) {
	// Reset counters if window expired
	if now.Sub(ad.lastResetTime) > ad.windowDuration {
		ad.reset()
		ad.lastResetTime = now
	}

	// Detect error spikes
	if severity == "ERROR" || severity == "FATAL" {
		if bucket, ok := ad.eventRates[severity]; ok {
			avgRate := float64(bucket.count) / ad.windowDuration.Minutes()
			if avgRate > 10 { // More than 10 errors/minute
				log.Printf("[ANOMALY] Error spike detected: %s at %.2f/min", severity, avgRate)
				anomaliesDetected.WithLabelValues("error_spike").Inc()
			}
		}
	}

	// Detect cascading failures (same reason repeating rapidly)
	if count, ok := ad.errorPatterns[reason]; ok && count > 10 {
		log.Printf("[ANOMALY] Cascading failure detected: %s occurred %d times", reason, count)
		anomaliesDetected.WithLabelValues("cascading_failure").Inc()
	}

	// Detect OOM patterns
	if reason == "OOMKilled" || reason == "LOG_OOM_KILLED" {
		if count := ad.errorPatterns[reason]; count > 3 {
			log.Printf("[ANOMALY] Memory leak suspected: %d OOM events in %v", count, ad.windowDuration)
			anomaliesDetected.WithLabelValues("memory_leak").Inc()
		}
	}
}

// reset clears the counters for the next window
func (ad *AnomalyDetector) reset() {
	ad.eventRates = make(map[string]*RateBucket)
	ad.resourceChurn = make(map[string]*RateBucket)
	ad.errorPatterns = make(map[string]int)
}

// GetAnomalyReport generates a summary of detected anomalies
func (ad *AnomalyDetector) GetAnomalyReport() map[string]interface{} {
	ad.mu.RLock()
	defer ad.mu.RUnlock()

	report := make(map[string]interface{})

	// Event rates
	eventRates := make(map[string]float64)
	for severity, bucket := range ad.eventRates {
		rate := float64(bucket.count) / ad.windowDuration.Minutes()
		eventRates[severity] = rate
	}
	report["event_rates_per_minute"] = eventRates

	// Top error patterns
	report["top_error_patterns"] = ad.errorPatterns

	// Resource churn
	churnRates := make(map[string]int)
	for kind, bucket := range ad.resourceChurn {
		churnRates[kind] = bucket.count
	}
	report["resource_churn"] = churnRates

	return report
}

// Enhanced RCA scoring with anomaly detection
func (ad *AnomalyDetector) AdjustRCAConfidence(baseConfidence float64, reason, severity string) float64 {
	ad.mu.RLock()
	defer ad.mu.RUnlock()

	adjustedConfidence := baseConfidence

	// Boost confidence if this reason is part of an ongoing anomaly
	if count, ok := ad.errorPatterns[reason]; ok && count > 5 {
		// This is part of a pattern, increase confidence
		adjustedConfidence *= 1.2
	}

	// Boost confidence for known cascading failure patterns
	if reason == "OOMKilled" || reason == "CrashLoopBackOff" {
		if ad.errorPatterns[reason] > 3 {
			adjustedConfidence *= 1.3
		}
	}

	// Cap at 1.0
	if adjustedConfidence > 1.0 {
		adjustedConfidence = 1.0
	}

	return adjustedConfidence
}

// StartPeriodicReporting starts a goroutine that logs anomaly reports
func (ad *AnomalyDetector) StartPeriodicReporting(interval time.Duration) chan struct{} {
	stopChan := make(chan struct{})

	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				report := ad.GetAnomalyReport()
				if len(report) > 0 {
					log.Printf("[ANOMALY REPORT] %v", report)
				}
			case <-stopChan:
				return
			}
		}
	}()

	return stopChan
}

// DetectMemoryLeaks analyzes OOM patterns across resources
func (ad *AnomalyDetector) DetectMemoryLeaks(ctx context.Context, graph *Graph) error {
	// Query Neo4j for OOM patterns
	s := graph.drv.NewSession(ctx, nil)
	defer s.Close(ctx)

	cy := `
		MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
		WHERE e.reason IN ['OOMKilled', 'LOG_OOM_KILLED']
		  AND e.event_time > datetime() - duration('PT1H')
		WITH r, count(e) as oom_count
		WHERE oom_count >= 3
		RETURN r.rid, r.kind, r.name, r.ns, oom_count
		ORDER BY oom_count DESC
		LIMIT 10
	`

	result, err := s.Run(ctx, cy, nil)
	if err != nil {
		return err
	}

	leakDetected := false
	for result.Next(ctx) {
		record := result.Record()
		rid, _ := record.Get("r.rid")
		oomCount, _ := record.Get("oom_count")

		log.Printf("[ANOMALY] Memory leak suspected in %v: %d OOM events in last hour", rid, oomCount)
		anomaliesDetected.WithLabelValues("memory_leak").Inc()
		leakDetected = true
	}

	if leakDetected {
		return fmt.Errorf("memory leaks detected")
	}

	return nil
}

// DetectCascadingFailures identifies cascading failure patterns
func (ad *AnomalyDetector) DetectCascadingFailures(ctx context.Context, graph *Graph) error {
	s := graph.drv.NewSession(ctx, nil)
	defer s.Close(ctx)

	cy := `
		MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
		WHERE e.event_time > datetime() - duration('PT15M')
		  AND e.severity IN ['ERROR', 'FATAL']
		WITH r, count(e) as error_count
		WHERE error_count >= 5
		OPTIONAL MATCH (r)-[:SELECTS|RUNS_ON|CONTROLS*1..2]-(related:Resource)
		OPTIONAL MATCH (related)<-[:ABOUT]-(re:Episodic)
		WHERE re.event_time > datetime() - duration('PT15M')
		  AND re.severity IN ['ERROR', 'FATAL']
		WITH r, error_count, count(DISTINCT re) as related_errors
		WHERE related_errors >= 3
		RETURN r.rid, r.kind, r.name, error_count, related_errors
		ORDER BY error_count DESC
		LIMIT 5
	`

	result, err := s.Run(ctx, cy, nil)
	if err != nil {
		return err
	}

	cascadeDetected := false
	for result.Next(ctx) {
		record := result.Record()
		rid, _ := record.Get("r.rid")
		errorCount, _ := record.Get("error_count")
		relatedErrors, _ := record.Get("related_errors")

		log.Printf("[ANOMALY] Cascading failure detected at %v: %d errors with %d related errors",
			rid, errorCount, relatedErrors)
		anomaliesDetected.WithLabelValues("cascading_failure").Inc()
		cascadeDetected = true
	}

	if cascadeDetected {
		return fmt.Errorf("cascading failures detected")
	}

	return nil
}
