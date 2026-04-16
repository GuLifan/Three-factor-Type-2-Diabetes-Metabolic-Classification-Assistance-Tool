from __future__ import annotations

# 患者信息页（TTCAS）
# - 负责患者基础信息/体格/检验指标录入
# - 负责调用业务层 EvaluatePatient 完成分型与报告生成
# - 负责导出 HTML/PDF，并写入本地患者归档

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Qt：输入校验/导出打印（PDF）/布局控件
from PySide6.QtCore import Qt
from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QDoubleValidator, QIntValidator, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)
from qfluentwidgets import CheckBox, ComboBox, LineEdit, PrimaryPushButton, PushButton, TextEdit, TitleLabel

# 项目模块：配置/路径/业务/存储/i18n
from ttcas_app.config import AppConfig
from ttcas_app.core_paths import AppPaths
from ttcas_app.domain import EvaluatePatient, PatientInput, PatientReport, compute_bmi, report_to_html
from ttcas_app.storage import PatientArchiveStore
from ttcas_app.domain import DoctorSession
from ttcas_app.ui_i18n import gender_items, ui_text


def _safe_int(text: str) -> int | None:
    t = text.strip()
    if not t:
        return None
    try:
        return int(t)
    except Exception:
        return None


def _safe_float(text: str) -> float | None:
    t = text.strip()
    if not t:
        return None
    try:
        return float(t)
    except Exception:
        return None


class PatientEntryPage(QWidget):
    """
    患者录入/分型/报告页（TTCAS）
    关键目标：
    - 内容很长：外层统一使用滚动容器，避免“窗口小/字体大时无法滚动”
    - 业务逻辑：只调用纯业务层用例（domain.EvaluatePatient），不在 UI 中手写算法
    - 归档：每次评估写入一个 JSON；同 Patient_ID 3 分钟内覆盖最新一次
    """

    def __init__(
        self, *, cfg: AppConfig, paths: AppPaths, logger: logging.Logger, session: DoctorSession, lang: str, parent=None
    ) -> None:
        super().__init__(parent)

        self._cfg = cfg
        self._paths = paths
        self._logger = logger
        self._session = session
        self._lang = lang
        self._store = PatientArchiveStore(paths.patients_dir)
        self._latest_report: PatientReport | None = None

        self._use_case = EvaluatePatient(
            app_version=cfg.app.app_version,
            cluster_version=cfg.model.cluster_version,
            cluster_method=cfg.model.method,
            zscore_mean=cfg.model.zscore_mean,
            zscore_std=cfg.model.zscore_std,
            centroids_z=cfg.model.centroids_z,
            zscore_mean_wwi=cfg.model.zscore_mean_wwi,
            zscore_std_wwi=cfg.model.zscore_std_wwi,
            centroids_z_wwi=cfg.model.centroids_z_wwi,
        )

        self._build_ui()

    def _build_ui(self) -> None:
        content = QWidget()
        content.setObjectName("patient_content")

        self._patient_id = LineEdit()
        self._patient_id.setObjectName("inp_patient_id")
        self._patient_id.setPlaceholderText("必填，例如：ZY01000123456")
        self._patient_id.editingFinished.connect(self._try_autofill_by_patient_id)

        self._patient_name = LineEdit()
        self._patient_name.setPlaceholderText("可选")

        self._birth_y = LineEdit()
        self._birth_m = LineEdit()
        self._birth_d = LineEdit()
        self._birth_y.setPlaceholderText("YYYY")
        self._birth_m.setPlaceholderText("MM")
        self._birth_d.setPlaceholderText("DD")
        self._birth_y.setValidator(QIntValidator(1926, 2100, self))
        self._birth_m.setValidator(QIntValidator(1, 12, self))
        self._birth_d.setValidator(QIntValidator(1, 31, self))
        self._birth_y.editingFinished.connect(self._on_birthdate_changed)
        self._birth_m.editingFinished.connect(self._on_birthdate_changed)
        self._birth_d.editingFinished.connect(self._on_birthdate_changed)
        self._birth_y.editingFinished.connect(lambda: self._guard_int_range(self._birth_y, "出生年份", 1926, 2100))
        self._birth_m.editingFinished.connect(lambda: self._guard_int_range(self._birth_m, "出生月份", 1, 12))
        self._birth_d.editingFinished.connect(lambda: self._guard_int_range(self._birth_d, "出生日", 1, 31))

        self._gender = ComboBox()
        self._set_gender_items(self._lang)

        self._age = LineEdit()
        self._age.setObjectName("inp_age")
        self._age.setPlaceholderText("必填（10~120）")
        self._age.setValidator(QIntValidator(10, 120, self))
        self._age.editingFinished.connect(lambda: self._guard_int_range(self._age, "年龄", 10, 120))

        self._phone = LineEdit()
        self._phone.setPlaceholderText("可选（11位数字）")

        self._sensor = LineEdit()
        self._sensor.setPlaceholderText("可选")

        self._height = LineEdit()
        self._weight = LineEdit()
        self._waist = LineEdit()
        self._height.setObjectName("inp_height")
        self._weight.setObjectName("inp_weight")
        self._waist.setObjectName("inp_waist")
        self._height.setPlaceholderText("cm")
        self._weight.setPlaceholderText("kg")
        self._waist.setPlaceholderText("cm（可选）")
        self._height.setValidator(QDoubleValidator(90.0, 220.0, 2, self))
        self._weight.setValidator(QDoubleValidator(30.0, 200.0, 2, self))
        self._waist.setValidator(QDoubleValidator(30.0, 200.0, 2, self))

        self._bmi_value = QLabel("-")
        self._bmi_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._height.textChanged.connect(self._update_bmi)
        self._weight.textChanged.connect(self._update_bmi)
        self._update_bmi()

        self._height.editingFinished.connect(lambda: self._guard_float_range(self._height, "身高", 90.0, 220.0))
        self._weight.editingFinished.connect(lambda: self._guard_float_range(self._weight, "体重", 30.0, 200.0))
        self._waist.editingFinished.connect(lambda: self._guard_float_range(self._waist, "腰围", 30.0, 200.0))

        self._dm_dx_year = LineEdit()
        self._dm_dx_month = LineEdit()
        self._dm_dx_year.setPlaceholderText("YYYY")
        self._dm_dx_month.setPlaceholderText("MM")
        self._dm_dx_year.setValidator(QIntValidator(1926, 2100, self))
        self._dm_dx_month.setValidator(QIntValidator(1, 12, self))
        self._dm_dx_year.editingFinished.connect(self._on_dm_dx_finished)
        self._dm_dx_month.editingFinished.connect(self._on_dm_dx_finished)

        self._dm_years = LineEdit()
        self._dm_months = LineEdit()
        self._dm_years.setPlaceholderText("年")
        self._dm_months.setPlaceholderText("月")
        self._dm_years.setValidator(QIntValidator(0, 80, self))
        self._dm_months.setValidator(QIntValidator(0, 11, self))
        self._dm_years.editingFinished.connect(self._on_dm_duration_finished)
        self._dm_months.editingFinished.connect(self._on_dm_duration_finished)

        self._fpg = LineEdit()
        self._fpg.setObjectName("inp_fpg")
        self._fpg_unit = ComboBox()
        self._fpg_unit.addItems(["mmol/L", "mg/dL"])
        self._fpg.setValidator(QDoubleValidator(0.5, 60.0, 3, self))
        self._fpg.editingFinished.connect(lambda: self._guard_float_range(self._fpg, "FPG", 0.5, 60.0))

        self._tg = LineEdit()
        self._tg.setObjectName("inp_tg")
        self._tg_unit = ComboBox()
        self._tg_unit.addItems(["mmol/L", "mg/dL"])
        self._tg.setValidator(QDoubleValidator(0.1, 100.0, 3, self))
        self._tg.editingFinished.connect(lambda: self._guard_float_range(self._tg, "TG", 0.1, 100.0))

        self._alb = LineEdit()
        self._scr = LineEdit()
        self._alb.setObjectName("inp_alb")
        self._scr.setObjectName("inp_scr")
        self._scr_unit = ComboBox()
        self._scr_unit.addItems(["umol/L", "mg/dL"])
        self._egfr = LineEdit()
        self._egfr.setPlaceholderText("可留空自动计算")
        self._alb.setValidator(QDoubleValidator(10.0, 60.0, 2, self))
        self._scr.setValidator(QDoubleValidator(0.1, 2000.0, 2, self))
        self._egfr.setValidator(QDoubleValidator(1.0, 200.0, 2, self))
        self._alb.editingFinished.connect(lambda: self._guard_float_range(self._alb, "ALB", 10.0, 60.0))
        self._scr.editingFinished.connect(lambda: self._guard_float_range(self._scr, "Scr", 0.1, 2000.0))
        self._egfr.editingFinished.connect(lambda: self._guard_float_range(self._egfr, "eGFR", 1.0, 200.0))

        self._hba1c = LineEdit()
        self._hba1c.setPlaceholderText("可选（%）")
        self._hba1c.setValidator(QDoubleValidator(3.0, 20.0, 2, self))
        self._hba1c.editingFinished.connect(lambda: self._guard_float_range(self._hba1c, "HbA1c", 3.0, 20.0))

        self._doctor_note = TextEdit()
        self._doctor_note.setPlaceholderText("医师备注（会归档到JSON；导出HTML不含此部分）")
        self._doctor_note.setFixedHeight(90)

        self._result = TextEdit()
        self._result.setReadOnly(True)
        self._result.setPlaceholderText("生成报告后在此处展示摘要…")
        self._result.setFixedHeight(220)

        self._btn_gen_archive = PrimaryPushButton("")
        self._btn_export_html = PushButton("")
        self._btn_export_pdf = PushButton("")
        self._btn_gen_archive.setObjectName("btn_gen_archive")
        self._btn_export_html.setObjectName("btn_export_html")
        self._btn_export_pdf.setObjectName("btn_export_pdf")

        self._btn_gen_archive.clicked.connect(self._on_generate_and_archive_clicked)
        self._btn_export_html.clicked.connect(self._on_export_html_clicked)
        self._btn_export_pdf.clicked.connect(self._on_export_pdf_clicked)
        self._btn_export_html.setEnabled(False)
        self._btn_export_pdf.setEnabled(False)

        self._header = TitleLabel("", content)

        self._box_info = QGroupBox("")
        info_grid = QGridLayout()

        self._lbl_pid = QLabel("")
        self._lbl_name = QLabel("")
        self._lbl_gender = QLabel("")
        self._lbl_dob = QLabel("")
        self._lbl_age = QLabel("")
        self._lbl_phone = QLabel("")
        self._lbl_sensor = QLabel("")

        self._lbl_height = QLabel("")
        self._lbl_weight = QLabel("")
        self._lbl_bmi = QLabel("")
        self._lbl_waist = QLabel("")

        self._lbl_dm_mode = QLabel("")
        self._lbl_dm_value = QLabel("")

        row_birth = QHBoxLayout()
        row_birth.addWidget(self._birth_y)
        row_birth.addWidget(QLabel("-"))
        row_birth.addWidget(self._birth_m)
        row_birth.addWidget(QLabel("-"))
        row_birth.addWidget(self._birth_d)
        row_birth_w = QWidget()
        row_birth_w.setLayout(row_birth)

        info_grid.addWidget(self._lbl_pid, 0, 0)
        info_grid.addWidget(self._patient_id, 0, 1)
        info_grid.addWidget(self._lbl_name, 0, 2)
        info_grid.addWidget(self._patient_name, 0, 3)

        info_grid.addWidget(self._lbl_gender, 1, 0)
        info_grid.addWidget(self._gender, 1, 1)
        info_grid.addWidget(self._lbl_dob, 1, 2)
        info_grid.addWidget(row_birth_w, 1, 3)
        info_grid.addWidget(self._lbl_age, 1, 4)
        info_grid.addWidget(self._age, 1, 5)

        info_grid.addWidget(self._lbl_phone, 2, 0)
        info_grid.addWidget(self._phone, 2, 1)
        info_grid.addWidget(self._lbl_sensor, 2, 2)
        info_grid.addWidget(self._sensor, 2, 3)
        info_grid.setColumnStretch(1, 2)
        info_grid.setColumnStretch(3, 2)
        info_grid.setColumnStretch(5, 1)
        self._box_info.setLayout(info_grid)

        self._box_body = QGroupBox("")
        body_grid = QGridLayout()
        body_grid.addWidget(self._lbl_height, 0, 0)
        body_grid.addWidget(self._height, 0, 1)
        body_grid.addWidget(self._lbl_weight, 0, 2)
        body_grid.addWidget(self._weight, 0, 3)
        body_grid.addWidget(self._lbl_bmi, 0, 4)
        body_grid.addWidget(self._bmi_value, 0, 5)
        body_grid.addWidget(self._lbl_waist, 0, 6)
        body_grid.addWidget(self._waist, 0, 7)
        body_grid.setColumnStretch(1, 1)
        body_grid.setColumnStretch(3, 1)
        body_grid.setColumnStretch(7, 1)
        self._box_body.setLayout(body_grid)

        self._box_history = QGroupBox("")
        hist_grid = QGridLayout()

        self._dm_dx_row = QWidget()
        dm_dx_lay = QHBoxLayout()
        dm_dx_lay.setContentsMargins(0, 0, 0, 0)
        dm_dx_lay.addWidget(self._dm_dx_year)
        dm_dx_lay.addWidget(QLabel("-"))
        dm_dx_lay.addWidget(self._dm_dx_month)
        dm_dx_lay.addStretch(1)
        self._dm_dx_row.setLayout(dm_dx_lay)

        self._dm_duration_row = QWidget()
        dm_dur_lay = QHBoxLayout()
        dm_dur_lay.setContentsMargins(0, 0, 0, 0)
        self._lbl_dm_year_unit = QLabel("")
        self._lbl_dm_month_unit = QLabel("")
        dm_dur_lay.addWidget(self._dm_years)
        dm_dur_lay.addWidget(self._lbl_dm_year_unit)
        dm_dur_lay.addWidget(self._dm_months)
        dm_dur_lay.addWidget(self._lbl_dm_month_unit)
        dm_dur_lay.addStretch(1)
        self._dm_duration_row.setLayout(dm_dur_lay)

        hist_grid.addWidget(self._lbl_dm_mode, 0, 0)
        hist_grid.addWidget(self._dm_dx_row, 0, 1)
        hist_grid.addWidget(self._lbl_dm_value, 0, 2)
        hist_grid.addWidget(self._dm_duration_row, 0, 3)

        self._complications: dict[str, CheckBox] = {}
        self._comp_other = CheckBox("")
        self._comp_other_text = LineEdit()
        self._comp_other_text.setEnabled(False)
        self._comp_other.toggled.connect(self._on_other_toggled)

        comp_grid = QGridLayout()
        comp_grid.setContentsMargins(0, 0, 0, 0)
        keys = ["DN", "DR", "DPN", "DPVD", "KETOSIS", "HTN", "CHD", "NAFLD"]
        r = 0
        c = 0
        for k in keys:
            cb = CheckBox("")
            self._complications[k] = cb
            comp_grid.addWidget(cb, r, c)
            c += 1
            if c >= 2:
                r += 1
                c = 0
        comp_grid.addWidget(self._comp_other, r, 0)
        comp_grid.addWidget(self._comp_other_text, r, 1)

        comp_w = QWidget()
        comp_w.setLayout(comp_grid)
        hist_grid.addWidget(comp_w, 1, 0, 1, 5)
        hist_grid.setColumnStretch(1, 2)
        hist_grid.setColumnStretch(3, 2)
        self._box_history.setLayout(hist_grid)

        self._box_labs = QGroupBox("")
        lab_grid = QGridLayout()
        self._lbl_fpg = QLabel("")
        self._lbl_tg = QLabel("")
        self._lbl_alb = QLabel("")
        self._lbl_scr = QLabel("")
        self._lbl_egfr = QLabel("")
        self._lbl_hba1c = QLabel("")

        lab_grid.addWidget(self._lbl_fpg, 0, 0)
        lab_grid.addWidget(self._fpg, 0, 1)
        lab_grid.addWidget(self._fpg_unit, 0, 2)
        lab_grid.addWidget(self._lbl_tg, 0, 3)
        lab_grid.addWidget(self._tg, 0, 4)
        lab_grid.addWidget(self._tg_unit, 0, 5)

        lab_grid.addWidget(self._lbl_alb, 1, 0)
        lab_grid.addWidget(self._alb, 1, 1)
        lab_grid.addWidget(QLabel(""), 1, 2)
        lab_grid.addWidget(self._lbl_scr, 1, 3)
        lab_grid.addWidget(self._scr, 1, 4)
        lab_grid.addWidget(self._scr_unit, 1, 5)

        lab_grid.addWidget(self._lbl_egfr, 2, 0)
        lab_grid.addWidget(self._egfr, 2, 1)
        lab_grid.addWidget(QLabel("mL/min/1.73m²"), 2, 2)
        lab_grid.addWidget(self._lbl_hba1c, 2, 3)
        lab_grid.addWidget(self._hba1c, 2, 4)
        lab_grid.addWidget(QLabel("%"), 2, 5)
        lab_grid.setColumnStretch(1, 1)
        lab_grid.setColumnStretch(4, 1)
        self._box_labs.setLayout(lab_grid)

        action_row = QHBoxLayout()
        action_row.addWidget(self._btn_gen_archive)
        action_row.addWidget(self._btn_export_html)
        action_row.addWidget(self._btn_export_pdf)
        action_row.addStretch(1)

        self._box_note = QGroupBox("")
        note_lay = QVBoxLayout()
        note_lay.addWidget(self._doctor_note)
        self._box_note.setLayout(note_lay)

        self._box_result = QGroupBox("")
        result_lay = QVBoxLayout()
        result_lay.addWidget(self._result)
        self._box_result.setLayout(result_lay)

        v = QVBoxLayout()
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(12)
        v.addWidget(self._header)
        v.addWidget(self._box_info)
        v.addWidget(self._box_body)
        v.addWidget(self._box_history)
        v.addWidget(self._box_labs)
        v.addLayout(action_row)
        v.addWidget(self._box_note)
        v.addWidget(self._box_result)
        v.addStretch(1)
        content.setLayout(v)

        scroll = QScrollArea()
        scroll.setObjectName("patient_scroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.viewport().setAutoFillBackground(False)

        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)

        self.setStyleSheet(
            """
            QWidget#patient_content { background: transparent; color: palette(text); }
            QScrollArea#patient_scroll { background: transparent; border: none; }
            QScrollArea#patient_scroll > QWidget > QWidget { background: transparent; }
            """
        )

        self.apply_language(self._lang)

    def apply_language(self, lang: str) -> None:
        self._lang = lang

        self._header.setText(ui_text("patient_title", lang))

        self._box_info.setTitle(ui_text("section_basic", lang))
        self._lbl_pid.setText(ui_text("pid_label", lang) + "*")
        self._lbl_name.setText(ui_text("name_label", lang))
        self._lbl_gender.setText(ui_text("gender_label", lang) + "*")
        self._lbl_dob.setText(ui_text("dob_label", lang))
        self._lbl_age.setText(ui_text("age_label", lang) + "*")
        self._lbl_phone.setText(ui_text("phone_label", lang))
        self._lbl_sensor.setText(ui_text("sensor_label", lang))

        self._box_body.setTitle(ui_text("section_body", lang))
        self._lbl_height.setText(ui_text("height_label", lang) + "*")
        self._lbl_weight.setText(ui_text("weight_label", lang) + "*")
        self._lbl_bmi.setText(ui_text("bmi_label", lang))
        self._lbl_waist.setText(ui_text("waist_label", lang))

        self._box_history.setTitle(ui_text("section_history", lang))
        self._lbl_dm_mode.setText(ui_text("dm_dx_date_label", lang))
        self._lbl_dm_value.setText(ui_text("dm_duration_label", lang))
        self._lbl_dm_year_unit.setText(ui_text("dm_year_label", lang))
        self._lbl_dm_month_unit.setText(ui_text("dm_month_label", lang))

        self._box_labs.setTitle(ui_text("section_labs", lang))
        self._lbl_fpg.setText(ui_text("fpg_label", lang) + "*")
        self._lbl_tg.setText(ui_text("tg_label", lang) + "*")
        self._lbl_alb.setText(ui_text("alb_label", lang) + "*")
        self._lbl_scr.setText(ui_text("scr_label", lang) + "*")
        self._lbl_egfr.setText(ui_text("egfr_label", lang))
        self._lbl_hba1c.setText(ui_text("hba1c_label", lang))

        self._box_note.setTitle(ui_text("note_title", lang))
        self._box_result.setTitle(ui_text("result_title", lang))

        self._btn_gen_archive.setText(ui_text("gen_archive_btn", lang))
        self._btn_export_html.setText(ui_text("export_html_btn", lang))
        self._btn_export_pdf.setText(ui_text("print_pdf_btn", lang))

        self._comp_other.setText("其他 Other" if lang == "zh" else "Other")
        self._comp_other_text.setPlaceholderText("填写其他内容 Specify here." if lang == "zh" else "Specify here.")

        comp_map = self._complication_label_map(lang)
        for k, cb in self._complications.items():
            cb.setText(comp_map.get(k, k))

        self._set_gender_items(lang)
        self._sync_dm_fields()

    def _set_gender_items(self, lang: str) -> None:
        current = self._gender_value()
        self._gender.clear()
        for value, display in gender_items(lang):
            self._gender.addItem(display, value)
        if current in ("男", "女"):
            for i in range(self._gender.count()):
                if self._gender.itemData(i) == current:
                    self._gender.setCurrentIndex(i)
                    break

    def _gender_value(self) -> str:
        try:
            v = self._gender.currentData()
        except Exception:
            v = None
        if isinstance(v, str) and v in ("男", "女"):
            return v
        t = self._gender.currentText().strip()
        return "女" if "女" in t or "female" in t.lower() else "男"

    def _guard_int_range(self, widget: LineEdit, label: str, lo: int, hi: int) -> None:
        raw = widget.text().strip()
        if not raw:
            return
        v = _safe_int(raw)
        if v is None:
            QMessageBox.warning(self, "输入错误", f"{label}只能填写数字，请检查是否包含非法字符")
            widget.setFocus()
            widget.selectAll()
            return
        if v < lo or v > hi:
            QMessageBox.warning(self, "输入错误", f"{label}合法范围：{lo}~{hi}")
            widget.setFocus()
            widget.selectAll()

    def _guard_float_range(self, widget: LineEdit, label: str, lo: float, hi: float) -> None:
        raw = widget.text().strip()
        if not raw:
            return
        v = _safe_float(raw)
        if v is None:
            QMessageBox.warning(self, "输入错误", f"{label}只能填写数字，请检查是否包含非法字符")
            widget.setFocus()
            widget.selectAll()
            return
        if v < lo or v > hi:
            QMessageBox.warning(self, "输入错误", f"{label}合法范围：{lo:g}~{hi:g}")
            widget.setFocus()
            widget.selectAll()

    def _update_bmi(self) -> None:
        h = _safe_float(self._height.text())
        w = _safe_float(self._weight.text())
        if h is None or w is None:
            self._bmi_value.setText("-")
            return
        try:
            self._bmi_value.setText(str(compute_bmi(float(h), float(w))))
        except Exception:
            self._bmi_value.setText("-")

    def _dm_duration_from_dx(self, year: int, month: int | None) -> tuple[int, int]:
        today = date.today()
        if year < 1926:
            raise ValueError("年份必须为1926年及以后")
        if month is None:
            dx = date(int(year), 1, 1)
            months_total = (today.year - dx.year) * 12 + (today.month - dx.month)
            years_rounded = int(round(months_total / 12.0))
            return max(0, years_rounded), 0
        if month < 1 or month > 12:
            raise ValueError("月份必须在 1~12 之间")
        dx = date(int(year), int(month), 1)
        months_total = (today.year - dx.year) * 12 + (today.month - dx.month)
        if months_total < 0:
            raise ValueError("首次确诊年月不能晚于当前年月")
        return months_total // 12, months_total % 12

    def _dx_from_dm_duration(self, years: int, months: int | None) -> tuple[int, int | None]:
        today = date.today()
        if years < 0 or years > 80:
            raise ValueError("病程年不合法")
        m = int(months) if months is not None else 0
        if m < 0 or m > 11:
            raise ValueError("病程月必须在 0~11 之间")
        total_months = years * 12 + m
        dx_year = today.year
        dx_month = today.month
        dx_year -= total_months // 12
        dx_month -= total_months % 12
        while dx_month <= 0:
            dx_month += 12
            dx_year -= 1
        if dx_year < 1926:
            dx_year = 1926
        if months is None:
            return dx_year, None
        return dx_year, dx_month

    def _on_dm_dx_finished(self) -> None:
        try:
            y = _safe_int(self._dm_dx_year.text())
            m = _safe_int(self._dm_dx_month.text())
            if y is None:
                return
            years, months = self._dm_duration_from_dx(int(y), int(m) if m is not None else None)
        except Exception as ex:
            QMessageBox.warning(self, "输入错误", str(ex))
            return

        with QSignalBlocker(self._dm_years), QSignalBlocker(self._dm_months):
            self._dm_years.setText(str(years))
            if self._dm_dx_month.text().strip():
                self._dm_months.setText(str(months))
            else:
                self._dm_months.setText("")

    def _on_dm_duration_finished(self) -> None:
        if self._dm_dx_year.text().strip():
            return
        y = _safe_int(self._dm_years.text())
        m = _safe_int(self._dm_months.text())
        if y is None and m is None:
            with QSignalBlocker(self._dm_dx_year), QSignalBlocker(self._dm_dx_month):
                self._dm_dx_year.setText("")
                self._dm_dx_month.setText("")
            return

        try:
            years = int(y) if y is not None else 0
            months_val: int | None = int(m) if m is not None else None
            dx_y, dx_m = self._dx_from_dm_duration(years, months_val)
        except Exception as ex:
            QMessageBox.warning(self, "输入错误", str(ex))
            return

        with QSignalBlocker(self._dm_dx_year), QSignalBlocker(self._dm_dx_month):
            self._dm_dx_year.setText(str(dx_y))
            self._dm_dx_month.setText(str(dx_m) if dx_m is not None else "")

    def _sync_dm_fields(self) -> None:
        if self._dm_dx_year.text().strip():
            self._on_dm_dx_finished()
        elif self._dm_years.text().strip() or self._dm_months.text().strip():
            self._on_dm_duration_finished()

    def _on_other_toggled(self, checked: bool) -> None:
        self._comp_other_text.setEnabled(bool(checked))
        if not checked:
            self._comp_other_text.setText("")

    def _complication_label_map(self, lang: str) -> dict[str, str]:
        if lang == "en":
            return {
                "DN": "DN Diabetic Nephropathy",
                "DR": "DR Diabetic Retinopathy",
                "DPN": "DPN Diabetic Peripheral Neuropathy",
                "DPVD": "DPVD Diabetic Peripheral Vascular Disease",
                "KETOSIS": "Ketosis",
                "HTN": "Hypertension (HTN)",
                "CHD": "CHD Coronary Heart Disease",
                "NAFLD": "NAFLD Non-alcoholic Fatty Liver Disease",
            }
        return {
            "DN": "糖尿病肾病 DN",
            "DR": "视网膜病变 DR",
            "DPN": "周围神经病变 DPN",
            "DPVD": "周围血管病变 DPVD",
            "KETOSIS": "酮症/倾向 Ketosis",
            "HTN": "高血压 Hypertension",
            "CHD": "冠心病 CHD",
            "NAFLD": "脂肪肝 NAFLD",
        }

    def _on_birthdate_changed(self) -> None:
        raw_y = self._birth_y.text().strip()
        raw_m = self._birth_m.text().strip()
        raw_d = self._birth_d.text().strip()

        by = _safe_int(raw_y) if raw_y else None
        bm = _safe_int(raw_m) if raw_m else None
        bd = _safe_int(raw_d) if raw_d else None

        if raw_y and by is None:
            QMessageBox.warning(self, "输入错误", "出生年份只能填写数字")
            self._birth_y.setFocus()
            self._birth_y.selectAll()
            return
        if raw_m and bm is None:
            QMessageBox.warning(self, "输入错误", "出生月份只能填写数字")
            self._birth_m.setFocus()
            self._birth_m.selectAll()
            return
        if raw_d and bd is None:
            QMessageBox.warning(self, "输入错误", "出生日只能填写数字")
            self._birth_d.setFocus()
            self._birth_d.selectAll()
            return

        if by is None and bm is None and bd is None:
            return
        if by is None or bm is None or bd is None:
            return
        try:
            bdate = date(by, bm, bd)
        except Exception:
            QMessageBox.warning(self, "输入错误", "出生日期不合法")
            return
        if bdate < date(1926, 1, 1):
            QMessageBox.warning(self, "输入错误", "出生日期不能早于1926年1月1日")
            return
        today = date.today()
        age = today.year - bdate.year - (1 if (today.month, today.day) < (bdate.month, bdate.day) else 0)
        if age > 0:
            self._age.setText(str(age))

    def _try_autofill_by_patient_id(self) -> None:
        pid = self._patient_id.text().strip()
        if not pid:
            return
        found = self._store.find_latest_record_for_patient(pid)
        if found is None:
            return
        file_name, record = found
        record["_source_file"] = file_name
        self.apply_record_dict(record)

    def _build_payload(self) -> PatientInput:
        def parse_int_field(label: str, raw: str, *, required: bool) -> int | None:
            t = (raw or "").strip()
            if not t:
                if required:
                    raise ValueError(f"{label}必填")
                return None
            v = _safe_int(t)
            if v is None:
                raise ValueError(f"{label}只能填写数字，请检查是否包含非法字符")
            return v

        def parse_float_field(label: str, raw: str, *, required: bool) -> float | None:
            t = (raw or "").strip()
            if not t:
                if required:
                    raise ValueError(f"{label}必填")
                return None
            v = _safe_float(t)
            if v is None:
                raise ValueError(f"{label}只能填写数字，请检查是否包含非法字符")
            return v

        pid = self._patient_id.text().strip()
        name = self._patient_name.text().strip() or None

        by = parse_int_field("出生年份", self._birth_y.text(), required=False)
        bm = parse_int_field("出生月份", self._birth_m.text(), required=False)
        bd = parse_int_field("出生日期", self._birth_d.text(), required=False)

        gender = self._gender_value()

        age = parse_int_field("年龄", self._age.text(), required=True)

        phone = self._phone.text().strip() or None
        sensor = self._sensor.text().strip() or None

        height = parse_float_field("身高", self._height.text(), required=True)
        weight = parse_float_field("体重", self._weight.text(), required=True)

        waist = parse_float_field("腰围", self._waist.text(), required=False)

        dm_dx_y = _safe_int(self._dm_dx_year.text())
        dm_dx_m = _safe_int(self._dm_dx_month.text()) if self._dm_dx_month.text().strip() else None
        dm_y = _safe_int(self._dm_years.text())
        dm_m = _safe_int(self._dm_months.text())

        if dm_dx_y is not None:
            years, months = self._dm_duration_from_dx(int(dm_dx_y), int(dm_dx_m) if dm_dx_m is not None else None)
            dm_y = years
            dm_m = months if dm_dx_m is not None else 0
        elif dm_y is not None or dm_m is not None:
            years = int(dm_y) if dm_y is not None else 0
            months_val: int | None = int(dm_m) if dm_m is not None else None
            dx_y, dx_m = self._dx_from_dm_duration(years, months_val)
            dm_dx_y = dx_y
            dm_dx_m = dx_m
            dm_y = years
            dm_m = int(dm_m) if dm_m is not None else 0

        fpg = parse_float_field("FPG", self._fpg.text(), required=True)
        tg = parse_float_field("TG", self._tg.text(), required=True)
        alb = parse_float_field("ALB", self._alb.text(), required=True)
        scr = parse_float_field("Scr", self._scr.text(), required=True)

        egfr = parse_float_field("eGFR", self._egfr.text(), required=False)
        hba1c = parse_float_field("HbA1c", self._hba1c.text(), required=False)

        comps: dict[str, bool] = {k: bool(cb.isChecked()) for k, cb in self._complications.items()}
        other_text = self._comp_other_text.text().strip() if self._comp_other.isChecked() else ""

        return PatientInput(
            patient_id=pid,
            patient_name=name,
            birth_year=by,
            birth_month=bm,
            birth_day=bd,
            gender=gender,
            age_years=int(age),
            phone_number=phone,
            cgm_sensor_id=sensor,
            height_cm=float(height),
            weight_kg=float(weight),
            waist_cm=float(waist) if waist is not None else None,
            dm_duration_years=dm_y,
            dm_duration_months=dm_m,
            dm_dx_year=dm_dx_y,
            dm_dx_month=dm_dx_m,
            complications=comps or None,
            complications_other=other_text or None,
            fpg_value=float(fpg),
            fpg_unit=self._fpg_unit.currentText(),
            tg_value=float(tg),
            tg_unit=self._tg_unit.currentText(),
            alb_g_l=float(alb),
            scr_value=float(scr),
            scr_unit=self._scr_unit.currentText(),
            egfr_value=float(egfr) if egfr is not None else None,
            hba1c_percent=float(hba1c) if hba1c is not None else None,
        )

    def _render_report_summary(self, report: PatientReport) -> str:
        ph = report.phenotype or {}
        egfr = ph.get("tyg_egfr_alb", {}) or {}
        wwi = ph.get("tyg_wwi_alb", {}) or {}

        lines: list[str] = []
        if self._lang == "en":
            lines.append(f"Generated at: {report.generated_at}")
            lines.append(f"Operator: {report.operator_doctor_id}")
            lines.append(f"Version: App {report.app_version} / Model {report.model_version} / Method {report.cluster_method}")
            if report.notes:
                lines.append("Notes: " + "; ".join(report.notes))
            lines.append("")
            lines.append("Derived:")
            lines.append(f"- BMI = {report.derived.bmi}")
            lines.append(f"- TyG = {report.derived.tyg}")
            lines.append(f"- eGFR = {report.derived.egfr}")
            lines.append(f"- WWI = {report.derived.wwi if report.derived.wwi is not None else 'N/A'}")
            lines.append("")
            lines.append("TyG-WWI-ALB:")
            if wwi.get("method") == "unavailable":
                lines.append(f"- Unavailable: {wwi.get('reason')}")
            else:
                lines.append(f"- Type {wwi.get('phenotype_code')}: {wwi.get('phenotype_en')} ({wwi.get('phenotype_cn')})")
                lines.append(f"- Explanation: {'; '.join(wwi.get('key_explanations') or [])}")
                lines.append(f"- Tips: {wwi.get('clinical_tips') or ''}")
            lines.append("")
            lines.append("TyG-eGFR-ALB:")
            lines.append(f"- Type {egfr.get('phenotype_code')}: {egfr.get('phenotype_en')} ({egfr.get('phenotype_cn')})")
            lines.append(f"- Explanation: {'; '.join(egfr.get('key_explanations') or [])}")
            lines.append(f"- Tips: {egfr.get('clinical_tips') or ''}")
        else:
            lines.append(f"生成时间：{report.generated_at}")
            lines.append(f"操作者：{report.operator_doctor_id}")
            lines.append(f"版本：App {report.app_version} / Model {report.model_version} / Method {report.cluster_method}")
            if report.notes:
                lines.append("说明：" + "；".join(report.notes))
            lines.append("")
            lines.append("衍生指标：")
            lines.append(f"- BMI = {report.derived.bmi}")
            lines.append(f"- TyG = {report.derived.tyg}")
            lines.append(f"- eGFR = {report.derived.egfr}")
            lines.append(f"- WWI = {report.derived.wwi if report.derived.wwi is not None else '未录入'}")
            lines.append("")
            lines.append("TyG-WWI-ALB：")
            if wwi.get("method") == "unavailable":
                lines.append(f"- 不可用：{wwi.get('reason')}")
            else:
                lines.append(f"- 表型{wwi.get('phenotype_code')}：{wwi.get('phenotype_cn')} / {wwi.get('phenotype_en')}")
                lines.append(f"- 解释：{'；'.join(wwi.get('key_explanations') or [])}")
                lines.append(f"- 提示：{wwi.get('clinical_tips') or ''}")
            lines.append("")
            lines.append("TyG-eGFR-ALB：")
            lines.append(f"- 表型{egfr.get('phenotype_code')}：{egfr.get('phenotype_cn')} / {egfr.get('phenotype_en')}")
            lines.append(f"- 解释：{'；'.join(egfr.get('key_explanations') or [])}")
            lines.append(f"- 提示：{egfr.get('clinical_tips') or ''}")
        return "\n".join(lines)

    def _on_generate_and_archive_clicked(self) -> None:
        try:
            payload = self._build_payload()
            note = self._doctor_note.toPlainText().strip() or None
            self._logger.info("生成并归档：%s", payload.patient_id)
            report = self._use_case.execute(
                payload=payload, operator_doctor_id=self._session.doctor_id, doctor_note=note
            )
            saved = self._store.save_report(report)
        except ValueError as ex:
            QMessageBox.warning(self, "输入错误", str(ex))
            return
        except Exception:
            self._logger.exception("生成并归档失败")
            QMessageBox.critical(self, "错误", "生成并归档失败，请查看日志。")
            return

        self._latest_report = report
        self._btn_export_html.setEnabled(True)
        self._btn_export_pdf.setEnabled(True)
        self._result.setPlainText(self._render_report_summary(report) + f"\n\n归档文件 Archive:\n- {saved.name}")

    def _on_export_html_clicked(self) -> None:
        if self._latest_report is None:
            QMessageBox.information(self, "提示", "请先生成报告。")
            return
        html = report_to_html(self._latest_report)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested = f"{self._latest_report.input.patient_id}+{ts}.html"
        path, _ = QFileDialog.getSaveFileName(self, "导出 HTML / Export HTML", suggested, "HTML (*.html)")
        if not path:
            return
        try:
            Path(path).write_text(html, encoding="utf-8")
            self._logger.info("导出HTML：%s", path)
            QMessageBox.information(self, "成功", "已导出 HTML。")
        except Exception:
            self._logger.exception("写入 HTML 报告失败")
            QMessageBox.critical(self, "错误", "写入失败，请查看日志。")

    def _on_export_pdf_clicked(self) -> None:
        if self._latest_report is None:
            QMessageBox.information(self, "提示", "请先生成报告。")
            return
        doc = QTextDocument(self)
        doc.setHtml(report_to_html(self._latest_report))

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suggested = f"{self._latest_report.input.patient_id}+{ts}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "导出 PDF / Export PDF", suggested, "PDF (*.pdf)")
        if not path:
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        doc.print_(printer)
        self._logger.info("导出PDF：%s", path)
        QMessageBox.information(self, "成功", "已导出 PDF。")

    def apply_record_dict(self, record: dict[str, Any]) -> None:
        """
        从归档记录回填到表单：
        - 支持历史归档结构
        - 只做“最常用字段”回填，避免因历史字段差异导致 UI 崩溃
        """

        inp = record.get("input") or record
        if not isinstance(inp, dict):
            return

        def s(key: str) -> str:
            v = inp.get(key)
            return "" if v is None else str(v)

        self._patient_id.setText(s("patient_id"))
        self._patient_name.setText(s("patient_name"))
        self._birth_y.setText(s("birth_year"))
        self._birth_m.setText(s("birth_month"))
        self._birth_d.setText(s("birth_day"))

        g = s("gender").strip()
        if g in ("男", "女"):
            for i in range(self._gender.count()):
                if self._gender.itemData(i) == g:
                    self._gender.setCurrentIndex(i)
                    break
        self._age.setText(s("age_years"))
        self._phone.setText(s("phone_number"))
        self._sensor.setText(s("cgm_sensor_id"))

        self._height.setText(s("height_cm"))
        self._weight.setText(s("weight_kg"))
        self._waist.setText(s("waist_cm"))
        self._update_bmi()

        dx_y = s("dm_dx_year").strip()
        dx_m = s("dm_dx_month").strip()
        if dx_y:
            self._dm_dx_year.setText(dx_y)
            self._dm_dx_month.setText(dx_m)
            self._dm_years.setText("")
            self._dm_months.setText("")
        else:
            self._dm_years.setText(s("dm_duration_years"))
            self._dm_months.setText(s("dm_duration_months"))
            self._dm_dx_year.setText("")
            self._dm_dx_month.setText("")
        self._sync_dm_fields()

        self._fpg.setText(s("fpg_value"))
        fpg_u = s("fpg_unit").strip()
        if fpg_u in ("mmol/L", "mg/dL"):
            self._fpg_unit.setCurrentText(fpg_u)

        self._tg.setText(s("tg_value"))
        tg_u = s("tg_unit").strip()
        if tg_u in ("mmol/L", "mg/dL"):
            self._tg_unit.setCurrentText(tg_u)

        self._alb.setText(s("alb_g_l"))
        self._scr.setText(s("scr_value"))
        scr_u = s("scr_unit").strip()
        if scr_u in ("umol/L", "mg/dL"):
            self._scr_unit.setCurrentText(scr_u)

        self._egfr.setText(s("egfr_value"))
        self._hba1c.setText(s("hba1c_percent"))

        comp_dict = inp.get("complications") if isinstance(inp, dict) else None
        if isinstance(comp_dict, dict):
            for k, cb in self._complications.items():
                cb.setChecked(bool(comp_dict.get(k)))
            other_txt = str(inp.get("complications_other") or "").strip()
            self._comp_other.setChecked(bool(other_txt))
            self._comp_other_text.setText(other_txt)
        else:
            mapping = {
                "DN": bool(inp.get("dn")) if isinstance(inp, dict) else False,
                "DR": bool(inp.get("dr")) if isinstance(inp, dict) else False,
                "DPN": bool(inp.get("dpn")) if isinstance(inp, dict) else False,
                "DPVD": bool(inp.get("dpvd")) if isinstance(inp, dict) else False,
                "KETOSIS": bool(inp.get("ketosis")) if isinstance(inp, dict) else False,
                "HTN": bool(inp.get("hypertension")) if isinstance(inp, dict) else False,
                "CHD": bool(inp.get("chd")) if isinstance(inp, dict) else False,
                "NAFLD": bool(inp.get("nafld")) if isinstance(inp, dict) else False,
            }
            for k, cb in self._complications.items():
                cb.setChecked(bool(mapping.get(k)))
            other_flag = bool(inp.get("other_comorbidity")) if isinstance(inp, dict) else False
            other_text = str(inp.get("other_comorbidity_text") or "").strip() if isinstance(inp, dict) else ""
            self._comp_other.setChecked(bool(other_flag or other_text))
            self._comp_other_text.setText(other_text)
        self._on_other_toggled(self._comp_other.isChecked())

        note = record.get("doctor_note") or record.get("doctorNote") or ""
        self._doctor_note.setPlainText(str(note))

        derived = record.get("derived") or {}
        ph = record.get("phenotype") or {}
        if isinstance(derived, dict) and isinstance(ph, dict):
            try:
                payload = self._build_payload()
                r = PatientReport(
                    input=payload,
                    derived=self._use_case.execute(
                        payload=payload,
                        operator_doctor_id=self._session.doctor_id,
                        doctor_note=self._doctor_note.toPlainText().strip() or None,
                    ).derived,
                    phenotype=ph,
                    operator_doctor_id=str(record.get("operator_doctor_id") or self._session.doctor_id),
                    doctor_note=self._doctor_note.toPlainText().strip() or None,
                    generated_at=str(record.get("generated_at") or record.get("generatedAt") or ""),
                    app_version=str(record.get("app_version") or self._cfg.app.app_version),
                    model_version=str(record.get("model_version") or self._cfg.model.cluster_version),
                    cluster_method=str(record.get("cluster_method") or self._cfg.model.method),
                    notes=list(record.get("notes") or []),
                )
                self._latest_report = r
                self._btn_export_html.setEnabled(True)
                self._btn_export_pdf.setEnabled(True)
                self._result.setPlainText(self._render_report_summary(r))
            except Exception:
                self._latest_report = None
                self._btn_export_html.setEnabled(False)
                self._btn_export_pdf.setEnabled(False)
                self._result.setPlainText("已回填表单。若需重新生成报告，请点击“生成报告”。")
        else:
            self._latest_report = None
            self._btn_export_html.setEnabled(False)
            self._btn_export_pdf.setEnabled(False)
            self._result.setPlainText("已回填表单。若需重新生成报告，请点击“生成报告”。")
