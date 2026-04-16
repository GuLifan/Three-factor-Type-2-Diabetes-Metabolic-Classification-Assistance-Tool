from __future__ import annotations

# 说明类弹窗（TTCAS）
# - ClusterPrincipleDialog：展示聚类原理图片 + 当前配置参数（μ/σ/质心）
# - ToolsPrincipleDialog：展示常用计算器的原理与公式（HTML 富文本）

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QScrollArea, QVBoxLayout, QTextBrowser, QWidget

from ttcas_app.config import AppConfig


class ClusterPrincipleDialog(QDialog):
    """
    聚类原则说明弹窗：
    - 读取 config.yaml 中配置的图片路径
    - 允许滚动查看
    - 尽量按当前窗口宽度自适应缩放（避免固定宽度带来的比例体验问题）
    """

    def __init__(self, *, cfg: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("聚类原则说明")
        self.resize(900, 700)

        self._cfg = cfg
        self._pix: QPixmap | None = None

        self._content = QWidget()
        self._v = QVBoxLayout()
        self._v.setContentsMargins(12, 12, 12, 12)
        self._v.setSpacing(12)
        self._content.setLayout(self._v)

        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._v.addWidget(self._image)

        self._params = QTextBrowser()
        self._params.setOpenExternalLinks(True)
        self._params.setReadOnly(True)
        self._v.addWidget(self._params, 1)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._content)

        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)

        path = cfg.resolve_path(cfg.ui.cluster_principle_image) if cfg.ui.cluster_principle_image else None
        if path is not None and path.exists():
            self._pix = QPixmap(str(path))
            self._apply_scaled_pixmap()
        else:
            self._image.setText("未找到聚类原则图片，请检查 config.yaml 的 ui.cluster_principle_image 配置。")

        self._params.setHtml(self._build_params_html())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_scaled_pixmap()

    def _apply_scaled_pixmap(self) -> None:
        if self._pix is None or self._pix.isNull():
            return
        target_w = max(480, int(self.width() - 80))
        scaled = self._pix.scaledToWidth(target_w, Qt.TransformationMode.SmoothTransformation)
        self._image.setPixmap(scaled)

    def _build_params_html(self) -> str:
        import html
        import json

        m = self._cfg.model
        explain = (
            "聚类方法：质心最近原则（Centroid Nearest）<br/>"
            "1) 先将特征做 Z 分数标准化：z = (x - μ) / σ<br/>"
            "2) 计算样本 z 与各质心 z 的欧氏距离：d = sqrt(Σ(z_i - c_i)^2)<br/>"
            "3) 距离最小的质心编号即为表型编号 k<br/>"
            "<br/>"
            "两条通道：<br/>"
            "- TyG-eGFR-ALB<br/>"
            "- TyG-WWI-ALB<br/>"
        )

        params = {
            "cluster_version": m.cluster_version,
            "method": m.method,
            "tyg_egfr_alb": {
                "zscore_mean": m.zscore_mean,
                "zscore_std": m.zscore_std,
                "centroids_z": m.centroids_z,
            },
            "tyg_wwi_alb": {
                "zscore_mean": m.zscore_mean_wwi,
                "zscore_std": m.zscore_std_wwi,
                "centroids_z": m.centroids_z_wwi,
            },
        }

        param_json = json.dumps(params, ensure_ascii=False, indent=2)
        return (
            "<h3>原理与参数</h3>"
            f"<div>{explain}</div>"
            "<h4>当前配置参数（来自 config.yaml）</h4>"
            f"<pre>{html.escape(param_json)}</pre>"
        )


class ToolsPrincipleDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("计算器说明")
        self.resize(760, 520)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setReadOnly(True)
        browser.setHtml(
            "<h3>常用计算器：原理与公式</h3>"
            "<b>1) BMI</b><br/>"
            "BMI = 体重(kg) / [身高(m)]²<br/>"
            "<br/>"
            "<b>2) WWI（体重校正腰围指数）</b><br/>"
            "WWI = 腰围(cm) / sqrt(体重(kg))<br/>"
            "<br/>"
            "<b>3) 病程（月）</b><br/>"
            "根据“首次确诊日期”与“当前日期”估算月份差（按 30 天≈1月进行四舍五入）。<br/>"
            "<br/>"
            "<b>4) eGFR</b><br/>"
            "- CKD-EPI 2009：eGFR = 141 × min(Scr/k,1)^α × max(Scr/k,1)^-1.209 × 0.993^Age × SexFactor<br/>"
            "- MDRD 4变量：eGFR = 175 × Scr^-1.154 × Age^-0.203 × SexFactor<br/>"
            "- Cockcroft–Gault（CrCl）：CrCl = (140-Age)×Weight / (72×Scr) × SexFactor<br/>"
            "<br/>"
            "<b>5) 单位换算</b><br/>"
            "- 血糖：mg/dL = mmol/L × 18<br/>"
            "- Scr：mg/dL = umol/L ÷ 88.4<br/>"
            "<br/>"
            "<b>6) CGM 动态计算器</b><br/>"
            "从 Excel/CSV 自动识别“时间列/血糖列”，后台线程计算常用 CGM 指标（TIR/TAR/TBR、GMI、CV、LBGI/HBGI、MODD、LAGE/MAGE 等）。<br/>"
            "当文件不存在或表头不匹配时，会直接终止计算并弹窗报错；上传新文件会中断前一个文件的计算并切换到新文件。<br/>"
        )

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(browser)

        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)
