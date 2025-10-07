# Ingress Setup for Permanent Access

This guide sets up Ingress so you can access Neo4j and Kafka UI without `kubectl port-forward`.

---

## 🚀 Quick Setup

### 1. Enable Ingress in Minikube

```bash
minikube addons enable ingress
```

Wait 1-2 minutes for the ingress controller to start:

```bash
# Check if ingress controller is running
kubectl get pods -n ingress-nginx
```

You should see pods like `ingress-nginx-controller-xxxxx` in `Running` state.

### 2. Apply Ingress Configuration

```bash
kubectl apply -f k8s/ingress.yaml
```

### 3. Update /etc/hosts

Add these entries to `/etc/hosts`:

```bash
# Get minikube IP
MINIKUBE_IP=$(minikube ip)

# Add to /etc/hosts (macOS/Linux)
sudo sh -c "echo '${MINIKUBE_IP} neo4j.local' >> /etc/hosts"
sudo sh -c "echo '${MINIKUBE_IP} kafka-ui.local' >> /etc/hosts"
sudo sh -c "echo '${MINIKUBE_IP} prometheus.local' >> /etc/hosts"
sudo sh -c "echo '${MINIKUBE_IP} grafana.local' >> /etc/hosts"
```

Or manually edit:
```bash
sudo nano /etc/hosts
```

Add these lines:
```
192.168.49.2  neo4j.local
192.168.49.2  kafka-ui.local
192.168.49.2  prometheus.local
192.168.49.2  grafana.local
```

(Replace `192.168.49.2` with your actual Minikube IP from `minikube ip`)

### 4. Access the UIs

**Neo4j Browser:**
- URL: http://neo4j.local
- Username: `neo4j`
- Password: `anuragvishwa`

**Kafka UI:**
- URL: http://kafka-ui.local

**Prometheus:**
- URL: http://prometheus.local

**Grafana:**
- URL: http://grafana.local
- Username: `admin`
- Password: Get with: `kubectl get secret -n monitoring prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d`

---

## 🔧 Troubleshooting

### Ingress Controller Not Starting

```bash
# Check addon status
minikube addons list | grep ingress

# If disabled, enable it
minikube addons enable ingress

# Wait and check pods
sleep 60
kubectl get pods -n ingress-nginx

# If still not there, check kube-system
kubectl get pods -n kube-system | grep ingress
```

### Can't Access URLs

**1. Check Ingress is created:**
```bash
kubectl get ingress -n observability
```

Should show:
```
NAME                      CLASS   HOSTS
kgroot-ingress            nginx   neo4j.local,kafka-ui.local,prometheus.local,...
kgroot-ingress-paths      nginx   kgroot.local
```

**2. Check Ingress controller has IP:**
```bash
kubectl get ingress -n observability kgroot-ingress
```

Should show an ADDRESS (Minikube IP).

**3. Verify /etc/hosts:**
```bash
cat /etc/hosts | grep local
```

Should show your entries.

**4. Test connectivity:**
```bash
# Ping the domain
ping neo4j.local

# Test HTTP
curl -I http://neo4j.local
```

### Alternative: Using minikube tunnel

If /etc/hosts doesn't work, use `minikube tunnel`:

```bash
# Run in a separate terminal (keep it running)
minikube tunnel

# Now access via:
# http://neo4j.local
# http://kafka-ui.local
```

---

## 📋 Alternative: Path-based Access

If you prefer single domain with paths, use the `kgroot-ingress-paths` ingress:

Add to /etc/hosts:
```
192.168.49.2  kgroot.local
```

Access:
- Neo4j: http://kgroot.local/neo4j
- Kafka UI: http://kgroot.local/kafka

**Note:** Neo4j Browser may not work well with path-based routing. Subdomain approach is recommended.

---

## 🎯 Recommended Setup (Production-like)

For a more production-like setup:

### Option 1: NodePort (Simplest)

Neo4j and Kafka UI already have NodePort services:

```bash
# Get URLs
echo "Neo4j: http://$(minikube ip):30474"
echo "Kafka UI: http://$(minikube ip):30777"

# Open in browser
minikube service neo4j-external -n observability
minikube service kafka-ui -n observability
```

**Pros:**
- ✅ No ingress needed
- ✅ Works immediately
- ✅ Simple

**Cons:**
- ❌ Need to remember ports
- ❌ Not how production works

### Option 2: Ingress with Custom Domain (Current Approach)

```bash
minikube addons enable ingress
kubectl apply -f k8s/ingress.yaml
# Add to /etc/hosts
```

**Pros:**
- ✅ Production-like setup
- ✅ Clean URLs (neo4j.local)
- ✅ No port numbers

**Cons:**
- ❌ Requires /etc/hosts editing
- ❌ Only works on your machine

### Option 3: Real DNS (Production)

For real deployments (not Minikube):

1. Get a real domain (e.g., kgroot.mycompany.com)
2. Point DNS to your cluster's load balancer
3. Use cert-manager for SSL certificates
4. Update ingress with TLS

```yaml
spec:
  tls:
    - hosts:
        - neo4j.kgroot.mycompany.com
      secretName: neo4j-tls
```

---

## 🧪 Testing the Setup

### Test Neo4j Access

```bash
# Via curl
curl -I http://neo4j.local

# Should return 200 OK

# Test query
curl -u neo4j:anuragvishwa http://neo4j.local/db/neo4j/tx/commit \
  -H "Content-Type: application/json" \
  -d '{"statements":[{"statement":"RETURN 1"}]}'
```

### Test Kafka UI Access

```bash
# Via curl
curl -I http://kafka-ui.local

# Should return 200 OK
```

---

## 📊 Architecture

```
┌──────────────┐
│   Browser    │
└──────┬───────┘
       │
       │ http://neo4j.local
       │ http://kafka-ui.local
       │
       ▼
┌──────────────────────┐
│   /etc/hosts         │
│   192.168.49.2 →     │
│   neo4j.local        │
│   kafka-ui.local     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Ingress Controller  │ (nginx)
│  (ingress-nginx)     │
└──────────┬───────────┘
           │
           ├─→ neo4j-external:7474
           └─→ kafka-ui:8080
```

---

## 🔄 Switching Between Access Methods

You can use multiple methods simultaneously:

**Port Forward (Quick access):**
```bash
kubectl port-forward -n observability svc/neo4j-external 7474:7474
# Access: http://localhost:7474
```

**NodePort (Direct IP access):**
```bash
minikube service neo4j-external -n observability
# Access: http://192.168.49.2:30474
```

**Ingress (Domain-based access):**
```bash
# Setup once, access anytime
# Access: http://neo4j.local
```

---

## 📝 Summary

**Recommended for Minikube:**
Use **NodePort** for simplicity:
```bash
minikube service neo4j-external -n observability
minikube service kafka-ui -n observability
```

**Recommended for Learning/Production-like:**
Use **Ingress** for experience with real-world setups:
```bash
minikube addons enable ingress
kubectl apply -f k8s/ingress.yaml
# Edit /etc/hosts
# Access http://neo4j.local
```

**Current Status:**
- ✅ Ingress YAML created (`k8s/ingress.yaml`)
- ⏳ Ingress controller deploying (takes 1-2 minutes)
- ⬜ /etc/hosts needs manual editing

Run this to check status:
```bash
kubectl get ingress -n observability -w
```

When you see an ADDRESS column with an IP, it's ready!
