from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.finding import Finding
    from src.domain.entities.source import Source


@dataclass
class TopicDetail:
    topic: str
    finding_count: int
    has_valid_excerpts: bool
    sources_with_raw: int


@dataclass
class CoverageResult:
    required_threshold: float
    actual_coverage: float
    required_topics: list[str]
    covered_topics: list[str]
    uncovered_topics: list[str]
    topics_detail: list[TopicDetail]
    passed: bool


class CoverageCalculator:
    def calculate_coverage(
        self,
        required_topics: list[str],
        topic_synonyms: dict[str, list[str]],
        findings: list[Finding],
        sources: dict[UUID, Source],
        knowledge_base_path: Path,
        threshold: float = 0.8,
    ) -> CoverageResult:
        if not required_topics:
            return CoverageResult(
                required_threshold=threshold,
                actual_coverage=1.0,
                required_topics=[],
                covered_topics=[],
                uncovered_topics=[],
                topics_detail=[],
                passed=True,
            )

        normalized_required = {t.lower(): t for t in required_topics}

        synonym_map: dict[str, str] = {}
        for topic, synonyms in topic_synonyms.items():
            topic_lower = topic.lower()
            synonym_map[topic_lower] = topic_lower
            for syn in synonyms:
                synonym_map[syn.lower()] = topic_lower

        topic_findings: dict[str, list[Finding]] = {t: [] for t in normalized_required}

        for finding in findings:
            for finding_topic in finding.topics:
                normalized = finding_topic.lower()
                if normalized in synonym_map:
                    target_topic = synonym_map[normalized]
                    if target_topic in topic_findings:
                        topic_findings[target_topic].append(finding)

        covered_topics: list[str] = []
        uncovered_topics: list[str] = []
        topics_detail: list[TopicDetail] = []

        for topic_lower, original in normalized_required.items():
            topic_finding_list = topic_findings.get(topic_lower, [])
            valid_findings: list[Finding] = []

            for f in topic_finding_list:
                if not f.excerpt_ref:
                    continue

                source = sources.get(f.source_id)
                if not source:
                    continue

                if not source.raw_path or not source.text_path:
                    continue

                raw_exists = (knowledge_base_path / source.raw_path).exists()
                text_exists = (knowledge_base_path / source.text_path).exists()

                if raw_exists and text_exists:
                    valid_findings.append(f)

            has_valid = len(valid_findings) > 0
            sources_with_raw = len({f.source_id for f in valid_findings})

            topics_detail.append(
                TopicDetail(
                    topic=original,
                    finding_count=len(valid_findings),
                    has_valid_excerpts=has_valid,
                    sources_with_raw=sources_with_raw,
                )
            )

            if has_valid:
                covered_topics.append(original)
            else:
                uncovered_topics.append(original)

        actual_coverage = len(covered_topics) / len(required_topics)
        passed = actual_coverage >= threshold

        return CoverageResult(
            required_threshold=threshold,
            actual_coverage=actual_coverage,
            required_topics=required_topics,
            covered_topics=covered_topics,
            uncovered_topics=uncovered_topics,
            topics_detail=topics_detail,
            passed=passed,
        )
