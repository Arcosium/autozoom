"""SinkRecorder.reattach 의 스트림 선별 규칙 검증 — pactl 없이 순수 로직만.

실행: .venv/bin/python -m pytest tests/test_reattach.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["AZ_DATA"] = tempfile.mkdtemp(prefix="az-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio import SinkRecorder  # noqa: E402

OURS = "77"
SINKS = {"77": "az_myjob", "88": "az_otherjob", "0": "auto_null.monitor", "1": "spk"}
pick = SinkRecorder._pick_browser_moves


def _si(index, sink, app="Chromium", binary="chrome"):
    return {"index": index, "sink": sink,
            "properties": {"application.name": app, "application.process.binary": binary}}


def test_moves_browser_drifted_to_default_sink():
    # 크로미움 스트림이 기본 싱크(spk)로 샜다 → 우리 싱크로 끌어온다
    moves = pick([_si(5, 1)], SINKS, OURS, "az_myjob")
    assert moves == ["5"]


def test_leaves_stream_already_on_our_sink():
    assert pick([_si(5, 77)], SINKS, OURS, "az_myjob") == []


def test_never_steals_another_jobs_sink():
    # 다른 잡의 az_ 싱크에 정상적으로 붙은 브라우저 스트림은 건드리지 않는다
    assert pick([_si(5, 88)], SINKS, OURS, "az_myjob") == []


def test_ignores_non_browser_streams():
    # 크로미움이 아닌 앱(예: 미디어 플레이어)은 옮기지 않는다
    assert pick([_si(5, 1, app="mpv", binary="mpv")], SINKS, OURS, "az_myjob") == []
