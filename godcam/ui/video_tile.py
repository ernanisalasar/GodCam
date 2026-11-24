"""Widget de vídeo de uma câmera: superfície do VLC + barra de status + reconexão."""
from __future__ import annotations

import threading
import time

import vlc
from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from godcam.config import CameraConfig
from godcam.core.network import Endpoint, resolve_endpoint
from godcam.core.player import RtspPlayer
from godcam.core.rtsp import build_rtsp_url


class VideoTile(QFrame):
    FRAME_BORDER = 2
    clicked = pyqtSignal(str)             # cam_id
    maximize_requested = pyqtSignal(str)  # duplo clique
    status_changed = pyqtSignal(str)
    _resolved = pyqtSignal(object)
    _failed = pyqtSignal(str)

    def __init__(self, cam: CameraConfig, parent=None) -> None:
        super().__init__(parent)
        self.cam = cam
        self.endpoint: Endpoint | None = None
        self._want_play = False
        self._recording = False
        self._talking = False
        self._attempts = 0
        self._retry_count = 0
        self._generation = 0
        self._stream_started = False
        self._video_available = False
        self._retry_pending = False
        self._frame_counter: int | None = None
        self._frame_counter_mode: str | None = None
        self._frame_progress_count = 0
        self._last_frame_progress = 0.0
        self._attempt_started = 0.0
        self._attached_win_id = 0
        self._display_mode = "fill"
        self._display_update_pending = False

        self.setObjectName("tile")
        self.setProperty("active", False)
        self.setMinimumSize(0, 0)

        self.player = RtspPlayer(self)
        self.surface = QWidget(self)
        self.surface.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)   # HWND próprio p/ o VLC
        self.surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.surface.setStyleSheet("background-color: #000;")
        self.surface.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.header = QWidget(self.surface)
        self.header.setObjectName("tileHeader")
        self.header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.name_lbl = QLabel(cam.name, self.header)
        self.name_lbl.setObjectName("tileName")
        self.name_lbl.setMinimumWidth(0)
        self.name_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.address_lbl = QLabel(cam.host_local or cam.host_remote, self.header)
        self.address_lbl.setObjectName("tileAddress")
        self.address_lbl.setMinimumWidth(0)
        self.address_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.badge_lbl = QLabel("", self.header)
        self.badge_lbl.setObjectName("tileBadge")
        self.status_lbl = QLabel("DESCONECTADA", self.header)
        self.status_lbl.setObjectName("tileStatus")
        self.status_lbl.setMinimumWidth(0)
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(5, 1, 5, 1)
        header_layout.setSpacing(5)
        header_layout.addWidget(self.name_lbl)
        header_layout.addWidget(self.address_lbl)
        header_layout.addWidget(self.badge_lbl)
        header_layout.addStretch(1)
        header_layout.addWidget(self.status_lbl)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.surface)

        self._resolved.connect(self._on_resolved)
        self._failed.connect(self._on_failed)
        self.player.playing.connect(self._on_player_playing)
        self.player.video_output.connect(self._on_video_output)
        self.player.failed.connect(self._on_player_failed)
        self.player.ended.connect(self._on_player_ended)
        self._watchdog = QTimer(self)
        self._watchdog.timeout.connect(self._check_alive)
        self._video_timeout = QTimer(self)
        self._video_timeout.setSingleShot(True)
        self._video_timeout.timeout.connect(self._on_video_timeout)
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._retry_connection)
        for widget in (self.surface, self.header, self.name_lbl, self.address_lbl, self.status_lbl):
            widget.installEventFilter(self)
        self.header.raise_()

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        if self._want_play:
            return
        self._want_play = True
        self._generation = -1
        self._set_status("CONECTANDO")
        threading.Thread(target=self._resolve, daemon=True).start()

    def _resolve(self) -> None:  # thread: testa conexão local sem travar a UI
        try:
            self._resolved.emit(resolve_endpoint(self.cam))
        except (OSError, ValueError):
            self._failed.emit("Não foi possível localizar o endereço da câmera.")

    def _on_resolved(self, ep: Endpoint) -> None:
        if not self._want_play:
            return
        self.endpoint = ep
        self._attach_surface()
        self._start_attempt()

    def _on_failed(self, msg: str) -> None:
        if self._want_play:
            self._set_status(f"ERRO · {msg}")
            self._prepare_retry()

    def _set_status(self, state: str) -> None:
        location = f" · {self.endpoint.origin.upper()} · {self.endpoint.host}" if self.endpoint else ""
        status = f"{state}{location}"
        self.status_lbl.setText(state.split(" · ", 1)[0])
        self.status_lbl.setToolTip(status)
        self.status_changed.emit(status)

    def resizeEvent(self, event) -> None:  # noqa: N802
        compact = self.width() < 175
        self.address_lbl.setVisible(not compact)
        self.badge_lbl.setVisible(self.width() >= 130)
        self._layout_header()
        self._schedule_display_update()
        super().resizeEvent(event)

    def _layout_header(self) -> None:
        width, height = self.surface.width(), self.surface.height()
        header_height = min(24, max(18, self.fontMetrics().height() + 4))
        self.header.setGeometry(0, 0, width, header_height)
        self.header.setVisible(width >= 175 and height >= 52)
        self.header.raise_()

    def _schedule_display_update(self) -> None:
        if self._display_update_pending:
            return
        self._display_update_pending = True
        QTimer.singleShot(0, self._apply_display_mode)

    def _apply_display_mode(self) -> None:
        self._display_update_pending = False
        width, height = self.surface.width(), self.surface.height()
        if width > 0 and height > 0 and self._video_available:
            self.player.set_display_mode(self._display_mode, width, height)

    def set_display_mode(self, mode: str) -> None:
        if mode not in ("fill", "fit", "stretch"):
            raise ValueError(f"Modo de exibição inválido: {mode}")
        self._display_mode = mode
        self._schedule_display_update()

    def _attach_surface(self) -> None:
        win_id = int(self.surface.winId())
        if win_id and win_id != self._attached_win_id:
            self.player.attach(win_id)
            self._attached_win_id = win_id

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # Handle critical Qt events for surface and UI layout.
        if watched is self.surface and event.type() == QEvent.Type.WinIdChange:
            QTimer.singleShot(0, self._attach_surface)
            return super().eventFilter(watched, event)
        elif watched is self.surface and event.type() == QEvent.Type.Resize:
            self._layout_header()
            self._schedule_display_update()
            return super().eventFilter(watched, event)
        # Intercept mouse events on the interactive widgets to emit signals exactly once
        # and stop further propagation. This prevents duplicate `maximize_requested`
        # emissions caused by the default event propagation chain.
        elif watched in (self.surface, self.header, self.name_lbl, self.address_lbl, self.status_lbl):
            if event.type() == QEvent.Type.MouseButtonPress:
                self.clicked.emit(self.cam.id)
                # Accept the event – stop propagation to parent widgets.
                return True
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                self.clicked.emit(self.cam.id)
                self.maximize_requested.emit(self.cam.id)
                # Accept the double‑click – no further handling required.
                return True
        # Fallback to the default implementation for all other events.
        return super().eventFilter(watched, event)

    def _start_attempt(self) -> None:
        if not self._want_play or self.endpoint is None:
            return
        self._retry_timer.stop()
        self._video_timeout.stop()
        if self._attempts:
            self._generation = -1
            self.player.stop()
        is_retry = self._attempts > 0 or self._retry_count > 0
        self._attempts += 1
        self._retry_pending = False
        self._stream_started = False
        self._video_available = False
        self._frame_counter = None
        self._frame_counter_mode = None
        self._frame_progress_count = 0
        self._attempt_started = time.monotonic()
        self._last_frame_progress = self._attempt_started
        self._set_status("RECONECTANDO" if is_retry else "CONECTANDO")
        try:
            self._generation = self.player.play(
                build_rtsp_url(self.cam, self.endpoint),
                username=self.cam.username,
                password=self.cam.password,
            )
        except (RuntimeError, vlc.VLCException):
            self._set_status("ERRO · falha ao iniciar o reprodutor")
            self._schedule_retry()
            return
        self._watchdog.start(1500)
        self._video_timeout.start(15000)

    def _event_is_current(self, generation: int) -> bool:
        return self._want_play and generation == self._generation

    def _on_player_playing(self, generation: int) -> None:
        if not self._event_is_current(generation):
            return
        self._stream_started = True
        self._video_timeout.start(15000)
        self._check_video_progress()

    def _on_video_output(self, generation: int, count: int) -> None:
        if not self._event_is_current(generation):
            return
        if count > 0:
            self._check_video_progress()
        elif self._stream_started and self.isVisible():
            self._prepare_retry("SEM VÍDEO")

    def _mark_video_available(self) -> None:
        self._video_timeout.stop()
        self._video_available = True
        self._retry_count = 0
        self._set_status("REPRODUZINDO")
        self._layout_header()
        self._schedule_display_update()

    def _on_video_timeout(self) -> None:
        if not self._want_play:
            return
        self._check_video_progress()
        if not self._video_available and not self._retry_pending:
            self._prepare_retry("SEM VÍDEO")

    def _on_player_failed(self, generation: int) -> None:
        if self._event_is_current(generation) and not self._retry_pending:
            self._video_timeout.stop()
            self._prepare_retry("ERRO · falha na reprodução")

    def _on_player_ended(self, generation: int) -> None:
        if self._event_is_current(generation) and not self._retry_pending:
            self._video_timeout.stop()
            self._prepare_retry("ERRO · transmissão encerrada")

    def _check_video_progress(self) -> None:
        visible = self.isVisible()
        if (not self._stream_started or self._retry_pending
                or (visible and not self.player.has_video_output())):
            return
        stats = self.player.video_stats()
        now = time.monotonic()
        if stats is None:
            if now - self._attempt_started >= 15:
                self._prepare_retry("SEM VÍDEO")
            return

        mode = "displayed" if visible else "decoded"
        counter = stats[1] if mode == "displayed" else stats[0]
        if self._frame_counter_mode != mode or self._frame_counter is None:
            self._frame_counter_mode = mode
            self._frame_counter = counter
            self._frame_progress_count = 0
            self._last_frame_progress = now
            return
        if counter > self._frame_counter:
            self._frame_counter = counter
            self._last_frame_progress = now
            self._frame_progress_count += 1
            if self._frame_progress_count >= 2:
                self._mark_video_available()
            return
        if counter < self._frame_counter:
            self._frame_counter = counter
            self._frame_progress_count = 0
            self._last_frame_progress = now
            return
        if now - self._last_frame_progress >= 8:
            state = "VÍDEO CONGELADO" if self._video_available else "SEM VÍDEO"
            self._prepare_retry(state)

    def _prepare_retry(self, state: str | None = None) -> None:
        if not self._want_play or self._retry_pending:
            return
        self._video_timeout.stop()
        self._watchdog.stop()
        self._video_available = False
        self._stream_started = False
        self._retry_pending = True
        self._set_status(state or "ERRO")
        self._schedule_retry()

    def _retry_connection(self) -> None:
        if not self._want_play:
            return
        self._retry_pending = False
        self._set_status("RECONECTANDO")
        if self.endpoint is None:
            threading.Thread(target=self._resolve, daemon=True).start()
        else:
            self._start_attempt()

    def _schedule_retry(self) -> None:
        if not self._want_play or self._retry_timer.isActive():
            return
        delays = (3, 8, 15, 30)
        delay = delays[min(self._retry_count, len(delays) - 1)]
        self._retry_count += 1
        self._retry_timer.start(delay * 1000)

    def _check_alive(self) -> None:
        if not self._want_play or self._retry_pending:
            return
        self.player.poll_events()
        if not self._want_play or self._retry_pending:
            return
        if self.player.is_dead():
            self._on_player_failed(self._generation)
        elif self._stream_started:
            if self.player.has_video_output() or not self.isVisible():
                self._check_video_progress()
            elif time.monotonic() - self._attempt_started >= 8:
                self._prepare_retry("SEM VÍDEO")

    def stop(self) -> None:
        self._want_play = False
        self._watchdog.stop()
        self._video_timeout.stop()
        self._retry_timer.stop()
        self._generation = -1
        self.player.stop()
        self.endpoint = None
        self._attempts = 0
        self._retry_count = 0
        self._retry_pending = False
        self._stream_started = False
        self._video_available = False
        self._set_status("DESCONECTADA")

    def dispose(self) -> None:
        self._want_play = False
        self._watchdog.stop()
        self._video_timeout.stop()
        self._retry_timer.stop()
        self.endpoint = None
        self.player.release()
        self._retry_pending = False
        self._stream_started = False
        self._video_available = False
        self._set_status("DESCONECTADA")

    # ------------------------------------------------------------------ estado
    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_recording(self, on: bool) -> None:
        self._recording = on
        self._refresh_badge()

    def set_talking(self, on: bool) -> None:
        self._talking = on
        self._refresh_badge()

    def _refresh_badge(self) -> None:
        parts = (["⏺ REC"] if self._recording else []) + (["🎤 FALANDO"] if self._talking else [])
        self.badge_lbl.setText("  ".join(parts))

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit(self.cam.id)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.maximize_requested.emit(self.cam.id)
