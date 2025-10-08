package vectorsearch

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"strings"

	"github.com/neo4j/neo4j-go-driver/v5/neo4j"
)

// Vector Search for semantic queries like:
// - "What bug is caused by what"
// - "Show me memory leak incidents"
// - "Find all pod crashes related to OOM"
// - "What caused the service outage yesterday"

// EmbeddingService handles text embedding and vector search
type EmbeddingService struct {
	driver          neo4j.DriverWithContext
	embeddingModel  string // "openai", "local", "sentence-transformers"
	vectorDimension int
}

// SearchQuery represents a semantic search query
type SearchQuery struct {
	Query          string  `json:"query"`
	TopK           int     `json:"top_k"`           // Number of results
	MinSimilarity  float64 `json:"min_similarity"`  // Cosine similarity threshold
	TimeWindowDays int     `json:"time_window_days"` // Time filter
	Filters        Filters `json:"filters"`
}

type Filters struct {
	Severity    []string `json:"severity"`    // ["ERROR", "FATAL"]
	Kind        []string `json:"kind"`        // ["Pod", "Service"]
	Namespace   []string `json:"namespace"`
	HasIncident bool     `json:"has_incident"`
}

// SearchResult represents a semantic search result
type SearchResult struct {
	EventID     string             `json:"event_id"`
	Reason      string             `json:"reason"`
	Message     string             `json:"message"`
	Severity    string             `json:"severity"`
	EventTime   string             `json:"event_time"`
	Subject     map[string]string  `json:"subject"`
	Similarity  float64            `json:"similarity"`
	RootCauses  []string           `json:"root_causes"`
	Incident    *string            `json:"incident,omitempty"`
	Explanation string             `json:"explanation"` // Why this result matches
}

func NewEmbeddingService(driver neo4j.DriverWithContext, model string) *EmbeddingService {
	return &EmbeddingService{
		driver:          driver,
		embeddingModel:  model,
		vectorDimension: 384, // Default for sentence-transformers/all-MiniLM-L6-v2
	}
}

// GenerateEmbedding generates vector embedding for text
// Supports multiple backends:
// 1. OpenAI API (production)
// 2. Sentence Transformers (local)
// 3. Simple TF-IDF (fallback)
func (es *EmbeddingService) GenerateEmbedding(ctx context.Context, text string) ([]float64, error) {
	switch es.embeddingModel {
	case "openai":
		return es.generateOpenAIEmbedding(ctx, text)
	case "sentence-transformers":
		return es.generateLocalEmbedding(ctx, text)
	default:
		// Simple TF-IDF based embedding (fallback)
		return es.generateSimpleEmbedding(text), nil
	}
}

// generateOpenAIEmbedding uses OpenAI API for embeddings
func (es *EmbeddingService) generateOpenAIEmbedding(ctx context.Context, text string) ([]float64, error) {
	// Implementation would call OpenAI API
	// For now, return placeholder
	return nil, fmt.Errorf("OpenAI embedding not implemented yet")
}

// generateLocalEmbedding uses local sentence-transformers model
func (es *EmbeddingService) generateLocalEmbedding(ctx context.Context, text string) ([]float64, error) {
	// Would call local Python service running sentence-transformers
	// For now, return placeholder
	return nil, fmt.Errorf("Local embedding not implemented yet")
}

// generateSimpleEmbedding creates a simple TF-IDF based embedding
func (es *EmbeddingService) generateSimpleEmbedding(text string) []float64 {
	// K8s-specific keywords and their importance
	keywords := map[string]float64{
		// Errors & Failures
		"oom":              1.0,
		"killed":           0.9,
		"crash":            0.9,
		"fail":             0.8,
		"error":            0.8,
		"fatal":            1.0,
		"panic":            0.9,
		"timeout":          0.7,
		"refused":          0.7,
		// Resource issues
		"memory":           0.8,
		"cpu":              0.7,
		"disk":             0.7,
		"quota":            0.6,
		"limit":            0.6,
		// Network
		"network":          0.7,
		"connection":       0.6,
		"dns":              0.6,
		// K8s Resources
		"pod":              0.5,
		"service":          0.5,
		"deployment":       0.5,
		"node":             0.6,
		// States
		"pending":          0.4,
		"crashloop":        1.0,
		"backoff":          0.7,
		"evicted":          0.8,
		"imagepull":        0.7,
		// Causality
		"caused":           0.9,
		"because":          0.8,
		"due":              0.8,
		"result":           0.7,
		"triggered":        0.8,
	}

	text = strings.ToLower(text)
	words := strings.Fields(text)

	embedding := make([]float64, es.vectorDimension)

	// Simple bag-of-words with keyword weights
	for i, word := range words {
		if weight, ok := keywords[word]; ok {
			// Distribute weight across embedding dimensions using position
			idx := (i * 17) % es.vectorDimension // Prime number for distribution
			embedding[idx] += weight
		}
	}

	// Normalize
	return normalizeVector(embedding)
}

// SemanticSearch performs vector similarity search
func (es *EmbeddingService) SemanticSearch(ctx context.Context, query SearchQuery) ([]SearchResult, error) {
	// Generate embedding for query
	queryVector, err := es.GenerateEmbedding(ctx, query.Query)
	if err != nil {
		// Fallback to keyword search
		return es.keywordSearch(ctx, query)
	}

	session := es.driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeRead})
	defer session.Close(ctx)

	// Build filter clauses
	whereClauses := []string{"e.embedding IS NOT NULL"}
	params := map[string]interface{}{
		"queryVector": queryVector,
		"topK":        query.TopK,
		"minSim":      query.MinSimilarity,
	}

	if query.TimeWindowDays > 0 {
		whereClauses = append(whereClauses,
			fmt.Sprintf("e.event_time > datetime() - duration('P%dD')", query.TimeWindowDays))
	}

	if len(query.Filters.Severity) > 0 {
		whereClauses = append(whereClauses, "e.severity IN $severities")
		params["severities"] = query.Filters.Severity
	}

	whereClause := strings.Join(whereClauses, " AND ")

	// Vector similarity search using cosine similarity
	cypher := fmt.Sprintf(`
		MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
		WHERE %s

		// Calculate cosine similarity
		WITH e, r,
		     gds.similarity.cosine(e.embedding, $queryVector) AS similarity
		WHERE similarity >= $minSim

		// Get root causes
		OPTIONAL MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(e)

		// Get incident
		OPTIONAL MATCH (e)-[:PART_OF]->(inc:Incident)

		RETURN
			e.eid as event_id,
			e.reason as reason,
			e.message as message,
			e.severity as severity,
			toString(e.event_time) as event_time,
			r.rid as subject_rid,
			r.kind as subject_kind,
			r.name as subject_name,
			r.ns as subject_ns,
			similarity,
			collect(DISTINCT cause.eid) as root_causes,
			inc.resource_id as incident_id
		ORDER BY similarity DESC
		LIMIT $topK
	`, whereClause)

	result, err := session.Run(ctx, cypher, params)
	if err != nil {
		return nil, err
	}

	var results []SearchResult
	for result.Next(ctx) {
		record := result.Record()

		sr := SearchResult{
			EventID:   getString(record, "event_id"),
			Reason:    getString(record, "reason"),
			Message:   getString(record, "message"),
			Severity:  getString(record, "severity"),
			EventTime: getString(record, "event_time"),
			Similarity: getFloat(record, "similarity"),
			Subject: map[string]string{
				"rid":       getString(record, "subject_rid"),
				"kind":      getString(record, "subject_kind"),
				"name":      getString(record, "subject_name"),
				"namespace": getString(record, "subject_ns"),
			},
			Explanation: es.explainMatch(query.Query, getString(record, "reason"), getString(record, "message")),
		}

		if causes, ok := record.Get("root_causes"); ok {
			if causeList, ok := causes.([]interface{}); ok {
				for _, c := range causeList {
					if causeStr, ok := c.(string); ok && causeStr != "" {
						sr.RootCauses = append(sr.RootCauses, causeStr)
					}
				}
			}
		}

		if incID := getString(record, "incident_id"); incID != "" {
			sr.Incident = &incID
		}

		results = append(results, sr)
	}

	return results, nil
}

// keywordSearch fallback for when embeddings are not available
func (es *EmbeddingService) keywordSearch(ctx context.Context, query SearchQuery) ([]SearchResult, error) {
	session := es.driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeRead})
	defer session.Close(ctx)

	keywords := extractKeywords(query.Query)

	cypher := `
		MATCH (e:Episodic)-[:ABOUT]->(r:Resource)
		WHERE (
			e.reason =~ $pattern OR
			e.message =~ $pattern
		)
		AND e.event_time > datetime() - duration('P7D')

		OPTIONAL MATCH (cause:Episodic)-[:POTENTIAL_CAUSE]->(e)
		OPTIONAL MATCH (e)-[:PART_OF]->(inc:Incident)

		RETURN
			e.eid as event_id,
			e.reason as reason,
			e.message as message,
			e.severity as severity,
			toString(e.event_time) as event_time,
			r.rid as subject_rid,
			r.kind as subject_kind,
			r.name as subject_name,
			r.ns as subject_ns,
			collect(DISTINCT cause.eid) as root_causes,
			inc.resource_id as incident_id
		ORDER BY e.event_time DESC
		LIMIT $topK
	`

	pattern := fmt.Sprintf("(?i).*(%s).*", strings.Join(keywords, "|"))
	result, err := session.Run(ctx, cypher, map[string]interface{}{
		"pattern": pattern,
		"topK":    query.TopK,
	})
	if err != nil {
		return nil, err
	}

	var results []SearchResult
	for result.Next(ctx) {
		record := result.Record()

		sr := SearchResult{
			EventID:   getString(record, "event_id"),
			Reason:    getString(record, "reason"),
			Message:   getString(record, "message"),
			Severity:  getString(record, "severity"),
			EventTime: getString(record, "event_time"),
			Similarity: 0.5, // Default for keyword match
			Subject: map[string]string{
				"rid":       getString(record, "subject_rid"),
				"kind":      getString(record, "subject_kind"),
				"name":      getString(record, "subject_name"),
				"namespace": getString(record, "subject_ns"),
			},
			Explanation: "Keyword match",
		}

		if causes, ok := record.Get("root_causes"); ok {
			if causeList, ok := causes.([]interface{}); ok {
				for _, c := range causeList {
					if causeStr, ok := c.(string); ok && causeStr != "" {
						sr.RootCauses = append(sr.RootCauses, causeStr)
					}
				}
			}
		}

		results = append(results, sr)
	}

	return results, nil
}

// CausalSearch answers "what caused what" questions
func (es *EmbeddingService) CausalSearch(ctx context.Context, query string) ([]CausalChain, error) {
	session := es.driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeRead})
	defer session.Close(ctx)

	keywords := extractKeywords(query)
	pattern := fmt.Sprintf("(?i).*(%s).*", strings.Join(keywords, "|"))

	cypher := `
		MATCH (effect:Episodic)-[:ABOUT]->(r:Resource)
		WHERE effect.reason =~ $pattern OR effect.message =~ $pattern

		// Find causal chain
		MATCH path = (root:Episodic)-[:POTENTIAL_CAUSE*1..3]->(effect)
		WHERE NOT EXISTS { (:Episodic)-[:POTENTIAL_CAUSE]->(root) }

		WITH path, effect, r,
		     [node in nodes(path) | node.eid] as event_ids,
		     [node in nodes(path) | node.reason] as reasons,
		     [rel in relationships(path) | rel.confidence] as confidences

		RETURN
			effect.eid as effect_id,
			effect.reason as effect_reason,
			r.rid as effect_resource,
			event_ids,
			reasons,
			confidences,
			length(path) as chain_length
		ORDER BY chain_length ASC, confidences[0] DESC
		LIMIT 10
	`

	result, err := session.Run(ctx, cypher, map[string]interface{}{
		"pattern": pattern,
	})
	if err != nil {
		return nil, err
	}

	var chains []CausalChain
	for result.Next(ctx) {
		record := result.Record()

		chain := CausalChain{
			EffectID:       getString(record, "effect_id"),
			EffectReason:   getString(record, "effect_reason"),
			EffectResource: getString(record, "effect_resource"),
			ChainLength:    int(getInt64(record, "chain_length")),
		}

		if eventIDs, ok := record.Get("event_ids"); ok {
			if ids, ok := eventIDs.([]interface{}); ok {
				for _, id := range ids {
					chain.EventIDs = append(chain.EventIDs, fmt.Sprint(id))
				}
			}
		}

		if reasons, ok := record.Get("reasons"); ok {
			if r, ok := reasons.([]interface{}); ok {
				for _, reason := range r {
					chain.Reasons = append(chain.Reasons, fmt.Sprint(reason))
				}
			}
		}

		if confs, ok := record.Get("confidences"); ok {
			if c, ok := confs.([]interface{}); ok {
				for _, conf := range c {
					if f, ok := conf.(float64); ok {
						chain.Confidences = append(chain.Confidences, f)
					}
				}
			}
		}

		chains = append(chains, chain)
	}

	return chains, nil
}

type CausalChain struct {
	EffectID       string    `json:"effect_id"`
	EffectReason   string    `json:"effect_reason"`
	EffectResource string    `json:"effect_resource"`
	EventIDs       []string  `json:"event_ids"`
	Reasons        []string  `json:"reasons"`
	Confidences    []float64 `json:"confidences"`
	ChainLength    int       `json:"chain_length"`
	Explanation    string    `json:"explanation"`
}

// IndexEmbeddings generates and stores embeddings for all events
func (es *EmbeddingService) IndexEmbeddings(ctx context.Context, batchSize int) error {
	session := es.driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer session.Close(ctx)

	// Get events without embeddings
	result, err := session.Run(ctx, `
		MATCH (e:Episodic)
		WHERE e.embedding IS NULL
		RETURN e.eid as eid, e.reason as reason, e.message as message
		LIMIT $batchSize
	`, map[string]interface{}{"batchSize": batchSize})
	if err != nil {
		return err
	}

	var updates []map[string]interface{}
	for result.Next(ctx) {
		record := result.Record()
		eid := getString(record, "eid")
		reason := getString(record, "reason")
		message := getString(record, "message")

		// Generate embedding
		text := reason + " " + message
		embedding, err := es.GenerateEmbedding(ctx, text)
		if err != nil {
			continue
		}

		updates = append(updates, map[string]interface{}{
			"eid":       eid,
			"embedding": embedding,
		})
	}

	// Batch update
	if len(updates) > 0 {
		_, err = session.Run(ctx, `
			UNWIND $updates as update
			MATCH (e:Episodic {eid: update.eid})
			SET e.embedding = update.embedding
		`, map[string]interface{}{"updates": updates})
		if err != nil {
			return err
		}
	}

	return nil
}

// Helper functions

func normalizeVector(v []float64) []float64 {
	var magnitude float64
	for _, val := range v {
		magnitude += val * val
	}
	magnitude = math.Sqrt(magnitude)

	if magnitude == 0 {
		return v
	}

	normalized := make([]float64, len(v))
	for i, val := range v {
		normalized[i] = val / magnitude
	}
	return normalized
}

func extractKeywords(query string) []string {
	query = strings.ToLower(query)

	// Remove common words
	stopWords := map[string]bool{
		"what": true, "is": true, "the": true, "a": true, "an": true,
		"caused": true, "by": true, "show": true, "me": true, "find": true,
		"all": true, "related": true, "to": true,
	}

	words := strings.Fields(query)
	var keywords []string
	for _, word := range words {
		word = strings.Trim(word, ".,?!")
		if !stopWords[word] && len(word) > 2 {
			keywords = append(keywords, word)
		}
	}

	return keywords
}

func (es *EmbeddingService) explainMatch(query, reason, message string) string {
	queryLower := strings.ToLower(query)
	reasonLower := strings.ToLower(reason)
	messageLower := strings.ToLower(message)

	// Extract keywords from query
	keywords := extractKeywords(query)

	var matches []string
	for _, kw := range keywords {
		if strings.Contains(reasonLower, kw) {
			matches = append(matches, fmt.Sprintf("'%s' in reason", kw))
		} else if strings.Contains(messageLower, kw) {
			matches = append(matches, fmt.Sprintf("'%s' in message", kw))
		}
	}

	if len(matches) > 0 {
		return "Matched: " + strings.Join(matches, ", ")
	}

	return "Semantic similarity"
}

func getString(record *neo4j.Record, key string) string {
	if val, ok := record.Get(key); ok && val != nil {
		return fmt.Sprint(val)
	}
	return ""
}

func getFloat(record *neo4j.Record, key string) float64 {
	if val, ok := record.Get(key); ok {
		if f, ok := val.(float64); ok {
			return f
		}
	}
	return 0.0
}

func getInt64(record *neo4j.Record, key string) int64 {
	if val, ok := record.Get(key); ok {
		if i, ok := val.(int64); ok {
			return i
		}
	}
	return 0
}
