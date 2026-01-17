"""Affiliate price scraper using Groq API for intelligent extraction.

This module is SEPARATE from the agent system - it uses Groq API specifically
for scraping affiliate prices from Swedish retailers.

Usage:
    from agentfarm.monetization.price_scraper import AffiliatePriceScraper

    scraper = AffiliatePriceScraper(groq_api_key="your-key")
    prices = await scraper.scrape_all_prices()
    best = scraper.find_best_prices(prices)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ===========================================
# Data Models
# ===========================================

class ProductPrice(BaseModel):
    """A scraped price for a product at a retailer."""

    product_id: str
    product_name: str
    retailer_id: str
    retailer_name: str
    url: str
    price: float | None = Field(default=None, description="Price in SEK")
    currency: str = "SEK"
    in_stock: bool | None = None
    stock_status: str | None = Field(default=None, description="In stock, Out of stock, Limited")
    scraped_at: float = Field(default_factory=time.time)
    raw_price_text: str | None = None
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PriceComparison(BaseModel):
    """Price comparison for a single product across retailers."""

    product_id: str
    product_name: str
    category: str
    prices: list[ProductPrice] = Field(default_factory=list)
    best_price: float | None = None
    best_retailer_id: str | None = None
    price_range: tuple[float, float] | None = None
    updated_at: float = Field(default_factory=time.time)

    def calculate_best_price(self) -> None:
        """Calculate best price from available prices."""
        valid_prices = [p for p in self.prices if p.price and p.in_stock is not False]
        if valid_prices:
            best = min(valid_prices, key=lambda p: p.price)
            self.best_price = best.price
            self.best_retailer_id = best.retailer_id
            prices_only = [p.price for p in valid_prices]
            self.price_range = (min(prices_only), max(prices_only))


class ScraperConfig(BaseModel):
    """Configuration for the price scraper."""

    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    rate_limit_per_domain: float = 2.0  # seconds between requests to same domain
    max_concurrent: int = 3
    timeout: int = 30
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 AgentFarm/1.0"
    cache_ttl: int = 3600  # 1 hour cache


# ===========================================
# Groq Price Extractor
# ===========================================

class GroqPriceExtractor:
    """Uses Groq LLM to extract prices from HTML content."""

    EXTRACTION_PROMPT = """You are a price extraction assistant. Extract product information from this HTML snippet.

HTML:
{html}

URL: {url}
Product we're looking for: {product_name}

Extract and return ONLY a JSON object with these fields:
{{
    "price": <number or null if not found>,
    "currency": "SEK",
    "in_stock": <true/false/null>,
    "stock_status": "<text like 'I lager', 'Slut', etc or null>",
    "raw_price_text": "<the exact price text found, e.g. '12 990 kr'>",
    "confidence": <0.0-1.0 how confident you are>
}}

Rules:
- Return ONLY the JSON, no explanation
- Price should be a number without spaces or currency symbols
- "12 990 kr" -> 12990
- "12.990:-" -> 12990
- If price not found, use null
- Confidence: 1.0 = exact match found, 0.5 = partial/uncertain, 0.0 = not found"""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=30)

    async def extract_price(
        self,
        html: str,
        url: str,
        product_name: str
    ) -> dict[str, Any]:
        """Extract price information from HTML using Groq LLM."""

        # Truncate HTML to avoid token limits (keep relevant parts)
        html_snippet = self._extract_relevant_html(html, product_name)

        prompt = self.EXTRACTION_PROMPT.format(
            html=html_snippet[:8000],
            url=url,
            product_name=product_name,
        )

        try:
            response = await self.client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
            )

            if response.status_code != 200:
                logger.error("Groq API error: %s %s", response.status_code, response.text)
                return self._fallback_extraction(html, product_name)

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Parse JSON from response
            return self._parse_extraction_result(content)

        except Exception as e:
            logger.error("Groq extraction error: %s", e)
            return self._fallback_extraction(html, product_name)

    def _extract_relevant_html(self, html: str, product_name: str) -> str:
        """Extract relevant portions of HTML for price extraction."""
        # Look for common price container patterns
        patterns = [
            r'<div[^>]*class="[^"]*price[^"]*"[^>]*>.*?</div>',
            r'<span[^>]*class="[^"]*price[^"]*"[^>]*>.*?</span>',
            r'<p[^>]*class="[^"]*price[^"]*"[^>]*>.*?</p>',
            r'<div[^>]*id="[^"]*price[^"]*"[^>]*>.*?</div>',
            r'<meta[^>]*property="product:price[^"]*"[^>]*>',
            r'"price":\s*[\d.]+',
            r'(?:pris|price)[^<]*[\d\s]+(?:kr|SEK)',
        ]

        snippets = []
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
            snippets.extend(matches[:5])  # Max 5 matches per pattern

        if snippets:
            return "\n---\n".join(snippets[:10])

        # Fallback: return around price-related sections
        price_idx = html.lower().find("pris")
        if price_idx == -1:
            price_idx = html.lower().find("price")
        if price_idx == -1:
            price_idx = html.find("kr")

        if price_idx > 0:
            start = max(0, price_idx - 500)
            end = min(len(html), price_idx + 1000)
            return html[start:end]

        # Last resort: return beginning of body
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if body_match:
            return body_match.group(1)[:8000]

        return html[:8000]

    def _parse_extraction_result(self, content: str) -> dict[str, Any]:
        """Parse the JSON result from Groq."""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return {
            "price": None,
            "currency": "SEK",
            "in_stock": None,
            "stock_status": None,
            "raw_price_text": None,
            "confidence": 0.0,
        }

    def _fallback_extraction(self, html: str, product_name: str) -> dict[str, Any]:
        """Fallback regex-based extraction when LLM fails."""
        price = None
        raw_text = None

        # Common Swedish price patterns
        patterns = [
            r'(\d[\d\s]*(?:\d{3}))\s*(?:kr|:-|SEK)',  # 12 990 kr
            r'(\d+[.,]\d+)\s*(?:kr|:-|SEK)',  # 12990.00 kr
            r'"price":\s*"?(\d+(?:[.,]\d+)?)"?',  # JSON price
            r'data-price="(\d+)"',  # data attribute
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                raw_text = match.group(0)
                price_str = match.group(1).replace(" ", "").replace(",", ".")
                try:
                    price = float(price_str)
                    if price > 100:  # Sanity check - prices should be > 100 SEK
                        break
                except ValueError:
                    continue

        # Check stock status
        in_stock = None
        stock_status = None
        stock_patterns = [
            (r'i\s*lager|in\s*stock', True, "I lager"),
            (r'slut|out\s*of\s*stock|slutsåld', False, "Slut i lager"),
            (r'beställningsvara|backorder', True, "Beställningsvara"),
        ]

        html_lower = html.lower()
        for pattern, is_in_stock, status in stock_patterns:
            if re.search(pattern, html_lower):
                in_stock = is_in_stock
                stock_status = status
                break

        return {
            "price": price,
            "currency": "SEK",
            "in_stock": in_stock,
            "stock_status": stock_status,
            "raw_price_text": raw_text,
            "confidence": 0.5 if price else 0.0,
        }

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# ===========================================
# Main Price Scraper
# ===========================================

class AffiliatePriceScraper:
    """Scrapes prices from affiliate retailers using Groq for extraction."""

    def __init__(
        self,
        groq_api_key: str | None = None,
        config: ScraperConfig | None = None,
        affiliates_path: Path | str | None = None,
    ):
        self.config = config or ScraperConfig()

        # Get Groq API key from config, parameter, or environment
        self.groq_api_key = groq_api_key or self.config.groq_api_key or os.getenv("GROQ_API_KEY")

        if not self.groq_api_key:
            raise ValueError("Groq API key required. Set GROQ_API_KEY environment variable.")

        self.extractor = GroqPriceExtractor(
            api_key=self.groq_api_key,
            model=self.config.groq_model,
        )

        self.http_client = httpx.AsyncClient(
            timeout=self.config.timeout,
            headers={"User-Agent": self.config.user_agent},
            follow_redirects=True,
        )

        # Load affiliates config
        self.affiliates_path = Path(affiliates_path) if affiliates_path else Path(".agentfarm/affiliates.json")
        self.affiliates_config = self._load_affiliates()

        # Rate limiting per domain
        self._last_request_time: dict[str, float] = {}
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)

        # Price cache
        self._price_cache: dict[str, ProductPrice] = {}
        self._cache_path = self.affiliates_path.parent / "price_cache.json"
        self._load_cache()

    def _load_affiliates(self) -> dict[str, Any]:
        """Load affiliates configuration."""
        if self.affiliates_path.exists():
            return json.loads(self.affiliates_path.read_text())
        return {"retailers": {}, "products": []}

    def _load_cache(self) -> None:
        """Load price cache from disk."""
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                now = time.time()
                for key, item in data.items():
                    if now - item.get("scraped_at", 0) < self.config.cache_ttl:
                        self._price_cache[key] = ProductPrice(**item)
            except (json.JSONDecodeError, ValueError):
                pass

    def _save_cache(self) -> None:
        """Save price cache to disk."""
        data = {k: v.model_dump() for k, v in self._price_cache.items()}
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(data, indent=2))

    async def _rate_limit(self, domain: str) -> None:
        """Apply rate limiting per domain."""
        last_time = self._last_request_time.get(domain, 0)
        wait_time = self.config.rate_limit_per_domain - (time.time() - last_time)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self._last_request_time[domain] = time.time()

    async def fetch_page(self, url: str) -> str | None:
        """Fetch a page with rate limiting."""
        domain = urlparse(url).netloc

        async with self._semaphore:
            await self._rate_limit(domain)

            try:
                response = await self.http_client.get(url)
                if response.status_code == 200:
                    return response.text
                logger.warning("HTTP %d for %s", response.status_code, url)
            except Exception as e:
                logger.error("Fetch error for %s: %s", url, e)

        return None

    async def scrape_product_price(
        self,
        product_id: str,
        product_name: str,
        retailer_id: str,
        retailer_name: str,
        url: str,
    ) -> ProductPrice:
        """Scrape price for a single product at a retailer."""
        cache_key = f"{product_id}:{retailer_id}"

        # Check cache
        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            if time.time() - cached.scraped_at < self.config.cache_ttl:
                logger.debug("Cache hit for %s at %s", product_name, retailer_name)
                return cached

        logger.info("Scraping %s from %s...", product_name, retailer_name)

        # Fetch page
        html = await self.fetch_page(url)

        if not html:
            return ProductPrice(
                product_id=product_id,
                product_name=product_name,
                retailer_id=retailer_id,
                retailer_name=retailer_name,
                url=url,
                price=None,
                in_stock=None,
                extraction_confidence=0.0,
            )

        # Extract price using Groq
        extraction = await self.extractor.extract_price(html, url, product_name)

        price = ProductPrice(
            product_id=product_id,
            product_name=product_name,
            retailer_id=retailer_id,
            retailer_name=retailer_name,
            url=url,
            price=extraction.get("price"),
            currency=extraction.get("currency", "SEK"),
            in_stock=extraction.get("in_stock"),
            stock_status=extraction.get("stock_status"),
            raw_price_text=extraction.get("raw_price_text"),
            extraction_confidence=extraction.get("confidence", 0.0),
        )

        # Cache result
        self._price_cache[cache_key] = price

        return price

    async def scrape_all_prices(self) -> list[ProductPrice]:
        """Scrape prices for all products from all retailers."""
        prices = []
        retailers = self.affiliates_config.get("retailers", {})
        products = self.affiliates_config.get("products", [])

        tasks = []
        for product in products:
            product_id = product["id"]
            product_name = product["name"]

            for retailer_id, url in product.get("links", {}).items():
                retailer = retailers.get(retailer_id, {})
                retailer_name = retailer.get("name", retailer_id)

                tasks.append(
                    self.scrape_product_price(
                        product_id=product_id,
                        product_name=product_name,
                        retailer_id=retailer_id,
                        retailer_name=retailer_name,
                        url=url,
                    )
                )

        if tasks:
            prices = await asyncio.gather(*tasks, return_exceptions=True)
            prices = [p for p in prices if isinstance(p, ProductPrice)]

        # Save cache
        self._save_cache()

        return prices

    def build_comparisons(self, prices: list[ProductPrice]) -> list[PriceComparison]:
        """Build price comparisons from scraped prices."""
        # Group by product
        by_product: dict[str, list[ProductPrice]] = {}
        for price in prices:
            if price.product_id not in by_product:
                by_product[price.product_id] = []
            by_product[price.product_id].append(price)

        comparisons = []
        products = {p["id"]: p for p in self.affiliates_config.get("products", [])}

        for product_id, product_prices in by_product.items():
            product = products.get(product_id, {})

            comparison = PriceComparison(
                product_id=product_id,
                product_name=product.get("name", product_id),
                category=product.get("category", "other"),
                prices=product_prices,
            )
            comparison.calculate_best_price()
            comparisons.append(comparison)

        return comparisons

    def find_best_prices(self, prices: list[ProductPrice]) -> dict[str, ProductPrice]:
        """Find the best price for each product."""
        best: dict[str, ProductPrice] = {}

        for price in prices:
            if price.price is None or price.in_stock is False:
                continue

            current_best = best.get(price.product_id)
            if current_best is None or (current_best.price and price.price < current_best.price):
                best[price.product_id] = price

        return best

    def generate_price_report(self, comparisons: list[PriceComparison]) -> dict[str, Any]:
        """Generate a price report for the website."""
        report = {
            "generated_at": datetime.now().isoformat(),
            "products": [],
        }

        for comp in comparisons:
            product_data = {
                "id": comp.product_id,
                "name": comp.product_name,
                "category": comp.category,
                "best_price": comp.best_price,
                "best_retailer": comp.best_retailer_id,
                "price_range": comp.price_range,
                "prices": [
                    {
                        "retailer": p.retailer_id,
                        "retailer_name": p.retailer_name,
                        "price": p.price,
                        "in_stock": p.in_stock,
                        "stock_status": p.stock_status,
                        "url": p.url,
                    }
                    for p in sorted(comp.prices, key=lambda x: x.price or float("inf"))
                ],
            }
            report["products"].append(product_data)

        return report

    def save_price_report(self, report: dict[str, Any], path: Path | str | None = None) -> Path:
        """Save price report to JSON file."""
        if path is None:
            path = self.affiliates_path.parent / "price_report.json"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        return path

    async def run_and_save(self) -> Path:
        """Run full scrape and save report."""
        logger.info("Starting price scrape...")

        prices = await self.scrape_all_prices()
        logger.info("Scraped %d prices", len(prices))

        comparisons = self.build_comparisons(prices)
        logger.info("Built %d comparisons", len(comparisons))

        report = self.generate_price_report(comparisons)
        path = self.save_price_report(report)

        logger.info("Price report saved to %s", path)
        return path

    async def close(self):
        """Close all connections."""
        await self.extractor.close()
        await self.http_client.aclose()


# ===========================================
# CLI
# ===========================================

async def main():
    """CLI entry point for price scraping."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Scrape affiliate prices using Groq")
    parser.add_argument("--config", "-c", help="Affiliates config path")
    parser.add_argument("--output", "-o", help="Output report path")
    parser.add_argument("--cache-ttl", type=int, default=3600, help="Cache TTL in seconds")
    args = parser.parse_args()

    config = ScraperConfig(cache_ttl=args.cache_ttl)

    scraper = AffiliatePriceScraper(
        config=config,
        affiliates_path=args.config,
    )

    try:
        path = await scraper.run_and_save()
        print(f"\nPrice report saved: {path}")

        # Print summary
        report = json.loads(path.read_text())
        print(f"\nProducts: {len(report['products'])}")
        for p in report["products"]:
            best = p.get("best_price")
            retailer = p.get("best_retailer")
            print(f"  {p['name']}: {best} SEK @ {retailer}" if best else f"  {p['name']}: No price found")
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
