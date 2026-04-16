from __future__ import annotations

# 应用启动入口（TTCAS）
# 目标：
# - 初始化：配置、QApplication、路径、日志、异常处理
# - 登录成功后再创建主窗口（登录与主体分离）

# 标准库：异常堆栈拼接、进程退出、路径类型
import sys
import traceback
import re
from pathlib import Path

# Qt：事件过滤器、DPI、调色板/字体/图标、弹窗
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

# QFluentWidgets：统一主题（它会通过样式表改变控件外观）
from qfluentwidgets import Theme, setTheme

# 项目内模块：配置/日志/路径/设置/存储
from ttcas_app.config import load_config
from ttcas_app.core_logging import setup_app_logger
from ttcas_app.core_paths import get_app_paths
from ttcas_app.core_settings import load_ui_settings
from ttcas_app.storage import DoctorAccountsStore


def _install_excepthook(*, log_file: Path) -> None:
    # sys.excepthook：捕获“未处理异常”的最后一道防线
    # 目的：在临床现场发生崩溃时，至少弹窗提示并给出日志路径，方便回收排查
    def excepthook(exc_type, exc_value, exc_tb) -> None:
        # 将异常类型/信息/堆栈统一拼成字符串
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        # 弹出阻塞型错误对话框（主窗口可能尚未创建，因此 parent=None）
        QMessageBox.critical(
            None,
            "程序异常",
            "程序发生未处理异常并即将退出。\n\n"
            f"请将以下日志文件提供给开发者：\n{log_file}\n\n"
            "异常详情：\n"
            f"{details}",
        )
        # 直接退出：未处理异常通常意味着状态不可恢复
        sys.exit(1)

    # 把全局异常钩子替换为我们自己的实现
    sys.excepthook = excepthook


def _apply_global_font(font_pt: int) -> None:
    # 获取当前 QApplication（必须在 QApplication 创建之后才能调用）
    app = QApplication.instance()
    if app is None:
        return
    # 基于现有字体复制一份，再修改字号，避免丢失字体家族/粗细等设置
    font = QFont(app.font())
    font.setPointSize(int(font_pt))
    # 设置到应用级别：全局控件默认会跟随
    app.setFont(font)


def _apply_app_palette(*, is_dark: bool) -> None:
    # 用 QPalette 控制“原生 Qt 控件”的基础颜色（背景/文字/高亮等）
    app = QApplication.instance()
    if app is None:
        return

    # 从当前调色板复制，避免遗漏系统默认角色
    pal = QPalette(app.palette())
    if is_dark:
        # 深色主题：白字 + 深色背景
        text = QColor(255, 255, 255)
        window = QColor(32, 32, 32)
        base = QColor(25, 25, 25)
        highlight = QColor(0, 120, 215)
        button = QColor(45, 45, 45)
    else:
        # 浅色主题：黑字 + 白色背景
        text = QColor(0, 0, 0)
        window = QColor(255, 255, 255)
        base = QColor(255, 255, 255)
        highlight = QColor(0, 120, 215)
        button = QColor(245, 245, 245)

    # Window：顶层窗口背景色
    pal.setColor(QPalette.ColorRole.Window, window)
    # Base：输入框/文本框等“内容区域”背景色
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.AlternateBase, base)
    # Button：按钮背景色
    pal.setColor(QPalette.ColorRole.Button, button)
    # WindowText/Text/ButtonText/ToolTipText：各类文字颜色
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.ToolTipText, text)
    # 高亮与高亮文字：列表选择、输入框选中等
    pal.setColor(QPalette.ColorRole.Highlight, highlight)
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    # 写回应用：使原生控件跟随
    app.setPalette(pal)


def _apply_theme_overrides(*, is_dark: bool) -> None:
    # QFluentWidgets 切主题主要靠全局样式表（QSS）
    # 但很多“原生控件”在混用 QSS + QPalette 时，可能出现“背景/字体颜色不更新”的问题
    # 这里追加一段只针对常见原生控件的 QSS，并用 palette(...) 绑定到 QPalette，从而随主题自动变化
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

    # 弹窗按钮在浅色主题下可能被 QFluentWidgets 的按钮样式“污染”为白字，这里强制纠正
    text_color = "#FFFFFF" if is_dark else "#000000"
    # 关键点：background-color / color 使用 palette(...)，避免写死颜色导致另外一个主题失真
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
    # 将“原有样式 + 覆盖样式”整体写回；每次切主题都重新注入，避免被覆盖
    app.setStyleSheet(base + override)


class _DialogThemeFilter(QObject):
    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        try:
            # 弹窗在 show 的瞬间补一层按钮文字颜色兜底：
            # - QMessageBox 的按钮属于原生 QPushButton
            # - 可能受到 QFluentWidgets 的样式影响导致浅色主题仍显示白字
            if event.type() == QEvent.Type.Show and isinstance(obj, QMessageBox):
                from qfluentwidgets.common.config import isDarkTheme

                is_dark = bool(isDarkTheme())
                text_color = "#FFFFFF" if is_dark else "#000000"
                obj.setStyleSheet(
                    f"QPushButton, QAbstractButton {{ color: {text_color}; }}"
                )
        except Exception:
            pass
        # 返回 False：不拦截事件，让 Qt 继续默认处理
        return False


def run(*, repo_root: Path) -> int:
    # 读取配置：默认 repo_root/config.yaml，也可由环境变量 TTCAS_CONFIG 指定
    cfg = load_config(repo_root=repo_root)

    # 高 DPI 相关设置：不同 Qt 版本支持的属性名略有差异，需逐项判断
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy") and hasattr(
        Qt.HighDpiScaleFactorRoundingPolicy, "PassThrough"
    ):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 创建 QApplication：Qt 程序的事件循环与全局状态从此开始
    app = QApplication(sys.argv)
    # organization/application 会影响：
    # - QStandardPaths.AppDataLocation（用户数据目录）
    # - QSettings 的落盘位置
    app.setOrganizationName(cfg.app.organization_name)
    app.setApplicationName(cfg.app.application_name)

    # 初始化 AppData 路径，并创建必要目录
    paths = get_app_paths()
    paths.ensure_dirs()
    # 初始化滚动日志：写入 AppData/logs/app.log
    logger = setup_app_logger(logs_dir=paths.logs_dir)
    # 启动关键信息：用于排障与版本追踪
    logger.info("应用启动：%s", cfg.app.application_display_name)
    logger.info("应用版本=%s 聚类版本=%s", cfg.app.app_version, cfg.model.cluster_version)
    logger.info("配置文件：%s", str(cfg.config_file))
    logger.info("AppData：%s", str(paths.app_data_dir))

    # 安装“未处理异常”钩子：保证崩溃时给出日志位置
    _install_excepthook(log_file=paths.logs_dir / "app.log")

    # 读取 UI 持久化设置：字体/主题/语言（由 QSettings 提供）
    ui_settings = load_ui_settings(default_font_pt=cfg.ui.font_point_size, default_theme=cfg.ui.theme_default)
    # 字体：应用级别全局生效
    _apply_global_font(ui_settings.font_point_size)
    # 主题：QFluentWidgets + QPalette 双保险
    is_dark = ui_settings.theme == "dark"
    setTheme(Theme.DARK if is_dark else Theme.LIGHT)
    _apply_app_palette(is_dark=is_dark)
    _apply_theme_overrides(is_dark=is_dark)
    # 语言：写入 QApplication property，供各页面读取
    app.setProperty("ui_language", ui_settings.language)
    logger.info("主题=%s 字体pt=%s 语言=%s", ui_settings.theme, ui_settings.font_point_size, ui_settings.language)

    # 安装弹窗主题过滤器：修复弹窗按钮文字颜色跟随主题
    app.installEventFilter(_DialogThemeFilter(app))

    # 设置应用图标：从 config.yaml 的 ui.icon_path 读取
    icon_file = cfg.resolve_path(cfg.ui.icon_path) if cfg.ui.icon_path else None
    if icon_file is not None and icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    # 初始化本地账号库：首次运行会创建默认文件
    accounts_store = DoctorAccountsStore(paths.config_dir / "doctor_accounts.json")
    accounts_store.ensure_default_file()

    from ttcas_app.ui_login import LoginDialog

    # 先登录再进入主窗口：避免“未登录状态”也能触发业务逻辑
    login = LoginDialog(cfg=cfg, store=accounts_store, logger=logger, lang=ui_settings.language)
    if login.exec() != QDialog.DialogCode.Accepted or login.session is None:
        # 用户关闭登录框/取消：正常退出，不算错误
        logger.info("用户取消登录，程序退出")
        return 0

    from ttcas_app.ui_main import MainWindow

    # 登录成功后创建主窗口并显示
    window = MainWindow(cfg=cfg, paths=paths, logger=logger, session=login.session)
    window.show()
    # 进入 Qt 事件循环：直到用户退出应用
    return app.exec()
