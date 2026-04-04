"""Literature search — web search for prior art, approach discovery, and novelty verification.

This module provides structured literature search capabilities that integrate
with the research loop at three points:
1. Before hypothesis — inform experiment design
2. After discovery — verify novelty
3. When stuck — find alternative approaches

Works with any agent backend. When used via the Claude Code plugin, the agent
calls WebSearch/WebFetch directly. When used via the Python harness, this
module provides the search queries and result formatting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchQuery:
    """A structured search query for literature review."""
    query: str
    purpose: str  # inform_hypothesis | verify_novelty | find_approaches
    sources: list[str] = field(default_factory=lambda: [
        "academic", "github", "documentation", "forums",
    ])


@dataclass
class PriorArtResult:
    """Result of a prior art search."""
    query: str
    sources_checked: list[dict[str, str]]  # [{"source": "...", "finding": "..."}]
    is_novel: bool | None = None  # None = inconclusive
    summary: str = ""


class LiteratureSearch:
    """Generates structured search queries and formats results for the research loop.

    This doesn't perform searches itself — it generates the queries and
    templates that agents (Claude/GPT) use with their web search capabilities.
    """

    @staticmethod
    def queries_for_hypothesis(topic: str, research_context: str = "") -> list[SearchQuery]:
        """Generate search queries to inform hypothesis formation."""
        queries = [
            SearchQuery(
                query=f"{topic} state of the art 2024 2025 2026",
                purpose="inform_hypothesis",
                sources=["academic"],
            ),
            SearchQuery(
                query=f"{topic} benchmark results comparison",
                purpose="inform_hypothesis",
                sources=["academic", "github"],
            ),
            SearchQuery(
                query=f"{topic} open problems challenges limitations",
                purpose="inform_hypothesis",
                sources=["academic", "forums"],
            ),
        ]
        if research_context:
            queries.append(SearchQuery(
                query=f"{topic} {research_context}",
                purpose="inform_hypothesis",
                sources=["academic", "github"],
            ))
        return queries

    @staticmethod
    def queries_for_novelty(finding: str, domain: str = "") -> list[SearchQuery]:
        """Generate search queries to verify novelty of a finding."""
        queries = [
            SearchQuery(
                query=f'"{finding}"',
                purpose="verify_novelty",
                sources=["academic", "documentation"],
            ),
            SearchQuery(
                query=f"{finding} known documented",
                purpose="verify_novelty",
                sources=["documentation", "forums"],
            ),
            SearchQuery(
                query=f"{finding} github issue",
                purpose="verify_novelty",
                sources=["github"],
            ),
        ]
        if domain:
            queries.append(SearchQuery(
                query=f"{domain} {finding}",
                purpose="verify_novelty",
                sources=["academic"],
            ))
        return queries

    @staticmethod
    def queries_for_approaches(question: str, tried: list[str] | None = None) -> list[SearchQuery]:
        """Generate search queries to find alternative approaches when stuck."""
        queries = [
            SearchQuery(
                query=f"{question} alternative approaches methods",
                purpose="find_approaches",
                sources=["academic", "github"],
            ),
            SearchQuery(
                query=f"{question} novel technique 2025 2026",
                purpose="find_approaches",
                sources=["academic"],
            ),
            SearchQuery(
                query=f"{question} survey comparison",
                purpose="find_approaches",
                sources=["academic"],
            ),
        ]
        if tried:
            exclusions = " ".join(f"-{t}" for t in tried[:5])
            queries.append(SearchQuery(
                query=f"{question} {exclusions}",
                purpose="find_approaches",
                sources=["academic", "github"],
            ))
        return queries

    @staticmethod
    def format_prior_art_section(result: PriorArtResult) -> str:
        """Format a PriorArtResult as a DISCOVERIES.md 'Prior art search' section."""
        lines = ["### Prior art search", ""]
        lines.append(f"Search query: \"{result.query}\"")
        lines.append("")

        for source in result.sources_checked:
            lines.append(f"- **{source['source']}**: {source['finding']}")

        lines.append("")
        if result.is_novel is True:
            lines.append("**Conclusion: No prior documentation found. This appears novel.**")
        elif result.is_novel is False:
            lines.append("**Conclusion: Prior art exists. See sources above.**")
        else:
            lines.append("**Conclusion: Inconclusive. Partial overlap with existing work.**")

        if result.summary:
            lines.append("")
            lines.append(result.summary)

        return "\n".join(lines)

    @staticmethod
    def format_approach_suggestions(
        question: str,
        approaches: list[dict[str, str]],
    ) -> str:
        """Format approach suggestions for the journal."""
        lines = [
            f"## Alternative Approaches for: {question}",
            "",
            "Based on literature search:",
            "",
        ]
        for i, approach in enumerate(approaches, 1):
            lines.append(f"### {i}. {approach.get('name', 'Unnamed')}")
            lines.append(f"**Source**: {approach.get('source', 'Unknown')}")
            lines.append(f"**Description**: {approach.get('description', '')}")
            if approach.get("relevance"):
                lines.append(f"**Relevance**: {approach['relevance']}")
            lines.append("")

        return "\n".join(lines)
