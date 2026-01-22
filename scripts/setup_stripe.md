# Stripe Setup Guide

## Aktuell Konfiguration (Live)

```
Domän:        agentfarm.se
Webhook URL:  https://agentfarm.se/webhook/stripe
Status:       LIVE ✅
```

### Miljövariabler (.env)

```bash
STRIPE_SECRET_KEY=sk_live_...              # Live secret key
STRIPE_WEBHOOK_SECRET=whsec_...            # Live webhook signing secret
STRIPE_PROMPT_PACK_PRICE_ID=price_...      # Live Price ID
STRIPE_BETA_OPERATOR_PRICE_ID=price_...    # Live Price ID
STRIPE_SUCCESS_URL=https://agentfarm.se/?payment=success
STRIPE_CANCEL_URL=https://agentfarm.se/?payment=cancelled
```

**VIKTIGT:** Price ID måste vara från LIVE-läge i Stripe Dashboard, inte test-läge!

---

## Problemlösning

### "Your card was declined. Your request was in test mode"

**Orsak:** Price ID är från testläge men du använder riktigt kort.

**Lösning:**
1. Gå till [dashboard.stripe.com/products](https://dashboard.stripe.com/products)
2. **Stäng av "Test mode"** (toggle uppe till höger)
3. Skapa produkt i live-läge
4. Kopiera Price ID
5. Uppdatera `.env` med nya Price ID
6. Starta om servern

### Webhook inte mottagen

**Kontrollera:**
1. SSL-certifikat fungerar: `curl -I https://agentfarm.se/webhook/stripe`
2. Webhook URL i Stripe Dashboard är korrekt
3. Rätt events är valda (checkout.session.completed)

---

## Setup från Scratch

### Steg 1: Skapa Stripe-konto

1. Gå till [stripe.com](https://stripe.com) och skapa konto
2. Verifiera företag/identitet för live-betalningar

### Steg 2: Skapa Produkt (Live Mode)

1. Gå till [dashboard.stripe.com/products](https://dashboard.stripe.com/products)
2. **Stäng av "Test mode"**
3. Klicka **"+ Add product"**
4. Fyll i:
   - Name: "Beta Operator Access"
   - Pricing: One time, 100 SEK (eller valfritt)
5. Spara och kopiera **Price ID** (klicka på priset → `price_xxxxx`)

### Steg 3: Hämta API-nycklar

1. Gå till [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys)
2. Kopiera **Secret key** (`sk_live_...`)
3. Kopiera **Publishable key** (`pk_live_...`) - för frontend

### Steg 4: Konfigurera Webhook

1. Gå till [dashboard.stripe.com/webhooks](https://dashboard.stripe.com/webhooks)
2. Klicka **"Add endpoint"**
3. Endpoint URL: `https://agentfarm.se/webhook/stripe`
4. Events att lyssna på:
   - `checkout.session.completed` (krävs)
   - `customer.subscription.deleted` (valfritt)
5. Klicka **"Add endpoint"**
6. Kopiera **Signing secret** (`whsec_...`)

### Steg 5: Uppdatera .env

```bash
nano /home/albin/agentfarm/.env
```

```bash
STRIPE_SECRET_KEY=sk_live_YOUR_KEY
STRIPE_WEBHOOK_SECRET=whsec_YOUR_SECRET
STRIPE_PROMPT_PACK_PRICE_ID=price_YOUR_LIVE_PRICE_ID
STRIPE_BETA_OPERATOR_PRICE_ID=price_YOUR_LIVE_PRICE_ID
STRIPE_SUCCESS_URL=https://agentfarm.se/?payment=success
STRIPE_CANCEL_URL=https://agentfarm.se/?payment=cancelled
```

### Steg 6: Starta om Server

```bash
pkill -f "agentfarm.cli web"
cd /home/albin/agentfarm
nohup python -m agentfarm.cli web --host 0.0.0.0 --port 8080 > /tmp/agentfarm.log 2>&1 &
```

---

## SSL Krav

Stripe webhooks i live-läge **kräver HTTPS**. Se [SSL_SETUP.md](../docs/SSL_SETUP.md) för certbot-konfiguration.

Nuvarande setup:
- agentfarm.se → nginx (SSL) → localhost:8080
- Certifikat: Let's Encrypt via Certbot

---

## Testa Webhook

### Via Stripe CLI

```bash
# Installera
curl -s https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public | gpg --dearmor | sudo tee /usr/share/keyrings/stripe.gpg
echo "deb [signed-by=/usr/share/keyrings/stripe.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" | sudo tee /etc/apt/sources.list.d/stripe.list
sudo apt update && sudo apt install stripe

# Logga in
stripe login

# Testa webhook
stripe trigger checkout.session.completed
```

### Via Dashboard

1. Gå till webhook i Stripe Dashboard
2. Klicka "Send test webhook"
3. Välj "checkout.session.completed"
4. Kolla serverloggen

### Via curl

```bash
# Kolla att endpoint svarar (bör ge 405 Method Not Allowed)
curl -I https://agentfarm.se/webhook/stripe
```

---

## Debugging

```bash
# Serverlogg
tail -f /tmp/agentfarm.log | grep -i stripe

# Kolla Stripe config via API (kräver admin)
curl http://localhost:8080/api/stripe/debug -H "Cookie: device_id=ADMIN_DEVICE"
```

**Förväntad logg vid lyckad webhook:**
```
=== STRIPE WEBHOOK RECEIVED ===
Stripe webhook: event_type=checkout.session.completed
handle_webhook: Signature verification PASSED
SUCCESS: Upgraded user to Beta Operator
```

---

*Senast uppdaterad: 2026-01-22*
