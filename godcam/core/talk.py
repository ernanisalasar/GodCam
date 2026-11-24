"""Áudio bidirecional ("Falar"): captura do microfone -> G.711 A-law -> câmera.

IMPORTANTE: a captura e a codificação (G.711) são padrão e estáveis. O transporte
até a câmera é o ponto frágil, pois as câmeras XMEye genéricas quase nunca suportam
ONVIF backchannel e usam o protocolo proprietário DVRIP (porta 34567).
`DvripTalkTransport` é EXPERIMENTAL: valide contra a sua câmera (veja README) e,
se o firmware divergir, só este transporte precisa ser ajustado/substituído.
"""
from __future__ import annotations

import hashlib
import json
import queue
import socket
import struct
import threading
from typing import Callable, Protocol

import numpy as np

from godcam.core.security import sanitize_message

# ---------------------------------------------------------------- G.711 A-law
_ALAW_SEG_END = np.array([0x1F, 0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF])


def encode_alaw(pcm16: np.ndarray) -> bytes:
    """PCM 16 bits -> G.711 A-law (1 byte/amostra). Implementação vetorizada."""
    pcm = pcm16.astype(np.int32) >> 3
    mask = np.where(pcm >= 0, 0xD5, 0x55)
    pcm = np.where(pcm >= 0, pcm, -pcm - 1)
    seg = np.minimum(np.searchsorted(_ALAW_SEG_END, pcm, side="left"), 8)
    shift = np.where(seg < 2, 1, seg)  # pcm já está em 13 bits (>> 3)
    aval = (seg << 4) | ((pcm >> shift) & 0x0F)
    aval = np.where(seg >= 8, 0x7F, aval)
    return ((aval ^ mask) & 0xFF).astype(np.uint8).tobytes()


# ------------------------------------------------------------------ Transportes
class TalkTransport(Protocol):
    def connect(self) -> None: ...
    def send_audio(self, alaw_frame: bytes) -> None: ...
    def close(self) -> None: ...


def sofia_hash(password: str) -> str:
    """Hash de senha usado pelo DVRIP/Xiongmai (MD5 reduzido a 8 caracteres)."""
    digest = hashlib.md5(password.encode()).digest()
    out = ""
    for i in range(8):
        n = (digest[2 * i] + digest[2 * i + 1]) % 62
        n += 48 if n <= 9 else (55 if n <= 35 else 61)
        out += chr(n)
    return out


class DvripTalkTransport:
    """EXPERIMENTAL — fala via DVRIP (porta 34567) com áudio G.711 A-law 8 kHz."""

    _HDR = "<BBBBIIBBHI"  # 20 bytes

    def __init__(self, host: str, port: int, user: str, password: str) -> None:
        self.host, self.port, self.user, self.password = host, port, user, password
        self._sock: socket.socket | None = None
        self._session = 0
        self._seq = 0

    def _send(self, msg_id: int, payload: bytes) -> None:
        self._seq += 1
        header = struct.pack(self._HDR, 0xFF, 0, 0, 0, self._session, self._seq, 0, 0, msg_id, len(payload))
        self._sock.sendall(header + payload)

    def _recv_n(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Conexão DVRIP encerrada pela câmera")
            buf += chunk
        return buf

    def _recv_json(self) -> dict:
        hdr = struct.unpack(self._HDR, self._recv_n(20))
        body = self._recv_n(hdr[-1]).rstrip(b"\x00\x0a")
        return json.loads(body.decode("utf-8", "ignore") or "{}")

    def connect(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), timeout=4)
        login = {"EncryptType": "MD5", "LoginType": "DVRIP-Web",
                 "PassWord": sofia_hash(self.password), "UserName": self.user}
        self._send(1000, json.dumps(login).encode() + b"\x0a\x00")
        resp = self._recv_json()
        if resp.get("Ret") not in (100, 515):
            raise ConnectionError(f"Login DVRIP recusado (Ret={resp.get('Ret')})")
        self._session = int(resp.get("SessionID", "0x0"), 16)
        claim = {"Name": "OPTalk", "SessionID": f"0x{self._session:08X}",
                 "OPTalk": {"Action": "Claim",
                            "AudioFormat": {"BitRate": 128, "EncodeType": "G711_ALAW",
                                            "SampleBit": 8, "SampleRate": 8}}}
        self._send(1430, json.dumps(claim).encode() + b"\x0a\x00")
        resp = self._recv_json()
        if resp.get("Ret") != 100:
            raise ConnectionError(f"Câmera recusou o canal de fala (Ret={resp.get('Ret')})")

    def send_audio(self, alaw_frame: bytes) -> None:
        # Cabeçalho de quadro de áudio: 00 00 01 FA | 0E (A-law) | 02 (8 kHz) | tamanho (LE16)
        frame = b"\x00\x00\x01\xFA\x0E\x02" + struct.pack("<H", len(alaw_frame)) + alaw_frame
        self._send(1432, frame)

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            finally:
                self._sock = None


# ---------------------------------------------------------------------- Serviço
class TalkService:
    """Push-to-talk: start() ao apertar, stop() ao soltar."""

    SAMPLE_RATE = 8000
    FRAME_SAMPLES = 160  # 20 ms

    def __init__(self, transport: TalkTransport, on_error: Callable[[str], None] | None = None) -> None:
        self._t = transport
        self._on_error = on_error or (lambda m: None)
        self._stream = None
        self._active = False
        self._q: queue.Queue = queue.Queue(maxsize=100)

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        self._q = queue.Queue(maxsize=100)
        threading.Thread(target=self._open, daemon=True).start()

    def _open(self) -> None:
        try:
            self._t.connect()  # pode demorar: fora da thread da UI
            if not self._active:  # usuário já soltou o botão
                self._t.close()
                return
            threading.Thread(target=self._send_loop, args=(self._q,), daemon=True).start()
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=self.FRAME_SAMPLES, callback=self._on_audio,
            )
            self._stream.start()
            if not self._active:
                self.stop()
        except Exception as exc:  # noqa: BLE001
            self._active = False
            self._on_error(f"Falar: {sanitize_message(exc)}")

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if self._active:
            try:
                self._q.put_nowait(encode_alaw(indata[:, 0]))
            except queue.Full:
                pass  # descarta quadro para não acumular atraso

    def _send_loop(self, q: queue.Queue) -> None:
        while True:
            frame = q.get()
            if frame is None:
                return
            try:
                self._t.send_audio(frame)
            except Exception as exc:  # noqa: BLE001
                self._on_error(f"Falar: {sanitize_message(exc)}")
                return

    def stop(self) -> None:
        self._active = False
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        self._q.put(None)
        self._t.close()
