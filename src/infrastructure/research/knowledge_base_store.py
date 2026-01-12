import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from src.domain.entities import Excerpt, Finding, KnowledgeBase, Source
from src.domain.entities.source import FetchMeta
from src.domain.services import SourceDeduplicator, SourceKeyGenerator
from src.domain.value_objects import SourceLocator


class KnowledgeBaseStore:
    """Store for knowledge base artifacts."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.kb_path = base_path / "knowledge_base"
        self._synthesis_dir = self.kb_path / "synthesis"
        self._source_key_gen = SourceKeyGenerator()
        self._deduplicator = SourceDeduplicator()

    def _ensure_dirs(self) -> None:
        (self.kb_path / "sources").mkdir(parents=True, exist_ok=True)
        (self.kb_path / "findings").mkdir(parents=True, exist_ok=True)
        (self.kb_path / "excerpts").mkdir(parents=True, exist_ok=True)
        (self.kb_path / "raw").mkdir(parents=True, exist_ok=True)
        (self.kb_path / "text").mkdir(parents=True, exist_ok=True)
        (self.kb_path / "synthesis").mkdir(parents=True, exist_ok=True)

    async def save_source(
        self,
        url: str,
        content: bytes,
        source_type: str,
        title: str = "",
        locator: SourceLocator | None = None,
        http_status: int = 200,
        mime_type: str = "text/html",
    ) -> tuple[Source, bool]:
        """Save a source and return (source, is_duplicate)."""
        self._ensure_dirs()

        canonical = self._source_key_gen.canonicalize_url(url)

        existing = await self.list_sources()
        is_dup, existing_source = self._deduplicator.is_duplicate(
            canonical, locator or SourceLocator(), existing
        )

        if is_dup and existing_source:
            return existing_source, True

        source_id = uuid4()
        source_key = self._source_key_gen.generate_key(url, source_type, title or None)

        ext = self._mime_to_ext(mime_type)
        raw_path = f"raw/{source_id}.{ext}"
        text_path = f"text/{source_id}.txt"

        (self.kb_path / raw_path).write_bytes(content)

        text = self._extract_text(content, mime_type)
        (self.kb_path / text_path).write_text(text, encoding="utf-8")

        content_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"

        source = Source(
            id=source_id,
            source_key=source_key,
            title=title or source_key,
            url=url,
            canonical_url=canonical,
            retrieved_at=datetime.now(UTC),
            content_hash=content_hash,
            locator=locator or SourceLocator(),
            source_type=source_type,
            raw_path=raw_path,
            text_path=text_path,
            fetch_meta=FetchMeta(
                http_status=http_status,
                final_url=url,
                mime_type=mime_type,
                size_bytes=len(content),
                extract_method=self._get_extract_method(mime_type),
            ),
        )

        source_file = self.kb_path / "sources" / f"{source_id}.json"
        source_file.write_text(source.model_dump_json(indent=2), encoding="utf-8")

        return source, False

    async def save_finding(self, finding: Finding) -> None:
        """Save a finding."""
        self._ensure_dirs()
        finding_file = self.kb_path / "findings" / f"{finding.id}.json"
        finding_file.write_text(finding.model_dump_json(indent=2), encoding="utf-8")

    async def save_excerpt(self, excerpt: Excerpt) -> None:
        """Save an excerpt."""
        self._ensure_dirs()
        excerpt_file = self.kb_path / "excerpts" / f"{excerpt.id}.json"
        excerpt_file.write_text(excerpt.model_dump_json(indent=2), encoding="utf-8")

    async def load_source(self, source_id: UUID) -> Source | None:
        """Load a source by ID."""
        source_file = self.kb_path / "sources" / f"{source_id}.json"
        if not source_file.exists():
            return None
        data = json.loads(source_file.read_text(encoding="utf-8"))
        return Source.model_validate(data)

    async def load_finding(self, finding_id: UUID) -> Finding | None:
        """Load a finding by ID."""
        finding_file = self.kb_path / "findings" / f"{finding_id}.json"
        if not finding_file.exists():
            return None
        data = json.loads(finding_file.read_text(encoding="utf-8"))
        return Finding.model_validate(data)

    async def load_excerpt(self, excerpt_id: UUID) -> Excerpt | None:
        """Load an excerpt by ID."""
        excerpt_file = self.kb_path / "excerpts" / f"{excerpt_id}.json"
        if not excerpt_file.exists():
            return None
        data = json.loads(excerpt_file.read_text(encoding="utf-8"))
        return Excerpt.model_validate(data)

    async def list_sources(self) -> list[Source]:
        """List all sources."""
        sources_dir = self.kb_path / "sources"
        if not sources_dir.exists():
            return []

        sources = []
        for f in sources_dir.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            sources.append(Source.model_validate(data))
        return sources

    async def list_findings(self) -> list[Finding]:
        """List all findings."""
        findings_dir = self.kb_path / "findings"
        if not findings_dir.exists():
            return []

        findings = []
        for f in findings_dir.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            findings.append(Finding.model_validate(data))
        return findings

    async def list_excerpts(self) -> list[Excerpt]:
        """List all excerpts."""
        excerpts_dir = self.kb_path / "excerpts"
        if not excerpts_dir.exists():
            return []

        excerpts = []
        for f in excerpts_dir.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            excerpts.append(Excerpt.model_validate(data))
        return excerpts

    async def build_knowledge_base(self, task_id: UUID) -> KnowledgeBase:
        """Build a KnowledgeBase aggregate from stored data."""
        sources = await self.list_sources()
        findings = await self.list_findings()
        excerpts = await self.list_excerpts()

        now = datetime.now(UTC)
        return KnowledgeBase(
            id=uuid4(),
            task_id=task_id,
            sources=[s.id for s in sources],
            findings=[f.id for f in findings],
            excerpts=[e.id for e in excerpts],
            source_key_map={s.source_key: s.id for s in sources},
            created_at=now,
            updated_at=now,
        )

    def save_synthesis_pass(self, pass_num: int, data: dict[str, Any]) -> Path:
        """Save a synthesis pass result."""
        self._synthesis_dir.mkdir(parents=True, exist_ok=True)
        path = self._synthesis_dir / f"pass_{pass_num}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def save_synthesis_log(self, log_data: dict[str, Any]) -> Path:
        """Save the synthesis log."""
        self._synthesis_dir.mkdir(parents=True, exist_ok=True)
        path = self._synthesis_dir / "synthesis_log.json"
        path.write_text(json.dumps(log_data, indent=2), encoding="utf-8")
        return path

    def load_synthesis_log(self) -> dict[str, Any] | None:
        """Load the synthesis log, returns None if not exists."""
        path = self._synthesis_dir / "synthesis_log.json"
        if not path.exists():
            return None
        result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return result

    def save_baseline(self, data: dict[str, Any]) -> Path:
        """Save baseline research results."""
        baseline_dir = self.kb_path / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        path = baseline_dir / "baseline.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def _mime_to_ext(self, mime_type: str) -> str:
        mapping = {
            "text/html": "html",
            "application/pdf": "pdf",
            "text/plain": "txt",
            "application/json": "json",
            "text/markdown": "md",
        }
        return mapping.get(mime_type.split(";")[0].strip(), "bin")

    def _get_extract_method(self, mime_type: str) -> str:
        if "pdf" in mime_type:
            return "pypdf"
        if "html" in mime_type:
            return "beautifulsoup"
        return "raw_text"

    def _extract_text(self, content: bytes, mime_type: str) -> str:
        """Extract text from content based on mime type."""
        try:
            if "pdf" in mime_type:
                return self._extract_pdf_text(content)
            if "html" in mime_type:
                return self._extract_html_text(content)
            return content.decode("utf-8", errors="replace")
        except (UnicodeDecodeError, ValueError, OSError):
            return content.decode("utf-8", errors="replace")

    def _extract_pdf_text(self, content: bytes) -> str:
        """Extract text from PDF content."""
        try:
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts)
        except ImportError:
            return "[PDF extraction requires pypdf library]"
        except Exception as e:
            return f"[PDF extraction failed: {e}]"

    def _extract_html_text(self, content: bytes) -> str:
        """Extract text from HTML content."""
        try:
            from bs4 import BeautifulSoup

            html = content.decode("utf-8", errors="replace")
            soup = BeautifulSoup(html, "html.parser")
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return text or html
        except ImportError:
            # Fallback: simple HTML tag stripping
            import re

            html = content.decode("utf-8", errors="replace")
            stripped: str = re.sub(r"<[^>]+>", "", html)
            return stripped
        except (UnicodeDecodeError, ValueError, TypeError):
            return content.decode("utf-8", errors="replace")
