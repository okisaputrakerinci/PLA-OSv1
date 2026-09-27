#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PLA-OSv1 – Desktop GUI (clean & compact)
- Fokus ke 2 aksi: Process (single/batch) & Evaluate.
- Tombol cepat: "Open Summary / Result" dan "Open Output Folder".
- Tema gelap/terang, scrollable forms, fully resizable.
- Kompatibel dengan leaf_area_research.py (schema_version >= 1.8).

Requires:
    pip install PySide6 opencv-python numpy
"""

import os
import sys
import json
import traceback
from dataclasses import dataclass, asdict
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

APP_TITLE = "PLA-OSv1"
APP_VERSION = "1.0.0"
COPYRIGHT_TEXT = "© 2025 Oki Saputra – OS AI Corp. All rights reserved."

# ---- Import pipeline ----
try:
    from leaf_area_research import (
        process_single_image,
        process_folder,
        evaluate_results,
    )
    _IMPORT_ERROR = None
except Exception as e:
    process_single_image = None
    process_folder = None
    evaluate_results = None
    _IMPORT_ERROR = e

SETTINGS_DIR = os.path.join("leaf-area")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, ".leaf_area_gui_settings.json")


# ---------- Branding & Icons ----------
import sys

def find_logo_path() -> Optional[str]:
    """
    Cari logo PNG saja agar tajam (hindari ico/jpg). Urutan prioritas:
    ./logo.png, ./logo_os_ai_corp.png, ./pla.png, lalu versi di folder leaf-area/ dan folder instalasi.
    """
    # Cek direktori tempat aplikasi dijalankan
    candidates = [
        os.path.join(".", "logo.png"),
        os.path.join(".", "logo_os_ai_corp.png"),
        os.path.join(".", "pla.png"),
        os.path.join("leaf-area", "logo.png"),
        os.path.join("leaf-area", "logo_os_ai_corp.png"),
        os.path.join("leaf-area", "pla.png"),
    ]
    
    # Jika aplikasi sudah diinstal, coba cari di folder instalasi
    if getattr(sys, 'frozen', False):  # Jika aplikasi dijalankan sebagai exe (pada instalasi)
        app_path = os.path.dirname(sys.executable)  # Direktori instalasi
        candidates.extend([
            os.path.join(app_path, "logo.png"),
            os.path.join(app_path, "logo_os_ai_corp.png"),
            os.path.join(app_path, "pla.png")
        ])
    
    for p in candidates:
        if os.path.exists(p) and p.lower().endswith(".png"):
            return p
    return None

def build_app_icon(path: Optional[str]) -> Optional[QtGui.QIcon]:
    """
    Bangun QIcon dari PNG atau ICO (multi-size). Kembali None kalau gagal.
    """
    if not path or not os.path.exists(path) or not (path.lower().endswith(".png") or path.lower().endswith(".ico")):
        return None
    try:
        pm = QtGui.QPixmap(path)
        if pm.isNull():
            return None
        icon = QtGui.QIcon()
        for s in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256):
            icon.addPixmap(pm.scaled(s, s, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        return icon
    except Exception:
        return None

def fallback_icon() -> QtGui.QIcon:
    """
    Fallback vektor sederhana dengan tulisan 'PLA' agar tetap tajam.
    """
    pm = QtGui.QPixmap(256, 256)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setBrush(QtGui.QBrush(QtGui.QColor(28, 160, 90)))
    p.setPen(QtCore.Qt.NoPen)
    p.drawRoundedRect(0, 0, 256, 256, 48, 48)
    font = QtGui.QFont()
    font.setPointSize(84)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))
    p.drawText(pm.rect(), QtCore.Qt.AlignCenter, "PLA")
    p.end()
    icon = QtGui.QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256):
        icon.addPixmap(pm.scaled(s, s, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
    return icon


def app_icon() -> QtGui.QIcon:
    ic = build_app_icon(find_logo_path())
    return ic if ic and not ic.isNull() else fallback_icon()


# ---------- Themes ----------
DARK_QSS = """
* { font-family: 'Segoe UI','Inter',Arial; }
QWidget { background: #111315; color: #E8EAF0; }
QMenuBar { background: #0E1012; border: none; }
QMenuBar::item { padding: 6px 10px; }
QMenuBar::item:selected { background: #1B1F24; }
QMenu { background: #15181B; border: 1px solid #2A2F36; }
QMenu::item { padding: 6px 18px; }
QMenu::item:selected { background: #25303A; }
QStatusBar { background: #0E1012; color: #AAB2BF; }
QToolTip { background: #1C2128; color: #E8EAF0; border: 1px solid #30363D; }
QLabel#BannerTitle { color: #E8EAF0; font-weight: 600; font-size: 18px; }
QLabel#Copyright { color: #9AA4B2; }
QGroupBox { border: 1px solid #2A2F36; margin-top: 16px; border-radius: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0px 4px; }
QLineEdit, QPlainTextEdit, QComboBox {
  background: #0E1012; border: 1px solid #2A2F36; padding: 6px 8px; border-radius: 8px; color: #E8EAF0;
}
QSpinBox, QDoubleSpinBox {
  background: #0E1012; border: 1px solid #2A2F36; padding: 2px 6px; border-radius: 8px; color: #E8EAF0;
}
QPushButton { background: #1F6FEB; color: white; border: none; padding: 8px 14px; border-radius: 8px; }
QPushButton:hover { background: #2B78F6; }
QPushButton:disabled { background: #2A2F36; color: #808A99; }
QProgressBar { border: 1px solid #2A2F36; text-align: center; height: 20px; border-radius: 10px; }
QProgressBar::chunk { background-color: #1F6FEB; border-radius: 10px; }
"""

LIGHT_QSS = """
* { font-family: 'Segoe UI','Inter',Arial; }
QWidget { background: #F7F9FC; color: #111315; }
QMenuBar { background: #FFFFFF; border: none; }
QMenuBar::item { padding: 6px 10px; }
QMenuBar::item:selected { background: #E8EEF8; }
QMenu { background: #FFFFFF; border: 1px solid #D9DFEA; }
QMenu::item { padding: 6px 18px; }
QMenu::item:selected { background: #E8EEF8; }
QStatusBar { background: #FFFFFF; color: #4B5563; }
QToolTip { background: #F0F4FA; color: #111315; border: 1px solid #D9DFEA; }
QLabel#BannerTitle { color: #0B1320; font-weight: 600; font-size: 18px; }
QLabel#Copyright { color: #6B7280; }
QGroupBox { border: 1px solid #D9DFEA; margin-top: 16px; border-radius: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0px 4px; }
QLineEdit, QPlainTextEdit, QComboBox {
  background: #FFFFFF; border: 1px solid #D9DFEA; padding: 6px 8px; border-radius: 8px; color: #111315;
}
QSpinBox, QDoubleSpinBox {
  background: #FFFFFF; border: 1px solid #D9DFEA; padding: 2px 6px; border-radius: 8px; color: #111315;
}
QPushButton { background: #1F6FEB; color: white; border: none; padding: 8px 14px; border-radius: 8px; }
QPushButton:hover { background: #2B78F6; }
QPushButton:disabled { background: #E5E7EB; color: #9CA3AF; }
QProgressBar { border: 1px solid #D9DFEA; text-align: center; height: 20px; border-radius: 10px; }
QProgressBar::chunk { background-color: #1F6FEB; border-radius: 10px; }
"""


# --------------------------- Settings Model ---------------------------
@dataclass
class ProcessSettings:
    image: str = ""
    data_folder: str = ""
    resize_long: Optional[int] = None
    save_prefix: str = ""
    out_folder: str = "output_batch"
    debug: bool = False           # extra debug masks (coin)
    save_steps: bool = True       # save Ainv/thresh/largest/filled
    coin_mm: float = 25.0
    manual_ppm: Optional[float] = None
    coin_is_dark: bool = True
    min_leaf_area_mm2: float = 300.0
    white_balance: bool = False
    gamma: float = 1.0
    clahe: bool = False
    gt_area_csv: str = ""
    camera_model: str = "unknown"
    lighting_condition: str = "unknown"
    background_color: str = "unknown"
    summary_out: str = ""
    seed: int = 42
    threads: int = 0
    log_hw: bool = False


@dataclass
class EvalSettings:
    results_folder: str = "output_batch"
    gt_area_csv: str = ""
    gt_mask_dir: str = ""
    summary_out: str = ""


@dataclass
class UiSettings:
    theme: str = "dark"           # "dark" or "light"
    start_minimized: bool = False


# --------------------------- Worker Threads ---------------------------
class ProcessWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    done = QtCore.Signal(dict)           # single-image meta
    batch_done = QtCore.Signal(str)      # summary.csv path
    progress = QtCore.Signal(int)

    def __init__(self, s: ProcessSettings, parent=None):
        super().__init__(parent)
        self.s = s

    def run(self):
        try:
            if self.s.image:
                self.progress.emit(5)
                meta = process_single_image(
                    img_path=self.s.image,
                    save_prefix=(self.s.save_prefix or os.path.join("output", os.path.splitext(os.path.basename(self.s.image))[0])),
                    coin_mm=self.s.coin_mm,
                    manual_ppm=self.s.manual_ppm,
                    min_leaf_area_mm2=self.s.min_leaf_area_mm2,
                    white_balance=self.s.white_balance,
                    gamma=self.s.gamma,
                    clahe=self.s.clahe,
                    debug=self.s.debug,
                    coin_is_dark=self.s.coin_is_dark,
                    resize_long=self.s.resize_long,
                    run_env={"threads": self.s.threads, "seed": self.s.seed} if self.s.log_hw else None,
                    save_steps=self.s.save_steps,
                )
                self.progress.emit(100)
                self.log.emit(f"[OK] {self.s.image} -> {meta['area_cm2']:.2f} cm²")
                self.done.emit(meta)
            elif self.s.data_folder:
                self.progress.emit(1)
                path = process_folder(
                    data_folder=self.s.data_folder,
                    out_folder=(self.s.out_folder or "output_batch"),
                    coin_mm=self.s.coin_mm,
                    manual_ppm=self.s.manual_ppm,
                    min_leaf_area_mm2=self.s.min_leaf_area_mm2,
                    white_balance=self.s.white_balance,
                    gamma=self.s.gamma,
                    clahe=self.s.clahe,
                    debug=self.s.debug,
                    gt_area_csv=(self.s.gt_area_csv or None),
                    camera_model=self.s.camera_model,
                    lighting_condition=self.s.lighting_condition,
                    background_color=self.s.background_color,
                    summary_out=(self.s.summary_out or None),
                    coin_is_dark=self.s.coin_is_dark,
                    resize_long=self.s.resize_long,
                    run_env={"threads": self.s.threads, "seed": self.s.seed} if self.s.log_hw else None,
                    save_steps=self.s.save_steps,
                )
                self.progress.emit(100)
                self.log.emit(f"Summary saved to {path}")
                self.batch_done.emit(path)
            else:
                self.log.emit("[ERROR] No input selected: choose image or folder.")
        except Exception:
            self.log.emit("[ERROR] " + traceback.format_exc())


class EvalWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    done = QtCore.Signal(str)   # eval summary path

    def __init__(self, s: EvalSettings, parent=None):
        super().__init__(parent)
        self.s = s

    def run(self):
        try:
            out = evaluate_results(
                results_folder=self.s.results_folder,
                gt_area_csv=(self.s.gt_area_csv or None),
                gt_mask_dir=(self.s.gt_mask_dir or None),
                summary_out=(self.s.summary_out or None),
            )
            self.log.emit(f"Evaluation summary saved to {out}")
            self.done.emit(out)
        except Exception:
            self.log.emit("[ERROR] " + traceback.format_exc())


# --------------------------- Small UI helpers ---------------------------
class LabeledEdit(QtWidgets.QWidget):
    """Compact line edit + optional Browse… button."""
    def __init__(self, label: str, browse_text: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.edit = QtWidgets.QLineEdit()
        self.btn = None

        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        lab = QtWidgets.QLabel(label); lab.setMinimumWidth(150)
        h.addWidget(lab)
        h.addWidget(self.edit, 1)
        if browse_text:
            self.btn = QtWidgets.QPushButton(browse_text)
            h.addWidget(self.btn)


# --------------------------- Main Window ---------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, ui_settings: UiSettings):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 720)
        self.setMinimumSize(900, 560)

        self.setWindowIcon(app_icon())

        # state
        self.process_settings = ProcessSettings()
        self.eval_settings = EvalSettings()
        self.ui_settings = ui_settings
        self._last_process_settings: Optional[ProcessSettings] = None
        self._tray_tip_shown = False
        self._last_summary_path: Optional[str] = None
        self._load_settings()

        # menu + header + central
        self._init_menu()
        self._build_header()
        self._build_central()

        self._init_tray()

        if _IMPORT_ERROR is not None:
            QtWidgets.QMessageBox.critical(
                self, "Import Error",
                "Tidak bisa import leaf_area_research.py\n\n%s" % _IMPORT_ERROR
            )

    # ---- menu
    def _init_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("&File")
        act_quit = QtGui.QAction("Exit", self, triggered=QtWidgets.QApplication.instance().quit)
        act_quit.setShortcut("Ctrl+Q"); m_file.addAction(act_quit)

        m_view = mb.addMenu("&View")
        self.act_theme_dark = QtGui.QAction("Dark Theme", self, checkable=True, checked=(self.ui_settings.theme == "dark"))
        self.act_theme_light = QtGui.QAction("Light Theme", self, checkable=True, checked=(self.ui_settings.theme == "light"))
        grp = QtGui.QActionGroup(self); grp.setExclusive(True); grp.addAction(self.act_theme_dark); grp.addAction(self.act_theme_light)
        self.act_theme_dark.triggered.connect(lambda: self._switch_theme("dark"))
        self.act_theme_light.triggered.connect(lambda: self._switch_theme("light"))
        m_view.addAction(self.act_theme_dark); m_view.addAction(self.act_theme_light)
        m_view.addSeparator()
        self.act_start_min = QtGui.QAction("Start minimized to tray", self, checkable=True, checked=self.ui_settings.start_minimized)
        self.act_start_min.triggered.connect(self._toggle_start_min)
        m_view.addAction(self.act_start_min)

        m_help = mb.addMenu("&Help")
        act_about = QtGui.QAction("About " + APP_TITLE, self, triggered=self._show_about)
        m_help.addAction(act_about)

    def _switch_theme(self, theme: str):
        self.ui_settings.theme = theme
        self._apply_theme()
        self._save_settings()

    def _toggle_start_min(self):
        self.ui_settings.start_minimized = self.act_start_min.isChecked()
        self._save_settings()

    def _apply_theme(self):
        app = QtWidgets.QApplication.instance()
        app.setStyleSheet(DARK_QSS if self.ui_settings.theme == "dark" else LIGHT_QSS)

    def _show_about(self):
        lp = find_logo_path()
        pm = QtGui.QPixmap(lp or "")
        icon_html = f'<img src="{lp}" height="64">' if (lp and not pm.isNull()) else ""
        text = f"""
        <div style="min-width:380px;">
          <div style="display:flex;gap:12px;align-items:center;margin-bottom:8px;">
            {icon_html}
            <div>
              <div style="font-size:16px;font-weight:700;">{APP_TITLE}</div>
              <div style="color:#9AA4B2;">Version {APP_VERSION}</div>
            </div>
          </div>
          <div style="margin:8px 0 16px;color:#9AA4B2;">
             PLA-OSv1 is a research tool designed to support plant morphology studies, focusing on leaf area estimation, perimeter, and other shape metrics from digital images.
          </div>
          <div style="font-size:12px;color:#9AA4B2;">{COPYRIGHT_TEXT}</div>
        </div>
        """
        QtWidgets.QMessageBox.information(self, f"About {APP_TITLE}", text)

    # ---- header
    def _build_header(self):
        header = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(header); h.setContentsMargins(12, 12, 12, 8)

        logo_label = QtWidgets.QLabel()
        lp = find_logo_path()
        if lp and os.path.exists(lp):
            logo_label.setPixmap(QtGui.QPixmap(lp).scaledToHeight(44, QtCore.Qt.SmoothTransformation))
        else:
            pm = QtGui.QPixmap(44, 44); pm.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            p.setBrush(QtGui.QBrush(QtGui.QColor(28, 160, 90))); p.setPen(QtCore.Qt.NoPen)
            p.drawRoundedRect(0, 0, 44, 44, 10, 10)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255))); f = QtGui.QFont(); f.setBold(True); f.setPointSize(16); p.setFont(f)
            p.drawText(pm.rect(), QtCore.Qt.AlignCenter, "PLA"); p.end()
            logo_label.setPixmap(pm)

        title = QtWidgets.QLabel(APP_TITLE); title.setObjectName("BannerTitle")

        box = QtWidgets.QHBoxLayout(); box.addWidget(logo_label); box.addSpacing(10); box.addWidget(title)
        brand = QtWidgets.QWidget(); brand.setLayout(box)

        container = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(container); v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(header)
        self._central_stack = v
        self.setCentralWidget(container)

        h.addWidget(brand); h.addStretch(1)

    # ---- central content (tabs with scrollable forms)
    def _build_central(self):
        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)
        self._central_stack.addWidget(tabs)
        self.tabs = tabs

        self._init_process_tab()
        self._init_eval_tab()
        self._init_statusbar()

    def _wrap_scroll(self, widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll

    # ---- Process tab
    def _init_process_tab(self):
        root = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(root); lay.setContentsMargins(14, 8, 14, 14); lay.setSpacing(12)

        # Group: Input
        g_in = QtWidgets.QGroupBox("Input")
        f_in = QtWidgets.QGridLayout(g_in); f_in.setHorizontalSpacing(10); f_in.setVerticalSpacing(8)
        self.ed_image = LabeledEdit("Single image:", "Browse…"); self.ed_folder = LabeledEdit("Folder (batch):", "Browse…")
        self.sp_resize = QtWidgets.QSpinBox(); self.sp_resize.setRange(0, 99999); self.sp_resize.setSuffix(" px (0 = off)"); self.sp_resize.setValue(0)
        f_in.addWidget(self.ed_image, 0, 0, 1, 2)
        f_in.addWidget(self.ed_folder, 1, 0, 1, 2)
        f_in.addWidget(QtWidgets.QLabel("Resize (longest):"), 2, 0); f_in.addWidget(self.sp_resize, 2, 1)

        # Group: Output
        g_out = QtWidgets.QGroupBox("Output")
        f_out = QtWidgets.QGridLayout(g_out)
        self.ed_prefix = LabeledEdit("Save prefix:")
        self.ed_outdir = LabeledEdit("Out folder:", "Browse…")
        self.cb_debug = QtWidgets.QCheckBox("Save debug images (coin masks)")
        self.cb_steps = QtWidgets.QCheckBox("Save step images (Ainv/thresh/largest/filled)"); self.cb_steps.setChecked(True)
        f_out.addWidget(self.ed_prefix, 0, 0, 1, 2)
        f_out.addWidget(self.ed_outdir, 1, 0, 1, 2)
        f_out.addWidget(self.cb_debug, 2, 0)
        f_out.addWidget(self.cb_steps, 2, 1)

        # Group: Calibration
        g_cal = QtWidgets.QGroupBox("Calibration")
        f_cal = QtWidgets.QGridLayout(g_cal)
        self.ds_coin = QtWidgets.QDoubleSpinBox(); self.ds_coin.setRange(0.1, 1000.0); self.ds_coin.setSuffix(" mm"); self.ds_coin.setValue(25.0)
        self.ds_ppm = QtWidgets.QDoubleSpinBox(); self.ds_ppm.setRange(0.0, 1e6); self.ds_ppm.setDecimals(4); self.ds_ppm.setSuffix(" px/mm (0 = auto)"); self.ds_ppm.setValue(0.0)
        self.cb_dark = QtWidgets.QCheckBox("Dark coin/marker")
        self.cb_dark.setChecked(True)
        f_cal.addWidget(QtWidgets.QLabel("Coin diameter:"), 0, 0); f_cal.addWidget(self.ds_coin, 0, 1)
        f_cal.addWidget(QtWidgets.QLabel("Manual px/mm:"), 1, 0); f_cal.addWidget(self.ds_ppm, 1, 1)
        f_cal.addWidget(self.cb_dark, 2, 0)

        # Group: Segmentation & QC
        g_seg = QtWidgets.QGroupBox("Segmentation & QC")
        f_seg = QtWidgets.QGridLayout(g_seg)
        self.ds_min = QtWidgets.QDoubleSpinBox(); self.ds_min.setRange(0.0, 1e9); self.ds_min.setSuffix(" mm²"); self.ds_min.setValue(300.0)
        self.cb_wb = QtWidgets.QCheckBox("Gray-world WB")
        self.ds_gamma = QtWidgets.QDoubleSpinBox(); self.ds_gamma.setRange(0.5, 2.0); self.ds_gamma.setSingleStep(0.01); self.ds_gamma.setValue(1.0)
        self.cb_clahe = QtWidgets.QCheckBox("CLAHE (LAB L)")
        f_seg.addWidget(QtWidgets.QLabel("Min leaf area:"), 0, 0); f_seg.addWidget(self.ds_min, 0, 1)
        f_seg.addWidget(QtWidgets.QLabel("Gamma:"), 1, 0); f_seg.addWidget(self.ds_gamma, 1, 1)
        f_seg.addWidget(self.cb_wb, 2, 0); f_seg.addWidget(self.cb_clahe, 2, 1)

        # Group: Metadata
        g_meta = QtWidgets.QGroupBox("Metadata")
        f_meta = QtWidgets.QGridLayout(g_meta)
        self.ed_gtcsv = LabeledEdit("GT area CSV:", "Browse…")
        self.ed_camera = QtWidgets.QLineEdit("unknown")
        self.ed_light = QtWidgets.QLineEdit("unknown")
        self.ed_bg = QtWidgets.QLineEdit("unknown")
        self.ed_summary = LabeledEdit("Custom summary.csv:", "Browse…")
        f_meta.addWidget(self.ed_gtcsv, 0, 0, 1, 2)
        f_meta.addWidget(QtWidgets.QLabel("Camera:"), 1, 0); f_meta.addWidget(self.ed_camera, 1, 1)
        f_meta.addWidget(QtWidgets.QLabel("Lighting:"), 2, 0); f_meta.addWidget(self.ed_light, 2, 1)
        f_meta.addWidget(QtWidgets.QLabel("Background:"), 3, 0); f_meta.addWidget(self.ed_bg, 3, 1)
        f_meta.addWidget(self.ed_summary, 4, 0, 1, 2)

        # Group: System
        g_sys = QtWidgets.QGroupBox("System")
        f_sys = QtWidgets.QGridLayout(g_sys)
        self.sp_seed = QtWidgets.QSpinBox(); self.sp_seed.setRange(0, 1000000); self.sp_seed.setValue(42)
        self.sp_threads = QtWidgets.QSpinBox(); self.sp_threads.setRange(0, 64); self.sp_threads.setValue(0)
        self.cb_loghw = QtWidgets.QCheckBox("Log HW/versions")
        f_sys.addWidget(QtWidgets.QLabel("Seed:"), 0, 0); f_sys.addWidget(self.sp_seed, 0, 1)
        f_sys.addWidget(QtWidgets.QLabel("Threads:"), 1, 0); f_sys.addWidget(self.sp_threads, 1, 1)
        f_sys.addWidget(self.cb_loghw, 2, 0)

        # Actions
        g_act = QtWidgets.QGroupBox("Actions & Logs")
        f_act = QtWidgets.QGridLayout(g_act)
        self.btn_run = QtWidgets.QPushButton("Run Process")
        self.progress = QtWidgets.QProgressBar(); self.progress.setRange(0, 100)
        self.btn_open_summary = QtWidgets.QPushButton("Open Summary / Result"); self.btn_open_summary.setEnabled(False)
        self.btn_open_outdir = QtWidgets.QPushButton("Open Output Folder")
        self.txt_log = QtWidgets.QPlainTextEdit(); self.txt_log.setReadOnly(True); self.txt_log.setMinimumHeight(140)
        f_act.addWidget(self.btn_run, 0, 0, 1, 1)
        f_act.addWidget(self.progress, 0, 1, 1, 1)
        f_act.addWidget(self.btn_open_summary, 0, 2, 1, 1)
        f_act.addWidget(self.btn_open_outdir, 0, 3, 1, 1)
        f_act.addWidget(self.txt_log, 1, 0, 1, 4)

        # Assemble
        for g in (g_in, g_out, g_cal, g_seg, g_meta, g_sys, g_act):
            lay.addWidget(g)
        lay.addStretch(1)

        # wire browse
        self.ed_image.btn.clicked.connect(self._pick_image)
        self.ed_folder.btn.clicked.connect(self._pick_folder)
        self.ed_outdir.btn.clicked.connect(self._pick_outdir)
        self.ed_gtcsv.btn.clicked.connect(self._pick_gtcsv)
        self.ed_summary.btn.clicked.connect(self._pick_summary)

        # actions
        self.btn_run.clicked.connect(self._on_run_process)
        self.btn_open_summary.clicked.connect(self._open_last_summary)
        self.btn_open_outdir.clicked.connect(self._open_out_folder)

        # UX: enable/disable field sesuai mode
        self.ed_image.edit.textChanged.connect(self._toggle_single_batch_fields)
        self.ed_folder.edit.textChanged.connect(self._toggle_single_batch_fields)
        self._toggle_single_batch_fields()

        # load settings to UI
        self._apply_process_settings_to_ui()

        # add to tabs (wrapped in scroll area)
        self.tabs.addTab(self._wrap_scroll(root), "Process")

    # ---- Evaluate tab
    def _init_eval_tab(self):
        root = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(root); lay.setContentsMargins(14, 8, 14, 14); lay.setSpacing(12)

        g = QtWidgets.QGroupBox("Evaluate")
        f = QtWidgets.QGridLayout(g)
        self.ev_results = LabeledEdit("Results folder:", "Browse…")
        self.ev_gtcsv = LabeledEdit("GT area CSV:", "Browse…")
        self.ev_gtmask = LabeledEdit("GT mask dir:", "Browse…")
        self.ev_summary = LabeledEdit("Summary out:", "Browse…")
        self.btn_eval = QtWidgets.QPushButton("Run Evaluate")
        self.btn_open_eval = QtWidgets.QPushButton("Open Evaluate Folder")
        self.btn_open_eval.setEnabled(False)
        self.txt_eval = QtWidgets.QPlainTextEdit(); self.txt_eval.setReadOnly(True); self.txt_eval.setMinimumHeight(120)

        f.addWidget(self.ev_results, 0, 0, 1, 2)
        f.addWidget(self.ev_gtcsv, 1, 0, 1, 2)
        f.addWidget(self.ev_gtmask, 2, 0, 1, 2)
        f.addWidget(self.ev_summary, 3, 0, 1, 2)
        f.addWidget(self.btn_eval, 4, 0, 1, 1)
        f.addWidget(self.btn_open_eval, 4, 1, 1, 1)
        f.addWidget(self.txt_eval, 5, 0, 1, 2)

        lay.addWidget(g); lay.addStretch(1)

        self.ev_results.btn.clicked.connect(self._pick_results_folder)
        self.ev_gtcsv.btn.clicked.connect(self._pick_gtcsv_ev)
        self.ev_gtmask.btn.clicked.connect(self._pick_gtmask)
        self.ev_summary.btn.clicked.connect(self._pick_summary_ev)
        self.btn_eval.clicked.connect(self._on_run_evaluate)
        self._apply_eval_settings_to_ui()

        self.tabs.addTab(self._wrap_scroll(root), "Evaluate")
        self.btn_open_eval.clicked.connect(self._open_eval_folder)

    def _init_statusbar(self):
        sb = self.statusBar(); sb.showMessage("Ready")
        lbl = QtWidgets.QLabel(COPYRIGHT_TEXT); lbl.setObjectName("Copyright")
        sb.addPermanentWidget(lbl)

    # ---- File dialogs
    def _pick_image(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if p: self.ed_image.edit.setText(p)

    def _pick_folder(self):
        p = QtWidgets.QFileDialog.getExistingDirectory(self, "Select input folder")
        if p: self.ed_folder.edit.setText(p)

    def _pick_outdir(self):
        p = QtWidgets.QFileDialog.getExistingDirectory(self, "Select output folder")
        if p: self.ed_outdir.edit.setText(p)

    def _pick_gtcsv(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select GT area CSV", "", "CSV (*.csv)")
        if p: self.ed_gtcsv.edit.setText(p)

    def _pick_summary(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save summary.csv", "summary.csv", "CSV (*.csv)")
        if p: self.ed_summary.edit.setText(p)

    def _pick_results_folder(self):
        p = QtWidgets.QFileDialog.getExistingDirectory(self, "Select results folder")
        if p: self.ev_results.edit.setText(p)

    def _pick_gtcsv_ev(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select GT area CSV", "", "CSV (*.csv)")
        if p: self.ev_gtcsv.edit.setText(p)

    def _pick_gtmask(self):
        p = QtWidgets.QFileDialog.getExistingDirectory(self, "Select GT masks folder")
        if p: self.ev_gtmask.edit.setText(p)

    def _pick_summary_ev(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save evaluation summary", "evaluation_summary.csv", "CSV (*.csv)")
        if p: self.ev_summary.edit.setText(p)

    # ---- Run actions
    def _on_run_process(self):
        s = self._collect_process_settings_from_ui()
        self._last_process_settings = s
        self._save_settings()

        self.txt_log.clear(); self.progress.setValue(0)
        self.statusBar().showMessage("Processing…")
        self.btn_run.setEnabled(False)

        self.worker = ProcessWorker(s)
        self.worker.log.connect(lambda m: self.txt_log.appendPlainText(m))
        self.worker.progress.connect(self.progress.setValue)
        self.worker.done.connect(self._on_single_done)
        self.worker.batch_done.connect(self._on_batch_done)
        self.worker.finished.connect(lambda: self.btn_run.setEnabled(True))
        self.worker.finished.connect(lambda: self.statusBar().showMessage("Done"))
        self.worker.start()

    def _on_run_evaluate(self):
        s = self._collect_eval_settings_from_ui()
        self._save_settings()
        self.txt_eval.clear(); self.statusBar().showMessage("Evaluating…"); self.btn_eval.setEnabled(False)
        self.eval_worker = EvalWorker(s)
        self.eval_worker.log.connect(lambda m: self.txt_eval.appendPlainText(m))
        self.eval_worker.done.connect(self._on_eval_done)
        self.eval_worker.finished.connect(lambda: self.btn_eval.setEnabled(True))
        self.eval_worker.finished.connect(lambda: self.statusBar().showMessage("Done"))
        self.eval_worker.start()

    # ---- Callbacks
    def _on_single_done(self, meta: dict):
        out = meta.get("outputs", {})
        # buka JSON result (single)
        self._last_summary_path = out.get("result_json") if out else None
        self.btn_open_summary.setEnabled(bool(self._last_summary_path))

    def _on_batch_done(self, summary_path: str):
        self._last_summary_path = summary_path if (summary_path and os.path.exists(summary_path)) else None
        self.txt_log.appendPlainText("Batch finished. Summary: %s" % summary_path)
        self.btn_open_summary.setEnabled(bool(self._last_summary_path))

    def _on_eval_done(self, path):

        self.txt_eval.appendPlainText(f"Saved: {path}")
        self.btn_open_eval.setEnabled(True)

    def _open_last_summary(self):
        if not self._last_summary_path:
            return
        p = self._last_summary_path
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(p))

    def _open_out_folder(self):
        path = None
        if self._last_summary_path and os.path.exists(self._last_summary_path):
            path = os.path.dirname(self._last_summary_path)
        elif self.process_settings.image and self.process_settings.save_prefix:
            path = os.path.dirname(self.process_settings.save_prefix)
        elif self.process_settings.data_folder and self.process_settings.out_folder:
            path = self.process_settings.out_folder
        if not path or not os.path.exists(path):
            QtWidgets.QMessageBox.information(self, "Open Output Folder", "Belum ada output.")
            return
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    # ---- Settings sync
    def _apply_process_settings_to_ui(self):
        s = self.process_settings
        self.ed_image.edit.setText(s.image)
        self.ed_folder.edit.setText(s.data_folder)
        self.sp_resize.setValue(s.resize_long or 0)
        self.ed_prefix.edit.setText(s.save_prefix)
        self.ed_outdir.edit.setText(s.out_folder)
        self.cb_debug.setChecked(s.debug)
        self.cb_steps.setChecked(s.save_steps)
        self.ds_coin.setValue(s.coin_mm)
        self.ds_ppm.setValue(s.manual_ppm or 0.0)
        self.cb_dark.setChecked(s.coin_is_dark)
        self.ds_min.setValue(s.min_leaf_area_mm2)
        self.cb_wb.setChecked(s.white_balance)
        self.ds_gamma.setValue(s.gamma)
        self.cb_clahe.setChecked(s.clahe)
        self.ed_gtcsv.edit.setText(s.gt_area_csv)
        self.ed_camera.setText(s.camera_model)
        self.ed_light.setText(s.lighting_condition)
        self.ed_bg.setText(s.background_color)
        self.ed_summary.edit.setText(s.summary_out)
        self.sp_seed.setValue(s.seed)
        self.sp_threads.setValue(s.threads)
        self.cb_loghw.setChecked(s.log_hw)

    def _collect_process_settings_from_ui(self) -> ProcessSettings:
        s = ProcessSettings()
        s.image = self.ed_image.edit.text().strip()
        s.data_folder = self.ed_folder.edit.text().strip()
        r = self.sp_resize.value(); s.resize_long = None if r == 0 else r
        s.save_prefix = self.ed_prefix.edit.text().strip()
        s.out_folder = self.ed_outdir.edit.text().strip() or "output_batch"
        s.debug = self.cb_debug.isChecked()
        s.save_steps = self.cb_steps.isChecked()
        s.coin_mm = float(self.ds_coin.value())
        ppm = float(self.ds_ppm.value()); s.manual_ppm = None if ppm == 0.0 else ppm
        s.coin_is_dark = self.cb_dark.isChecked()
        s.min_leaf_area_mm2 = float(self.ds_min.value())
        s.white_balance = self.cb_wb.isChecked()
        s.gamma = float(self.ds_gamma.value())
        s.clahe = self.cb_clahe.isChecked()
        s.gt_area_csv = self.ed_gtcsv.edit.text().strip()
        s.camera_model = self.ed_camera.text().strip() or "unknown"
        s.lighting_condition = self.ed_light.text().strip() or "unknown"
        s.background_color = self.ed_bg.text().strip() or "unknown"
        s.summary_out = self.ed_summary.edit.text().strip()
        s.seed = int(self.sp_seed.value())
        s.threads = int(self.sp_threads.value())
        s.log_hw = self.cb_loghw.isChecked()
        self.process_settings = s
        return s

    def _apply_eval_settings_to_ui(self):
        s = self.eval_settings
        self.ev_results.edit.setText(s.results_folder)
        self.ev_gtcsv.edit.setText(s.gt_area_csv)
        self.ev_gtmask.edit.setText(s.gt_mask_dir)
        self.ev_summary.edit.setText(s.summary_out)

    def _collect_eval_settings_from_ui(self) -> EvalSettings:
        s = EvalSettings()
        s.results_folder = self.ev_results.edit.text().strip() or "output_batch"
        s.gt_area_csv = self.ev_gtcsv.edit.text().strip()
        s.gt_mask_dir = self.ev_gtmask.edit.text().strip()
        s.summary_out = self.ev_summary.edit.text().strip()
        self.eval_settings = s
        return s

    # ---- Mode toggling
    def _toggle_single_batch_fields(self):
        single = bool(self.ed_image.edit.text().strip())
        batch = bool(self.ed_folder.edit.text().strip())
        # kalau single → matikan out_folder; kalau batch → matikan save_prefix
        self.ed_outdir.edit.setEnabled(batch)
        if self.ed_outdir.btn: self.ed_outdir.btn.setEnabled(batch)
        self.ed_prefix.edit.setEnabled(single)

    # ---- Persist settings
    def _load_settings(self):
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "process" in data: self.process_settings = ProcessSettings(**data["process"])
                if "evaluate" in data: self.eval_settings = EvalSettings(**data["evaluate"])
                if "ui" in data: self.ui_settings = UiSettings(**data["ui"])
        except Exception:
            print("Warning: failed to load settings:", traceback.format_exc())

    def _save_settings(self):
        try:
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "process": asdict(self.process_settings),
                    "evaluate": asdict(self.eval_settings),
                    "ui": asdict(self.ui_settings),
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            print("Warning: failed to save settings:", traceback.format_exc())

    # ---- Tray
    def _init_tray(self):
        self.tray = QtWidgets.QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_TITLE)
        menu = QtWidgets.QMenu()
        act_open = menu.addAction("Open")
        act_process_last = menu.addAction("Process Last")
        menu.addSeparator()
        act_exit = menu.addAction("Exit")
        act_open.triggered.connect(self._tray_open)
        act_process_last.triggered.connect(self._tray_process_last)
        act_exit.triggered.connect(QtWidgets.QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_open(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def _tray_process_last(self):
        if not self._last_process_settings:
            QtWidgets.QMessageBox.information(self, "Process Last", "Belum ada proses terakhir.")
            return
        # langsung jalankan ulang dengan settings terakhir:
        s = self._last_process_settings
        self.process_settings = s
        self._apply_process_settings_to_ui()
        self._on_run_process()

    def _tray_activated(self, reason):
        if reason in (QtWidgets.QSystemTrayIcon.Trigger, QtWidgets.QSystemTrayIcon.DoubleClick):
            self._tray_open()

    def closeEvent(self, e: QtGui.QCloseEvent):
        e.ignore()
        self.hide()
        if not self._tray_tip_shown:
            self.tray.showMessage(APP_TITLE, "Aplikasi tetap berjalan di system tray.",
                                  QtWidgets.QSystemTrayIcon.Information, 2500)
            self._tray_tip_shown = True
    def _open_eval_folder(self):

        path = None
        summary = self.ev_summary.edit.text().strip()
        if summary and os.path.exists(summary):
            path = os.path.dirname(summary)
        else:
            results = self.ev_results.edit.text().strip()
            if results and os.path.exists(results):
                path = results
        if not path:
            QtWidgets.QMessageBox.information(
                self,
                "Open Evaluate Folder",
                "Folder evaluate belum tersedia."
            )
            return
        if sys.platform.startswith("win"):
            os.startfile(path)
        else:
            QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(path)
            )

def main():
    # konsistenkan tampilan ikon/panah
    QtWidgets.QApplication.setStyle("Fusion")

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Windows taskbar AppID (agar icon tampil)
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OSAI.PLAOSv1.GUI")
        except Exception:
            pass

    ui = UiSettings()
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "ui" in data:
                ui = UiSettings(**data["ui"])
    except Exception:
        pass

    app.setWindowIcon(app_icon())
    app.setStyleSheet(DARK_QSS if ui.theme == "dark" else LIGHT_QSS)

    win = MainWindow(ui)
    if ui.start_minimized:
        win.hide()
    else:
        win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
