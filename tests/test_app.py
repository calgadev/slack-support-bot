import pytest
from pydantic import SecretStr

from support_bot.app import build_app, run
from support_bot.config import Settings


def test_build_app_registers_listeners_without_network(tmp_path) -> None:
    settings = Settings(
        slack_bot_token=SecretStr("xoxb-test"),
        gemini_api_key=SecretStr("test"),
        data_dir=tmp_path,
    )
    components = build_app(settings, verify_token=False)
    assert len(components.app._listeners) == 6  # 2 events + 2 ticket + 2 feedback buttons
    assert (tmp_path / "support_bot.db").exists()
    components.db.close()


def test_missing_tokens_fail_fast(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="SLACK_APP_TOKEN"):
        run(Settings(data_dir=tmp_path))
    with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
        build_app(Settings(data_dir=tmp_path))
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        build_app(
            Settings(data_dir=tmp_path, slack_bot_token=SecretStr("xoxb-test")), verify_token=False
        )
