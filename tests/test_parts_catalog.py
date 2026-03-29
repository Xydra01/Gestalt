"""Tests for parts_catalog loading (bundled JSON or embedded mock only)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

import parts_catalog
from parts_catalog import (
    SOURCE_EMBEDDED_MOCK,
    SOURCE_LOCAL_JSON,
    load_parts_catalog,
)


def test_without_url_uses_local_json_when_repo_file_present() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        data, src = load_parts_catalog()
    assert src == SOURCE_LOCAL_JSON
    assert "cpus" in data and isinstance(data["cpus"], list)


def test_embedded_when_no_local_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        empty_root = Path(td)
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(parts_catalog, "_ROOT", empty_root):
                data, src = load_parts_catalog()
    assert src == SOURCE_EMBEDDED_MOCK
    assert data["cpus"][0]["id"] == "c1"
