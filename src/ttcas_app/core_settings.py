from __future__ import annotations

# UI 持久化设置（TTCAS）
# - 基于 Qt 的 QSettings：用于保存字体大小、主题、语言
# - 注意：QSettings 的存储路径会受到 QApplication 的 organization/application 影响

from dataclasses import dataclass

from PySide6.QtCore import QSettings


@dataclass(frozen=True)
class UiSettings:
    font_point_size: int
    theme: str
    language: str


def _settings() -> QSettings:
    """
    QSettings 的命名空间由：
    - QApplication.setOrganizationName
    - QApplication.setApplicationName
    决定；这两个值必须在 QApplication 初始化后尽早设置且保持稳定。
    """

    return QSettings()


def load_ui_settings(*, default_font_pt: int, default_theme: str) -> UiSettings:
    s = _settings()
    font_pt = int(s.value("ui/font_point_size", default_font_pt))
    theme = str(s.value("ui/theme", default_theme))
    language = str(s.value("ui/language", "zh"))
    if theme not in ("light", "dark"):
        theme = default_theme
    if font_pt < 8:
        font_pt = 8
    if font_pt > 24:
        font_pt = 24
    if language not in ("zh", "en"):
        language = "zh"
    return UiSettings(font_point_size=font_pt, theme=theme, language=language)


def save_font_point_size(font_pt: int) -> None:
    s = _settings()
    s.setValue("ui/font_point_size", int(font_pt))


def save_theme(theme: str) -> None:
    t = "dark" if str(theme).lower() == "dark" else "light"
    s = _settings()
    s.setValue("ui/theme", t)


def save_language(language: str) -> None:
    lang = "en" if str(language).lower() in ("en", "english") else "zh"
    s = _settings()
    s.setValue("ui/language", lang)
