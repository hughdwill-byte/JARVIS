"""Shared fixtures: temp database and a no-API config."""

import pytest

from app.config import Config
from app.memory.database import Database


@pytest.fixture()
def cfg(tmp_path):
    return Config(
        llm_provider="none",
        anthropic_api_key="",
        vision_provider="none",
        stt_provider="none",
        tts_provider="none",
        database_path=tmp_path / "test.db",
        # Isolate from the developer's real mcp_servers.json — tests must not
        # depend on local filesystem state.
        mcp_config_path=tmp_path / "mcp_servers.json",
    )


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()
