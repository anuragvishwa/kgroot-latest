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

	"io"
	"net/http"

	"github.com/IBM/sarama"
	appsv1 "k8s.io/api/apps/v1"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	meta "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/labels"
	"k8s.io/client-go/informers"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/cache"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/tools/leaderelection"
	"k8s.io/client-go/tools/leaderelection/resourcelock"
)

// ===== Models =====
// ---- Prom targets API shapes ----
type promTargetsResp struct {
	Status string `json:"status"`
	Data   struct {
		ActiveTargets  []promTarget `json:"activeTargets"`
		DroppedTargets []promTarget `json:"droppedTargets"`
	} `json:"data"`
}

type promTarget struct {
	Labels           map[string]string `json:"labels"`
	DiscoveredLabels map[string]string `json:"discoveredLabels"`
	ScrapeURL        string            `json:"scrapeUrl"`
	LastScrape       string            `json:"lastScrape"`
	LastError        string            `json:"lastError"`
	Health           string            `json:"health"` // "up"/"down"/"unknown"
}

// What we publish
type TargetRecord struct {
	Op         string            `json:"op"` // UPSERT / DELETE (tombstone when Value=nil)
	At         time.Time         `json:"at"`
	ClientID   string            `json:"client_id,omitempty"` // Multi-tenant: client identifier
	Cluster    string            `json:"cluster"`
	Labels     map[string]string `json:"labels"`
	ScrapeURL  string            `json:"scrapeUrl"`
	Health     string            `json:"health"`
	LastScrape string            `json:"lastScrape"`
	LastError  string            `json:"lastError,omitempty"`
}

type ResourceRecord struct {
	Op        string            `json:"op"` // "UPSERT" or "DELETE"
	At        time.Time         `json:"at"`
	ClientID  string            `json:"client_id,omitempty"` // Multi-tenant: client identifier
	Cluster   string            `json:"cluster"`
	Kind      string            `json:"kind"`
	UID       string            `json:"uid"`
	Namespace string            `json:"namespace,omitempty"`
	Name      string            `json:"name"`
	Labels    map[string]string `json:"labels,omitempty"`
	OwnerRefs []OwnerRef        `json:"ownerRefs,omitempty"`

	// Hints / joins
	Node       string            `json:"node,omitempty"`
	PodIP      string            `json:"podIP,omitempty"`
	ServiceSel map[string]string `json:"serviceSelector,omitempty"`
	ServiceIPs []string          `json:"serviceIPs,omitempty"`
	Image      string            `json:"image,omitempty"`
	Replicas   *int32            `json:"replicas,omitempty"`
	Status     map[string]any    `json:"status,omitempty"`
	Spec       any               `json:"spec,omitempty"`
}

type OwnerRef struct {
	Kind string `json:"kind"`
	Name string `json:"name"`
}

type EdgeRecord struct {
	Op       string    `json:"op"` // "UPSERT" or "DELETE"
	At       time.Time `json:"at"`
	ClientID string    `json:"client_id,omitempty"` // Multi-tenant: client identifier
	Cluster  string    `json:"cluster"`
	ID       string    `json:"id"`
	From     string    `json:"from"`
	To       string    `json:"to"`
	Type     string    `json:"type"` // RUNS_ON, SELECTS, CONTROLS
}

// ===== Edge/index state =====

func targetKey(cluster string, t promTarget) string {
	// stable, compacted-topic key (tweak if you prefer)
	job := t.Labels["job"]
	ns := t.Labels["namespace"]
	svc := t.Labels["service"]
	inst := t.Labels["instance"]
	return fmt.Sprintf("%s|%s|%s|%s|%s", cluster, job, ns, svc, inst)
}

func fetchPromTargets(client *http.Client, promURL string) (*promTargetsResp, error) {
	req, err := http.NewRequest("GET", strings.TrimRight(promURL, "/")+"/api/v1/targets", nil)
	if err != nil {
		return nil, err
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("prometheus %s: %s", resp.Status, string(b))
	}
	var out promTargetsResp
	dec := json.NewDecoder(resp.Body)
	if err := dec.Decode(&out); err != nil {
		return nil, err
	}
	if strings.ToLower(out.Status) != "success" {
		return nil, fmt.Errorf("prometheus returned status=%q", out.Status)
	}
	return &out, nil
}

// Poll /targets and publish to Kafka (compacted with tombstones)
func runPromTargetSync(ctx context.Context, cluster, clientID, promURL string, p sarama.AsyncProducer, topic string, interval time.Duration) {
	httpc := &http.Client{Timeout: 10 * time.Second}
	prev := map[string]struct{}{}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			res, err := fetchPromTargets(httpc, promURL)
			if err != nil {
				log.Printf("prom targets: %v", err)
				continue
			}
			now := time.Now().UTC()
			curr := map[string]struct{}{}

			for _, t := range res.Data.ActiveTargets {
				k := targetKey(cluster, t)
				curr[k] = struct{}{}
				rec := TargetRecord{
					Op: "UPSERT", At: now, ClientID: clientID, Cluster: cluster,
					Labels: t.Labels, ScrapeURL: t.ScrapeURL,
					Health: t.Health, LastScrape: t.LastScrape, LastError: t.LastError,
				}
				sendJSON(p, clientID, topic, k, rec)
			}

			// Tombstones for disappeared targets
			for k := range prev {
				if _, still := curr[k]; !still {
					sendJSON(p, clientID, topic, k, nil)
				}
			}
			prev = curr
		}
	}
}

type edgeIndex struct {
	mu   sync.Mutex
	data map[string]map[string]struct{} // serviceID -> set(podID)
}

func newEdgeIndex() *edgeIndex { return &edgeIndex{data: make(map[string]map[string]struct{})} }
func (e *edgeIndex) snapshot(serviceID string) map[string]struct{} {
	e.mu.Lock()
	defer e.mu.Unlock()
	cp := map[string]struct{}{}
	for k := range e.data[serviceID] {
		cp[k] = struct{}{}
	}
	return cp
}
func (e *edgeIndex) set(serviceID string, pods map[string]struct{}) {
	e.mu.Lock()
	e.data[serviceID] = pods
	e.mu.Unlock()
}
func (e *edgeIndex) add(serviceID, podID string) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.data[serviceID] == nil {
		e.data[serviceID] = map[string]struct{}{}
	}
	e.data[serviceID][podID] = struct{}{}
}
func (e *edgeIndex) remove(serviceID, podID string) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if set := e.data[serviceID]; set != nil {
		delete(set, podID)
		if len(set) == 0 {
			delete(e.data, serviceID)
		}
	}
}

// Tracks the *controlling* owner (Deployment/RS/DS/Job) for each Pod
type podControllerIndex struct {
	mu   sync.Mutex
	data map[string]string // podID -> controllerID ("replicaset:ns:name", "daemonset:ns:name", "job:ns:name")
}

func newPodControllerIndex() *podControllerIndex {
	return &podControllerIndex{data: map[string]string{}}
}
func (p *podControllerIndex) get(podID string) (string, bool) {
	p.mu.Lock()
	defer p.mu.Unlock()
	v, ok := p.data[podID]
	return v, ok
}
func (p *podControllerIndex) set(podID, ctrlID string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.data[podID] = ctrlID
}
func (p *podControllerIndex) del(podID string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	delete(p.data, podID)
}

var (
	svcEdgeIdx = newEdgeIndex()
	podIdx     = newPodControllerIndex()
)

// ===== Kafka helpers =====

func newProducer(brokers []string, clientID string) (sarama.AsyncProducer, error) {
	cfg := sarama.NewConfig()
	cfg.Version = sarama.V3_6_0_0

	// 🔧 required for idempotent producers
	cfg.Net.MaxOpenRequests = 1
	cfg.Producer.Idempotent = true
	cfg.Producer.RequiredAcks = sarama.WaitForAll

	// nice-to-haves
	cfg.Producer.Retry.Max = 5
	cfg.Producer.Return.Successes = false
	cfg.Producer.Return.Errors = true
	cfg.Producer.Compression = sarama.CompressionZSTD
	cfg.ClientID = clientID

	return sarama.NewAsyncProducer(brokers, cfg)
}

func tenantKey(clientID, key string) string {
	if clientID == "" {
		return key
	}
	if key == "" {
		return clientID
	}
	return clientID + "|" + key
}

func sendJSON(p sarama.AsyncProducer, clientID, topic, key string, v any) {
	var b []byte
	var err error
	if v != nil {
		b, err = json.Marshal(v)
		if err != nil {
			log.Printf("marshal error: %v", err)
			return
		}
	}
	msg := &sarama.ProducerMessage{
		Topic: topic,
		Key:   sarama.StringEncoder(tenantKey(clientID, key)),
		Value: sarama.ByteEncoder(b),
	}
	p.Input() <- msg
}

// ===== K8s config =====

func kubeConfig() (*rest.Config, error) {
	if cfg, err := rest.InClusterConfig(); err == nil {
		return cfg, nil
	}
	kc := os.Getenv("KUBECONFIG")
	if kc == "" {
		home, _ := os.UserHomeDir()
		kc = fmt.Sprintf("%s/.kube/config", home)
	}
	return clientcmd.BuildConfigFromFlags("", kc)
}

// ===== utils =====

func ownerRefs(refs []meta.OwnerReference) []OwnerRef {
	out := make([]OwnerRef, 0, len(refs))
	for _, r := range refs {
		out = append(out, OwnerRef{Kind: r.Kind, Name: r.Name})
	}
	return out
}
func keyFor(kind, uid string) string { return fmt.Sprintf("%s:%s", strings.ToLower(kind), uid) }
func idFor(kind, ns, name string) string {
	if ns == "" {
		return fmt.Sprintf("%s:%s", strings.ToLower(kind), name)
	}
	return fmt.Sprintf("%s:%s:%s", strings.ToLower(kind), ns, name)
}
func edgeID(fromKind, fromNS, fromName, toKind, toNS, toName string) string {
	return idFor("edge", "", idFor(fromKind, fromNS, fromName)+"->"+idFor(toKind, toNS, toName))
}
func nodeReady(n *corev1.Node) bool {
	for _, c := range n.Status.Conditions {
		if c.Type == corev1.NodeReady && c.Status == corev1.ConditionTrue {
			return true
		}
	}
	return false
}
func aggregateRestartCount(pod *corev1.Pod) int32 {
	var total int32
	for _, cs := range pod.Status.ContainerStatuses {
		total += cs.RestartCount
	}
	return total
}
func allContainersReady(pod *corev1.Pod) bool {
	for _, cs := range pod.Status.ContainerStatuses {
		if !cs.Ready {
			return false
		}
	}
	return true
}
func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// ===== owner lookups =====

func owningOfKind(refs []meta.OwnerReference, kind string) (string, bool) {
	for _, r := range refs {
		if r.Kind == kind {
			return r.Name, true
		}
	}
	return "", false
}
func owningDeploymentName(refs []meta.OwnerReference) (string, bool) {
	return owningOfKind(refs, "Deployment")
}
func owningReplicaSetName(refs []meta.OwnerReference) (string, bool) {
	return owningOfKind(refs, "ReplicaSet")
}
func owningDaemonSetName(refs []meta.OwnerReference) (string, bool) {
	return owningOfKind(refs, "DaemonSet")
}
func owningJobName(refs []meta.OwnerReference) (string, bool) { return owningOfKind(refs, "Job") }
func owningCronJobName(refs []meta.OwnerReference) (string, bool) {
	return owningOfKind(refs, "CronJob")
}

// ===== Reconcilers =====

func collectServiceIPs(svc *corev1.Service) []string {
	var ips []string
	if len(svc.Spec.ClusterIPs) > 0 {
		ips = append(ips, svc.Spec.ClusterIPs...)
	}
	if svc.Spec.ClusterIP != "" && svc.Spec.ClusterIP != "None" {
		ips = append(ips, svc.Spec.ClusterIP)
	}
	return ips
}

func reconcileServiceEdges(cluster string, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicTopo string, svc *corev1.Service) {
	svcID := idFor("service", svc.Namespace, svc.Name)

	if len(svc.Spec.Selector) == 0 {
		// clear all
		old := svcEdgeIdx.snapshot(svcID)
		for podID := range old {
			parts := strings.Split(podID, ":")
			if len(parts) != 3 {
				continue
			}
			eid := edgeID("service", svc.Namespace, svc.Name, "pod", parts[1], parts[2])
			sendJSON(p, clientID, topicTopo, eid, nil)
		}
		svcEdgeIdx.set(svcID, map[string]struct{}{})
		return
	}

	sel := labels.SelectorFromSet(labels.Set(svc.Spec.Selector))
	pods, err := client.CoreV1().Pods(svc.Namespace).List(context.Background(), meta.ListOptions{LabelSelector: sel.String()})
	if err != nil {
		log.Printf("svc reconcile list pods: %v", err)
		return
	}

	now := time.Now().UTC()
	current := make(map[string]struct{}, len(pods.Items))
	for _, pod := range pods.Items {
		current[idFor("pod", pod.Namespace, pod.Name)] = struct{}{}
	}
	prev := svcEdgeIdx.snapshot(svcID)

	// adds
	for podID := range current {
		if _, had := prev[podID]; !had {
			parts := strings.Split(podID, ":")
			if len(parts) != 3 {
				continue
			}
			e := EdgeRecord{
				Op: "UPSERT", At: now, ClientID: clientID, Cluster: cluster,
				ID:   edgeID("service", svc.Namespace, svc.Name, "pod", parts[1], parts[2]),
				From: idFor("service", svc.Namespace, svc.Name), To: podID, Type: "SELECTS",
			}
			sendJSON(p, clientID, topicTopo, e.ID, e)
			svcEdgeIdx.add(svcID, podID)
		}
	}
	// deletes
	for podID := range prev {
		if _, still := current[podID]; !still {
			parts := strings.Split(podID, ":")
			if len(parts) != 3 {
				continue
			}
			eid := edgeID("service", svc.Namespace, svc.Name, "pod", parts[1], parts[2])
			sendJSON(p, clientID, topicTopo, eid, nil)
			svcEdgeIdx.remove(svcID, podID)
		}
	}
}

func reconcilePodServiceMembership(cluster string, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicTopo string, pod *corev1.Pod) {
	services, err := client.CoreV1().Services(pod.Namespace).List(context.Background(), meta.ListOptions{})
	if err != nil {
		log.Printf("pod reconcile list svcs: %v", err)
		return
	}
	podID := idFor("pod", pod.Namespace, pod.Name)
	lbls := labels.Set(pod.Labels)
	now := time.Now().UTC()

	for _, svc := range services.Items {
		svcID := idFor("service", svc.Namespace, svc.Name)
		selector := svc.Spec.Selector
		old := svcEdgeIdx.snapshot(svcID)
		_, had := old[podID]

		if len(selector) == 0 {
			if had {
				eid := edgeID("service", svc.Namespace, svc.Name, "pod", pod.Namespace, pod.Name)
				sendJSON(p, clientID, topicTopo, eid, nil)
				svcEdgeIdx.remove(svcID, podID)
			}
			continue
		}
		match := labels.SelectorFromSet(labels.Set(selector)).Matches(lbls)
		switch {
		case match && !had:
			e := EdgeRecord{
				Op: "UPSERT", At: now, ClientID: clientID, Cluster: cluster,
				ID:   edgeID("service", svc.Namespace, svc.Name, "pod", pod.Namespace, pod.Name),
				From: svcID, To: podID, Type: "SELECTS",
			}
			sendJSON(p, clientID, topicTopo, e.ID, e)
			svcEdgeIdx.add(svcID, podID)
		case !match && had:
			eid := edgeID("service", svc.Namespace, svc.Name, "pod", pod.Namespace, pod.Name)
			sendJSON(p, clientID, topicTopo, eid, nil)
			svcEdgeIdx.remove(svcID, podID)
		}
	}
}

// ===== Handlers =====

func pushPod(cluster string, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicRes, topicTopo string, pod *corev1.Pod) {
	rec := ResourceRecord{
		Op:        "UPSERT",
		At:        time.Now().UTC(),
		ClientID:  clientID,
		Cluster:   cluster,
		Kind:      "Pod",
		UID:       string(pod.UID),
		Namespace: pod.Namespace,
		Name:      pod.Name,
		Labels:    pod.Labels,
		OwnerRefs: ownerRefs(pod.OwnerReferences),
		Node:      pod.Spec.NodeName,
		PodIP:     pod.Status.PodIP,
		Status: map[string]any{
			"phase":          pod.Status.Phase,
			"restartCount":   aggregateRestartCount(pod),
			"containerReady": allContainersReady(pod),
		},
	}
	// Pod -> Node
	if pod.Spec.NodeName != "" {
		e := EdgeRecord{
			Op: "UPSERT", At: rec.At, ClientID: clientID, Cluster: cluster,
			ID:   edgeID("pod", pod.Namespace, pod.Name, "node", "", pod.Spec.NodeName),
			From: idFor("pod", pod.Namespace, pod.Name), To: idFor("node", "", pod.Spec.NodeName), Type: "RUNS_ON",
		}
		sendJSON(p, clientID, topicTopo, e.ID, e)
	}

	// CONTROLS from controller (ReplicaSet | DaemonSet | Job)
	var ctrlKind, ctrlName string
	if name, ok := owningReplicaSetName(pod.OwnerReferences); ok {
		ctrlKind, ctrlName = "replicaset", name
	}
	if name, ok := owningDaemonSetName(pod.OwnerReferences); ok {
		ctrlKind, ctrlName = "daemonset", name
	}
	if name, ok := owningJobName(pod.OwnerReferences); ok {
		ctrlKind, ctrlName = "job", name
	}
	if ctrlKind != "" {
		ctrlID := idFor(ctrlKind, pod.Namespace, ctrlName)
		edge := EdgeRecord{
			Op: "UPSERT", At: rec.At, ClientID: clientID, Cluster: cluster,
			ID:   edgeID(ctrlKind, pod.Namespace, ctrlName, "pod", pod.Namespace, pod.Name),
			From: ctrlID, To: idFor("pod", pod.Namespace, pod.Name), Type: "CONTROLS",
		}
		sendJSON(p, clientID, topicTopo, edge.ID, edge)

		// Tombstone old controller edge if changed
		podID := idFor("pod", pod.Namespace, pod.Name)
		if prev, ok := podIdx.get(podID); !ok || prev != ctrlID {
			if ok && prev != "" {
				pp := strings.Split(prev, ":") // kind:ns:name
				var pk, pns, pn string
				if len(pp) == 3 {
					pk, pns, pn = pp[0], pp[1], pp[2]
				}
				oldID := edgeID(pk, pns, pn, "pod", pod.Namespace, pod.Name)
				sendJSON(p, clientID, topicTopo, oldID, nil)
			}
			podIdx.set(podID, ctrlID)
		}
	}

	// Service membership reconcile for this pod
	reconcilePodServiceMembership(cluster, clientID, client, p, topicTopo, pod)

	sendJSON(p, clientID, topicRes, keyFor("Pod", rec.UID), rec)
}

func deletePod(cluster string, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicRes, topicTopo string, pod *corev1.Pod) {
	// Tombstone controller edge
	podID := idFor("pod", pod.Namespace, pod.Name)
	if prev, ok := podIdx.get(podID); ok && prev != "" {
		pp := strings.Split(prev, ":")
		if len(pp) == 3 {
			oldID := edgeID(pp[0], pp[1], pp[2], "pod", pod.Namespace, pod.Name)
			sendJSON(p, clientID, topicTopo, oldID, nil)
		}
		podIdx.del(podID)
	}
	// Tombstone Service -> Pod edges
	svcs, _ := client.CoreV1().Services(pod.Namespace).List(context.Background(), meta.ListOptions{})
	for _, svc := range svcs.Items {
		svcID := idFor("service", svc.Namespace, svc.Name)
		old := svcEdgeIdx.snapshot(svcID)
		if _, had := old[podID]; had {
			eid := edgeID("service", svc.Namespace, svc.Name, "pod", pod.Namespace, pod.Name)
			sendJSON(p, clientID, topicTopo, eid, nil)
			svcEdgeIdx.remove(svcID, podID)
		}
	}
	sendJSON(p, clientID, topicRes, keyFor("Pod", string(pod.UID)), nil)
}

func pushService(cluster string, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicRes, topicTopo string, svc *corev1.Service) {
	rec := ResourceRecord{
		Op:        "UPSERT",
		At:        time.Now().UTC(),
		ClientID:  clientID,
		Cluster:   cluster,
		Kind:      "Service",
		UID:       string(svc.UID),
		Namespace: svc.Namespace,
		Name:      svc.Name,
		Labels:    svc.Labels,
		OwnerRefs: ownerRefs(svc.OwnerReferences),
		ServiceSel: func() map[string]string {
			if svc.Spec.Selector == nil {
				return map[string]string{}
			}
			return svc.Spec.Selector
		}(),
		ServiceIPs: collectServiceIPs(svc),
		Spec:       map[string]any{"type": svc.Spec.Type, "ports": svc.Spec.Ports, "ipFamilyPolicy": svc.Spec.IPFamilyPolicy},
	}
	reconcileServiceEdges(cluster, clientID, client, p, topicTopo, svc)
	sendJSON(p, clientID, topicRes, keyFor("Service", rec.UID), rec)
}

func deleteService(clientID string, p sarama.AsyncProducer, topicRes, topicTopo string, svc *corev1.Service) {
	svcID := idFor("service", svc.Namespace, svc.Name)
	old := svcEdgeIdx.snapshot(svcID)
	for podID := range old {
		parts := strings.Split(podID, ":")
		if len(parts) != 3 {
			continue
		}
		eid := edgeID("service", svc.Namespace, svc.Name, "pod", parts[1], parts[2])
		sendJSON(p, clientID, topicTopo, eid, nil)
	}
	svcEdgeIdx.set(svcID, map[string]struct{}{})
	sendJSON(p, clientID, topicRes, keyFor("Service", string(svc.UID)), nil)
}

func pushDeployment(cluster string, clientID string, p sarama.AsyncProducer, topicRes, topicTopo string, d *appsv1.Deployment) {
	rec := ResourceRecord{
		Op:        "UPSERT",
		At:        time.Now().UTC(),
		ClientID:  clientID,
		Cluster:   cluster,
		Kind:      "Deployment",
		UID:       string(d.UID),
		Namespace: d.Namespace,
		Name:      d.Name,
		Labels:    d.Labels,
		OwnerRefs: ownerRefs(d.OwnerReferences),
		Replicas:  d.Spec.Replicas,
		Spec:      map[string]any{"strategy": d.Spec.Strategy.Type, "selector": d.Spec.Selector},
	}
	sendJSON(p, clientID, topicRes, keyFor("Deployment", rec.UID), rec)
}

func deleteDeployment(clientID string, p sarama.AsyncProducer, topicRes string, d *appsv1.Deployment) {
	sendJSON(p, clientID, topicRes, keyFor("Deployment", string(d.UID)), nil)
}

func pushReplicaSet(cluster string, clientID string, p sarama.AsyncProducer, topicRes, topicTopo string, rs *appsv1.ReplicaSet) {
	rec := ResourceRecord{
		Op:        "UPSERT",
		At:        time.Now().UTC(),
		ClientID:  clientID,
		Cluster:   cluster,
		Kind:      "ReplicaSet",
		UID:       string(rs.UID),
		Namespace: rs.Namespace,
		Name:      rs.Name,
		Labels:    rs.Labels,
		OwnerRefs: ownerRefs(rs.OwnerReferences),
		Replicas:  rs.Spec.Replicas,
		Spec:      map[string]any{"selector": rs.Spec.Selector},
	}
	if depName, ok := owningDeploymentName(rs.OwnerReferences); ok {
		e := EdgeRecord{
			Op: "UPSERT", At: rec.At, ClientID: clientID, Cluster: cluster,
			ID:   edgeID("deployment", rs.Namespace, depName, "replicaset", rs.Namespace, rs.Name),
			From: idFor("deployment", rs.Namespace, depName), To: idFor("replicaset", rs.Namespace, rs.Name), Type: "CONTROLS",
		}
		sendJSON(p, clientID, topicTopo, e.ID, e)
	}
	sendJSON(p, clientID, topicRes, keyFor("ReplicaSet", rec.UID), rec)
}

func deleteReplicaSet(clientID string, p sarama.AsyncProducer, topicRes string, rs *appsv1.ReplicaSet) {
	sendJSON(p, clientID, topicRes, keyFor("ReplicaSet", string(rs.UID)), nil)
}

func pushDaemonSet(cluster string, clientID string, p sarama.AsyncProducer, topicRes string, ds *appsv1.DaemonSet) {
	rec := ResourceRecord{
		Op:        "UPSERT",
		At:        time.Now().UTC(),
		ClientID:  clientID,
		Cluster:   cluster,
		Kind:      "DaemonSet",
		UID:       string(ds.UID),
		Namespace: ds.Namespace,
		Name:      ds.Name,
		Labels:    ds.Labels,
		OwnerRefs: ownerRefs(ds.OwnerReferences),
		Replicas:  nil,
		Status: map[string]any{
			"desired":   ds.Status.DesiredNumberScheduled,
			"ready":     ds.Status.NumberReady,
			"available": ds.Status.NumberAvailable,
		},
		Spec: map[string]any{"selector": ds.Spec.Selector},
	}
	sendJSON(p, clientID, topicRes, keyFor("DaemonSet", rec.UID), rec)
}

func deleteDaemonSet(clientID string, p sarama.AsyncProducer, topicRes string, ds *appsv1.DaemonSet) {
	sendJSON(p, clientID, topicRes, keyFor("DaemonSet", string(ds.UID)), nil)
}

func pushJob(cluster string, clientID string, p sarama.AsyncProducer, topicRes, topicTopo string, j *batchv1.Job) {
	rec := ResourceRecord{
		Op:        "UPSERT",
		At:        time.Now().UTC(),
		ClientID:  clientID,
		Cluster:   cluster,
		Kind:      "Job",
		UID:       string(j.UID),
		Namespace: j.Namespace,
		Name:      j.Name,
		Labels:    j.Labels,
		OwnerRefs: ownerRefs(j.OwnerReferences),
		Status: map[string]any{
			"active":     j.Status.Active,
			"succeeded":  j.Status.Succeeded,
			"failed":     j.Status.Failed,
			"startTime":  j.Status.StartTime,
			"completion": j.Status.CompletionTime,
		},
		Spec: map[string]any{"parallelism": j.Spec.Parallelism, "completions": j.Spec.Completions},
	}
	// CronJob -> Job
	if cjName, ok := owningCronJobName(j.OwnerReferences); ok {
		e := EdgeRecord{
			Op: "UPSERT", At: rec.At, ClientID: clientID, Cluster: cluster,
			ID:   edgeID("cronjob", j.Namespace, cjName, "job", j.Namespace, j.Name),
			From: idFor("cronjob", j.Namespace, cjName), To: idFor("job", j.Namespace, j.Name), Type: "CONTROLS",
		}
		sendJSON(p, clientID, topicTopo, e.ID, e)
	}
	sendJSON(p, clientID, topicRes, keyFor("Job", rec.UID), rec)
}

func deleteJob(clientID string, p sarama.AsyncProducer, topicRes string, j *batchv1.Job) {
	sendJSON(p, clientID, topicRes, keyFor("Job", string(j.UID)), nil)
}

func pushCronJob(cluster string, clientID string, p sarama.AsyncProducer, topicRes string, cj *batchv1.CronJob) {
	rec := ResourceRecord{
		Op:        "UPSERT",
		At:        time.Now().UTC(),
		ClientID:  clientID,
		Cluster:   cluster,
		Kind:      "CronJob",
		UID:       string(cj.UID),
		Namespace: cj.Namespace,
		Name:      cj.Name,
		Labels:    cj.Labels,
		OwnerRefs: ownerRefs(cj.OwnerReferences),
		Status: map[string]any{
			"lastScheduleTime": cj.Status.LastScheduleTime,
			"active":           len(cj.Status.Active),
		},
		Spec: map[string]any{"schedule": cj.Spec.Schedule, "suspend": cj.Spec.Suspend},
	}
	sendJSON(p, clientID, topicRes, keyFor("CronJob", rec.UID), rec)
}

func deleteCronJob(clientID string, p sarama.AsyncProducer, topicRes string, cj *batchv1.CronJob) {
	sendJSON(p, clientID, topicRes, keyFor("CronJob", string(cj.UID)), nil)
}

func pushNode(cluster string, clientID string, p sarama.AsyncProducer, topicRes string, n *corev1.Node) {
	rec := ResourceRecord{
		Op:       "UPSERT",
		At:       time.Now().UTC(),
		ClientID: clientID,
		Cluster:  cluster,
		Kind:     "Node",
		UID:      string(n.UID),
		Name:     n.Name,
		Labels:   n.Labels,
		Status:   map[string]any{"ready": nodeReady(n)},
	}
	sendJSON(p, clientID, topicRes, keyFor("Node", rec.UID), rec)
}

func deleteNode(clientID string, p sarama.AsyncProducer, topicRes string, n *corev1.Node) {
	sendJSON(p, clientID, topicRes, keyFor("Node", string(n.UID)), nil)
}

// ===== Leader-runner =====

func runWatchers(ctx context.Context, cluster string, clientID string, client *kubernetes.Clientset, producer sarama.AsyncProducer, topicRes, topicTopo string) {
	// Periodic resync to reconcile Service<->Pod edges even without direct events
	factory := informers.NewSharedInformerFactory(client, 30*time.Second)

	// Pods
	podInf := factory.Core().V1().Pods().Informer()
	podInf.AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc: func(obj any) { pushPod(cluster, clientID, client, producer, topicRes, topicTopo, obj.(*corev1.Pod)) },
		UpdateFunc: func(_, newObj any) {
			pushPod(cluster, clientID, client, producer, topicRes, topicTopo, newObj.(*corev1.Pod))
		},
		DeleteFunc: func(obj any) {
			pod, ok := obj.(*corev1.Pod)
			if !ok {
				tomb, _ := obj.(cache.DeletedFinalStateUnknown)
				if p, ok := tomb.Obj.(*corev1.Pod); ok {
					pod = p
				}
			}
			if pod != nil {
				deletePod(cluster, clientID, client, producer, topicRes, topicTopo, pod)
			}
		},
	})

	// Services
	svcInf := factory.Core().V1().Services().Informer()
	svcInf.AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc: func(obj any) {
			pushService(cluster, clientID, client, producer, topicRes, topicTopo, obj.(*corev1.Service))
		},
		UpdateFunc: func(_, newObj any) {
			pushService(cluster, clientID, client, producer, topicRes, topicTopo, newObj.(*corev1.Service))
		},
		DeleteFunc: func(obj any) {
			svc, ok := obj.(*corev1.Service)
			if !ok {
				tomb, _ := obj.(cache.DeletedFinalStateUnknown)
				if s, ok := tomb.Obj.(*corev1.Service); ok {
					svc = s
				}
			}
			if svc != nil {
				deleteService(clientID, producer, topicRes, topicTopo, svc)
			}
		},
	})

	// Deployments
	depInf := factory.Apps().V1().Deployments().Informer()
	depInf.AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc: func(obj any) {
			pushDeployment(cluster, clientID, producer, topicRes, topicTopo, obj.(*appsv1.Deployment))
		},
		UpdateFunc: func(_, newObj any) {
			pushDeployment(cluster, clientID, producer, topicRes, topicTopo, newObj.(*appsv1.Deployment))
		},
		DeleteFunc: func(obj any) {
			d, ok := obj.(*appsv1.Deployment)
			if !ok {
				tomb, _ := obj.(cache.DeletedFinalStateUnknown)
				if dd, ok := tomb.Obj.(*appsv1.Deployment); ok {
					d = dd
				}
			}
			if d != nil {
				deleteDeployment(clientID, producer, topicRes, d)
			}
		},
	})

	// ReplicaSets
	rsInf := factory.Apps().V1().ReplicaSets().Informer()
	rsInf.AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc: func(obj any) {
			pushReplicaSet(cluster, clientID, producer, topicRes, topicTopo, obj.(*appsv1.ReplicaSet))
		},
		UpdateFunc: func(_, newObj any) {
			pushReplicaSet(cluster, clientID, producer, topicRes, topicTopo, newObj.(*appsv1.ReplicaSet))
		},
		DeleteFunc: func(obj any) {
			rs, ok := obj.(*appsv1.ReplicaSet)
			if !ok {
				tomb, _ := obj.(cache.DeletedFinalStateUnknown)
				if rr, ok := tomb.Obj.(*appsv1.ReplicaSet); ok {
					rs = rr
				}
			}
			if rs != nil {
				deleteReplicaSet(clientID, producer, topicRes, rs)
			}
		},
	})

	// DaemonSets
	dsInf := factory.Apps().V1().DaemonSets().Informer()
	dsInf.AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc:    func(obj any) { pushDaemonSet(cluster, clientID, producer, topicRes, obj.(*appsv1.DaemonSet)) },
		UpdateFunc: func(_, newObj any) { pushDaemonSet(cluster, clientID, producer, topicRes, newObj.(*appsv1.DaemonSet)) },
		DeleteFunc: func(obj any) {
			ds, ok := obj.(*appsv1.DaemonSet)
			if !ok {
				tomb, _ := obj.(cache.DeletedFinalStateUnknown)
				if dd, ok := tomb.Obj.(*appsv1.DaemonSet); ok {
					ds = dd
				}
			}
			if ds != nil {
				deleteDaemonSet(clientID, producer, topicRes, ds)
			}
		},
	})

	// Jobs
	jobInf := factory.Batch().V1().Jobs().Informer()
	jobInf.AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc:    func(obj any) { pushJob(cluster, clientID, producer, topicRes, topicTopo, obj.(*batchv1.Job)) },
		UpdateFunc: func(_, newObj any) { pushJob(cluster, clientID, producer, topicRes, topicTopo, newObj.(*batchv1.Job)) },
		DeleteFunc: func(obj any) {
			j, ok := obj.(*batchv1.Job)
			if !ok {
				tomb, _ := obj.(cache.DeletedFinalStateUnknown)
				if jj, ok := tomb.Obj.(*batchv1.Job); ok {
					j = jj
				}
			}
			if j != nil {
				deleteJob(clientID, producer, topicRes, j)
			}
		},
	})

	// CronJobs
	cjInf := factory.Batch().V1().CronJobs().Informer()
	cjInf.AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc:    func(obj any) { pushCronJob(cluster, clientID, producer, topicRes, obj.(*batchv1.CronJob)) },
		UpdateFunc: func(_, newObj any) { pushCronJob(cluster, clientID, producer, topicRes, newObj.(*batchv1.CronJob)) },
		DeleteFunc: func(obj any) {
			cj, ok := obj.(*batchv1.CronJob)
			if !ok {
				tomb, _ := obj.(cache.DeletedFinalStateUnknown)
				if cc, ok := tomb.Obj.(*batchv1.CronJob); ok {
					cj = cc
				}
			}
			if cj != nil {
				deleteCronJob(clientID, producer, topicRes, cj)
			}
		},
	})

	// Nodes
	nodeInf := factory.Core().V1().Nodes().Informer()
	nodeInf.AddEventHandler(cache.ResourceEventHandlerFuncs{
		AddFunc:    func(obj any) { pushNode(cluster, clientID, producer, topicRes, obj.(*corev1.Node)) },
		UpdateFunc: func(_, newObj any) { pushNode(cluster, clientID, producer, topicRes, newObj.(*corev1.Node)) },
		DeleteFunc: func(obj any) {
			n, ok := obj.(*corev1.Node)
			if !ok {
				tomb, _ := obj.(cache.DeletedFinalStateUnknown)
				if nn, ok := tomb.Obj.(*corev1.Node); ok {
					n = nn
				}
			}
			if n != nil {
				deleteNode(clientID, producer, topicRes, n)
			}
		},
	})

	// Start and sync
	stop := make(chan struct{})
	go factory.Start(stop)

	okMap := map[string]bool{
		"pods":        cache.WaitForCacheSync(stop, podInf.HasSynced),
		"services":    cache.WaitForCacheSync(stop, svcInf.HasSynced),
		"deployments": cache.WaitForCacheSync(stop, depInf.HasSynced),
		"replicasets": cache.WaitForCacheSync(stop, rsInf.HasSynced),
		"daemonsets":  cache.WaitForCacheSync(stop, dsInf.HasSynced),
		"jobs":        cache.WaitForCacheSync(stop, jobInf.HasSynced),
		"cronjobs":    cache.WaitForCacheSync(stop, cjInf.HasSynced),
		"nodes":       cache.WaitForCacheSync(stop, nodeInf.HasSynced),
	}
	for kind, ok := range okMap {
		if !ok {
			log.Printf("warning: informer %s did not sync", kind)
		}
	}

	log.Printf("leader: watchers running")
	<-ctx.Done()
	close(stop)
	log.Printf("leader: context done, exiting watchers")
}

// ===== main with leader election =====

func main() {
	cluster := getenv("CLUSTER_NAME", "minikube")
	brokers := strings.Split(getenv("KAFKA_BOOTSTRAP", "kafka:9092"), ",")
	topicRes := getenv("TOPIC_STATE", "state.k8s.resource")
	topicTopo := getenv("TOPIC_TOPO", "state.k8s.topology")
	clientID := getenv("KAFKA_CLIENT_ID", "state-watcher")
	// Multi-tenant: Read CLIENT_ID from environment
	tenantClientID := getenv("CLIENT_ID", "")
	if tenantClientID != "" {
		log.Printf("multi-tenant mode: client_id=%s", tenantClientID)
	}
	promURL := getenv("PROM_URL", "http://kube-prometheus-stack-prometheus.monitoring.svc:9090")
	topicProm := getenv("TOPIC_PROM_TARGETS", "state.prom.targets")
	promTick := 30 * time.Second

	cfg, err := kubeConfig()
	if err != nil {
		log.Fatalf("kube config: %v", err)
	}
	client, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		log.Fatalf("kube client: %v", err)
	}

	producer, err := newProducer(brokers, clientID)
	if err != nil {
		log.Fatalf("kafka: %v", err)
	}
	defer producer.Close()
	go func() {
		for err := range producer.Errors() {
			log.Printf("kafka err: %v", err)
		}
	}()

	// Leader election
	leaseNS := getenv("LEASE_NAMESPACE", "observability")
	leaseName := getenv("LEASE_NAME", "state-watcher-leader")
	id := getenv("POD_NAME", "") // set via Downward API; fallback to hostname
	if id == "" {
		h, _ := os.Hostname()
		id = h
	}

	lock := &resourcelock.LeaseLock{
		LeaseMeta: meta.ObjectMeta{Name: leaseName, Namespace: leaseNS},
		Client:    client.CoordinationV1(),
		LockConfig: resourcelock.ResourceLockConfig{
			Identity: id,
		},
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		c := make(chan os.Signal, 1)
		signal.Notify(c, syscall.SIGINT, syscall.SIGTERM)
		<-c
		cancel()
	}()

	lec := leaderelection.LeaderElectionConfig{
		Lock:          lock,
		LeaseDuration: 15 * time.Second,
		RenewDeadline: 10 * time.Second,
		RetryPeriod:   2 * time.Second,
		Callbacks: leaderelection.LeaderCallbacks{
			OnStartedLeading: func(ctx context.Context) {
				go runPromTargetSync(ctx, cluster, tenantClientID, promURL, producer, topicProm, promTick)
				runWatchers(ctx, cluster, tenantClientID, client, producer, topicRes, topicTopo)
			},
			OnStoppedLeading: func() {
				log.Printf("lost leadership, exiting")
				os.Exit(0)
			},
			OnNewLeader: func(current string) {
				if current == id {
					log.Printf("I am the leader: %s", current)
				} else {
					log.Printf("new leader: %s", current)
				}
			},
		},
		ReleaseOnCancel: true,
		Name:            "state-watcher",
	}

	log.Printf("starting leader election on %s/%s as %s", leaseNS, leaseName, id)
	leaderelection.RunOrDie(ctx, lec)
}
