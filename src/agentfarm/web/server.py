"""
AgentFarm Web Server - 80s Sci-Fi Neural Interface

Serves the retro dashboard and provides WebSocket connections
for real-time agent communication visualization.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Try to import aiohttp, fall back to basic HTTP server if not available
try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from http.server import HTTPServer, SimpleHTTPRequestHandler

from agentfarm.config import AgentFarmConfig, ProviderConfig, ProviderType


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
            return

        data = json.dumps(message)
        dead_clients = set()

        for ws in self.clients:
            try:
                await ws.send_str(data)
            except Exception:
                dead_clients.add(ws)

        self.clients -= dead_clients

    def add(self, ws: web.WebSocketResponse) -> None:
        self.clients.add(ws)

    def remove(self, ws: web.WebSocketResponse) -> None:
        self.clients.discard(ws)


# Global state
ws_clients = WebSocketClients()
current_working_dir = "."


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

    # Sanitize project name
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '-', name.lower())
    safe_name = re.sub(r'-+', '-', safe_name).strip('-')
    if not safe_name:
        safe_name = 'nytt-projekt'

    # Create project in ~/nya projekt/
    projects_base = Path.home() / "nya projekt"
    projects_base.mkdir(exist_ok=True)

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

    async def event_callback(event: str, data: dict[str, Any]) -> None:
        """Callback to broadcast events to WebSocket clients."""
        await ws_clients.broadcast({'type': event, **data})

    try:
        await ws_clients.broadcast({
            'type': 'workflow_start',
            'task': task,
            'provider': 'multi-provider',
            'working_dir': working_dir,
        })

        # Create orchestrator in multi-provider mode (no single provider passed)
        orchestrator = Orchestrator(
            provider=None,  # Triggers multi-provider mode
            working_dir=working_dir,
            event_callback=event_callback,
            use_multi_provider=True,
        )

        # Inject file tools
        file_tools = FileTools(working_dir)
        orchestrator.inject_tools(file_tools=file_tools)

        # Run the workflow
        result = await orchestrator.run_workflow(task)

        # Send final result
        await ws_clients.broadcast({
            'type': 'workflow_result',
            'success': result.success,
            'summary': result.pr_summary,
            'tokens': orchestrator.get_total_tokens_used(),
        })

    except Exception as e:
        import traceback
        await ws_clients.broadcast({
            'type': 'agent_message',
            'agent': 'orchestrator',
            'content': f"Error: {str(e)}",
        })
        await ws_clients.broadcast({
            'type': 'workflow_complete',
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        })


async def run_real_workflow(task: str, provider_type: str, working_dir: str) -> None:
    """Run a real AgentFarm workflow and broadcast updates."""
    from agentfarm.orchestrator import Orchestrator
    from agentfarm.tools.file_tools import FileTools

    async def event_callback(event: str, data: dict[str, Any]) -> None:
        """Callback to broadcast events to WebSocket clients."""
        await ws_clients.broadcast({'type': event, **data})

    try:
        # Notify start
        await ws_clients.broadcast({
            'type': 'workflow_start',
            'task': task,
            'provider': provider_type,
            'working_dir': working_dir,
        })

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

        # Inject file tools
        file_tools = FileTools(working_dir)
        orchestrator.inject_tools(file_tools=file_tools)

        # Run the workflow
        result = await orchestrator.run_workflow(task)

        # Final result already sent via callback, but send summary too
        await ws_clients.broadcast({
            'type': 'workflow_result',
            'success': result.success,
            'summary': result.pr_summary,
            'tokens': result.total_tokens_used,
        })

    except Exception as e:
        import traceback
        await ws_clients.broadcast({
            'type': 'agent_message',
            'agent': 'orchestrator',
            'content': f"Error: {str(e)}",
        })
        await ws_clients.broadcast({
            'type': 'workflow_complete',
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        })


async def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Broadcast an event to all connected clients."""
    await ws_clients.broadcast({
        'type': event_type,
        **data,
    })


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()

    app.router.add_get('/', index_handler)
    app.router.add_get('/mobile', mobile_handler)
    app.router.add_get('/m', mobile_handler)  # Short alias
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/api/providers', api_providers_handler)
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
