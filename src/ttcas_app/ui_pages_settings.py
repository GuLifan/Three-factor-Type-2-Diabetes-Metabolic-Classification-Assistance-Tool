from __future__ import annotations

# 设置页（TTCAS）
# - 只负责“展示与发信号”：不直接落盘、不直接改主题/字体
# - 主窗口负责接收信号并执行全局应用（便于集中控制与日志记录）

from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtWidgets import QFormLayout, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, CardWidget, PushButton, SubtitleLabel, SwitchButton

from ttcas_app.config import AppConfig
from ttcas_app.core_paths import AppPaths
from ttcas_app.core_settings import load_ui_settings
from ttcas_app.ui_i18n import ui_text


class SettingsPage(QWidget):
    """
    设置/信息页面（TTCAS）
    - 字体大小：A-/A+，全局立即生效并持久化
    - 主题：浅色/深色，立即生效并持久化
    - 本地目录：AppData/logs/data/config
    - 快捷入口：外部归档、聚类原则、计算器说明、用户手册、关于信息
    """

    fontDeltaRequested = Signal(int)
    darkModeRequested = Signal(bool)
    languageModeRequested = Signal(bool)
    openArchiveRequested = Signal()
    openConfigRequested = Signal()
    openPatientsRequested = Signal()
    openLogsRequested = Signal()
    showClusterPrincipleRequested = Signal()
    showToolsPrincipleRequested = Signal()
    openUserManualRequested = Signal()

    def __init__(self, *, cfg: AppConfig, paths: AppPaths, lang: str, parent=None) -> None:
        super().__init__(parent)

        self._cfg = cfg
        self._paths = paths
        self._lang = lang

        content = QWidget()
        content.setObjectName("settings_content")

        self._font_label = QLabel("-")
        self._switch_dark = SwitchButton(self)
        self._switch_dark.setObjectName("switch_dark")
        self._switch_dark.checkedChanged.connect(self.darkModeRequested.emit)

        self._switch_lang = SwitchButton(self)
        self._switch_lang.setObjectName("switch_lang")
        self._switch_lang.checkedChanged.connect(self.languageModeRequested.emit)

        btn_font_minus = PushButton("A-")
        btn_font_plus = PushButton("A+")
        btn_font_minus.setObjectName("btn_font_minus")
        btn_font_plus.setObjectName("btn_font_plus")
        btn_font_minus.clicked.connect(lambda: self.fontDeltaRequested.emit(-1))
        btn_font_plus.clicked.connect(lambda: self.fontDeltaRequested.emit(+1))

        font_row = QHBoxLayout()
        font_row.addWidget(self._font_label)
        font_row.addStretch(1)
        font_row.addWidget(btn_font_minus)
        font_row.addWidget(btn_font_plus)
        font_row_w = QWidget()
        font_row_w.setLayout(font_row)

        self._lbl_font = QLabel("")
        self._lbl_theme = QLabel("")
        self._lbl_lang = QLabel("")

        self._ui_form = QFormLayout()
        self._ui_form.addRow(self._lbl_font, font_row_w)
        self._ui_form.addRow(self._lbl_theme, self._switch_dark)
        self._ui_form.addRow(self._lbl_lang, self._switch_lang)

        self._ui_card_title = SubtitleLabel("")
        ui_card = CardWidget(content)
        ui_card_lay = QVBoxLayout(ui_card)
        ui_card_lay.addWidget(self._ui_card_title)
        ui_form_w = QWidget()
        ui_form_w.setLayout(self._ui_form)
        ui_card_lay.addWidget(ui_form_w)

        self._btn_open_archive = PushButton("")
        self._btn_open_archive.clicked.connect(self.openArchiveRequested.emit)
        self._btn_open_config = PushButton("")
        self._btn_open_config.clicked.connect(self.openConfigRequested.emit)
        self._btn_open_patients = PushButton("")
        self._btn_open_patients.clicked.connect(self.openPatientsRequested.emit)
        self._btn_open_logs = PushButton("")
        self._btn_open_logs.clicked.connect(self.openLogsRequested.emit)

        self._paths_card_title = SubtitleLabel("")
        paths_card = CardWidget(content)
        paths_card_lay = QVBoxLayout(paths_card)
        paths_card_lay.addWidget(self._paths_card_title)
        row_paths = QHBoxLayout()
        row_paths.addWidget(self._btn_open_archive)
        row_paths.addWidget(self._btn_open_config)
        row_paths.addWidget(self._btn_open_patients)
        row_paths.addWidget(self._btn_open_logs)
        row_paths.addStretch(1)
        row_paths_w = QWidget()
        row_paths_w.setLayout(row_paths)
        paths_card_lay.addWidget(row_paths_w)

        self._btn_cluster = PushButton("")
        self._btn_cluster.clicked.connect(self.showClusterPrincipleRequested.emit)
        self._btn_tools = PushButton("")
        self._btn_tools.clicked.connect(self.showToolsPrincipleRequested.emit)
        self._btn_manual = PushButton("")
        self._btn_manual.clicked.connect(self.openUserManualRequested.emit)

        self._docs_card_title = SubtitleLabel("")
        docs_card = CardWidget(content)
        docs_card_lay = QVBoxLayout(docs_card)
        docs_card_lay.addWidget(self._docs_card_title)
        row_docs = QHBoxLayout()
        row_docs.addWidget(self._btn_cluster)
        row_docs.addWidget(self._btn_tools)
        row_docs.addWidget(self._btn_manual)
        row_docs.addStretch(1)
        row_docs_w = QWidget()
        row_docs_w.setLayout(row_docs)
        docs_card_lay.addWidget(row_docs_w)

        self._about_card_title = SubtitleLabel("")
        about_card = CardWidget(content)
        about_card_lay = QVBoxLayout(about_card)
        about_card_lay.addWidget(self._about_card_title)

        self._about_top = QLabel("")
        self._about_mid = QLabel("")
        self._about_bot = QLabel("")
        for lab in (self._about_top, self._about_mid, self._about_bot):
            lab.setWordWrap(True)
            lab.setOpenExternalLinks(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
            about_card_lay.addWidget(lab)

        v = QVBoxLayout()
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(12)
        self._page_title = CaptionLabel("")
        v.addWidget(self._page_title)
        v.addWidget(ui_card)
        v.addWidget(paths_card)
        v.addWidget(docs_card)
        v.addWidget(about_card)
        v.addStretch(1)
        content.setLayout(v)

        scroll = QScrollArea()
        scroll.setObjectName("settings_scroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.viewport().setAutoFillBackground(False)

        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)

        self.setStyleSheet(
            """
            QWidget#settings_content { background: transparent; color: palette(text); }
            QScrollArea#settings_scroll { background: transparent; border: none; }
            QScrollArea#settings_scroll > QWidget > QWidget { background: transparent; }
            """
        )

        self.refresh(theme_hint=None, font_pt_hint=None)
        self.apply_language(lang)

    def refresh(self, *, theme_hint: str | None, font_pt_hint: int | None) -> None:
        ui = load_ui_settings(default_font_pt=self._cfg.ui.font_point_size, default_theme=self._cfg.ui.theme_default)
        pt = int(font_pt_hint) if font_pt_hint is not None else int(ui.font_point_size)
        theme = str(theme_hint) if theme_hint is not None else str(ui.theme)
        self._font_label.setText(f"{pt} pt")
        with QSignalBlocker(self._switch_dark):
            self._switch_dark.setChecked(theme == "dark")
        with QSignalBlocker(self._switch_lang):
            self._switch_lang.setChecked(ui.language == "en")

    def apply_language(self, lang: str) -> None:
        self._lang = lang

        self._page_title.setText(ui_text("settings_title", lang))
        self._ui_card_title.setText(ui_text("settings_block_ui", lang))
        self._paths_card_title.setText(ui_text("settings_block_paths", lang))
        self._docs_card_title.setText(ui_text("settings_block_docs", lang))
        self._about_card_title.setText("关于" if lang == "zh" else "About")

        self._lbl_font.setText(ui_text("settings_font", lang))
        self._lbl_theme.setText(ui_text("settings_theme", lang))
        self._lbl_lang.setText(ui_text("settings_lang", lang))

        self._switch_dark.setOnText(ui_text("settings_theme_dark", lang))
        self._switch_dark.setOffText(ui_text("settings_theme_light", lang))

        self._switch_lang.setOnText(ui_text("settings_lang_en", lang))
        self._switch_lang.setOffText(ui_text("settings_lang_zh", lang))

        self._btn_open_archive.setText(ui_text("btn_open_external_archive", lang))
        self._btn_open_config.setText(ui_text("btn_open_config", lang))
        self._btn_open_patients.setText(ui_text("btn_open_patients", lang))
        self._btn_open_logs.setText(ui_text("btn_open_logs", lang))

        self._btn_cluster.setText(ui_text("btn_cluster", lang))
        self._btn_tools.setText(ui_text("btn_tools", lang))
        self._btn_manual.setText(ui_text("btn_manual", lang))
        self._about_top.setText(self._as_html_links(self._cfg.ui.about.version_info))
        self._about_mid.setText(self._as_html_links(self._cfg.ui.about.dev_info))
        self._about_bot.setText(self._as_html_links(self._cfg.ui.about.contact_dev))
        self.refresh(theme_hint=None, font_pt_hint=None)

    @staticmethod
    def _as_html_links(text: str) -> str:
        import html
        import re

        normalized = (text or "").replace("\\n", "\n")
        raw = html.escape(normalized).replace("\n", "<br/>")
        url_re = re.compile(r"(https?://[^\s<]+)")
        return url_re.sub(r'<a href="\1">\1</a>', raw)
