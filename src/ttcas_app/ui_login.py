from __future__ import annotations

# 登录/注册对话框（TTCAS）
# - 登录成功后由 app.py 创建主窗口
# - 账号存储在 AppData/config/doctor_accounts.json（离线）

import logging
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout
from qfluentwidgets import ComboBox, LineEdit, PushButton

from ttcas_app.config import AppConfig
from ttcas_app.domain import DoctorSession
from ttcas_app.storage import DoctorAccountsStore
from ttcas_app.ui_i18n import ui_text


class LoginDialog(QDialog):
    """
    医师登录对话框（TTCAS）
    - 登录：Doctor_ID + Password
    - 注册：弹出 RegisterDialog 写入本地账号库
    """

    def __init__(
        self, *, cfg: AppConfig, store: DoctorAccountsStore, logger: logging.Logger, lang: str, parent=None
    ) -> None:
        super().__init__(parent)

        self._lang = lang
        self.setWindowTitle(ui_text("login_title", self._lang))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(460)

        self._cfg = cfg
        self._store = store
        self._logger = logger
        self._session: DoctorSession | None = None

        self._doctor_id = LineEdit()
        self._doctor_id.setPlaceholderText("6~20位，例如：doctor01")

        self._password = LineEdit()
        self._password.setPlaceholderText("6~20位")
        self._password.setEchoMode(LineEdit.EchoMode.Password)

        form = QFormLayout()
        form.addRow(ui_text("login_doctor_id", self._lang), self._doctor_id)
        form.addRow(ui_text("login_password", self._lang), self._password)

        self._btn_login = PushButton(ui_text("login_btn", self._lang))
        self._btn_login.clicked.connect(self._on_login_clicked)
        self._btn_login.setDefault(True)
        self._btn_login.setAutoDefault(True)

        self._btn_register = PushButton(ui_text("register_btn", self._lang))
        self._btn_register.clicked.connect(self._on_register_clicked)
        self._btn_register.setAutoDefault(False)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self._btn_register)
        btns.addWidget(self._btn_login)

        hint = QLabel(f"{self._cfg.app.application_display_name} {self._cfg.app.app_version}")
        hint.setWordWrap(True)

        version = QLabel(f"聚类逻辑版本：{self._cfg.model.cluster_version}")

        layout = QVBoxLayout()
        layout.addWidget(hint)
        layout.addWidget(version)
        layout.addLayout(form)
        layout.addLayout(btns)
        self.setLayout(layout)

    @property
    def session(self) -> DoctorSession | None:
        return self._session

    def _on_login_clicked(self) -> None:
        doctor_id = self._doctor_id.text().strip()
        self._btn_login.setEnabled(False)
        try:
            self._logger.info("尝试登录：%s", doctor_id or "<empty>")
            ok = self._store.authenticate(doctor_id=doctor_id, password=self._password.text())
            if not ok:
                raise ValueError("账号或密码错误")
        except ValueError as ex:
            self._logger.warning("登录失败：%s | %s", doctor_id or "<empty>", str(ex))
            QMessageBox.warning(self, "登录失败", str(ex))
            self._btn_login.setEnabled(True)
            return
        except Exception:
            self._logger.exception("登录过程中发生未预期错误")
            QMessageBox.critical(self, "错误", "登录失败，请查看日志。")
            self._btn_login.setEnabled(True)
            return

        self._session = DoctorSession(doctor_id=doctor_id, login_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self._logger.info("登录成功：%s", doctor_id)
        self.accept()

    def _on_register_clicked(self) -> None:
        self._logger.info("打开注册对话框")
        dialog = RegisterDialog(store=self._store, logger=self._logger, lang=self._lang, parent=self)
        dialog.exec()


class RegisterDialog(QDialog):
    """
    注册对话框（TTCAS）
    - 写入本地账号库（AppData/config/doctor_accounts.json）
    - 兼容旧结构：若旧文件中已有账号，注册时会正常判重
    """

    def __init__(self, *, store: DoctorAccountsStore, logger: logging.Logger, lang: str, parent=None) -> None:
        super().__init__(parent)

        self._lang = lang
        self.setWindowTitle(ui_text("register_title", self._lang))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(520)

        self._store = store
        self._logger = logger

        self._doctor_id = LineEdit()
        self._doctor_id.setPlaceholderText("6~20位，例如：ZY01000123456")

        self._organization = LineEdit()
        self._organization.setPlaceholderText("西安交通大学第一附属医院")

        self._department = LineEdit()
        self._department.setPlaceholderText("内分泌代谢科")

        self._password1 = LineEdit()
        self._password1.setEchoMode(LineEdit.EchoMode.Password)
        self._password1.setPlaceholderText("6~20位")

        self._password2 = LineEdit()
        self._password2.setEchoMode(LineEdit.EchoMode.Password)
        self._password2.setPlaceholderText("再次输入密码")

        form = QFormLayout()
        form.addRow(ui_text("login_doctor_id", self._lang), self._doctor_id)
        form.addRow(ui_text("org_label", self._lang), self._organization)
        form.addRow(ui_text("dept_label", self._lang), self._department)
        form.addRow(ui_text("login_password", self._lang), self._password1)
        form.addRow(ui_text("confirm_password", self._lang), self._password2)

        self._btn_save = PushButton(ui_text("btn_save", self._lang))
        self._btn_save.clicked.connect(self._on_save_clicked)

        self._btn_cancel = PushButton(ui_text("btn_cancel", self._lang))
        self._btn_cancel.clicked.connect(self.reject)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self._btn_cancel)
        btns.addWidget(self._btn_save)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(btns)
        self.setLayout(layout)

    def _on_save_clicked(self) -> None:
        try:
            did = self._doctor_id.text().strip()
            dep = self._department.text().strip()
            org = self._organization.text().strip()

            if not dep:
                raise ValueError("科室不能为空")
            if not org:
                raise ValueError("单位不能为空")

            pwd1 = self._password1.text()
            pwd2 = self._password2.text()
            if pwd1 != pwd2:
                raise ValueError("两次输入的密码不一致")

            self._logger.info("尝试注册账号：%s", did or "<empty>")
            self._store.register(doctor_id=did, password=pwd1, organization=org, department=dep)
        except ValueError as ex:
            self._logger.warning("注册失败：%s", str(ex))
            QMessageBox.warning(self, "注册失败", str(ex))
            return
        except Exception:
            self._logger.exception("注册过程中发生未预期错误")
            QMessageBox.critical(self, "错误", "注册失败，请查看日志。")
            return

        QMessageBox.information(self, "成功", "账号已保存。")
        self.accept()
