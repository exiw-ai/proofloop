from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.source import Source
    from src.domain.value_objects import SourceLocator


class SourceDeduplicator:
    def is_duplicate(
        self,
        new_canonical_url: str,
        new_locator: SourceLocator,
        existing_sources: list[Source],
    ) -> tuple[bool, Source | None]:
        for source in existing_sources:
            if source.canonical_url == new_canonical_url:
                return True, source

            if new_locator.doi and new_locator.doi == source.locator.doi:
                return True, source

            if new_locator.arxiv_id and new_locator.arxiv_id == source.locator.arxiv_id:
                return True, source

            if new_locator.github_sha and new_locator.github_sha == source.locator.github_sha:
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
