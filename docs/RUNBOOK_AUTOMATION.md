# 🤖 Runbook Automation - Complete Guide

**Purpose**: Automate incident remediation based on RCA findings
**Version**: 1.0
**Status**: Implementation Plan + MVP Code

---

## 📑 Table of Contents

1. [What is Runbook Automation?](#what-is-runbook-automation)
2. [Why Add It to KGroot?](#why-add-it-to-kgroot)
3. [Architecture](#architecture)
4. [Runbook Definition Format](#runbook-definition-format)
5. [Implementation Phases](#implementation-phases)
6. [MVP Implementation](#mvp-implementation)
7. [Example Runbooks](#example-runbooks)
8. [Safety & Guardrails](#safety--guardrails)
9. [Integration with RCA](#integration-with-rca)
10. [Competitive Analysis](#competitive-analysis)

---

## What is Runbook Automation?

**Runbook Automation** automatically executes remediation actions when incidents are detected, based on:
1. **Root Cause Analysis (RCA)** findings
2. **Predefined runbooks** (step-by-step procedures)
3. **Safety rules** (approval requirements, blast radius limits)

### Example Scenario

**Without Runbook Automation**:
```
1. Alert fires: PodCrashLooping
2. On-call engineer gets paged at 3am
3. Engineer logs in, runs kubectl commands
4. Identifies root cause: OOMKilled
5. Manually increases memory limits
6. Redeploys pod
7. Verifies fix
Time: 20-30 minutes
```

**With Runbook Automation**:
```
1. Alert fires: PodCrashLooping
2. KGroot RCA identifies: OOMKilled (95% confidence)
3. Runbook triggers automatically:
   - Increase memory from 256Mi → 512Mi
   - Apply change via kubectl
   - Wait for pod to stabilize
4. Send notification: "Auto-remediated OOMKilled"
Time: 2-3 minutes, no human intervention
```

---

## Why Add It to KGroot?

### Current State (Your System)
✅ **Best-in-class RCA**: 99.32% accuracy, 51K+ causal links
✅ **Real-time detection**: Kafka streaming, immediate analysis
✅ **Explainable AI**: Confidence scores, causal chains

❌ **Manual remediation**: Humans still need to fix issues

### With Runbook Automation
🚀 **Close the loop**: Detect → Diagnose → **Remediate**
🚀 **Reduce MTTR**: From 20 minutes → 2 minutes
🚀 **Competitive edge**: BigPanda, Resolve.ai have this
🚀 **Higher pricing**: Justify $999-$2999/mo pricing

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────┐
│                 KGroot RCA System                   │
│                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐     │
│  │ Neo4j    │───▶│ kg-api   │───▶│ Runbook  │     │
│  │ RCA      │    │ RCA API  │    │ Engine   │     │
│  └──────────┘    └──────────┘    └────┬─────┘     │
│                                        │           │
│                                        ▼           │
│                              ┌──────────────────┐  │
│                              │ Runbook Library  │  │
│                              │ (YAML files)     │  │
│                              └────┬─────────────┘  │
│                                   │                │
└───────────────────────────────────┼────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
         ┌──────────┐        ┌──────────┐       ┌──────────┐
         │Kubernetes│        │  Slack   │       │ Webhook  │
         │  kubectl │        │  Notify  │       │ Trigger  │
         └──────────┘        └──────────┘       └──────────┘
```

### Data Flow

1. **Incident Detected**: Alert fires, stored in Neo4j as Episodic node
2. **RCA Triggered**: Graph builder identifies root cause (e.g., OOMKilled)
3. **Runbook Matched**: Runbook engine finds matching runbook
4. **Safety Check**: Verify conditions (confidence > 0.8, manual approval if risky)
5. **Execute Actions**: Run kubectl commands, call APIs
6. **Verify Success**: Check if incident resolved
7. **Notify**: Send summary to Slack/Teams

---

## Runbook Definition Format

### Runbook YAML Schema

```yaml
# File: runbooks/oomkilled-increase-memory.yaml
runbook:
  id: oomkilled-increase-memory-v1
  name: "Auto-remediate OOMKilled by increasing memory"
  version: 1.0
  author: sre-team

  # Trigger conditions
  trigger:
    root_cause_reason: "OOMKilled"
    symptom_reason: ["CrashLoopBackOff", "BackOff", "Error"]
    min_confidence: 0.80  # Only run if RCA confidence > 80%
    affected_resource_kinds: ["Pod"]

  # Safety guardrails
  safety:
    require_approval: false  # Set true for risky actions
    max_executions_per_hour: 5  # Rate limit
    blast_radius_limit: 10  # Max resources to affect
    dry_run_first: true  # Test before real execution

  # Remediation steps
  steps:
    - name: "Get current memory limit"
      action: kubectl_get
      params:
        resource: "pod"
        name: "{{ incident.resource.name }}"
        namespace: "{{ incident.resource.namespace }}"
        field: "spec.containers[0].resources.limits.memory"
      output_var: current_memory

    - name: "Calculate new memory limit"
      action: calculate
      params:
        expression: "{{ current_memory | parse_memory | multiply(2) }}"
      output_var: new_memory

    - name: "Update Deployment memory limit"
      action: kubectl_patch
      params:
        resource: "deployment"
        name: "{{ incident.resource.controller }}"
        namespace: "{{ incident.resource.namespace }}"
        patch: |
          spec:
            template:
              spec:
                containers:
                - name: "{{ incident.resource.container_name }}"
                  resources:
                    limits:
                      memory: "{{ new_memory }}"

    - name: "Wait for pod to restart"
      action: wait
      params:
        condition: "pod/{{ incident.resource.name }} ready"
        timeout: 300  # 5 minutes

    - name: "Verify incident resolved"
      action: check_neo4j
      params:
        query: |
          MATCH (e:Episodic {eid: $incident_id})
          MATCH (new_incident:Episodic)-[:ABOUT]->(r:Resource {rid: $resource_rid})
          WHERE new_incident.event_time > $incident_time + duration({minutes: 5})
            AND new_incident.reason IN ['OOMKilled', 'CrashLoopBackOff']
          RETURN count(new_incident) AS new_failures
        expect: "new_failures == 0"

  # Notification
  notification:
    on_success:
      slack:
        channel: "#incidents"
        message: |
          ✅ Auto-remediated OOMKilled incident
          Pod: {{ incident.resource.name }}
          Action: Increased memory {{ current_memory }} → {{ new_memory }}
          RCA Confidence: {{ incident.rca_confidence }}

    on_failure:
      slack:
        channel: "#incidents"
        message: |
          ❌ Runbook failed for OOMKilled incident
          Pod: {{ incident.resource.name }}
          Error: {{ error_message }}
          Manual intervention required

  # Rollback (if remediation fails)
  rollback:
    - name: "Revert memory change"
      action: kubectl_patch
      params:
        resource: "deployment"
        name: "{{ incident.resource.controller }}"
        patch: |
          spec:
            template:
              spec:
                containers:
                - name: "{{ incident.resource.container_name }}"
                  resources:
                    limits:
                      memory: "{{ current_memory }}"
```

---

## Implementation Phases

### Phase 1: MVP (2-3 weeks)

**Goal**: Basic runbook execution for 3 common issues

**Features**:
- ✅ YAML runbook parser
- ✅ Basic actions: kubectl, slack notifications
- ✅ Manual approval workflow
- ✅ 3 starter runbooks (OOMKilled, ImagePullBackOff, NodeNotReady)

**MVP Runbook Engine** (Go):
```go
// File: kg/runbook-engine.go

package main

import (
    "context"
    "gopkg.in/yaml.v3"
)

type Runbook struct {
    ID      string            `yaml:"id"`
    Name    string            `yaml:"name"`
    Trigger RunbookTrigger    `yaml:"trigger"`
    Safety  SafetyConfig      `yaml:"safety"`
    Steps   []RunbookStep     `yaml:"steps"`
}

type RunbookTrigger struct {
    RootCauseReason string   `yaml:"root_cause_reason"`
    SymptomReason   []string `yaml:"symptom_reason"`
    MinConfidence   float64  `yaml:"min_confidence"`
}

type SafetyConfig struct {
    RequireApproval bool `yaml:"require_approval"`
    MaxExecutionsPerHour int `yaml:"max_executions_per_hour"`
    DryRunFirst bool `yaml:"dry_run_first"`
}

type RunbookStep struct {
    Name   string                 `yaml:"name"`
    Action string                 `yaml:"action"`
    Params map[string]interface{} `yaml:"params"`
}

type RunbookEngine struct {
    runbooks map[string]*Runbook
}

func (e *RunbookEngine) LoadRunbooks(dir string) error {
    // Load all YAML files from runbooks/ directory
    // ...
}

func (e *RunbookEngine) FindMatchingRunbook(incident *Incident) *Runbook {
    for _, rb := range e.runbooks {
        if rb.Trigger.RootCauseReason == incident.RootCause.Reason &&
           incident.RCAConfidence >= rb.Trigger.MinConfidence {
            return rb
        }
    }
    return nil
}

func (e *RunbookEngine) ExecuteRunbook(ctx context.Context, rb *Runbook, incident *Incident) error {
    // Safety check
    if rb.Safety.RequireApproval {
        if !waitForApproval(incident.ID) {
            return fmt.Errorf("approval denied")
        }
    }

    // Execute steps
    for _, step := range rb.Steps {
        if err := e.executeStep(ctx, step, incident); err != nil {
            return fmt.Errorf("step %s failed: %w", step.Name, err)
        }
    }

    return nil
}

func (e *RunbookEngine) executeStep(ctx context.Context, step RunbookStep, incident *Incident) error {
    switch step.Action {
    case "kubectl_patch":
        return e.kubectlPatch(ctx, step.Params, incident)
    case "slack_notify":
        return e.slackNotify(ctx, step.Params, incident)
    case "wait":
        return e.wait(ctx, step.Params)
    default:
        return fmt.Errorf("unknown action: %s", step.Action)
    }
}
```

**Complexity**: Medium (200-300 lines of Go code)

---

### Phase 2: Enhanced (1-2 months)

**Additional Features**:
- ✅ Conditional logic (if/else in runbooks)
- ✅ Rollback on failure
- ✅ Runbook chaining (one runbook calls another)
- ✅ Metrics (success rate, execution time)
- ✅ Runbook versioning

---

### Phase 3: Advanced (3-6 months)

**Enterprise Features**:
- ✅ ML-based runbook recommendation
- ✅ Self-learning (improve runbooks based on outcomes)
- ✅ Multi-cluster orchestration
- ✅ Integration with ticketing (Jira, ServiceNow)
- ✅ Audit logs and compliance

---

## MVP Implementation

### File Structure

```
kgroot_latest/
├── kg/
│   ├── runbook-engine.go       # NEW: Runbook execution engine
│   └── runbook-matcher.go      # NEW: Match incidents to runbooks
│
├── runbooks/                   # NEW: Runbook library
│   ├── oomkilled-increase-memory.yaml
│   ├── imagepullbackoff-fix-registry.yaml
│   ├── nodenotready-cordon-drain.yaml
│   └── README.md
│
├── kg-api/
│   └── runbook-api.go          # NEW: REST API for runbooks
│
└── docs/
    └── RUNBOOK_AUTOMATION.md   # This file
```

### Integration Points

#### 1. Trigger Runbook from RCA

**Modify `kg/graph-builder.go`**:

```go
// After RCA link is created
func (h *Handler) processEvent(ev EventNormalized) {
    // ... existing RCA logic ...

    // NEW: Check if runbook should run
    if h.runbookEngine != nil && ev.Severity == "ERROR" {
        go h.checkAndExecuteRunbook(ev.EventID)
    }
}

func (h *Handler) checkAndExecuteRunbook(incidentID string) {
    incident := h.getRCAForIncident(incidentID)
    if incident.RootCause == nil || incident.RCAConfidence < 0.7 {
        return // No high-confidence RCA, skip runbook
    }

    runbook := h.runbookEngine.FindMatchingRunbook(incident)
    if runbook != nil {
        log.Printf("[runbook] Found match for %s: %s", incidentID, runbook.Name)
        if err := h.runbookEngine.ExecuteRunbook(context.Background(), runbook, incident); err != nil {
            log.Printf("[runbook] Execution failed: %v", err)
        }
    }
}
```

#### 2. Approval Workflow (Slack)

**Slack Interactive Button**:
```go
func (e *RunbookEngine) waitForApproval(incidentID string) bool {
    // Send Slack message with Approve/Deny buttons
    slackMsg := SlackMessage{
        Text: "Runbook execution requires approval",
        Attachments: []Attachment{
            {
                Text: fmt.Sprintf("Incident: %s", incidentID),
                Actions: []Action{
                    {Type: "button", Text: "Approve", Value: "approve"},
                    {Type: "button", Text: "Deny", Value: "deny"},
                },
            },
        },
    }

    // Wait for user interaction (webhook callback)
    return waitForSlackResponse(incidentID, 5*time.Minute)
}
```

---

## Example Runbooks

### Runbook 1: OOMKilled → Increase Memory

**Problem**: Pod killed due to out-of-memory
**Solution**: Double memory limit

```yaml
runbook:
  id: oomkilled-increase-memory-v1
  trigger:
    root_cause_reason: "OOMKilled"
    min_confidence: 0.80

  steps:
    - name: "Increase memory limit"
      action: kubectl_patch
      params:
        resource: "deployment"
        patch: |
          spec:
            template:
              spec:
                containers:
                - name: app
                  resources:
                    limits:
                      memory: "{{ current_memory * 2 }}"
```

---

### Runbook 2: ImagePullBackOff → Fix Registry Auth

**Problem**: Pod can't pull container image
**Solution**: Update image pull secret

```yaml
runbook:
  id: imagepullbackoff-fix-auth-v1
  trigger:
    root_cause_reason: "ImagePullBackOff"
    min_confidence: 0.75

  safety:
    require_approval: true  # Risky: affects registry credentials

  steps:
    - name: "Check if secret exists"
      action: kubectl_get
      params:
        resource: "secret"
        name: "regcred"
        namespace: "{{ incident.resource.namespace }}"

    - name: "Recreate secret"
      action: kubectl_apply
      params:
        manifest: |
          apiVersion: v1
          kind: Secret
          metadata:
            name: regcred
          type: kubernetes.io/dockerconfigjson
          data:
            .dockerconfigjson: "{{ base64(registry_config) }}"

    - name: "Restart pods"
      action: kubectl_rollout_restart
      params:
        resource: "deployment/{{ incident.resource.controller }}"
```

---

### Runbook 3: NodeNotReady → Cordon and Drain

**Problem**: Kubernetes node is not ready
**Solution**: Cordon node, drain pods, trigger node replacement

```yaml
runbook:
  id: nodenotready-cordon-drain-v1
  trigger:
    root_cause_reason: "NodeNotReady"
    min_confidence: 0.85
    affected_resource_kinds: ["Node"]

  safety:
    require_approval: true  # High blast radius
    dry_run_first: true

  steps:
    - name: "Cordon node"
      action: kubectl_cordon
      params:
        node: "{{ incident.resource.name }}"

    - name: "Drain pods"
      action: kubectl_drain
      params:
        node: "{{ incident.resource.name }}"
        ignore_daemonsets: true
        delete_emptydir_data: true

    - name: "Trigger node replacement (cloud provider)"
      action: webhook
      params:
        url: "https://cloud-api.example.com/replace-node"
        method: "POST"
        body: |
          {
            "node_name": "{{ incident.resource.name }}",
            "cluster": "{{ incident.cluster }}"
          }
```

---

## Safety & Guardrails

### 1. Confidence Threshold

Only execute runbooks if RCA confidence > 80%

```yaml
safety:
  min_confidence: 0.80
```

### 2. Manual Approval

Require human approval for risky actions:

```yaml
safety:
  require_approval: true
```

### 3. Dry Run First

Test runbook without making changes:

```yaml
safety:
  dry_run_first: true
```

### 4. Rate Limiting

Prevent runbook storms:

```yaml
safety:
  max_executions_per_hour: 5
```

### 5. Blast Radius Limit

Limit number of affected resources:

```yaml
safety:
  blast_radius_limit: 10  # Max 10 pods/nodes
```

### 6. Rollback on Failure

Automatically revert changes if runbook fails:

```yaml
rollback:
  - name: "Revert deployment"
    action: kubectl_rollout_undo
```

### 7. Audit Logs

Log all runbook executions to Neo4j:

```cypher
CREATE (exec:RunbookExecution {
  id: "exec-123",
  runbook_id: "oomkilled-increase-memory-v1",
  incident_id: "event-abc123",
  executed_at: datetime(),
  executed_by: "system",
  status: "success",
  actions_taken: ["increased memory 256Mi→512Mi"]
})
```

---

## Integration with RCA

### RCA → Runbook Flow

```
1. Alert fires: PodCrashLooping
2. KGroot RCA finds: OOMKilled (confidence: 0.92)
3. Runbook engine queries Neo4j:
   MATCH (symptom:Episodic {eid: $incident_id})
   MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom)
   RETURN cause.reason, r.confidence
4. Match to runbook: oomkilled-increase-memory-v1
5. Execute if confidence > 0.80
```

### Neo4j Query for Runbook Trigger

```cypher
// Get incident with RCA for runbook matching
MATCH (symptom:Episodic {eid: $incident_id})
MATCH (symptom)-[:ABOUT]->(resource:Resource)

// Get root cause
OPTIONAL MATCH (cause:Episodic)-[r:POTENTIAL_CAUSE]->(symptom)
WITH symptom, resource, cause, r
ORDER BY coalesce(r.confidence, 0.0) DESC
LIMIT 1

RETURN {
  incident_id: symptom.eid,
  symptom_reason: symptom.reason,
  root_cause_reason: cause.reason,
  rca_confidence: coalesce(r.confidence, 0.0),
  resource: {
    kind: resource.kind,
    name: resource.name,
    namespace: resource.ns,
    uid: resource.uid
  }
} AS incident_context;
```

---

## Competitive Analysis

### How Competitors Do Runbook Automation

| Feature | Resolve.ai | BigPanda | PagerDuty | **KGroot** |
|---------|-----------|----------|-----------|---------|
| **RCA-based triggering** | ❌ No | ❌ No | ⚠️ Limited | ✅ **Yes (99% accuracy)** |
| **Confidence-based execution** | ❌ No | ❌ No | ❌ No | ✅ **Yes** |
| **Kubernetes-native** | ❌ No | ❌ No | ⚠️ Limited | ✅ **Yes** |
| **Explainable actions** | ⚠️ Limited | ❌ No | ⚠️ Limited | ✅ **Yes (causal chain)** |
| **YAML runbooks** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ **Yes** |
| **Manual approval** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ **Yes** |
| **Rollback support** | ✅ Yes | ⚠️ Limited | ✅ Yes | ✅ **Yes** |

**Your Competitive Advantage**:
- Only system that triggers runbooks based on high-confidence RCA
- Competitors use rule-based triggers (less intelligent)

---

## Pricing Impact

### With Runbook Automation

**Value Proposition**:
- Reduce MTTR by 80% (20 min → 2 min)
- Reduce on-call burden (80% of incidents auto-remediated)
- Prevent cascading failures (fix root cause before symptoms spread)

**Pricing Justification**:
- **Without runbooks**: $299/mo (diagnostic tool)
- **With runbooks**: $999-$2999/mo (full automation)

**ROI for Customer**:
- 1 engineer on-call = $150K/year salary
- Saves 5 hours/week = 15% productivity gain = $22K/year
- Product pays for itself in 6 months

---

## Next Steps

### Week 1-2: Build MVP
- [ ] Create runbook YAML parser (Go)
- [ ] Implement 3 basic actions: kubectl_patch, slack_notify, wait
- [ ] Write 3 starter runbooks (OOMKilled, ImagePullBackOff, NodeNotReady)

### Week 3: Integration
- [ ] Integrate runbook engine into kg-builder
- [ ] Add RCA → Runbook matching logic
- [ ] Test with local Minikube

### Week 4: Production Testing
- [ ] Deploy to staging
- [ ] Test manual approval workflow
- [ ] Measure MTTR improvement

### Month 2-3: Scale
- [ ] Add 10 more runbooks (cover 80% of incidents)
- [ ] Build runbook marketplace (community-contributed)
- [ ] Add metrics dashboard

---

## FAQ

### Q1: Is runbook automation safe?

**A**: Yes, with proper guardrails:
- Confidence threshold (only run if RCA > 80% confident)
- Manual approval for risky actions
- Dry run mode
- Rollback on failure
- Rate limiting (prevent storms)

### Q2: What if runbook makes things worse?

**A**: Rollback support:
```yaml
rollback:
  - name: "Undo changes"
    action: kubectl_rollout_undo
```

### Q3: How do I write custom runbooks?

**A**: Copy existing YAML template, modify trigger and steps. No coding required.

### Q4: Can runbooks call external APIs?

**A**: Yes, via `webhook` action:
```yaml
- name: "Call external API"
  action: webhook
  params:
    url: "https://api.example.com/remediate"
    method: "POST"
```

### Q5: How much dev effort?

**A**:
- MVP: 2-3 weeks (1 engineer)
- Production-ready: 6-8 weeks
- Complexity: Medium

---

**End of Runbook Automation Guide**

For questions, contact: sre-team@yourcompany.com
