from pathlib import Path

from support_bot.health import heartbeat_age, is_healthy, write_heartbeat


def test_fresh_heartbeat_is_healthy(tmp_path: Path) -> None:
    hb = tmp_path / "hb"
    write_heartbeat(hb, now=1000.0)
    assert is_healthy(hb, max_age_seconds=90, now=1050.0)


def test_stale_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    hb = tmp_path / "hb"
    write_heartbeat(hb, now=1000.0)
    assert not is_healthy(hb, max_age_seconds=90, now=1091.0)


def test_missing_or_corrupt_heartbeat(tmp_path: Path) -> None:
    hb = tmp_path / "hb"
    assert heartbeat_age(hb) is None
    hb.write_text("garbage", encoding="utf-8")
    assert not is_healthy(hb, max_age_seconds=90)
