from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domain.entities.source import Source


@dataclass
class SourceCheck:
    source_key: str
    has_raw: bool
    has_text: bool
    raw_file_exists: bool
    text_file_exists: bool
    http_status: int
    final_url: str


@dataclass
class CitationValidationResult:
    checked_files: list[str]
    citations_found: list[str]
    citations_valid: list[str]
    citations_invalid: list[str]
    validation_errors: list[str]
    sources_checked: list[SourceCheck]
    all_citations_resolve: bool
    all_sources_have_url: bool
    all_sources_have_retrieved_at: bool
    all_sources_have_content_hash: bool
    all_sources_have_raw: bool
    all_sources_have_text: bool
    all_raw_files_exist: bool
    all_text_files_exist: bool
    all_http_status_ok: bool
    passed: bool


CITATION_PATTERN = re.compile(r"\[@([a-zA-Z0-9_-]+)\]")


class CitationValidator:
    def extract_citations(self, text: str) -> list[str]:
        return CITATION_PATTERN.findall(text)

    def validate_citations(
        self,
        report_files: dict[str, str],
        source_key_map: dict[str, UUID],
        sources: dict[UUID, Source],
        knowledge_base_path: Path,
    ) -> CitationValidationResult:
        checked_files = list(report_files.keys())
        all_citations: set[str] = set()

        for content in report_files.values():
            all_citations.update(self.extract_citations(content))

        citations_found = list(all_citations)
        citations_valid: list[str] = []
        citations_invalid: list[str] = []
        validation_errors: list[str] = []
        sources_checked: list[SourceCheck] = []

        all_citations_resolve = True
        all_sources_have_url = True
        all_sources_have_retrieved_at = True
        all_sources_have_content_hash = True
        all_sources_have_raw = True
        all_sources_have_text = True
        all_raw_files_exist = True
        all_text_files_exist = True
        all_http_status_ok = True

        for citation_key in citations_found:
            if citation_key not in source_key_map:
                citations_invalid.append(citation_key)
                validation_errors.append(f"Citation [@{citation_key}] not found in sources")
                all_citations_resolve = False
                continue

            source_id = source_key_map[citation_key]
            source = sources.get(source_id)

            if not source:
                citations_invalid.append(citation_key)
                validation_errors.append(
                    f"Source {source_id} not found for citation [@{citation_key}]"
                )
                all_citations_resolve = False
                continue

            has_raw = bool(source.raw_path)
            has_text = bool(source.text_path)
            raw_file_exists = (knowledge_base_path / source.raw_path).exists() if has_raw else False
            text_file_exists = (
                (knowledge_base_path / source.text_path).exists() if has_text else False
            )
            http_status = source.fetch_meta.http_status if source.fetch_meta else 0
            final_url = source.fetch_meta.final_url if source.fetch_meta else ""

            sources_checked.append(
                SourceCheck(
                    source_key=citation_key,
                    has_raw=has_raw,
                    has_text=has_text,
                    raw_file_exists=raw_file_exists,
                    text_file_exists=text_file_exists,
                    http_status=http_status,
                    final_url=final_url,
                )
            )

            if not source.url:
                all_sources_have_url = False
                validation_errors.append(f"Source {citation_key} missing URL")

            if not source.retrieved_at:
                all_sources_have_retrieved_at = False
                validation_errors.append(f"Source {citation_key} missing retrieved_at")

            if not source.content_hash:
                all_sources_have_content_hash = False
                validation_errors.append(f"Source {citation_key} missing content_hash")

            if not has_raw:
                all_sources_have_raw = False
                validation_errors.append(f"Source {citation_key} missing raw_path")
            elif not raw_file_exists:
                all_raw_files_exist = False
                validation_errors.append(f"Raw file not found for source {citation_key}")

            if not has_text:
                all_sources_have_text = False
                validation_errors.append(f"Source {citation_key} missing text_path")
            elif not text_file_exists:
                all_text_files_exist = False
                validation_errors.append(f"Text file not found for source {citation_key}")

            if http_status >= 400:
                all_http_status_ok = False
                validation_errors.append(f"Source {citation_key} has HTTP status {http_status}")

            if all(
                [
                    has_raw,
                    has_text,
                    raw_file_exists,
                    text_file_exists,
                    http_status < 400,
                    source.url,
                    source.retrieved_at,
                    source.content_hash,
                ]
            ):
                citations_valid.append(citation_key)
            else:
                citations_invalid.append(citation_key)

        passed = all(
            [
                all_citations_resolve,
                all_sources_have_url,
                all_sources_have_retrieved_at,
                all_sources_have_content_hash,
                all_sources_have_raw,
                all_sources_have_text,
                all_raw_files_exist,
                all_text_files_exist,
                all_http_status_ok,
            ]
        )

        return CitationValidationResult(
            checked_files=checked_files,
            citations_found=citations_found,
            citations_valid=citations_valid,
            citations_invalid=citations_invalid,
            validation_errors=validation_errors,
            sources_checked=sources_checked,
            all_citations_resolve=all_citations_resolve,
            all_sources_have_url=all_sources_have_url,
            all_sources_have_retrieved_at=all_sources_have_retrieved_at,
            all_sources_have_content_hash=all_sources_have_content_hash,
            all_sources_have_raw=all_sources_have_raw,
            all_sources_have_text=all_sources_have_text,
            all_raw_files_exist=all_raw_files_exist,
            all_text_files_exist=all_text_files_exist,
            all_http_status_ok=all_http_status_ok,
            passed=passed,
        )
