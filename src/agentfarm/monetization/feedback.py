from __future__ import annotations

"""Feedback collection system for AgentFarm."""

import json
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FeedbackCategory(str):
    """Feedback categories."""

    BUG = "bug"
    FEATURE = "feature"
    GENERAL = "general"
    UX = "ux"
    PERFORMANCE = "performance"


class FeedbackEntry(BaseModel):
    """A user feedback submission."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    device_id: str = Field(..., description="User's device fingerprint")
    category: str = Field(default="general", description="bug, feature, general, ux, performance")
    message: str = Field(..., description="Feedback content")
    workflow_id: str | None = Field(default=None, description="Related workflow if applicable")
    contact_email: str | None = Field(default=None, description="Optional contact email")
    user_agent: str | None = Field(default=None, description="Browser/client info")
    page_url: str | None = Field(default=None, description="Page where feedback was submitted")
    rating: int | None = Field(default=None, ge=1, le=5, description="Optional 1-5 rating")
    timestamp: float = Field(default_factory=time.time)
    status: str = Field(default="new", description="new, reviewed, resolved, archived")
    admin_notes: str | None = Field(default=None, description="Internal notes")


class FeedbackManager:
    """Manages feedback collection and storage.

    Stores feedback as individual JSON files for easy backup and review.
    """

    def __init__(self, storage_dir: Path | str) -> None:
        self.storage_dir = Path(storage_dir)
        self.feedback_dir = self.storage_dir / "feedback"
        self.feedback_dir.mkdir(parents=True, exist_ok=True)

    def _feedback_path(self, feedback_id: str) -> Path:
        """Get path to feedback file."""
        return self.feedback_dir / f"{feedback_id}.json"

    def submit(self, feedback: FeedbackEntry) -> str:
        """Save feedback to disk.

        Args:
            feedback: Feedback entry to save

        Returns:
            Feedback ID
        """
        feedback_path = self._feedback_path(feedback.id)
        feedback_path.write_text(feedback.model_dump_json(indent=2))
        return feedback.id

    def create_feedback(
        self,
        device_id: str,
        message: str,
        category: str = "general",
        workflow_id: str | None = None,
        contact_email: str | None = None,
        user_agent: str | None = None,
        page_url: str | None = None,
        rating: int | None = None,
    ) -> FeedbackEntry:
        """Create and save a new feedback entry.

        Args:
            device_id: User's device fingerprint
            message: Feedback content
            category: Feedback category
            workflow_id: Related workflow ID if applicable
            contact_email: Optional contact email
            user_agent: Browser/client info
            page_url: Page URL where feedback was submitted
            rating: Optional 1-5 rating

        Returns:
            Created feedback entry
        """
        feedback = FeedbackEntry(
            device_id=device_id,
            message=message,
            category=category,
            workflow_id=workflow_id,
            contact_email=contact_email,
            user_agent=user_agent,
            page_url=page_url,
            rating=rating,
        )
        self.submit(feedback)
        return feedback

    def get_feedback(self, feedback_id: str) -> FeedbackEntry | None:
        """Get feedback by ID."""
        feedback_path = self._feedback_path(feedback_id)
        if not feedback_path.exists():
            return None

        try:
            data = json.loads(feedback_path.read_text())
            return FeedbackEntry(**data)
        except (json.JSONDecodeError, ValueError):
            return None

    def list_feedback(
        self,
        status: str | None = None,
        category: str | None = None,
        device_id: str | None = None,
        limit: int = 100,
    ) -> list[FeedbackEntry]:
        """List feedback entries with optional filtering.

        Args:
            status: Filter by status (new, reviewed, resolved, archived)
            category: Filter by category
            device_id: Filter by user
            limit: Maximum entries to return

        Returns:
            List of feedback entries, most recent first
        """
        entries: list[FeedbackEntry] = []

        for feedback_file in self.feedback_dir.glob("*.json"):
            try:
                data = json.loads(feedback_file.read_text())
                entry = FeedbackEntry(**data)

                # Apply filters
                if status and entry.status != status:
                    continue
                if category and entry.category != category:
                    continue
                if device_id and entry.device_id != device_id:
                    continue

                entries.append(entry)
            except (json.JSONDecodeError, ValueError):
                continue

        # Sort by timestamp, newest first
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:limit]

    def update_status(self, feedback_id: str, status: str, admin_notes: str | None = None) -> bool:
        """Update feedback status (admin function).

        Args:
            feedback_id: Feedback ID
            status: New status
            admin_notes: Optional admin notes

        Returns:
            True if updated successfully
        """
        feedback = self.get_feedback(feedback_id)
        if not feedback:
            return False

        feedback.status = status
        if admin_notes:
            feedback.admin_notes = admin_notes

        self.submit(feedback)
        return True

    def get_stats(self) -> dict[str, Any]:
        """Get feedback statistics."""
        entries = self.list_feedback(limit=10000)

        status_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        ratings: list[int] = []

        for entry in entries:
            status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
            category_counts[entry.category] = category_counts.get(entry.category, 0) + 1
            if entry.rating:
                ratings.append(entry.rating)

        avg_rating = sum(ratings) / len(ratings) if ratings else None

        return {
            "total_count": len(entries),
            "status_counts": status_counts,
            "category_counts": category_counts,
            "average_rating": avg_rating,
            "ratings_count": len(ratings),
            "new_count": status_counts.get("new", 0),
        }

    def delete_feedback(self, feedback_id: str) -> bool:
        """Delete feedback entry (admin function)."""
        feedback_path = self._feedback_path(feedback_id)
        if feedback_path.exists():
            feedback_path.unlink()
            return True
        return False

    def export_feedback(self, format: str = "json") -> str:
        """Export all feedback as JSON or CSV.

        Args:
            format: "json" or "csv"

        Returns:
            Exported data as string
        """
        entries = self.list_feedback(limit=100000)

        if format == "csv":
            lines = ["id,device_id,category,message,rating,status,timestamp,contact_email"]
            for entry in entries:
                # Escape message for CSV
                msg = entry.message.replace('"', '""').replace("\n", " ")
                lines.append(
                    f'"{entry.id}","{entry.device_id}","{entry.category}","{msg}",'
                    f'{entry.rating or ""},"{entry.status}",{entry.timestamp},"{entry.contact_email or ""}"'
                )
            return "\n".join(lines)
        else:
            return json.dumps([e.model_dump() for e in entries], indent=2)
