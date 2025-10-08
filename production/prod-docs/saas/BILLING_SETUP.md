# Billing & Metering Setup

Complete guide for implementing usage-based billing for your KG RCA SaaS platform.

---

## Table of Contents

1. [Overview](#overview)
2. [Pricing Model](#pricing-model)
3. [Usage Tracking](#usage-tracking)
4. [Stripe Integration](#stripe-integration)
5. [Invoice Generation](#invoice-generation)
6. [Payment Processing](#payment-processing)
7. [Usage Dashboards](#usage-dashboards)
8. [Cost Optimization](#cost-optimization)

---

## Overview

**Revenue Model**: Usage-based billing with tiered pricing

**Billable Metrics**:
- Events ingested (per 1K events)
- RCA queries executed (per query)
- Storage used (per GB)
- API calls (per 1K calls)

**Billing Cycle**: Monthly, with real-time usage tracking

---

## Pricing Model

### Tiered Pricing

| Plan | Base Price | Events/Day | RCA Queries | Storage | API Calls | Overage |
|------|-----------|------------|-------------|---------|-----------|---------|
| **Free** | $0 | 10K | 100 | 1 GB | 10K | N/A (hard limit) |
| **Basic** | $99/mo | 100K | 1K | 10 GB | 100K | $0.10/1K events |
| **Pro** | $499/mo | 1M | 10K | 100 GB | 1M | $0.05/1K events |
| **Enterprise** | Custom | Unlimited | Unlimited | Unlimited | Unlimited | Custom |

### Usage-Based Pricing

**Events Ingested**:
- Free: $0 (up to 10K/day, then hard limit)
- Basic: $0.10 per 1,000 events over limit
- Pro: $0.05 per 1,000 events over limit
- Enterprise: Custom rates

**RCA Queries**:
- Free: $0 (up to 100/month, then hard limit)
- Basic: $0.50 per query over limit
- Pro: $0.25 per query over limit
- Enterprise: Custom rates

**Storage**:
- Free: $0 (up to 1 GB)
- Basic: $2 per GB over 10 GB
- Pro: $1 per GB over 100 GB
- Enterprise: Custom rates

**Example Monthly Bill (Pro Plan)**:
```
Base: $499
Events: 35M total → 5M overage → $250 (5M / 1K * $0.05)
Queries: 12K total → 2K overage → $500 (2K * $0.25)
Storage: 150 GB total → 50 GB overage → $50 (50 * $1)
Total: $1,299
```

---

## Usage Tracking

### 3.1 Metrics Collection

**File**: `/production/billing-service/metrics.go`

```go
package billing

import (
    "context"
    "time"
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

// Billable metrics
var (
    eventsIngested = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "billing_events_ingested_total",
            Help: "Total events ingested per client",
        },
        []string{"client_id", "event_type"},
    )

    rcaQueries = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "billing_rca_queries_total",
            Help: "Total RCA queries per client",
        },
        []string{"client_id"},
    )

    storageUsed = promauto.NewGaugeVec(
        prometheus.GaugeOpts{
            Name: "billing_storage_used_bytes",
            Help: "Storage used per client in bytes",
        },
        []string{"client_id", "storage_type"},
    )

    apiCalls = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "billing_api_calls_total",
            Help: "Total API calls per client",
        },
        []string{"client_id", "endpoint", "status"},
    )
)

type UsageTracker struct {
    db *sql.DB
}

// Track event ingestion
func (ut *UsageTracker) TrackEvent(clientID, eventType string) {
    eventsIngested.WithLabelValues(clientID, eventType).Inc()

    // Store in PostgreSQL for billing
    ut.db.Exec(`
        INSERT INTO usage_logs (client_id, metric_type, metric_value, timestamp)
        VALUES ($1, 'events_ingested', 1, NOW())
    `, clientID)
}

// Track RCA query
func (ut *UsageTracker) TrackRCAQuery(clientID string, queryType string) {
    rcaQueries.WithLabelValues(clientID).Inc()

    ut.db.Exec(`
        INSERT INTO usage_logs (client_id, metric_type, metric_value, timestamp)
        VALUES ($1, 'rca_queries', 1, NOW())
    `, clientID)
}

// Track storage usage (runs hourly)
func (ut *UsageTracker) TrackStorage(clientID string) error {
    // Query Neo4j database size
    neo4jSize, err := ut.getNeo4jDatabaseSize(clientID)
    if err != nil {
        return err
    }

    // Query Kafka topic size
    kafkaSize, err := ut.getKafkaTopicSize(clientID)
    if err != nil {
        return err
    }

    totalSize := neo4jSize + kafkaSize
    storageUsed.WithLabelValues(clientID, "total").Set(float64(totalSize))

    ut.db.Exec(`
        INSERT INTO usage_logs (client_id, metric_type, metric_value, timestamp)
        VALUES ($1, 'storage_bytes', $2, NOW())
    `, clientID, totalSize)

    return nil
}

// Track API call
func (ut *UsageTracker) TrackAPICall(clientID, endpoint string, statusCode int) {
    apiCalls.WithLabelValues(clientID, endpoint, fmt.Sprintf("%d", statusCode)).Inc()

    ut.db.Exec(`
        INSERT INTO usage_logs (client_id, metric_type, metric_value, timestamp)
        VALUES ($1, 'api_calls', 1, NOW())
    `, clientID)
}

// Get Neo4j database size
func (ut *UsageTracker) getNeo4jDatabaseSize(clientID string) (int64, error) {
    dbName := strings.ReplaceAll(clientID, "-", "_")

    query := fmt.Sprintf(`
        USE %s;
        CALL apoc.meta.stats() YIELD nodeCount, relCount
        RETURN nodeCount, relCount
    `, dbName)

    // Execute query and estimate size
    // ~1KB per node, ~500 bytes per relationship
    var nodeCount, relCount int64
    // ... execute query ...

    size := (nodeCount * 1024) + (relCount * 512)
    return size, nil
}

// Get Kafka topic size
func (ut *UsageTracker) getKafkaTopicSize(clientID string) (int64, error) {
    // Use Kafka Admin API to get topic sizes
    topics := []string{
        fmt.Sprintf("%s.events.normalized", clientID),
        fmt.Sprintf("%s.state.k8s.resource", clientID),
        fmt.Sprintf("%s.state.k8s.topology", clientID),
        fmt.Sprintf("%s.logs.normalized", clientID),
        fmt.Sprintf("%s.alerts.raw", clientID),
    }

    var totalSize int64
    for _, topic := range topics {
        size, err := ut.getTopicSize(topic)
        if err != nil {
            return 0, err
        }
        totalSize += size
    }

    return totalSize, nil
}
```

### 3.2 PostgreSQL Schema

```sql
-- Database: billing

-- Clients table
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    plan VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    stripe_customer_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_clients_client_id ON clients(client_id);
CREATE INDEX idx_clients_stripe_customer_id ON clients(stripe_customer_id);

-- Subscriptions table
CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) REFERENCES clients(client_id),
    plan VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    stripe_subscription_id VARCHAR(255),
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Usage logs table (raw metrics)
CREATE TABLE usage_logs (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL,
    metric_type VARCHAR(50) NOT NULL,
    metric_value BIGINT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_usage_logs_client_id ON usage_logs(client_id);
CREATE INDEX idx_usage_logs_timestamp ON usage_logs(timestamp);
CREATE INDEX idx_usage_logs_client_timestamp ON usage_logs(client_id, timestamp);

-- Daily usage aggregates
CREATE TABLE daily_usage (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    events_ingested BIGINT DEFAULT 0,
    rca_queries INTEGER DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    api_calls BIGINT DEFAULT 0,
    UNIQUE(client_id, date)
);

CREATE INDEX idx_daily_usage_client_date ON daily_usage(client_id, date);

-- Monthly usage aggregates
CREATE TABLE monthly_usage (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    events_ingested BIGINT DEFAULT 0,
    rca_queries INTEGER DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    api_calls BIGINT DEFAULT 0,
    base_cost DECIMAL(10, 2) DEFAULT 0,
    overage_cost DECIMAL(10, 2) DEFAULT 0,
    total_cost DECIMAL(10, 2) DEFAULT 0,
    UNIQUE(client_id, year, month)
);

-- Invoices table
CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL,
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    base_amount DECIMAL(10, 2) NOT NULL,
    overage_amount DECIMAL(10, 2) NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    stripe_invoice_id VARCHAR(255),
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Payments table
CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id),
    client_id VARCHAR(255) NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'USD',
    status VARCHAR(50) DEFAULT 'pending',
    stripe_payment_intent_id VARCHAR(255),
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 3.3 Aggregation CronJob

```bash
# Aggregate daily usage (runs at 1 AM UTC)
kubectl create cronjob daily-usage-aggregation \
  --image=your-registry.com/billing-service:v1.0.0 \
  --schedule="0 1 * * *" \
  --restart=OnFailure \
  -- /bin/sh -c "
    psql \$DATABASE_URL <<SQL
      INSERT INTO daily_usage (client_id, date, events_ingested, rca_queries, storage_bytes, api_calls)
      SELECT
        client_id,
        CURRENT_DATE - 1,
        COALESCE(SUM(CASE WHEN metric_type = 'events_ingested' THEN metric_value END), 0),
        COALESCE(SUM(CASE WHEN metric_type = 'rca_queries' THEN metric_value END), 0),
        COALESCE(MAX(CASE WHEN metric_type = 'storage_bytes' THEN metric_value END), 0),
        COALESCE(SUM(CASE WHEN metric_type = 'api_calls' THEN metric_value END), 0)
      FROM usage_logs
      WHERE DATE(timestamp) = CURRENT_DATE - 1
      GROUP BY client_id
      ON CONFLICT (client_id, date) DO UPDATE SET
        events_ingested = EXCLUDED.events_ingested,
        rca_queries = EXCLUDED.rca_queries,
        storage_bytes = EXCLUDED.storage_bytes,
        api_calls = EXCLUDED.api_calls;
SQL
  "
```

---

## Stripe Integration

### 4.1 Setup Stripe

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login to Stripe
stripe login

# Create products and prices
stripe products create \
  --name="KG RCA Basic Plan" \
  --description="100K events/day, 1K RCA queries"

stripe prices create \
  --product=prod_basic_123 \
  --unit-amount=9900 \
  --currency=usd \
  --recurring[interval]=month

# Create usage-based pricing for overages
stripe prices create \
  --product=prod_basic_123 \
  --billing-scheme=tiered \
  --currency=usd \
  --recurring[interval]=month \
  --recurring[usage-type]=metered \
  --tiers[0][up_to]=100000 \
  --tiers[0][unit_amount]=0 \
  --tiers[1][up_to]=inf \
  --tiers[1][unit_amount]=10
```

### 4.2 Stripe Integration Code

**File**: `/production/billing-service/stripe.go`

```go
package billing

import (
    "github.com/stripe/stripe-go/v76"
    "github.com/stripe/stripe-go/v76/customer"
    "github.com/stripe/stripe-go/v76/subscription"
    "github.com/stripe/stripe-go/v76/usagerecord"
)

type StripeService struct {
    apiKey string
}

func NewStripeService(apiKey string) *StripeService {
    stripe.Key = apiKey
    return &StripeService{apiKey: apiKey}
}

// Create customer
func (s *StripeService) CreateCustomer(clientID, name, email string) (string, error) {
    params := &stripe.CustomerParams{
        Name:  stripe.String(name),
        Email: stripe.String(email),
        Metadata: map[string]string{
            "client_id": clientID,
        },
    }

    c, err := customer.New(params)
    if err != nil {
        return "", err
    }

    return c.ID, nil
}

// Create subscription
func (s *StripeService) CreateSubscription(customerID, priceID string) (string, error) {
    params := &stripe.SubscriptionParams{
        Customer: stripe.String(customerID),
        Items: []*stripe.SubscriptionItemsParams{
            {
                Price: stripe.String(priceID),
            },
        },
    }

    sub, err := subscription.New(params)
    if err != nil {
        return "", err
    }

    return sub.ID, nil
}

// Report usage (for metered billing)
func (s *StripeService) ReportUsage(subscriptionItemID string, quantity int64) error {
    params := &stripe.UsageRecordParams{
        SubscriptionItem: stripe.String(subscriptionItemID),
        Quantity:         stripe.Int64(quantity),
        Timestamp:        stripe.Int64(time.Now().Unix()),
    }

    _, err := usagerecord.New(params)
    return err
}

// Report daily usage to Stripe
func (s *StripeService) ReportDailyUsage(clientID string) error {
    // Get subscription item IDs
    items, err := s.getSubscriptionItems(clientID)
    if err != nil {
        return err
    }

    // Get yesterday's usage
    usage, err := s.getDailyUsage(clientID, time.Now().AddDate(0, 0, -1))
    if err != nil {
        return err
    }

    // Report events ingested
    if eventsItem, ok := items["events"]; ok {
        s.ReportUsage(eventsItem, usage.EventsIngested)
    }

    // Report RCA queries
    if queriesItem, ok := items["queries"]; ok {
        s.ReportUsage(queriesItem, int64(usage.RCAQueries))
    }

    // Report storage
    if storageItem, ok := items["storage"]; ok {
        storageGB := usage.StorageBytes / (1024 * 1024 * 1024)
        s.ReportUsage(storageItem, storageGB)
    }

    return nil
}
```

### 4.3 Webhook Handler

```go
// Handle Stripe webhooks
func (s *StripeService) HandleWebhook(payload []byte, signature string) error {
    event, err := webhook.ConstructEvent(payload, signature, s.webhookSecret)
    if err != nil {
        return err
    }

    switch event.Type {
    case "invoice.payment_succeeded":
        var invoice stripe.Invoice
        json.Unmarshal(event.Data.Raw, &invoice)
        s.handlePaymentSucceeded(&invoice)

    case "invoice.payment_failed":
        var invoice stripe.Invoice
        json.Unmarshal(event.Data.Raw, &invoice)
        s.handlePaymentFailed(&invoice)

    case "customer.subscription.deleted":
        var subscription stripe.Subscription
        json.Unmarshal(event.Data.Raw, &subscription)
        s.handleSubscriptionCanceled(&subscription)
    }

    return nil
}

func (s *StripeService) handlePaymentSucceeded(invoice *stripe.Invoice) {
    clientID := invoice.Customer.Metadata["client_id"]

    // Update database
    s.db.Exec(`
        UPDATE invoices
        SET status = 'paid', paid_at = NOW()
        WHERE stripe_invoice_id = $1
    `, invoice.ID)

    // Send email to client
    s.sendPaymentConfirmationEmail(clientID, invoice)
}
```

---

## Invoice Generation

### 5.1 Monthly Invoice Generation

```go
// Generate monthly invoice (runs on 1st of each month)
func (bs *BillingService) GenerateMonthlyInvoices() error {
    // Get all active clients
    clients, err := bs.db.Query(`
        SELECT client_id, plan FROM clients WHERE status = 'active'
    `)
    if err != nil {
        return err
    }
    defer clients.Close()

    for clients.Next() {
        var clientID, plan string
        clients.Scan(&clientID, &plan)

        // Calculate usage for last month
        usage, err := bs.calculateMonthlyUsage(clientID)
        if err != nil {
            log.Printf("Error calculating usage for %s: %v", clientID, err)
            continue
        }

        // Calculate charges
        charges := bs.calculateCharges(plan, usage)

        // Create invoice
        invoiceNum := fmt.Sprintf("INV-%s-%s", clientID, time.Now().Format("2006-01"))
        _, err = bs.db.Exec(`
            INSERT INTO invoices (client_id, invoice_number, period_start, period_end, base_amount, overage_amount, total_amount, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
        `, clientID, invoiceNum, usage.PeriodStart, usage.PeriodEnd, charges.Base, charges.Overage, charges.Total)

        if err != nil {
            log.Printf("Error creating invoice for %s: %v", clientID, err)
            continue
        }

        // Create Stripe invoice
        stripeInvoiceID, err := bs.stripe.CreateInvoice(clientID, charges.Total)
        if err != nil {
            log.Printf("Error creating Stripe invoice for %s: %v", clientID, err)
        }

        // Send invoice email
        bs.sendInvoiceEmail(clientID, invoiceNum, charges)
    }

    return nil
}

// Calculate charges based on plan and usage
func (bs *BillingService) calculateCharges(plan string, usage *MonthlyUsage) *Charges {
    planLimits := bs.getPlanLimits(plan)

    charges := &Charges{
        Base: planLimits.BasePrice,
    }

    // Calculate event overage
    if usage.EventsIngested > planLimits.EventsLimit {
        overage := usage.EventsIngested - planLimits.EventsLimit
        charges.EventsOverage = float64(overage) / 1000 * planLimits.EventsOverageRate
    }

    // Calculate query overage
    if usage.RCAQueries > planLimits.QueriesLimit {
        overage := usage.RCAQueries - planLimits.QueriesLimit
        charges.QueriesOverage = float64(overage) * planLimits.QueriesOverageRate
    }

    // Calculate storage overage
    storageGB := usage.StorageBytes / (1024 * 1024 * 1024)
    if storageGB > planLimits.StorageLimit {
        overage := storageGB - planLimits.StorageLimit
        charges.StorageOverage = float64(overage) * planLimits.StorageOverageRate
    }

    charges.Overage = charges.EventsOverage + charges.QueriesOverage + charges.StorageOverage
    charges.Total = charges.Base + charges.Overage

    return charges
}
```

### 5.2 Invoice Email Template

```html
<!-- invoice-email.html -->
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; }
        .invoice { max-width: 600px; margin: 0 auto; }
        .header { background: #4A90E2; color: white; padding: 20px; }
        .details { padding: 20px; }
        .line-item { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #eee; }
        .total { font-size: 20px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="invoice">
        <div class="header">
            <h1>KG RCA Invoice</h1>
            <p>Invoice #{{.InvoiceNumber}}</p>
        </div>

        <div class="details">
            <p><strong>Client:</strong> {{.ClientName}}</p>
            <p><strong>Plan:</strong> {{.Plan}}</p>
            <p><strong>Period:</strong> {{.PeriodStart}} - {{.PeriodEnd}}</p>

            <h3>Usage</h3>
            <div class="line-item">
                <span>Events Ingested</span>
                <span>{{.EventsIngested}} events</span>
            </div>
            <div class="line-item">
                <span>RCA Queries</span>
                <span>{{.RCAQueries}} queries</span>
            </div>
            <div class="line-item">
                <span>Storage Used</span>
                <span>{{.StorageGB}} GB</span>
            </div>
            <div class="line-item">
                <span>API Calls</span>
                <span>{{.APICalls}} calls</span>
            </div>

            <h3>Charges</h3>
            <div class="line-item">
                <span>Base Plan</span>
                <span>${{.BaseAmount}}</span>
            </div>
            <div class="line-item">
                <span>Overage Charges</span>
                <span>${{.OverageAmount}}</span>
            </div>
            <div class="line-item total">
                <span>Total</span>
                <span>${{.TotalAmount}}</span>
            </div>

            <p style="margin-top: 30px;">
                <a href="{{.PaymentURL}}" style="background: #4A90E2; color: white; padding: 10px 20px; text-decoration: none;">
                    Pay Now
                </a>
            </p>

            <p style="color: #666; font-size: 12px;">
                Payment will be automatically charged to your card on file.
                <br>Questions? Contact support@your-company.com
            </p>
        </div>
    </div>
</body>
</html>
```

---

## Payment Processing

### 6.1 Automatic Payment

```go
// Process automatic payment (3 days after invoice)
func (bs *BillingService) ProcessAutomaticPayments() error {
    // Get pending invoices older than 3 days
    invoices, err := bs.db.Query(`
        SELECT id, client_id, total_amount, stripe_invoice_id
        FROM invoices
        WHERE status = 'pending'
        AND created_at < NOW() - INTERVAL '3 days'
    `)
    if err != nil {
        return err
    }
    defer invoices.Close()

    for invoices.Next() {
        var invoiceID int
        var clientID string
        var amount float64
        var stripeInvoiceID string

        invoices.Scan(&invoiceID, &clientID, &amount, &stripeInvoiceID)

        // Charge via Stripe
        paymentIntent, err := bs.stripe.ChargeCustomer(clientID, amount)
        if err != nil {
            log.Printf("Payment failed for %s: %v", clientID, err)
            bs.handlePaymentFailure(invoiceID, clientID)
            continue
        }

        // Update invoice
        bs.db.Exec(`
            UPDATE invoices
            SET status = 'paid', paid_at = NOW()
            WHERE id = $1
        `, invoiceID)

        // Record payment
        bs.db.Exec(`
            INSERT INTO payments (invoice_id, client_id, amount, status, stripe_payment_intent_id, paid_at)
            VALUES ($1, $2, $3, 'succeeded', $4, NOW())
        `, invoiceID, clientID, amount, paymentIntent.ID)

        // Send receipt
        bs.sendPaymentReceipt(clientID, invoiceID)
    }

    return nil
}

// Handle payment failure
func (bs *BillingService) handlePaymentFailure(invoiceID int, clientID string) {
    // Mark invoice as failed
    bs.db.Exec(`
        UPDATE invoices SET status = 'failed' WHERE id = $1
    `, invoiceID)

    // Send notification to client
    bs.sendPaymentFailureEmail(clientID, invoiceID)

    // After 3 failed attempts, suspend account
    failedCount := bs.getFailedPaymentCount(clientID)
    if failedCount >= 3 {
        bs.suspendClient(clientID)
    }
}

// Suspend client account
func (bs *BillingService) suspendClient(clientID string) {
    bs.db.Exec(`
        UPDATE clients SET status = 'suspended' WHERE client_id = $1
    `, clientID)

    // Revoke API key
    bs.revokeAPIKey(clientID)

    // Stop processing client data
    bs.stopDataProcessing(clientID)

    // Send suspension notice
    bs.sendSuspensionEmail(clientID)
}
```

---

## Usage Dashboards

### 7.1 Client Usage Dashboard

```yaml
# Grafana dashboard for clients
apiVersion: v1
kind: ConfigMap
metadata:
  name: client-usage-dashboard
data:
  dashboard.json: |
    {
      "dashboard": {
        "title": "Usage & Billing",
        "panels": [
          {
            "title": "Events Ingested (This Month)",
            "targets": [{
              "expr": "sum(billing_events_ingested_total{client_id=\"$client_id\"})"
            }],
            "thresholds": [
              {"value": 100000, "color": "green"},
              {"value": 1000000, "color": "yellow"},
              {"value": 10000000, "color": "red"}
            ]
          },
          {
            "title": "RCA Queries (This Month)",
            "targets": [{
              "expr": "sum(billing_rca_queries_total{client_id=\"$client_id\"})"
            }]
          },
          {
            "title": "Storage Used",
            "targets": [{
              "expr": "billing_storage_used_bytes{client_id=\"$client_id\"} / 1024 / 1024 / 1024"
            }]
          },
          {
            "title": "Estimated Bill",
            "targets": [{
              "expr": "billing_estimated_cost{client_id=\"$client_id\"}"
            }],
            "format": "currency"
          },
          {
            "title": "Daily Events",
            "type": "graph",
            "targets": [{
              "expr": "sum(rate(billing_events_ingested_total{client_id=\"$client_id\"}[1d]))"
            }]
          }
        ]
      }
    }
```

### 7.2 Admin Billing Dashboard

```yaml
# Grafana dashboard for admins
apiVersion: v1
kind: ConfigMap
metadata:
  name: admin-billing-dashboard
data:
  dashboard.json: |
    {
      "dashboard": {
        "title": "Billing Overview (All Clients)",
        "panels": [
          {
            "title": "Monthly Revenue",
            "targets": [{
              "expr": "sum(billing_monthly_revenue)"
            }]
          },
          {
            "title": "Top Clients by Usage",
            "type": "table",
            "targets": [{
              "expr": "topk(10, sum by (client_id) (billing_events_ingested_total))"
            }]
          },
          {
            "title": "Revenue by Plan",
            "type": "pie",
            "targets": [{
              "expr": "sum by (plan) (billing_monthly_revenue)"
            }]
          },
          {
            "title": "Failed Payments",
            "targets": [{
              "expr": "count(billing_invoices{status=\"failed\"})"
            }]
          }
        ]
      }
    }
```

---

## Cost Optimization

### 8.1 Data Retention Policies

```bash
# Automatically cleanup old data to reduce storage costs

# Delete events older than retention period
kubectl create cronjob cleanup-old-events \
  --schedule="0 2 * * *" \
  --image=your-registry.com/graph-builder:v1.0.0 \
  -- /bin/sh -c "
    for client in \$(psql -t -c 'SELECT client_id FROM clients WHERE status = \"active\"'); do
      # Get client's retention days based on plan
      retention=\$(psql -t -c \"SELECT CASE plan WHEN 'free' THEN 7 WHEN 'basic' THEN 30 WHEN 'pro' THEN 90 ELSE 365 END FROM clients WHERE client_id = '\$client'\")

      # Delete old Neo4j events
      cypher-shell -d \${client//-/_} <<CYPHER
        MATCH (e:Episodic)
        WHERE e.event_time < datetime() - duration({days: \$retention})
        DETACH DELETE e
CYPHER
    done
  "
```

### 8.2 Kafka Compression

```yaml
# Enable compression in Kafka to reduce storage
kafka:
  config:
    compressionType: lz4  # or zstd for better compression
    logSegmentBytes: 1073741824  # 1 GB segments
    logRetentionHours: 168  # 7 days
    logRetentionBytes: 10737418240  # 10 GB per topic
```

### 8.3 Neo4j Optimization

```cypher
-- Compact Neo4j database (runs monthly)
CALL apoc.trigger.add('compact_db', '
  MATCH (e:Episodic)
  WHERE e.event_time < datetime() - duration({days: 90})
  WITH e LIMIT 10000
  DETACH DELETE e
', {phase: 'after'});
```

---

## Summary

**Billing Flow**:
1. Track usage in real-time → Prometheus metrics + PostgreSQL logs
2. Aggregate daily → CronJob at 1 AM
3. Generate invoices monthly → 1st of each month
4. Charge via Stripe → 3 days after invoice
5. Handle failures → Suspend after 3 failures

**Key Metrics**:
- Events ingested (per 1K)
- RCA queries (per query)
- Storage used (per GB)
- API calls (per 1K)

**Stripe Integration**:
- Metered billing for usage-based pricing
- Automatic payment collection
- Webhook handling for payment events

**Next Steps**:
1. Deploy billing-service
2. Configure Stripe products and prices
3. Setup webhooks
4. Test with a pilot client
5. Launch billing for all clients

---

## Related Documentation

- [SAAS_ARCHITECTURE.md](SAAS_ARCHITECTURE.md) - Multi-tenant architecture
- [SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md) - Server deployment guide
- [CLIENT_ONBOARDING.md](CLIENT_ONBOARDING.md) - Client onboarding process
