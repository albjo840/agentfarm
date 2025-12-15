"""Tests for Pydantic schemas."""

import pytest

from agentfarm.models.schemas import (
    ExecutionResult,
    FileChange,
    PlanStep,
    ReviewComment,
    ReviewResult,
    StepStatus,
    TaskPlan,
    SingleTestResult,
    VerificationResult,
    WorkflowResult,
)


class TestPlanStep:
    def test_create_step(self):
        step = PlanStep(
            id=1,
            description="Create file",
            agent="ExecutorAgent",
            tools=["write_file"],
        )
        assert step.id == 1
        assert step.status == StepStatus.PENDING
        assert step.output is None

    def test_step_with_dependencies(self):
        step = PlanStep(
            id=2,
            description="Test file",
            agent="VerifierAgent",
            dependencies=[1],
        )
        assert step.dependencies == [1]


class TestTaskPlan:
    def test_create_plan(self):
        plan = TaskPlan(
            task_description="Add feature",
            summary="Adding new feature",
            steps=[
                PlanStep(id=1, description="Step 1", agent="ExecutorAgent"),
                PlanStep(id=2, description="Step 2", agent="VerifierAgent"),
            ],
        )
        assert len(plan.steps) == 2
        assert plan.summary == "Adding new feature"


class TestFileChange:
    def test_create_change(self):
        change = FileChange(
            path="src/main.py",
            action="edit",
            diff="+new line",
        )
        assert change.path == "src/main.py"
        assert change.action == "edit"


class TestExecutionResult:
    def test_successful_execution(self):
        result = ExecutionResult(
            success=True,
            step_id=1,
            files_changed=[FileChange(path="test.py", action="create")],
            output="Created test.py",
        )
        assert result.success
        assert len(result.files_changed) == 1

    def test_failed_execution(self):
        result = ExecutionResult(
            success=False,
            step_id=1,
            output="",
            error="File not found",
        )
        assert not result.success
        assert result.error == "File not found"


class TestVerificationResult:
    def test_passing_verification(self):
        result = VerificationResult(
            success=True,
            tests_passed=5,
            tests_failed=0,
            summary="All tests pass",
        )
        assert result.success
        assert result.tests_passed == 5

    def test_failing_verification(self):
        result = VerificationResult(
            success=False,
            tests_passed=3,
            tests_failed=2,
            test_results=[
                SingleTestResult(name="test_a", passed=True),
                SingleTestResult(name="test_b", passed=False),
            ],
            summary="2 tests failed",
        )
        assert not result.success
        assert len(result.test_results) == 2


class TestReviewResult:
    def test_approved_review(self):
        result = ReviewResult(
            approved=True,
            summary="LGTM",
            suggestions=["Consider adding docstring"],
        )
        assert result.approved
        assert len(result.suggestions) == 1

    def test_rejected_review(self):
        result = ReviewResult(
            approved=False,
            comments=[
                ReviewComment(
                    file="main.py",
                    line=10,
                    severity="error",
                    message="Missing error handling",
                )
            ],
            summary="Needs error handling",
        )
        assert not result.approved
        assert result.comments[0].severity == "error"


class TestWorkflowResult:
    def test_successful_workflow(self):
        result = WorkflowResult(
            success=True,
            task_description="Add feature",
            pr_summary="Added feature X",
            total_tokens_used=1500,
        )
        assert result.success
        assert result.total_tokens_used == 1500

    def test_failed_workflow(self):
        result = WorkflowResult(
            success=False,
            task_description="Add feature",
            pr_summary="Failed at planning",
        )
        assert not result.success
