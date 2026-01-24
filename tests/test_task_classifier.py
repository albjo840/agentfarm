"""Tests for TaskClassifier."""

import pytest
from agentfarm.orchestrator import TaskClassifier
from agentfarm.agents.base import AgentContext, TaskType


class TestTaskClassifier:
    """Test task classification."""

    def test_classify_codegen_swedish(self):
        """Test codegen detection with Swedish keywords."""
        assert TaskClassifier.classify("Skapa en funktion som beräknar primtal") == TaskType.CODEGEN
        assert TaskClassifier.classify("Skriv en klass för användarhantering") == TaskType.CODEGEN
        assert TaskClassifier.classify("Implementera en valideringsfunktion") == TaskType.CODEGEN

    def test_classify_codegen_english(self):
        """Test codegen detection with English keywords."""
        assert TaskClassifier.classify("Create a function that validates emails") == TaskType.CODEGEN
        assert TaskClassifier.classify("Write a class for user management") == TaskType.CODEGEN
        assert TaskClassifier.classify("Add a new helper function") == TaskType.CODEGEN

    def test_classify_bugfix(self):
        """Test bugfix detection."""
        assert TaskClassifier.classify("Fixa buggen i login-funktionen") == TaskType.BUGFIX
        assert TaskClassifier.classify("Fix the error in the parser") == TaskType.BUGFIX
        assert TaskClassifier.classify("Koden fungerar inte, korrigera den") == TaskType.BUGFIX
        assert TaskClassifier.classify("Det är ett problem med koden") == TaskType.BUGFIX

    def test_classify_refactor(self):
        """Test refactor detection."""
        assert TaskClassifier.classify("Refaktorera login-modulen") == TaskType.REFACTOR
        assert TaskClassifier.classify("Extract the validation logic into a function") == TaskType.REFACTOR
        assert TaskClassifier.classify("Förenkla koden i utils.py") == TaskType.REFACTOR
        assert TaskClassifier.classify("Rename the variable to something better") == TaskType.REFACTOR

    def test_classify_multistep(self):
        """Test multistep detection."""
        assert TaskClassifier.classify("Skapa ett pygame spel") == TaskType.MULTISTEP
        assert TaskClassifier.classify("Build a complete CLI todo app") == TaskType.MULTISTEP
        assert TaskClassifier.classify("Create a web scraper with tests") == TaskType.MULTISTEP
        assert TaskClassifier.classify("Bygg ett komplett API system") == TaskType.MULTISTEP

    def test_classify_general(self):
        """Test general fallback."""
        assert TaskClassifier.classify("Vad gör denna kod?") == TaskType.GENERAL
        assert TaskClassifier.classify("Explain how this works") == TaskType.GENERAL

    def test_multistep_takes_precedence(self):
        """Test that multistep keywords take precedence."""
        # "Skapa ett spel" matches both CODEGEN (skapa) and MULTISTEP (spel)
        # MULTISTEP should win
        assert TaskClassifier.classify("Skapa ett spel med pygame") == TaskType.MULTISTEP

    def test_get_hints_returns_list(self):
        """Test that hints are returned as a list."""
        hints = TaskClassifier.get_hints(TaskType.CODEGEN)
        assert isinstance(hints, list)
        assert len(hints) > 0

    def test_get_hints_all_types(self):
        """Test hints exist for all task types."""
        for task_type in [TaskType.CODEGEN, TaskType.BUGFIX, TaskType.REFACTOR,
                          TaskType.MULTISTEP, TaskType.GENERAL]:
            hints = TaskClassifier.get_hints(task_type)
            assert len(hints) > 0, f"No hints for {task_type}"

    def test_enrich_context(self):
        """Test context enrichment."""
        base_context = AgentContext(
            task_summary="Skapa en funktion för att validera email",
            relevant_files=["utils.py"],
        )

        enriched = TaskClassifier.enrich_context(base_context, base_context.task_summary)

        # Original fields preserved
        assert enriched.task_summary == base_context.task_summary
        assert enriched.relevant_files == base_context.relevant_files

        # New fields added
        assert enriched.task_type == TaskType.CODEGEN
        assert len(enriched.task_hints) > 0
        assert "write_file" in enriched.task_hints[1].lower()  # Codegen hint

    def test_enrich_context_preserves_constraints(self):
        """Test that constraints are preserved."""
        base_context = AgentContext(
            task_summary="Fix the bug",
            constraints=["No external dependencies", "Python 3.10+"],
        )

        enriched = TaskClassifier.enrich_context(base_context, base_context.task_summary)

        assert enriched.constraints == base_context.constraints
        assert enriched.task_type == TaskType.BUGFIX


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
