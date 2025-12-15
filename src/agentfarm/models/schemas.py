from __future__ import annotations

"""Pydantic schemas for agent communication."""

from enum import Enum
from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    """Status of a plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    """A single step in a task plan."""

    id: int = Field(..., description="Step number")
    description: str = Field(..., description="What this step accomplishes")
    agent: str = Field(..., description="Which agent handles this step")
    tools: list[str] = Field(default_factory=list, description="Tools needed")
    dependencies: list[int] = Field(default_factory=list, description="Step IDs this depends on")
    status: StepStatus = Field(default=StepStatus.PENDING)
    output: str | None = Field(default=None, description="Step output/result")


class TaskPlan(BaseModel):
    """A complete plan for a task."""

    task_description: str = Field(..., description="Original task description")
    summary: str = Field(..., description="Brief summary of the approach")
    steps: list[PlanStep] = Field(..., description="Steps to complete the task")
    estimated_tokens: int | None = Field(default=None, description="Estimated token usage")


class FileChange(BaseModel):
    """A file change made during execution."""

    path: str = Field(..., description="File path")
    action: str = Field(..., description="create, edit, or delete")
    diff: str | None = Field(default=None, description="Diff of changes")


class ExecutionResult(BaseModel):
    """Result from ExecutorAgent."""

    success: bool
    step_id: int
    files_changed: list[FileChange] = Field(default_factory=list)
    output: str = Field(..., description="Execution output/summary")
    error: str | None = Field(default=None)


class SingleTestResult(BaseModel):
    """Result from a single test."""

    name: str
    passed: bool
    output: str | None = None
    duration_ms: int | None = None


class VerificationResult(BaseModel):
    """Result from VerifierAgent."""

    success: bool
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    test_results: list[SingleTestResult] = Field(default_factory=list)
    lint_issues: list[str] = Field(default_factory=list)
    type_errors: list[str] = Field(default_factory=list)
    coverage_percent: float | None = None
    summary: str = ""


class ReviewComment(BaseModel):
    """A review comment on code."""

    file: str
    line: int | None = None
    severity: str = Field(..., description="info, warning, error")
    message: str


class ReviewResult(BaseModel):
    """Result from ReviewerAgent."""

    approved: bool
    comments: list[ReviewComment] = Field(default_factory=list)
    summary: str = ""
    suggestions: list[str] = Field(default_factory=list)


class WorkflowResult(BaseModel):
    """Complete result of PLAN→EXECUTE→VERIFY→REVIEW workflow."""

    success: bool
    task_description: str
    plan: TaskPlan | None = None
    execution_results: list[ExecutionResult] = Field(default_factory=list)
    verification: VerificationResult | None = None
    review: ReviewResult | None = None
    pr_summary: str | None = Field(default=None, description="Generated PR description")
    total_tokens_used: int | None = None
