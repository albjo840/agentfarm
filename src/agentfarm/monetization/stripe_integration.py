from __future__ import annotations

"""Stripe integration for subscriptions and payments."""

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class StripeConfig(BaseModel):
    """Stripe configuration."""

    secret_key: str = Field(..., description="Stripe secret key (sk_...)")
    webhook_secret: str = Field(..., description="Webhook signing secret (whsec_...)")
    early_access_price_id: str = Field(default="", description="Price ID for Early Access subscription (optional)")
    prompt_pack_price_id: str = Field(default="", description="Price ID for 10-prompt pack")
    prompt_pack_amount: int = Field(default=10, description="Prompts per pack")
    beta_operator_price_id: str = Field(default="", description="Price ID for Beta Operator (10 workflows + premium features)")
    beta_operator_prompts: int = Field(default=10, description="Workflows included with Beta Operator")
    token_pack_price_ids: dict[str, str] = Field(
        default_factory=lambda: {
            "small": "",  # Legacy
            "medium": "",
            "large": "",
        }
    )
    success_url: str = Field(default="http://localhost:8080/?payment=success")
    cancel_url: str = Field(default="http://localhost:8080/?payment=cancelled")


class StripeEvent(BaseModel):
    """Parsed Stripe webhook event."""

    id: str
    type: str
    data: dict[str, Any]
    created: int


class CheckoutSession(BaseModel):
    """Stripe checkout session info."""

    id: str
    url: str
    device_id: str
    product_type: str  # "early_access" or "token_pack_small", etc.


class StripeIntegration:
    """Handles Stripe webhooks and checkout sessions.

    Uses raw HTTP requests to avoid requiring the stripe SDK.
    For production, consider using the official stripe-python package.
    """

    STRIPE_API_BASE = "https://api.stripe.com/v1"

    def __init__(self, config: StripeConfig | None = None) -> None:
        """Initialize Stripe integration.

        Args:
            config: Stripe configuration. If None, loads from environment.
        """
        if config:
            self.config = config
        else:
            self.config = StripeConfig(
                secret_key=os.getenv("STRIPE_SECRET_KEY", ""),
                webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
                early_access_price_id=os.getenv("STRIPE_EARLY_ACCESS_PRICE_ID", ""),
                prompt_pack_price_id=os.getenv("STRIPE_PROMPT_PACK_PRICE_ID", ""),
                prompt_pack_amount=int(os.getenv("STRIPE_PROMPT_PACK_AMOUNT", "10")),
                beta_operator_price_id=os.getenv("STRIPE_BETA_OPERATOR_PRICE_ID", ""),
                beta_operator_prompts=int(os.getenv("STRIPE_BETA_OPERATOR_PROMPTS", "10")),
                success_url=os.getenv("STRIPE_SUCCESS_URL", "http://localhost:8080/?payment=success"),
                cancel_url=os.getenv("STRIPE_CANCEL_URL", "http://localhost:8080/?payment=cancelled"),
            )

        self._enabled = bool(self.config.secret_key and self.config.webhook_secret)

    @property
    def enabled(self) -> bool:
        """Check if Stripe is properly configured."""
        return self._enabled

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature.

        Args:
            payload: Raw request body
            signature: Stripe-Signature header value

        Returns:
            True if signature is valid
        """
        if not self._enabled:
            return False

        try:
            # Parse signature header
            elements = dict(item.split("=", 1) for item in signature.split(","))
            timestamp = elements.get("t", "")
            expected_sig = elements.get("v1", "")

            if not timestamp or not expected_sig:
                return False

            # Check timestamp (reject if older than 5 minutes)
            if abs(time.time() - int(timestamp)) > 300:
                logger.warning("Stripe webhook timestamp too old")
                return False

            # Compute expected signature
            signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
            computed_sig = hmac.new(
                self.config.webhook_secret.encode("utf-8"),
                signed_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(computed_sig, expected_sig)

        except Exception as e:
            logger.error(f"Webhook signature verification failed: {e}")
            return False

    def parse_webhook_event(self, payload: bytes) -> StripeEvent | None:
        """Parse webhook payload into StripeEvent.

        Args:
            payload: Raw request body (JSON)

        Returns:
            Parsed event or None if invalid
        """
        try:
            data = json.loads(payload)
            return StripeEvent(
                id=data["id"],
                type=data["type"],
                data=data.get("data", {}).get("object", {}),
                created=data.get("created", 0),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse webhook event: {e}")
            return None

    async def handle_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        """Process Stripe webhook event.

        Args:
            payload: Raw request body
            signature: Stripe-Signature header

        Returns:
            Dict with action to take: {"action": "...", "device_id": "...", ...}
        """
        logger.info("handle_webhook: Verifying signature (secret starts with: %s...)",
                    self.config.webhook_secret[:10] if self.config.webhook_secret else "EMPTY")

        if not self.verify_webhook_signature(payload, signature):
            logger.error("handle_webhook: Signature verification FAILED")
            logger.error("handle_webhook: signature header = %s", signature[:50] if signature else "EMPTY")
            return {"action": "invalid_signature", "error": "Signature verification failed"}

        logger.info("handle_webhook: Signature verification PASSED")

        event = self.parse_webhook_event(payload)
        if not event:
            logger.error("handle_webhook: Failed to parse event from payload")
            return {"action": "parse_error", "error": "Failed to parse event"}

        logger.info(f"Processing Stripe event: {event.type}")

        # Handle different event types
        if event.type == "checkout.session.completed":
            return self._handle_checkout_completed(event)
        elif event.type == "customer.subscription.updated":
            return self._handle_subscription_updated(event)
        elif event.type == "customer.subscription.deleted":
            return self._handle_subscription_deleted(event)
        elif event.type == "invoice.payment_succeeded":
            return self._handle_payment_succeeded(event)
        elif event.type == "invoice.payment_failed":
            return self._handle_payment_failed(event)
        else:
            logger.debug(f"Unhandled event type: {event.type}")
            return {"action": "ignored", "event_type": event.type}

    def _handle_checkout_completed(self, event: StripeEvent) -> dict[str, Any]:
        """Handle successful checkout session."""
        session_data = event.data
        device_id = session_data.get("client_reference_id", "")
        mode = session_data.get("mode", "")
        metadata = session_data.get("metadata", {})
        product_type = metadata.get("product_type", "")
        customer_id = session_data.get("customer", "")

        if mode == "subscription":
            return {
                "action": "upgrade_tier",
                "device_id": device_id,
                "tier": "early_access",
                "stripe_customer_id": customer_id,
            }
        elif mode == "payment":
            # Check if it's a Beta Operator purchase
            if product_type == "beta_operator":
                return {
                    "action": "upgrade_beta_operator",
                    "device_id": device_id,
                    "prompts": self.config.beta_operator_prompts,
                    "stripe_customer_id": customer_id,
                }
            # Check if it's a prompt pack purchase
            if product_type == "prompt_pack":
                return {
                    "action": "add_prompts",
                    "device_id": device_id,
                    "prompts": self.config.prompt_pack_amount,
                    "product_type": product_type,
                }
            # Legacy: token pack purchase
            tokens = self._get_token_pack_amount(product_type)
            return {
                "action": "add_tokens",
                "device_id": device_id,
                "tokens": tokens,
                "product_type": product_type,
            }
        else:
            return {"action": "unknown_mode", "mode": mode}

    def _handle_subscription_updated(self, event: StripeEvent) -> dict[str, Any]:
        """Handle subscription update (renewal, upgrade, etc.)."""
        subscription = event.data
        customer_id = subscription.get("customer", "")
        status = subscription.get("status", "")
        metadata = subscription.get("metadata", {})
        device_id = metadata.get("device_id", "")

        if status == "active":
            return {
                "action": "subscription_active",
                "device_id": device_id,
                "stripe_customer_id": customer_id,
            }
        elif status in ("past_due", "unpaid"):
            return {
                "action": "subscription_payment_issue",
                "device_id": device_id,
                "status": status,
            }
        else:
            return {"action": "subscription_status_change", "status": status}

    def _handle_subscription_deleted(self, event: StripeEvent) -> dict[str, Any]:
        """Handle subscription cancellation."""
        subscription = event.data
        metadata = subscription.get("metadata", {})
        device_id = metadata.get("device_id", "")

        return {
            "action": "downgrade_tier",
            "device_id": device_id,
            "tier": "free",
        }

    def _handle_payment_succeeded(self, event: StripeEvent) -> dict[str, Any]:
        """Handle successful invoice payment (subscription renewal)."""
        invoice = event.data
        customer_id = invoice.get("customer", "")
        subscription_id = invoice.get("subscription", "")

        return {
            "action": "subscription_renewed",
            "stripe_customer_id": customer_id,
            "subscription_id": subscription_id,
        }

    def _handle_payment_failed(self, event: StripeEvent) -> dict[str, Any]:
        """Handle failed invoice payment."""
        invoice = event.data
        customer_id = invoice.get("customer", "")

        return {
            "action": "payment_failed",
            "stripe_customer_id": customer_id,
        }

    def _get_token_pack_amount(self, product_type: str) -> int:
        """Get token amount for a token pack product."""
        token_packs = {
            "token_pack_small": 500,
            "token_pack_medium": 2000,
            "token_pack_large": 5000,
        }
        return token_packs.get(product_type, 0)

    def create_checkout_url(self, device_id: str, product_type: str = "prompt_pack") -> str:
        """Generate Stripe checkout URL.

        Args:
            device_id: User's device fingerprint
            product_type: "prompt_pack" (default) or "early_access"

        Returns:
            Checkout URL (or placeholder if not configured)
        """
        if not self._enabled:
            return f"{self.config.cancel_url}&error=stripe_not_configured"

        # Determine price ID
        if product_type == "beta_operator":
            price_id = self.config.beta_operator_price_id
            mode = "payment"
        elif product_type == "prompt_pack":
            price_id = self.config.prompt_pack_price_id
            mode = "payment"
        elif product_type == "early_access":
            price_id = self.config.early_access_price_id
            mode = "subscription"
        else:
            # Legacy token packs
            price_id = self.config.token_pack_price_ids.get(
                product_type.replace("token_pack_", ""), ""
            )
            mode = "payment"

        if not price_id:
            return f"{self.config.cancel_url}&error=invalid_product"

        logger.info(f"Would create checkout session: device={device_id}, product={product_type}")
        return f"https://checkout.stripe.com/placeholder?device_id={device_id}&product={product_type}"

    async def create_checkout_session(self, device_id: str, product_type: str = "prompt_pack") -> CheckoutSession | None:
        """Create a Stripe checkout session via API.

        Args:
            device_id: User's device fingerprint
            product_type: "prompt_pack" (default) or "early_access"

        Returns:
            CheckoutSession with URL, or None if failed
        """
        if not self._enabled:
            logger.warning("Stripe not configured, cannot create checkout session")
            return None

        try:
            import httpx

            # Determine price ID and mode
            if product_type == "beta_operator":
                price_id = self.config.beta_operator_price_id
                mode = "payment"
            elif product_type == "prompt_pack":
                price_id = self.config.prompt_pack_price_id
                mode = "payment"
            elif product_type == "early_access":
                price_id = self.config.early_access_price_id
                mode = "subscription"
            else:
                # Legacy token packs
                pack_size = product_type.replace("token_pack_", "")
                price_id = self.config.token_pack_price_ids.get(pack_size, "")
                mode = "payment"

            if not price_id:
                logger.error(f"No price ID configured for {product_type}")
                return None

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.STRIPE_API_BASE}/checkout/sessions",
                    auth=(self.config.secret_key, ""),
                    data={
                        "mode": mode,
                        "line_items[0][price]": price_id,
                        "line_items[0][quantity]": "1",
                        "success_url": self.config.success_url,
                        "cancel_url": self.config.cancel_url,
                        "client_reference_id": device_id,
                        "metadata[device_id]": device_id,
                        "metadata[product_type]": product_type,
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Stripe API error: {response.text}")
                    return None

                session_data = response.json()
                return CheckoutSession(
                    id=session_data["id"],
                    url=session_data["url"],
                    device_id=device_id,
                    product_type=product_type,
                )

        except ImportError:
            logger.error("httpx not installed, cannot create checkout session")
            return None
        except Exception as e:
            logger.error(f"Failed to create checkout session: {e}")
            return None

    def get_customer_portal_url(self, customer_id: str) -> str:
        """Get Stripe customer portal URL for managing subscription.

        In production, this would create a portal session via API.
        """
        if not self._enabled or not customer_id:
            return self.config.cancel_url

        # Placeholder - would need API call to create portal session
        return f"https://billing.stripe.com/p/placeholder/{customer_id}"
