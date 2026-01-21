# AgentFarm Monetization

> Se även: [INDEX.md](./INDEX.md) | [ARCHITECTURE.md](./ARCHITECTURE.md) | [WEB.md](./WEB.md)

## 🌐 Live URL

**Publik portal:** [http://taborsen.duckdns.org:8080/](http://taborsen.duckdns.org:8080/)

## Pricing Model

AgentFarm använder ett tvåstegs-system: **Tryout** (gratis) och **Beta Operator** (betald).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRICING MODEL                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────┐    ┌─────────────────────────────┐   │
│  │   TRYOUT (Gratis)           │    │   BETA OPERATOR (29 kr)     │   │
│  ├─────────────────────────────┤    ├─────────────────────────────┤   │
│  │                             │    │                             │   │
│  │  • 1 gratis workflow        │    │  • 10 workflows             │   │
│  │  • Alla 6 agenter           │    │  • Alla 6 agenter           │   │
│  │  • Grundläggande access     │    │  • Filuppladdning           │   │
│  │                             │    │  • Custom system prompts    │   │
│  │  Ingen registrering krävs   │    │  • Feedback till utvecklare │   │
│  │  Device-baserad identitet   │    │  • VPN-access               │   │
│  │                             │    │  • ZIP-nedladdning          │   │
│  └─────────────────────────────┘    └─────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────┐    ┌─────────────────────────────┐   │
│  │   AFFILIATE REVENUE         │    │   ADMIN ACCESS              │   │
│  ├─────────────────────────────┤    ├─────────────────────────────┤   │
│  │                             │    │                             │   │
│  │  • /hardware sida           │    │  • Unlimited prompts (∞)    │   │
│  │  • GPU-prestanda stats      │    │  • Full access to all       │   │
│  │  • Affiliate-länkar         │    │    features                 │   │
│  │  • Amazon Associates (SE)   │    │  • Set via scripts/         │   │
│  │                             │    │    set_admin.py             │   │
│  └─────────────────────────────┘    └─────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Access Levels

| Feature | Gäst | Tryout | Beta Operator | Admin |
|---------|------|--------|---------------|-------|
| Visa sidan | ✅ | ✅ | ✅ | ✅ |
| Köra workflows | ❌ | 1 st | 10 st | ∞ |
| Filuppladdning | ❌ | ❌ | ✅ | ✅ |
| Custom prompts | ❌ | ❌ | ✅ | ✅ |
| Skicka feedback | ❌ | ❌ | ✅ | ✅ |
| VPN-access | ❌ | ✅ | ✅ | ✅ |
| ZIP-nedladdning | ❌ | ✅ | ✅ | ✅ |

## Subscription Tiers (Kod)

```python
class SubscriptionTier(str, Enum):
    FREE = "free"              # Gäst, ingen access
    TRYOUT = "tryout"          # Har testat (1 gratis workflow)
    BETA_OPERATOR = "beta_operator"  # Betalande (29 kr, 10 workflows)
    EARLY_ACCESS = "early_access"    # Legacy tier
    PRO = "pro"                # Framtida tier
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

## UserManager API

```python
from agentfarm.monetization import UserManager, SubscriptionTier

users = UserManager(storage_dir=".agentfarm")

# Hämta eller skapa användare
user = users.get_or_create_user(device_id)

# Kolla om användare är Beta Operator
if users.is_beta_operator(device_id):
    # Har access till premium-funktioner
    pass

# Uppgradera till Beta Operator (efter Stripe-betalning)
users.upgrade_to_beta_operator(device_id, stripe_customer_id)
# Ger automatiskt 10 workflows
```

## Stripe Integration

### Environment Variables

```bash
# Obligatoriska
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Beta Operator (29 kr, engångsbetalning)
STRIPE_BETA_OPERATOR_PRICE_ID=price_1SrD6WHKMZEfwz9FBZTwDejG

# URLs
STRIPE_SUCCESS_URL=http://taborsen.duckdns.org:8080/?payment=success
STRIPE_CANCEL_URL=http://taborsen.duckdns.org:8080/?payment=cancelled
```

### Checkout Flow

```
┌────────────┐    ┌─────────────────┐    ┌──────────────┐
│   Gäst     │───▶│  Tryout Modal   │───▶│  1 workflow  │
└────────────┘    └─────────────────┘    └──────────────┘
                           │
                           ▼
┌────────────┐    ┌─────────────────┐    ┌──────────────┐
│  Tryout    │───▶│ Beta Operator   │───▶│ Stripe       │
│  user      │    │ Modal (29 kr)   │    │ Checkout     │
└────────────┘    └─────────────────┘    └──────────────┘
                                                │
                                                ▼
                                         ┌──────────────┐
                                         │ Webhook:     │
                                         │ upgrade_     │
                                         │ beta_operator│
                                         └──────────────┘
```

### Privacy Disclaimer (Beta Operator Modal)

En expanderbar "Integritet & Datasäkerhet"-sektion visas i Beta Operator-modalen:

| Sektion | Innehåll |
|---------|----------|
| 🛡️ Air-gapped | Data lämnar aldrig lokal infrastruktur, bearbetas på AMD 7800 XT |
| 🔒 VPN | Punkt-till-punkt WireGuard-tunnel, ingen avlyssning möjlig |
| 📋 GDPR | Dataminimering, ingen träning på data, radering vid session-slut |
| 🏛️ NIS2 | Minskad tredjepartsrisk, underlättar compliance |

**Consent-text:**
> "Genom att genomföra betalningen godkänner du att din data hanteras enligt ovanstående säkerhetsprotokoll."

Translations finns för svenska (`beta.privacy_*`) och engelska.

### API Endpoints

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/user` | GET | Hämta användarprofil (inkl. is_beta_operator) |
| `/api/user/tryout` | POST | Starta tryout (1 gratis workflow) |
| `/api/checkout/beta-operator` | POST | Skapa Stripe checkout för Beta Operator |
| `/webhook/stripe` | POST | Stripe webhook handler |
| `/api/feedback` | POST | Skicka feedback (Beta Operator only) |
| `/api/user/agent-prompts` | POST | Sätt custom prompts (Beta Operator only) |
| `/api/files/upload` | POST | Ladda upp filer (Beta Operator only) |

### Webhook Events

| Event | Action | Resultat |
|-------|--------|----------|
| `checkout.session.completed` (beta_operator) | `upgrade_beta_operator` | Tier → BETA_OPERATOR, +10 workflows |
| `customer.subscription.deleted` | `downgrade_tier` | Tier → FREE |

## Affiliate System

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
```

### Konfigurerade retailers

| Retailer | Status | Affiliate Tag |
|----------|--------|---------------|
| Amazon.se | ✅ Aktiv | `tag=agentfarm-21` |

### affiliates.json

```json
{
  "retailers": {
    "amazon": {
      "name": "Amazon.se",
      "affiliate_param": "tag=agentfarm-21"
    }
  },
  "products": [
    {
      "id": "amd_7900xtx",
      "name": "AMD Radeon RX 7900 XTX",
      "category": "gpu",
      "badge": "RECOMMENDED",
      "links": {
        "amazon": "https://www.amazon.se/s?k=AMD+Radeon+RX+7900+XTX&tag=agentfarm-21"
      }
    }
    // ... 12 produkter (4 GPU, 4 CPU, 4 RAM)
  ]
}
```

### Hardware Page Features

- **My Stack** - Visar utvecklarens egen hårdvara (RX 7800 XT, Ryzen 9 7950X, 64GB DDR5)
- **Animerade visualiseringar** - GPU-fläktar snurrar, CPU-die pulsar, RAM-chips flimrar
- **i18n-support** - Svenska och engelska översättningar
- **Badge-typer**: RECOMMENDED, BEST VALUE, BUDGET, TOP PERFORMANCE, HIGH CAPACITY, EXTREME

## Feedback System (Beta Operator only)

```python
from agentfarm.monetization import FeedbackManager

feedback = FeedbackManager(storage_dir=".agentfarm")

# Endast Beta Operators kan skicka feedback
entry = feedback.create_feedback(
    device_id="user123",
    message="Feedback...",
    category="bug",  # bug, feature, ux, performance, general
    rating=4,
)
```

## Storage

```
.agentfarm/
├── users/                   # UserProfile JSON-filer
│   ├── device123.json
│   └── device456.json
├── tokens/
│   └── transactions.json    # Token/prompt transaktioner
├── feedback/                # Feedback entries
│   └── fb_abc123.json
├── affiliates.json          # Affiliate config
└── analytics/
    └── affiliate_clicks.json
```

## Säkerhet

| Resurs | Publik | Skydd |
|--------|--------|-------|
| Web UI (port 8080) | ✅ | Gäster kan se, premium bakom betalning |
| Ollama API (11434) | ❌ | Blockerad av brandvägg |
| VPN (51820) | ✅ | Kräver WireGuard-config |
| GitLab (443) | ✅ | Kräver inloggning |

---

*Se även: [SECURITY.md](./SECURITY.md) | [WEB.md](./WEB.md)*
