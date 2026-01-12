from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".proofloop"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def sample_task_id() -> uuid4:
    return uuid4()
