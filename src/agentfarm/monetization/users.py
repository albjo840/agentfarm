from __future__ import annotations

"""User management with device fingerprint-based identification and token tracking."""

import json
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SubscriptionTier(str, Enum):
    """Subscription tiers for AgentFarm."""

    FREE = "free"
    EARLY_ACCESS = "early_access"
    PRO = "pro"


class UserProfile(BaseModel):
    """User profile for token tracking and subscriptions."""

    device_id: str = Field(..., description="Unique device fingerprint")
    email: str | None = Field(default=None, description="Optional email for account linking")
    tier: SubscriptionTier = Field(default=SubscriptionTier.FREE)
    stripe_customer_id: str | None = Field(default=None)
    tokens_remaining: int = Field(default=100, description="Available tokens")
    tokens_used_total: int = Field(default=0, description="Lifetime token usage")
    company_context: str | None = Field(default=None, description="Custom company instructions")
    created_at: float = Field(default_factory=time.time)
    last_active: float = Field(default_factory=time.time)


class TokenTransaction(BaseModel):
    """Record of token usage or purchase."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_device_id: str
    amount: int = Field(..., description="Positive for purchases, negative for usage")
    reason: str = Field(..., description="workflow_run, token_pack_small, subscription_refresh, etc.")
    workflow_id: str | None = None
    timestamp: float = Field(default_factory=time.time)


class UserManager:
    """Manages user profiles and token balances.

    Uses device fingerprints for identification - no passwords required.
    Data is stored as JSON files in .agentfarm/users/
    """

    def __init__(self, storage_dir: Path | str) -> None:
        self.storage_dir = Path(storage_dir)
        self.users_dir = self.storage_dir / "users"
        self.tokens_dir = self.storage_dir / "tokens"
        self.contexts_dir = self.storage_dir / "contexts"

        # Create directories
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.tokens_dir.mkdir(parents=True, exist_ok=True)
        self.contexts_dir.mkdir(parents=True, exist_ok=True)

    def _user_path(self, device_id: str) -> Path:
        """Get path to user profile file."""
        # Sanitize device_id for filesystem
        safe_id = "".join(c for c in device_id if c.isalnum() or c in "-_")[:64]
        return self.users_dir / f"{safe_id}.json"

    def get_or_create_user(self, device_id: str) -> UserProfile:
        """Get existing user or create new one with free tier."""
        user_path = self._user_path(device_id)

        if user_path.exists():
            try:
                data = json.loads(user_path.read_text())
                user = UserProfile(**data)
                # Update last_active
                user.last_active = time.time()
                self._save_user(user)
                return user
            except (json.JSONDecodeError, ValueError):
                pass

        # Create new user
        user = UserProfile(device_id=device_id)
        self._save_user(user)
        self._log_transaction(device_id, 100, "initial_grant")
        return user

    def _save_user(self, user: UserProfile) -> None:
        """Save user profile to disk."""
        user_path = self._user_path(user.device_id)
        user_path.write_text(user.model_dump_json(indent=2))

    def get_user(self, device_id: str) -> UserProfile | None:
        """Get user by device ID, returns None if not found."""
        user_path = self._user_path(device_id)
        if not user_path.exists():
            return None
        try:
            data = json.loads(user_path.read_text())
            return UserProfile(**data)
        except (json.JSONDecodeError, ValueError):
            return None

    def update_tokens(self, device_id: str, amount: int, reason: str, workflow_id: str | None = None) -> int:
        """Add/subtract tokens, return new balance.

        Args:
            device_id: User's device fingerprint
            amount: Positive to add, negative to subtract
            reason: Description of transaction
            workflow_id: Optional workflow ID for tracking

        Returns:
            New token balance
        """
        user = self.get_or_create_user(device_id)

        # For Early Access tier, tokens are unlimited
        if user.tier == SubscriptionTier.EARLY_ACCESS and amount < 0:
            # Still track usage but don't deduct
            user.tokens_used_total += abs(amount)
            self._save_user(user)
            self._log_transaction(device_id, amount, reason, workflow_id)
            return user.tokens_remaining  # Return unchanged balance

        user.tokens_remaining += amount
        if amount < 0:
            user.tokens_used_total += abs(amount)

        # Don't go below 0
        if user.tokens_remaining < 0:
            user.tokens_remaining = 0

        self._save_user(user)
        self._log_transaction(device_id, amount, reason, workflow_id)
        return user.tokens_remaining

    def check_tokens(self, device_id: str, required: int) -> bool:
        """Check if user has enough tokens.

        Early Access users always have enough tokens.
        """
        user = self.get_or_create_user(device_id)
        if user.tier == SubscriptionTier.EARLY_ACCESS:
            return True
        return user.tokens_remaining >= required

    def use_tokens(self, device_id: str, amount: int, reason: str = "workflow_run", workflow_id: str | None = None) -> tuple[bool, int]:
        """Attempt to use tokens. Returns (success, new_balance).

        Args:
            device_id: User's device fingerprint
            amount: Number of tokens to use (positive number)
            reason: Description of usage
            workflow_id: Optional workflow ID

        Returns:
            Tuple of (success, new_balance)
        """
        if not self.check_tokens(device_id, amount):
            user = self.get_user(device_id)
            return False, user.tokens_remaining if user else 0

        new_balance = self.update_tokens(device_id, -amount, reason, workflow_id)
        return True, new_balance

    def _log_transaction(self, device_id: str, amount: int, reason: str, workflow_id: str | None = None) -> None:
        """Log a token transaction."""
        transaction = TokenTransaction(
            user_device_id=device_id,
            amount=amount,
            reason=reason,
            workflow_id=workflow_id,
        )

        # Append to transactions log
        log_path = self.tokens_dir / "transactions.json"
        transactions: list[dict[str, Any]] = []

        if log_path.exists():
            try:
                transactions = json.loads(log_path.read_text())
            except json.JSONDecodeError:
                transactions = []

        transactions.append(transaction.model_dump())

        # Keep last 10000 transactions
        if len(transactions) > 10000:
            transactions = transactions[-10000:]

        log_path.write_text(json.dumps(transactions, indent=2))

    def get_transactions(self, device_id: str | None = None, limit: int = 100) -> list[TokenTransaction]:
        """Get recent transactions, optionally filtered by device_id."""
        log_path = self.tokens_dir / "transactions.json"
        if not log_path.exists():
            return []

        try:
            data = json.loads(log_path.read_text())
            transactions = [TokenTransaction(**t) for t in data]
        except (json.JSONDecodeError, ValueError):
            return []

        if device_id:
            transactions = [t for t in transactions if t.user_device_id == device_id]

        # Return most recent first
        transactions.reverse()
        return transactions[:limit]

    def set_company_context(self, device_id: str, context: str) -> None:
        """Save company context/instructions for a user."""
        user = self.get_or_create_user(device_id)
        user.company_context = context
        self._save_user(user)

        # Also save to contexts directory for backup
        context_path = self.contexts_dir / f"{user.device_id[:16]}.txt"
        context_path.write_text(context)

    def get_company_context(self, device_id: str) -> str | None:
        """Get company context for a user."""
        user = self.get_user(device_id)
        return user.company_context if user else None

    def upgrade_tier(self, device_id: str, tier: SubscriptionTier, stripe_customer_id: str | None = None) -> UserProfile:
        """Upgrade user to a new tier."""
        user = self.get_or_create_user(device_id)
        user.tier = tier
        if stripe_customer_id:
            user.stripe_customer_id = stripe_customer_id
        self._save_user(user)
        self._log_transaction(device_id, 0, f"tier_upgrade_{tier.value}")
        return user

    def refresh_subscription_tokens(self, device_id: str, tokens: int = 1000) -> int:
        """Refresh tokens for subscription renewal."""
        return self.update_tokens(device_id, tokens, "subscription_refresh")

    def list_users(self, limit: int = 100) -> list[UserProfile]:
        """List all users (admin function)."""
        users: list[UserProfile] = []
        for user_file in self.users_dir.glob("*.json"):
            try:
                data = json.loads(user_file.read_text())
                users.append(UserProfile(**data))
            except (json.JSONDecodeError, ValueError):
                continue

        # Sort by last_active, most recent first
        users.sort(key=lambda u: u.last_active, reverse=True)
        return users[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get usage statistics (admin function)."""
        users = self.list_users(limit=10000)
        transactions = self.get_transactions(limit=10000)

        total_tokens_used = sum(u.tokens_used_total for u in users)
        tier_counts = {tier.value: 0 for tier in SubscriptionTier}
        for user in users:
            tier_counts[user.tier.value] += 1

        return {
            "total_users": len(users),
            "tier_counts": tier_counts,
            "total_tokens_used": total_tokens_used,
            "transactions_count": len(transactions),
            "active_last_24h": sum(1 for u in users if time.time() - u.last_active < 86400),
        }
