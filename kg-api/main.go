package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gorilla/mux"
	"github.com/neo4j/neo4j-go-driver/v5/neo4j"
	"github.com/rs/cors"
)

// Knowledge Graph API for incremental updates and RCA queries
// Addresses: "How to update knowledge graph as K8s changes quickly"

type Server struct {
	driver neo4j.DriverWithContext
	port   string
}

// GraphUpdate represents an incremental update to the knowledge graph
type GraphUpdate struct {
	Timestamp time.Time              `json:"timestamp"`
	Resources []ResourceUpdate       `json:"resources,omitempty"`
	Edges     []EdgeUpdate           `json:"edges,omitempty"`
	Events    []EventUpdate          `json:"events,omitempty"`
}

type ResourceUpdate struct {
	Action    string            `json:"action"` // CREATE, UPDATE, DELETE
	Kind      string            `json:"kind"`
	UID       string            `json:"uid"`
	Namespace string            `json:"namespace,omitempty"`
	Name      string            `json:"name"`
	Labels    map[string]string `json:"labels,omitempty"`
	Status    map[string]any    `json:"status,omitempty"`
}

type EdgeUpdate struct {
	Action string `json:"action"` // CREATE, DELETE
	From   string `json:"from"`
	To     string `json:"to"`
	Type   string `json:"type"`
}

type EventUpdate struct {
	Action    string `json:"action"` // CREATE
	EventID   string `json:"event_id"`
	EventTime string `json:"event_time"`
	Severity  string `json:"severity"`
	Reason    string `json:"reason"`
	Message   string `json:"message"`
	SubjectUID string `json:"subject_uid"`
}

// RCAQuery represents a root cause analysis query
type RCAQuery struct {
	EventID      string `json:"event_id"`
	ResourceUID  string `json:"resource_uid,omitempty"`
	TimeWindow   int    `json:"time_window_minutes,omitempty"` // default: 15
	MaxHops      int    `json:"max_hops,omitempty"`            // default: 3
	MinConfidence float64 `json:"min_confidence,omitempty"`     // default: 0.4
}

// RCAResult represents the root cause analysis result
type RCAResult struct {
	EventID       string         `json:"event_id"`
	EventTime     string         `json:"event_time"`
	Reason        string         `json:"reason"`
	Severity      string         `json:"severity"`
	Subject       ResourceInfo   `json:"subject"`
	PotentialCauses []Cause      `json:"potential_causes"`
	RelatedIncident *Incident    `json:"related_incident,omitempty"`
	BlastRadius     []ResourceInfo `json:"blast_radius"`
	Timeline        []TimelineEvent `json:"timeline"`
}

type ResourceInfo struct {
	RID       string            `json:"rid"`
	Kind      string            `json:"kind"`
	Name      string            `json:"name"`
	Namespace string            `json:"namespace,omitempty"`
	Labels    map[string]string `json:"labels,omitempty"`
}

type Cause struct {
	EventID        string       `json:"event_id"`
	EventTime      string       `json:"event_time"`
	Reason         string       `json:"reason"`
	Message        string       `json:"message"`
	Severity       string       `json:"severity"`
	Confidence     float64      `json:"confidence"`
	Hops           int          `json:"hops"`
	Subject        ResourceInfo `json:"subject"`
	TemporalScore  float64      `json:"temporal_score"`
	DistanceScore  float64      `json:"distance_score"`
	DomainScore    float64      `json:"domain_score"`
}

type Incident struct {
	ResourceID   string    `json:"resource_id"`
	WindowStart  string    `json:"window_start"`
	WindowEnd    string    `json:"window_end"`
	EventCount   int       `json:"event_count"`
	Severity     string    `json:"severity"`
}

type TimelineEvent struct {
	EventTime string `json:"event_time"`
	Reason    string `json:"reason"`
	Severity  string `json:"severity"`
	Message   string `json:"message"`
	Resource  string `json:"resource"`
}

// GraphStats represents current graph statistics
type GraphStats struct {
	Timestamp       time.Time         `json:"timestamp"`
	Resources       int               `json:"resources"`
	Episodic        int               `json:"episodic_events"`
	Incidents       int               `json:"incidents"`
	Edges           int               `json:"edges"`
	ResourcesByKind map[string]int    `json:"resources_by_kind"`
	EdgesByType     map[string]int    `json:"edges_by_type"`
	EventsBySeverity map[string]int   `json:"events_by_severity"`
	OldestEvent     string            `json:"oldest_event"`
	NewestEvent     string            `json:"newest_event"`
}

func main() {
	neo4jURI := getenv("NEO4J_URI", "neo4j://neo4j:7687")
	neo4jUser := getenv("NEO4J_USER", "neo4j")
	neo4jPass := getenv("NEO4J_PASS", "password")
	port := getenv("PORT", "8080")

	driver, err := neo4j.NewDriverWithContext(neo4jURI, neo4j.BasicAuth(neo4jUser, neo4jPass, ""))
	if err != nil {
		log.Fatalf("Failed to connect to Neo4j: %v", err)
	}
	defer driver.Close(context.Background())

	server := &Server{
		driver: driver,
		port:   port,
	}

	router := mux.NewRouter()

	// RCA endpoints
	router.HandleFunc("/api/v1/rca", server.handleRCAQuery).Methods("POST")
	router.HandleFunc("/api/v1/rca/{event_id}", server.handleRCAByEventID).Methods("GET")

	// Incremental update endpoints
	router.HandleFunc("/api/v1/updates", server.handleIncrementalUpdate).Methods("POST")
	router.HandleFunc("/api/v1/updates/batch", server.handleBatchUpdate).Methods("POST")

	// Graph query endpoints
	router.HandleFunc("/api/v1/graph/stats", server.handleGraphStats).Methods("GET")
	router.HandleFunc("/api/v1/graph/resource/{uid}", server.handleResourceQuery).Methods("GET")
	router.HandleFunc("/api/v1/graph/topology/{uid}", server.handleTopologyQuery).Methods("GET")

	// Incident endpoints
	router.HandleFunc("/api/v1/incidents", server.handleIncidentsList).Methods("GET")
	router.HandleFunc("/api/v1/incidents/{resource_id}", server.handleIncidentByResource).Methods("GET")

	// Health endpoints
	router.HandleFunc("/healthz", server.handleHealth).Methods("GET")
	router.HandleFunc("/readyz", server.handleReadiness).Methods("GET")

	// CORS
	c := cors.New(cors.Options{
		AllowedOrigins: []string{"*"},
		AllowedMethods: []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders: []string{"*"},
	})
	handler := c.Handler(router)

	log.Printf("🚀 Knowledge Graph API starting on :%s", port)
	log.Printf("📊 Endpoints:")
	log.Printf("   POST   /api/v1/rca - Root Cause Analysis")
	log.Printf("   GET    /api/v1/rca/{event_id} - RCA by Event ID")
	log.Printf("   POST   /api/v1/updates - Incremental graph updates")
	log.Printf("   GET    /api/v1/graph/stats - Graph statistics")
	log.Printf("   GET    /api/v1/incidents - List active incidents")

	if err := http.ListenAndServe(":"+port, handler); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

func (s *Server) handleRCAQuery(w http.ResponseWriter, r *http.Request) {
	var query RCAQuery
	if err := json.NewDecoder(r.Body).Decode(&query); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Set defaults
	if query.TimeWindow == 0 {
		query.TimeWindow = 15
	}
	if query.MaxHops == 0 {
		query.MaxHops = 3
	}
	if query.MinConfidence == 0 {
		query.MinConfidence = 0.4
	}

	result, err := s.performRCA(r.Context(), query)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (s *Server) handleRCAByEventID(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	eventID := vars["event_id"]

	query := RCAQuery{
		EventID:      eventID,
		TimeWindow:   15,
		MaxHops:      3,
		MinConfidence: 0.4,
	}

	result, err := s.performRCA(r.Context(), query)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (s *Server) performRCA(ctx context.Context, query RCAQuery) (*RCAResult, error) {
	session := s.driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeRead})
	defer session.Close(ctx)

	// Enhanced RCA query with confidence scoring
	cypher := `
	MATCH (e:Episodic {eid:$eid})-[:ABOUT]->(subj:Resource)
	OPTIONAL MATCH (e)<-[pc:POTENTIAL_CAUSE]-(cause:Episodic)-[:ABOUT]->(causeRes:Resource)
	WHERE pc.confidence >= $minConfidence AND pc.hops <= $maxHops
	OPTIONAL MATCH (e)-[:PART_OF]->(inc:Incident)
	OPTIONAL MATCH (subj)-[*1..2]-(related:Resource)
	WHERE related <> subj
	RETURN
		e.eid as event_id,
		e.event_time as event_time,
		e.reason as reason,
		e.severity as severity,
		e.message as message,
		subj.rid as subj_rid,
		subj.kind as subj_kind,
		subj.name as subj_name,
		subj.ns as subj_ns,
		collect(DISTINCT {
			event_id: cause.eid,
			event_time: toString(cause.event_time),
			reason: cause.reason,
			message: cause.message,
			severity: cause.severity,
			confidence: pc.confidence,
			hops: pc.hops,
			temporal_score: pc.temporal_score,
			distance_score: pc.distance_score,
			domain_score: pc.domain_score,
			subject_rid: causeRes.rid,
			subject_kind: causeRes.kind,
			subject_name: causeRes.name,
			subject_ns: causeRes.ns
		}) as causes,
		collect(DISTINCT {
			rid: related.rid,
			kind: related.kind,
			name: related.name,
			ns: related.ns
		}) as blast_radius,
		inc.resource_id as inc_resource_id,
		inc.window_start as inc_window_start,
		inc.window_end as inc_window_end,
		inc.event_count as inc_event_count
	`

	result, err := session.Run(ctx, cypher, map[string]any{
		"eid":           query.EventID,
		"minConfidence": query.MinConfidence,
		"maxHops":       query.MaxHops,
	})
	if err != nil {
		return nil, err
	}

	if !result.Next(ctx) {
		return nil, fmt.Errorf("event not found: %s", query.EventID)
	}

	record := result.Record()

	rcaResult := &RCAResult{
		EventID:   getString(record, "event_id"),
		EventTime: getString(record, "event_time"),
		Reason:    getString(record, "reason"),
		Severity:  getString(record, "severity"),
		Subject: ResourceInfo{
			RID:       getString(record, "subj_rid"),
			Kind:      getString(record, "subj_kind"),
			Name:      getString(record, "subj_name"),
			Namespace: getString(record, "subj_ns"),
		},
		PotentialCauses: []Cause{},
		BlastRadius:     []ResourceInfo{},
		Timeline:        []TimelineEvent{},
	}

	// Parse causes
	if causesRaw, ok := record.Get("causes"); ok {
		if causes, ok := causesRaw.([]any); ok {
			for _, c := range causes {
				if causeMap, ok := c.(map[string]any); ok {
					if causeMap["event_id"] != nil {
						rcaResult.PotentialCauses = append(rcaResult.PotentialCauses, Cause{
							EventID:       fmt.Sprint(causeMap["event_id"]),
							EventTime:     fmt.Sprint(causeMap["event_time"]),
							Reason:        fmt.Sprint(causeMap["reason"]),
							Message:       fmt.Sprint(causeMap["message"]),
							Severity:      fmt.Sprint(causeMap["severity"]),
							Confidence:    getFloat64(causeMap, "confidence"),
							Hops:          int(getInt64(causeMap, "hops")),
							TemporalScore: getFloat64(causeMap, "temporal_score"),
							DistanceScore: getFloat64(causeMap, "distance_score"),
							DomainScore:   getFloat64(causeMap, "domain_score"),
							Subject: ResourceInfo{
								RID:       fmt.Sprint(causeMap["subject_rid"]),
								Kind:      fmt.Sprint(causeMap["subject_kind"]),
								Name:      fmt.Sprint(causeMap["subject_name"]),
								Namespace: fmt.Sprint(causeMap["subject_ns"]),
							},
						})
					}
				}
			}
		}
	}

	// Parse blast radius
	if blastRaw, ok := record.Get("blast_radius"); ok {
		if blast, ok := blastRaw.([]any); ok {
			for _, r := range blast {
				if resMap, ok := r.(map[string]any); ok {
					if resMap["rid"] != nil {
						rcaResult.BlastRadius = append(rcaResult.BlastRadius, ResourceInfo{
							RID:       fmt.Sprint(resMap["rid"]),
							Kind:      fmt.Sprint(resMap["kind"]),
							Name:      fmt.Sprint(resMap["name"]),
							Namespace: fmt.Sprint(resMap["ns"]),
						})
					}
				}
			}
		}
	}

	// Parse incident
	if incResID, ok := record.Get("inc_resource_id"); ok && incResID != nil {
		rcaResult.RelatedIncident = &Incident{
			ResourceID:  fmt.Sprint(incResID),
			WindowStart: getString(record, "inc_window_start"),
			WindowEnd:   getString(record, "inc_window_end"),
			EventCount:  int(getInt64FromRecord(record, "inc_event_count")),
		}
	}

	return rcaResult, nil
}

func (s *Server) handleIncrementalUpdate(w http.ResponseWriter, r *http.Request) {
	var update GraphUpdate
	if err := json.NewDecoder(r.Body).Decode(&update); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	if err := s.applyGraphUpdate(r.Context(), update); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func (s *Server) applyGraphUpdate(ctx context.Context, update GraphUpdate) error {
	session := s.driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer session.Close(ctx)

	// Apply resource updates
	for _, res := range update.Resources {
		switch strings.ToUpper(res.Action) {
		case "CREATE", "UPDATE":
			_, err := session.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
				_, err := tx.Run(ctx, `
					MERGE (r:Resource {uid: $uid})
					SET r.kind = $kind,
					    r.name = $name,
					    r.ns = $ns,
					    r.labels_json = $labels,
					    r.updated_at = datetime()
				`, map[string]any{
					"uid":    res.UID,
					"kind":   res.Kind,
					"name":   res.Name,
					"ns":     res.Namespace,
					"labels": toJSON(res.Labels),
				})
				return nil, err
			})
			if err != nil {
				return err
			}
		case "DELETE":
			_, err := session.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
				_, err := tx.Run(ctx, `MATCH (r:Resource {uid: $uid}) DETACH DELETE r`, map[string]any{"uid": res.UID})
				return nil, err
			})
			if err != nil {
				return err
			}
		}
	}

	return nil
}

func (s *Server) handleGraphStats(w http.ResponseWriter, r *http.Request) {
	stats, err := s.getGraphStats(r.Context())
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(stats)
}

func (s *Server) getGraphStats(ctx context.Context) (*GraphStats, error) {
	session := s.driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeRead})
	defer session.Close(ctx)

	stats := &GraphStats{
		Timestamp:        time.Now(),
		ResourcesByKind:  make(map[string]int),
		EdgesByType:      make(map[string]int),
		EventsBySeverity: make(map[string]int),
	}

	// Get counts
	result, err := session.Run(ctx, `
		OPTIONAL MATCH (r:Resource) WITH count(r) as resources
		OPTIONAL MATCH (e:Episodic) WITH resources, count(e) as events
		OPTIONAL MATCH (inc:Incident) WITH resources, events, count(inc) as incidents
		OPTIONAL MATCH ()-[rel]->() WITH resources, events, incidents, count(rel) as edges
		RETURN resources, events, incidents, edges
	`, nil)
	if err != nil {
		return nil, err
	}

	if result.Next(ctx) {
		record := result.Record()
		stats.Resources = int(getInt64FromRecord(record, "resources"))
		stats.Episodic = int(getInt64FromRecord(record, "events"))
		stats.Incidents = int(getInt64FromRecord(record, "incidents"))
		stats.Edges = int(getInt64FromRecord(record, "edges"))
	}

	return stats, nil
}

func (s *Server) handleIncidentsList(w http.ResponseWriter, r *http.Request) {
	// Implementation for listing active incidents
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode([]Incident{})
}

func (s *Server) handleIncidentByResource(w http.ResponseWriter, r *http.Request) {
	// Implementation for getting incident by resource
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(nil)
}

func (s *Server) handleResourceQuery(w http.ResponseWriter, r *http.Request) {
	// Implementation for resource query
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(nil)
}

func (s *Server) handleTopologyQuery(w http.ResponseWriter, r *http.Request) {
	// Implementation for topology query
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(nil)
}

func (s *Server) handleBatchUpdate(w http.ResponseWriter, r *http.Request) {
	// Implementation for batch updates
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("ok"))
}

func (s *Server) handleReadiness(w http.ResponseWriter, r *http.Request) {
	// Check Neo4j connectivity
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	session := s.driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeRead})
	defer session.Close(ctx)

	_, err := session.Run(ctx, "RETURN 1", nil)
	if err != nil {
		http.Error(w, "not ready", http.StatusServiceUnavailable)
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("ready"))
}

// Helper functions
func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getString(record *neo4j.Record, key string) string {
	if val, ok := record.Get(key); ok && val != nil {
		return fmt.Sprint(val)
	}
	return ""
}

func getInt64FromRecord(record *neo4j.Record, key string) int64 {
	if val, ok := record.Get(key); ok {
		if i, ok := val.(int64); ok {
			return i
		}
	}
	return 0
}

func getInt64(m map[string]any, key string) int64 {
	if val, ok := m[key]; ok {
		if i, ok := val.(int64); ok {
			return i
		}
		if f, ok := val.(float64); ok {
			return int64(f)
		}
	}
	return 0
}

func getFloat64(m map[string]any, key string) float64 {
	if val, ok := m[key]; ok {
		if f, ok := val.(float64); ok {
			return f
		}
		if i, ok := val.(int64); ok {
			return float64(i)
		}
	}
	return 0.0
}

func toJSON(v any) string {
	b, _ := json.Marshal(v)
	return string(b)
}
