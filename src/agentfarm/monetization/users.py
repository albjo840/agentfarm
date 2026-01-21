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
    TRYOUT = "tryout"  # Has tried the service (1 free workflow)
    BETA_OPERATOR = "beta_operator"  # Paid tier: 10 workflows + premium features
    EARLY_ACCESS = "early_access"
    PRO = "pro"


class UserProfile(BaseModel):
    """User profile for prompt tracking and subscriptions."""

    device_id: str = Field(..., description="Unique device fingerprint")
    email: str | None = Field(default=None, description="Optional email for account linking")
    tier: SubscriptionTier = Field(default=SubscriptionTier.FREE)
    stripe_customer_id: str | None = Field(default=None)
    tokens_remaining: int = Field(default=0, description="Legacy - use prompts_remaining")
    tokens_used_total: int = Field(default=0, description="Lifetime token usage")
    prompts_remaining: int = Field(default=0, description="Available prompts (workflows)")
    prompts_used_total: int = Field(default=0, description="Lifetime prompt usage")
    company_context: str | None = Field(default=None, description="Custom company instructions")
    agent_custom_prompts: dict[str, str] = Field(
        default_factory=dict,
        description="Custom system prompt additions per agent: {agent_id: custom_text}"
    )
    is_admin: bool = Field(default=False, description="Admin has unlimited access")
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
        """Get existing user or create new one with 1 free tryout workflow."""
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

        # Create new user with 1 FREE tryout workflow (no guest mode)
        user = UserProfile(
            device_id=device_id,
            tier=SubscriptionTier.TRYOUT,
            prompts_remaining=1,  # 1 free workflow to try
        )
        self._save_user(user)
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
        total_prompts_used = sum(u.prompts_used_total for u in users)
        tier_counts = {tier.value: 0 for tier in SubscriptionTier}
        for user in users:
            tier_counts[user.tier.value] += 1

        return {
            "total_users": len(users),
            "tier_counts": tier_counts,
            "total_tokens_used": total_tokens_used,
            "total_prompts_used": total_prompts_used,
            "transactions_count": len(transactions),
            "active_last_24h": sum(1 for u in users if time.time() - u.last_active < 86400),
        }

    # =========================================================================
    # PROMPT-BASED ACCESS (New Model)
    # =========================================================================

    def can_run_workflow(self, device_id: str) -> tuple[bool, str]:
        """Check if user can run a workflow.

        Returns:
            Tuple of (allowed, reason)
        """
        user = self.get_or_create_user(device_id)

        # Admins have unlimited access
        if user.is_admin:
            return True, "admin"

        # Early Access tier has unlimited prompts
        if user.tier == SubscriptionTier.EARLY_ACCESS:
            return True, "early_access"

        # Check prompt balance
        if user.prompts_remaining > 0:
            return True, f"{user.prompts_remaining} prompts remaining"

        return False, "no_prompts"

    def use_prompt(self, device_id: str, workflow_id: str | None = None) -> tuple[bool, int]:
        """Use one prompt for a workflow. Returns (success, remaining).

        Admins and Early Access don't consume prompts.
        """
        user = self.get_or_create_user(device_id)

        # Admins don't consume prompts
        if user.is_admin:
            user.prompts_used_total += 1
            self._save_user(user)
            return True, -1  # -1 indicates unlimited

        # Early Access doesn't consume prompts
        if user.tier == SubscriptionTier.EARLY_ACCESS:
            user.prompts_used_total += 1
            self._save_user(user)
            return True, -1

        # Check and deduct prompt
        if user.prompts_remaining <= 0:
            return False, 0

        user.prompts_remaining -= 1
        user.prompts_used_total += 1
        self._save_user(user)
        self._log_transaction(device_id, -1, "workflow_prompt", workflow_id)

        return True, user.prompts_remaining

    def add_prompts(self, device_id: str, amount: int, reason: str = "purchase") -> int:
        """Add prompts to user's balance. Returns new balance."""
        user = self.get_or_create_user(device_id)
        user.prompts_remaining += amount
        self._save_user(user)
        self._log_transaction(device_id, amount, f"prompts_{reason}")
        return user.prompts_remaining

    def get_prompts_remaining(self, device_id: str) -> int:
        """Get user's remaining prompts. Returns -1 for unlimited (admin/early_access)."""
        user = self.get_or_create_user(device_id)
        if user.is_admin or user.tier == SubscriptionTier.EARLY_ACCESS:
            return -1
        return user.prompts_remaining

    # =========================================================================
    # CUSTOM AGENT PROMPTS
    # =========================================================================

    def set_agent_custom_prompt(self, device_id: str, agent_id: str, custom_text: str) -> None:
        """Set custom system prompt addition for an agent.

        Args:
            device_id: User's device fingerprint
            agent_id: Agent ID (planner, executor, verifier, reviewer, ux)
            custom_text: Custom text to append to agent's system prompt
        """
        user = self.get_or_create_user(device_id)
        if not user.agent_custom_prompts:
            user.agent_custom_prompts = {}
        user.agent_custom_prompts[agent_id] = custom_text
        self._save_user(user)

    def get_agent_custom_prompt(self, device_id: str, agent_id: str) -> str | None:
        """Get custom system prompt addition for an agent."""
        user = self.get_user(device_id)
        if not user or not user.agent_custom_prompts:
            return None
        return user.agent_custom_prompts.get(agent_id)

    def get_all_agent_custom_prompts(self, device_id: str) -> dict[str, str]:
        """Get all custom agent prompts for a user."""
        user = self.get_user(device_id)
        if not user or not user.agent_custom_prompts:
            return {}
        return user.agent_custom_prompts

    def clear_agent_custom_prompt(self, device_id: str, agent_id: str) -> None:
        """Remove custom prompt for an agent."""
        user = self.get_or_create_user(device_id)
        if user.agent_custom_prompts and agent_id in user.agent_custom_prompts:
            del user.agent_custom_prompts[agent_id]
            self._save_user(user)

    # =========================================================================
    # ADMIN MANAGEMENT
    # =========================================================================

    def set_admin(self, device_id: str, is_admin: bool = True) -> UserProfile:
        """Set admin status for a user."""
        user = self.get_or_create_user(device_id)
        user.is_admin = is_admin
        self._save_user(user)
        return user

    def is_admin(self, device_id: str) -> bool:
        """Check if user is an admin."""
        user = self.get_user(device_id)
        return user.is_admin if user else False

    def is_beta_operator(self, device_id: str) -> bool:
        """Check if user is a Beta Operator (paid tier with premium features)."""
        user = self.get_user(device_id)
        if not user:
            return False
        # Admins and higher tiers also have beta operator privileges
        if user.is_admin:
            return True
        return user.tier in (SubscriptionTier.BETA_OPERATOR, SubscriptionTier.EARLY_ACCESS, SubscriptionTier.PRO)

    def upgrade_to_beta_operator(self, device_id: str, stripe_customer_id: str | None = None) -> UserProfile:
        """Upgrade user to Beta Operator tier with 10 workflows."""
        user = self.get_or_create_user(device_id)
        user.tier = SubscriptionTier.BETA_OPERATOR
        user.prompts_remaining += 10  # Add 10 workflows
        if stripe_customer_id:
            user.stripe_customer_id = stripe_customer_id
        self._save_user(user)
        self._log_transaction(device_id, 10, "beta_operator_upgrade")
        return user
