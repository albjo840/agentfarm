from __future__ import annotations

"""Monetization module for AgentFarm.

This module provides:
- Affiliate tracking for hardware recommendations
- User management with device fingerprint-based identification
- Token tracking for usage-based billing
- Stripe integration for subscriptions and one-time payments
- Feedback collection system
"""

# Affiliate system (Branch 2)
from agentfarm.monetization.affiliates import AffiliateManager, AffiliateProduct, AffiliateClick

# User management & payments (Branch 1)
from agentfarm.monetization.users import UserManager, UserProfile, SubscriptionTier
from agentfarm.monetization.feedback import FeedbackManager, FeedbackEntry
from agentfarm.monetization.stripe_integration import StripeIntegration

# Unified tier management
from agentfarm.monetization.tiers import TierManager, TierLimits, AccessLevel

__all__ = [
    # Affiliates
    "AffiliateManager",
    "AffiliateProduct",
    "AffiliateClick",
    # Users & Subscriptions
    "UserManager",
    "UserProfile",
    "SubscriptionTier",
    # Feedback
    "FeedbackManager",
    "FeedbackEntry",
    # Payments
    "StripeIntegration",
    # Tier Management
    "TierManager",
    "TierLimits",
    "AccessLevel",
]
