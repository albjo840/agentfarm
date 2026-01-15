from __future__ import annotations

"""Affiliate link management and click tracking for AgentFarm."""

import json
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

from pydantic import BaseModel, Field


class Retailer(BaseModel):
    """A retailer/affiliate partner."""

    id: str
    name: str
    affiliate_param: str = Field(..., description="URL parameter for affiliate tracking, e.g. 'ref=agentfarm'")
    base_url: str | None = None


class AffiliateProduct(BaseModel):
    """A product with affiliate links to multiple retailers."""

    id: str
    name: str
    description: str
    category: str = Field(..., description="gpu, cpu, ram, sbc, etc.")
    badge: str | None = Field(default=None, description="RECOMMENDED, BEST VALUE, etc.")
    image_url: str | None = None
    links: dict[str, str] = Field(default_factory=dict, description="retailer_id -> product URL")


class AffiliateClick(BaseModel):
    """A tracked affiliate click."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    product_id: str
    retailer_id: str
    device_id: str | None = None
    referrer: str | None = None
    user_agent: str | None = None
    timestamp: float = Field(default_factory=time.time)


class AffiliateConfig(BaseModel):
    """Configuration for affiliate system."""

    retailers: dict[str, Retailer] = Field(default_factory=dict)
    products: list[AffiliateProduct] = Field(default_factory=list)


class AffiliateManager:
    """Manages affiliate links and click tracking.

    Configuration is loaded from .agentfarm/affiliates.json
    Clicks are logged to .agentfarm/analytics/affiliate_clicks.json
    """

    def __init__(self, storage_dir: Path | str, config_path: Path | str | None = None) -> None:
        self.storage_dir = Path(storage_dir)
        self.analytics_dir = self.storage_dir / "analytics"
        self.analytics_dir.mkdir(parents=True, exist_ok=True)

        # Config path defaults to .agentfarm/affiliates.json
        self.config_path = Path(config_path) if config_path else self.storage_dir / "affiliates.json"

        self.config = self._load_config()

    def _load_config(self) -> AffiliateConfig:
        """Load affiliate configuration from JSON file."""
        if not self.config_path.exists():
            # Create default config
            default_config = self._create_default_config()
            self._save_config(default_config)
            return default_config

        try:
            data = json.loads(self.config_path.read_text())
            # Parse retailers
            retailers = {}
            for rid, rdata in data.get("retailers", {}).items():
                retailers[rid] = Retailer(id=rid, **rdata)

            # Parse products
            products = [AffiliateProduct(**p) for p in data.get("products", [])]

            return AffiliateConfig(retailers=retailers, products=products)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load affiliate config: {e}")
            return AffiliateConfig()

    def _save_config(self, config: AffiliateConfig) -> None:
        """Save configuration to file."""
        data = {
            "retailers": {rid: {"name": r.name, "affiliate_param": r.affiliate_param}
                          for rid, r in config.retailers.items()},
            "products": [p.model_dump() for p in config.products],
        }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def _create_default_config(self) -> AffiliateConfig:
        """Create default affiliate configuration with Swedish retailers."""
        retailers = {
            "dustin": Retailer(id="dustin", name="Dustin", affiliate_param="ref=agentfarm"),
            "komplett": Retailer(id="komplett", name="Komplett", affiliate_param="wt.mc_id=agentfarm"),
            "inet": Retailer(id="inet", name="Inet", affiliate_param="ref=agentfarm"),
            "electrokit": Retailer(id="electrokit", name="Electrokit", affiliate_param="ref=agentfarm"),
        }

        products = [
            AffiliateProduct(
                id="amd_7900xtx",
                name="AMD Radeon RX 7900 XTX",
                description="ROCm 6.x stöd, 24GB VRAM - perfekt för lokala LLMs och AI-inferens",
                category="gpu",
                badge="RECOMMENDED",
                links={
                    "dustin": "https://www.dustin.se/product/5011335054",
                    "komplett": "https://www.komplett.se/product/1234567",
                    "inet": "https://www.inet.se/produkt/1234567",
                },
            ),
            AffiliateProduct(
                id="amd_7900gre",
                name="AMD Radeon RX 7900 GRE",
                description="ROCm stöd, 16GB VRAM - bästa värdet för AI/ML-arbete",
                category="gpu",
                badge="BEST VALUE",
                links={
                    "dustin": "https://www.dustin.se/product/5011335055",
                    "komplett": "https://www.komplett.se/product/1234568",
                },
            ),
            AffiliateProduct(
                id="amd_7800xt",
                name="AMD Radeon RX 7800 XT",
                description="ROCm stöd, 16GB VRAM - prisvärt alternativ",
                category="gpu",
                badge=None,
                links={
                    "inet": "https://www.inet.se/produkt/1234568",
                    "komplett": "https://www.komplett.se/product/1234569",
                },
            ),
            AffiliateProduct(
                id="raspberry_pi_5",
                name="Raspberry Pi 5 8GB",
                description="Perfekt för edge inference och lokala MCP-servrar",
                category="sbc",
                badge="EDGE AI",
                links={
                    "electrokit": "https://www.electrokit.com/raspberry-pi-5-8gb",
                },
            ),
        ]

        return AffiliateConfig(retailers=retailers, products=products)

    def get_products(self, category: str | None = None) -> list[AffiliateProduct]:
        """Get all products, optionally filtered by category."""
        products = self.config.products
        if category:
            products = [p for p in products if p.category == category]
        return products

    def get_product(self, product_id: str) -> AffiliateProduct | None:
        """Get a product by ID."""
        for product in self.config.products:
            if product.id == product_id:
                return product
        return None

    def get_retailers(self) -> dict[str, Retailer]:
        """Get all configured retailers."""
        return self.config.retailers

    def get_affiliate_url(self, product_id: str, retailer_id: str) -> str | None:
        """Get affiliate URL for a product at a specific retailer.

        Appends the affiliate tracking parameter to the product URL.
        """
        product = self.get_product(product_id)
        if not product:
            return None

        base_url = product.links.get(retailer_id)
        if not base_url:
            return None

        retailer = self.config.retailers.get(retailer_id)
        if not retailer:
            return base_url

        # Parse and append affiliate parameter
        return self._append_param(base_url, retailer.affiliate_param)

    def _append_param(self, url: str, param: str) -> str:
        """Append a parameter to a URL."""
        parsed = urlparse(url)
        existing_params = parse_qs(parsed.query)

        # Parse the new param
        key, value = param.split("=", 1) if "=" in param else (param, "")
        existing_params[key] = [value]

        # Rebuild query string
        new_query = urlencode(existing_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)

    def track_click(
        self,
        product_id: str,
        retailer_id: str,
        device_id: str | None = None,
        referrer: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str | None, AffiliateClick]:
        """Track an affiliate click and return the redirect URL.

        Args:
            product_id: Product being clicked
            retailer_id: Retailer being clicked
            device_id: User's device fingerprint
            referrer: HTTP referrer
            user_agent: User agent string

        Returns:
            Tuple of (affiliate_url, click_record)
        """
        click = AffiliateClick(
            product_id=product_id,
            retailer_id=retailer_id,
            device_id=device_id,
            referrer=referrer,
            user_agent=user_agent,
        )

        # Log the click
        self._log_click(click)

        # Get the affiliate URL
        url = self.get_affiliate_url(product_id, retailer_id)

        return url, click

    def _log_click(self, click: AffiliateClick) -> None:
        """Log a click to the analytics file."""
        log_path = self.analytics_dir / "affiliate_clicks.json"
        clicks: list[dict[str, Any]] = []

        if log_path.exists():
            try:
                clicks = json.loads(log_path.read_text())
            except json.JSONDecodeError:
                clicks = []

        clicks.append(click.model_dump())

        # Keep last 50000 clicks
        if len(clicks) > 50000:
            clicks = clicks[-50000:]

        log_path.write_text(json.dumps(clicks, indent=2))

    def get_click_stats(self, days: int = 30) -> dict[str, Any]:
        """Get click statistics for the last N days."""
        log_path = self.analytics_dir / "affiliate_clicks.json"
        if not log_path.exists():
            return {"total_clicks": 0, "by_product": {}, "by_retailer": {}}

        try:
            clicks = json.loads(log_path.read_text())
        except json.JSONDecodeError:
            return {"total_clicks": 0, "by_product": {}, "by_retailer": {}}

        cutoff = time.time() - (days * 86400)
        recent_clicks = [c for c in clicks if c.get("timestamp", 0) > cutoff]

        by_product: dict[str, int] = {}
        by_retailer: dict[str, int] = {}

        for click in recent_clicks:
            pid = click.get("product_id", "unknown")
            rid = click.get("retailer_id", "unknown")
            by_product[pid] = by_product.get(pid, 0) + 1
            by_retailer[rid] = by_retailer.get(rid, 0) + 1

        return {
            "total_clicks": len(recent_clicks),
            "by_product": by_product,
            "by_retailer": by_retailer,
            "days": days,
        }

    def get_categories(self) -> list[str]:
        """Get list of unique product categories."""
        categories = set()
        for product in self.config.products:
            categories.add(product.category)
        return sorted(categories)

    def add_product(self, product: AffiliateProduct) -> None:
        """Add a new product to the configuration."""
        # Remove existing product with same ID
        self.config.products = [p for p in self.config.products if p.id != product.id]
        self.config.products.append(product)
        self._save_config(self.config)

    def remove_product(self, product_id: str) -> bool:
        """Remove a product from the configuration."""
        original_len = len(self.config.products)
        self.config.products = [p for p in self.config.products if p.id != product_id]
        if len(self.config.products) < original_len:
            self._save_config(self.config)
            return True
        return False
