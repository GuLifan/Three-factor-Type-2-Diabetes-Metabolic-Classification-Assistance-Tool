from __future__ import annotations

# 主窗口（TTCAS）
# - 负责创建各功能页面，并接收 Settings 页信号完成“字体/主题/语言”等全局设置
# - 负责打开外部资源（用户手册 PDF、外部归档 JSON）

import logging
import re
from pathlib import Path

# Qt：延迟合并多次操作（QTimer）、打开本地文件（QDesktopServices）、调色板与字体
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPalette
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget

# QFluentWidgets：主窗口外壳、侧边栏图标、主题切换
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import FluentWindow, NavigationItemPosition, Theme, setTheme

# 项目配置与持久化设置
from ttcas_app.config import AppConfig
from ttcas_app.core_paths import AppPaths
from ttcas_app.core_settings import load_ui_settings, save_font_point_size, save_language, save_theme

# 领域对象与存储
from ttcas_app.domain import DoctorSession
from ttcas_app.storage import PatientArchiveStore

# i18n 与页面
from ttcas_app.ui_i18n import ui_text
from ttcas_app.ui_pages_archive import PatientArchivePage
from ttcas_app.ui_pages_patient import PatientEntryPage
from ttcas_app.ui_pages_settings import SettingsPage
from ttcas_app.ui_pages_tools import ToolsPage
from ttcas_app.ui_principle_dialogs import ClusterPrincipleDialog, ToolsPrincipleDialog


class MainWindow(FluentWindow):
    """
    主窗口（TTCAS）
    - 左侧导航 + 右侧页面
    - 统一承接全局设置：字体、主题、关于、打开外部归档等
    """

    def __init__(self, *, cfg: AppConfig, paths: AppPaths, logger: logging.Logger, session: DoctorSession) -> None:
        super().__init__()
        # 运行时依赖：配置、路径、日志、当前会话信息
        self._cfg = cfg
        self._paths = paths
        self._logger = logger
        self._session = session
        # repo_root：用于定位 assets/（用户手册、说明图片等）
        self._repo_root = cfg.repo_root
        # 初始化语言：优先从 QApplication property 读取，否则回退 QSettings
        self._lang = self._get_initial_language()

        # 主窗口标题/尺寸：标题来自 config.yaml
        self.setWindowTitle(cfg.app.window_title)
        self.resize(1600, 1000)
        self.setMinimumSize(1200, 800)

        # 归档存储：用于读取 AppData/data/patients 里的归档文件
        self._archive_store = PatientArchiveStore(paths.patients_dir)

        # 主题切换：用 QTimer 合并快速多次点击，避免频繁重建/闪烁
        self._theme_apply_timer = QTimer(self)
        self._theme_apply_timer.setSingleShot(True)
        self._theme_apply_timer.timeout.connect(self._apply_pending_theme)
        self._pending_dark_mode: bool | None = None

        # 语言切换：同理，用计时器合并触发
        self._lang_apply_timer = QTimer(self)
        self._lang_apply_timer.setSingleShot(True)
        self._lang_apply_timer.timeout.connect(self._apply_pending_language)
        self._pending_lang: str | None = None

        # 字体切换：同理，用计时器合并触发
        self._font_apply_timer = QTimer(self)
        self._font_apply_timer.setSingleShot(True)
        self._font_apply_timer.timeout.connect(self._apply_pending_font_delta)
        self._pending_font_delta: int = 0

        # 创建页面并注册到侧边导航
        self._register_pages()

    def _get_initial_language(self) -> str:
        # 语言来源优先级：
        # 1) QApplication property（启动时由 app.py 写入）
        # 2) QSettings（用户上次选择）
        app = QApplication.instance()
        if app is not None:
            v = app.property("ui_language")
            if isinstance(v, str) and v in ("zh", "en"):
                return v
        ui = load_ui_settings(default_font_pt=self._cfg.ui.font_point_size, default_theme=self._cfg.ui.theme_default)
        return ui.language

    def _register_pages(self) -> None:
        # 患者页：输入/分型/报告导出/归档
        self._patient_entry_page = PatientEntryPage(
            cfg=self._cfg, paths=self._paths, logger=self._logger, session=self._session, lang=self._lang
        )
        self._patient_entry_page.setObjectName("patient_entry_page")

        # 归档页：列表 + 预览 + 回填患者页
        self._patient_archive_page = PatientArchivePage(store=self._archive_store, logger=self._logger, lang=self._lang)
        self._patient_archive_page.setObjectName("patient_archive_page")
        self._patient_archive_page.recordLoaded.connect(self._patient_entry_page.apply_record_dict)

        # 工具页：BMI/WWI/eGFR/单位换算/CGM 等
        self._tools_page = ToolsPage(logger=self._logger, lang=self._lang)
        self._tools_page.setObjectName("tools_page")

        # 设置页：主题/字体/语言、打开目录、说明与手册
        self._settings_page = SettingsPage(cfg=self._cfg, paths=self._paths, lang=self._lang)
        self._settings_page.setObjectName("settings_page")

        # Settings 页信号绑定：由主窗口统一落盘并广播刷新
        self._settings_page.fontDeltaRequested.connect(self._adjust_font)
        self._settings_page.darkModeRequested.connect(self._toggle_dark_mode)
        self._settings_page.languageModeRequested.connect(self._toggle_language)
        self._settings_page.openArchiveRequested.connect(self._open_archive_file)
        self._settings_page.openConfigRequested.connect(self._open_config_dir)
        self._settings_page.openPatientsRequested.connect(self._open_patients_dir)
        self._settings_page.openLogsRequested.connect(self._open_logs_dir)
        self._settings_page.showClusterPrincipleRequested.connect(self._show_cluster_principle)
        self._settings_page.showToolsPrincipleRequested.connect(self._show_tools_principle)
        self._settings_page.openUserManualRequested.connect(self._open_user_manual_pdf)

        # 侧边栏：注册子页面（QFluentWidgets 的 FluentWindow API）
        self._nav_patient = self.addSubInterface(
            self._patient_entry_page, FIF.PEOPLE, ui_text("nav_patient", self._lang)
        )
        self._nav_tools = self.addSubInterface(self._tools_page, FIF.CALENDAR, ui_text("nav_tools", self._lang))
        self._nav_archive = self.addSubInterface(
            self._patient_archive_page, FIF.FOLDER, ui_text("nav_archive", self._lang)
        )
        self._nav_settings = self.addSubInterface(
            self._settings_page,
            FIF.SETTING,
            ui_text("nav_settings", self._lang),
            NavigationItemPosition.BOTTOM,
        )

    def _open_user_manual_pdf(self) -> None:
        # 用户手册统一放在仓库 assets 目录；优先打开 Manual.pdf
        assets_dir = self._repo_root / "assets"
        preferred = assets_dir / "Manual.pdf"
        manual_file: Path | None = preferred if preferred.exists() else None

        # 若 preferred 不存在，但 assets 下只有一个 PDF，则取那个 PDF
        if manual_file is None and assets_dir.exists():
            pdfs = sorted(assets_dir.glob("*.pdf"))
            if len(pdfs) == 1:
                manual_file = pdfs[0]

        # 找不到手册时弹窗提示，并打印日志
        if manual_file is None or not manual_file.exists():
            msg = f"未找到用户手册 PDF。\n\n请将 PDF 放到：\n{preferred}"
            if assets_dir.exists():
                pdfs = sorted(assets_dir.glob("*.pdf"))
                if pdfs:
                    msg += "\n\n当前 assets 目录下已有 PDF：\n" + "\n".join(str(p.name) for p in pdfs)
            QMessageBox.information(self, "用户手册", msg)
            self._logger.warning("用户手册PDF未找到：%s", str(preferred))
            return

        # 调起系统默认 PDF 阅读器
        self._logger.info("打开用户手册PDF：%s", str(manual_file))
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(manual_file)))
        if not ok:
            QMessageBox.warning(self, "用户手册", "无法打开 PDF，请检查系统默认 PDF 阅读器设置。")
            self._logger.warning("打开用户手册PDF失败：%s", str(manual_file))

    def _show_cluster_principle(self) -> None:
        # 聚类说明弹窗：包含原理、参数、说明图
        self._logger.info("打开：聚类原则说明")
        dialog = ClusterPrincipleDialog(cfg=self._cfg, parent=self)
        dialog.exec()

    def _show_tools_principle(self) -> None:
        # 工具/计算器说明弹窗：包含常用公式与说明
        self._logger.info("打开：计算器说明")
        dialog = ToolsPrincipleDialog(parent=self)
        dialog.exec()

    def _adjust_font(self, delta: int) -> None:
        # 记录累积变化量（可能快速点击 A+/A- 多次）
        self._pending_font_delta += int(delta)
        # 延迟一点再应用：把多次点击合并成一次，减少 UI 抖动
        self._font_apply_timer.start(60)

    def _apply_pending_font_delta(self) -> None:
        # 没有待处理变化就直接退出
        if self._pending_font_delta == 0:
            return
        try:
            app = QApplication.instance()
            if app is None:
                return
            # 当前字号与下一字号（限制在 [8, 24]，避免过小/过大导致布局溢出）
            current_pt = int(app.font().pointSize())
            next_pt = max(8, min(24, current_pt + int(self._pending_font_delta)))
            self._pending_font_delta = 0
            # 持久化保存字号
            save_font_point_size(next_pt)

            # 应用字体到 QApplication：原生控件将跟随
            font = QFont(app.font())
            font.setPointSize(next_pt)
            app.setFont(font)

            # 类似主题切换的彻底控件刷新逻辑，确保字体更改立即生效
            try:
                import shiboken6  # type: ignore

                def _is_valid(o: object) -> bool:
                    try:
                        return bool(shiboken6.isValid(o))  # type: ignore[attr-defined]
                    except Exception:
                        return False

            except Exception:

                def _is_valid(o: object) -> bool:
                    return o is not None

            roots: list[QWidget] = []
            for w in list(QApplication.topLevelWidgets()):
                if isinstance(w, QWidget) and _is_valid(w):
                    roots.append(w)
            for w in (app.activeModalWidget(), app.activePopupWidget()):
                if isinstance(w, QWidget) and _is_valid(w):
                    roots.append(w)

            targets: list[QWidget] = []
            seen: set[int] = set()
            for root in roots:
                for w in [root, *list(root.findChildren(QWidget))]:
                    if not _is_valid(w):
                        continue
                    wid = id(w)
                    if wid in seen:
                        continue
                    seen.add(wid)
                    targets.append(w)

            # 更新所有控件
            for w in targets:
                try:
                    w.setFont(font)
                    w.update()
                except Exception:
                    continue

            # 刷新控件样式，确保字体更改生效
            for root in roots:
                try:
                    if not _is_valid(root):
                        continue
                    st = root.style()
                    try:
                        st.unpolish(root)
                    except Exception:
                        pass
                    try:
                        st.polish(root)
                    except Exception:
                        pass
                    root.update()
                except Exception:
                    continue

            # 设置页刷新显示的字号
            self._settings_page.refresh(theme_hint=None, font_pt_hint=next_pt)
            self._logger.info("字体大小调整：%s", next_pt)
            # 确保所有事件都被处理，字体更改立即生效
            QApplication.processEvents()
        except Exception:
            self._logger.exception("字体调整失败")
            QMessageBox.critical(self, "错误", "字体调整失败，请查看日志。")

    def _toggle_dark_mode(self, checked: bool) -> None:
        # SwitchButton 的 checkedChanged 会直接触发到这里
        self._pending_dark_mode = bool(checked)
        # 通过计时器合并多次快速切换
        self._theme_apply_timer.start(80)

    def _apply_pending_theme(self) -> None:
        if self._pending_dark_mode is None:
            return
        checked = bool(self._pending_dark_mode)
        self._pending_dark_mode = None
        try:
            # 主题字符串用于持久化存储
            theme = "dark" if checked else "light"
            save_theme(theme)
            # QFluentWidgets 主题切换（会更新全局 QSS）
            setTheme(Theme.DARK if checked else Theme.LIGHT)
            # QPalette：保证原生控件跟随（避免“文字还是黑/背景不变”等问题）
            self._apply_app_palette(is_dark=checked)
            # 覆盖 QSS：纠正原生控件颜色与弹窗按钮文字颜色
            self._apply_theme_overrides(is_dark=checked)
            # 设置页：刷新开关状态显示
            self._settings_page.refresh(theme_hint=theme, font_pt_hint=None)
            self._logger.info("主题切换：%s", theme)
        except Exception:
            self._logger.exception("主题切换失败")
            QMessageBox.critical(self, "错误", "主题切换失败，请查看日志。")

    @staticmethod
    def _apply_theme_overrides(*, is_dark: bool) -> None:
        # 与 app.py 中的 _apply_theme_overrides 相同目的：
        # - 切主题时重新注入一段基于 palette(...) 的 QSS
        # - 让原生输入/列表控件、弹窗按钮文字颜色始终与主题一致
        app = QApplication.instance()
        if app is None:
            return

        override_begin = "/*__TTCAS_THEME_OVERRIDE_BEGIN__*/"
        override_end = "/*__TTCAS_THEME_OVERRIDE_END__*/"
        override_re = re.compile(
            r"\n?\s*" + re.escape(override_begin) + r".*?" + re.escape(override_end) + r"\s*",
            flags=re.DOTALL,
        )

        base = app.styleSheet() or ""
        base = re.sub(override_re, "", base)
        app.setProperty("_ttcas_fluent_base_qss", base)

        text_color = "#FFFFFF" if is_dark else "#000000"
        override = (
            "\n"
            f"{override_begin}\n"
            "QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QTreeWidget, QTableWidget {"
            "  background-color: palette(base);"
            "  color: palette(text);"
            "}"
            "QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {"
            "  background-color: palette(highlight);"
            "  color: palette(highlighted-text);"
            "}"
            "QMessageBox QPushButton, QMessageBox QAbstractButton, QDialogButtonBox QPushButton, QDialogButtonBox QAbstractButton {"
            f"  color: {text_color};"
            "}"
            f"\n{override_end}\n"
        )
        app.setStyleSheet(base + override)

    def _apply_app_palette(self, *, is_dark: bool) -> None:
        # 注意：QFluentWidgets 依赖 QSS；QPalette 主要影响原生控件与 palette(...) 引用
        app = QApplication.instance()
        if app is None:
            return

        pal = QPalette(app.palette())
        if is_dark:
            text = QColor(255, 255, 255)
            window = QColor(32, 32, 32)
            base = QColor(25, 25, 25)
            highlight = QColor(0, 120, 215)
            button = QColor(45, 45, 45)
        else:
            text = QColor(0, 0, 0)
            window = QColor(255, 255, 255)
            base = QColor(255, 255, 255)
            highlight = QColor(0, 120, 215)
            button = QColor(245, 245, 245)

        pal.setColor(QPalette.ColorRole.Window, window)
        pal.setColor(QPalette.ColorRole.Base, base)
        pal.setColor(QPalette.ColorRole.AlternateBase, base)
        pal.setColor(QPalette.ColorRole.Button, button)
        pal.setColor(QPalette.ColorRole.WindowText, text)
        pal.setColor(QPalette.ColorRole.Text, text)
        pal.setColor(QPalette.ColorRole.ButtonText, text)
        pal.setColor(QPalette.ColorRole.ToolTipText, text)
        pal.setColor(QPalette.ColorRole.Highlight, highlight)
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        app.setPalette(pal)

        try:
            import shiboken6  # type: ignore

            def _is_valid(o: object) -> bool:
                try:
                    return bool(shiboken6.isValid(o))  # type: ignore[attr-defined]
                except Exception:
                    return False

        except Exception:

            def _is_valid(o: object) -> bool:
                return o is not None

        roots: list[QWidget] = []
        for w in list(QApplication.topLevelWidgets()):
            if isinstance(w, QWidget) and _is_valid(w):
                roots.append(w)
        for w in (app.activeModalWidget(), app.activePopupWidget()):
            if isinstance(w, QWidget) and _is_valid(w):
                roots.append(w)

        targets: list[QWidget] = []
        seen: set[int] = set()
        for root in roots:
            for w in [root, *list(root.findChildren(QWidget))]:
                if not _is_valid(w):
                    continue
                wid = id(w)
                if wid in seen:
                    continue
                seen.add(wid)
                targets.append(w)

        for w in targets:
            try:
                w.setPalette(pal)
                w.update()
            except Exception:
                continue

        for root in roots:
            try:
                if not _is_valid(root):
                    continue
                st = root.style()
                try:
                    st.unpolish(root)
                except Exception:
                    pass
                try:
                    st.polish(root)
                except Exception:
                    pass
                root.update()
            except Exception:
                continue

    def _toggle_language(self, checked: bool) -> None:
        # checked=True 表示切到英文；False 表示中文
        self._pending_lang = "en" if checked else "zh"
        self._lang_apply_timer.start(80)

    def _apply_pending_language(self) -> None:
        if self._pending_lang is None:
            return
        lang = str(self._pending_lang)
        self._pending_lang = None
        try:
            if lang == self._lang:
                return
            # 持久化语言设置
            save_language(lang)
            # 同步到 QApplication property，便于其他组件读取
            app = QApplication.instance()
            if app is not None:
                app.setProperty("ui_language", lang)
            # 刷新导航与页面语言
            self._apply_language(lang)
            self._logger.info("语言切换：%s", lang)
        except Exception:
            self._logger.exception("语言切换失败")
            QMessageBox.critical(self, "错误", "语言切换失败，请查看日志。")

    def _apply_language(self, lang: str) -> None:
        # 统一入口：更新导航文字 + 通知各页面刷新
        self._lang = lang

        self._nav_patient.setText(ui_text("nav_patient", lang))
        self._nav_tools.setText(ui_text("nav_tools", lang))
        self._nav_archive.setText(ui_text("nav_archive", lang))
        self._nav_settings.setText(ui_text("nav_settings", lang))

        self._patient_entry_page.apply_language(lang)
        self._tools_page.apply_language(lang)
        self._patient_archive_page.apply_language(lang)
        self._settings_page.apply_language(lang)


    def _open_archive_file(self) -> None:
        # 打开外部归档 JSON，并回填到患者页
        file_path, _ = QFileDialog.getOpenFileName(self, "选择归档 JSON 文件", "", "JSON (*.json);;All Files (*)")
        if not file_path:
            return

        self._logger.info("打开外部归档JSON：%s", file_path)
        try:
            data = self._archive_store.load(Path(file_path))
        except Exception:
            self._logger.exception("打开归档文件失败")
            QMessageBox.critical(self, "错误", "打开失败，请查看日志。")
            return

        data["_source_file"] = str(file_path)
        self._patient_entry_page.apply_record_dict(data)
        self.switchTo(self._patient_entry_page)

    def _open_config_dir(self) -> None:
        # 打开 AppData/config 目录
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._paths.config_dir)))
        if not ok:
            QMessageBox.warning(self, "提示", "无法打开目录，请手动复制路径到资源管理器。")

    def _open_patients_dir(self) -> None:
        # 打开 AppData/data/patients 目录（若不存在则创建）
        self._paths.patients_dir.mkdir(parents=True, exist_ok=True)
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._paths.patients_dir)))
        if not ok:
            QMessageBox.warning(self, "提示", "无法打开目录，请手动复制路径到资源管理器。")

    def _open_logs_dir(self) -> None:
        # 打开 AppData/logs 目录（若不存在则创建）
        self._paths.logs_dir.mkdir(parents=True, exist_ok=True)
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._paths.logs_dir)))
        if not ok:
            QMessageBox.warning(self, "提示", "无法打开目录，请手动复制路径到资源管理器。")
