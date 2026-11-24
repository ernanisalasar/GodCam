"""godcam — Monitor de câmeras XMEye/ONVIF (ponto de entrada)."""
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from godcam.config import CameraStore
from godcam.core.security import CredentialProtectionError, sanitize_message
from godcam.ui.theme import apply_dark


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GodCam")
    apply_dark(app)

    try:
        # Importado aqui para mostrar uma mensagem amigável se o VLC não existir.
        from godcam.ui.main_window import MainWindow
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(
            None, "godcam",
            f"Falha ao iniciar:\n\n{sanitize_message(exc)}\n\n"
            "Verifique se o VLC (64 bits) está instalado e se rodou "
            "'pip install -r requirements.txt'.",
        )
        return 1

    store = CameraStore()
    try:
        store.load()
    except (CredentialProtectionError, OSError, ValueError) as exc:
        QMessageBox.critical(
            None,
            "godcam",
            "Não foi possível carregar ou proteger cameras.json. "
            f"A configuração existente foi preservada. Detalhe: {sanitize_message(exc)}",
        )
        return 1
    if store.credential_errors:
        QMessageBox.warning(
            None,
            "godcam",
            "Uma ou mais credenciais protegidas não puderam ser recuperadas neste usuário Windows. "
            "Edite a câmera e informe novamente a senha.",
        )
    window = MainWindow(store)
    app.setWindowIcon(window.windowIcon())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
