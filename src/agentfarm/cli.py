from __future__ import annotations

"""Command-line interface for AgentFarm."""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

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

from agentfarm.config import AgentFarmConfig, ProviderType, get_default_config
from agentfarm.orchestrator import Orchestrator
from agentfarm.tools.code_tools import CodeTools
from agentfarm.tools.file_tools import FileTools
from agentfarm.tools.git_tools import GitTools
from agentfarm.tools.sandbox import SandboxRunner


def create_provider(config: AgentFarmConfig):
    """Create LLM provider from config."""
    pc = config.provider

    if pc.type == ProviderType.GROQ:
        from agentfarm.providers.groq import GroqProvider
        return GroqProvider(
            model=pc.model,
            api_key=pc.api_key,
        )
    elif pc.type == ProviderType.OLLAMA:
        from agentfarm.providers.ollama import OllamaProvider
        return OllamaProvider(
            model=pc.model,
            base_url=pc.base_url or "http://localhost:11434",
        )
    elif pc.type == ProviderType.GEMINI:
        from agentfarm.providers.gemini import GeminiProvider
        return GeminiProvider(
            model=pc.model,
            api_key=pc.api_key,
        )
    elif pc.type in (ProviderType.SILICONFLOW, ProviderType.QWEN):
        from agentfarm.providers.siliconflow import SiliconFlowProvider
        return SiliconFlowProvider(
            model=pc.model,
            api_key=pc.api_key,
        )
    elif pc.type == ProviderType.CLAUDE:
        from agentfarm.providers.claude import ClaudeProvider
        return ClaudeProvider(
            model=pc.model,
            api_key=pc.api_key,
        )
    raise ValueError(f"Unsupported provider: {pc.type}")


def create_orchestrator(config: AgentFarmConfig) -> Orchestrator:
    """Create and configure orchestrator.

    Uses multi-provider mode by default, falling back to available providers.
    Only creates a single provider if explicitly configured via environment.
    """
    import os

    # Check if a specific provider is explicitly requested
    explicit_provider = os.getenv("AGENTFARM_PROVIDER")

    if explicit_provider:
        # User explicitly requested a provider - use single-provider mode
        provider = create_provider(config)
        orchestrator = Orchestrator(provider, working_dir=config.working_dir, use_multi_provider=False)
    else:
        # Use multi-provider mode with automatic fallback
        orchestrator = Orchestrator(provider=None, working_dir=config.working_dir, use_multi_provider=True)

    # Inject tools
    file_tools = FileTools(config.working_dir)
    code_tools = CodeTools(config.working_dir)
    git_tools = GitTools(config.working_dir)

    sandbox = None
    if config.sandbox.enabled:
        sandbox = SandboxRunner(
            working_dir=config.working_dir,
            image=config.sandbox.image,
            timeout=config.sandbox.timeout,
            memory=config.sandbox.memory,
            cpu_limit=config.sandbox.cpu_limit,
        )

    orchestrator.inject_tools(file_tools, code_tools, git_tools, sandbox)
    return orchestrator


async def run_workflow(args: argparse.Namespace) -> int:
    """Run the full workflow."""
    config = get_default_config()
    config.working_dir = args.workdir

    orchestrator = create_orchestrator(config)

    print(f"Running workflow for task: {args.task}")
    print("-" * 50)

    result = await orchestrator.run_workflow(
        task=args.task,
        context_files=args.files,
        constraints=args.constraints,
    )

    print("\n" + "=" * 50)
    print("RESULT")
    print("=" * 50)

    if result.success:
        print("Status: SUCCESS")
    else:
        print("Status: FAILED")

    if result.plan:
        print(f"\nPlan: {result.plan.summary}")
        print(f"Steps: {len(result.plan.steps)}")

    if result.verification:
        v = result.verification
        print(f"\nTests: {v.tests_passed} passed, {v.tests_failed} failed")

    if result.review:
        r = result.review
        status = "Approved" if r.approved else "Changes requested"
        print(f"\nReview: {status}")

    if result.pr_summary:
        print("\n--- PR Summary ---")
        print(result.pr_summary)

    if result.total_tokens_used:
        print(f"\nTokens used: {result.total_tokens_used}")

    return 0 if result.success else 1


async def run_plan(args: argparse.Namespace) -> int:
    """Run only the planning phase."""
    config = get_default_config()
    config.working_dir = args.workdir

    orchestrator = create_orchestrator(config)

    from agentfarm.agents.base import AgentContext

    context = AgentContext(
        task_summary=args.task,
        relevant_files=args.files or [],
    )

    plan = await orchestrator.planner.create_plan(context, args.task)

    if plan:
        print(json.dumps(plan.model_dump(), indent=2))
        return 0
    else:
        print("Failed to create plan", file=sys.stderr)
        return 1


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AgentFarm - Multi-agent code assistant"
    )
    parser.add_argument(
        "--workdir", "-w",
        default=".",
        help="Working directory (default: current)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # workflow command
    workflow_parser = subparsers.add_parser(
        "workflow", help="Run full PLAN→EXECUTE→VERIFY→REVIEW workflow"
    )
    workflow_parser.add_argument("task", help="Task description")
    workflow_parser.add_argument(
        "--files", "-f",
        nargs="*",
        help="Context files",
    )
    workflow_parser.add_argument(
        "--constraints", "-c",
        nargs="*",
        help="Constraints to follow",
    )

    # plan command
    plan_parser = subparsers.add_parser("plan", help="Create a plan only")
    plan_parser.add_argument("task", help="Task description")
    plan_parser.add_argument(
        "--files", "-f",
        nargs="*",
        help="Context files",
    )

    # mcp command
    mcp_parser = subparsers.add_parser("mcp", help="Run as MCP server")

    # web command
    web_parser = subparsers.add_parser("web", help="Run the 80s sci-fi web interface")
    web_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0 for VPN access)",
    )
    web_parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080)",
    )

    # scrape-prices command
    scrape_parser = subparsers.add_parser(
        "scrape-prices",
        help="Scrape affiliate prices using Groq API"
    )
    scrape_parser.add_argument(
        "--config", "-c",
        help="Affiliates config path (default: .agentfarm/affiliates.json)",
    )
    scrape_parser.add_argument(
        "--output", "-o",
        help="Output report path (default: .agentfarm/price_report.json)",
    )
    scrape_parser.add_argument(
        "--cache-ttl",
        type=int,
        default=3600,
        help="Cache TTL in seconds (default: 3600)",
    )

    args = parser.parse_args()

    if args.command == "workflow":
        sys.exit(asyncio.run(run_workflow(args)))
    elif args.command == "plan":
        sys.exit(asyncio.run(run_plan(args)))
    elif args.command == "mcp":
        from agentfarm.mcp_server import main as mcp_main
        mcp_main()
    elif args.command == "web":
        from agentfarm.web.server import run_server
        run_server(args.host, args.port, args.workdir)
    elif args.command == "scrape-prices":
        sys.exit(asyncio.run(run_scrape_prices(args)))
    else:
        parser.print_help()
        sys.exit(1)


async def run_scrape_prices(args) -> int:
    """Run affiliate price scraper using Groq API."""
    import os

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        print("Error: GROQ_API_KEY environment variable not set")
        print("Get your API key at: https://console.groq.com/keys")
        return 1

    from agentfarm.monetization.price_scraper import AffiliatePriceScraper, ScraperConfig

    print("Starting affiliate price scraper...")
    print(f"  Config: {args.config or '.agentfarm/affiliates.json'}")
    print(f"  Cache TTL: {args.cache_ttl}s")
    print()

    try:
        config = ScraperConfig(
            groq_api_key=groq_api_key,
            cache_ttl=args.cache_ttl,
        )

        scraper = AffiliatePriceScraper(
            config=config,
            affiliates_path=args.config,
        )

        path = await scraper.run_and_save()
        await scraper.close()

        print(f"\nPrice report saved: {path}")

        # Print summary
        report = json.loads(path.read_text())
        print(f"\nProducts: {len(report['products'])}")
        for p in report["products"]:
            best = p.get("best_price")
            retailer = p.get("best_retailer")
            if best:
                print(f"  {p['name']}: {best:,.0f} SEK @ {retailer}")
            else:
                print(f"  {p['name']}: No price found")

        return 0

    except Exception as e:
        logging.exception("Price scrape failed")
        print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    main()
