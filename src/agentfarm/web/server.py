"""
AgentFarm Web Server - 80s Sci-Fi Neural Interface

Serves the retro dashboard and provides WebSocket connections
for real-time agent communication visualization.

Now powered by EventBus for decoupled pub/sub communication.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Import EventBus and persistence
from agentfarm.events import Event, EventBus, EventType, PriorityLevel, WorkflowPersistence

# Import LLM Router
from agentfarm.providers.router import LLMRouter, TaskType, get_task_type_for_agent

# Import Affiliate Manager
from agentfarm.monetization.affiliates import AffiliateManager

# Import Monitoring
from agentfarm.monitoring import GPUMonitor, PerformanceTracker

# Try to import aiohttp, fall back to basic HTTP server if not available
try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from http.server import HTTPServer, SimpleHTTPRequestHandler

from agentfarm.config import AgentFarmConfig, ProviderConfig, ProviderType

# Import monetization module
from agentfarm.monetization.users import UserManager, SubscriptionTier
from agentfarm.monetization.feedback import FeedbackManager, FeedbackEntry
from agentfarm.monetization.stripe_integration import StripeIntegration
from agentfarm.monetization.tiers import TierManager, TierLimits

# Optional: Import context injector for RAG indexing
try:
    from agentfarm.security.context_injector import ContextInjector
    CONTEXT_INJECTOR_AVAILABLE = True
except ImportError:
    CONTEXT_INJECTOR_AVAILABLE = False
    ContextInjector = None  # type: ignore


# Paths
WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"


class WebSocketClients:
    """Manage WebSocket client connections."""

    def __init__(self):
        self.clients: set[web.WebSocketResponse] = set()

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast message to all connected clients."""
        if not self.clients:
            logger.debug("No WebSocket clients connected, skipping broadcast")
            return

        data = json.dumps(message)
        dead_clients = set()

        logger.info("Broadcasting to %d clients: %s", len(self.clients), message.get('type', 'unknown'))

        for ws in self.clients:
            try:
                await ws.send_str(data)
            except Exception as e:
                logger.warning("Failed to send to client: %s", e)
                dead_clients.add(ws)

        self.clients -= dead_clients

    def add(self, ws: web.WebSocketResponse) -> None:
        self.clients.add(ws)
        logger.info("WebSocket client connected. Total clients: %d", len(self.clients))

    def remove(self, ws: web.WebSocketResponse) -> None:
        self.clients.discard(ws)


# Global state
ws_clients = WebSocketClients()
current_working_dir = "."
event_bus = EventBus(max_history=500)  # Global event bus
llm_router: LLMRouter | None = None  # Global LLM router
workflow_persistence: WorkflowPersistence | None = None  # Workflow state persistence
affiliate_manager: AffiliateManager | None = None  # Affiliate link manager
_event_bus_task: asyncio.Task | None = None  # Background task for event processing

# Monetization globals
user_manager: UserManager | None = None
feedback_manager: FeedbackManager | None = None
stripe_integration: StripeIntegration | None = None
tier_manager: TierManager | None = None
context_injector: ContextInjector | None = None

# Monitoring globals
gpu_monitor: GPUMonitor | None = None
performance_tracker: PerformanceTracker | None = None


async def _broadcast_event_handler(event: Event) -> None:
    """Handler that broadcasts all events to WebSocket clients.

    Flattens the event structure for frontend compatibility:
    - Converts type to lowercase (AGENT_MESSAGE -> agent_message)
    - Merges data fields to top level
    """
    # Flatten event for frontend
    flat_event = {
        "type": event.type.name.lower(),  # Frontend expects lowercase
        "source": event.source,
        **event.data,  # Merge data fields to top level
    }
    await ws_clients.broadcast(flat_event)


def setup_event_bus() -> None:
    """Set up event bus with WebSocket broadcasting."""
    global _event_bus_task

    # Subscribe WebSocket broadcaster to ALL events
    event_bus.subscribe_all(_broadcast_event_handler)

    # Start event bus processing loop
    _event_bus_task = asyncio.create_task(event_bus.run())
    logger.info("EventBus started with WebSocket broadcasting")


def create_provider(provider_type: str):
    """Create LLM provider from type string."""
    provider_type = provider_type.lower()

    if provider_type == "groq":
        from agentfarm.providers.groq import GroqProvider
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        return GroqProvider(
            model="llama-3.3-70b-versatile",
            api_key=api_key,
        )

    elif provider_type == "gemini":
        from agentfarm.providers.gemini import GeminiProvider
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY not set")
        return GeminiProvider(
            model="gemini-1.5-flash",
            api_key=api_key,
        )

    elif provider_type in ("qwen", "siliconflow"):
        from agentfarm.providers.siliconflow import SiliconFlowProvider
        api_key = os.getenv("SILICONFLOW_API_KEY")
        if not api_key:
            raise ValueError("SILICONFLOW_API_KEY not set")
        return SiliconFlowProvider(
            model="Qwen/Qwen2.5-7B-Instruct",
            api_key=api_key,
        )

    elif provider_type == "ollama":
        from agentfarm.providers.ollama import OllamaProvider
        return OllamaProvider(
            model=os.getenv("OLLAMA_MODEL", "llama3.2"),
            base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )

    elif provider_type == "claude":
        from agentfarm.providers.claude import ClaudeProvider
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ClaudeProvider(
            model="claude-sonnet-4-20250514",
            api_key=api_key,
        )

    else:
        raise ValueError(f"Unknown provider: {provider_type}")


def get_available_providers() -> list[dict[str, Any]]:
    """Get list of available providers based on env vars."""
    providers = []

    # Auto mode always available - uses multi-provider with fallback
    providers.append({"id": "auto", "name": "AUTO (Multi-provider)", "available": True})

    if os.getenv("GROQ_API_KEY"):
        providers.append({"id": "groq", "name": "GROQ (Llama)", "available": True})
    else:
        providers.append({"id": "groq", "name": "GROQ (Llama)", "available": False})

    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        providers.append({"id": "gemini", "name": "GEMINI (Google)", "available": True})
    else:
        providers.append({"id": "gemini", "name": "GEMINI (Google)", "available": False})

    if os.getenv("SILICONFLOW_API_KEY"):
        providers.append({"id": "qwen", "name": "QWEN (SiliconFlow)", "available": True})
    else:
        providers.append({"id": "qwen", "name": "QWEN (SiliconFlow)", "available": False})

    if os.getenv("ANTHROPIC_API_KEY"):
        providers.append({"id": "claude", "name": "CLAUDE (Anthropic)", "available": True})
    else:
        providers.append({"id": "claude", "name": "CLAUDE (Anthropic)", "available": False})

    # Ollama is always potentially available (local)
    providers.append({"id": "ollama", "name": "OLLAMA (Local)", "available": True})

    return providers


async def index_handler(request: web.Request) -> web.Response:
    """Serve the main dashboard."""
    index_path = TEMPLATES_DIR / "index.html"
    return web.FileResponse(index_path)


async def mobile_handler(request: web.Request) -> web.Response:
    """Serve the mobile interface."""
    mobile_path = TEMPLATES_DIR / "mobile.html"
    return web.FileResponse(mobile_path)


async def hardware_handler(request: web.Request) -> web.Response:
    """Serve the hardware terminal page."""
    hardware_path = TEMPLATES_DIR / "hardware.html"
    return web.FileResponse(hardware_path)


async def api_hardware_stats_handler(request: web.Request) -> web.Response:
    """Return real-time GPU stats."""
    if gpu_monitor is None:
        return web.json_response({"error": "GPU monitor not initialized"}, status=503)

    try:
        stats = await gpu_monitor.get_stats()
        perf_stats = performance_tracker.get_stats() if performance_tracker else {}

        return web.json_response({
            "gpu": stats.to_dict(),
            "performance": perf_stats,
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_hardware_gpu_handler(request: web.Request) -> web.Response:
    """Return GPU info only."""
    if gpu_monitor is None:
        return web.json_response({"available": False})

    try:
        stats = await gpu_monitor.get_stats()
        return web.json_response(stats.to_dict())
    except Exception as e:
        return web.json_response({"error": str(e), "available": False})


async def api_hardware_performance_handler(request: web.Request) -> web.Response:
    """Return LLM performance metrics."""
    if performance_tracker is None:
        return web.json_response({"error": "Performance tracker not initialized"}, status=503)

    return web.json_response(performance_tracker.get_stats())


async def api_affiliates_products_handler(request: web.Request) -> web.Response:
    """Return list of affiliate products."""
    if affiliate_manager is None:
        return web.json_response({"error": "Affiliate manager not initialized"}, status=503)

    category = request.query.get("category")
    products = affiliate_manager.get_products(category=category)

    return web.json_response([
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "category": p.category,
            "badge": p.badge,
            "image_url": p.image_url,
            "links": p.links,
        }
        for p in products
    ])


async def api_affiliates_categories_handler(request: web.Request) -> web.Response:
    """Return list of product categories."""
    if affiliate_manager is None:
        return web.json_response({"error": "Affiliate manager not initialized"}, status=503)

    categories = affiliate_manager.get_categories()
    return web.json_response(categories)


async def api_affiliates_click_handler(request: web.Request) -> web.Response:
    """Track affiliate click and redirect to retailer."""
    if affiliate_manager is None:
        return web.json_response({"error": "Affiliate manager not initialized"}, status=503)

    product_id = request.match_info["product_id"]
    retailer_id = request.match_info["retailer_id"]

    # Get tracking info from request
    device_id = request.cookies.get("device_id")
    referrer = request.headers.get("Referer")
    user_agent = request.headers.get("User-Agent")

    # Track the click and get redirect URL
    url, click = affiliate_manager.track_click(
        product_id=product_id,
        retailer_id=retailer_id,
        device_id=device_id,
        referrer=referrer,
        user_agent=user_agent,
    )

    if not url:
        return web.json_response({"error": "Product or retailer not found"}, status=404)

    # Redirect to affiliate URL
    raise web.HTTPFound(location=url)


async def api_affiliates_stats_handler(request: web.Request) -> web.Response:
    """Return affiliate click statistics."""
    if affiliate_manager is None:
        return web.json_response({"error": "Affiliate manager not initialized"}, status=503)

    days = int(request.query.get("days", "30"))
    stats = affiliate_manager.get_click_stats(days=days)

    return web.json_response(stats)


async def api_affiliates_prices_handler(request: web.Request) -> web.Response:
    """Return current price comparisons from scraped data.

    Uses Groq API for intelligent price extraction from retailer pages.
    """
    storage_dir = Path(".agentfarm")
    price_report_path = storage_dir / "price_report.json"

    if not price_report_path.exists():
        return web.json_response({
            "error": "No price data available. Run price scraper first.",
            "hint": "POST /api/affiliates/prices/scrape to update prices",
        }, status=404)

    try:
        report = json.loads(price_report_path.read_text())
        return web.json_response(report)
    except json.JSONDecodeError as e:
        return web.json_response({"error": f"Invalid price data: {e}"}, status=500)


async def api_affiliates_scrape_handler(request: web.Request) -> web.Response:
    """Trigger a price scrape using Groq API.

    This runs asynchronously and updates the price_report.json file.
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return web.json_response({
            "error": "GROQ_API_KEY not configured",
            "hint": "Set GROQ_API_KEY environment variable for price scraping",
        }, status=503)

    # Import here to avoid circular imports
    from agentfarm.monetization.price_scraper import AffiliatePriceScraper, ScraperConfig

    try:
        config = ScraperConfig(groq_api_key=groq_api_key)
        scraper = AffiliatePriceScraper(config=config)

        # Run scrape in background
        async def run_scrape():
            try:
                path = await scraper.run_and_save()
                logger.info("Price scrape completed: %s", path)
                # Broadcast update to connected clients
                await ws_clients.broadcast({
                    "type": "price_update",
                    "status": "complete",
                    "path": str(path),
                })
            except Exception as e:
                logger.error("Price scrape failed: %s", e)
                await ws_clients.broadcast({
                    "type": "price_update",
                    "status": "error",
                    "error": str(e),
                })
            finally:
                await scraper.close()

        asyncio.create_task(run_scrape())

        return web.json_response({
            "status": "started",
            "message": "Price scrape started in background",
        })

    except Exception as e:
        logger.error("Failed to start price scrape: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def api_affiliates_best_prices_handler(request: web.Request) -> web.Response:
    """Return best prices for each product.

    Filters to only show products with valid prices and in stock.
    """
    storage_dir = Path(".agentfarm")
    price_report_path = storage_dir / "price_report.json"

    if not price_report_path.exists():
        return web.json_response({"products": []})

    try:
        report = json.loads(price_report_path.read_text())

        best_prices = []
        for product in report.get("products", []):
            if product.get("best_price"):
                best_prices.append({
                    "id": product["id"],
                    "name": product["name"],
                    "category": product.get("category"),
                    "best_price": product["best_price"],
                    "best_retailer": product.get("best_retailer"),
                    "price_range": product.get("price_range"),
                })

        return web.json_response({
            "generated_at": report.get("generated_at"),
            "products": best_prices,
        })
    except json.JSONDecodeError as e:
        return web.json_response({"error": f"Invalid price data: {e}"}, status=500)


async def static_handler(request: web.Request) -> web.Response:
    """Serve static files."""
    path = request.match_info.get('path', '')
    file_path = STATIC_DIR / path

    if not file_path.exists() or not file_path.is_file():
        raise web.HTTPNotFound()

    return web.FileResponse(file_path)


async def api_providers_handler(request: web.Request) -> web.Response:
    """Return available providers."""
    return web.json_response(get_available_providers())


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections for real-time updates."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    ws_clients.add(ws)

    # Send welcome message with available providers
    await ws.send_json({
        'type': 'connected',
        'message': 'Neural interface connected',
        'providers': get_available_providers(),
        'working_dir': current_working_dir,
    })

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await handle_ws_message(ws, data)
            elif msg.type == web.WSMsgType.ERROR:
                break
    finally:
        ws_clients.remove(ws)

    return ws


async def handle_ws_message(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    """Handle incoming WebSocket messages."""
    global current_working_dir
    msg_type = data.get('type')

    if msg_type == 'execute':
        # Start a workflow execution
        task = data.get('task', '')
        provider = data.get('provider', 'auto')  # Default to auto (uses multi-provider/Ollama)
        workdir = data.get('workdir', current_working_dir)
        # Run in background so we don't block
        asyncio.create_task(run_real_workflow(task, provider, workdir))

    elif msg_type == 'create_project':
        # Create a new project and start workflow (multi-provider mode)
        name = data.get('name', 'nytt-projekt')
        prompt = data.get('prompt', '')
        # Run in background - multi-provider mode is automatic
        asyncio.create_task(create_and_run_project(name, prompt))

    elif msg_type == 'ping':
        await ws.send_json({'type': 'pong'})

    elif msg_type == 'set_workdir':
        current_working_dir = data.get('workdir', '.')
        await ws.send_json({'type': 'workdir_set', 'workdir': current_working_dir})


async def create_and_run_project(name: str, prompt: str) -> None:
    """Create a new project directory and run workflow in multi-provider mode."""
    import re

    logger.info("Creating project: %s with prompt: %s", name, prompt[:100])

    # Sanitize project name
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())
    safe_name = re.sub(r'-+', '-', safe_name).strip('-')
    if not safe_name:
        safe_name = 'nytt-projekt'

    # Create project in ~/nya projekt/
    projects_base = Path.home() / "nya projekt"
    projects_base.mkdir(exist_ok=True)
    logger.info("Projects base directory: %s", projects_base)

    project_path = projects_base / safe_name

    # Handle existing project names
    if project_path.exists():
        counter = 1
        while (projects_base / f"{safe_name}-{counter}").exists():
            counter += 1
        safe_name = f"{safe_name}-{counter}"
        project_path = projects_base / safe_name

    # Create project directory
    project_path.mkdir(parents=True)
    logger.info("Created project directory: %s", project_path)

    await ws_clients.broadcast({
        'type': 'project_created',
        'name': safe_name,
        'path': str(project_path),
    })

    # Run workflow in multi-provider mode
    await run_multi_provider_workflow(prompt, str(project_path))


async def run_multi_provider_workflow(task: str, working_dir: str) -> None:
    """Run AgentFarm workflow with multi-provider mode (each agent uses optimal provider)."""
    from agentfarm.orchestrator import Orchestrator
    from agentfarm.tools.file_tools import FileTools
    import uuid

    # Create correlation ID for this workflow
    correlation_id = str(uuid.uuid4())[:8]

    async def event_callback(event_name: str, data: dict[str, Any]) -> None:
        """Callback that emits events to the event bus."""
        # Handle stage_change specially - broadcast directly to WebSocket
        if event_name == 'stage_change':
            await ws_clients.broadcast({
                'type': 'stage_change',
                'stage': data.get('stage'),
                'status': data.get('status'),
            })
            return

        # Map old event names to EventType
        event_type_map = {
            'workflow_start': EventType.WORKFLOW_START,
            'workflow_complete': EventType.WORKFLOW_COMPLETE,
            'agent_message': EventType.AGENT_MESSAGE,
            'step_start': EventType.STEP_START,
            'step_complete': EventType.STEP_COMPLETE,
            'parallel_execution_start': EventType.STEP_START,
            'tokens_update': EventType.AGENT_MESSAGE,
        }
        event_type = event_type_map.get(event_name, EventType.AGENT_MESSAGE)
        source = data.get('agent', 'orchestrator')

        await event_bus.emit(Event(
            type=event_type,
            source=source,
            data=data,
            correlation_id=correlation_id,
        ))

    try:
        await event_bus.emit(Event(
            type=EventType.WORKFLOW_START,
            source="orchestrator",
            data={
                'task': task,
                'provider': 'multi-provider',
                'working_dir': working_dir,
            },
            correlation_id=correlation_id,
        ))

        # Create orchestrator in multi-provider mode (no single provider passed)
        orchestrator = Orchestrator(
            provider=None,  # Triggers multi-provider mode
            working_dir=working_dir,
            event_callback=event_callback,
            use_multi_provider=True,
        )

        # Set up collaboration event broadcasting
        setup_collaboration_events(orchestrator)

        # Inject file tools
        file_tools = FileTools(working_dir)
        orchestrator.inject_tools(file_tools=file_tools)

        # Run the workflow
        result = await orchestrator.run_workflow(task)

        # Send final result via event bus
        await event_bus.emit(Event(
            type=EventType.WORKFLOW_COMPLETE,
            source="orchestrator",
            data={
                'success': result.success,
                'summary': result.pr_summary,
                'tokens': orchestrator.get_total_tokens_used(),
            },
            correlation_id=correlation_id,
        ))

    except Exception as e:
        import traceback
        await event_bus.emit(Event(
            type=EventType.WORKFLOW_ERROR,
            source="orchestrator",
            data={
                'error': str(e),
                'traceback': traceback.format_exc(),
            },
            priority=PriorityLevel.HIGH,
            correlation_id=correlation_id,
        ))


async def run_real_workflow(task: str, provider_type: str, working_dir: str) -> None:
    """Run a real AgentFarm workflow and broadcast updates via event bus."""
    from agentfarm.orchestrator import Orchestrator
    from agentfarm.tools.file_tools import FileTools
    import uuid

    # Create correlation ID for this workflow
    correlation_id = str(uuid.uuid4())[:8]

    async def event_callback(event_name: str, data: dict[str, Any]) -> None:
        """Callback that emits events to the event bus."""
        # Handle stage_change specially - broadcast directly to WebSocket
        if event_name == 'stage_change':
            await ws_clients.broadcast({
                'type': 'stage_change',
                'stage': data.get('stage'),
                'status': data.get('status'),
            })
            return

        event_type_map = {
            'workflow_start': EventType.WORKFLOW_START,
            'workflow_complete': EventType.WORKFLOW_COMPLETE,
            'agent_message': EventType.AGENT_MESSAGE,
            'step_start': EventType.STEP_START,
            'step_complete': EventType.STEP_COMPLETE,
            'parallel_execution_start': EventType.STEP_START,
            'tokens_update': EventType.AGENT_MESSAGE,
        }
        event_type = event_type_map.get(event_name, EventType.AGENT_MESSAGE)
        source = data.get('agent', 'orchestrator')

        await event_bus.emit(Event(
            type=event_type,
            source=source,
            data=data,
            correlation_id=correlation_id,
        ))

    try:
        # Notify start via event bus
        await event_bus.emit(Event(
            type=EventType.WORKFLOW_START,
            source="orchestrator",
            data={
                'task': task,
                'provider': provider_type,
                'working_dir': working_dir,
            },
            correlation_id=correlation_id,
        ))

        # Create orchestrator - use multi-provider mode for "auto" or as fallback
        if provider_type == "auto":
            # Use multi-provider mode with automatic fallback
            orchestrator = Orchestrator(
                provider=None,
                working_dir=working_dir,
                event_callback=event_callback,
                use_multi_provider=True,
            )
        else:
            # Try specific provider, fall back to multi-provider if unavailable
            try:
                provider = create_provider(provider_type)
                orchestrator = Orchestrator(
                    provider=provider,
                    working_dir=working_dir,
                    event_callback=event_callback,
                    use_multi_provider=False,
                )
            except ValueError as e:
                # Fallback to multi-provider mode
                await ws_clients.broadcast({
                    'type': 'agent_message',
                    'agent': 'orchestrator',
                    'content': f"Provider {provider_type} unavailable, using auto-detect...",
                })
                orchestrator = Orchestrator(
                    provider=None,
                    working_dir=working_dir,
                    event_callback=event_callback,
                    use_multi_provider=True,
                )

        # Set up collaboration event broadcasting
        setup_collaboration_events(orchestrator)

        # Inject file tools
        file_tools = FileTools(working_dir)
        orchestrator.inject_tools(file_tools=file_tools)

        # Run the workflow
        result = await orchestrator.run_workflow(task)

        # Final result via event bus
        await event_bus.emit(Event(
            type=EventType.WORKFLOW_COMPLETE,
            source="orchestrator",
            data={
                'success': result.success,
                'summary': result.pr_summary,
                'tokens': result.total_tokens_used,
            },
            correlation_id=correlation_id,
        ))

    except Exception as e:
        import traceback
        await event_bus.emit(Event(
            type=EventType.WORKFLOW_ERROR,
            source="orchestrator",
            data={
                'error': str(e),
                'traceback': traceback.format_exc(),
            },
            priority=PriorityLevel.HIGH,
            correlation_id=correlation_id,
        ))


async def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Broadcast an event to all connected clients."""
    await ws_clients.broadcast({
        'type': event_type,
        **data,
    })


def setup_collaboration_events(orchestrator) -> None:
    """Set up collaboration event broadcasting to WebSocket clients.

    This connects the ProactiveCollaborator to the WebSocket so that
    collaboration events are visualized in the UI (robots moving together,
    speech bubbles showing discussion, etc.)
    """
    from agentfarm.agents.collaboration import ProactiveCollaboration

    async def on_collaboration(collab: ProactiveCollaboration) -> None:
        """Broadcast collaboration event to all clients."""
        await ws_clients.broadcast({
            'type': 'agent_collaboration',
            'initiator': collab.initiator,
            'participants': collab.participants,
            'collaboration_type': collab.collaboration_type.value,
            'topic': collab.topic[:100],  # Truncate for UI
        })

    # If orchestrator has a proactive collaborator, add listener
    if hasattr(orchestrator, 'proactive_collaborator') and orchestrator.proactive_collaborator:
        orchestrator.proactive_collaborator.add_listener(on_collaboration)

    # Also hook into the agents' proactive collaborators
    for agent_name, agent in getattr(orchestrator, '_agents', {}).items():
        if hasattr(agent, 'proactive_collaborator') and agent.proactive_collaborator:
            agent.proactive_collaborator.add_listener(on_collaboration)


async def api_events_handler(request: web.Request) -> web.Response:
    """Return event bus metrics and recent history."""
    limit = int(request.query.get('limit', '50'))
    event_type = request.query.get('type')

    filter_type = EventType[event_type] if event_type else None
    history = event_bus.get_history(event_type=filter_type, limit=limit)

    return web.json_response({
        'metrics': event_bus.get_metrics(),
        'history': [e.to_dict() for e in history],
    })


async def api_interrupt_handler(request: web.Request) -> web.Response:
    """Send an interrupt event (for mobile/remote control)."""
    data = await request.json()
    reason = data.get('reason', 'User interrupt')

    await event_bus.emit(Event(
        type=EventType.INTERRUPT,
        source="api",
        data={'reason': reason},
        priority=PriorityLevel.CRITICAL,
    ))

    return web.json_response({'status': 'interrupt_sent'})


async def api_router_handler(request: web.Request) -> web.Response:
    """Return LLM router status."""
    if llm_router is None:
        return web.json_response({"error": "Router not initialized"}, status=503)
    return web.json_response(llm_router.get_status())


async def api_router_test_handler(request: web.Request) -> web.Response:
    """Test a model via the router."""
    if llm_router is None:
        return web.json_response({"error": "Router not initialized"}, status=503)

    data = await request.json()
    prompt = data.get("prompt", "Say hello in one word.")
    task_type_str = data.get("task_type", "general")
    model = data.get("model")  # Optional: force specific model

    try:
        task_type = TaskType[task_type_str.upper()]
    except KeyError:
        task_type = TaskType.GENERAL

    try:
        response, used_model = await llm_router.complete(
            messages=[{"role": "user", "content": prompt}],
            task_type=task_type,
            preferred_model=model,
        )
        return web.json_response({
            "model_used": used_model,
            "response": response.get("message", {}).get("content", ""),
            "task_type": task_type.value,
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_workflows_handler(request: web.Request) -> web.Response:
    """List workflows with optional status filter."""
    if workflow_persistence is None:
        return web.json_response({"error": "Persistence not initialized"}, status=503)

    status = request.query.get("status")
    limit = int(request.query.get("limit", "50"))

    workflows = workflow_persistence.list_workflows(status=status, limit=limit)
    resumable = workflow_persistence.get_resumable_workflows()

    return web.json_response({
        "workflows": workflows,
        "resumable_count": len(resumable),
    })


async def api_workflow_detail_handler(request: web.Request) -> web.Response:
    """Get detailed workflow state."""
    if workflow_persistence is None:
        return web.json_response({"error": "Persistence not initialized"}, status=503)

    workflow_id = request.match_info["id"]
    state = workflow_persistence.load_workflow(workflow_id)

    if state is None:
        return web.json_response({"error": "Workflow not found"}, status=404)

    return web.json_response(state.to_dict())


async def api_workflow_pause_handler(request: web.Request) -> web.Response:
    """Pause a running workflow."""
    if workflow_persistence is None:
        return web.json_response({"error": "Persistence not initialized"}, status=503)

    workflow_id = request.match_info["id"]
    success = workflow_persistence.pause_workflow(workflow_id)

    if success:
        return web.json_response({"status": "paused", "id": workflow_id})
    return web.json_response({"error": "Could not pause workflow"}, status=400)


async def api_launch_handler(request: web.Request) -> web.Response:
    """Open a project folder in the system file manager (local only)."""
    import subprocess
    import sys

    data = await request.json()
    path = data.get("path", "")

    if not path:
        return web.json_response({"error": "No path provided"}, status=400)

    project_path = Path(path)
    if not project_path.exists():
        return web.json_response({"error": "Path does not exist"}, status=404)

    try:
        if sys.platform == "linux":
            subprocess.Popen(["xdg-open", str(project_path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(project_path)])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", str(project_path)])

        return web.json_response({"status": "launched", "path": str(project_path)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_files_list_handler(request: web.Request) -> web.Response:
    """List files in a directory for the web file browser."""
    import mimetypes

    path = request.query.get("path", "")

    if not path:
        # Default to projects directory
        path = str(Path.home() / "nya projekt")

    target_path = Path(path)

    # Security: Only allow access to projects directory and subdirectories
    projects_base = Path.home() / "nya projekt"
    try:
        target_path = target_path.resolve()
        if not str(target_path).startswith(str(projects_base.resolve())):
            return web.json_response({"error": "Access denied"}, status=403)
    except Exception:
        return web.json_response({"error": "Invalid path"}, status=400)

    if not target_path.exists():
        return web.json_response({"error": "Path does not exist"}, status=404)

    if not target_path.is_dir():
        return web.json_response({"error": "Not a directory"}, status=400)

    files = []
    for item in sorted(target_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        try:
            stat = item.stat()
            mime_type, _ = mimetypes.guess_type(str(item))
            files.append({
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
                "size": stat.st_size if not item.is_dir() else None,
                "modified": stat.st_mtime,
                "mime_type": mime_type,
            })
        except (PermissionError, OSError):
            continue

    # Check if we can go up
    can_go_up = target_path != projects_base.resolve()
    parent_path = str(target_path.parent) if can_go_up else None

    return web.json_response({
        "path": str(target_path),
        "files": files,
        "can_go_up": can_go_up,
        "parent_path": parent_path,
    })


async def api_files_content_handler(request: web.Request) -> web.Response:
    """Get file content for viewing in browser."""
    import mimetypes

    path = request.query.get("path", "")

    if not path:
        return web.json_response({"error": "No path provided"}, status=400)

    target_path = Path(path)

    # Security: Only allow access to projects directory
    projects_base = Path.home() / "nya projekt"
    try:
        target_path = target_path.resolve()
        if not str(target_path).startswith(str(projects_base.resolve())):
            return web.json_response({"error": "Access denied"}, status=403)
    except Exception:
        return web.json_response({"error": "Invalid path"}, status=400)

    if not target_path.exists():
        return web.json_response({"error": "File does not exist"}, status=404)

    if target_path.is_dir():
        return web.json_response({"error": "Cannot read directory"}, status=400)

    mime_type, _ = mimetypes.guess_type(str(target_path))

    # For text files, return content directly
    text_types = [
        'text/', 'application/json', 'application/javascript',
        'application/xml', 'application/x-python', 'application/x-sh',
    ]
    is_text = any(mime_type and mime_type.startswith(t) for t in text_types)

    # Also check common extensions
    text_extensions = {'.py', '.js', '.ts', '.html', '.css', '.json', '.md', '.txt',
                       '.yml', '.yaml', '.toml', '.ini', '.cfg', '.sh', '.bash',
                       '.sql', '.xml', '.svg', '.env', '.gitignore', '.dockerfile'}
    if target_path.suffix.lower() in text_extensions:
        is_text = True

    if is_text:
        try:
            content = target_path.read_text(encoding='utf-8', errors='replace')
            # Limit content size for browser
            if len(content) > 500000:
                content = content[:500000] + "\n\n... (file truncated, too large to display)"
            return web.json_response({
                "path": str(target_path),
                "name": target_path.name,
                "content": content,
                "mime_type": mime_type or "text/plain",
                "size": target_path.stat().st_size,
            })
        except Exception as e:
            return web.json_response({"error": f"Cannot read file: {e}"}, status=500)
    else:
        # For binary files, return info only
        return web.json_response({
            "path": str(target_path),
            "name": target_path.name,
            "content": None,
            "mime_type": mime_type or "application/octet-stream",
            "size": target_path.stat().st_size,
            "binary": True,
        })


async def api_files_download_handler(request: web.Request) -> web.Response:
    """Download a file."""
    path = request.query.get("path", "")

    if not path:
        return web.json_response({"error": "No path provided"}, status=400)

    target_path = Path(path)

    # Security: Only allow access to projects directory
    projects_base = Path.home() / "nya projekt"
    try:
        target_path = target_path.resolve()
        if not str(target_path).startswith(str(projects_base.resolve())):
            return web.json_response({"error": "Access denied"}, status=403)
    except Exception:
        return web.json_response({"error": "Invalid path"}, status=400)

    if not target_path.exists() or target_path.is_dir():
        return web.json_response({"error": "File not found"}, status=404)

    return web.FileResponse(
        target_path,
        headers={
            "Content-Disposition": f'attachment; filename="{target_path.name}"'
        }
    )


async def api_project_download_zip_handler(request: web.Request) -> web.Response:
    """Download entire project as ZIP file."""
    import zipfile
    import io

    path = request.query.get("path", "")

    if not path:
        return web.json_response({"error": "No path provided"}, status=400)

    project_path = Path(path)

    # Security: Only allow access to projects directory
    projects_base = Path.home() / "nya projekt"
    try:
        project_path = project_path.resolve()
        if not str(project_path).startswith(str(projects_base.resolve())):
            return web.json_response({"error": "Access denied"}, status=403)
    except Exception:
        return web.json_response({"error": "Invalid path"}, status=400)

    if not project_path.exists() or not project_path.is_dir():
        return web.json_response({"error": "Project not found"}, status=404)

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    project_name = project_path.name

    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in project_path.rglob('*'):
                if file_path.is_file():
                    # Skip hidden files and common excludes
                    if any(part.startswith('.') for part in file_path.parts):
                        continue
                    if '__pycache__' in str(file_path):
                        continue
                    if file_path.suffix in {'.pyc', '.pyo'}:
                        continue

                    # Add file to ZIP with relative path
                    arcname = str(file_path.relative_to(project_path))
                    zipf.write(file_path, arcname)

        zip_buffer.seek(0)
        zip_data = zip_buffer.read()

        logger.info("Created ZIP for project %s (%d bytes)", project_name, len(zip_data))

        return web.Response(
            body=zip_data,
            content_type='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{project_name}.zip"',
                'Content-Length': str(len(zip_data)),
            }
        )

    except Exception as e:
        logger.error("Failed to create ZIP: %s", e)
        return web.json_response({"error": f"Failed to create ZIP: {e}"}, status=500)


async def api_projects_list_handler(request: web.Request) -> web.Response:
    """List all projects with metadata."""
    projects_base = Path.home() / "nya projekt"

    if not projects_base.exists():
        return web.json_response({"projects": []})

    projects = []
    for project_dir in sorted(projects_base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if project_dir.is_dir() and not project_dir.name.startswith('.'):
            try:
                stat = project_dir.stat()
                # Count files
                file_count = sum(1 for _ in project_dir.rglob('*') if _.is_file())
                # Calculate total size
                total_size = sum(f.stat().st_size for f in project_dir.rglob('*') if f.is_file())

                projects.append({
                    "name": project_dir.name,
                    "path": str(project_dir),
                    "created": stat.st_ctime,
                    "modified": stat.st_mtime,
                    "file_count": file_count,
                    "total_size": total_size,
                })
            except (PermissionError, OSError):
                continue

    return web.json_response({
        "projects": projects[:50],  # Limit to 50 most recent
        "total": len(projects),
    })


# =============================================================================
# FILE UPLOAD (SecureVault) API HANDLERS
# =============================================================================

ALLOWED_FILE_EXTENSIONS = {'.txt', '.md', '.py', '.js', '.json', '.yaml', '.yml', '.csv', '.pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


async def extract_pdf_text(content: bytes) -> str:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader
        from io import BytesIO

        reader = PdfReader(BytesIO(content))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except ImportError:
        logger.warning("pypdf not installed, PDF text extraction unavailable")
        return ""
    except Exception as e:
        logger.error("PDF extraction failed: %s", e)
        return ""


async def api_files_upload_handler(request: web.Request) -> web.Response:
    """Upload file to SecureVault (Beta Operator only)."""
    if not user_manager:
        return web.json_response({"error": "User manager not initialized"}, status=503)

    device_id = _get_device_id(request)

    # Check if user is Beta Operator
    if not user_manager.is_beta_operator(device_id):
        return web.json_response({
            "error": "Filuppladdning kräver Beta Operator",
            "feature": "file_upload",
            "upgrade_url": "/api/checkout/beta-operator"
        }, status=403)

    # Get vault directory
    vault_dir = Path(current_working_dir) / ".agentfarm" / "vault" / device_id[:16]
    vault_dir.mkdir(parents=True, exist_ok=True)

    # Parse multipart upload
    reader = await request.multipart()
    field = await reader.next()

    if not field or field.name != 'file':
        return web.json_response({"error": "No file provided"}, status=400)

    filename = field.filename
    if not filename:
        return web.json_response({"error": "No filename"}, status=400)

    # Validate file extension
    ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_FILE_EXTENSIONS:
        return web.json_response({
            "error": f"Invalid file type. Allowed: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}"
        }, status=400)

    # Read file content with size limit
    content = b''
    while True:
        chunk = await field.read_chunk()
        if not chunk:
            break
        content += chunk
        if len(content) > MAX_FILE_SIZE:
            return web.json_response({
                "error": f"File too large. Maximum size: {MAX_FILE_SIZE // 1024 // 1024}MB"
            }, status=400)

    # Sanitize filename
    safe_filename = "".join(c for c in filename if c.isalnum() or c in '._-').strip()
    if not safe_filename:
        safe_filename = "uploaded_file" + ext

    # Save file to vault
    file_path = vault_dir / safe_filename
    file_path.write_bytes(content)

    logger.info("File uploaded: %s (%d bytes) by %s", safe_filename, len(content), device_id[:8])

    # Index for RAG if context injector is available
    indexed = False
    if context_injector and CONTEXT_INJECTOR_AVAILABLE:
        try:
            # Extract text for indexing
            if ext == '.pdf':
                text_content = await extract_pdf_text(content)
            else:
                text_content = content.decode('utf-8', errors='replace')

            if text_content:
                await context_injector.add_document(
                    filename=safe_filename,
                    content=text_content,
                    metadata={
                        "device_id": device_id[:8],
                        "uploaded": True,
                    }
                )
                indexed = True
                logger.info("File indexed for RAG: %s", safe_filename)
        except Exception as e:
            logger.warning("Failed to index file: %s", e)

    response = web.json_response({
        "status": "uploaded",
        "filename": safe_filename,
        "size": len(content),
        "indexed": indexed,
    })

    # Set device_id cookie if not present
    if "device_id" not in request.cookies:
        response.set_cookie("device_id", device_id, max_age=365*24*60*60, httponly=True)

    return response


async def api_files_vault_list_handler(request: web.Request) -> web.Response:
    """List files in user's vault."""
    if not tier_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    device_id = _get_device_id(request)
    _, limits = tier_manager.get_user_tier(device_id)

    # Even free users can see the list (empty), but upload is blocked
    vault_dir = Path(current_working_dir) / ".agentfarm" / "vault" / device_id[:16]

    files = []
    if vault_dir.exists():
        for item in sorted(vault_dir.iterdir(), key=lambda x: x.name.lower()):
            if item.is_file():
                try:
                    stat = item.stat()
                    files.append({
                        "name": item.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })
                except (PermissionError, OSError):
                    continue

    response = web.json_response({
        "files": files,
        "can_upload": limits.can_upload_files,
        "count": len(files),
    })

    # Set device_id cookie if not present
    if "device_id" not in request.cookies:
        response.set_cookie("device_id", device_id, max_age=365*24*60*60, httponly=True)

    return response


async def api_files_vault_delete_handler(request: web.Request) -> web.Response:
    """Delete a file from user's vault."""
    if not tier_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    device_id = _get_device_id(request)
    filename = request.match_info.get("filename", "")

    if not filename:
        return web.json_response({"error": "No filename provided"}, status=400)

    # Sanitize filename to prevent path traversal
    safe_filename = "".join(c for c in filename if c.isalnum() or c in '._-').strip()
    if not safe_filename or safe_filename != filename:
        return web.json_response({"error": "Invalid filename"}, status=400)

    vault_dir = Path(current_working_dir) / ".agentfarm" / "vault" / device_id[:16]
    file_path = vault_dir / safe_filename

    if not file_path.exists():
        return web.json_response({"error": "File not found"}, status=404)

    # Delete file
    try:
        file_path.unlink()
        logger.info("File deleted: %s by %s", safe_filename, device_id[:8])
    except Exception as e:
        return web.json_response({"error": f"Failed to delete: {e}"}, status=500)

    # Remove from RAG index if available
    if context_injector and CONTEXT_INJECTOR_AVAILABLE:
        try:
            await context_injector.delete_document(safe_filename)
        except Exception as e:
            logger.warning("Failed to remove from index: %s", e)

    return web.json_response({
        "status": "deleted",
        "filename": safe_filename,
    })


async def api_wireguard_qr_handler(request: web.Request) -> web.Response:
    """Generate a new WireGuard peer and return QR code. Requires tryout registration."""
    import subprocess
    import re

    # Check if user has access (tryout or paid)
    if user_manager:
        device_id = _get_device_id(request)
        user = user_manager.get_or_create_user(device_id)
        has_access = (
            user.is_admin or
            user.tier == SubscriptionTier.EARLY_ACCESS or
            user.prompts_remaining > 0
        )
        if not has_access:
            return web.json_response({
                "error": "VPN-access kräver att du startar en tryout först",
                "require_tryout": True
            }, status=403)

    try:
        # Get server public key
        result = subprocess.run(
            ["sudo", "wg", "show", "wg0", "public-key"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return web.json_response({"error": "WireGuard not running"}, status=500)
        server_pubkey = result.stdout.strip()

        # Get existing peers to find next IP
        result = subprocess.run(
            ["sudo", "wg", "show", "wg0", "allowed-ips"],
            capture_output=True, text=True, timeout=5
        )
        existing_ips = re.findall(r'10\.0\.0\.(\d+)', result.stdout)
        existing_nums = [int(ip) for ip in existing_ips]
        next_num = max(existing_nums + [2]) + 1  # Start from 3 if only server (1) and first peer (2)

        if next_num > 254:
            return web.json_response({"error": "No more IPs available"}, status=400)

        # Generate new key pair
        result = subprocess.run(["wg", "genkey"], capture_output=True, text=True, timeout=5)
        private_key = result.stdout.strip()

        result = subprocess.run(
            ["wg", "pubkey"],
            input=private_key, capture_output=True, text=True, timeout=5
        )
        public_key = result.stdout.strip()

        # Get endpoint (DuckDNS or public IP)
        endpoint = "taborsen.duckdns.org:51820"

        # Create client config
        client_config = f"""[Interface]
PrivateKey = {private_key}
Address = 10.0.0.{next_num}/24
DNS = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey = {server_pubkey}
Endpoint = {endpoint}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25"""

        # Add peer to WireGuard
        subprocess.run(
            ["sudo", "wg", "set", "wg0", "peer", public_key, "allowed-ips", f"10.0.0.{next_num}/32"],
            capture_output=True, timeout=5
        )

        # Save to config file
        peer_config = f"\n[Peer]\nPublicKey = {public_key}\nAllowedIPs = 10.0.0.{next_num}/32\n"
        subprocess.run(
            ["sudo", "tee", "-a", "/etc/wireguard/wg0.conf"],
            input=peer_config, capture_output=True, text=True, timeout=5
        )

        # Generate QR code as text (ANSI)
        result = subprocess.run(
            ["qrencode", "-t", "UTF8"],
            input=client_config, capture_output=True, text=True, timeout=5
        )
        qr_text = result.stdout

        return web.json_response({
            "success": True,
            "ip": f"10.0.0.{next_num}",
            "qr_text": qr_text,
            "config": client_config,
        })

    except subprocess.TimeoutExpired:
        return web.json_response({"error": "Command timed out"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# =============================================================================
# MONETIZATION API HANDLERS
# =============================================================================

def _get_device_id(request: web.Request) -> str:
    """Extract device ID from cookie or create new one."""
    device_id = request.cookies.get("device_id")
    if not device_id:
        import uuid
        device_id = str(uuid.uuid4())
    return device_id


async def api_user_handler(request: web.Request) -> web.Response:
    """Get current user profile."""
    if not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    device_id = _get_device_id(request)
    user = user_manager.get_or_create_user(device_id)

    # Check if user can run workflows
    can_run, reason = user_manager.can_run_workflow(device_id)

    # Determine if user is in tryout mode
    is_tryout = user.prompts_remaining > 0 and not user.is_admin and user.tier != SubscriptionTier.EARLY_ACCESS

    # Check Beta Operator status
    is_beta = user.is_admin or user.tier in (
        SubscriptionTier.BETA_OPERATOR,
        SubscriptionTier.EARLY_ACCESS,
        SubscriptionTier.PRO
    )

    response = web.json_response({
        "device_id": user.device_id,
        "tier": user.tier.value,
        "is_admin": user.is_admin,
        "is_beta_operator": is_beta,
        "is_tryout": is_tryout,
        "prompts_remaining": user.prompts_remaining if not (user.is_admin or user.tier == SubscriptionTier.EARLY_ACCESS) else -1,
        "tryout_remaining": user.prompts_remaining if is_tryout else None,
        "prompts_used_total": user.prompts_used_total,
        "can_run_workflow": can_run,
        "access_reason": reason,
        "tokens_remaining": user.tokens_remaining,  # Legacy
        "tokens_used_total": user.tokens_used_total,  # Legacy
        "has_company_context": bool(user.company_context),
        "has_custom_prompts": bool(user.agent_custom_prompts),
        "agent_custom_prompts": user.agent_custom_prompts or {},
        "stripe_enabled": stripe_integration.enabled if stripe_integration else False,
        # Beta Operator exclusive features
        "can_upload_files": is_beta,
        "can_customize_prompts": is_beta,
        "can_send_feedback": is_beta,
    })

    # Set device_id cookie if not present
    if "device_id" not in request.cookies:
        response.set_cookie("device_id", device_id, max_age=365*24*60*60, httponly=True)

    return response


async def api_user_tryout_handler(request: web.Request) -> web.Response:
    """Register user for tryout - gives 3 free workflows."""
    if not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    device_id = _get_device_id(request)
    user = user_manager.get_or_create_user(device_id)

    # Check if already registered for tryout
    if user.is_admin or user.tier == SubscriptionTier.EARLY_ACCESS:
        return web.json_response({
            "status": "already_premium",
            "message": "Du har redan full tillgång",
            "user": _user_to_dict(user, is_tryout=True)
        })

    # Register for tryout - give 1 free workflow
    TRYOUT_PROMPTS = 1
    if user.prompts_remaining < TRYOUT_PROMPTS:
        user.prompts_remaining = TRYOUT_PROMPTS
        user_manager._save_user(user)

    response = web.json_response({
        "status": "success",
        "message": f"Välkommen! Du har nu {TRYOUT_PROMPTS} gratis workflows.",
        "user": _user_to_dict(user, is_tryout=True)
    })

    # Set device_id cookie
    if "device_id" not in request.cookies:
        response.set_cookie("device_id", device_id, max_age=365*24*60*60, httponly=True)

    return response


def _user_to_dict(user, is_tryout: bool = False) -> dict:
    """Convert User to dict for API response."""
    # Beta Operator check: paid tier with premium features
    is_beta = user.is_admin or user.tier in (
        SubscriptionTier.BETA_OPERATOR,
        SubscriptionTier.EARLY_ACCESS,
        SubscriptionTier.PRO
    )
    return {
        "device_id": user.device_id,
        "tier": user.tier.value,
        "is_admin": user.is_admin,
        "is_beta_operator": is_beta,
        "is_tryout": is_tryout or user.prompts_remaining > 0,
        "prompts_remaining": user.prompts_remaining if not (user.is_admin or user.tier == SubscriptionTier.EARLY_ACCESS) else -1,
        "tryout_remaining": user.prompts_remaining if is_tryout else None,
        "prompts_used_total": user.prompts_used_total,
        # Premium features (Beta Operator only)
        "can_upload_files": is_beta,
        "can_customize_prompts": is_beta,
        "can_send_feedback": is_beta,
    }


async def api_user_context_handler(request: web.Request) -> web.Response:
    """Save company context for the user."""
    if not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    device_id = _get_device_id(request)
    data = await request.json()
    context = data.get("context", "")

    if len(context) > 50000:
        return web.json_response({"error": "Context too long (max 50000 chars)"}, status=400)

    user_manager.set_company_context(device_id, context)
    return web.json_response({"status": "saved", "length": len(context)})


async def api_tokens_handler(request: web.Request) -> web.Response:
    """Get token balance for current user."""
    if not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    device_id = _get_device_id(request)
    user = user_manager.get_or_create_user(device_id)

    return web.json_response({
        "tokens_remaining": user.tokens_remaining,
        "tokens_used_total": user.tokens_used_total,
        "prompts_remaining": user.prompts_remaining,
        "prompts_used_total": user.prompts_used_total,
        "tier": user.tier.value,
        "unlimited": user.is_admin or user.tier == SubscriptionTier.EARLY_ACCESS,
    })


# =============================================================================
# CUSTOM AGENT PROMPTS API
# =============================================================================

async def api_agent_prompts_get_handler(request: web.Request) -> web.Response:
    """Get custom prompts for all agents."""
    if not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    device_id = _get_device_id(request)
    prompts = user_manager.get_all_agent_custom_prompts(device_id)

    return web.json_response({
        "prompts": prompts,
        "agents": ["planner", "executor", "verifier", "reviewer", "ux"],
    })


async def api_agent_prompts_set_handler(request: web.Request) -> web.Response:
    """Set custom prompt for an agent. Requires Beta Operator."""
    if not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    device_id = _get_device_id(request)

    # Check if user is Beta Operator
    if not user_manager.is_beta_operator(device_id):
        return web.json_response({
            "error": "Anpassade systemprompter kräver Beta Operator",
            "feature": "custom_prompts",
            "upgrade_url": "/api/checkout/beta-operator"
        }, status=403)

    data = await request.json()
    agent_id = data.get("agent_id", "")
    custom_text = data.get("custom_text", "")

    # Validate agent_id
    valid_agents = ["planner", "executor", "verifier", "reviewer", "ux"]
    if agent_id not in valid_agents:
        return web.json_response({
            "error": f"Invalid agent_id. Must be one of: {valid_agents}",
        }, status=400)

    # Validate length
    if len(custom_text) > 2000:
        return web.json_response({
            "error": "Custom prompt too long (max 2000 chars)",
        }, status=400)

    if custom_text.strip():
        user_manager.set_agent_custom_prompt(device_id, agent_id, custom_text)
        logger.info("Set custom prompt for %s agent by user %s", agent_id, device_id[:8])
    else:
        user_manager.clear_agent_custom_prompt(device_id, agent_id)
        logger.info("Cleared custom prompt for %s agent by user %s", agent_id, device_id[:8])

    return web.json_response({
        "status": "saved",
        "agent_id": agent_id,
        "length": len(custom_text),
    })


# =============================================================================
# ADMIN API
# =============================================================================

async def api_admin_set_admin_handler(request: web.Request) -> web.Response:
    """Set admin status for a user. Only admins can do this."""
    if not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    # Check if requester is admin
    requester_device_id = _get_device_id(request)
    if not user_manager.is_admin(requester_device_id):
        return web.json_response({"error": "Admin access required"}, status=403)

    data = await request.json()
    target_device_id = data.get("device_id", "")
    is_admin = data.get("is_admin", True)

    if not target_device_id:
        return web.json_response({"error": "device_id required"}, status=400)

    user = user_manager.set_admin(target_device_id, is_admin)
    logger.info("Admin %s set admin=%s for user %s", requester_device_id[:8], is_admin, target_device_id[:8])

    return web.json_response({
        "status": "updated",
        "device_id": target_device_id,
        "is_admin": user.is_admin,
    })


async def api_admin_add_prompts_handler(request: web.Request) -> web.Response:
    """Add prompts to a user. Admin only."""
    if not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    # Check if requester is admin
    requester_device_id = _get_device_id(request)
    if not user_manager.is_admin(requester_device_id):
        return web.json_response({"error": "Admin access required"}, status=403)

    data = await request.json()
    target_device_id = data.get("device_id", "")
    amount = data.get("amount", 10)

    if not target_device_id:
        return web.json_response({"error": "device_id required"}, status=400)

    new_balance = user_manager.add_prompts(target_device_id, amount, "admin_grant")
    logger.info("Admin %s added %d prompts to user %s", requester_device_id[:8], amount, target_device_id[:8])

    return web.json_response({
        "status": "added",
        "device_id": target_device_id,
        "amount": amount,
        "new_balance": new_balance,
    })


async def api_subscription_checkout_handler(request: web.Request) -> web.Response:
    """Create Stripe checkout session for prompt pack purchase."""
    if not stripe_integration or not stripe_integration.enabled:
        return web.json_response({"error": "Stripe not configured"}, status=503)

    device_id = _get_device_id(request)
    data = await request.json()
    product_type = data.get("product_type", "prompt_pack")  # Default to prompt pack

    session = await stripe_integration.create_checkout_session(device_id, product_type)
    if session:
        return web.json_response({
            "checkout_url": session.url,
            "session_id": session.id,
        })
    else:
        # Fallback to simple URL
        url = stripe_integration.create_checkout_url(device_id, product_type)
        return web.json_response({"checkout_url": url})


async def api_beta_operator_checkout_handler(request: web.Request) -> web.Response:
    """Create Stripe checkout session for Beta Operator upgrade.

    Beta Operator includes:
    - 10 workflows
    - File upload (SecureVault)
    - Custom system prompts
    - Direct feedback to developer
    """
    if not stripe_integration or not stripe_integration.enabled:
        return web.json_response({"error": "Stripe not configured"}, status=503)

    device_id = _get_device_id(request)

    # Check if already Beta Operator
    if user_manager and user_manager.is_beta_operator(device_id):
        return web.json_response({
            "error": "Du är redan Beta Operator",
            "already_upgraded": True,
        }, status=400)

    session = await stripe_integration.create_checkout_session(device_id, "beta_operator")
    if session:
        return web.json_response({
            "checkout_url": session.url,
            "session_id": session.id,
            "product": {
                "name": "Beta Operator",
                "description": "10 workflows + premium features",
                "features": [
                    "10 AI-drivna workflows",
                    "Filuppladdning (SecureVault)",
                    "Anpassade systemprompter",
                    "Direkt feedback till utvecklaren",
                ],
            },
        })
    else:
        # Fallback to simple URL
        url = stripe_integration.create_checkout_url(device_id, "beta_operator")
        return web.json_response({"checkout_url": url})


async def api_stripe_webhook_handler(request: web.Request) -> web.Response:
    """Handle Stripe webhook events."""
    if not stripe_integration or not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    payload = await request.read()
    signature = request.headers.get("Stripe-Signature", "")

    result = await stripe_integration.handle_webhook(payload, signature)
    action = result.get("action", "")

    logger.info("Stripe webhook action: %s", action)

    # Process the action
    if action == "upgrade_tier":
        device_id = result.get("device_id", "")
        tier_str = result.get("tier", "early_access")
        tier = SubscriptionTier.EARLY_ACCESS if tier_str == "early_access" else SubscriptionTier.FREE
        customer_id = result.get("stripe_customer_id")
        if device_id:
            user_manager.upgrade_tier(device_id, tier, customer_id)
            logger.info("Upgraded user %s to %s", device_id[:8], tier.value)

    elif action == "upgrade_beta_operator":
        device_id = result.get("device_id", "")
        customer_id = result.get("stripe_customer_id")
        if device_id:
            user_manager.upgrade_to_beta_operator(device_id, customer_id)
            logger.info("Upgraded user %s to Beta Operator", device_id[:8])

    elif action == "add_prompts":
        device_id = result.get("device_id", "")
        prompts = result.get("prompts", 0)
        if device_id and prompts:
            user_manager.add_prompts(device_id, prompts, f"purchase_{result.get('product_type', 'unknown')}")
            logger.info("Added %d prompts to user %s", prompts, device_id[:8])

    elif action == "add_tokens":
        device_id = result.get("device_id", "")
        tokens = result.get("tokens", 0)
        if device_id and tokens:
            user_manager.update_tokens(device_id, tokens, f"purchase_{result.get('product_type', 'unknown')}")
            logger.info("Added %d tokens to user %s", tokens, device_id[:8])

    elif action == "downgrade_tier":
        device_id = result.get("device_id", "")
        if device_id:
            user_manager.upgrade_tier(device_id, SubscriptionTier.FREE)
            logger.info("Downgraded user %s to free", device_id[:8])

    elif action == "subscription_renewed":
        # Find user by stripe customer ID and refresh tokens
        customer_id = result.get("stripe_customer_id", "")
        if customer_id:
            # Would need to look up user by customer ID
            logger.info("Subscription renewed for customer %s", customer_id[:8])

    elif action == "invalid_signature":
        return web.json_response({"error": "Invalid signature"}, status=400)

    return web.json_response({"received": True, "action": action})


async def api_feedback_handler(request: web.Request) -> web.Response:
    """Submit user feedback. Requires Beta Operator."""
    if not feedback_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    device_id = _get_device_id(request)

    # Check if user is Beta Operator
    if user_manager and not user_manager.is_beta_operator(device_id):
        return web.json_response({
            "error": "Feedback kräver Beta Operator",
            "feature": "feedback",
            "upgrade_url": "/api/checkout/beta-operator"
        }, status=403)

    data = await request.json()

    message = data.get("message", "").strip()
    if not message:
        return web.json_response({"error": "Message required"}, status=400)
    if len(message) > 10000:
        return web.json_response({"error": "Message too long"}, status=400)

    feedback = feedback_manager.create_feedback(
        device_id=device_id,
        message=message,
        category=data.get("category", "general"),
        workflow_id=data.get("workflow_id"),
        contact_email=data.get("email"),
        user_agent=request.headers.get("User-Agent"),
        rating=data.get("rating"),
    )

    logger.info("Feedback received: %s from %s", feedback.id, device_id[:8])
    return web.json_response({"status": "submitted", "id": feedback.id})


async def api_feedback_list_handler(request: web.Request) -> web.Response:
    """List feedback (admin endpoint)."""
    if not feedback_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    # Simple admin check via query param (should use proper auth in production)
    if request.query.get("admin_key") != os.getenv("AGENTFARM_ADMIN_KEY", ""):
        return web.json_response({"error": "Unauthorized"}, status=401)

    status = request.query.get("status")
    category = request.query.get("category")
    limit = int(request.query.get("limit", "100"))

    entries = feedback_manager.list_feedback(status=status, category=category, limit=limit)
    stats = feedback_manager.get_stats()

    return web.json_response({
        "feedback": [e.model_dump() for e in entries],
        "stats": stats,
    })


async def api_monetization_stats_handler(request: web.Request) -> web.Response:
    """Get monetization stats (admin endpoint)."""
    if not user_manager:
        return web.json_response({"error": "Not initialized"}, status=503)

    # Simple admin check
    if request.query.get("admin_key") != os.getenv("AGENTFARM_ADMIN_KEY", ""):
        return web.json_response({"error": "Unauthorized"}, status=401)

    user_stats = user_manager.get_stats()
    feedback_stats = feedback_manager.get_stats() if feedback_manager else {}

    return web.json_response({
        "users": user_stats,
        "feedback": feedback_stats,
        "stripe_enabled": stripe_integration.enabled if stripe_integration else False,
    })


async def on_startup(app: web.Application) -> None:
    """Called when app starts - set up event bus, router, and persistence."""
    global llm_router, workflow_persistence, affiliate_manager, user_manager, feedback_manager, stripe_integration
    global gpu_monitor, performance_tracker, tier_manager, context_injector

    setup_event_bus()

    # Initialize hardware monitoring
    gpu_monitor = GPUMonitor()
    performance_tracker = PerformanceTracker()

    # Subscribe PerformanceTracker to LLM events
    from agentfarm.events import EventType
    event_bus.subscribe(EventType.LLM_REQUEST, performance_tracker.on_llm_request)
    event_bus.subscribe(EventType.LLM_RESPONSE, performance_tracker.on_llm_response)

    logger.info("Hardware monitoring initialized (GPU available: %s)", gpu_monitor.is_available)

    # Initialize affiliate manager
    storage_dir = Path(current_working_dir) / ".agentfarm"
    affiliate_manager = AffiliateManager(storage_dir=storage_dir)
    logger.info("Affiliate manager initialized")

    # Initialize workflow persistence
    workflow_persistence = WorkflowPersistence(
        storage_dir=Path(current_working_dir) / ".agentfarm" / "workflows"
    )
    workflow_persistence.connect(event_bus)
    logger.info("Workflow persistence initialized")

    # Initialize monetization
    agentfarm_dir = Path(current_working_dir) / ".agentfarm"
    user_manager = UserManager(agentfarm_dir)
    feedback_manager = FeedbackManager(agentfarm_dir)
    stripe_integration = StripeIntegration()
    logger.info("Monetization initialized (Stripe enabled: %s)", stripe_integration.enabled)

    # Initialize TierManager (unified access control)
    tier_manager = TierManager(storage_dir=agentfarm_dir, enable_vault=False)  # Using file-based vault
    logger.info("Tier manager initialized")

    # Initialize ContextInjector for RAG indexing (if available)
    if CONTEXT_INJECTOR_AVAILABLE:
        try:
            context_injector = ContextInjector(storage_path=agentfarm_dir / "context")
            logger.info("Context injector initialized (RAG available: %s)", context_injector.is_available)
        except Exception as e:
            logger.warning("Failed to initialize context injector: %s", e)
            context_injector = None
    else:
        context_injector = None
        logger.info("Context injector not available (optional dependencies not installed)")

    # Initialize LLM router with event bus integration
    llm_router = LLMRouter(event_bus=event_bus)
    availability = await llm_router.initialize()

    available_count = sum(1 for v in availability.values() if v)
    logger.info(
        "LLM Router initialized: %d/%d models available",
        available_count,
        len(availability),
    )


async def on_cleanup(app: web.Application) -> None:
    """Called when app shuts down - stop event bus, router, and persistence."""
    if workflow_persistence:
        workflow_persistence.stop()
    event_bus.stop()
    if _event_bus_task:
        _event_bus_task.cancel()
    if llm_router:
        await llm_router.close()


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()

    # Lifecycle hooks
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Routes
    app.router.add_get('/', index_handler)
    app.router.add_get('/mobile', mobile_handler)
    app.router.add_get('/m', mobile_handler)  # Short alias
    app.router.add_get('/hardware', hardware_handler)
    app.router.add_get('/api/hardware', api_hardware_stats_handler)
    app.router.add_get('/api/hardware/gpu', api_hardware_gpu_handler)
    app.router.add_get('/api/hardware/performance', api_hardware_performance_handler)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/api/providers', api_providers_handler)
    # Affiliate routes
    app.router.add_get('/api/affiliates/products', api_affiliates_products_handler)
    app.router.add_get('/api/affiliates/categories', api_affiliates_categories_handler)
    app.router.add_get('/api/affiliates/{product_id}/click/{retailer_id}', api_affiliates_click_handler)
    app.router.add_get('/api/affiliates/stats', api_affiliates_stats_handler)
    app.router.add_get('/api/affiliates/prices', api_affiliates_prices_handler)
    app.router.add_post('/api/affiliates/prices/scrape', api_affiliates_scrape_handler)
    app.router.add_get('/api/affiliates/prices/best', api_affiliates_best_prices_handler)
    app.router.add_get('/api/events', api_events_handler)
    app.router.add_post('/api/interrupt', api_interrupt_handler)
    app.router.add_get('/api/router', api_router_handler)
    app.router.add_post('/api/router/test', api_router_test_handler)
    app.router.add_get('/api/workflows', api_workflows_handler)
    app.router.add_get('/api/workflows/{id}', api_workflow_detail_handler)
    app.router.add_post('/api/workflows/{id}/pause', api_workflow_pause_handler)
    app.router.add_post('/api/launch', api_launch_handler)
    app.router.add_get('/api/files', api_files_list_handler)
    app.router.add_get('/api/files/content', api_files_content_handler)
    app.router.add_get('/api/files/download', api_files_download_handler)
    app.router.add_get('/api/projects', api_projects_list_handler)
    app.router.add_get('/api/projects/download-zip', api_project_download_zip_handler)

    # File upload (SecureVault) routes
    app.router.add_post('/api/files/upload', api_files_upload_handler)
    app.router.add_get('/api/files/vault', api_files_vault_list_handler)
    app.router.add_delete('/api/files/vault/{filename}', api_files_vault_delete_handler)

    app.router.add_post('/api/wireguard/new-peer', api_wireguard_qr_handler)

    # Monetization routes
    app.router.add_get('/api/user', api_user_handler)
    app.router.add_post('/api/user/tryout', api_user_tryout_handler)
    app.router.add_post('/api/user/context', api_user_context_handler)

    # Custom agent prompts
    app.router.add_get('/api/user/agent-prompts', api_agent_prompts_get_handler)
    app.router.add_post('/api/user/agent-prompts', api_agent_prompts_set_handler)

    # Admin endpoints
    app.router.add_post('/api/admin/set-admin', api_admin_set_admin_handler)
    app.router.add_post('/api/admin/add-prompts', api_admin_add_prompts_handler)
    app.router.add_get('/api/tokens', api_tokens_handler)
    app.router.add_post('/api/subscription/checkout', api_subscription_checkout_handler)
    app.router.add_post('/api/checkout/beta-operator', api_beta_operator_checkout_handler)
    app.router.add_post('/webhook/stripe', api_stripe_webhook_handler)
    app.router.add_post('/api/feedback', api_feedback_handler)
    app.router.add_get('/api/feedback', api_feedback_list_handler)
    app.router.add_get('/api/monetization/stats', api_monetization_stats_handler)

    app.router.add_get('/static/{path:.*}', static_handler)

    return app


def run_server(host: str = '0.0.0.0', port: int = 8080, workdir: str = '.') -> None:
    """Run the web server."""
    global current_working_dir
    current_working_dir = workdir

    if AIOHTTP_AVAILABLE:
        app = create_app()
        print(f"\n{'='*60}")
        print("  AGENTFARM NEURAL INTERFACE")
        print(f"{'='*60}")
        print(f"  Dashboard:    http://{host}:{port}")
        print(f"  Mobile:       http://{host}:{port}/mobile")
        print(f"  Hardware:     http://{host}:{port}/hardware")
        print(f"  VPN access:   http://10.0.0.1:{port}/mobile")
        print(f"  Working dir:  {workdir}")
        print()
        print("  Available providers:")
        for p in get_available_providers():
            status = "✓" if p['available'] else "✗"
            print(f"    {status} {p['name']}")
        print()
        print(f"  Press Ctrl+C to stop")
        print(f"{'='*60}\n")
        web.run_app(app, host=host, port=port, print=None)
    else:
        # Fallback to simple HTTP server
        run_simple_server(host, port)


def run_simple_server(host: str, port: int) -> None:
    """Run a simple HTTP server (no WebSocket support)."""
    os.chdir(WEB_DIR)

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/':
                self.path = '/templates/index.html'
            elif self.path.startswith('/static/'):
                self.path = self.path
            return super().do_GET()

        def log_message(self, format, *args):
            pass  # Suppress logging

    print(f"\n{'='*60}")
    print("  AGENTFARM NEURAL INTERFACE (Simple Mode)")
    print(f"{'='*60}")
    print(f"  Server running at: http://{host}:{port}")
    print(f"  Note: WebSocket not available, install aiohttp for full features")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*60}\n")

    server = HTTPServer((host, port), Handler)
    server.serve_forever()


# CLI entry point
def main():
    """Main entry point for CLI."""
    import argparse

    parser = argparse.ArgumentParser(description='AgentFarm Web Interface')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--port', '-p', type=int, default=8080, help='Port to listen on')
    parser.add_argument('--workdir', '-w', default='.', help='Working directory for workflows')
    args = parser.parse_args()

    run_server(args.host, args.port, args.workdir)


if __name__ == '__main__':
    main()
