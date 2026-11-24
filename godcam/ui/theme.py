"""Tema escuro (Fusion + QSS)."""
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

BG, PANEL, BORDER, TEXT, MUTED = "#0f1115", "#171a20", "#262b33", "#e6e8eb", "#8b93a1"
ACCENT, DANGER = "#3b82f6", "#ef4444"

QSS = f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog, QWidget#root {{ background: {BG}; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {PANEL}; padding: 6px 10px; border-bottom: 1px solid {BORDER}; }}
QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
             margin-top: 10px; padding: 5px 4px 4px 4px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {MUTED}; }}
QListWidget, QLineEdit, QSpinBox, QComboBox {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px; }}
QListWidget::item {{ padding: 5px 4px; border-radius: 5px; }}
QListWidget::item:selected {{ background: {ACCENT}; }}
QPushButton, QToolButton {{ background: #20242c; border: 1px solid {BORDER};
                           border-radius: 5px; padding: 4px 6px; }}
QPushButton:hover, QToolButton:hover {{ background: #2a2f39; }}
QPushButton:pressed, QToolButton:pressed {{ background: {ACCENT}; }}
QPushButton:disabled, QToolButton:disabled {{ color: #555c68; }}
QPushButton:checked {{ background: {DANGER}; border-color: {DANGER}; }}
QPushButton#talk:pressed {{ background: #16a34a; border-color: #16a34a; }}
QToolButton.ptz {{ font-size: 14px; min-width: 30px; min-height: 30px; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; }}
QToolBar {{ background: {PANEL}; border: none; spacing: 6px; padding: 4px; }}
QFrame#tile {{ background: {PANEL}; border: 2px solid {BORDER}; border-radius: 8px; }}
QFrame#tile[active="true"] {{ border-color: {ACCENT}; }}
QWidget#tileHeader {{ background-color: rgba(15, 17, 21, 210); border-bottom: 1px solid {BORDER}; }}
QLabel#tileName {{ font-weight: 600; }}
QLabel#tileStatus {{ color: {MUTED}; }}
QLabel#tileAddress {{ color: {MUTED}; font-size: 10px; }}
QLabel#tileBadge {{ color: {DANGER}; font-weight: 700; }}
QLabel#placeholder {{ color: {MUTED}; font-size: 15px; }}
QWidget#sidePanel {{ background: {PANEL}; }}
QLabel#sectionTitle {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QFrame#emptySlot {{ background: {PANEL}; border: 1px dashed {BORDER}; border-radius: 6px; }}
QLabel#emptySlotText {{ color: {MUTED}; font-size: 11px; }}
QWidget#videoGrid {{ background: {BG}; }}
QScrollArea#controlsScroll {{ background: {PANEL}; }}
"""


def apply_dark(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: BG, QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: PANEL, QPalette.ColorRole.AlternateBase: BG,
        QPalette.ColorRole.Text: TEXT, QPalette.ColorRole.Button: PANEL,
        QPalette.ColorRole.ButtonText: TEXT, QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: "#ffffff", QPalette.ColorRole.ToolTipBase: PANEL,
        QPalette.ColorRole.ToolTipText: TEXT,
    }.items():
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
