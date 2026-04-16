from __future__ import annotations

# 关于页（TTCAS）
# - 使用 QTextBrowser 显示富文本（支持链接）
# - 文本来自 config.yaml 的 ui.about.* 字段

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget, QTextBrowser
from qfluentwidgets import SubtitleLabel

from ttcas_app.config import AppConfig
from ttcas_app.ui_i18n import ui_text


class _AboutBasePage(QWidget):
    def __init__(self, *, cfg: AppConfig, lang: str) -> None:
        super().__init__()
        self._cfg = cfg
        self._lang = lang

        self._title = SubtitleLabel("")
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setReadOnly(True)

        content = QWidget()
        content.setObjectName("about_content")
        v = QVBoxLayout()
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(12)
        v.addWidget(self._title)
        v.addWidget(self._browser, 1)
        content.setLayout(v)

        scroll = QScrollArea()
        scroll.setObjectName("about_scroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.viewport().setAutoFillBackground(False)

        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)

        self.setStyleSheet(
            """
            QWidget#about_content { background: transparent; }
            QScrollArea#about_scroll { background: transparent; border: none; }
            QScrollArea#about_scroll > QWidget > QWidget { background: transparent; }
            """
        )

    @staticmethod
    def _as_html(text: str) -> str:
        import html
        import re

        normalized = (text or "").replace("\\n", "\n")
        raw = html.escape(normalized).replace("\n", "<br/>")
        url_re = re.compile(r"(https?://[^\s<]+)")
        return url_re.sub(r'<a href="\1">\1</a>', raw)

    def apply_language(self, lang: str) -> None:
        self._lang = lang


class AboutVersionPage(_AboutBasePage):
    def __init__(self, *, cfg: AppConfig, lang: str) -> None:
        super().__init__(cfg=cfg, lang=lang)
        self.apply_language(lang)

    def apply_language(self, lang: str) -> None:
        super().apply_language(lang)
        self._title.setText(ui_text("nav_about_version", lang))
        self._browser.setHtml(self._as_html(self._cfg.ui.about.version_info))


class AboutDevPage(_AboutBasePage):
    def __init__(self, *, cfg: AppConfig, lang: str) -> None:
        super().__init__(cfg=cfg, lang=lang)
        self.apply_language(lang)

    def apply_language(self, lang: str) -> None:
        super().apply_language(lang)
        self._title.setText(ui_text("nav_about_dev", lang))
        self._browser.setHtml(self._as_html(self._cfg.ui.about.dev_info))


class AboutContactPage(_AboutBasePage):
    def __init__(self, *, cfg: AppConfig, lang: str) -> None:
        super().__init__(cfg=cfg, lang=lang)
        self.apply_language(lang)

    def apply_language(self, lang: str) -> None:
        super().apply_language(lang)
        self._title.setText(ui_text("nav_about_contact", lang))
        self._browser.setHtml(self._as_html(self._cfg.ui.about.contact_dev))
