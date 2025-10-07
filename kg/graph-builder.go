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
	Op      string    `json:"op"`
	At      time.Time `json:"at"`
	Cluster string    `json:"cluster"`
	ID      string    `json:"id"`
	From    string    `json:"from"`
	To      string    `json:"to"`
	Type    string    `json:"type"` // SELECTS | RUNS_ON | CONTROLS | ...
}

// events.normalized
type EventNormalized struct {
	EventID   string       `json:"event_id"`
	EventTime string       `json:"event_time"`
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
	Etype     string       `json:"etype"`   // "k8s.log"
	Severity  string       `json:"severity"`// INFO/WARNING/ERROR/FATAL
	Message   string       `json:"message"` // normalized text
	Subject   EventSubject `json:"subject"` // kind=Pod, ns/name (uid often empty)
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
		`CREATE CONSTRAINT res_rid IF NOT EXISTS FOR (r:Resource) REQUIRE r.rid IS UNIQUE`,
		`CREATE CONSTRAINT epi_eid IF NOT EXISTS FOR (e:Episodic) REQUIRE e.eid IS UNIQUE`,
		`CREATE CONSTRAINT tgt_tid IF NOT EXISTS FOR (t:PromTarget) REQUIRE t.tid IS UNIQUE`,
		`CREATE CONSTRAINT rule_rkey IF NOT EXISTS FOR (r:Rule) REQUIRE r.rkey IS UNIQUE`,
		`CREATE INDEX res_kind IF NOT EXISTS FOR (r:Resource) ON (r.kind)`,
		`CREATE INDEX res_ns_name IF NOT EXISTS FOR (r:Resource) ON (r.ns, r.name)`,
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
	if strings.TrimSpace(s) == "" { return def }
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

    // 👇 keep only this one
    cy := fmt.Sprintf(`
MERGE (r:Resource:%s {rid:$rid})
SET r.kind=$kind, r.uid=$uid, r.ns=$ns, r.name=$name, r.cluster=$cluster,
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


func (g *Graph) DeleteResourceByKey(ctx context.Context, key string) error {
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
		_, err := tx.Run(ctx, `MATCH (r:Resource {rid:$rid}) DETACH DELETE r`, map[string]any{"rid": rid})
		return err
	})
}

func (g *Graph) UpsertEdge(ctx context.Context, rec EdgeRecord) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)

	fromRid := ridFromString(rec.From)
	toRid   := ridFromString(rec.To)
	relType := safeRelTypeName(rec.Type)

	fk, fns, fname, fuid := parseRid(fromRid)
	tk, tns, tname, tuid := parseRid(toRid)

	cy := fmt.Sprintf(`
MERGE (a:Resource {rid:$from})
SET  a.kind = coalesce(a.kind, $fromKind),
     a.ns   = coalesce(a.ns,   $fromNS),
     a.name = coalesce(a.name, $fromName),
     a.uid  = coalesce(a.uid,  $fromUID)
MERGE (b:Resource {rid:$to})
SET  b.kind = coalesce(b.kind, $toKind),
     b.ns   = coalesce(b.ns,   $toNS),
     b.name = coalesce(b.name, $toName),
     b.uid  = coalesce(b.uid,  $toUID)
MERGE (a)-[r:%s {id:$id}]->(b)
SET  r.cluster=$cluster, r.updated_at=datetime($at)
`, relType)

	params := map[string]any{
		"from":     fromRid,
		"to":       toRid,
		"id":       rec.ID,
		"cluster":  rec.Cluster,
		"at":       rec.At.UTC().Format(time.RFC3339Nano),
		"fromKind": fk, "fromNS": fns, "fromName": fname, "fromUID": fuid,
		"toKind":   tk, "toNS":   tns, "toName":   tname, "toUID":   tuid,
	}

	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, cy, params)
		return err
	})
}


func (g *Graph) DeleteEdgeByID(ctx context.Context, id string) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, `MATCH ()-[r]->() WHERE r.id=$id DELETE r`, map[string]any{"id": id})
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
MERGE (e:Episodic {eid:$eid})
SET  e.etype=$etype, e.severity=$severity, e.reason=$reason, e.message=$message,
     e.event_time=datetime($eventTime), e.updated_at=datetime($eventTime)
MERGE (s:Resource {rid:$subRid})
  ON CREATE SET s.kind=$subKind, s.ns=$subNS, s.name=$subName, s.uid=$subUID
SET  s.kind = coalesce(s.kind, $subKind),
     s.ns   = coalesce(s.ns,   $subNS),
     s.name = coalesce(s.name, $subName),
     s.uid  = coalesce(s.uid,  $subUID),
     s.updated_at = datetime($eventTime)
MERGE (e)-[:ABOUT]->(s)
`, params)
		if err != nil {
			return err
		}

		// Add subtype label once we know the kind (requires APOC)
		if subKind != "" {
			_, _ = tx.Run(ctx, `
MATCH (s:Resource {rid:$rid})
CALL apoc.create.addLabels(s, [$label]) YIELD node
RETURN 0
`, map[string]any{"rid": subRid, "label": safeLabelName(subKind)})
		}
		return nil
	})
}


func (g *Graph) LinkRCA(ctx context.Context, eid string, windowMin int) error {
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	params := map[string]any{"eid": eid, "mins": windowMin}
	cy := `
MATCH (e:Episodic {eid:$eid})-[:ABOUT]->(r:Resource)
WITH e, r
MATCH (c:Episodic)-[:ABOUT]->(u:Resource)
WHERE c.event_time <= e.event_time
  AND c.event_time >= e.event_time - duration({minutes:$mins})
  AND u <> r
OPTIONAL MATCH p = shortestPath( (u)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r) )
WITH e, c, p WHERE p IS NOT NULL
MERGE (c)-[pc:POTENTIAL_CAUSE]->(e)
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
MERGE (t:PromTarget {tid:$tid})
SET t.cluster=$cluster, t.labels_kv=$labels_kv, t.labels_json=$labels_json,
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
MATCH (t:PromTarget {tid:$tid})
WITH t
MATCH (s:Resource {rid:$svcRid})
MERGE (t)-[:SCRAPES]->(s)`

	if ns != "" && svc != "" {
		_ = writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
			_, err := tx.Run(ctx, linkCy, map[string]any{
				"tid":    tid,
				"svcRid": fmt.Sprintf("service:%s:%s", ns, svc),
			})
			return err
		})
	}
	if ns != "" && pod != "" {
		_ = writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
			_, err := tx.Run(ctx, linkCy, map[string]any{
				"tid":    tid,
				"svcRid": fmt.Sprintf("pod:%s:%s", ns, pod),
			})
			return err
		})
	}
	return nil
}

func (g *Graph) DeletePromTargetByKey(ctx context.Context, key string) error {
	if key == "" {
		return nil
	}
	s := g.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	return writeWithRetry(ctx, s, func(tx neo4j.ManagedTransaction) error {
		_, err := tx.Run(ctx, `MATCH (t:PromTarget {tid:$tid}) DETACH DELETE t`, map[string]any{"tid": key})
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
MERGE (r:Rule {rkey:$rkey})
SET r.name=$name, r.group=$group, r.type=$rtype,
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
MATCH (r:Rule {rkey:$rkey})
MATCH (s:Resource {rid:$rid})
MERGE (r)-[:SCOPES]->(s)`, map[string]any{"rkey": rkey, "rid": fmt.Sprintf("service:%s:%s", ns, svc)})
			return err
		})
	}
	return nil
}

/***************
 * Consumers
 ***************/
type handler struct {
	graph     *Graph
	rcaWindow int
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
  if isConstraintErr(err) { continue }
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
	if msg.Value == nil || len(msg.Value) == 0 {
		return h.graph.DeleteResourceByKey(context.Background(), string(msg.Key))
	}
	var rec ResourceRecord
	if err := json.Unmarshal(msg.Value, &rec); err != nil {
		return err
	}
	if strings.EqualFold(rec.Op, "DELETE") {
		return h.graph.DeleteResourceByKey(context.Background(), string(msg.Key))
	}
	return h.graph.UpsertResource(context.Background(), rec)
}

func (h *handler) handleTopo(msg *sarama.ConsumerMessage) error {
	id := string(msg.Key)
	if msg.Value == nil || len(msg.Value) == 0 {
		return h.graph.DeleteEdgeByID(context.Background(), id)
	}
	var rec EdgeRecord
	if err := json.Unmarshal(msg.Value, &rec); err != nil {
		return err
	}
	if rec.ID == "" {
		rec.ID = id
	}
	if strings.EqualFold(rec.Op, "DELETE") {
		return h.graph.DeleteEdgeByID(context.Background(), rec.ID)
	}
	return h.graph.UpsertEdge(context.Background(), rec)
}

func (h *handler) handleEvent(msg *sarama.ConsumerMessage) error {
	if msg.Value == nil || len(msg.Value) == 0 {
		return nil
	}
	var ev EventNormalized
	if err := json.Unmarshal(msg.Value, &ev); err != nil {
		return err
	}
	if ev.EventID == "" {
		ev.EventID = string(msg.Key)
	}
	if err := h.graph.UpsertEpisodeAndLink(context.Background(), ev); err != nil {
		return err
	}
	if ev.Reason != "" {
		_ = h.linkRuleToEpisode(context.Background(), ev.Reason, ev.EventID)
	}
	return h.graph.LinkRCA(context.Background(), ev.EventID, h.rcaWindow)
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
	}

	if err := h.graph.UpsertEpisodeAndLink(context.Background(), ev); err != nil {
		return err
	}
	return h.graph.LinkRCA(context.Background(), ev.EventID, h.rcaWindow)
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

func isHighSignalLog(sev, msg string) bool {
	sev = strings.ToUpper(sev)
	m := strings.ToLower(msg)
	if sev == "ERROR" || sev == "FATAL" {
		return true
	}
	// well-known problem patterns
	if strings.Contains(m, "crashloopbackoff") ||
		strings.Contains(m, "back-off restarting failed container") ||
		strings.Contains(m, "readiness probe failed") ||
		strings.Contains(m, "liveness probe failed") ||
		strings.Contains(m, "imagepullbackoff") || strings.Contains(m, "errimagepull") ||
		strings.Contains(m, "oom killed") || strings.Contains(m, "oomkilled") ||
		strings.Contains(m, "panic:") {
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
func (h *handler) linkRuleToEpisode(ctx context.Context, ruleName, eid string) error {
	s := h.graph.drv.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeWrite})
	defer s.Close(ctx)
	_, err := s.ExecuteWrite(ctx, func(tx neo4j.ManagedTransaction) (any, error) {
		_, err := tx.Run(ctx, `
MATCH (e:Episodic {eid:$eid})
MATCH (r:Rule {name:$name})
MERGE (r)-[:EMITS]->(e)`, map[string]any{"eid": eid, "name": ruleName})
		return nil, err
	})
	return err
}

func (h *handler) handlePromTarget(msg *sarama.ConsumerMessage) error {
	key := string(msg.Key)
	if msg.Value == nil || len(msg.Value) == 0 {
		return h.graph.DeletePromTargetByKey(context.Background(), key)
	}
	var rec PromTargetRecord
	if err := json.Unmarshal(msg.Value, &rec); err != nil {
		return err
	}
	if strings.EqualFold(rec.Op, "DELETE") {
		return h.graph.DeletePromTargetByKey(context.Background(), key)
	}
	return h.graph.UpsertPromTarget(context.Background(), key, rec)
}

func (h *handler) handleRule(msg *sarama.ConsumerMessage) error {
	key := string(msg.Key)
	if msg.Value == nil || len(msg.Value) == 0 {
		return nil // soft-delete optional
	}
	var rec RuleRecord
	if err := json.Unmarshal(msg.Value, &rec); err != nil {
		return err
	}
	if strings.EqualFold(rec.Op, "DELETE") {
		return nil
	}
	return h.graph.UpsertRule(context.Background(), key, rec)
}

func (h *handler) handleCommand(msg *sarama.ConsumerMessage) error {
	if msg.Value == nil || len(msg.Value) == 0 {
		return nil
	}
	var m struct{ Op string `json:"op"` }
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
	group := getenv("KAFKA_GROUP", "kg-builder")

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
	cfg.ClientID = "kg-builder"

	cg, err := sarama.NewConsumerGroup(brokers, group, cfg)
	if err != nil {
		log.Fatalf("kafka: %v", err)
	}
	defer cg.Close()

	h := &handler{
		graph:         g,
		rcaWindow:     rcaWin,
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
