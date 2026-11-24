"""Resolução de endereço: decide se usa o IP local ou o endereço externo."""
from __future__ import annotations

import socket
from dataclasses import dataclass

from godcam.config import CameraConfig


@dataclass
class Endpoint:
    host: str
    origin: str        # "local" | "remoto"
    rtsp_port: int
    onvif_port: int
    dvrip_port: int


def tcp_open(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _local(cam: CameraConfig) -> Endpoint:
    return Endpoint(cam.host_local, "local", cam.rtsp_port, cam.onvif_port, cam.dvrip_port)


def _remote(cam: CameraConfig) -> Endpoint:
    return Endpoint(
        cam.host_remote, "remoto",
        cam.remote_rtsp_port or cam.rtsp_port,
        cam.remote_onvif_port or cam.onvif_port,
        cam.remote_dvrip_port or cam.dvrip_port,
    )


def resolve_endpoint(cam: CameraConfig) -> Endpoint:
    """Modo auto: testa a porta RTSP local; se não responder, usa o endereço externo."""
    if cam.prefer == "local" and cam.host_local:
        return _local(cam)
    if cam.prefer == "remote" and cam.host_remote:
        return _remote(cam)
    if cam.host_local and tcp_open(cam.host_local, cam.rtsp_port):
        return _local(cam)
    if cam.host_remote:
        return _remote(cam)
    if cam.host_local:
        return _local(cam)
    raise ValueError("Câmera sem endereço configurado (local ou externo).")
