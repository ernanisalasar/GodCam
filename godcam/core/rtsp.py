"""Montagem da URL RTSP a partir do cadastro da câmera."""
from __future__ import annotations

from urllib.parse import quote

from godcam.config import CameraConfig
from godcam.core.network import Endpoint


def build_rtsp_url(cam: CameraConfig, ep: Endpoint, mask_password: bool = False) -> str:
    password = "****" if mask_password else quote(cam.password, safe="")
    return cam.rtsp_template.format(
        host=ep.host,
        port=ep.rtsp_port,
        user=quote(cam.username, safe=""),
        password=password,
        channel=cam.channel,
        stream=cam.stream,
    )
