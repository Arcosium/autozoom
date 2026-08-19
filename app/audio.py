"""PulseAudio 가상 싱크로 브라우저 출력 오디오를 캡처한다.

잡마다 전용 null-sink 를 만들고, 그 싱크의 monitor 를 parec 로 떠서 wav 로 적는다.
브라우저에는 PULSE_SINK 환경변수로 해당 싱크를 물린다 → 회의 소리가 스피커 대신
그 싱크로만 흐르고, 다른 프로세스 소리는 섞이지 않는다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

SAMPLE_RATE = 16000  # whisper 입력 규격


class AudioError(RuntimeError):
    pass


def _pulse_env() -> dict:
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env


def ensure_daemon() -> None:
    """Pulse 프로토콜 서버가 살아있는지 확인한다.

    이 서버(GB10)는 PulseAudio 가 아니라 **PipeWire** 를 쓴다. pipewire-pulse 가
    Pulse 프로토콜을 제공하므로 pactl/parec 이 그대로 통한다. pulseaudio 패키지를
    설치하면 pipewire-audio/pipewire-alsa 가 제거되니 절대 설치하지 말 것.
    """
    for tool in ("pactl", "parec"):
        if not shutil.which(tool):
            raise AudioError(f"{tool} 이(가) 없다. `sudo apt-get install -y pulseaudio-utils` 필요.")
    env = _pulse_env()
    if subprocess.run(["pactl", "info"], env=env, capture_output=True).returncode == 0:
        return
    # PipeWire 유저 서비스가 내려가 있으면 한 번 올려본다.
    subprocess.run(["systemctl", "--user", "start", "pipewire", "pipewire-pulse", "wireplumber"],
                   env=env, capture_output=True, check=False)
    for _ in range(20):
        if subprocess.run(["pactl", "info"], env=env, capture_output=True).returncode == 0:
            return
        time.sleep(0.25)
    raise AudioError("Pulse 프로토콜 서버(pipewire-pulse)에 접속할 수 없다.")


class SinkRecorder:
    """전용 null-sink + parec 녹음기. 컨텍스트 매니저로 쓴다."""

    def __init__(self, job_id: str, wav_path: Path):
        self.sink_name = f"az_{job_id}"
        self.wav_path = wav_path
        self._module_id: str | None = None
        self._sink_index: str | None = None
        self._proc: subprocess.Popen | None = None
        self.env = _pulse_env()

    def __enter__(self) -> "SinkRecorder":
        ensure_daemon()
        out = subprocess.run(
            ["pactl", "load-module", "module-null-sink",
             f"sink_name={self.sink_name}",
             f"sink_properties=device.description={self.sink_name}"],
            env=self.env, capture_output=True, text=True,
        )
        if out.returncode != 0:
            raise AudioError(f"null-sink 생성 실패: {out.stderr.strip()}")
        self._module_id = out.stdout.strip()
        self._sink_index = self._lookup_sink_index()
        self.wav_path.parent.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(
            ["parec", "--device", f"{self.sink_name}.monitor",
             "--file-format=wav", "--format=s16le",
             f"--rate={SAMPLE_RATE}", "--channels=1", str(self.wav_path)],
            env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        return self

    def browser_env(self) -> dict:
        """브라우저에 물릴 환경변수 (이 싱크로만 소리가 나가게)."""
        env = dict(self.env)
        env["PULSE_SINK"] = self.sink_name
        return env

    def bytes_written(self) -> int:
        try:
            return self.wav_path.stat().st_size
        except OSError:
            return 0

    def _sinks_by_index(self) -> dict[str, str]:
        out = subprocess.run(["pactl", "list", "short", "sinks"],
                             env=self.env, capture_output=True, text=True)
        m = {}
        for line in out.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                m[parts[0]] = parts[1]
        return m

    def _lookup_sink_index(self) -> str | None:
        for idx, name in self._sinks_by_index().items():
            if name == self.sink_name:
                return idx
        return None

    @staticmethod
    def _pick_browser_moves(inputs: list, sinks: dict, sink_index: str,
                            sink_name: str) -> list[str]:
        """우리 싱크로 도로 끌어올 sink-input 인덱스들을 고른다(부수효과 없음, 테스트 대상).

        규칙: 크로미움 재생 스트림 중, **다른 az_ 잡 싱크가 아닌** 곳으로 샌 것만 옮긴다.
        이미 우리 싱크면 건드리지 않고, 다른 잡의 싱크에 정상적으로 붙은 것도 훔치지 않는다.
        """
        moves = []
        for si in inputs:
            props = si.get("properties") or {}
            tag = (str(props.get("application.name") or "")
                   + " " + str(props.get("application.process.binary") or "")).lower()
            if not any(t in tag for t in ("chrom", "playwright", "headless")):
                continue
            cur = str(si.get("sink"))
            if cur == str(sink_index):
                continue                                   # 이미 우리 싱크
            if sinks.get(cur, "").startswith("az_"):
                continue                                   # 다른 잡 싱크 — 훔치지 않는다
            idx = si.get("index")
            if idx is not None:
                moves.append(str(idx))
        return moves

    def reattach(self) -> int:
        """우리 싱크에서 샌 브라우저 재생 스트림을 도로 끌어온다.

        PipeWire 가 WebRTC 재협상·페이지 리로드 때 스트림을 기본 싱크로 옮겨,
        회의 중 녹음이 조용히 무음이 되는 사고를 막는다(2026-08-19 실측: 2시간
        지점에서 스트림이 이탈해 뒷부분이 통째로 무음 녹음됨).
        """
        if not self._sink_index:
            self._sink_index = self._lookup_sink_index()
        if not self._sink_index:
            return 0
        try:
            inputs = json.loads(subprocess.run(
                ["pactl", "-f", "json", "list", "sink-inputs"],
                env=self.env, capture_output=True, text=True).stdout or "[]")
        except Exception:  # noqa: BLE001 — 회복 시도가 녹음을 죽이면 안 된다
            return 0
        moves = self._pick_browser_moves(inputs, self._sinks_by_index(),
                                         self._sink_index, self.sink_name)
        for idx in moves:
            subprocess.run(["pactl", "move-sink-input", idx, self.sink_name],
                           env=self.env, capture_output=True, check=False)
        return len(moves)

    def __exit__(self, *exc) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._module_id:
            subprocess.run(["pactl", "unload-module", self._module_id],
                           env=self.env, capture_output=True, check=False)
