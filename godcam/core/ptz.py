"""Controle PTZ via ONVIF (ContinuousMove / Stop).

Os comandos rodam em uma thread própria para não travar a interface.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from godcam.core.security import sanitize_message


class PTZController:
    def __init__(self, host: str, port: int, user: str, password: str,
                 on_error: Callable[[str], None] | None = None) -> None:
        self.host, self.port, self.user, self.password = host, port, user, password
        self._on_error = on_error or (lambda msg: None)
        self._cam = None
        self._ptz = None
        self._token = None
        self._pool = ThreadPoolExecutor(max_workers=1)  # serializa os comandos

    # ---------- API pública (não bloqueante) ----------
    def move(self, pan: float = 0.0, tilt: float = 0.0, zoom: float = 0.0) -> None:
        """Velocidades normalizadas de -1.0 a 1.0."""
        self._submit(self._move, pan, tilt, zoom)

    def stop(self) -> None:
        self._submit(self._stop)

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ---------- internos ----------
    def _submit(self, fn, *args) -> None:
        def runner():
            try:
                fn(*args)
            except Exception as exc:  # noqa: BLE001
                self._on_error(f"PTZ: {sanitize_message(exc)}")
        self._pool.submit(runner)

    def _connect(self) -> None:
        if self._ptz is not None:
            return
        from onvif import ONVIFCamera  # import tardio: lib é pesada

        try:
            # adjust_time corrige falha de autenticação por relógio da câmera desajustado
            cam = ONVIFCamera(self.host, self.port, self.user, self.password, adjust_time=True)
        except TypeError:
            cam = ONVIFCamera(self.host, self.port, self.user, self.password)
        media = cam.create_media_service()
        self._ptz = cam.create_ptz_service()
        self._token = media.GetProfiles()[0].token
        self._cam = cam

    def _move(self, pan: float, tilt: float, zoom: float) -> None:
        self._connect()
        req = self._ptz.create_type("ContinuousMove")
        req.ProfileToken = self._token
        velocity = {"PanTilt": {"x": pan, "y": tilt}}
        if zoom:
            velocity["Zoom"] = {"x": zoom}
        req.Velocity = velocity
        self._ptz.ContinuousMove(req)

    def _stop(self) -> None:
        self._connect()
        req = self._ptz.create_type("Stop")
        req.ProfileToken = self._token
        req.PanTilt = True
        req.Zoom = True
        self._ptz.Stop(req)
