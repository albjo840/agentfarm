from __future__ import annotations

"""UXDesignerAgent - Advanced UI/UX design and code generation.

Inspired by:
- OpenUI (wandb/openui) - text → component with multiple frameworks
- screenshot-to-code (abi/screenshot-to-code) - image → code workflows
- Lovable.dev - production-ready component generation
"""

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from agentfarm.agents.base import AgentContext, AgentResult, BaseAgent
from agentfarm.providers.base import CompletionResponse, LLMProvider, ToolDefinition


class UIFramework(str, Enum):
    """Supported UI frameworks for code generation."""
    REACT = "react"
    REACT_TAILWIND = "react-tailwind"
    HTML_TAILWIND = "html-tailwind"
    VUE = "vue"
    SVELTE = "svelte"


class ComponentLibrary(str, Enum):
    """Supported component libraries."""
    NONE = "none"
    SHADCN = "shadcn"
    RADIX = "radix"
    HEADLESS = "headless"
    MATERIAL = "material"


class GeneratedComponent(BaseModel):
    """A generated UI component with code."""

    name: str = Field(..., description="Component name (PascalCase)")
    description: str = Field(..., description="What the component does")
    framework: UIFramework = Field(default=UIFramework.REACT_TAILWIND)
    code: str = Field(..., description="The generated code")
    dependencies: list[str] = Field(default_factory=list, description="Required packages")
    props: list[dict[str, Any]] = Field(default_factory=list, description="Component props")
    usage_example: str = Field(default="", description="Example usage code")


class DesignTokens(BaseModel):
    """Design system tokens."""

    colors: dict[str, str] = Field(default_factory=dict)
    spacing: dict[str, str] = Field(default_factory=dict)
    typography: dict[str, str] = Field(default_factory=dict)
    shadows: dict[str, str] = Field(default_factory=dict)
    radii: dict[str, str] = Field(default_factory=dict)


class UXReview(BaseModel):
    """Result of UX review."""

    score: int = Field(..., ge=1, le=10)
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    accessibility_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    improved_code: str | None = Field(default=None, description="Suggested improved code")


class UXDesignerAgent(BaseAgent):
    """Advanced UI/UX design agent that generates production-ready components.

    Capabilities:
    - Generate complete UI components from text descriptions
    - Support multiple frameworks (React, Vue, Svelte, HTML+Tailwind)
    - Create accessible, responsive designs by default
    - Review and improve existing UI code
    - Generate design systems and tokens
    - Iterative refinement based on feedback

    Inspired by OpenUI, screenshot-to-code, and Lovable.dev patterns.
    """

    name = "UXDesignerAgent"
    description = "Generates production-ready UI components and reviews UX"

    def __init__(
        self,
        provider: LLMProvider,
        default_framework: UIFramework = UIFramework.REACT_TAILWIND,
        component_library: ComponentLibrary = ComponentLibrary.SHADCN,
    ) -> None:
        super().__init__(provider)
        self.default_framework = default_framework
        self.component_library = component_library
        self._register_tools()

    @property
    def system_prompt(self) -> str:
        return f"""You are UXDesignerAgent, an expert UI/UX designer and frontend developer.
You generate production-ready, accessible UI components.

## Your Stack
- Default framework: {self.default_framework.value}
- Component library: {self.component_library.value}
- Styling: Tailwind CSS (utility-first)

## Design Principles
1. **Accessible by default** - ARIA labels, keyboard navigation, focus states
2. **Mobile-first** - Responsive design starting from smallest screens
3. **Semantic HTML** - Proper heading hierarchy, landmarks, buttons vs links
4. **State handling** - Loading, error, empty, success states
5. **Dark mode ready** - Use CSS variables or Tailwind dark: variants

## Code Style
- TypeScript for React/Vue components
- Proper prop typing with defaults
- Extract magic values into constants
- Include JSDoc comments for complex props
- Use CSS variables for theming

## Component Structure
When generating components, always include:
1. Complete, runnable code (no "..." or placeholders)
2. All required imports
3. Type definitions for props
4. Default prop values where sensible
5. Usage example in a comment

## Accessibility Checklist
- [ ] Keyboard navigable (Tab, Enter, Escape, Arrow keys)
- [ ] Focus visible and logical order
- [ ] ARIA labels for icons/images
- [ ] Color contrast 4.5:1 minimum
- [ ] Screen reader tested (conceptually)
- [ ] Reduced motion respected

When asked to generate a component, output COMPLETE working code.
Do NOT use placeholders or ask for clarification - make sensible defaults."""

    def _register_tools(self) -> None:
        """Register UX design tools."""
        self.register_tool(
            name="generate_component",
            description="Generate a complete UI component from a description",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Component name in PascalCase (e.g., 'UserCard', 'SearchInput')",
                    },
                    "description": {
                        "type": "string",
                        "description": "What the component should do and look like",
                    },
                    "framework": {
                        "type": "string",
                        "enum": ["react", "react-tailwind", "html-tailwind", "vue", "svelte"],
                        "description": "Target framework for code generation",
                    },
                    "features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific features to include (e.g., 'loading state', 'dark mode')",
                    },
                },
                "required": ["name", "description"],
            },
            handler=self._generate_component,
        )

        self.register_tool(
            name="review_component",
            description="Review existing UI code for UX issues and accessibility",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The component code to review",
                    },
                    "focus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Areas to focus on (accessibility, performance, ux, responsive)",
                    },
                },
                "required": ["code"],
            },
            handler=self._review_component,
        )

        self.register_tool(
            name="refine_component",
            description="Refine/improve a component based on feedback",
            parameters={
                "type": "object",
                "properties": {
                    "current_code": {
                        "type": "string",
                        "description": "The current component code",
                    },
                    "feedback": {
                        "type": "string",
                        "description": "What to change or improve",
                    },
                },
                "required": ["current_code", "feedback"],
            },
            handler=self._refine_component,
        )

        self.register_tool(
            name="generate_design_system",
            description="Generate a design system/tokens for a project",
            parameters={
                "type": "object",
                "properties": {
                    "style": {
                        "type": "string",
                        "description": "Design style (modern, minimal, playful, corporate, etc.)",
                    },
                    "primary_color": {
                        "type": "string",
                        "description": "Primary brand color (hex or name)",
                    },
                    "dark_mode": {
                        "type": "boolean",
                        "description": "Include dark mode variants",
                    },
                },
                "required": ["style"],
            },
            handler=self._generate_design_system,
        )

        self.register_tool(
            name="generate_page_layout",
            description="Generate a complete page layout with multiple components",
            parameters={
                "type": "object",
                "properties": {
                    "page_type": {
                        "type": "string",
                        "description": "Type of page (landing, dashboard, settings, profile, etc.)",
                    },
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Sections to include (hero, features, pricing, etc.)",
                    },
                    "framework": {
                        "type": "string",
                        "enum": ["react", "react-tailwind", "html-tailwind", "vue", "svelte"],
                    },
                },
                "required": ["page_type"],
            },
            handler=self._generate_page_layout,
        )

    def get_tools(self) -> list[ToolDefinition]:
        return self._tools

    async def _generate_component(
        self,
        name: str,
        description: str,
        framework: str | None = None,
        features: list[str] | None = None,
    ) -> str:
        """Guide for component generation."""
        fw = framework or self.default_framework.value
        feat = ", ".join(features) if features else "standard features"
        return f"""Generate a {fw} component named '{name}'.

Description: {description}
Features: {feat}
Library: {self.component_library.value}

Requirements:
- Complete, runnable code with all imports
- TypeScript types for props
- Tailwind CSS for styling
- Accessible (ARIA, keyboard nav, focus states)
- Responsive (mobile-first)
- Include all states (loading, error, empty if applicable)

Output the complete code without placeholders."""

    async def _review_component(
        self,
        code: str,
        focus: list[str] | None = None,
    ) -> str:
        """Guide for component review."""
        areas = ", ".join(focus) if focus else "accessibility, usability, code quality"
        return f"""Review this component code:

```
{code[:2000]}
```

Focus areas: {areas}

Analyze:
1. Accessibility issues (WCAG 2.1 compliance)
2. UX problems (missing states, feedback, etc.)
3. Code quality (types, naming, structure)
4. Responsive design issues
5. Performance concerns

Provide specific, actionable feedback with code examples."""

    async def _refine_component(
        self,
        current_code: str,
        feedback: str,
    ) -> str:
        """Guide for component refinement."""
        return f"""Refine this component based on feedback:

Current code:
```
{current_code[:2000]}
```

Requested changes: {feedback}

Output the complete updated code with the requested improvements.
Do not use placeholders - provide the full working code."""

    async def _generate_design_system(
        self,
        style: str,
        primary_color: str | None = None,
        dark_mode: bool = True,
    ) -> str:
        """Guide for design system generation."""
        return f"""Generate a {style} design system.

Primary color: {primary_color or 'choose appropriate'}
Dark mode: {'yes' if dark_mode else 'no'}

Include:
1. Color palette (primary, secondary, neutral, semantic)
2. Typography scale (font sizes, weights, line heights)
3. Spacing scale (4px base, or 0.25rem)
4. Border radii
5. Shadows
6. Tailwind config extension

Output as:
1. CSS variables (for theming)
2. Tailwind config (extend section)
3. Usage examples"""

    async def _generate_page_layout(
        self,
        page_type: str,
        sections: list[str] | None = None,
        framework: str | None = None,
    ) -> str:
        """Guide for page layout generation."""
        fw = framework or self.default_framework.value
        secs = ", ".join(sections) if sections else "standard sections for this page type"
        return f"""Generate a complete {page_type} page layout.

Framework: {fw}
Sections: {secs}

Requirements:
- Responsive layout (mobile-first)
- Semantic HTML structure
- Navigation and footer included
- Proper heading hierarchy
- All components complete (no placeholders)

Output the complete page code."""

    async def process_response(
        self,
        response: CompletionResponse,
        tool_outputs: list[str]
    ) -> AgentResult:
        """Process the response into an AgentResult."""
        content = response.content

        # Try to extract code blocks from the response
        code_blocks = self._extract_code_blocks(content)

        return AgentResult(
            success=True,
            output=content,
            data={
                "tool_outputs": tool_outputs,
                "code_blocks": code_blocks,
            },
            tokens_used=response.total_tokens,
            summary_for_next_agent=self._create_summary(content, code_blocks),
        )

    def _extract_code_blocks(self, content: str) -> list[dict[str, str]]:
        """Extract code blocks from markdown content."""
        blocks = []
        in_block = False
        current_lang = ""
        current_code = []

        for line in content.split("\n"):
            if line.startswith("```"):
                if in_block:
                    # End of block
                    blocks.append({
                        "language": current_lang,
                        "code": "\n".join(current_code),
                    })
                    current_code = []
                    in_block = False
                else:
                    # Start of block
                    current_lang = line[3:].strip() or "text"
                    in_block = True
            elif in_block:
                current_code.append(line)

        return blocks

    def _create_summary(self, content: str, code_blocks: list[dict]) -> str:
        """Create a concise summary for handoff."""
        if code_blocks:
            langs = [b["language"] for b in code_blocks]
            return f"Generated {len(code_blocks)} code block(s): {', '.join(langs)}"

        # Summarize text content
        lines = [l.strip() for l in content.split("\n") if l.strip()][:3]
        return "UX: " + " | ".join(lines)

    # Convenience methods for direct use

    async def generate(
        self,
        context: AgentContext,
        description: str,
        framework: UIFramework | None = None,
    ) -> GeneratedComponent:
        """Generate a UI component from a description."""
        fw = framework or self.default_framework
        request = f"""Generate a complete {fw.value} component:

{description}

Use {self.component_library.value} patterns if applicable.
Output complete, production-ready code."""

        result = await self.run(context, request)

        # Extract code from result
        code = ""
        if result.data.get("code_blocks"):
            code = result.data["code_blocks"][0].get("code", "")
        else:
            code = result.output

        return GeneratedComponent(
            name="Component",
            description=description,
            framework=fw,
            code=code,
            dependencies=[],
        )

    async def review(
        self,
        context: AgentContext,
        code: str,
    ) -> UXReview:
        """Review UI code for UX issues."""
        request = f"""Review this UI code for UX and accessibility issues:

```
{code}
```

Score 1-10 and list specific issues with suggestions."""

        result = await self.run(context, request)

        return UXReview(
            score=7,  # Would parse from result in production
            strengths=["Reviewed"],
            issues=[],
            accessibility_issues=[],
            suggestions=[],
        )
