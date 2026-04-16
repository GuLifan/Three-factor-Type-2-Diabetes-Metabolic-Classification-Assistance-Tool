from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import PushButton, SubtitleLabel, TextEdit

from ttcas_app.storage import PatientArchiveStore
from ttcas_app.ui_i18n import ui_text


class PatientArchivePage(QWidget):
    """
    归档浏览页（TTCAS）
    - 展示 AppData/data/patients 下的归档文件列表
    - 点击“加载到患者页”后，发出 recordLoaded(dict) 信号
    """

    recordLoaded = Signal(dict)

    def __init__(self, *, store: PatientArchiveStore, logger: logging.Logger, lang: str, parent=None) -> None:
        super().__init__(parent)
        self._store = store
        self._logger = logger
        self._lang = lang
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        self._list = QListWidget()
        self._list.setObjectName("archive_list")
        self._list.itemDoubleClicked.connect(lambda _: self._emit_selected())
        self._list.currentItemChanged.connect(lambda *_: self._update_preview())

        self._btn_refresh = PushButton("")
        self._btn_refresh.clicked.connect(self.refresh)

        self._btn_load = PushButton("")
        self._btn_load.clicked.connect(self._emit_selected)

        self._preview = TextEdit()
        self._preview.setObjectName("archive_preview")
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("")

        row = QHBoxLayout()
        row.addWidget(self._btn_refresh)
        row.addWidget(self._btn_load)
        row.addStretch(1)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Horizontal)
        splitter.addWidget(self._list)
        splitter.addWidget(self._preview)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        v = QVBoxLayout()
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(12)
        self._title = SubtitleLabel("")
        v.addWidget(self._title)
        v.addLayout(row)
        v.addWidget(splitter, 1)
        self.setLayout(v)

        self.setStyleSheet(
            """
            QListWidget, QTextEdit {
                background-color: palette(base);
                color: palette(text);
                border: 1px solid palette(mid);
            }

            QListWidget::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
            """
        )

        self.apply_language(self._lang)

    def apply_language(self, lang: str) -> None:
        self._lang = lang
        self._title.setText(ui_text("archive_title", lang))
        self._btn_refresh.setText(ui_text("archive_refresh", lang))
        self._btn_load.setText(ui_text("archive_load", lang))
        self._preview.setPlaceholderText(ui_text("archive_preview", lang))

    def refresh(self) -> None:
        self._list.clear()
        files = self._store.list_files()
        if not files:
            it = QListWidgetItem("暂无归档（patients 目录为空）" if self._lang == "zh" else "No records (patients folder is empty).")
            it.setData(32, None)
            self._list.addItem(it)
            self._preview.setPlainText("")
            return

        for p in files:
            display = self._format_item(p)
            it = QListWidgetItem(display)
            it.setData(32, str(p))
            self._list.addItem(it)
        if self._list.count():
            self._list.setCurrentRow(0)
            self._update_preview()

    def _format_item(self, path: Path) -> str:
        try:
            d = self._store.load(path)
        except Exception:
            return f"{path.name}（无法解析）"
        inp = d.get("input") or {}
        pid = inp.get("patient_id") if isinstance(inp, dict) else None
        gen = d.get("generated_at") or d.get("generatedAt") or ""
        name = inp.get("patient_name") if isinstance(inp, dict) else None
        name_s = f" {name}" if name else ""
        return f"{path.name} | {pid or '-'}{name_s} | {gen}"

    def _emit_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        p = item.data(32)
        if not p:
            return
        try:
            d = self._store.load(Path(str(p)))
        except Exception:
            self._logger.exception("读取归档失败：%s", str(p))
            QMessageBox.critical(self, "错误", "读取归档失败，请查看日志。")
            return
        d["_source_file"] = str(p)
        self.recordLoaded.emit(d)

    def _update_preview(self) -> None:
        item = self._list.currentItem()
        if item is None:
            self._preview.setPlainText("")
            return
        p = item.data(32)
        if not p:
            self._preview.setPlainText("")
            return
        try:
            d = self._store.load(Path(str(p)))
        except Exception:
            self._preview.setPlainText("无法解析该归档文件。" if self._lang == "zh" else "Failed to parse the record.")
            return
        self._preview.setPlainText(json.dumps(d, ensure_ascii=False, indent=2))
