import pytest

from assistants import env


@pytest.fixture(autouse=True)
def no_local_env_file(monkeypatch, tmp_path):
    """Tests never read the developer's real `.env`, which may hold a live Groq key."""
    monkeypatch.setattr(env, "ENV_FILE", tmp_path / "missing.env")
