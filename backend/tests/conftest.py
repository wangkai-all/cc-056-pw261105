import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import init_db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """每个测试用独立的 SQLite 文件。"""
    monkeypatch.setenv("BILLING_DB", str(tmp_path / "test.db"))
    init_db()
