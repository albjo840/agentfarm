# Stripe Webhook Setup Guide

## Problem
After paying with Stripe, the user returns to "guest" mode instead of being upgraded to Beta Operator.

## Root Cause
The Stripe webhook is not properly configured, so when payment completes, Stripe can't notify the server to upgrade the user.

## Solution

### Step 1: Configure Webhook in Stripe Dashboard

1. Go to https://dashboard.stripe.com/test/webhooks (test mode)
   - Or https://dashboard.stripe.com/webhooks (live mode)

2. Click **"Add endpoint"**

3. Enter the endpoint URL:
   ```
   http://taborsen.duckdns.org:8080/webhook/stripe
   ```

   **Note:** For live mode, you MUST use HTTPS. Options:
   - Set up SSL/TLS on your server
   - Use a reverse proxy like nginx with Let's Encrypt
   - Use Cloudflare for SSL termination

4. Under "Select events to listen to", click **"Select events"**

5. Select these events:
   - `checkout.session.completed` (required)
   - `customer.subscription.deleted` (optional, for subscription cancellations)

6. Click **"Add endpoint"**

7. **IMPORTANT:** Copy the "Signing secret" (starts with `whsec_`)

### Step 2: Update .env File

Edit `/home/albin/agentfarm/.env`:

```bash
# Replace with your NEW signing secret from Step 1
STRIPE_WEBHOOK_SECRET=whsec_YOUR_NEW_SECRET_HERE
```

### Step 3: Restart the Server

```bash
# Stop and restart agentfarm web server
pkill -f "agentfarm web"
cd /home/albin/agentfarm && agentfarm web
```

### Step 4: Test the Webhook

#### Option A: Use Stripe CLI (Recommended for development)

```bash
# Install Stripe CLI
# On Ubuntu/Debian:
curl -s https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public | gpg --dearmor | sudo tee /usr/share/keyrings/stripe.gpg
echo "deb [signed-by=/usr/share/keyrings/stripe.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" | sudo tee /etc/apt/sources.list.d/stripe.list
sudo apt update && sudo apt install stripe

# Login to Stripe
stripe login

# Forward webhooks to local server
stripe listen --forward-to localhost:8080/webhook/stripe

# In another terminal, trigger a test event
stripe trigger checkout.session.completed
```

#### Option B: Test via Stripe Dashboard

1. Go to your webhook endpoint in Stripe Dashboard
2. Click "Send test webhook"
3. Select "checkout.session.completed"
4. Click "Send test webhook"
5. Check server logs for webhook receipt

#### Option C: Manual Admin Upgrade (for testing)

As an admin, call:
```bash
curl -X POST http://localhost:8080/api/stripe/test-upgrade \
  -H "Content-Type: application/json" \
  -H "Cookie: device_id=YOUR_DEVICE_ID" \
  -d '{}'
```

### Step 5: Verify Configuration

Check the debug endpoint:
```bash
curl http://localhost:8080/api/stripe/debug \
  -H "Cookie: device_id=YOUR_ADMIN_DEVICE_ID"
```

## Switching to Live Mode

When ready for production:

1. Go to https://dashboard.stripe.com/apikeys (not /test/apikeys)
2. Copy the live secret key (starts with `sk_live_`)
3. Create a live webhook endpoint with HTTPS URL
4. Copy the live signing secret

Update `.env`:
```bash
STRIPE_SECRET_KEY=sk_live_YOUR_LIVE_KEY
STRIPE_WEBHOOK_SECRET=whsec_YOUR_LIVE_WEBHOOK_SECRET
STRIPE_SUCCESS_URL=https://yourdomain.com/?payment=success
STRIPE_CANCEL_URL=https://yourdomain.com/?payment=cancelled
```

## Debugging

Check server logs for webhook events:
```bash
tail -f /var/log/agentfarm.log | grep -i stripe
# Or if running in foreground, watch the console output
```

Expected log output on successful webhook:
```
=== STRIPE WEBHOOK RECEIVED ===
Stripe webhook: event_type=checkout.session.completed, client_reference_id=abc123...
handle_webhook: Signature verification PASSED
Stripe webhook result: action=upgrade_beta_operator
SUCCESS: Upgraded user abc123... to Beta Operator
```
