package main

import (
	"context"
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"regexp"
	"sort"
	"strings"
	"syscall"
	"time"
	"unicode"

	"github.com/IBM/sarama"
	"github.com/neo4j/neo4j-go-driver/v5/neo4j"
)

/***************
 * Input models
 ***************/

// state.k8s.resource
type ResourceRecord struct {
	Op        string            `json:"op"`
	At        time.Time         `json:"at"`
	ClientID  string            `json:"client_id,omitempty"` // Multi-tenant: client identifier
	Cluster   string            `json:"cluster"`
	Kind      string            `json:"kind"`
	UID       string            `json:"uid"`
	Namespace string            `json:"namespace,omitempty"`
	Name      string            `json:"name"`
	Labels    map[string]string `json:"labels,omitempty"`
	OwnerRefs []OwnerRef        `json:"ownerRefs,omitempty"`
	Node      string            `json:"node,omitempty"`
	PodIP     string            `json:"podIP,omitempty"`
	Image     string            `json:"image,omitempty"`
	Replicas  *int32            `json:"replicas,omitempty"`
	Status    map[string]any    `json:"status,omitempty"`
	Spec      any               `json:"spec,omitempty"`
}
type OwnerRef struct{ Kind, Name string }

// state.k8s.topology
type EdgeRecord struct {
	Op       string    `json:"op"`
	At       time.Time `json:"at"`
	ClientID string    `json:"client_id,omitempty"` // Multi-tenant: client identifier
	Cluster  string    `json:"cluster"`
	ID       string    `json:"id"`
	From     string    `json:"from"`
	To       string    `json:"to"`
	Type     string    `json:"type"` // SELECTS | RUNS_ON | CONTROLS | ...
}

// events.normalized
type EventNormalized struct {
	EventID   string       `json:"event_id"`
	EventTime string       `json:"event_time"`
	ClientID  string       `json:"client_id,omitempty"` // Multi-tenant: client identifier
	Etype     string       `json:"etype"`
	Severity  string       `json:"severity"`
	Reason    string       `json:"reason"`
	Message   string       `json:"message"`
	Subject   EventSubject `json:"subject"`
	// source/labels/annotations can exist; we ignore here on purpose
}
type EventSubject struct {
	Kind string `json:"kind"`
	UID  string `json:"uid"`
	NS   string `json:"ns"`
	Name string `json:"name"`
}

// logs.normalized (Vector)
type LogNormalized struct {
	EventID   string       `json:"event_id"`
	EventTime string       `json:"event_time"`
	ClientID  string       `json:"client_id,omitempty"` // Multi-tenant: client identifier
	Etype     string       `json:"etype"`               // "k8s.log"
	Severity  string       `json:"severity"`            // INFO/WARNING/ERROR/FATAL
	Message   string       `json:"message"`             // normalized text
	Subject   EventSubject `json:"subject"`             // kind=Pod, ns/name (uid often empty)
	// helpful fallbacks:
	PodUID string `json:"pod_uid,omitempty"`
	PodNS  string `json:"pod_namespace,omitempty"`
	Pod    string `json:"pod_name,omitempty"`
	// nested kubernetes object may also carry pod_uid
	Kubernetes struct {
		PodUID string `json:"pod_uid,omitempty"`
	} `json:"kubernetes"`
}

// state.prom.targets
type PromTargetRecord struct {
	Op         string            `json:"op"` // UPSERT/DELETE (tombstone = Value=nil)
	At         time.Time         `json:"at"`
	ClientID   string            `json:"client_id,omitempty"` // Multi-tenant: client identifier
	Cluster    string            `json:"cluster"`
	Labels     map[string]string `json:"labels"`
	ScrapeURL  string            `json:"scrapeUrl"`
	Health     string            `json:"health"`
	LastScrape string            `json:"lastScrape"`
	LastError  string            `json:"lastError,omitempty"`
}

// state.prom.rules
type RuleRecord struct {
	Op          string            `json:"op"`
	At          time.Time         `json:"at"`
	ClientID    string            `json:"client_id,omitempty"` // Multi-tenant: client identifier
	Cluster     string            `json:"cluster"`
	Group       string            `json:"group"`
	Rule        string            `json:"rule"`
	Type        string            `json:"type"` // alerting/recording
	Labels      map[string]string `json:"labels,omitempty"`
	Annotations map[string]string `json:"annotations,omitempty"`
	Expr        string            `json:"expr,omitempty"`
}

/***************
 * Env & helpers
 ***************/
func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func safeLabelName(s string) string {
	s = strings.TrimSpace(s)
	if s == "" {
		return "L_Unknown"
	}
	var b []rune
	for _, r := range s {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || r == '_' {
			b = append(b, r)
		} else {
			b = append(b, '_')
		}
	}
	if len(b) == 0 || !unicode.IsLetter(b[0]) {
		return "L_" + string(b)
	}
	return string(b)
}
func safeRelTypeName(s string) string {
	s = strings.TrimSpace(strings.ToUpper(s))
	if s == "" {
		return "R_REL"
	}
	var b []rune
	for _, r := range s {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || r == '_' {
			b = append(b, r)
		} else {
			b = append(b, '_')
		}
	}
	if len(b) == 0 || !unicode.IsLetter(b[0]) {
		return "R_" + string(b)
	}
	return string(b)
}

func toJSON(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		return "{}"
	}
	return string(b)
}
func labelsToKV(m map[string]string) []string {
	if len(m) == 0 {
		return nil
	}
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := make([]string, 0, len(keys))
	for _, k := range keys {
		out = append(out, k+"="+m[k])
	}
	return out
}

func isConstraintErr(err error) bool {
	if ne, ok := err.(*neo4j.Neo4jError); ok {
		return strings.Contains(ne.Code, "ConstraintValidationFailed")
	}
	return false
}

func splitTenantKey(key string) (tenant, raw string) {
    // Support both historic "tenant|raw" and newer "tenant::raw" formats
    if strings.Contains(key, "::") {
        parts := strings.SplitN(key, "::", 2)
        if len(parts) == 2 && parts[0] != "" {
            return parts[0], parts[1]
        }
    }
    parts := strings.SplitN(key, "|", 2)
    if len(parts) == 2 && parts[0] != "" {
        return parts[0], parts[1]
    }
    return "", key
}
func writeWithRetry(ctx context.Context, s neo4j.SessionWithContext, fn func(tx neo4j.ManagedTransaction) error) error {
	var last error
	for i := 0; i < 3; i++ {
		_, last = s.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
			if err := fn(tx); err != nil {
				return nil, err
			}
			return nil, nil
		})
		if last == nil {
			return nil
		}
		if isConstraintErr(last) {
			time.Sleep(time.Duration(i+1) * 120 * time.Millisecond)
			continue
		}
		break
	}
	return last
}

var (
	topicRes       = getenv("TOPIC_RES", "state.k8s.resource")
	topicTopo      = getenv("TOPIC_TOPO", "state.k8s.topology")
	topicEvt       = getenv("TOPIC_EVT", "events.normalized")
	topicLogs      = getenv("TOPIC_LOGS", "logs.normalized") // NEW
	topicPromTgts  = getenv("TOPIC_PROM_TARGETS", "state.prom.targets")
	topicPromRules = getenv("TOPIC_PROM_RULES", "state.prom.rules")
	topicCommands  = getenv("TOPIC_COMMANDS", "graph.commands")
	ridKeyRe       = regexp.MustCompile(`^([A-Za-z]+):(.+)$`)
)

/***************
 * Neo4j layer
 ***************/
type Graph struct{ drv neo4j.DriverWithContext }

func NewGraph(uri, user, pass string) (*Graph, error) {
	drv, err := neo4j.NewDriverWithContext(uri, neo4j.BasicAuth(user, pass, ""))
	if err != nil {
		return nil, err
	}
	return &Graph{drv: drv}, nil
}
func (g *Graph) Close(ctx context.Context) { _ = g.drv.Close(ctx) }

func (g *Graph) EnsureSchema(ctx context.Context) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	stmts := []string{
		// Original constraints
		`CREATE CONSTRAINT res_rid IF NOT EXISTS FOR (r:Resource) REQUIRE r.rid IS UNIQUE`,
		`CREATE CONSTRAINT epi_eid IF NOT EXISTS FOR (e:Episodic) REQUIRE e.eid IS UNIQUE`,
		`CREATE CONSTRAINT tgt_tid IF NOT EXISTS FOR (t:PromTarget) REQUIRE t.tid IS UNIQUE`,
		`CREATE CONSTRAINT rule_rkey IF NOT EXISTS FOR (r:Rule) REQUIRE r.rkey IS UNIQUE`,

		// ENHANCED: Indexes for RCA queries
		`CREATE INDEX res_kind IF NOT EXISTS FOR (r:Resource) ON (r.kind)`,
		`CREATE INDEX res_ns_name IF NOT EXISTS FOR (r:Resource) ON (r.ns, r.name)`,
		`CREATE INDEX epi_severity IF NOT EXISTS FOR (e:Episodic) ON (e.severity)`,
		`CREATE INDEX epi_event_time IF NOT EXISTS FOR (e:Episodic) ON (e.event_time)`,
		`CREATE INDEX epi_reason IF NOT EXISTS FOR (e:Episodic) ON (e.reason)`,

		// ENHANCED: Incident clustering support
		`CREATE INDEX inc_resource IF NOT EXISTS FOR (i:Incident) ON (i.resource_id, i.window_start)`,

		// MULTI-TENANT: Index for client_id filtering
		`CREATE INDEX res_client_id IF NOT EXISTS FOR (r:Resource) ON (r.client_id)`,
		`CREATE INDEX epi_client_id IF NOT EXISTS FOR (e:Episodic) ON (e.client_id)`,
		`CREATE INDEX rule_client_id IF NOT EXISTS FOR (r:Rule) ON (r.client_id)`,
		`CREATE INDEX tgt_client_id IF NOT EXISTS FOR (t:PromTarget) ON (t.client_id)`,
		`CREATE INDEX inc_client_id IF NOT EXISTS FOR (i:Incident) ON (i.client_id)`,
	}
	for _, q := range stmts {
		if _, err := s.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
			_, err := tx.Run(ctx, q, nil)
			return nil, err
		}); err != nil {
			return err
		}
	}
	return nil
}

func lowerKind(k string) string { return strings.ToLower(k) }
func ridFor(kind, uid, ns, name string) string {
	if uid != "" {
		return fmt.Sprintf("%s:%s", lowerKind(kind), uid)
	}
	if ns == "" {
		return fmt.Sprintf("%s::%s", lowerKind(kind), name)
	}
	return fmt.Sprintf("%s:%s:%s", lowerKind(kind), ns, name)
}
func ridFromString(id string) string { return strings.ToLower(id) }

func ifEmpty(s, def string) string {
	if strings.TrimSpace(s) == "" {
		return def
	}
	return s
}

func canonKind(s string) string {
	s = strings.TrimSpace(strings.ToLower(s))
	if s == "" {
		return ""
	}
	r := []rune(s)
	r[0] = unicode.ToUpper(r[0])
	return string(r)
}

func parseRid(rid string) (kind, ns, name, uid string) {
	rid = strings.TrimSpace(strings.ToLower(rid))
	parts := strings.Split(rid, ":")
	switch len(parts) {
	case 2: // kind:uid
		kind = canonKind(parts[0])
		uid = parts[1]
	case 3: // kind:ns:name
		kind = canonKind(parts[0])
		ns = parts[1]
		name = parts[2]
	}
	return
}

func (g *Graph) UpsertResource(ctx context.Context, rec ResourceRecord) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	rid := ridFor(rec.Kind, rec.UID, rec.Namespace, rec.Name) // your original order if needed

	props := map[string]any{
		"rid":         rid,
		"kind":        rec.Kind,
		"uid":         rec.UID,
		"ns":          rec.Namespace,
		"name":        rec.Name,
		"cluster":     rec.Cluster,
		"client_id":   rec.ClientID, // Multi-tenant: store client_id
		"labels_kv":   labelsToKV(rec.Labels),
		"labels_json": toJSON(rec.Labels),
		"status_json": toJSON(rec.Status),
		"spec_json":   toJSON(rec.Spec),
		"node":        rec.Node,
		"podIP":       rec.PodIP,
		"image":       rec.Image,
		"at":          rec.At.UTC().Format(time.RFC3339Nano),
	}

	kindLabel := safeLabelName(ifEmpty(rec.Kind, "Unknown"))

	// Multi-tenant: Include client_id in node properties
	cy := fmt.Sprintf(`
MERGE (r:Resource:%s {rid:$rid, client_id:$client_id})
SET r.kind=$kind, r.uid=$uid, r.ns=$ns, r.name=$name, r.cluster=$cluster,
    r.client_id=$client_id,
    r.labels_kv=$labels_kv, r.labels_json=$labels_json,
    r.status_json=$status_json, r.spec_json=$spec_json,
    r.node=$node, r.podIP=$podIP, r.image=$image,
    r.updated_at = datetime($at)
`, kindLabel)

	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, cy, props)
		return err
	})
}

func (g *Graph) DeleteResourceByKey(ctx context.Context, key, clientID string) error {
	m := ridKeyRe.FindStringSubmatch(key)
	var rid string
	if len(m) == 3 {
		rid = strings.ToLower(m[1]) + ":" + m[2]
	} else {
		rid = strings.ToLower(key)
	}
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		query := `MATCH (r:Resource {rid:$rid})`
		params := map[string]any{"rid": rid}
		if clientID != "" {
			query = `MATCH (r:Resource {rid:$rid, client_id:$client_id})`
			params["client_id"] = clientID
		}
		query += ` DETACH DELETE r`
		_, err := tx.Run(ctx, query, params)
		return err
	})
}

func (g *Graph) UpsertEdge(ctx context.Context, rec EdgeRecord) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)

	fromRid := ridFromString(rec.From)
	toRid := ridFromString(rec.To)
	relType := safeRelTypeName(rec.Type)

	fk, fns, fname, fuid := parseRid(fromRid)
	tk, tns, tname, tuid := parseRid(toRid)

	cy := fmt.Sprintf(`
MERGE (a:Resource {rid:$from, client_id:$client_id})
SET  a.kind = coalesce(a.kind, $fromKind),
     a.ns   = coalesce(a.ns,   $fromNS),
     a.name = coalesce(a.name, $fromName),
     a.uid  = coalesce(a.uid,  $fromUID)
MERGE (b:Resource {rid:$to, client_id:$client_id})
SET  b.kind = coalesce(b.kind, $toKind),
     b.ns   = coalesce(b.ns,   $toNS),
     b.name = coalesce(b.name, $toName),
     b.uid  = coalesce(b.uid,  $toUID)
MERGE (a)-[r:%s {id:$id, client_id:$client_id}]->(b)
SET  r.cluster=$cluster, r.client_id=$client_id, r.updated_at=datetime($at)
`, relType)

	params := map[string]any{
		"from":      fromRid,
		"to":        toRid,
		"id":        rec.ID,
		"client_id": rec.ClientID,
		"cluster":   rec.Cluster,
		"at":        rec.At.UTC().Format(time.RFC3339Nano),
		"fromKind":  fk, "fromNS": fns, "fromName": fname, "fromUID": fuid,
		"toKind": tk, "toNS": tns, "toName": tname, "toUID": tuid,
	}

	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, cy, params)
		return err
	})
}

func (g *Graph) DeleteEdgeByID(ctx context.Context, id, clientID string) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		query := `MATCH ()-[r]->() WHERE r.id=$id`
		params := map[string]any{"id": id}
		if clientID != "" {
			query += ` AND r.client_id=$client_id`
			params["client_id"] = clientID
		}
		query += ` DELETE r`
		_, err := tx.Run(ctx, query, params)
		return err
	})
}

func (g *Graph) UpsertEpisodeAndLink(ctx context.Context, ev EventNormalized) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)

	evTime := ev.EventTime
	if _, err := time.Parse(time.RFC3339Nano, evTime); err != nil {
		if _, err2 := time.Parse(time.RFC3339, evTime); err2 != nil {
			evTime = time.Now().UTC().Format(time.RFC3339Nano)
		}
	}

	subRid := ridFor(ev.Subject.Kind, ev.Subject.UID, ev.Subject.NS, ev.Subject.Name)
	subKind := canonKind(ev.Subject.Kind) // normalize for label

	params := map[string]any{
		"eid":       ev.EventID,
		"client_id": ev.ClientID,
		"etype":     ev.Etype,
		"severity":  strings.ToUpper(ev.Severity),
		"reason":    ev.Reason,
		"message":   ev.Message,
		"eventTime": evTime,
		"subRid":    subRid,
		"subKind":   subKind,
		"subNS":     ev.Subject.NS,
		"subName":   ev.Subject.Name,
		"subUID":    ev.Subject.UID,
	}

	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		// Upsert episodic + subject, coalescing subject props
		_, err := tx.Run(ctx, `
MERGE (e:Episodic {eid:$eid, client_id:$client_id})
SET  e.client_id=$client_id, e.etype=$etype, e.severity=$severity, e.reason=$reason, e.message=$message,
     e.event_time=datetime($eventTime), e.updated_at=datetime($eventTime)
MERGE (s:Resource {rid:$subRid, client_id:$client_id})
  ON CREATE SET s.kind=$subKind, s.ns=$subNS, s.name=$subName, s.uid=$subUID
SET  s.kind = coalesce(s.kind, $subKind),
     s.ns   = coalesce(s.ns,   $subNS),
     s.name = coalesce(s.name, $subName),
     s.uid  = coalesce(s.uid,  $subUID),
     s.updated_at = datetime($eventTime)
MERGE (e)-[rel:ABOUT {client_id:$client_id}]->(s)
ON CREATE SET rel.client_id=$client_id
`, params)
		if err != nil {
			return err
		}

		// Add subtype label once we know the kind (requires APOC)
		if subKind != "" {
			_, _ = tx.Run(ctx, `
MATCH (s:Resource {rid:$rid, client_id:$client_id})
CALL apoc.create.addLabels(s, [$label]) YIELD node
RETURN 0
`, map[string]any{"rid": subRid, "client_id": ev.ClientID, "label": safeLabelName(subKind)})
		}
		return nil
	})
}

func (g *Graph) LinkRCA(ctx context.Context, eid, clientID string, windowMin int) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	params := map[string]any{"eid": eid, "client_id": clientID, "mins": windowMin}
	cy := `
MATCH (e:Episodic {eid:$eid, client_id:$client_id})-[:ABOUT]->(r:Resource {client_id:$client_id})
WITH e, r
MATCH (c:Episodic {client_id:$client_id})-[:ABOUT]->(u:Resource {client_id:$client_id})
WHERE c.event_time <= e.event_time
  AND c.event_time >= e.event_time - duration({minutes:$mins})
  AND u <> r
OPTIONAL MATCH p = shortestPath( (u)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r) )
WITH e, c, p WHERE p IS NOT NULL
MERGE (c)-[pc:POTENTIAL_CAUSE {client_id:$client_id}]->(e)
ON CREATE SET pc.hops = length(p), pc.created_at = datetime()`
	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, cy, params)
		return err
	})
}

/*** Prom targets & rules ***/
func (g *Graph) UpsertPromTarget(ctx context.Context, key string, rec PromTargetRecord) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	tid := key
	if tid == "" {
		job, ns, svc, inst := rec.Labels["job"], rec.Labels["namespace"], rec.Labels["service"], rec.Labels["instance"]
		tid = fmt.Sprintf("%s|%s|%s|%s|%s", rec.Cluster, job, ns, svc, inst)
	}
	props := map[string]any{
		"tid":         tid,
		"client_id":   rec.ClientID,
		"cluster":     rec.Cluster,
		"labels_kv":   labelsToKV(rec.Labels),
		"labels_json": toJSON(rec.Labels),
		"scrape":      rec.ScrapeURL,
		"health":      strings.ToUpper(rec.Health),
		"lastScrape":  rec.LastScrape,
		"lastError":   rec.LastError,
		"at":          rec.At.UTC().Format(time.RFC3339Nano),
	}
	cy := `
MERGE (t:PromTarget {tid:$tid, client_id:$client_id})
SET t.client_id=$client_id, t.cluster=$cluster, t.labels_kv=$labels_kv, t.labels_json=$labels_json,
    t.scrapeUrl=$scrape, t.health=$health,
    t.lastScrape=$lastScrape, t.lastError=$lastError, t.updated_at=datetime($at)`
	if err := writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, cy, props)
		return err
	}); err != nil {
		return err
	}

	// Link to Service and/or Pod if label hints exist
	ns := rec.Labels["namespace"]
	job := rec.Labels["job"]
	svc := rec.Labels["service"]
	pod := rec.Labels["pod"]
	if svc == "" && job != "" {
		svc = job // common fallback
	}

	linkCy := `
MATCH (t:PromTarget {tid:$tid, client_id:$client_id})
WITH t
MATCH (s:Resource {rid:$svcRid, client_id:$client_id})
MERGE (t)-[:SCRAPES]->(s)`

	if ns != "" && svc != "" {
		_ = writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
			_, err := tx.Run(ctx, linkCy, map[string]any{
				"tid":       tid,
				"client_id": rec.ClientID,
				"svcRid":    fmt.Sprintf("service:%s:%s", ns, svc),
			})
			return err
		})
	}
	if ns != "" && pod != "" {
		_ = writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
			_, err := tx.Run(ctx, linkCy, map[string]any{
				"tid":       tid,
				"client_id": rec.ClientID,
				"svcRid":    fmt.Sprintf("pod:%s:%s", ns, pod),
			})
			return err
		})
	}
	return nil
}

func (g *Graph) DeletePromTargetByKey(ctx context.Context, key, clientID string) error {
	if key == "" {
		return nil
	}
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		query := `MATCH (t:PromTarget {tid:$tid})`
		params := map[string]any{"tid": key}
		if clientID != "" {
			query = `MATCH (t:PromTarget {tid:$tid, client_id:$client_id})`
			params["client_id"] = clientID
		}
		query += ` DETACH DELETE t`
		_, err := tx.Run(ctx, query, params)
		return err
	})
}

func (g *Graph) UpsertRule(ctx context.Context, key string, rec RuleRecord) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	rkey := key
	if rkey == "" {
		rkey = rec.Group + "|" + rec.Rule
	}
	params := map[string]any{
		"rkey":        rkey,
		"client_id":   rec.ClientID,
		"name":        rec.Rule,
		"group":       rec.Group,
		"rtype":       strings.ToLower(rec.Type),
		"labels_json": toJSON(rec.Labels),
		"ann_json":    toJSON(rec.Annotations),
		"expr":        rec.Expr,
		"cluster":     rec.Cluster,
		"at":          rec.At.UTC().Format(time.RFC3339Nano),
	}
	cy := `
MERGE (r:Rule {rkey:$rkey, client_id:$client_id})
SET r.client_id=$client_id, r.name=$name, r.group=$group, r.type=$rtype,
    r.labels_json=$labels_json, r.annotations_json=$ann_json, r.expr=$expr,
    r.cluster=$cluster, r.updated_at=datetime($at)`
	if err := writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, cy, params)
		return err
	}); err != nil {
		return err
	}

	// Optional scope linkage: map to Service via labels
	ns := rec.Labels["namespace"]
	job := rec.Labels["job"]
	svc := rec.Labels["service"]
	if svc == "" && job != "" {
		svc = job
	}
	if ns != "" && svc != "" {
		_ = writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
			_, err := tx.Run(ctx, `
MATCH (r:Rule {rkey:$rkey, client_id:$client_id})
MATCH (s:Resource {rid:$rid, client_id:$client_id})
MERGE (r)-[:SCOPES {client_id:$client_id}]->(s)`, map[string]any{
				"rkey":      rkey,
				"client_id": rec.ClientID,
				"rid":       fmt.Sprintf("service:%s:%s", ns, svc),
			})
			return err
		})
	}
	return nil
}

/**************************************
 * ENHANCED: Production RCA Features
 **************************************/

// Severity Escalation: WARNING→ERROR after repeats (Production Gap #5)
func (g *Graph) EscalateSeverity(ctx context.Context, eid, clientID string, windowMin, threshold int) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)

	cy := `
	MATCH (e:Episodic {eid:$eid, client_id:$client_id})-[:ABOUT]->(r:Resource {client_id:$client_id})
	WHERE e.severity IN ['WARNING', 'ERROR']
	MATCH (r)<-[:ABOUT]-(prev:Episodic {client_id:$client_id})
	WHERE prev.reason = e.reason
	  AND prev.event_time >= e.event_time - duration({minutes:$window})
	  AND prev.eid <> e.eid
	WITH e, COUNT(prev) AS repeat_count
	WHERE repeat_count >= $threshold
	SET e.severity = CASE e.severity
	                  WHEN 'WARNING' THEN 'ERROR'
	                  WHEN 'ERROR' THEN 'FATAL'
	                  ELSE e.severity END,
	    e.escalated = true,
	    e.repeat_count = repeat_count
	RETURN e.eid, e.severity, repeat_count`

	params := map[string]any{
		"eid":       eid,
		"client_id": clientID,
		"window":    windowMin,
		"threshold": threshold,
	}

	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, cy, params)
		return err
	})
}

// Incident Clustering: Group related episodic events
func (g *Graph) ClusterIncident(ctx context.Context, eid, clientID string, windowMin int) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)

	// Find related events in time window with shared resources
	cy := `
	MATCH (e:Episodic {eid:$eid, client_id:$client_id})-[:ABOUT]->(r:Resource {client_id:$client_id})
	WITH e, r
	MATCH (r)<-[:ABOUT]-(related:Episodic {client_id:$client_id})
	WHERE related.event_time >= e.event_time - duration({minutes:$window})
	  AND related.event_time <= e.event_time + duration({minutes:$window})
	  AND related.eid <> e.eid
	  AND (related.severity IN ['ERROR', 'FATAL'] OR e.severity IN ['ERROR', 'FATAL'])
	WITH e, collect(DISTINCT related) AS related_events
	WHERE size(related_events) >= 2

	// Create or find incident node
	MERGE (inc:Incident {
		client_id: $client_id,
		resource_id: head([(e)-[:ABOUT]->(r) | r.rid]),
		window_start: datetime(e.event_time) - duration({minutes:$window})
	})
	SET inc.window_end = datetime(e.event_time) + duration({minutes:$window}),
	    inc.event_count = size(related_events) + 1,
	    inc.updated_at = datetime()

	// Link events to incident
	MERGE (e)-[:PART_OF {client_id:$client_id}]->(inc)
	WITH inc, related_events
	UNWIND related_events AS rel
	MERGE (rel)-[:PART_OF {client_id:$client_id}]->(inc)
	RETURN inc.resource_id, inc.event_count`

	params := map[string]any{
		"eid":       eid,
		"client_id": clientID,
		"window":    windowMin,
	}

	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, cy, params)
		return err
	})
}

// Enhanced LinkRCA with confidence scoring (domain heuristics)
func (g *Graph) LinkRCAWithScore(ctx context.Context, eid, clientID string, windowMin int) error {
	startTime := time.Now()
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)

	cy := `
	MATCH (e:Episodic {eid:$eid, client_id:$client_id})-[:ABOUT]->(r:Resource {client_id:$client_id})
	WITH e, r
	MATCH (c:Episodic {client_id:$client_id})-[:ABOUT]->(u:Resource {client_id:$client_id})
	WHERE c.event_time <= e.event_time
	  AND c.event_time >= e.event_time - duration({minutes:$mins})
	  AND u <> r
	OPTIONAL MATCH p = shortestPath( (u)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r) )
	WITH e, c, p, u, r WHERE p IS NOT NULL

	// Calculate confidence score with domain heuristics
	WITH e, c, p,
	     // Base temporal score (closer in time = higher confidence)
	     1.0 - (duration.between(c.event_time, e.event_time).milliseconds / (60000.0 * $mins)) AS temporal_score,
	     // Graph distance (fewer hops = higher confidence)
	     1.0 / (length(p) + 1.0) AS distance_score

	// Domain heuristics for K8s failure patterns
	WITH e, c, p, temporal_score, distance_score,
	     CASE
		// === NEW: Patterns from YOUR actual data ===
			WHEN c.reason = 'KubePodCrashLooping' AND e.reason = 'KubePodNotReady' THEN 0.85
			WHEN c.reason = 'NodeClockNotSynchronising' AND e.reason = 'PrometheusMissingRuleEvaluations' THEN 0.85
			WHEN c.reason = 'KubePodNotReady' AND e.reason = 'KubePodCrashLooping' THEN 0.80
			WHEN c.reason = 'KubePodCrashLooping' AND e.reason = 'KubePodCrashLooping' THEN 0.75
	       // High confidence: OOMKilled → CrashLoop
	       WHEN c.reason CONTAINS 'OOMKilled' AND e.reason CONTAINS 'CrashLoop' THEN 0.95
	       // High confidence: ImagePullBackOff → Pending
	       WHEN c.reason CONTAINS 'ImagePull' AND e.reason CONTAINS 'FailedScheduling' THEN 0.90
	       // High confidence: Node issues → Pod eviction
	       WHEN c.reason CONTAINS 'NodeNotReady' AND e.reason CONTAINS 'Evicted' THEN 0.90
	       // Medium confidence: Network errors → Service unavailable
	       WHEN c.message =~ '(?i).*(connection refused|timeout).*' AND e.severity = 'ERROR' THEN 0.70
	       // Medium confidence: Database errors → API errors
	       WHEN c.message =~ '(?i).*(database|deadlock).*' AND e.message =~ '(?i).*(api|service).*' THEN 0.65
	       // Low confidence: Generic errors
	       WHEN c.severity = 'ERROR' AND e.severity = 'ERROR' THEN 0.50
	       ELSE 0.40
	     END AS domain_score

	// Final confidence = weighted average
	WITH e, c, p, temporal_score, distance_score, domain_score,
	     (temporal_score * 0.3 + distance_score * 0.3 + domain_score * 0.4) AS confidence

	MERGE (c)-[pc:POTENTIAL_CAUSE {client_id:$client_id}]->(e)
	ON CREATE SET pc.hops = length(p),
	              pc.created_at = datetime()
	SET pc.confidence = confidence,
	    pc.temporal_score = temporal_score,
	    pc.distance_score = distance_score,
	    pc.domain_score = domain_score,
	    pc.updated_at = datetime()
	RETURN c.eid, e.eid, confidence, temporal_score, distance_score, domain_score ORDER BY confidence DESC`

	params := map[string]any{
		"eid":       eid,
		"client_id": clientID,
		"mins":      windowMin,
	}

	var linksCreated int
	err := writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		result, err := tx.Run(ctx, cy, params)
		if err != nil {
			return err
		}

		// Track confidence scores for metrics
		for result.Next(ctx) {
			linksCreated++
			record := result.Record()

			if conf, ok := record.Get("confidence"); ok {
				if confVal, ok := conf.(float64); ok {
					rcaConfidenceScoreDistribution.WithLabelValues("final").Observe(confVal)
				}
			}
			if temp, ok := record.Get("temporal_score"); ok {
				if tempVal, ok := temp.(float64); ok {
					rcaConfidenceScoreDistribution.WithLabelValues("temporal").Observe(tempVal)
				}
			}
			if dist, ok := record.Get("distance_score"); ok {
				if distVal, ok := dist.(float64); ok {
					rcaConfidenceScoreDistribution.WithLabelValues("distance").Observe(distVal)
				}
			}
			if dom, ok := record.Get("domain_score"); ok {
				if domVal, ok := dom.(float64); ok {
					rcaConfidenceScoreDistribution.WithLabelValues("domain").Observe(domVal)
				}
			}
		}

		return result.Err()
	})

	// Track metrics
	duration := time.Since(startTime)
	trackNeo4jOperation("link_rca_with_score", duration, err)

	if err == nil && linksCreated > 0 {
		for i := 0; i < linksCreated; i++ {
			trackRCALink()
		}
	}

	return err
}

/***************
 * Consumers
 ***************/
type handler struct {
	graph     *Graph
	rcaWindow int
	clientID  string // Multi-tenant: filter messages by client_id
	// topics
	resTopic, topoTopic, evtTopic string
	logsTopic                     string
	promTgtTopic, promRuleTopic   string
	cmdTopic                      string
}

func (h *handler) Setup(s sarama.ConsumerGroupSession) error   { return nil }
func (h *handler) Cleanup(s sarama.ConsumerGroupSession) error { return nil }

func (h *handler) ConsumeClaim(sess sarama.ConsumerGroupSession, claim sarama.ConsumerGroupClaim) error {
	for msg := range claim.Messages() {
		if err := h.dispatch(msg); err != nil {
			if isConstraintErr(err) {
				continue
			}
			log.Printf("consume %s p%d@%d err: %v", msg.Topic, msg.Partition, msg.Offset, err)
		}
		sess.MarkMessage(msg, "")
	}
	return nil
}

func (h *handler) dispatch(msg *sarama.ConsumerMessage) error {
	switch msg.Topic {
	case h.resTopic:
		return h.handleResource(msg)
	case h.topoTopic:
		return h.handleTopo(msg)
	case h.evtTopic:
		return h.handleEvent(msg)
	case h.logsTopic:
		return h.handleLog(msg) // NEW
	case h.promTgtTopic:
		return h.handlePromTarget(msg)
	case h.promRuleTopic:
		return h.handleRule(msg)
	case h.cmdTopic:
		return h.handleCommand(msg)
	default:
		return nil
	}
}

func (h *handler) handleResource(msg *sarama.ConsumerMessage) error {
	tenantFromKey, rawKey := splitTenantKey(string(msg.Key))
	if msg.Value == nil || len(msg.Value) == 0 {
		if h.clientID != "" {
			if tenantFromKey == "" {
				return nil
			}
			if tenantFromKey != h.clientID {
				return nil
			}
		}
		return h.graph.DeleteResourceByKey(context.Background(), rawKey, tenantFromKey)
	}
	var rec ResourceRecord
	if err := json.Unmarshal(msg.Value, &rec); err != nil {
		return err
	}

	// Multi-tenant: filter by client_id if configured
	if rec.ClientID == "" && tenantFromKey != "" {
		rec.ClientID = tenantFromKey
	}
	if h.clientID != "" {
		switch {
		case rec.ClientID == "":
			if tenantFromKey == "" || tenantFromKey != h.clientID {
				return nil
			}
			rec.ClientID = tenantFromKey
		case rec.ClientID != h.clientID:
			return nil // Skip messages from other clients
		}
	}

	if strings.EqualFold(rec.Op, "DELETE") {
		return h.graph.DeleteResourceByKey(context.Background(), rawKey, rec.ClientID)
	}
	return h.graph.UpsertResource(context.Background(), rec)
}

func (h *handler) handleTopo(msg *sarama.ConsumerMessage) error {
	tenantFromKey, rawID := splitTenantKey(string(msg.Key))
	if msg.Value == nil || len(msg.Value) == 0 {
		if h.clientID != "" {
			if tenantFromKey == "" || tenantFromKey != h.clientID {
				return nil
			}
		}
		return h.graph.DeleteEdgeByID(context.Background(), rawID, tenantFromKey)
	}
	var rec EdgeRecord
	if err := json.Unmarshal(msg.Value, &rec); err != nil {
		return err
	}
	if rec.ID == "" {
		rec.ID = rawID
	}
	if rec.ClientID == "" && tenantFromKey != "" {
		rec.ClientID = tenantFromKey
	}
	if h.clientID != "" {
		switch {
		case rec.ClientID == "" && tenantFromKey != "":
			rec.ClientID = tenantFromKey
		case rec.ClientID == "":
			return nil
		case rec.ClientID != h.clientID:
			return nil
		}
	}
	if strings.EqualFold(rec.Op, "DELETE") {
		return h.graph.DeleteEdgeByID(context.Background(), rec.ID, rec.ClientID)
	}
	return h.graph.UpsertEdge(context.Background(), rec)
}

// ENHANCED: Event handling with RCA, severity escalation, and incident clustering
func (h *handler) handleEvent(msg *sarama.ConsumerMessage) error {
    startTime := time.Now()

    if msg.Value == nil || len(msg.Value) == 0 {
        return nil
    }
    tenantFromKey, rawKey := splitTenantKey(string(msg.Key))
    var ev EventNormalized
    if err := json.Unmarshal(msg.Value, &ev); err != nil {
        return err
    }

    // Backward/forward compatibility: if incoming message is not in normalized schema
    // (missing etype/subject), try to map from kubernetes-event-exporter payload.
    if strings.TrimSpace(ev.Etype) == "" || (ev.Subject == (EventSubject{})) {
        // Lightweight shape for exporter payload
        var raw struct {
            ClientID       string                 `json:"client_id"`
            Metadata       map[string]any         `json:"metadata"`
            Reason         string                 `json:"reason"`
            Message        string                 `json:"message"`
            Type           string                 `json:"type"`
            EventTime      any                    `json:"eventTime"`
            FirstTimestamp string                 `json:"firstTimestamp"`
            LastTimestamp  string                 `json:"lastTimestamp"`
            InvolvedObject struct {
                Kind      string `json:"kind"`
                UID       string `json:"uid"`
                Namespace string `json:"namespace"`
                Name      string `json:"name"`
            } `json:"involvedObject"`
        }
        if err := json.Unmarshal(msg.Value, &raw); err == nil {
            // Fill client_id from payload or Kafka key
            if ev.ClientID == "" {
                ev.ClientID = raw.ClientID
            }
            if ev.ClientID == "" && tenantFromKey != "" {
                ev.ClientID = tenantFromKey
            }

            // Normalize event_time
            et := ""
            switch t := raw.EventTime.(type) {
            case string:
                et = t
            case nil:
                et = ""
            default:
                // Fallback to RFC3339 if possible
                et = fmt.Sprint(t)
            }
            if et == "" {
                if raw.LastTimestamp != "" {
                    et = raw.LastTimestamp
                } else if raw.FirstTimestamp != "" {
                    et = raw.FirstTimestamp
                } else {
                    et = time.Now().UTC().Format(time.RFC3339Nano)
                }
            }
            ev.EventTime = et

            // Event type
            ev.Etype = "k8s.event"

            // Severity: map from Type (Normal/Warning) to INFO/WARNING, else uppercased
            tp := strings.ToUpper(strings.TrimSpace(raw.Type))
            switch tp {
            case "NORMAL":
                ev.Severity = "INFO"
            case "WARNING":
                ev.Severity = "WARNING"
            case "ERROR", "FATAL", "CRITICAL":
                ev.Severity = tp
            default:
                if tp == "" {
                    ev.Severity = "INFO"
                } else {
                    ev.Severity = tp
                }
            }

            // Reason/message
            ev.Reason = ifEmpty(strings.TrimSpace(raw.Reason), "Unknown")
            ev.Message = raw.Message

            // Subject
            ev.Subject = EventSubject{
                Kind: ifEmpty(raw.InvolvedObject.Kind, "Unknown"),
                UID:  raw.InvolvedObject.UID,
                NS:   raw.InvolvedObject.Namespace,
                Name: raw.InvolvedObject.Name,
            }

            // EventID: prefer Metadata.uid or Kafka key, fallback to hash of time+reason+subject
            if ev.EventID == "" {
                if rawUID, _ := raw.Metadata["uid"].(string); rawUID != "" {
                    ev.EventID = rawUID
                } else if rawKey != "" {
                    ev.EventID = rawKey
                } else {
                    h := sha1.New()
                    ioStr := fmt.Sprintf("%s|%s|%s/%s|%s", ev.EventTime, ev.Etype, ev.Subject.NS, ev.Subject.Name, ev.Reason)
                    _, _ = h.Write([]byte(ioStr))
                    ev.EventID = hex.EncodeToString(h.Sum(nil))
                }
            }
        }
    }

	// Multi-tenant: filter by client_id if configured
	if ev.ClientID == "" && tenantFromKey != "" {
		ev.ClientID = tenantFromKey
	}
	if h.clientID != "" {
		switch {
		case ev.ClientID == "":
			if tenantFromKey == "" || tenantFromKey != h.clientID {
				return nil
			}
			ev.ClientID = tenantFromKey
		case ev.ClientID != h.clientID:
			return nil // Skip messages from other clients
		}
	}

	if ev.EventID == "" {
		if rawKey != "" {
			ev.EventID = rawKey
		} else {
			ev.EventID = string(msg.Key)
		}
	}
	if err := h.graph.UpsertEpisodeAndLink(context.Background(), ev); err != nil {
		return err
	}
	if ev.Reason != "" {
		_ = h.linkRuleToEpisode(context.Background(), ev.Reason, ev.EventID, ev.ClientID)
	}

	// ENHANCED: Use LinkRCAWithScore for confidence-based causal links
	rcaStart := time.Now()
	clientID := ev.ClientID
	if err := h.graph.LinkRCAWithScore(context.Background(), ev.EventID, clientID, h.rcaWindow); err != nil {
		log.Printf("LinkRCAWithScore failed for %s: %v", ev.EventID, err)
		// Fallback to simple LinkRCA if enhanced version fails
		if fallbackErr := h.graph.LinkRCA(context.Background(), ev.EventID, clientID, h.rcaWindow); fallbackErr == nil {
			// Track that we used fallback (NULL confidence)
			rcaNullConfidenceLinks.Inc()
		}
	}
	rcaDuration := time.Since(rcaStart)
	trackSLACompliance("rca_compute", rcaDuration, defaultSLAThresholds)

	// ENHANCED: Check for severity escalation (WARNING→ERROR on repeats)
	sevEscalationEnabled := getenv("SEVERITY_ESCALATION_ENABLED", "true") == "true"
	if sevEscalationEnabled && (strings.ToUpper(ev.Severity) == "WARNING" || strings.ToUpper(ev.Severity) == "ERROR") {
		windowMin := 5
		threshold := 3
		if v := getenv("SEVERITY_ESCALATION_WINDOW_MIN", ""); v != "" {
			fmt.Sscanf(v, "%d", &windowMin)
		}
		if v := getenv("SEVERITY_ESCALATION_THRESHOLD", ""); v != "" {
			fmt.Sscanf(v, "%d", &threshold)
		}
		_ = h.graph.EscalateSeverity(context.Background(), ev.EventID, clientID, windowMin, threshold)
	}

	// ENHANCED: Cluster related incidents (for ERROR/FATAL events)
	incidentClusteringEnabled := getenv("INCIDENT_CLUSTERING_ENABLED", "true") == "true"
	if incidentClusteringEnabled && (strings.ToUpper(ev.Severity) == "ERROR" || strings.ToUpper(ev.Severity) == "FATAL") {
		_ = h.graph.ClusterIncident(context.Background(), ev.EventID, clientID, h.rcaWindow)
	}

	// Track end-to-end latency and SLA compliance
	totalDuration := time.Since(startTime)
	trackEndToEndLatency(h.evtTopic, totalDuration)
	trackSLACompliance("message_processing", totalDuration, defaultSLAThresholds)

	return nil
}

// NEW: logs.normalized → filtered Episodic events
func (h *handler) handleLog(msg *sarama.ConsumerMessage) error {
	if msg.Value == nil || len(msg.Value) == 0 {
		return nil
	}
	var lr LogNormalized
	if err := json.Unmarshal(msg.Value, &lr); err != nil {
		return err
	}

	// Multi-tenant: filter by client_id if configured
	if h.clientID != "" && lr.ClientID != "" && lr.ClientID != h.clientID {
		return nil // Skip messages from other clients
	}

	// filter: only high-signal to avoid graph bloat
	if !isHighSignalLog(lr.Severity, lr.Message) {
		return nil
	}

	// fill subject uid if missing (from record)
	if lr.Subject.UID == "" {
		if lr.PodUID != "" {
			lr.Subject.UID = lr.PodUID
		} else if lr.Kubernetes.PodUID != "" {
			lr.Subject.UID = lr.Kubernetes.PodUID
		}
	}
	// ensure subject fields for rid synthesis
	if lr.Subject.Kind == "" {
		lr.Subject.Kind = "Pod"
	}
	if lr.Subject.NS == "" {
		if lr.PodNS != "" {
			lr.Subject.NS = lr.PodNS
		}
	}
	if lr.Subject.Name == "" {
		if lr.Pod != "" {
			lr.Subject.Name = lr.Pod
		}
	}

	// reason mapping (stable-ish buckets)
	reason := classifyLogReason(lr.Severity, lr.Message)

	// ensure event id
	eid := lr.EventID
	if eid == "" {
		// deterministic hash: key|time|reason|first 64 chars of message
		hsum := sha1.Sum([]byte(fmt.Sprintf("%s|%s|%s|%s", string(msg.Key), lr.EventTime, reason, truncate(lr.Message, 64))))
		eid = hex.EncodeToString(hsum[:])
	}

	ev := EventNormalized{
		EventID:   eid,
		EventTime: coalesceTime(lr.EventTime),
		Etype:     "k8s.log",
		Severity:  strings.ToUpper(lr.Severity),
		Reason:    reason,
		Message:   lr.Message,
		Subject:   lr.Subject,
		ClientID:  lr.ClientID,
	}

	if err := h.graph.UpsertEpisodeAndLink(context.Background(), ev); err != nil {
		return err
	}

	// ENHANCED: Use LinkRCAWithScore for confidence-based causal links
	clientID := ev.ClientID
	if err := h.graph.LinkRCAWithScore(context.Background(), ev.EventID, clientID, h.rcaWindow); err != nil {
		// Fallback to simple LinkRCA if enhanced version fails
		if fallbackErr := h.graph.LinkRCA(context.Background(), ev.EventID, clientID, h.rcaWindow); fallbackErr == nil {
			// Track that we used fallback (NULL confidence)
			rcaNullConfidenceLinks.Inc()
		}
	}

	// ENHANCED: Severity escalation and incident clustering (same as handleEvent)
	sevEscalationEnabled := getenv("SEVERITY_ESCALATION_ENABLED", "true") == "true"
	if sevEscalationEnabled && (strings.ToUpper(ev.Severity) == "WARNING" || strings.ToUpper(ev.Severity) == "ERROR") {
		windowMin := 5
		threshold := 3
		if v := getenv("SEVERITY_ESCALATION_WINDOW_MIN", ""); v != "" {
			fmt.Sscanf(v, "%d", &windowMin)
		}
		if v := getenv("SEVERITY_ESCALATION_THRESHOLD", ""); v != "" {
			fmt.Sscanf(v, "%d", &threshold)
		}
		_ = h.graph.EscalateSeverity(context.Background(), ev.EventID, clientID, windowMin, threshold)
	}

	incidentClusteringEnabled := getenv("INCIDENT_CLUSTERING_ENABLED", "true") == "true"
	if incidentClusteringEnabled && (strings.ToUpper(ev.Severity) == "ERROR" || strings.ToUpper(ev.Severity) == "FATAL") {
		_ = h.graph.ClusterIncident(context.Background(), ev.EventID, clientID, h.rcaWindow)
	}

	return nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}
func coalesceTime(ts string) string {
	if ts == "" {
		return time.Now().UTC().Format(time.RFC3339Nano)
	}
	// accept RFC3339 or RFC3339Nano strings
	if _, err := time.Parse(time.RFC3339Nano, ts); err == nil {
		return ts
	}
	if _, err := time.Parse(time.RFC3339, ts); err == nil {
		return ts
	}
	return time.Now().UTC().Format(time.RFC3339Nano)
}

// ENHANCED: 40+ error patterns for production accuracy (Production Gap #3)
func isHighSignalLog(sev, msg string) bool {
	sev = strings.ToUpper(sev)
	m := strings.ToLower(msg)

	// Always include ERROR and FATAL severity
	if sev == "ERROR" || sev == "FATAL" {
		return true
	}

	// Category 1: Pod/Container failures (K8s specific)
	if strings.Contains(m, "crashloopbackoff") ||
		strings.Contains(m, "back-off restarting failed container") ||
		strings.Contains(m, "oom killed") || strings.Contains(m, "oomkilled") ||
		strings.Contains(m, "exit code") || strings.Contains(m, "exited with code") ||
		strings.Contains(m, "container died") || strings.Contains(m, "pod evicted") {
		return true
	}

	// Category 2: Image/Registry issues
	if strings.Contains(m, "imagepullbackoff") || strings.Contains(m, "errimagepull") ||
		strings.Contains(m, "failed to pull image") || strings.Contains(m, "image not found") ||
		strings.Contains(m, "manifest unknown") || strings.Contains(m, "unauthorized") && strings.Contains(m, "registry") {
		return true
	}

	// Category 3: Health check failures
	if strings.Contains(m, "readiness probe failed") || strings.Contains(m, "liveness probe failed") ||
		strings.Contains(m, "startup probe failed") || strings.Contains(m, "probe timeout") ||
		strings.Contains(m, "health check failed") {
		return true
	}

	// Category 4: Network/Connectivity errors
	if strings.Contains(m, "connection refused") || strings.Contains(m, "connection reset") ||
		strings.Contains(m, "connection timeout") || strings.Contains(m, "i/o timeout") ||
		strings.Contains(m, "dial tcp") && strings.Contains(m, "timeout") ||
		strings.Contains(m, "no route to host") || strings.Contains(m, "network unreachable") ||
		strings.Contains(m, "dns lookup failed") || strings.Contains(m, "could not resolve") ||
		strings.Contains(m, "unable to connect") || strings.Contains(m, "deadline exceeded") {
		return true
	}

	// Category 5: Resource exhaustion
	if strings.Contains(m, "out of memory") || strings.Contains(m, "disk full") ||
		strings.Contains(m, "no space left") || strings.Contains(m, "too many open files") ||
		strings.Contains(m, "resource exhausted") || strings.Contains(m, "quota exceeded") ||
		strings.Contains(m, "cpu throttling") || strings.Contains(m, "eviction threshold") {
		return true
	}

	// Category 6: Application panics/crashes
	if strings.Contains(m, "panic:") || strings.Contains(m, "fatal error") ||
		strings.Contains(m, "segfault") || strings.Contains(m, "segmentation fault") ||
		strings.Contains(m, "core dumped") || strings.Contains(m, "stack overflow") ||
		strings.Contains(m, "null pointer") || strings.Contains(m, "assertion failed") {
		return true
	}

	// Category 7: Database errors
	if strings.Contains(m, "database") && (strings.Contains(m, "connection failed") || strings.Contains(m, "connection lost") ||
		strings.Contains(m, "query timeout") || strings.Contains(m, "deadlock") ||
		strings.Contains(m, "duplicate key") || strings.Contains(m, "constraint violation") ||
		strings.Contains(m, "too many connections") || strings.Contains(m, "connection pool")) {
		return true
	}

	// Category 8: Security/Certificate errors
	if strings.Contains(m, "certificate") && (strings.Contains(m, "expired") || strings.Contains(m, "invalid") ||
		strings.Contains(m, "verify failed") || strings.Contains(m, "untrusted")) ||
		strings.Contains(m, "tls handshake") && strings.Contains(m, "failed") ||
		strings.Contains(m, "authentication failed") || strings.Contains(m, "permission denied") {
		return true
	}

	// Category 9: Storage/Volume errors
	if strings.Contains(m, "failed to mount") || strings.Contains(m, "volume") && strings.Contains(m, "failed") ||
		strings.Contains(m, "persistentvolume") && strings.Contains(m, "error") ||
		strings.Contains(m, "failed to attach") || strings.Contains(m, "io error") {
		return true
	}

	// Category 10: API/HTTP errors (5xx)
	if strings.Contains(m, "500") || strings.Contains(m, "502") || strings.Contains(m, "503") || strings.Contains(m, "504") ||
		strings.Contains(m, "internal server error") || strings.Contains(m, "bad gateway") ||
		strings.Contains(m, "service unavailable") || strings.Contains(m, "gateway timeout") {
		return true
	}

	return false
}

func classifyLogReason(sev, msg string) string {
	sevU := strings.ToUpper(sev)
	m := strings.ToLower(msg)
	switch {
	case strings.Contains(m, "crashloopbackoff"):
		return "LOG_CRASHLOOP"
	case strings.Contains(m, "readiness probe failed"):
		return "LOG_READINESS_FAIL"
	case strings.Contains(m, "liveness probe failed"):
		return "LOG_LIVENESS_FAIL"
	case strings.Contains(m, "imagepullbackoff") || strings.Contains(m, "errimagepull"):
		return "LOG_IMAGE_PULL_FAIL"
	case strings.Contains(m, "oom killed") || strings.Contains(m, "oomkilled"):
		return "LOG_OOM_KILLED"
	case strings.Contains(m, "panic:"):
		return "LOG_PANIC"
	}
	switch sevU {
	case "FATAL":
		return "LOG_FATAL"
	case "ERROR":
		return "LOG_ERROR"
	case "WARNING", "WARN":
		return "LOG_WARNING"
	default:
		return "LOG_INFO"
	}
}

/*** Rule linkage ***/
func (h *handler) linkRuleToEpisode(ctx context.Context, ruleName, eid, clientID string) error {
	s := h.graph.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	_, err := s.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
		_, err := tx.Run(ctx, `
MATCH (e:Episodic {eid:$eid, client_id:$client_id})
MATCH (r:Rule {name:$name, client_id:$client_id})
MERGE (r)-[:EMITS {client_id:$client_id}]->(e)`, map[string]any{"eid": eid, "name": ruleName, "client_id": clientID})
		return nil, err
	})
	return err
}

func (h *handler) handlePromTarget(msg *sarama.ConsumerMessage) error {
	tenantFromKey, rawKey := splitTenantKey(string(msg.Key))
	if msg.Value == nil || len(msg.Value) == 0 {
		if h.clientID != "" {
			if tenantFromKey == "" || tenantFromKey != h.clientID {
				return nil
			}
		}
		return h.graph.DeletePromTargetByKey(context.Background(), rawKey, tenantFromKey)
	}
	var rec PromTargetRecord
	if err := json.Unmarshal(msg.Value, &rec); err != nil {
		return err
	}

	// Multi-tenant: filter by client_id if configured
	if rec.ClientID == "" && tenantFromKey != "" {
		rec.ClientID = tenantFromKey
	}
	if h.clientID != "" {
		switch {
		case rec.ClientID == "":
			if tenantFromKey == "" || tenantFromKey != h.clientID {
				return nil
			}
			rec.ClientID = tenantFromKey
		case rec.ClientID != h.clientID:
			return nil
		}
	}

	if strings.EqualFold(rec.Op, "DELETE") {
		return h.graph.DeletePromTargetByKey(context.Background(), rawKey, rec.ClientID)
	}
	return h.graph.UpsertPromTarget(context.Background(), rawKey, rec)
}

func (h *handler) handleRule(msg *sarama.ConsumerMessage) error {
	tenantFromKey, rawKey := splitTenantKey(string(msg.Key))
	if msg.Value == nil || len(msg.Value) == 0 {
		return nil // soft-delete optional
	}
	var rec RuleRecord
	if err := json.Unmarshal(msg.Value, &rec); err != nil {
		return err
	}

	// Multi-tenant: filter by client_id if configured
	if rec.ClientID == "" && tenantFromKey != "" {
		rec.ClientID = tenantFromKey
	}
	if h.clientID != "" {
		switch {
		case rec.ClientID == "":
			if tenantFromKey == "" || tenantFromKey != h.clientID {
				return nil
			}
			rec.ClientID = tenantFromKey
		case rec.ClientID != h.clientID:
			return nil
		}
	}

	if strings.EqualFold(rec.Op, "DELETE") {
		return nil
	}
	return h.graph.UpsertRule(context.Background(), rawKey, rec)
}

func (h *handler) handleCommand(msg *sarama.ConsumerMessage) error {
	if msg.Value == nil || len(msg.Value) == 0 {
		return nil
	}
	var m struct {
		Op string `json:"op"`
	}
	if err := json.Unmarshal(msg.Value, &m); err != nil {
		return err
	}
	switch strings.ToUpper(m.Op) {
	case "ENSURE_SCHEMA":
		return h.graph.EnsureSchema(context.Background())
	default:
		return nil
	}
}

/***************
 * main
 ***************/
func main() {
	log.SetFlags(0)

	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "healthcheck":
			if err := runHealthcheck(); err != nil {
				fmt.Printf("not ok: %v\n", err)
				os.Exit(1)
			}
			fmt.Println("ok")
			return
		}
	}

	brokers := strings.Split(getenv("KAFKA_BROKERS", "localhost:9092"), ",")

	// Multi-tenant: Support client-specific consumer groups
	clientID := getenv("CLIENT_ID", "")
	group := getenv("KAFKA_GROUP", "kg-builder")
	if clientID != "" {
		group = fmt.Sprintf("%s-%s", group, clientID)
		log.Printf("multi-tenant mode enabled: client_id=%s, consumer_group=%s", clientID, group)
	}

	neo4jURI := getenv("NEO4J_URI", "neo4j://localhost:7687")
	neo4jUser := getenv("NEO4J_USER", "neo4j")
	neo4jPass := getenv("NEO4J_PASS", "password")

	rcaWin := 15
	if v := getenv("RCA_WINDOW_MIN", ""); v != "" {
		var i int
		if _, err := fmt.Sscan(v, &i); err == nil && i > 0 {
			rcaWin = i
		}
	}

	g, err := NewGraph(neo4jURI, neo4jUser, neo4jPass)
	if err != nil {
		log.Fatalf("neo4j: %v", err)
	}
	defer g.Close(context.Background())
	if err := g.EnsureSchema(context.Background()); err != nil {
		log.Fatalf("ensure schema: %v", err)
	}
	log.Printf("schema ready")

	cfg := sarama.NewConfig()
	cfg.Version = sarama.V3_6_0_0
	cfg.Consumer.Group.Rebalance.Strategy = sarama.BalanceStrategyRange
	cfg.Consumer.Offsets.Initial = sarama.OffsetNewest // set to Oldest for full backfill on first run
	cfg.Consumer.Return.Errors = true
	// Multi-tenant: Use client-specific Kafka client ID
	kafkaClientID := "kg-builder"
	if clientID != "" {
		kafkaClientID = fmt.Sprintf("kg-builder-%s", clientID)
	}
	cfg.ClientID = kafkaClientID

	cg, err := sarama.NewConsumerGroup(brokers, group, cfg)
	if err != nil {
		log.Fatalf("kafka: %v", err)
	}
	defer cg.Close()

	h := &handler{
		graph:         g,
		rcaWindow:     rcaWin,
		clientID:      clientID, // Multi-tenant: filter messages by client_id
		resTopic:      topicRes,
		topoTopic:     topicTopo,
		evtTopic:      topicEvt,
		logsTopic:     topicLogs, // NEW
		promTgtTopic:  topicPromTgts,
		promRuleTopic: topicPromRules,
		cmdTopic:      topicCommands,
	}

	var topics []string
	for _, t := range []string{h.resTopic, h.topoTopic, h.evtTopic, h.logsTopic, h.promTgtTopic, h.promRuleTopic, h.cmdTopic} {
		if t != "" {
			topics = append(topics, t)
		}
	}
	log.Printf("consuming topics: %v", topics)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		for err := range cg.Errors() {
			log.Printf("kafka error: %v", err)
		}
	}()

	// Start metrics server
	metricsAddr := getenv("METRICS_PORT", "9090")
	if metricsAddr != "" {
		if !strings.Contains(metricsAddr, ":") {
			metricsAddr = ":" + metricsAddr
		}
		go func() {
			log.Printf("starting metrics server on %s", metricsAddr)
			if err := StartMetricsServer(metricsAddr); err != nil {
				log.Printf("metrics server error: %v", err)
			}
		}()
	}

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	go func() { <-sig; cancel() }()

	for ctx.Err() == nil {
		if err := cg.Consume(ctx, topics, h); err != nil {
			log.Printf("consume error: %v", err)
			time.Sleep(2 * time.Second)
		}
	}
	log.Printf("shutdown")
}

func runHealthcheck() error {
	required := []string{
		"KAFKA_BROKERS",
		"NEO4J_URI",
		"NEO4J_USER",
		"NEO4J_PASS",
	}

	for _, key := range required {
		if strings.TrimSpace(os.Getenv(key)) == "" {
			return fmt.Errorf("%s not set", key)
		}
	}

	return nil
}
