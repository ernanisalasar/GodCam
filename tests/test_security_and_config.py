"""Tests with synthetic credentials only; no user AppData is accessed."""
from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

from godcam.config import CONFIG_FORMAT_VERSION, CameraConfig, CameraStore
from godcam.core.security import CredentialProtectionError, protect_secret, sanitize_message, unprotect_secret


def fake_protect(value: str) -> str:
    return "test:" + base64.b64encode(value.encode("utf-8")).decode("ascii")


def fake_unprotect(value: str) -> str:
    if value == "BROKEN":
        raise CredentialProtectionError("synthetic failure")
    if not value.startswith("test:"):
        raise CredentialProtectionError("invalid synthetic protected value")
    return base64.b64decode(value[5:].encode("ascii")).decode("utf-8")


class CameraStoreSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "cameras.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def store(self, **kwargs) -> CameraStore:
        return CameraStore(self.path, protect_password=fake_protect, unprotect_password=fake_unprotect, **kwargs)

    def test_new_installation_has_no_preconfigured_cameras(self) -> None:
        store = self.store()
        store.load()
        self.assertEqual(store.cameras, [])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["version"], CONFIG_FORMAT_VERSION)

    def test_legacy_plaintext_migrates_to_versioned_protected_json(self) -> None:
        secret = "ficticia-ç-🔒-!"
        self.path.write_text(json.dumps([{"id": "one", "name": "Teste", "password": secret}]), encoding="utf-8")
        store = self.store()
        store.load()
        raw = self.path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        self.assertEqual(payload["version"], CONFIG_FORMAT_VERSION)
        self.assertNotIn("password", payload["cameras"][0])
        self.assertNotIn(secret, raw)
        self.assertEqual(store.cameras[0].password, secret)
        reloaded = self.store()
        reloaded.load()
        self.assertEqual(reloaded.cameras[0].password, secret)

    def test_empty_password_and_multiple_cameras_round_trip(self) -> None:
        store = self.store()
        store.cameras = [
            CameraConfig.new(name="Sem senha", host_local="192.0.2.10", password=""),
            CameraConfig.new(name="Unicode", host_local="198.51.100.10", password="áéíõü-123!"),
        ]
        store.save()
        reloaded = self.store()
        reloaded.load()
        self.assertEqual([camera.password for camera in reloaded.cameras], ["", "áéíõü-123!"])

    def test_upsert_preserves_protected_credential_after_edit(self) -> None:
        store = self.store()
        store.cameras = [CameraConfig.new(name="Antes", host_local="192.0.2.10", password="synthetic-secret")]
        store.save()
        store.load()
        edited = store.cameras[0]
        edited.name = "Depois"
        store.upsert(edited)
        reloaded = self.store()
        reloaded.load()
        self.assertEqual(reloaded.cameras[0].name, "Depois")
        self.assertEqual(reloaded.cameras[0].password, "synthetic-secret")

    def test_versioned_payload_with_plaintext_is_migrated(self) -> None:
        secret = "synthetic-secret"
        self.path.write_text(
            json.dumps({"version": CONFIG_FORMAT_VERSION, "cameras": [{"id": "one", "name": "Teste", "password": secret}]}),
            encoding="utf-8",
        )
        store = self.store()
        store.load()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("password", payload["cameras"][0])
        self.assertEqual(store.cameras[0].password, secret)

    def test_encryption_failure_keeps_legacy_file_unchanged(self) -> None:
        original = json.dumps([{"id": "one", "name": "Teste", "password": "synthetic-secret"}])
        self.path.write_text(original, encoding="utf-8")
        store = CameraStore(
            self.path,
            protect_password=lambda _: (_ for _ in ()).throw(CredentialProtectionError("synthetic failure")),
            unprotect_password=fake_unprotect,
        )
        with self.assertRaises(CredentialProtectionError):
            store.load()
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_unprotect_failure_preserves_protected_value(self) -> None:
        self.path.write_text(
            json.dumps({"version": CONFIG_FORMAT_VERSION, "cameras": [{"id": "one", "name": "Teste", "password_protected": "BROKEN"}]}),
            encoding="utf-8",
        )
        store = self.store()
        store.load()
        self.assertEqual(store.cameras[0].password, "")
        self.assertTrue(store.cameras[0].credential_error)
        store.save()
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["cameras"][0]["password_protected"], "BROKEN")

    def test_atomic_write_failure_keeps_previous_file(self) -> None:
        store = self.store()
        store.cameras = [CameraConfig.new(name="Teste", host_local="203.0.113.10", password="synthetic-secret")]
        store.save()
        original = self.path.read_text(encoding="utf-8")
        store.cameras[0].name = "Alterada"
        store._atomic_writer = lambda *_: (_ for _ in ()).throw(OSError("synthetic write failure"))
        with self.assertRaises(OSError):
            store.save()
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_password_is_not_exposed_by_repr(self) -> None:
        self.assertNotIn("synthetic-secret", repr(CameraConfig.new(name="Teste", password="synthetic-secret")))


class SecuritySanitizationTests(unittest.TestCase):
    def test_sanitizes_credentials_urls_authorization_and_network(self) -> None:
        message = (
            "RTSP rtsp://user:synthetic-secret@192.0.2.10:554/path "
            "password=synthetic-secret UserName=user Authorization: Basic abcdef "
            "connection to camera.example.test:8899 from 203.0.113.10 failed"
        )
        sanitized = sanitize_message(message)
        for value in ("synthetic-secret", "192.0.2.10", "203.0.113.10", "camera.example.test:8899", "abcdef"):
            self.assertNotIn(value, sanitized)
        self.assertIn("failed", sanitized)


@unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
class WindowsDpapiTests(unittest.TestCase):
    def test_dpapi_round_trip_unicode_and_empty_values(self) -> None:
        for secret in ("", "ficticia-ç-🔒-!" * 20):
            protected = protect_secret(secret)
            if secret:
                self.assertNotIn(secret, protected)
            self.assertEqual(unprotect_secret(protected), secret)


if __name__ == "__main__":
    unittest.main()
