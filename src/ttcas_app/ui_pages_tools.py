from __future__ import annotations

# 常用计算器页（TTCAS）
# - 该页面包含一组“边输边算”的小工具：BMI/WWI、病程、eGFR、单位换算等
# - CGM 动态指标计算耗时较长，因此放到后台线程执行，避免 UI 卡死

import logging
from datetime import date
from pathlib import Path

# Qt Core：线程/信号/定时器/鼠标事件标志等
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
# Qt Gui：输入校验器（限制输入范围/格式）
from PySide6.QtGui import QDoubleValidator, QIntValidator
# Qt Widgets：布局、容器、弹窗、文件选择对话框等
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
# QFluentWidgets：更接近 Win11 风格的输入框/按钮/文本框
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton, PushButton, TextEdit

# CGM 业务层：计算函数 + 可识别的输入异常类型
from ttcas_app.cgm_metrics import (
    CgmCancelledError,
    CgmFileNotFoundError,
    CgmHeaderMismatchError,
    compute_cgm_metrics_from_file,
)
from ttcas_app.domain import (
    compute_bmi,
    compute_crcl_cockcroft_gault,
    compute_egfr_ckd_epi_2009,
    compute_egfr_mdrd_4var,
    compute_wwi,
    fpg_to_mg_dl,
    scr_to_mg_dl,
)


def _safe_int(text: str) -> int | None:
    # 将输入框文本安全转换为 int（失败返回 None）
    t = text.strip()
    if not t:
        return None
    try:
        return int(t)
    except Exception:
        return None


def _safe_float(text: str) -> float | None:
    # 将输入框文本安全转换为 float（失败返回 None）
    t = text.strip()
    if not t:
        return None
    try:
        return float(t)
    except Exception:
        return None


def _months_between(d1: date, d2: date) -> int:
    # 两个日期之间的“月数”粗略估算：
    # - 先算整月差
    # - 再用天数差/30 作为小数补偿，并四舍五入
    if d2 < d1:
        d1, d2 = d2, d1
    base = (d2.year - d1.year) * 12 + (d2.month - d1.month)
    frac = (d2.day - d1.day) / 30.0
    return int(round(base + frac))


class _CgmWorker(QObject):
    # 后台 worker：
    # - 在 QThread 中运行 compute_cgm_metrics_from_file
    # - 通过信号把结果/错误带回 UI 线程
    finished = Signal(int, str, dict)
    failed = Signal(int, str, str, str)
    cancelled = Signal(int, str)

    def __init__(self, file_path: str, job_id: int) -> None:
        super().__init__()
        # file_path：要计算的 Excel/CSV 路径
        self._file_path = file_path
        # job_id：用于忽略“旧任务回调”（用户切文件后，旧任务完成也不应覆盖新任务输出）
        self._job_id = job_id

    def run(self) -> None:
        # 后台线程取消检查：
        # - UI 发起 thread.requestInterruption()
        # - 业务层在关键步骤调用 cancel_check()
        def cancel_check() -> None:
            t = QThread.currentThread()
            if t is not None and t.isInterruptionRequested():
                raise CgmCancelledError()

        try:
            # 计算入口：内部会做文件存在性与表头校验
            res = compute_cgm_metrics_from_file(self._file_path, cancel_check=cancel_check)
        except CgmCancelledError:
            # 被用户切文件/中断：不算错误，只回传 cancelled
            self.cancelled.emit(self._job_id, self._file_path)
            return
        except CgmFileNotFoundError as ex:
            # 文件不存在：UI 需要弹窗提示并结束任务
            self.failed.emit(self._job_id, self._file_path, "file_not_found", str(ex))
            return
        except CgmHeaderMismatchError as ex:
            # 表头不匹配：UI 需要弹窗提示并结束任务
            self.failed.emit(self._job_id, self._file_path, "header_mismatch", str(ex))
            return
        except Exception as ex:
            # 其他未知异常：记录日志并在输出框显示错误信息
            self.failed.emit(self._job_id, self._file_path, "unknown", str(ex))
            return
        # 成功：回传指标字典
        self.finished.emit(self._job_id, self._file_path, res)


class ToolsPage(QWidget):
    """
    常用计算器页面（TTCAS）
    - 外层统一滚动容器
    - CGM 计算放后台线程，避免界面卡死
    """

    def __init__(self, *, logger: logging.Logger, lang: str, parent=None) -> None:
        super().__init__(parent)
        # logger：主窗口传入的统一日志实例
        self._logger = logger
        # lang：当前 UI 语言（zh/en）
        self._lang = lang
        # 任务列表：用于清理已结束线程，避免引用泄漏
        self._cgm_jobs: list[tuple[QThread, QObject]] = []
        self._last_cgm_thread: QThread | None = None
        self._last_cgm_worker: QObject | None = None
        # “当前任务”信息：用于日志与 UI 展示
        self._cgm_current_file_path: str | None = None
        self._cgm_current_thread: QThread | None = None
        self._cgm_current_job_id: int | None = None
        # job_seq：自增任务号，确保每次启动计算都有唯一 id
        self._cgm_job_seq = 0
        # job_id -> thread：用于在回调里关闭对应 thread（避免跨线程更新导致崩溃）
        self._cgm_job_threads: dict[int, QThread] = {}
        # 语言延迟刷新：如果正在跑 CGM，避免重建 UI 造成引用失效
        self._pending_lang_refresh: str | None = None

        self._content = QWidget()
        self._content.setObjectName("tools_content")
        self._v = QVBoxLayout()
        self._v.setContentsMargins(12, 12, 12, 12)
        self._v.setSpacing(12)
        self._content.setLayout(self._v)

        scroll = QScrollArea()
        scroll.setObjectName("tools_scroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._content)
        scroll.viewport().setAutoFillBackground(False)

        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)

        self.setStyleSheet(
            """
            QWidget#tools_content { background: transparent; color: palette(text); }
            QScrollArea#tools_scroll { background: transparent; border: none; }
            QScrollArea#tools_scroll > QWidget > QWidget { background: transparent; }
            """
        )

        self.apply_language(lang)

    def apply_language(self, lang: str) -> None:
        self._lang = lang
        if self._cgm_current_thread is not None and self._cgm_current_thread.isRunning():
            self._pending_lang_refresh = lang
            return
        self._pending_lang_refresh = None
        self._clear_layout(self._v)

        self._v.addWidget(self._bmi_section())
        self._v.addWidget(self._duration_section())
        self._v.addWidget(self._egfr_section())
        self._v.addWidget(self._glucose_unit_section())
        self._v.addWidget(self._cgm_section())
        self._v.addStretch(1)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _bmi_section(self) -> QGroupBox:
        height = LineEdit()
        weight = LineEdit()
        waist = LineEdit()
        height.setObjectName("tools_bmi_height")
        weight.setObjectName("tools_bmi_weight")
        waist.setObjectName("tools_bmi_waist")
        height.setValidator(QDoubleValidator(90.0, 220.0, 2, self))
        weight.setValidator(QDoubleValidator(30.0, 200.0, 2, self))
        waist.setValidator(QDoubleValidator(30.0, 200.0, 2, self))
        out_bmi = QLabel("-")
        out_wwi = QLabel("-")
        out_bmi.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        out_wwi.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        def calc() -> None:
            h = _safe_float(height.text())
            w = _safe_float(weight.text())
            wa = _safe_float(waist.text())

            if h is not None and w is not None:
                try:
                    out_bmi.setText(str(compute_bmi(h, w)))
                except Exception:
                    out_bmi.setText("-")
            else:
                out_bmi.setText("-")

            if w is not None and wa is not None:
                try:
                    out_wwi.setText(str(compute_wwi(wa, w)))
                except Exception:
                    out_wwi.setText("-")
            else:
                out_wwi.setText("-")

        height.textChanged.connect(calc)
        weight.textChanged.connect(calc)
        waist.textChanged.connect(calc)

        def guard_float(widget: LineEdit, label: str, lo: float, hi: float) -> None:
            raw = widget.text().strip()
            if not raw:
                return
            v = _safe_float(raw)
            if v is None:
                QMessageBox.warning(self, "输入错误" if self._lang == "zh" else "Invalid input", f"{label}只能填写数字" if self._lang == "zh" else f"{label} must be numeric")
                widget.setFocus()
                widget.selectAll()
                return
            if v < lo or v > hi:
                msg = f"{label}合法范围：{lo:g}~{hi:g}" if self._lang == "zh" else f"{label} range: {lo:g}~{hi:g}"
                QMessageBox.warning(self, "输入错误" if self._lang == "zh" else "Invalid input", msg)
                widget.setFocus()
                widget.selectAll()

        height.editingFinished.connect(lambda: guard_float(height, "身高" if self._lang == "zh" else "Height", 90.0, 220.0))
        weight.editingFinished.connect(lambda: guard_float(weight, "体重" if self._lang == "zh" else "Weight", 30.0, 200.0))
        waist.editingFinished.connect(lambda: guard_float(waist, "腰围" if self._lang == "zh" else "Waist", 30.0, 200.0))

        box = QGroupBox("BMI与WWI（体重校正腰围指数）" if self._lang == "zh" else "BMI & WWI")
        row = QHBoxLayout()
        row.addWidget(QLabel("身高(cm)" if self._lang == "zh" else "Height (cm)"))
        row.addWidget(height, 1)
        row.addWidget(QLabel("体重(kg)" if self._lang == "zh" else "Weight (kg)"))
        row.addWidget(weight, 1)
        row.addWidget(QLabel("腰围 Waist(cm)" if self._lang == "zh" else "Waist (cm)"))
        row.addWidget(waist, 1)
        row.addWidget(QLabel("BMI"))
        row.addWidget(out_bmi, 1)
        row.addWidget(QLabel("WWI"))
        row.addWidget(out_wwi, 1)
        w = QWidget()
        w.setLayout(row)

        v = QVBoxLayout()
        v.addWidget(w)
        box.setLayout(v)
        return box

    def _duration_section(self) -> QGroupBox:
        y = LineEdit()
        m = LineEdit()
        d = LineEdit()
        y.setPlaceholderText("YYYY")
        m.setPlaceholderText("MM")
        d.setPlaceholderText("DD")

        out = QLabel("-")
        out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        def calc(show_error: bool) -> None:
            try:
                yy_text = y.text().strip()
                if not yy_text:
                    out.setText("-")
                    return
                yy = int(yy_text)

                mm_text = m.text().strip()
                dd_text = d.text().strip()

                if mm_text and dd_text:
                    mm = int(mm_text)
                    dd = int(dd_text)
                    start = date(yy, mm, dd)
                    if start < date(1950, 1, 1):
                        raise ValueError("首次糖尿病日期不能早于1950年1月1日")
                    months = _months_between(start, date.today())
                    out.setText(f"{months // 12}年{months % 12}月（共{months}月）")
                    return

                start = date(yy, 1, 1)
                if start < date(1950, 1, 1):
                    raise ValueError("首次糖尿病日期不能早于1950年1月1日")
                months = _months_between(start, date.today())
                years = int(round(months / 12.0))
                out.setText(f"约 {years} 年")
            except Exception as ex:
                out.setText("-")
                if show_error:
                    QMessageBox.warning(self, "输入错误", str(ex))

        y.editingFinished.connect(lambda: calc(True))
        m.editingFinished.connect(lambda: calc(True))
        d.editingFinished.connect(lambda: calc(True))
        y.textChanged.connect(lambda: calc(False))
        m.textChanged.connect(lambda: calc(False))
        d.textChanged.connect(lambda: calc(False))

        box = QGroupBox("病程估算（首次确诊日期 → 当前）" if self._lang == "zh" else "DM Duration Estimator")
        row = QHBoxLayout()
        row.addWidget(QLabel("首次确诊日期" if self._lang == "zh" else "Dx date"))
        row.addWidget(y)
        row.addWidget(QLabel("-"))
        row.addWidget(m)
        row.addWidget(QLabel("-"))
        row.addWidget(d)
        row.addWidget(QLabel("结果" if self._lang == "zh" else "Result"))
        row.addWidget(out, 2)
        w = QWidget()
        w.setLayout(row)

        v = QVBoxLayout()
        v.addWidget(w)
        box.setLayout(v)
        return box

    def _egfr_section(self) -> QGroupBox:
        age = LineEdit()
        age.setObjectName("tools_egfr_age")
        age.setValidator(QIntValidator(10, 120, self))
        gender = ComboBox()
        gender.addItems(["男 Male", "女 Female"] if self._lang == "zh" else ["Male", "Female"])
        weight = LineEdit()
        weight.setObjectName("tools_egfr_weight")
        weight.setValidator(QDoubleValidator(30.0, 200.0, 2, self))

        scr = LineEdit()
        scr.setObjectName("tools_egfr_scr")
        scr.setValidator(QDoubleValidator(0.1, 2000.0, 2, self))
        scr_unit = ComboBox()
        scr_unit.addItems(["umol/L", "mg/dL"])

        out_ckd = QLabel("-")
        out_mdrd = QLabel("-")
        out_cg = QLabel("-")

        for lab in (out_ckd, out_mdrd, out_cg):
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        def gender_value() -> str:
            t = gender.currentText()
            return "女" if "女" in t or "female" in t.lower() else "男"

        def calc() -> None:
            a = _safe_int(age.text())
            w = _safe_float(weight.text())
            s = _safe_float(scr.text())
            if a is None or s is None:
                out_ckd.setText("-")
                out_mdrd.setText("-")
                out_cg.setText("-")
                return
            try:
                s_mg = scr_to_mg_dl(s, scr_unit.currentText())
                g = gender_value()
                out_ckd.setText(str(compute_egfr_ckd_epi_2009(s_mg, a, g)))
                out_mdrd.setText(str(compute_egfr_mdrd_4var(s_mg, a, g)))
                out_cg.setText(str(compute_crcl_cockcroft_gault(s_mg, a, g, w))) if w is not None else out_cg.setText("-")
            except Exception:
                out_ckd.setText("-")
                out_mdrd.setText("-")
                out_cg.setText("-")

        for wgt in (age, weight, scr):
            wgt.textChanged.connect(calc)
        gender.currentIndexChanged.connect(calc)
        scr_unit.currentIndexChanged.connect(calc)

        box = QGroupBox("eGFR / CrCl 计算器（多公式）" if self._lang == "zh" else "eGFR / CrCl (Multi-Formula)")
        grid = QGridLayout()

        grid.addWidget(QLabel("年龄 Age" if self._lang == "zh" else "Age"), 0, 0)
        grid.addWidget(age, 0, 1)
        grid.addWidget(QLabel("性别 Gender" if self._lang == "zh" else "Gender"), 0, 2)
        grid.addWidget(gender, 0, 3)
        grid.addWidget(QLabel("体重(kg)" if self._lang == "zh" else "Weight (kg)"), 0, 4)
        grid.addWidget(weight, 0, 5)

        grid.addWidget(QLabel("Scr"), 1, 0)
        grid.addWidget(scr, 1, 1)
        grid.addWidget(scr_unit, 1, 2)

        grid.addWidget(QLabel("CKD-EPI"), 2, 0)
        grid.addWidget(out_ckd, 2, 1, 1, 2)
        grid.addWidget(QLabel("MDRD"), 3, 0)
        grid.addWidget(out_mdrd, 3, 1, 1, 2)
        grid.addWidget(QLabel("Cockcroft-Gault"), 4, 0)
        grid.addWidget(out_cg, 4, 1, 1, 2)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(5, 1)
        box.setLayout(grid)
        return box

    def _glucose_unit_section(self) -> QGroupBox:
        glucose_in = LineEdit()
        glucose_in.setObjectName("tools_glucose_in")
        glucose_unit = ComboBox()
        glucose_unit.addItems(["mmol/L", "mg/dL"])
        glucose_out = QLabel("-")
        glucose_out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        hba1c_in = LineEdit()
        hba1c_in.setObjectName("tools_hba1c_in")
        hba1c_out = QLabel("-")
        hba1c_out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        def calc_glucose() -> None:
            v = _safe_float(glucose_in.text())
            if v is None:
                glucose_out.setText("-")
                return
            try:
                mg = fpg_to_mg_dl(v, glucose_unit.currentText())
                mmol = mg / 18.0
                a1c = (mg + 46.7) / 28.7
                if self._lang == "zh":
                    glucose_out.setText(f"{mmol:.3f} mmol/L  |  {mg:.1f} mg/dL  |  HbA1c≈{a1c:.2f} %")
                else:
                    glucose_out.setText(f"{mmol:.3f} mmol/L  |  {mg:.1f} mg/dL  |  HbA1c≈{a1c:.2f} %")
            except Exception:
                glucose_out.setText("-")

        def calc_hba1c() -> None:
            a1c = _safe_float(hba1c_in.text())
            if a1c is None:
                hba1c_out.setText("-")
                return
            try:
                eag_mg = 28.7 * float(a1c) - 46.7
                eag_mmol = eag_mg / 18.0
                hba1c_out.setText(f"eAG: {eag_mmol:.3f} mmol/L  |  {eag_mg:.1f} mg/dL")
            except Exception:
                hba1c_out.setText("-")

        glucose_in.textChanged.connect(calc_glucose)
        glucose_unit.currentIndexChanged.connect(calc_glucose)
        hba1c_in.textChanged.connect(calc_hba1c)

        box = QGroupBox("血糖单位换算与HbA1c估算" if self._lang == "zh" else "Glucose Unit & HbA1c Estimation")
        grid = QGridLayout()

        grid.addWidget(QLabel("血糖 Glucose" if self._lang == "zh" else "Glucose"), 0, 0)
        grid.addWidget(glucose_in, 0, 1)
        grid.addWidget(glucose_unit, 0, 2)
        grid.addWidget(QLabel("输出" if self._lang == "zh" else "Output"), 0, 3)
        grid.addWidget(glucose_out, 0, 4)

        grid.addWidget(QLabel("HbA1c(%)"), 1, 0)
        grid.addWidget(hba1c_in, 1, 1)
        grid.addWidget(QLabel(""), 1, 2)
        grid.addWidget(QLabel("估算" if self._lang == "zh" else "Estimate"), 1, 3)
        grid.addWidget(hba1c_out, 1, 4)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(4, 2)
        box.setLayout(grid)
        return box

    def _cgm_section(self) -> QGroupBox:
        # CGM 动态指标计算区：
        # - 选择文件（Excel/CSV）
        # - 开始计算（后台线程）
        # - 结果/错误输出到文本框
        self._cgm_file = LineEdit()
        self._cgm_file.setReadOnly(True)
        self._cgm_out = TextEdit()
        self._cgm_out.setReadOnly(True)
        self._cgm_out.setFixedHeight(220)

        btn_pick = PushButton("选择文件" if self._lang == "zh" else "Choose File")
        btn_run = PrimaryPushButton("开始计算" if self._lang == "zh" else "Run")

        def pick() -> None:
            # 选择文件：Excel/CSV
            path, _ = QFileDialog.getOpenFileName(
                self,
                "选择 CGM 文件" if self._lang == "zh" else "Select CGM file",
                "",
                "Excel/CSV (*.xlsx *.xls *.csv);;All Files (*)",
            )
            if not path:
                return
            self._cgm_file.setText(path)
            # 如果当前正在计算：根据需求“立刻终止前文件计算并切换到新文件”
            if self._cgm_current_thread is not None and self._cgm_current_thread.isRunning():
                self._start_cgm_job(path)

        def run() -> None:
            # 开始计算：没有选文件就提示
            file_path = self._cgm_file.text().strip()
            if not file_path:
                QMessageBox.information(self, "提示" if self._lang == "zh" else "Info", "请先选择文件。" if self._lang == "zh" else "Please choose a file first.")
                return
            self._start_cgm_job(file_path)

        btn_pick.clicked.connect(pick)
        btn_run.clicked.connect(run)

        row = QHBoxLayout()
        row.addWidget(QLabel("文件" if self._lang == "zh" else "File"))
        row.addWidget(self._cgm_file, 1)
        row.addWidget(btn_pick)
        row.addWidget(btn_run)

        box = QGroupBox("CGM 动态计算器（后台线程）" if self._lang == "zh" else "CGM Metrics (Background)")
        v = QVBoxLayout()
        v.addLayout(row)
        v.addWidget(self._cgm_out)
        box.setLayout(v)
        return box

    def _cancel_cgm_thread(self, thread: QThread) -> None:
        # 中断后台线程：
        # - requestInterruption 只会设置“中断标记”
        # - 实际停止依赖 worker 在业务计算过程中不断调用 cancel_check()
        try:
            thread.requestInterruption()
        except Exception:
            pass

    def _start_cgm_job(self, file_path: str) -> None:
        # 启动一个新的 CGM 后台任务：
        # - 如果已有任务在跑：先中断旧任务，再启动新任务（需求：重新上传即切换）
        # - 每个任务使用 job_id 防止“旧回调覆盖新结果”
        self._cgm_jobs = [(t, w) for (t, w) in self._cgm_jobs if t.isRunning()]
        if self._cgm_current_thread is not None and self._cgm_current_thread.isRunning():
            old = self._cgm_current_file_path or ""
            self._logger.info("CGM计算中断并切换文件：%s -> %s", old, file_path)
            self._cancel_cgm_thread(self._cgm_current_thread)

        # 自增任务号（job_id）
        self._cgm_job_seq += 1
        job_id = int(self._cgm_job_seq)
        # UI：先提示“正在计算”，避免用户误以为没响应
        self._logger.info("CGM计算开始：%s", file_path)
        self._cgm_out.setPlainText("正在计算，请稍候…" if self._lang == "zh" else "Running, please wait...")

        # 创建线程与 worker，并把 worker 移动到线程里运行
        thread = QThread(self)
        worker = _CgmWorker(file_path, job_id)
        worker.moveToThread(thread)
        self._last_cgm_thread = thread
        self._last_cgm_worker = worker
        # 记录“当前任务”信息
        self._cgm_current_thread = thread
        self._cgm_current_file_path = file_path
        self._cgm_current_job_id = job_id
        self._cgm_job_threads[job_id] = thread

        # thread.started 触发 worker.run（真正执行计算）
        thread.started.connect(worker.run)

        # worker 信号回调到 UI 线程（Qt 会做跨线程队列投递）
        worker.finished.connect(self._on_cgm_finished)
        worker.failed.connect(self._on_cgm_failed)
        worker.cancelled.connect(self._on_cgm_cancelled)

        def cleanup() -> None:
            # 线程退出后的清理：
            # - 移除已结束线程引用
            # - 清空“当前任务”指针
            # - 若语言切换在等待，则在此时重建 UI
            try:
                self._cgm_jobs = [(t, w) for (t, w) in self._cgm_jobs if t.isRunning()]
                self._cgm_job_threads.pop(job_id, None)
                if self._last_cgm_thread is thread:
                    self._last_cgm_thread = None
                if self._last_cgm_worker is worker:
                    self._last_cgm_worker = None
                if self._cgm_current_thread is thread:
                    self._cgm_current_thread = None
                    self._cgm_current_file_path = None
                    self._cgm_current_job_id = None
                if self._pending_lang_refresh is not None:
                    lang = str(self._pending_lang_refresh)
                    self._pending_lang_refresh = None
                    self.apply_language(lang)
            except Exception:
                pass

        # 线程结束后释放 QObject，避免内存泄漏
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(cleanup)

        # 保存到 job 列表，便于后续过滤掉已结束线程
        self._cgm_jobs.append((thread, worker))
        # 启动线程：触发 thread.started
        thread.start()

    def _on_cgm_finished(self, job_id: int, file_path: str, res: dict) -> None:
        # 注意：该函数运行在 UI 线程
        # - 只处理“当前任务”的回调
        # - 始终关闭对应的 thread（正常退出）
        thread = self._cgm_job_threads.get(job_id)
        try:
            if self._cgm_current_job_id is None or job_id != self._cgm_current_job_id:
                return
            self._logger.info("CGM计算完成：%s", file_path)
            txt_lines = []
            for k in sorted(res.keys()):
                v = res[k]
                txt_lines.append(f"{k}: {v}")
            self._cgm_out.setPlainText("\n".join(txt_lines))
        except Exception:
            self._logger.exception("CGM结果渲染失败")
            self._cgm_out.setPlainText("结果渲染失败，请查看日志。" if self._lang == "zh" else "Failed to render results. Check logs.")
        finally:
            if thread is not None and thread.isRunning():
                thread.quit()

    def _on_cgm_failed(self, job_id: int, file_path: str, kind: str, msg: str) -> None:
        # 失败回调：
        # - file_not_found / header_mismatch：弹窗提示并结束
        # - unknown：仅写入输出框与日志
        thread = self._cgm_job_threads.get(job_id)
        try:
            if self._cgm_current_job_id is None or job_id != self._cgm_current_job_id:
                return
            self._logger.warning("CGM计算失败：%s | %s", file_path, msg)
            prefix = "计算失败" if self._lang == "zh" else "Failed"
            self._cgm_out.setPlainText(f"{prefix}: {msg}")
            if kind in {"file_not_found", "header_mismatch"}:
                title = "CGM计算错误" if self._lang == "zh" else "CGM Error"
                QMessageBox.critical(self, title, msg)
        except Exception:
            pass
        finally:
            if thread is not None and thread.isRunning():
                thread.quit()

    def _on_cgm_cancelled(self, job_id: int, file_path: str) -> None:
        # 取消回调：用户切文件触发
        thread = self._cgm_job_threads.get(job_id)
        try:
            if self._cgm_current_job_id is None or job_id != self._cgm_current_job_id:
                return
            self._logger.info("CGM计算已取消：%s", file_path)
            self._cgm_out.setPlainText("已取消" if self._lang == "zh" else "Cancelled")
        except Exception:
            pass
        finally:
            if thread is not None and thread.isRunning():
                thread.quit()
