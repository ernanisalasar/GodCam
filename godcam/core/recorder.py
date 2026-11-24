"""Gravação em .mp4 via ffmpeg (cópia de vídeo, áudio convertido para AAC).

Usa MP4 fragmentado: se o app/PC travar, o arquivo continua reproduzível.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from godcam.config import recordings_dir
from godcam.core.security import sanitize_message


class RecorderError(RuntimeError):
    pass


def _redact_error(text: str) -> str:
    return sanitize_message(text)


class Recorder:
    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self.ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
        self._proc: subprocess.Popen | None = None
        self.output: Path | None = None
        self.last_error = ""

    def start(self, url: str, cam_name: str) -> Path:
        if not self.ffmpeg:
            raise RecorderError("ffmpeg não encontrado no PATH. Instale com: winget install Gyan.FFmpeg")
        safe = re.sub(r"[^\w\-]+", "_", cam_name).strip("_") or "camera"
        folder = recordings_dir() / safe
        folder.mkdir(parents=True, exist_ok=True)
        self.output = folder / f"{safe}_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        cmd = [
            self.ffmpeg, "-hide_banner", "-loglevel", "error",
            "-rtsp_transport", "tcp", "-use_wallclock_as_timestamps", "1",
            "-i", url,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "64k",
            "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
            "-y", str(self.output),
        ]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL, creationflags=flags,
        )
        return self.output

    def is_running(self) -> bool:
        if self._proc is None:
            return False
        if self._proc.poll() is None:
            return True
        if not self.last_error and self._proc.stderr:
            message = self._proc.stderr.read().decode("utf-8", "ignore").strip()
            self.last_error = _redact_error(message)[-300:]
        return False

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        try:  # "q" faz o ffmpeg finalizar o arquivo corretamente
            proc.stdin.write(b"q")
            proc.stdin.flush()
        except OSError:
            pass
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
