"""Painel de controles da câmera ativa: PTZ, áudio, falar e gravar."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget)


class ControlPanel(QWidget):
    ptz_move = pyqtSignal(float, float, float)   # pan, tilt, zoom
    ptz_stop = pyqtSignal()
    talk_pressed = pyqtSignal()
    talk_released = pyqtSignal()
    record_toggled = pyqtSignal(bool)
    mute_toggled = pyqtSignal(bool)
    volume_changed = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.active_lbl = QLabel("Nenhuma câmera ativa")
        self.active_lbl.setObjectName("tileName")
        self.active_lbl.setWordWrap(True)
        self.active_lbl.setMinimumWidth(0)
        self.active_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        # ---- PTZ
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(1, 10)
        self.speed.setValue(5)
        pad = QGridLayout()
        pad.addWidget(self._hold("▲", 0, 1, 0), 0, 1)
        pad.addWidget(self._hold("◀", -1, 0, 0), 1, 0)
        stop = self._btn("■")
        stop.clicked.connect(self.ptz_stop.emit)
        pad.addWidget(stop, 1, 1)
        pad.addWidget(self._hold("▶", 1, 0, 0), 1, 2)
        pad.addWidget(self._hold("▼", 0, -1, 0), 2, 1)
        ptz_box = QGroupBox("Movimento (PTZ)")
        lay = QVBoxLayout(ptz_box)
        lay.setContentsMargins(5, 10, 5, 5)
        lay.setSpacing(4)
        lay.addLayout(pad)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        zoom_row.addStretch(1)
        zoom_row.addWidget(self._hold("＋", 0, 0, 1))
        zoom_row.addWidget(self._hold("－", 0, 0, -1))
        lay.addLayout(zoom_row)
        lay.addWidget(QLabel("Velocidade"))
        lay.addWidget(self.speed)

        # ---- Áudio
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.valueChanged.connect(self.volume_changed.emit)
        self.mute = QCheckBox("Mudo")
        self.mute.toggled.connect(self.mute_toggled.emit)
        audio_box = QGroupBox("Ouvir")
        lay = QVBoxLayout(audio_box)
        lay.setContentsMargins(5, 10, 5, 5)
        lay.setSpacing(4)
        lay.addWidget(self.volume)
        lay.addWidget(self.mute)

        # ---- Falar / Gravar
        _icon_dir = Path(__file__).parent.parent / "resources" / "icons"
        self.talk = QPushButton("Falar")
        self.talk.setIcon(QIcon(str(_icon_dir / "mic.svg")))
        self.talk.setIconSize(QSize(20, 20))
        self.talk.setObjectName("talk")
        self.talk.setToolTip("Mantenha pressionado para falar.")
        self.talk.pressed.connect(self.talk_pressed.emit)
        self.talk.released.connect(self.talk_released.emit)
        self.record = QPushButton("Gravar")
        self.record.setIcon(QIcon(str(_icon_dir / "circle-dot.svg")))
        self.record.setIconSize(QSize(20, 20))
        self.record.setCheckable(True)
        self.record.toggled.connect(self._on_record)
        action_box = QGroupBox("Ações")
        lay = QVBoxLayout(action_box)
        lay.setContentsMargins(5, 10, 5, 5)
        lay.setSpacing(4)
        lay.addWidget(self.talk)
        lay.addWidget(self.record)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)
        for w in (self.active_lbl, ptz_box, audio_box, action_box):
            root.addWidget(w)
        root.addStretch(1)
        self.set_controls_enabled(False)

    # ---------------------------------------------------------------- helpers
    def _btn(self, text: str) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setProperty("class", "ptz")
        b.setFixedSize(32, 32)
        b.setStyleSheet("font-size:14px; padding:0px;")
        return b

    def _hold(self, text: str, pan: int, tilt: int, zoom: int) -> QToolButton:
        """Botão que move enquanto pressionado e para ao soltar."""
        b = self._btn(text)
        b.pressed.connect(lambda: self.ptz_move.emit(*(v * self.speed.value() / 10.0 for v in (pan, tilt, zoom))))
        b.released.connect(self.ptz_stop.emit)
        return b

    def _on_record(self, on: bool) -> None:
        self.record.setText("Parar gravação" if on else "Gravar")
        self.record_toggled.emit(on)

    # -------------------------------------------------------------- API pública
    def set_active(self, name: str | None) -> None:
        self.active_lbl.setText(f"Câmera ativa: {name}" if name else "Nenhuma câmera ativa")
        self.set_controls_enabled(name is not None)

    def set_controls_enabled(self, enabled: bool) -> None:
        for w in (self.talk, self.record, self.volume, self.mute, self.speed):
            w.setEnabled(enabled)
        for b in self.findChildren(QToolButton):
            b.setEnabled(enabled)

    def set_recording(self, on: bool) -> None:
        self.record.blockSignals(True)
        self.record.setChecked(on)
        self.record.setText("Parar gravação" if on else "Gravar")
        self.record.blockSignals(False)
