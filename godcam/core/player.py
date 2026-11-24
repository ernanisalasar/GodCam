"""Player RTSP baseado em libvlc (vídeo + áudio, baixa latência)."""
from __future__ import annotations

import sys
from hashlib import sha256
from fractions import Fraction

import vlc
from PyQt6.QtCore import QObject, pyqtSignal

_video_instance: vlc.Instance | None = None
_audio_instance: vlc.Instance | None = None


def _get_video_instance() -> vlc.Instance:
    """Keep camera video silent without changing its negotiated audio track."""
    global _video_instance
    if _video_instance is None:
        _video_instance = vlc.Instance(
            "--quiet",
            "--no-video-title-show",
            "--no-snapshot-preview",
            "--no-osd",
            "--aout=adummy",
        )
    return _video_instance


def _get_audio_instance() -> vlc.Instance:
    global _audio_instance
    if _audio_instance is None:
        _audio_instance = vlc.Instance(
            "--quiet",
            "--no-video-title-show",
            "--no-snapshot-preview",
            "--no-osd",
        )
    return _audio_instance


def _new_media(
    instance: vlc.Instance,
    url: str,
    caching_ms: int,
    username: str,
    password: str,
    *,
    disable_video: bool = False,
) -> vlc.Media:
    media = instance.media_new(url)
    media.add_option(f":network-caching={caching_ms}")
    media.add_option(":rtsp-tcp")
    if username:
        media.add_option(f":rtsp-user={username}")
    if password:
        media.add_option(f":rtsp-pwd={password}")
    if disable_video:
        media.add_option(":no-video")
    return media


class RtspPlayer(QObject):
    playing = pyqtSignal(int)
    video_output = pyqtSignal(int, int)
    failed = pyqtSignal(int)
    ended = pyqtSignal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._instance = _get_video_instance()
        self._player = self._instance.media_player_new()
        self._media: vlc.Media | None = None
        self._generation = 0
        self._window_id = 0
        self._released = False
        self._display_geometry: tuple[str, str] | None = None
        self._last_state: vlc.State | None = None
        self._last_video_output = False
        self._player.video_set_mouse_input(False)
        self._player.video_set_key_input(False)

    def attach(self, win_id: int) -> None:
        """Associa a saída de vídeo a uma janela nativa do Qt."""
        win_id = int(win_id)
        if not win_id or win_id == self._window_id:
            return
        if sys.platform.startswith("win"):
            self._player.set_hwnd(win_id)
        elif sys.platform == "darwin":
            self._player.set_nsobject(win_id)
        else:
            self._player.set_xwindow(win_id)
        self._window_id = win_id

    def play(
        self,
        url: str,
        caching_ms: int = 1000,
        username: str = "",
        password: str = "",
    ) -> int:
        if self._released:
            raise RuntimeError("O reprodutor já foi encerrado.")
        media = _new_media(
            self._instance,
            url,
            caching_ms,
            username,
            password,
        )
        self._media = media
        self._player.set_media(media)
        self._display_geometry = None
        self._generation += 1
        self._last_state = None
        self._last_video_output = False
        if self._player.play() == -1:
            raise RuntimeError("O libVLC não conseguiu iniciar a reprodução.")
        return self._generation

    def poll_events(self) -> None:
        """Forward VLC state changes from the Qt thread, avoiding native-thread callbacks."""
        if self._released:
            return
        state = self._player.get_state()
        generation = self._generation
        if state != self._last_state:
            if state == vlc.State.Playing:
                self.playing.emit(generation)
            elif state == vlc.State.Error:
                self.failed.emit(generation)
            elif state == vlc.State.Ended:
                self.ended.emit(generation)
            self._last_state = state

        has_video_output = bool(self._player.has_vout())
        if has_video_output != self._last_video_output:
            self.video_output.emit(generation, int(has_video_output))
            self._last_video_output = has_video_output

    def stop(self) -> None:
        if self._released:
            return
        self._generation += 1
        self._player.stop()
        self._last_state = vlc.State.Stopped
        self._last_video_output = False

    def has_video_output(self) -> bool:
        return bool(self._player.has_vout())

    def video_stats(self) -> tuple[int, int, int] | None:
        """Return decoded frames, displayed frames, and demuxed bytes for the active media."""
        if self._media is None:
            return None
        stats = vlc.MediaStats()
        if not self._media.get_stats(stats):
            return None
        return (
            int(stats.decoded_video),
            int(stats.displayed_pictures),
            int(stats.demux_read_bytes),
        )

    def set_display_mode(self, mode: str, width: int, height: int) -> None:
        """Apply an aspect policy without replacing the active media player."""
        if mode not in ("fill", "fit", "stretch"):
            raise ValueError(f"Modo de exibição inválido: {mode}")
        if width <= 0 or height <= 0:
            return
        ratio = Fraction(width, height).limit_denominator(1000)
        aspect = f"{ratio.numerator}:{ratio.denominator}"
        geometry = (mode, aspect)
        if geometry == self._display_geometry:
            return
        previous_mode = self._display_geometry[0] if self._display_geometry else None

        if mode == "stretch":
            self._player.video_set_aspect_ratio(aspect)
        elif previous_mode == "stretch":
            self._player.video_set_aspect_ratio(None)
        self._display_geometry = geometry

    def is_dead(self) -> bool:
        return self._player.get_state() in (vlc.State.Error, vlc.State.Ended)

    def release(self) -> None:
        if self._released:
            return
        self.stop()
        self._released = True
        self._player.release()
        self._media = None


class RtspAudioPlayer(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._instance = _get_audio_instance()
        self._player = self._instance.media_player_new()
        self._media: vlc.Media | None = None
        self._playback_key: bytes | None = None
        self._playing_requested = False
        self._released = False
        self._volume = 80

    def play(
        self,
        url: str,
        caching_ms: int = 1000,
        username: str = "",
        password: str = "",
    ) -> None:
        if self._released:
            raise RuntimeError("O reprodutor de áudio já foi encerrado.")

        key = sha256(
            "\0".join((url, username, password)).encode("utf-8")
        ).digest()
        if self._playback_key == key and self._playing_requested:
            state = self._player.get_state()
            if state not in (vlc.State.Error, vlc.State.Ended, vlc.State.Stopped):
                return

        self.stop()
        media = _new_media(
            self._instance,
            url,
            caching_ms,
            username,
            password,
            disable_video=True,
        )
        self._media = media
        self._playback_key = key
        self._player.set_media(media)
        if self._player.play() == -1:
            self.stop()
            raise RuntimeError("O libVLC não conseguiu iniciar o áudio.")
        self._playing_requested = True
        self._player.audio_set_volume(self._volume)
        self._player.audio_set_mute(False)

    def stop(self) -> None:
        if self._released:
            return
        if self._playing_requested or self._media is not None:
            self._player.stop()
        self._playing_requested = False
        self._playback_key = None
        self._media = None

    def set_volume(self, volume: int) -> None:
        self._volume = int(volume)
        self._player.audio_set_volume(self._volume)

    def set_muted(self, muted: bool) -> None:
        self._player.audio_set_mute(muted)

    def is_dead(self) -> bool:
        return self._playing_requested and self._player.get_state() in (
            vlc.State.Error,
            vlc.State.Ended,
        )

    def release(self) -> None:
        if self._released:
            return
        self.stop()
        self._released = True
        self._player.release()
        self._media = None
