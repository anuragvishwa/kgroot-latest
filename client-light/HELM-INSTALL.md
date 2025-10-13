# Direct Helm Installation

Install KG RCA Agent directly from GitHub release without cloning the repo.

## Method 1: Install from GitHub Release (Recommended)

```bash
# 1. Download Helm chart package
wget https://github.com/anuragvishwa/kgroot-latest/releases/download/v1.0.2/kg-rca-agent-1.0.1.tgz

# 2. Create your values file
cat > my-values.yaml <<EOF
client:
  id: "my-cluster-prod"
  kafka:
    bootstrapServers: "98.90.147.12:9092"
EOF

# 3. Install
helm install kg-rca-agent kg-rca-agent-1.0.1.tgz \
  --values my-values.yaml \
  --namespace observability \
  --create-namespace

# 4. Verify
kubectl get pods -n observability
```

## Method 2: Install from Git Repository

```bash
# 1. Clone repo
git clone https://github.com/anuragvishwa/kgroot-latest.git
cd kgroot-latest/client-light

# 2. Create values
cat > my-values.yaml <<EOF
client:
  id: "my-cluster"
  kafka:
    bootstrapServers: "98.90.147.12:9092"
EOF

# 3. Install
helm install kg-rca-agent ./helm-chart \
  --values my-values.yaml \
  --namespace observability \
  --create-namespace
```

## Configuration Examples

### Minimal (Testing)
```yaml
client:
  id: "test-cluster"
  kafka:
    bootstrapServers: "98.90.147.12:9092"
```

### Production with SSL
```yaml
client:
  id: "prod-us-west"
  apiKey: "your-api-key"
  kafka:
    bootstrapServers: "kafka.lumniverse.com:9093"
    sasl:
      enabled: true
      mechanism: SCRAM-SHA-512
      username: "prod-us-west"
      password: "secure-password"
```

### With Namespace Filtering
```yaml
client:
  id: "prod-cluster"
  kafka:
    bootstrapServers: "98.90.147.12:9092"
  monitoredNamespaces:
    - production
    - staging
```

## Upgrade

```bash
# Download new version
wget https://github.com/anuragvishwa/kgroot-latest/releases/download/v1.0.3/kg-rca-agent-1.0.3.tgz

# Upgrade
helm upgrade kg-rca-agent kg-rca-agent-1.0.3.tgz \
  --values my-values.yaml \
  --namespace observability
```

## Uninstall

```bash
helm uninstall kg-rca-agent --namespace observability
kubectl delete namespace observability
```

## Troubleshooting

### Download Failed
If wget fails, download manually from:
https://github.com/anuragvishwa/kgroot-latest/releases/tag/v1.0.2

### Installation Failed
```bash
# Check Helm syntax
helm lint kg-rca-agent-1.0.1.tgz

# Dry run first
helm install kg-rca-agent kg-rca-agent-1.0.1.tgz \
  --values my-values.yaml \
  --namespace observability \
  --dry-run --debug
```

## Next Steps

After installation, verify data is reaching the server:
- See [INSTALL-TEST-GUIDE.md](INSTALL-TEST-GUIDE.md) for verification steps
