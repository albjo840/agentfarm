# AgentFarm Monetization

> Se även: [INDEX.md](./INDEX.md) | [ARCHITECTURE.md](./ARCHITECTURE.md) | [WEB.md](./WEB.md)

## Dual Revenue Model

AgentFarm har två intäktsströmmar som kompletterar varandra:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         REVENUE STREAMS                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────┐    ┌─────────────────────────────┐   │
│  │   BRANCH 1: AFFILIATES      │    │   BRANCH 2: EARLY ACCESS    │   │
│  │   (Hardware Revenue)        │    │   (Subscription Revenue)    │   │
│  ├─────────────────────────────┤    ├─────────────────────────────┤   │
│  │                             │    │                             │   │
│  │  Målgrupp:                  │    │  Målgrupp:                  │   │
│  │  • DIY-byggare              │    │  • Företag                  │   │
│  │  • Entusiaster              │    │  • Utvecklare               │   │
│  │  • Studenter                │    │  • Startups                 │   │
│  │                             │    │                             │   │
│  │  Erbjudande:                │    │  Erbjudande:                │   │
│  │  • /hardware sida           │    │  • Unlimited workflows      │   │
│  │  • GPU-prestanda stats      │    │  • Company context (Vault)  │   │
│  │  • Affiliate-länkar         │    │  • Fil-uppladdning          │   │
│  │                             │    │  • VPN-access               │   │
│  │  Revenue:                   │    │  Revenue:                   │   │
│  │  • Click-baserat            │    │  • Månadsprenumeration      │   │
│  │  • 1-5% per köp             │    │  • Token-packs (optional)   │   │
│  │                             │    │                             │   │
│  └─────────────────────────────┘    └─────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Modulstruktur

```
src/agentfarm/monetization/
├── __init__.py              # Exporterar alla klasser
├── tiers.py                 # TierManager (unified controller)
├── affiliates.py            # AffiliateManager, click tracking
├── stripe_integration.py    # StripeIntegration
├── users.py                 # UserManager, UserProfile
└── feedback.py              # FeedbackManager
```

## TierManager (Central koordinator)

```python
from agentfarm.monetization import TierManager, AccessLevel, TierLimits

tier_mgr = TierManager(storage_dir=".agentfarm")

# Kontrollera access
allowed, reason = tier_mgr.check_workflow_access(device_id)
# allowed=True, reason="free_tier" eller "early_access"
# allowed=False, reason="Daily limit reached (5 workflows/day)"

# Hämta tier-info
access, limits = tier_mgr.get_user_tier(device_id)
# access: AccessLevel.FREE eller AccessLevel.EARLY_ACCESS
# limits.workflows_per_day: 5 (free) eller -1 (unlimited)
# limits.can_upload_files: False (free) eller True (early_access)
# limits.max_context_chars: 0 (free) eller 50000 (early_access)
```

## Tier Limits

| Feature | FREE | EARLY_ACCESS |
|---------|------|--------------|
| Workflows/dag | 5 | Unlimited |
| Company context | Nej | 50,000 chars |
| Fil-uppladdning | Nej | Ja |
| Priority queue | Nej | Ja |
| VPN-access | Nej | Ja |

## 1. Affiliate System

### AffiliateManager

```python
from agentfarm.monetization import AffiliateManager

manager = AffiliateManager(storage_dir=".agentfarm")

# Hämta produkter
products = manager.get_products(category="gpu")

# Spåra klick
url, click = manager.track_click(
    product_id="amd_7900xtx",
    retailer_id="dustin",
    device_id=user_device_id,
)
# url = "https://www.dustin.se/product/123?ref=agentfarm"

# Statistik
stats = manager.get_click_stats(days=30)
# {"total_clicks": 142, "by_product": {...}, "by_retailer": {...}}
```

### Konfigurerade retailers

| Retailer | Affiliate-param | Status |
|----------|-----------------|--------|
| Dustin | `ref=agentfarm` | Aktiv |
| Komplett | `wt.mc_id=agentfarm` | Aktiv |
| Inet | `ref=agentfarm` | Aktiv |
| Electrokit | `ref=agentfarm` | Aktiv |
| Proshop | - | TODO |
| Amazon (Adtraction) | - | TODO |

### Produktkategorier

- `gpu` - Grafikkort (AMD ROCm-kompatibla)
- `sbc` - Single board computers (Raspberry Pi)
- `storage` - NVMe, RAM
- `networking` - Switchar, kablar

## 2. Stripe Early Access

### StripeIntegration

```python
from agentfarm.monetization import StripeIntegration

stripe = StripeIntegration()

if stripe.enabled:
    # Skapa checkout session
    session = await stripe.create_checkout_session(
        device_id="user123",
        product_type="early_access"
    )
    # Redirect user till session.url

    # Verifiera webhook
    result = await stripe.handle_webhook(payload, signature)
    # {"action": "upgrade_tier", "device_id": "...", "tier": "early_access"}
```

### Environment Variables

```bash
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_EARLY_ACCESS_PRICE_ID=price_...
STRIPE_SUCCESS_URL=https://domain.com/?payment=success
STRIPE_CANCEL_URL=https://domain.com/?payment=cancelled
```

### Webhook Events

| Event | Action |
|-------|--------|
| `checkout.session.completed` | `upgrade_tier` eller `add_tokens` |
| `customer.subscription.deleted` | `downgrade_tier` |
| `invoice.paid` | `subscription_renewed` |

## 3. User Management

### UserManager

```python
from agentfarm.monetization import UserManager, SubscriptionTier

users = UserManager(storage_dir=".agentfarm")

# Hämta eller skapa användare
user = users.get_or_create_user(device_id)
# user.tier: SubscriptionTier.FREE eller .EARLY_ACCESS
# user.tokens_remaining: int
# user.company_context: str | None

# Uppgradera tier
users.upgrade_tier(device_id, SubscriptionTier.EARLY_ACCESS)

# Sätt company context
users.set_company_context(device_id, "Vi är ett fintech-bolag som...")
```

### UserProfile (Pydantic model)

```python
class UserProfile(BaseModel):
    device_id: str
    tier: SubscriptionTier = SubscriptionTier.FREE
    tokens_remaining: int = 0
    tokens_used_total: int = 0
    company_context: str | None = None
    stripe_customer_id: str | None = None
    created_at: float
    last_active: float
```

## 4. Feedback System

### FeedbackManager

```python
from agentfarm.monetization import FeedbackManager

feedback = FeedbackManager(storage_dir=".agentfarm")

# Skapa feedback
entry = feedback.create_feedback(
    device_id="user123",
    message="Agenten fastnade i en loop",
    category="bug",
    workflow_id="abc123",
    rating=3,
)

# Lista feedback (admin)
entries = feedback.list_feedback(status="new", limit=100)
stats = feedback.get_stats()
```

### Feedback Categories

- `bug` - Buggar och fel
- `feature` - Feature requests
- `ux` - UX/UI feedback
- `performance` - Prestandaproblem
- `general` - Övrigt

## API Endpoints

Se [WEB.md](./WEB.md) för fullständig API-dokumentation.

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/user` | GET | Hämta användarprofil |
| `/api/user/context` | POST | Spara company context |
| `/api/tokens` | GET | Token-balans |
| `/api/subscription/checkout` | POST | Skapa Stripe checkout |
| `/webhook/stripe` | POST | Stripe webhook handler |
| `/api/feedback` | POST | Skicka feedback |
| `/api/affiliates/products` | GET | Lista produkter |
| `/api/affiliates/{id}/click/{retailer}` | GET | Track click + redirect |

## Storage

```
.agentfarm/
├── users.json              # UserManager data
├── affiliates.json         # AffiliateManager config
├── feedback/               # Feedback entries
│   ├── abc123.json
│   └── def456.json
└── analytics/
    └── affiliate_clicks.json
```

---

*Se även: [SECURITY.md](./SECURITY.md) för Secure Vault (company context storage)*
