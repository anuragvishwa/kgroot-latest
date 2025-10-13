# Quick Payment Flow for Alpha Customers

## Option 1: Stripe Payment Link (5 minutes setup)

### 1. Create Stripe Account
- Go to stripe.com
- Create account (free)
- Get API keys

### 2. Create Payment Link
```bash
# In Stripe Dashboard:
Products → Create Product
- Name: "KG RCA Pilot Setup"
- Price: $500 one-time
- Generate Payment Link
```

### 3. Send to Customers
```
Subject: Your KG RCA Pilot Setup

Hi [Name],

Excited to get you started with KG RCA!

Next steps:
1. Complete payment: [STRIPE_PAYMENT_LINK]
2. I'll provision your infrastructure within 24 hours
3. We'll schedule onboarding call

Questions? Reply to this email.

Best,
[Your name]
```

### 4. After Payment
- Stripe sends webhook → You get notified
- Spin up EC2 instance for them ($77/month)
- Their $500 covers 6 months of AWS costs
- Send credentials

---

## Option 2: Invoice Payment (for corporate buyers)

### Tools:
- Stripe Invoicing (free)
- PayPal Invoicing (free)
- Wave Accounting (free)

### Terms:
- **Due:** Net 7 (payment within 7 days)
- **Setup Fee:** $500
- **Monthly:** $99/month (starts after setup)
- **Minimum:** 3 months ($297)

### Sample Invoice:
```
INVOICE #001

Bill To: Acme Corp
Date: 2025-10-11
Due: 2025-10-18 (Net 7)

Items:
1. KG RCA Setup Fee             $500.00
2. Month 1-3 Service (3x$99)    $297.00
                               --------
Total:                          $797.00

Payment via: Stripe/PayPal/Wire
```

**Send invoice → Get paid → Start work**

---

## Option 3: Hybrid Model (RECOMMENDED)

### Tier 1: SMB/Startups (Self-service)
- Pay online via Stripe ($500 setup + $99/mo)
- Automated onboarding
- Email support

### Tier 2: Enterprise (Sales-led)
- $2,500 setup (covers POC infrastructure)
- $499-2,000/month
- Custom contract
- 50% upfront, 50% after POC success

---

## Quick Stripe Setup (No Code)

### Step 1: Create Product
```
Stripe Dashboard → Products → + New
Name: KG RCA Pilot Program
Pricing: $500 one-time + $99/month recurring
```

### Step 2: Generate Payment Link
```
Payment Links → + New
Product: KG RCA Pilot Program
Success URL: https://yourdomain.com/success
✓ Collect customer email
✓ Collect billing address
```

### Step 3: Share Link
```
https://buy.stripe.com/your-unique-link
```

That's it! No website needed.

---

## Cash Flow Projection

### Scenario: 5 Pilot Customers

**Month 0 (Setup):**
```
Income:  5 × $500 setup = $2,500
Costs:   5 × $77 AWS   = $385
Profit:                  $2,115 ✅
```

**Month 1-3 (Recurring):**
```
Income:  5 × $99/mo    = $495/month
Costs:   5 × $77 AWS   = $385/month
Profit:                  $110/month ✅
```

**You're cash-flow positive from Day 1!**

---

## What If They Don't Want to Pay Upfront?

### Option A: Reduce Setup Fee
```
$250 setup + $149/month (3-month min)
Total upfront: $250 + $447 = $697
```

### Option B: First Month Prepaid
```
$0 setup + $299 first month (then $99/month)
```

### Option C: Partial Refund
```
$500 setup, refundable if you don't see 50% MTTR reduction
(But keep $200 to cover AWS costs if they churn)
```

---

## Red Flags to Avoid

❌ **Don't do:**
- Free pilots without payment
- "Pay after you see value" (they never will)
- Net 30/60 payment terms for small companies
- Work without written agreement

✅ **Do:**
- Get payment before provisioning
- 3-month minimum commitment
- Clear refund policy
- Simple 1-page agreement

---

## Simple Agreement Template

```
KG RCA PILOT AGREEMENT

Customer: [Company Name]
Date: [Date]
Duration: 3 months (auto-renews monthly)

Fees:
- Setup: $500 (one-time, non-refundable after provisioning)
- Monthly: $99/month (billed monthly)
- Minimum: 3 months

What You Get:
- KG RCA platform access
- Up to 100K events/day
- Email support (24-hour response)
- 20-minute onboarding call

Cancellation:
- After 3 months: 30 days notice
- Refund: If <50% MTTR improvement, refund 50% of setup fee

Payment: Via Stripe (card) or Invoice (Net 7)

Agreed:
[Customer Signature] [Date]
[Your Signature] [Date]
```

---

## Next Steps (Today)

1. **Create Stripe account** (15 min)
2. **Create payment link** for $500 setup + $99/mo (10 min)
3. **Update outreach** to mention pilot fee (5 min)
4. **Send to first 10 prospects** (30 min)

**Total time: 1 hour to start getting paid**
