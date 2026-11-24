"""Diálogo de cadastro/edição de câmera."""
from __future__ import annotations

from dataclasses import replace

from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
                             QMessageBox, QSpinBox, QVBoxLayout)

from godcam.config import DEFAULT_RTSP_TEMPLATE, CameraConfig


def _spin(value: int, lo: int = 0, hi: int = 65535) -> QSpinBox:
    box = QSpinBox()
    box.setRange(lo, hi)
    box.setValue(value)
    return box


class CameraDialog(QDialog):
    def __init__(self, cam: CameraConfig | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Câmera")
        self.setMinimumWidth(460)
        self._cam = cam or CameraConfig.new(name="Nova câmera")
        c = self._cam

        self.name = QLineEdit(c.name)
        self.host_local = QLineEdit(c.host_local)
        self.host_local.setPlaceholderText("192.0.2.10 (exemplo fictício)")
        self.host_remote = QLineEdit(c.host_remote)
        self.host_remote.setPlaceholderText("meucam.ddns.net  /  IP público  /  IP Tailscale")
        self.rtsp_port, self.onvif_port, self.dvrip_port = _spin(c.rtsp_port), _spin(c.onvif_port), _spin(c.dvrip_port)
        self.r_rtsp, self.r_onvif, self.r_dvrip = (_spin(c.remote_rtsp_port), _spin(c.remote_onvif_port),
                                                   _spin(c.remote_dvrip_port))
        for w in (self.r_rtsp, self.r_onvif, self.r_dvrip):
            w.setSpecialValueText("igual ao local")
        self.user = QLineEdit(c.username)
        self.password = QLineEdit(c.password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.channel = _spin(c.channel, 1, 64)
        self.stream = QComboBox()
        self.stream.addItem("Principal (HD)", 0)
        self.stream.addItem("Secundário (leve — melhor p/ acesso remoto)", 1)
        self.stream.setCurrentIndex(0 if c.stream == 0 else 1)
        self.prefer = QComboBox()
        for label, value in (("Automático (local → externo)", "auto"), ("Sempre local", "local"),
                             ("Sempre externo", "remote")):
            self.prefer.addItem(label, value)
        self.prefer.setCurrentIndex(max(0, self.prefer.findData(c.prefer)))
        self.template = QLineEdit(c.rtsp_template)

        form = QFormLayout()
        form.addRow("Nome", self.name)
        form.addRow("IP local", self.host_local)
        form.addRow("Endereço externo", self.host_remote)
        form.addRow("Porta RTSP", self.rtsp_port)
        form.addRow("Porta ONVIF", self.onvif_port)
        form.addRow("Porta DVRIP (Falar)", self.dvrip_port)
        form.addRow("Porta RTSP externa", self.r_rtsp)
        form.addRow("Porta ONVIF externa", self.r_onvif)
        form.addRow("Porta DVRIP externa", self.r_dvrip)
        form.addRow("Usuário", self.user)
        form.addRow("Senha", self.password)
        form.addRow("Canal", self.channel)
        form.addRow("Stream", self.stream)
        form.addRow("Conectar usando", self.prefer)
        form.addRow("Modelo da URL RTSP", self.template)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _validate(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "godcam", "Informe um nome.")
        elif not (self.host_local.text().strip() or self.host_remote.text().strip()):
            QMessageBox.warning(self, "godcam", "Informe o IP local e/ou o endereço externo.")
        elif self._cam.credential_error and not self.password.text():
            QMessageBox.warning(
                self,
                "godcam",
                "A credencial protegida não pôde ser recuperada. Informe uma nova senha para salvar esta câmera.",
            )
        else:
            self.accept()

    def result_config(self) -> CameraConfig:
        return replace(
            self._cam,
            name=self.name.text().strip(),
            host_local=self.host_local.text().strip(),
            host_remote=self.host_remote.text().strip(),
            rtsp_port=self.rtsp_port.value(), onvif_port=self.onvif_port.value(),
            dvrip_port=self.dvrip_port.value(),
            remote_rtsp_port=self.r_rtsp.value(), remote_onvif_port=self.r_onvif.value(),
            remote_dvrip_port=self.r_dvrip.value(),
            username=self.user.text().strip(), password=self.password.text(),
            password_protected="", credential_error="",
            channel=self.channel.value(), stream=self.stream.currentData(),
            prefer=self.prefer.currentData(),
            rtsp_template=self.template.text().strip() or DEFAULT_RTSP_TEMPLATE,
        )
