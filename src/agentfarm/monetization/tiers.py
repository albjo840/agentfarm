from __future__ import annotations

"""Tier management for AgentFarm - Unified access control.

This module ties together the monetization components to provide
a unified tier system:

PUBLIC TIER (Free):
- Access to hardware recommendations with affiliate links
- Limited workflow executions per day
- No company context injection
- Revenue: Affiliate clicks

PAID TIER (Early Access):
- Unlimited workflow executions
- Company context injection (Secure Vault)
- Priority support
- Anonymized feedback loop
- Revenue: Stripe subscription

Architecture:
┌─────────────────────────────────────────────────────────┐
│                    TierManager                          │
│  Coordinates: UserManager + StripeIntegration +        │
│               AffiliateManager                          │
└─────────────────────────────────────────────────────────┘
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from agentfarm.monetization.users import UserManager, UserProfile, SubscriptionTier
from agentfarm.monetization.stripe_integration import StripeIntegration
from agentfarm.monetization.affiliates import AffiliateManager

# Optional import for SecureVault
try:
    from agentfarm.security.vault import SecureVault, VaultSession
    VAULT_AVAILABLE = True
except ImportError:
    VAULT_AVAILABLE = False
    SecureVault = None  # type: ignore
    VaultSession = None  # type: ignore

logger = logging.getLogger(__name__)


class AccessLevel(str, Enum):
    """Access levels for features."""

    BLOCKED = "blocked"       # Rate limited or not authenticated
    FREE = "free"             # Basic access
    EARLY_ACCESS = "early_access"  # Full access


@dataclass
class TierLimits:
    """Limits for each tier."""

    workflows_per_day: int
    max_context_chars: int
    can_upload_files: bool
    priority_queue: bool

    @classmethod
    def free(cls) -> "TierLimits":
        return cls(
            workflows_per_day=5,
            max_context_chars=0,  # No context injection for free
            can_upload_files=False,
            priority_queue=False,
        )

    @classmethod
    def early_access(cls) -> "TierLimits":
        return cls(
            workflows_per_day=-1,  # Unlimited
            max_context_chars=50000,
            can_upload_files=True,
            priority_queue=True,
        )


class TierManager:
    """Unified tier management for AgentFarm.

    Coordinates between user management, payment processing,
    and affiliate tracking to provide consistent access control.
    """

    def __init__(
        self,
        storage_dir: Path | str,
        stripe_config: dict[str, str] | None = None,
        enable_vault: bool = True,
    ) -> None:
        """Initialize tier manager.

        Args:
            storage_dir: Directory for persistent storage (.agentfarm/)
            stripe_config: Optional Stripe configuration override
            enable_vault: Whether to enable SecureVault for Early Access
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.users = UserManager(self.storage_dir)
        self.affiliates = AffiliateManager(self.storage_dir)
        self.stripe = StripeIntegration()

        # Initialize SecureVault if available and enabled
        self.vault: SecureVault | None = None
        self._vault_sessions: dict[str, VaultSession] = {}  # device_id -> session

        if enable_vault and VAULT_AVAILABLE:
            try:
                self.vault = SecureVault()
                if self.vault.is_available:
                    logger.info("SecureVault initialized (Docker available)")
                else:
                    logger.warning("SecureVault: Docker not available")
                    self.vault = None
            except Exception as e:
                logger.warning("Failed to initialize SecureVault: %s", e)
                self.vault = None

        logger.info(
            "TierManager initialized (Stripe: %s, Vault: %s, Users: %d)",
            "enabled" if self.stripe.enabled else "disabled",
            "enabled" if self.vault else "disabled",
            len(self.users.list_users()),
        )

    def get_user_tier(self, device_id: str) -> tuple[AccessLevel, TierLimits]:
        """Get access level and limits for a user.

        Args:
            device_id: User's device fingerprint

        Returns:
            Tuple of (access_level, limits)
        """
        user = self.users.get_or_create_user(device_id)

        if user.tier == SubscriptionTier.EARLY_ACCESS:
            return AccessLevel.EARLY_ACCESS, TierLimits.early_access()
        else:
            return AccessLevel.FREE, TierLimits.free()

    def check_workflow_access(self, device_id: str) -> tuple[bool, str]:
        """Check if user can run a workflow.

        Args:
            device_id: User's device fingerprint

        Returns:
            Tuple of (allowed, reason)
        """
        access, limits = self.get_user_tier(device_id)

        if access == AccessLevel.EARLY_ACCESS:
            return True, "early_access"

        # Check daily limit for free users
        user = self.users.get_or_create_user(device_id)
        daily_workflows = self._count_daily_workflows(device_id)

        if limits.workflows_per_day > 0 and daily_workflows >= limits.workflows_per_day:
            return False, f"Daily limit reached ({limits.workflows_per_day} workflows/day)"

        return True, "free_tier"

    def _count_daily_workflows(self, device_id: str) -> int:
        """Count workflows run today by user.

        Note: This would normally check workflow persistence.
        For now, returns 0 (no limit enforcement yet).
        """
        # TODO: Integrate with WorkflowPersistence to count actual runs
        return 0

    def get_company_context(self, device_id: str) -> str | None:
        """Get company context for a user (Early Access only).

        Args:
            device_id: User's device fingerprint

        Returns:
            Company context string or None if not available/allowed
        """
        access, limits = self.get_user_tier(device_id)

        if not limits.max_context_chars:
            return None  # Free tier can't use context

        user = self.users.get_or_create_user(device_id)
        return user.company_context

    def set_company_context(self, device_id: str, context: str) -> tuple[bool, str]:
        """Set company context for a user.

        Args:
            device_id: User's device fingerprint
            context: Company context/persona text

        Returns:
            Tuple of (success, message)
        """
        access, limits = self.get_user_tier(device_id)

        if not limits.max_context_chars:
            return False, "Company context requires Early Access subscription"

        if len(context) > limits.max_context_chars:
            return False, f"Context too long (max {limits.max_context_chars} chars)"

        self.users.set_company_context(device_id, context)
        return True, f"Context saved ({len(context)} chars)"

    async def create_checkout(self, device_id: str, product: str = "early_access") -> str | None:
        """Create Stripe checkout URL for subscription.

        Args:
            device_id: User's device fingerprint
            product: Product type ("early_access" or token pack)

        Returns:
            Checkout URL or None if Stripe not configured
        """
        if not self.stripe.enabled:
            return None

        session = await self.stripe.create_checkout_session(device_id, product)
        return session.url if session else None

    def handle_payment_success(self, device_id: str, product: str) -> None:
        """Handle successful payment.

        Args:
            device_id: User's device fingerprint
            product: Product purchased
        """
        if product == "early_access":
            self.users.upgrade_tier(device_id, SubscriptionTier.EARLY_ACCESS)
            logger.info("User %s upgraded to Early Access", device_id[:8])

    # ===========================================
    # SECURE VAULT METHODS (Early Access only)
    # ===========================================

    async def get_vault_session(self, device_id: str) -> VaultSession | None:
        """Get or create a vault session for a user.

        Only available for Early Access users. Returns None for free tier.

        Args:
            device_id: User's device fingerprint

        Returns:
            VaultSession or None if not available/allowed
        """
        if not self.vault:
            return None

        access, limits = self.get_user_tier(device_id)
        if access != AccessLevel.EARLY_ACCESS:
            logger.debug("Vault access denied for %s (tier: %s)", device_id[:8], access.value)
            return None

        # Check for existing session
        existing = self._vault_sessions.get(device_id)
        if existing and not existing.is_expired:
            return existing

        # Create new session
        try:
            session = await self.vault.create_session(device_id)
            self._vault_sessions[device_id] = session
            logger.info("Created vault session for %s", device_id[:8])
            return session
        except Exception as e:
            logger.error("Failed to create vault session: %s", e)
            return None

    async def store_in_vault(
        self,
        device_id: str,
        filename: str,
        content: str | bytes,
    ) -> tuple[bool, str]:
        """Store a document in the user's vault.

        Only available for Early Access users.

        Args:
            device_id: User's device fingerprint
            filename: Document filename
            content: Document content

        Returns:
            Tuple of (success, message)
        """
        session = await self.get_vault_session(device_id)
        if not session:
            return False, "Vault access requires Early Access subscription"

        try:
            path = await self.vault.store_document(session, filename, content)
            return True, f"Document stored: {path}"
        except Exception as e:
            return False, f"Failed to store document: {e}"

    async def retrieve_from_vault(
        self,
        device_id: str,
        filename: str,
    ) -> tuple[bytes | None, str]:
        """Retrieve a document from the user's vault.

        Args:
            device_id: User's device fingerprint
            filename: Document to retrieve

        Returns:
            Tuple of (content or None, message)
        """
        session = await self.get_vault_session(device_id)
        if not session:
            return None, "Vault access requires Early Access subscription"

        try:
            content = await self.vault.retrieve_document(session, filename)
            return content, "Document retrieved"
        except Exception as e:
            return None, f"Failed to retrieve document: {e}"

    async def list_vault_documents(self, device_id: str) -> list[str]:
        """List documents in user's vault.

        Args:
            device_id: User's device fingerprint

        Returns:
            List of document filenames (empty if not available)
        """
        session = await self.get_vault_session(device_id)
        if not session:
            return []

        try:
            return await self.vault.list_documents(session)
        except Exception:
            return []

    async def close_vault_session(self, device_id: str) -> bool:
        """Close and cleanup a user's vault session.

        Args:
            device_id: User's device fingerprint

        Returns:
            True if session was closed, False otherwise
        """
        session = self._vault_sessions.pop(device_id, None)
        if not session or not self.vault:
            return False

        try:
            await self.vault.destroy_session(session)
            logger.info("Closed vault session for %s", device_id[:8])
            return True
        except Exception as e:
            logger.error("Failed to close vault session: %s", e)
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get tier statistics."""
        users = self.users.list_users()

        tier_counts = {
            "free": 0,
            "early_access": 0,
        }
        for user in users:
            tier_counts[user.tier.value] = tier_counts.get(user.tier.value, 0) + 1

        affiliate_stats = self.affiliates.get_click_stats(days=30)

        # Vault statistics
        vault_stats = self.vault.get_stats() if self.vault else {"available": False}
        vault_stats["active_user_sessions"] = len(self._vault_sessions)

        return {
            "total_users": len(users),
            "tier_distribution": tier_counts,
            "affiliate_clicks_30d": affiliate_stats.get("total_clicks", 0),
            "stripe_enabled": self.stripe.enabled,
            "vault": vault_stats,
        }
