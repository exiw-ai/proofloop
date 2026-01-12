"""Tests for ReportPackStore."""

from pathlib import Path
from uuid import uuid4

import pytest

from src.domain.value_objects import ReportPackTemplate
from src.infrastructure.research.report_pack_store import ReportPackStore


@pytest.fixture
def store(tmp_path: Path) -> ReportPackStore:
    return ReportPackStore(base_path=tmp_path)


class TestCreateReportPack:
    @pytest.mark.asyncio
    async def test_creates_pack_with_template(self, store: ReportPackStore) -> None:
        task_id = uuid4()
        pack = await store.create_report_pack(task_id, ReportPackTemplate.GENERAL_DEFAULT)

        assert pack.task_id == task_id
        assert pack.template == ReportPackTemplate.GENERAL_DEFAULT
        assert pack.status == "pending"
        assert "executive_summary.md" in pack.required_files
        assert pack.present_files == []
        assert pack.missing_files == pack.required_files

    @pytest.mark.asyncio
    async def test_creates_academic_pack(self, store: ReportPackStore) -> None:
        task_id = uuid4()
        pack = await store.create_report_pack(task_id, ReportPackTemplate.ACADEMIC_REVIEW)

        assert pack.template == ReportPackTemplate.ACADEMIC_REVIEW
        assert "abstract.md" in pack.required_files
        assert "bibliography.md" in pack.required_files


class TestSaveReportFile:
    @pytest.mark.asyncio
    async def test_saves_file(self, store: ReportPackStore, tmp_path: Path) -> None:
        await store.save_report_file("summary.md", "# Summary\n\nTest content")

        file_path = tmp_path / "reports" / "summary.md"
        assert file_path.exists()
        assert file_path.read_text() == "# Summary\n\nTest content"

    @pytest.mark.asyncio
    async def test_creates_reports_dir(self, store: ReportPackStore, tmp_path: Path) -> None:
        await store.save_report_file("test.md", "content")

        assert (tmp_path / "reports").is_dir()


class TestLoadReportFile:
    @pytest.mark.asyncio
    async def test_loads_existing_file(self, store: ReportPackStore) -> None:
        await store.save_report_file("test.md", "test content")

        content = await store.load_report_file("test.md")

        assert content == "test content"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_file(self, store: ReportPackStore) -> None:
        content = await store.load_report_file("nonexistent.md")

        assert content is None


class TestListReportFiles:
    @pytest.mark.asyncio
    async def test_lists_markdown_files(self, store: ReportPackStore) -> None:
        await store.save_report_file("summary.md", "content1")
        await store.save_report_file("findings.md", "content2")

        files = await store.list_report_files()

        assert "summary.md" in files
        assert "findings.md" in files

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_reports_dir(self, store: ReportPackStore) -> None:
        files = await store.list_report_files()

        assert files == []


class TestUpdatePackStatus:
    @pytest.mark.asyncio
    async def test_marks_complete_when_all_files_present(self, store: ReportPackStore) -> None:
        task_id = uuid4()
        pack = await store.create_report_pack(task_id, ReportPackTemplate.GENERAL_DEFAULT)

        # Create all required files
        for filename in pack.required_files:
            await store.save_report_file(filename, "content")

        updated = await store.update_pack_status(pack)

        assert updated.status == "complete"
        assert updated.missing_files == []
        assert len(updated.present_files) == len(pack.required_files)

    @pytest.mark.asyncio
    async def test_marks_partial_when_some_files_present(self, store: ReportPackStore) -> None:
        task_id = uuid4()
        pack = await store.create_report_pack(task_id, ReportPackTemplate.GENERAL_DEFAULT)

        # Create only one file
        await store.save_report_file("executive_summary.md", "content")

        updated = await store.update_pack_status(pack)

        assert updated.status == "partial"
        assert "executive_summary.md" in updated.present_files
        assert len(updated.missing_files) > 0

    @pytest.mark.asyncio
    async def test_marks_pending_when_no_files(self, store: ReportPackStore) -> None:
        task_id = uuid4()
        pack = await store.create_report_pack(task_id, ReportPackTemplate.GENERAL_DEFAULT)

        updated = await store.update_pack_status(pack)

        assert updated.status == "pending"


class TestSaveManifest:
    @pytest.mark.asyncio
    async def test_saves_manifest_json(self, store: ReportPackStore, tmp_path: Path) -> None:
        task_id = uuid4()
        pack = await store.create_report_pack(task_id, ReportPackTemplate.GENERAL_DEFAULT)

        manifest_hash = await store.save_manifest(pack, {"coverage": 0.95})

        assert manifest_hash.startswith("sha256:")
        assert (tmp_path / "reports" / "manifest.json").exists()

    @pytest.mark.asyncio
    async def test_manifest_contains_metrics(self, store: ReportPackStore) -> None:
        task_id = uuid4()
        pack = await store.create_report_pack(task_id, ReportPackTemplate.GENERAL_DEFAULT)

        await store.save_manifest(pack, {"coverage": 0.95, "sources": 10})

        manifest = await store.load_manifest()
        assert manifest is not None
        assert manifest["metrics"]["coverage"] == 0.95
        assert manifest["metrics"]["sources"] == 10


class TestLoadManifest:
    @pytest.mark.asyncio
    async def test_loads_existing_manifest(self, store: ReportPackStore) -> None:
        task_id = uuid4()
        pack = await store.create_report_pack(task_id, ReportPackTemplate.GENERAL_DEFAULT)
        await store.save_manifest(pack, {})

        manifest = await store.load_manifest()

        assert manifest is not None
        assert manifest["template"] == "general_default"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_manifest(self, store: ReportPackStore) -> None:
        manifest = await store.load_manifest()

        assert manifest is None
