"""Pydantic schemas for MCP tool responses."""

from __future__ import annotations

from pydantic import BaseModel


class EvalRunResult(BaseModel):
    """Result from running an evaluation."""

    success: bool
    tests_run: int
    tests_passed: int
    tests_failed: int
    total_score: float
    max_score: float
    percentage: float
    duration_seconds: float
    report_path: str | None = None
    by_category: dict | None = None


class PromptInfo(BaseModel):
    """Information about an agent prompt."""

    agent: str
    prompt: str
    length: int
    has_custom_suffix: bool


class AgentTestResult(BaseModel):
    """Result from testing an agent."""

    agent: str
    success: bool
    output: str
    summary: str
    tokens_used: int | None = None
    duration_seconds: float
