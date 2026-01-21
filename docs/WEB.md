# AgentFarm Web Interface

> Se även: [INDEX.md](./INDEX.md) | [ARCHITECTURE.md](./ARCHITECTURE.md) | [MONETIZATION.md](./MONETIZATION.md)

## 🌐 Live URL

**Kundportal:** [http://taborsen.duckdns.org:8080/](http://taborsen.duckdns.org:8080/)

## Översikt

80s Sci-Fi themed web interface med real-time agent visualization.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         WEB PAGES                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  /              - Main Dashboard (robot visualization)                 │
│  /mobile (/m)   - Mobile UI (VPN-optimerad)                           │
│  /hardware      - Hardware Terminal (affiliate-länkar)                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Filstruktur

```
src/agentfarm/web/
├── server.py              # aiohttp app + handlers
├── templates/
│   ├── index.html         # Main dashboard
│   ├── mobile.html        # Mobile interface
│   └── hardware.html      # Hardware terminal (affiliate-länkar)
└── static/
    ├── css/
    │   └── retro.css      # 80s sci-fi styling
    └── js/
        ├── app.js         # Main application
        ├── robots.js      # Robot visualizer
        └── translations.js # i18n system (SV/EN)
```

## Server (`server.py`)

### Startup

```python
async def on_startup(app: web.Application) -> None:
    global llm_router, workflow_persistence, affiliate_manager
    global user_manager, feedback_manager, stripe_integration
    global gpu_monitor, performance_tracker

    setup_event_bus()

    # Initialize managers
    affiliate_manager = AffiliateManager(storage_dir)
    workflow_persistence = WorkflowPersistence(...)
    user_manager = UserManager(storage_dir)
    feedback_manager = FeedbackManager(storage_dir)
    stripe_integration = StripeIntegration()
    llm_router = LLMRouter(event_bus=event_bus)

    # Hardware monitoring
    gpu_monitor = GPUMonitor()
    performance_tracker = PerformanceTracker()

    # Subscribe PerformanceTracker to LLM events
    event_bus.subscribe(EventType.LLM_REQUEST, performance_tracker.on_llm_request)
    event_bus.subscribe(EventType.LLM_RESPONSE, performance_tracker.on_llm_response)
```

### WebSocket

```python
async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    ws_clients.add(ws)

    # Send welcome
    await ws.send_json({
        'type': 'connected',
        'providers': get_available_providers(),
    })

    # Handle messages
    async for msg in ws:
        await handle_ws_message(ws, msg.data)
```

### WebSocket Messages

**Client → Server:**

| Type | Data | Description |
|------|------|-------------|
| `execute` | `{task, provider, workdir}` | Start workflow |
| `create_project` | `{name, prompt}` | Create project + workflow |
| `ping` | - | Keepalive |
| `set_workdir` | `{workdir}` | Change working directory |

**Server → Client:**

| Type | Data | Description |
|------|------|-------------|
| `connected` | `{providers}` | Connection established |
| `workflow_start` | `{task, provider}` | Workflow began |
| `agent_message` | `{agent, content}` | Agent output |
| `stage_change` | `{stage, status}` | Workflow stage update |
| `step_start/complete` | `{step_id, success}` | Step lifecycle |
| `agent_collaboration` | `{initiator, participants, type}` | Collaboration event |
| `workflow_complete` | `{success, summary}` | Workflow finished |

## REST API Endpoints

### Core API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/providers` | GET | List available LLM providers |
| `/api/events` | GET | Event bus metrics + history |
| `/api/interrupt` | POST | Send interrupt signal |
| `/api/router` | GET | LLM router status |
| `/api/router/test` | POST | Test model |
| `/api/workflows` | GET | List workflows |
| `/api/workflows/{id}` | GET | Workflow details |
| `/api/workflows/{id}/pause` | POST | Pause workflow |
| `/api/launch` | POST | Open folder in file manager |

### File Browser API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/files` | GET | List files in directory |
| `/api/files/content` | GET | Get file content |
| `/api/files/download` | GET | Download file |

### Monetization API

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/user` | GET | - | Get user profile (inkl. is_beta_operator) |
| `/api/user/tryout` | POST | - | Starta tryout (1 gratis workflow) |
| `/api/user/context` | POST | Beta | Save company context |
| `/api/user/agent-prompts` | GET | - | Get custom agent prompts |
| `/api/user/agent-prompts` | POST | Beta | Set custom agent prompts |
| `/api/checkout/beta-operator` | POST | - | Create Stripe checkout (29 kr) |
| `/api/files/upload` | POST | Beta | Upload files to SecureVault |
| `/api/files/vault` | GET | - | List uploaded files |
| `/webhook/stripe` | POST | - | Stripe webhook handler |
| `/api/feedback` | POST | Beta | Submit feedback |
| `/api/feedback` | GET | Admin | List all feedback |
| `/api/monetization/stats` | GET | Admin | Admin statistics |

**Auth nivåer:**
- `-` = Alla användare
- `Beta` = Beta Operator krävs
- `Admin` = Admin krävs

### Affiliate API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/affiliates/products` | GET | List products |
| `/api/affiliates/categories` | GET | List categories |
| `/api/affiliates/{product}/click/{retailer}` | GET | Track + redirect |
| `/api/affiliates/stats` | GET | Click statistics |

### Infrastructure API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/wireguard/new-peer` | POST | Generate WireGuard peer |

### Hardware Monitoring API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/hardware` | GET | Combined hardware + performance stats |
| `/api/hardware/gpu` | GET | GPU stats (AMD rocm-smi / NVIDIA nvidia-smi) |
| `/api/hardware/performance` | GET | LLM performance metrics (tokens/sec, latency) |

**Example Response (`/api/hardware`):**

```json
{
  "gpu": {
    "available": true,
    "vendor": "AMD",
    "stats": {
      "gpu_temp": 65,
      "gpu_util": 75,
      "vram_used_mb": 4096,
      "vram_total_mb": 16384
    }
  },
  "performance": {
    "overall": {
      "total_requests": 150,
      "success_rate": 98.5,
      "avg_latency_ms": 850,
      "avg_tokens_per_second": 45.2
    },
    "by_model": {
      "qwen-coder": {
        "total_requests": 80,
        "tokens_per_second": 52.1,
        "latency_ms": {"avg": 720, "p50": 680, "p95": 1200}
      }
    },
    "by_agent": {
      "executor": {"total_requests": 45, "success_rate": 100}
    }
  }
}
```

**Example Response (`/api/hardware/performance`):**

```json
{
  "overall": {
    "total_requests": 150,
    "successful_requests": 148,
    "success_rate": 98.5,
    "avg_latency_ms": 850,
    "avg_tokens_per_second": 45.2,
    "active_requests": 2
  },
  "by_model": {
    "qwen-coder": {
      "model": "qwen-coder",
      "total_requests": 80,
      "success_rate": 100.0,
      "tokens": {"input": 50000, "output": 25000, "total": 75000},
      "latency_ms": {"avg": 720, "p50": 680, "p95": 1200, "p99": 1500},
      "tokens_per_second": 52.1
    }
  },
  "recent": [
    {
      "model": "qwen-coder",
      "agent": "executor",
      "task_type": "code_generation",
      "latency_ms": 650,
      "input_tokens": 500,
      "output_tokens": 250,
      "tokens_per_second": 55.3,
      "success": true
    }
  ]
}
```

## Robot Visualizer (`robots.js`)

### RobotVisualizer Class

```javascript
class RobotVisualizer {
    constructor(canvasId) {
        this.robots = {
            planner: new Robot('planner', 'blue', ...),
            executor: new Robot('executor', 'green', ...),
            verifier: new Robot('verifier', 'yellow', ...),
            reviewer: new Robot('reviewer', 'purple', ...),
            ux: new Robot('ux', 'red', ...),
        };
    }

    // Trigger robot animation
    activateRobot(name, message) { ... }

    // Show collaboration between robots
    showCollaboration(initiator, participants) { ... }
}
```

### Robot States

- **idle** - Wandering, thinking, scanning
- **active** - Walking animation, speech bubble
- **collaborating** - Gravitating toward other robots

### Idle Behaviors

```javascript
const IdleBehavior = {
    WANDER: 'wander',      // Random movement
    THINK: 'think',        // Thinking animation
    SCAN: 'scan',          // Looking around
    IDLE: 'idle',          // Standing still
};
```

## CSS Themes (`retro.css`)

### Color Variables

```css
:root {
    --bg: #0a0a12;
    --cyan: #00ffff;
    --magenta: #ff00ff;
    --yellow: #ffff00;
    --green: #00ff00;
    --red: #ff0000;
    --text: #e0e0e0;
    --text-dim: #808080;
    --border: #333344;
}
```

### Animations

- `glow` - Neon glow pulsing
- `scanline` - CRT scanline effect
- `flicker` - Text flickering
- `badge-glow` - Badge highlight

## Internationalization (i18n)

AgentFarm stöder svenska och engelska med flagg-toggle i header.

### translations.js

```javascript
const TRANSLATIONS = {
    sv: {
        "header.system": "SYSTEM",
        "input.placeholder": "Beskriv vad du vill skapa...",
        "beta.privacy_title": "INTEGRITET & DATASÄKERHET",
        // 100+ översättningar...
    },
    en: {
        "header.system": "SYSTEM",
        "input.placeholder": "Describe what you want to create...",
        "beta.privacy_title": "PRIVACY & DATA SECURITY",
        // 100+ translations...
    }
};

// API
window.i18n = {
    t,                    // Get translation: t('key')
    setLanguage,          // Switch language: setLanguage('en')
    applyTranslations,    // Re-apply all translations
    initLanguageToggle,   // Initialize toggle buttons
    getCurrentLanguage,   // Get current language
};
```

### HTML Attributes

```html
<!-- Text content -->
<span data-i18n="header.system">SYSTEM</span>

<!-- Placeholder -->
<input data-i18n-placeholder="input.placeholder" placeholder="...">

<!-- Title/tooltip -->
<button data-i18n-title="button.tooltip" title="...">
```

### Translation Keys

| Prefix | Beskrivning |
|--------|-------------|
| `header.*` | Header-element |
| `section.*` | Sektionsrubriker |
| `input.*` | Input-fält och hints |
| `stage.*` | Workflow-steg |
| `beta.*` | Beta Operator modal + privacy |
| `tryout.*` | Tryout modal |
| `feedback.*` | Feedback modal |
| `agents.*` | Agent-konfiguration |
| `hw.*` | Hardware-sidan |

### Language Toggle

```html
<div class="language-toggle">
    <button class="lang-btn" data-lang="sv" title="Svenska">
        <span class="flag">🇸🇪</span>
    </button>
    <button class="lang-btn" data-lang="en" title="English">
        <span class="flag">🇬🇧</span>
    </button>
</div>
```

Språkval sparas i `localStorage` under nyckeln `agentfarm_lang`.

## Running the Server

```bash
# Default
agentfarm web

# Custom port
agentfarm web --port 3000

# External access
agentfarm web --host 0.0.0.0

# With working directory
agentfarm web --workdir ~/projects
```

**URLs (Production):**
- Dashboard: `http://taborsen.duckdns.org:8080/`
- Mobile: `http://taborsen.duckdns.org:8080/mobile`
- Hardware: `http://taborsen.duckdns.org:8080/hardware`

**URLs (Local Development):**
- Dashboard: `http://localhost:8080/`
- Mobile: `http://localhost:8080/mobile`
- Hardware: `http://localhost:8080/hardware`
- VPN: `http://10.0.0.1:8080/mobile`

## Deployment (`deploy/`)

### Docker Compose

```yaml
# deploy/docker-compose.yml
services:
  agentfarm:
    build: ..
    ports:
      - "8080:8080"
    environment:
      - GROQ_API_KEY
      - STRIPE_SECRET_KEY

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d
      - ./certbot:/var/www/certbot

  certbot:
    image: certbot/certbot
```

### Nginx Config

```nginx
# deploy/nginx/conf.d/agentfarm.conf
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL
    ssl_certificate /etc/letsencrypt/live/.../fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/.../privkey.pem;

    # WebSocket
    location /ws {
        proxy_pass http://agentfarm:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # API
    location / {
        proxy_pass http://agentfarm:8080;
        limit_req zone=api burst=20;
    }
}
```

---

*Se även: [SECURITY.md](./SECURITY.md) för säkerhetskonfiguration*
