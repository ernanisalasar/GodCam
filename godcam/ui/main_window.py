"""Janela principal: lista de câmeras, grade de vídeo e painel de controles."""
from __future__ import annotations

from pathlib import Path

import vlc
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QAction, QColor, QIcon
from PyQt6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
                             QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget)

from godcam.config import CameraConfig, CameraStore
from godcam.core.player import RtspAudioPlayer
from godcam.core.ptz import PTZController
from godcam.core.recorder import Recorder, RecorderError
from godcam.core.rtsp import build_rtsp_url
from godcam.core.security import sanitize_message
from godcam.core.talk import DvripTalkTransport, TalkService
from godcam.ui.camera_dialog import CameraDialog
from godcam.ui.control_panel import ControlPanel
from godcam.ui.help_dialog import HelpDialog
from godcam.ui.video_tile import VideoTile


class _GridSlot(QFrame):
    activated = pyqtSignal(int)

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.setObjectName("emptySlot")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        label = QLabel("BLOCO VAZIO\nSelecione uma câmera e clique aqui")
        label.setObjectName("emptySlotText")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.activated.emit(self.index)


class MainWindow(QMainWindow):
    error = pyqtSignal(str)  # permite reportar erros vindos de threads com segurança

    def __init__(self, store: CameraStore) -> None:
        super().__init__()
        self.store = store
        self.tiles: dict[str, VideoTile] = {}
        self.recorders: dict[str, Recorder] = {}
        self.ptz: dict[tuple, PTZController] = {}
        self.talk: TalkService | None = None
        self.audio_player = RtspAudioPlayer(self)
        self._audio_error_reported = False
        self.active_id: str | None = None
        self.maximized_id: str | None = None
        self.slot_assignments: dict[int, str] = {}
        self.grid_slots: dict[int, _GridSlot] = {}
        self.grid_count = 4
        self.video_display_mode = "fill"
        self._syncing_selection = False
        self.volume = 80
        self.user_muted = False
        self._closing = False

        self.setWindowTitle("GodCam")
        icon_path = Path(__file__).parent.parent / "resources" / "scan-eye.ico"
        self.setWindowIcon(QIcon(str(icon_path)))
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        available_width = available.width() if available else 1366
        available_height = available.height() if available else 768
        self.setMinimumSize(min(800, available_width), min(560, available_height))
        self.resize(min(1366, available_width), min(768, available_height))
        self._build_ui()
        self._build_help_menu()
        self._refresh_list()
        self.error.connect(self._show_error)

        self._rec_timer = QTimer(self)  # detecta gravações que caíram
        self._rec_timer.timeout.connect(self._poll_recorders)
        self._rec_timer.start(2000)
        self._audio_timer = QTimer(self)
        self._audio_timer.timeout.connect(self._poll_audio)
        self._audio_timer.start(1000)

    # ===================================================================== UI
    def _build_help_menu(self) -> None:
        menu = self.menuBar().addMenu("Ajuda")
        help_action = QAction("Ajuda do GodCam", self)
        help_action.triggered.connect(lambda: HelpDialog(self).exec())
        menu.addAction(help_action)
        about_action = QAction("Sobre o GodCam", self)
        about_action.triggered.connect(lambda: HelpDialog(self, show_about=True).exec())
        menu.addAction(about_action)

    def _build_ui(self) -> None:
        self.regions = QSplitter(Qt.Orientation.Horizontal)
        self.regions.setChildrenCollapsible(False)

        # Esquerda: lista de câmeras e ações.
        self.listw = QListWidget()
        # Prepare icon directory (relative to this file)
        _icon_dir = Path(__file__).parent.parent / "resources" / "icons"

        self.listw.setObjectName("cameraList")
        self.listw.setMinimumWidth(150)
        self.listw.setWordWrap(True)
        self.listw.itemDoubleClicked.connect(lambda _: self._connect_selected())
        self.listw.currentItemChanged.connect(self._on_list_selection_changed)
        camera_panel = QWidget()
        camera_panel.setObjectName("sidePanel")
        camera_panel.setMinimumWidth(165)
        camera_layout = QVBoxLayout(camera_panel)
        camera_layout.setContentsMargins(6, 6, 6, 6)
        camera_layout.setSpacing(4)
        camera_title = QLabel("CÂMERAS")
        camera_title.setObjectName("sectionTitle")
        camera_layout.addWidget(camera_title)
        camera_layout.addWidget(self.listw, 1)
        # ---- Botões de controle (vertical) ----
        # Conectar
        connect_btn = QPushButton("Conectar")
        connect_btn.setIcon(QIcon(str(_icon_dir / "link.svg")))
        connect_btn.setIconSize(QSize(20, 20))
        connect_btn.clicked.connect(self._connect_selected)
        connect_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        connect_btn.setMinimumHeight(38)
        camera_layout.addWidget(connect_btn)
        # Desconectar
        disconnect_btn = QPushButton("Desconectar")
        disconnect_btn.setIcon(QIcon(str(_icon_dir / "unplug.svg")))
        disconnect_btn.setIconSize(QSize(20, 20))
        disconnect_btn.clicked.connect(self._disconnect_selected)
        disconnect_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        disconnect_btn.setMinimumHeight(38)
        camera_layout.addWidget(disconnect_btn)
        # Adicionar câmera
        add_button = QPushButton("Adicionar câmera")
        add_button.setIcon(QIcon(str(_icon_dir / "plus.svg")))
        add_button.setIconSize(QSize(20, 20))
        add_button.clicked.connect(self._add_camera)
        add_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        add_button.setMinimumHeight(38)
        camera_layout.addWidget(add_button)
        # Editar
        edit_btn = QPushButton("Editar")
        edit_btn.setIcon(QIcon(str(_icon_dir / "pencil.svg")))
        edit_btn.setIconSize(QSize(20, 20))
        edit_btn.clicked.connect(self._edit_camera)
        edit_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        edit_btn.setMinimumHeight(38)
        camera_layout.addWidget(edit_btn)
        # Remover
        remove_btn = QPushButton("Remover")
        remove_btn.setIcon(QIcon(str(_icon_dir / "trash.svg")))
        remove_btn.setIconSize(QSize(20, 20))
        remove_btn.clicked.connect(self._remove_camera)
        remove_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        remove_btn.setMinimumHeight(38)
        camera_layout.addWidget(remove_btn)
        # Conectar todas (mantido sem ícone)
        all_btn = QPushButton("Conectar todas")
        all_btn.clicked.connect(self._connect_all)
        all_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        all_btn.setMinimumHeight(38)
        camera_layout.addWidget(all_btn)

        # Centro: blocos persistentes; alterar a grade só muda sua disposição.
        center = QWidget()
        center.setObjectName("root")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(5, 4, 5, 4)
        center_layout.setSpacing(5)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("GRADE"))
        self.grid_size = QComboBox()
        for label, count, rows, columns in (
            ("1 · 1×1", 1, 1, 1), ("4 · 2×2", 4, 2, 2), ("6 · 2×3", 6, 2, 3),
            ("9 · 3×3", 9, 3, 3), ("16 · 4×4", 16, 4, 4), ("25 · 5×5", 25, 5, 5),
            ("36 · 6×6", 36, 6, 6), ("64 · 8×8", 64, 8, 8),
        ):
            self.grid_size.addItem(label, (count, rows, columns))
        self.grid_size.setCurrentIndex(1)
        self.grid_size.currentIndexChanged.connect(self._on_grid_size_changed)
        toolbar.addWidget(self.grid_size)
        toolbar.addWidget(QLabel("VÍDEO"))
        self.display_mode = QComboBox()
        self.display_mode.addItem("Preencher", "fill")
        self.display_mode.addItem("Ajustar", "fit")
        self.display_mode.addItem("Esticar", "stretch")
        self.display_mode.setToolTip(
            "Preencher aproveita todo o bloco quando a proporção coincide; Ajustar mostra "
            "o quadro completo; Esticar pode deformar a imagem."
        )
        self.display_mode.currentIndexChanged.connect(self._on_display_mode_changed)
        toolbar.addWidget(self.display_mode)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("Clique em um bloco vazio para mover a câmera ativa"))
        center_layout.addLayout(toolbar)
        self.grid_host = QWidget()
        self.grid_host.setObjectName("videoGrid")
        self.grid_host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(4)
        self.grid_area = QWidget(center)
        area_layout = QVBoxLayout(self.grid_area)
        area_layout.setContentsMargins(0, 0, 0, 0)
        area_layout.addWidget(self.grid_host, 0, Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.grid_area, 1)

        # Direita: controles compactos e roláveis.
        self.panel = ControlPanel()
        self.panel.ptz_move.connect(self._ptz_move)
        self.panel.ptz_stop.connect(self._ptz_stop)
        self.panel.talk_pressed.connect(self._talk_start)
        self.panel.talk_released.connect(self._talk_stop)
        self.panel.record_toggled.connect(self._toggle_record)
        self.panel.mute_toggled.connect(self._on_mute)
        self.panel.volume_changed.connect(self._on_volume)
        controls_scroll = QScrollArea()
        controls_scroll.setObjectName("controlsScroll")
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFrameShape(QFrame.Shape.NoFrame)
        controls_scroll.setMinimumWidth(225)
        controls_scroll.setWidget(self.panel)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.regions.addWidget(camera_panel)
        self.regions.addWidget(center)
        self.regions.addWidget(controls_scroll)
        self.regions.setStretchFactor(0, 0)
        self.regions.setStretchFactor(1, 1)
        self.regions.setStretchFactor(2, 0)
        self.regions.setSizes([195, 941, 230])
        self.setCentralWidget(self.regions)
        self.regions.splitterMoved.connect(lambda *_: QTimer.singleShot(0, self._resize_grid))
        self.statusBar().showMessage("Duplo clique no bloco para ampliar ou restaurar.")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "grid_area"):
            QTimer.singleShot(0, self._resize_grid)

    def _resize_grid(self) -> None:
        if not hasattr(self, "grid_area"):
            return
        _, rows, columns = self.grid_size.currentData()
        if self.maximized_id in self.tiles:
            rows = columns = 1
        area = self.grid_area.contentsRect()
        spacing = self.grid.spacing()
        frame_inset = VideoTile.FRAME_BORDER * 2
        available_video_width = max(
            0, area.width() - spacing * (columns - 1) - frame_inset * columns
        ) / columns
        available_video_height = max(
            0, area.height() - spacing * (rows - 1) - frame_inset * rows
        ) / rows
        cell_width = min(
            available_video_width,
            available_video_height * (16 / 9),
        )
        cell_height = cell_width * (9 / 16)
        width = max(1, round((cell_width + frame_inset) * columns + spacing * (columns - 1)))
        height = max(1, round((cell_height + frame_inset) * rows + spacing * (rows - 1)))
        if self.grid_host.size().width() != width or self.grid_host.size().height() != height:
            self.grid_host.setFixedSize(width, height)

    def _refresh_list(self) -> None:
        current = self._selected_id()
        if current is None or self.store.get(current) is None:
            current = self.active_id if self.active_id and self.store.get(self.active_id) else None
        self._syncing_selection = True
        self.listw.clear()
        for cam in self.store.cameras:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, cam.id)
            self.listw.addItem(item)
            if cam.id == current:
                self.listw.setCurrentItem(item)
            self._update_camera_status(cam.id)
        self._syncing_selection = False
        self._select(current)

    def _selected_id(self) -> str | None:
        item = self.listw.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_list_selection_changed(self, current, previous) -> None:
        if not self._syncing_selection and current is not None:
            self._select(current.data(Qt.ItemDataRole.UserRole))

    def _update_camera_status(self, cam_id: str, status: str | None = None) -> None:
        cam = self.store.get(cam_id)
        if cam is None:
            return
        for index in range(self.listw.count()):
            item = self.listw.item(index)
            if item.data(Qt.ItemDataRole.UserRole) != cam_id:
                continue
            tile = self.tiles.get(cam_id)
            current_status = status or (tile.status_lbl.text() if tile else "DESCONECTADA")
            address = cam.host_local or cam.host_remote or "Sem endereço"
            item.setText(f"{cam.name}\n{address}  ·  {current_status}")
            item.setToolTip(f"{cam.name} · {address} · {current_status}")
            normalized = current_status.split(" · ", 1)[0].strip()
            color = ("#4ade80" if normalized == "REPRODUZINDO" else
                     "#f87171" if normalized in
                     ("ERRO", "SEM VÍDEO", "VÍDEO CONGELADO") else
                     "#fbbf24" if normalized in ("CONECTANDO", "RECONECTANDO") else "#8b93a1")
            item.setForeground(QColor(color))
            break

    # ================================================== gerenciador de câmeras
    def _add_camera(self) -> None:
        dlg = CameraDialog(parent=self)
        if dlg.exec():
            self.store.upsert(dlg.result_config())
            self._refresh_list()

    def _edit_camera(self) -> None:
        cam = self.store.get(self._selected_id() or "")
        if not cam:
            return
        dlg = CameraDialog(cam, self)
        if dlg.exec():
            new = dlg.result_config()
            self.store.upsert(new)
            if new.id in self.tiles:  # reconecta com as novas configurações
                self._disconnect(new.id)
                self._connect(new.id)
            self._refresh_list()

    def _remove_camera(self) -> None:
        cam = self.store.get(self._selected_id() or "")
        if cam and QMessageBox.question(self, "godcam", f"Remover '{cam.name}'?") == QMessageBox.StandardButton.Yes:
            self._disconnect(cam.id)
            self.store.remove(cam.id)
            self._refresh_list()

    # ========================================================== conexões/vídeo
    def _connect_selected(self) -> None:
        if cam_id := self._selected_id():
            self._connect(cam_id)

    def _disconnect_selected(self) -> None:
        if cam_id := self._selected_id():
            self._disconnect(cam_id)

    def _connect_all(self) -> None:
        for cam in self.store.cameras:
            self._connect(cam.id)

    def _next_free_slot(self) -> int | None:
        occupied = set(self.slot_assignments)
        for index in range(self.grid_count):
            if index not in occupied:
                return index
        if self.grid_count < 64:
            next_index = next(i for i, count in enumerate((1, 4, 6, 9, 16, 25, 36, 64))
                              if count > self.grid_count)
            self.grid_size.setCurrentIndex(next_index)
            for index in range(self.grid_count):
                if index not in occupied:
                    return index
        return None

    def _connect(self, cam_id: str, slot_index: int | None = None) -> None:
        cam = self.store.get(cam_id)
        if not cam:
            return
        if cam_id not in self.tiles:
            if slot_index is None:
                slot_index = self._next_free_slot()
            elif slot_index >= self.grid_count:
                self._show_error("O bloco escolhido não pertence à grade atual.")
                return
            if slot_index is None:
                self._show_error("A grade está cheia. Escolha um layout maior.")
                return
            tile = VideoTile(cam, self.grid_host)
            tile.clicked.connect(self._select)
            tile.maximize_requested.connect(self._toggle_maximize)
            tile.status_changed.connect(lambda status, camera_id=cam_id:
                                        self._on_tile_status(camera_id, status))
            self.tiles[cam_id] = tile
            tile.set_display_mode(self.video_display_mode)
            self._assign_to_slot(cam_id, slot_index)
            self._relayout()
            tile.start()
        elif slot_index is not None:
            self._assign_to_slot(cam_id, slot_index)
            self._relayout()
        else:
            assigned_slot = next((index for index, assigned_id in self.slot_assignments.items()
                                  if assigned_id == cam_id), None)
            if assigned_slot is not None and assigned_slot >= self.grid_count:
                assigned_slot = None
            if assigned_slot is not None:
                self._select(cam_id)
                return
            free_slot = self._next_free_slot()
            if free_slot is None:
                self._show_error("A grade está cheia. Escolha um layout maior.")
                return
            self._assign_to_slot(cam_id, free_slot)
            self._relayout()
        self._select(cam_id)

    def _assign_to_slot(self, cam_id: str, slot_index: int) -> None:
        previous_slot = next((index for index, assigned_id in self.slot_assignments.items()
                              if assigned_id == cam_id), None)
        displaced_id = self.slot_assignments.get(slot_index)
        swapped = previous_slot is not None and displaced_id is not None
        if swapped:
            self.slot_assignments[previous_slot] = displaced_id
        elif displaced_id is not None:
            self.slot_assignments.pop(slot_index)
        if previous_slot is not None and previous_slot != slot_index and not swapped:
            self.slot_assignments.pop(previous_slot, None)
        self.slot_assignments[slot_index] = cam_id

    def _on_tile_status(self, cam_id: str, status: str) -> None:
        self._update_camera_status(cam_id, status)
        if cam_id == self.active_id:
            self._apply_audio()
        cam = self.store.get(cam_id)
        if cam:
            self.statusBar().showMessage(f"{cam.name}: {status}", 5000)

    def _on_grid_size_changed(self, index: int) -> None:
        self.grid_count = self.grid_size.itemData(index)[0]
        self._relayout()
        QTimer.singleShot(0, self._resize_grid)

    def _on_display_mode_changed(self, index: int) -> None:
        self.video_display_mode = self.display_mode.itemData(index)
        for tile in self.tiles.values():
            tile.set_display_mode(self.video_display_mode)

    def _activate_slot(self, slot_index: int) -> None:
        cam_id = self.slot_assignments.get(slot_index)
        if cam_id is not None:
            self._select(cam_id)
        elif self.active_id is not None:
            if self.active_id not in self.tiles:
                self._connect(self.active_id, slot_index)
            else:
                self._assign_to_slot(self.active_id, slot_index)
                self._relayout()

    def _disconnect(self, cam_id: str) -> None:
        tile = self.tiles.pop(cam_id, None)
        if not tile:
            return
        if cam_id in self.recorders:
            self._stop_recording(cam_id)
        if self.maximized_id == cam_id:
            self.maximized_id = None
        for slot_index, assigned_id in tuple(self.slot_assignments.items()):
            if assigned_id == cam_id:
                self.slot_assignments.pop(slot_index)
        tile.dispose()
        tile.setParent(None)
        tile.deleteLater()
        if self.active_id == cam_id:
            self.active_id = None
            next_camera = next(iter(self.slot_assignments.values()), next(iter(self.tiles), None))
            self._select(next_camera)
        self._update_camera_status(cam_id)
        self._relayout()

    def _relayout(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        for index in range(64):
            self.grid.setRowStretch(index, 0)
            self.grid.setColumnStretch(index, 0)
        if self.maximized_id in self.tiles:
            tile = self.tiles[self.maximized_id]
            for cam_id, other_tile in self.tiles.items():
                other_tile.setVisible(cam_id == self.maximized_id)
            for slot in self.grid_slots.values():
                slot.setVisible(False)
            self.grid.addWidget(tile, 0, 0)
            QTimer.singleShot(0, self._resize_grid)
            return
        _, rows, columns = self.grid_size.currentData()
        for row in range(rows):
            self.grid.setRowStretch(row, 1)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)
        visible_ids = set()
        for slot_index in range(self.grid_count):
            row, column = divmod(slot_index, columns)
            cam_id = self.slot_assignments.get(slot_index)
            if cam_id in self.tiles:
                tile = self.tiles[cam_id]
                self.grid.addWidget(tile, row, column)
                tile.setVisible(True)
                visible_ids.add(cam_id)
            else:
                slot = self.grid_slots.get(slot_index)
                if slot is None:
                    slot = _GridSlot(slot_index, self.grid_host)
                    slot.activated.connect(self._activate_slot)
                    self.grid_slots[slot_index] = slot
                self.grid.addWidget(slot, row, column)
                slot.setVisible(True)
        for cam_id, tile in self.tiles.items():
            if cam_id not in visible_ids:
                tile.setVisible(False)
        for slot_index, slot in self.grid_slots.items():
            if slot_index >= self.grid_count:
                slot.setVisible(False)
        QTimer.singleShot(0, self._resize_grid)

    def _toggle_maximize(self, cam_id: str) -> None:
        self.maximized_id = None if self.maximized_id == cam_id else cam_id
        self._select(cam_id)
        self._relayout()

    def _select(self, cam_id: str | None) -> None:
        if cam_id is not None and self.store.get(cam_id) is None:
            cam_id = None
        self.active_id = cam_id
        self._syncing_selection = True
        for index in range(self.listw.count()):
            item = self.listw.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == cam_id:
                self.listw.setCurrentItem(item)
                break
        if cam_id is None:
            self.listw.setCurrentItem(None)
            self.listw.clearSelection()
        self._syncing_selection = False
        for cid, tile in self.tiles.items():
            tile.set_active(cid == cam_id)
        tile = self._active_tile()
        self.panel.set_active(tile.cam.name if tile else None)
        self.panel.set_recording(cam_id in self.recorders)
        self._apply_audio()

    def _active_tile(self) -> VideoTile | None:
        return self.tiles.get(self.active_id or "")

    # ================================================================== áudio
    def _apply_audio(self) -> None:
        """Only the verified active camera has a separate audio-only RTSP player."""
        self.audio_player.set_volume(self.volume)
        tile = self._active_tile()
        talking = self.talk is not None
        if (self._closing or tile is None or tile.endpoint is None or self.user_muted or talking
                or tile.status_lbl.text() != "REPRODUZINDO"):
            self.audio_player.set_muted(True)
            self.audio_player.stop()
            self._audio_error_reported = False
            return

        self.audio_player.set_muted(False)
        try:
            self.audio_player.play(
                build_rtsp_url(tile.cam, tile.endpoint),
                username=tile.cam.username,
                password=tile.cam.password,
            )
        except (RuntimeError, vlc.VLCException):
            self.audio_player.set_muted(True)
            self.audio_player.stop()
            if not self._audio_error_reported:
                self._show_error("Não foi possível iniciar o áudio da câmera ativa.")
            self._audio_error_reported = True
        else:
            self._audio_error_reported = False

    def _poll_audio(self) -> None:
        if not self._closing and self.audio_player.is_dead():
            self.audio_player.set_muted(True)
            self.audio_player.stop()
            if not self._audio_error_reported:
                self._show_error("A transmissão de áudio da câmera ativa foi interrompida.")
            self._audio_error_reported = True

    def _on_mute(self, muted: bool) -> None:
        self.user_muted = muted
        self._apply_audio()

    def _on_volume(self, value: int) -> None:
        self.volume = value
        self._apply_audio()

    # =================================================================== PTZ
    def _ptz_for(self, tile: VideoTile) -> PTZController:
        ep = tile.endpoint
        if ep is None:
            raise RuntimeError("A câmera ainda não conectou.")
        key = (tile.cam.id, ep.host, ep.onvif_port)
        if key not in self.ptz:
            self.ptz[key] = PTZController(ep.host, ep.onvif_port, tile.cam.username,
                                          tile.cam.password, on_error=self.error.emit)
        return self.ptz[key]

    def _ptz_move(self, pan: float, tilt: float, zoom: float) -> None:
        if tile := self._active_tile():
            try:
                self._ptz_for(tile).move(pan, tilt, zoom)
            except Exception as exc:  # noqa: BLE001
                self._show_error(str(exc))

    def _ptz_stop(self) -> None:
        if tile := self._active_tile():
            try:
                self._ptz_for(tile).stop()
            except Exception as exc:  # noqa: BLE001
                self._show_error(str(exc))

    # ================================================================= Falar
    def _talk_start(self) -> None:
        tile = self._active_tile()
        if not tile or tile.endpoint is None or self.talk:
            return
        ep, cam = tile.endpoint, tile.cam
        transport = DvripTalkTransport(ep.host, ep.dvrip_port, cam.username, cam.password)
        self.talk = TalkService(transport, on_error=self.error.emit)
        self.talk.start()
        tile.set_talking(True)
        self._apply_audio()

    def _talk_stop(self) -> None:
        if not self.talk:
            return
        self.talk.stop()
        self.talk = None
        for tile in self.tiles.values():
            tile.set_talking(False)
        self._apply_audio()

    # =============================================================== Gravação
    def _toggle_record(self, on: bool) -> None:
        tile = self._active_tile()
        if not tile:
            return
        if not on:
            self._stop_recording(tile.cam.id)
            return
        if tile.endpoint is None:
            self.panel.set_recording(False)
            self._show_error("A câmera ainda não conectou.")
            return
        rec = Recorder()
        try:
            path = rec.start(build_rtsp_url(tile.cam, tile.endpoint), tile.cam.name)
        except RecorderError as exc:
            self.panel.set_recording(False)
            self._show_error(str(exc))
            return
        self.recorders[tile.cam.id] = rec
        tile.set_recording(True)
        self.statusBar().showMessage(f"Gravando em {path}", 8000)

    def _stop_recording(self, cam_id: str) -> None:
        rec = self.recorders.pop(cam_id, None)
        if rec:
            rec.stop()
            self.statusBar().showMessage(f"Gravação salva: {rec.output}", 8000)
        if tile := self.tiles.get(cam_id):
            tile.set_recording(False)
        if cam_id == self.active_id:
            self.panel.set_recording(False)

    def _poll_recorders(self) -> None:
        for cam_id, rec in list(self.recorders.items()):
            if not rec.is_running():
                self.recorders.pop(cam_id)
                if tile := self.tiles.get(cam_id):
                    tile.set_recording(False)
                if cam_id == self.active_id:
                    self.panel.set_recording(False)
                self._show_error(f"A gravação parou. {rec.last_error}")

    # ================================================================== misc
    def _show_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"⚠ {sanitize_message(msg)}", 10000)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._closing = True
        self._audio_timer.stop()
        self._talk_stop()
        for cam_id in list(self.recorders):
            self._stop_recording(cam_id)
        for ctrl in self.ptz.values():
            ctrl.close()
        for cam_id in list(self.tiles):
            self._disconnect(cam_id)
        self.audio_player.release()
        super().closeEvent(event)
