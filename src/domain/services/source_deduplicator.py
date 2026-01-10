from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.entities.source import Source


class SourceDeduplicator:
    def is_duplicate(
        self,
        new_canonical_url: str,
        new_locator: dict[str, Any],
        existing_sources: list[Source],
    ) -> tuple[bool, Source | None]:
        for source in existing_sources:
            if source.canonical_url == new_canonical_url:
                return True, source

            if new_locator.get("doi") and new_locator.get("doi") == source.locator.get("doi"):
                return True, source

            if new_locator.get("arxiv_id") and new_locator.get("arxiv_id") == source.locator.get(
                "arxiv_id"
            ):
                return True, source

            if new_locator.get("github_sha") and new_locator.get(
                "github_sha"
            ) == source.locator.get("github_sha"):
                return True, source

        return False, None

    def find_duplicates(self, sources: list[Source]) -> list[tuple[Source, Source]]:
        duplicates: list[tuple[Source, Source]] = []
        seen: list[Source] = []

        for source in sources:
            is_dup, existing = self.is_duplicate(
                source.canonical_url,
                source.locator,
                seen,
            )
            if is_dup and existing:
                duplicates.append((source, existing))
            else:
                seen.append(source)

        return duplicates
