"""Modelo de dados e persistência DPAPI das câmeras em %APPDATA%/godcam."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass, field, fields
from pathlib import Path

from godcam.core.security import CredentialProtectionError, protect_secret, unprotect_secret

APP_NAME = "godcam"
CONFIG_FORMAT_VERSION = 2

# Formato RTSP clássico das placas Xiongmai/XMEye.
# Alternativas comuns: rtsp://{host}:{port}/onvif1  ou  rtsp://{user}:{password}@{host}:{port}/stream1
DEFAULT_RTSP_TEMPLATE = (
    "rtsp://{host}:{port}/user={user}&password={password}"
    "&channel={channel}&stream={stream}.sdp?real_stream"
)


def app_dir() -> Path:
    """Pasta de configuração do app."""
    base = os.environ.get("APPDATA") if sys.platform.startswith("win") else None
    root = Path(base) if base else Path.home() / ".config"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def recordings_dir() -> Path:
    """Pasta padrão das gravações (~/Videos/godcam)."""
    path = Path.home() / "Videos" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class CameraConfig:
    id: str
    name: str
    host_local: str = ""          # ex.: 192.0.2.10 (endereço fictício para documentação)
    host_remote: str = ""         # DDNS ou IP público (ou IP Tailscale)
    rtsp_port: int = 554
    onvif_port: int = 8899        # 8899 (XMEye) ou 80
    dvrip_port: int = 34567       # protocolo proprietário XMEye (usado no "Falar")
    # Portas externas (port forwarding). 0 = usar as mesmas portas locais.
    remote_rtsp_port: int = 0
    remote_onvif_port: int = 0
    remote_dvrip_port: int = 0
    username: str = "admin"
    password: str = field(default="", repr=False)
    channel: int = 1
    stream: int = 0               # 0 = principal (HD), 1 = secundário (leve, bom p/ remoto)
    prefer: str = "auto"          # auto | local | remote
    rtsp_template: str = DEFAULT_RTSP_TEMPLATE
    password_protected: str = field(default="", repr=False, compare=False)
    credential_error: str = field(default="", repr=False, compare=False)

    @staticmethod
    def new(**kwargs) -> "CameraConfig":
        return CameraConfig(id=uuid.uuid4().hex[:8], **kwargs)


class CameraStore:
    """Lista de câmeras salva em cameras.json."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        protect_password=protect_secret,
        unprotect_password=unprotect_secret,
        atomic_writer=None,
    ) -> None:
        self.path = path or app_dir() / "cameras.json"
        self.cameras: list[CameraConfig] = []
        self.credential_errors: list[str] = []
        self._protect_password = protect_password
        self._unprotect_password = unprotect_password
        self._atomic_writer = atomic_writer or _atomic_write_json

    def load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items, needs_migration = self._read_items(data)
            self.cameras = [self._camera_from_item(item) for item in items]
            if needs_migration:
                # A escrita só ocorre depois que todas as credenciais foram protegidas e validadas.
                self.save()
        else:
            # Instalações novas não recebem câmeras, rede ou credenciais pré-configuradas.
            self.cameras = []
            self.save()

    def save(self) -> None:
        payload = {
            "version": CONFIG_FORMAT_VERSION,
            "cameras": [self._item_from_camera(camera) for camera in self.cameras],
        }
        self._atomic_writer(self.path, payload)

    def _read_items(self, data: object) -> tuple[list[dict], bool]:
        if isinstance(data, list):
            if not all(isinstance(item, dict) for item in data):
                raise ValueError("O formato legado de cameras.json é inválido.")
            return data, True
        if not isinstance(data, dict) or data.get("version") != CONFIG_FORMAT_VERSION:
            raise ValueError("Versão de cameras.json não suportada.")
        items = data.get("cameras")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ValueError("O campo cameras de cameras.json é inválido.")
        # Um arquivo já versionado, mas que ainda contenha password plaintext, também é migrado.
        return items, any("password" in item for item in items)

    def _camera_from_item(self, item: dict) -> CameraConfig:
        known = {f.name for f in fields(CameraConfig)}
        values = {k: v for k, v in item.items() if k in known and k not in {"password", "password_protected", "credential_error"}}
        plaintext = item.get("password")
        protected = item.get("password_protected")
        if isinstance(protected, str):
            try:
                password = self._unprotect_password(protected)
            except CredentialProtectionError:
                name = str(values.get("name", "Câmera sem nome"))
                self.credential_errors.append(name)
                return CameraConfig(
                    **values,
                    password="",
                    password_protected=protected,
                    credential_error="Não foi possível recuperar a credencial protegida.",
                )
            return CameraConfig(**values, password=password, password_protected=protected)
        if isinstance(plaintext, str):
            return CameraConfig(**values, password=plaintext)
        return CameraConfig(**values, password="")

    def _item_from_camera(self, camera: CameraConfig) -> dict:
        item = {
            field_.name: getattr(camera, field_.name)
            for field_ in fields(CameraConfig)
            if field_.name not in {"password", "password_protected", "credential_error"}
        }
        if camera.credential_error and camera.password_protected and not camera.password:
            item["password_protected"] = camera.password_protected
            return item
        protected = self._protect_password(camera.password)
        try:
            if self._unprotect_password(protected) != camera.password:
                raise CredentialProtectionError("A validação da credencial protegida falhou.")
        except CredentialProtectionError:
            raise
        item["password_protected"] = protected
        return item

    def get(self, cam_id: str) -> CameraConfig | None:
        return next((c for c in self.cameras if c.id == cam_id), None)

    def upsert(self, cam: CameraConfig) -> None:
        for i, existing in enumerate(self.cameras):
            if existing.id == cam.id:
                self.cameras[i] = cam
                break
        else:
            self.cameras.append(cam)
        self.save()

    def remove(self, cam_id: str) -> None:
        self.cameras = [c for c in self.cameras if c.id != cam_id]
        self.save()


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Persiste JSON validado sem substituir o arquivo anterior antes do sucesso."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, ensure_ascii=False)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # Validação antes da substituição: arquivo JSON, versão e estrutura esperadas.
        validated = json.loads(temporary.read_text(encoding="utf-8"))
        if validated.get("version") != CONFIG_FORMAT_VERSION or not isinstance(validated.get("cameras"), list):
            raise ValueError("O JSON temporário de câmeras não passou na validação.")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
