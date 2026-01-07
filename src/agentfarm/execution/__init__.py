"""Execution module for AgentFarm.

Provides parallel execution capabilities for multi-agent workflows.
"""

from agentfarm.execution.parallel import (
    DependencyAnalyzer,
    ParallelExecutionState,
    ParallelExecutor,
)

__all__ = [
    "DependencyAnalyzer",
    "ParallelExecutionState",
    "ParallelExecutor",
]
