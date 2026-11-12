import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Keep tests independent from any local .env file or real tokens."""
    monkeypatch.chdir(tmp_path)
    for var in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
