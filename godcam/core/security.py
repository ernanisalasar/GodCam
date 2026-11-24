"""Proteção local de credenciais e sanitização de mensagens diagnósticas."""
from __future__ import annotations

import base64
import ctypes
import os
import re
from ctypes import wintypes


class CredentialProtectionError(RuntimeError):
    """A proteção ou recuperação de uma credencial não pôde ser concluída."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


_CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _windows_only() -> None:
    if os.name != "nt":
        raise CredentialProtectionError("A proteção DPAPI requer Windows.")


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _copy_and_free(blob: _DataBlob) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        if blob.pbData:
            ctypes.windll.kernel32.LocalFree(blob.pbData)


def protect_secret(value: str) -> str:
    """Protege texto UTF-8 com DPAPI no escopo do usuário Windows atual."""
    _windows_only()
    if not isinstance(value, str):
        raise TypeError("A credencial deve ser texto.")

    source, _source_buffer = _blob(value.encode("utf-8"))
    target = _DataBlob()
    crypt_protect = ctypes.windll.crypt32.CryptProtectData
    crypt_protect.argtypes = (
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)
    )
    crypt_protect.restype = wintypes.BOOL
    if not crypt_protect(
        ctypes.byref(source), "GodCam camera credential", None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(target)
    ):
        code = ctypes.get_last_error()
        raise CredentialProtectionError(f"Não foi possível proteger a credencial (Windows error {code}).")
    return base64.b64encode(_copy_and_free(target)).decode("ascii")


def unprotect_secret(protected: str) -> str:
    """Recupera em memória uma credencial DPAPI codificada para JSON."""
    _windows_only()
    if not isinstance(protected, str):
        raise CredentialProtectionError("O valor protegido da credencial é inválido.")
    try:
        encoded = base64.b64decode(protected.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise CredentialProtectionError("O valor protegido da credencial é inválido.") from exc

    source, _source_buffer = _blob(encoded)
    target = _DataBlob()
    crypt_unprotect = ctypes.windll.crypt32.CryptUnprotectData
    crypt_unprotect.argtypes = (
        ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)
    )
    crypt_unprotect.restype = wintypes.BOOL
    if not crypt_unprotect(
        ctypes.byref(source), None, None, None, None, _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(target)
    ):
        code = ctypes.get_last_error()
        raise CredentialProtectionError(
            "Não foi possível recuperar a credencial protegida "
            f"(Windows error {code})."
        )
    try:
        return _copy_and_free(target).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialProtectionError("A credencial protegida não contém texto UTF-8 válido.") from exc


_URL_WITH_CREDENTIALS = re.compile(r"(?i)\b(?:rtsp|rtsps|http|https)://[^\s/@:]+:[^\s/@]+@[^\s\"'<>]+")
_RTSP_URL = re.compile(r"(?i)\brtsps?://[^\s\"'<>]+")
_AUTHORIZATION = re.compile(r"(?im)^(\s*authorization\s*:\s*).*$")
_AUTH_SCHEME = re.compile(r"(?i)\b(?:basic|digest)\s+[A-Za-z0-9+/=._:-]+")
_SENSITIVE_PARAMETER = re.compile(
    r"(?i)\b(user(?:name)?|password|passwd|pwd|token|api[_-]?key|secret|PassWord|UserName)"
    r"(\s*[=:]\s*)([^&\s,;\"'<>]+)"
)
_HOST_PORT = re.compile(
    r"(?i)\b(?:localhost|(?:\d{1,3}\.){3}\d{1,3}|[a-z0-9-]+(?:\.[a-z0-9-]+)+):\d{1,5}\b"
)
_IPV4 = re.compile(r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])")


def sanitize_message(message: object) -> str:
    """Remove segredos e detalhes de infraestrutura de mensagens destinadas ao usuário."""
    text = str(message)
    text = _AUTHORIZATION.sub(r"\1[REDACTED]", text)
    text = _URL_WITH_CREDENTIALS.sub("[REDACTED_URL]", text)
    text = _RTSP_URL.sub("[REDACTED_URL]", text)
    text = _AUTH_SCHEME.sub("[REDACTED_AUTH]", text)
    text = _SENSITIVE_PARAMETER.sub(r"\1\2[REDACTED]", text)
    text = _HOST_PORT.sub("[REDACTED_ENDPOINT]", text)
    return _IPV4.sub("[REDACTED_IP]", text)
