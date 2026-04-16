from __future__ import annotations

# 业务域（TTCAS）
# - 不依赖任何 PySide6：便于单元测试与复用
# - 包含：数据结构（账号/会话/患者输入/报告）、输入校验、指标计算、聚类分型、报告渲染

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


def now_iso() -> str:
    # 统一的时间戳格式：用于日志/归档字段/账号创建时间等
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class DoctorAccount:
    # 医师账号（本地离线）
    # - doctor_id：登录账号（唯一键）
    # - organization/department：可选展示信息
    # - password：存储的密码（兼容早期明文与 sha256 前缀）
    # - created_at：账号创建时间
    doctor_id: str
    organization: str | None
    department: str | None
    password: str
    created_at: str

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "DoctorAccount":
        # 兼容旧字段名：
        # - Doctor_ID / Organization / Department / Password
        doctor_id = str(d.get("doctor_id") or d.get("Doctor_ID") or "").strip()
        organization = d.get("organization") or d.get("Organization")
        department = d.get("department") or d.get("Department")
        organization_s = str(organization).strip() if organization is not None else None
        department_s = str(department).strip() if department is not None else None
        password = str(d.get("password") or d.get("Password") or "").strip()
        created_at = str(d.get("created_at") or d.get("createdAt") or now_iso())
        if not doctor_id or not password:
            raise ValueError("账号记录缺少 doctor_id/password")
        return DoctorAccount(
            doctor_id=doctor_id,
            organization=organization_s or None,
            department=department_s or None,
            password=password,
            created_at=created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"doctor_id": self.doctor_id, "password": self.password, "created_at": self.created_at}
        if self.organization:
            d["organization"] = self.organization
        if self.department:
            d["department"] = self.department
        return d


@dataclass(frozen=True)
class DoctorSession:
    doctor_id: str
    login_at: str


@dataclass(frozen=True)
class PatientInput:
    """
    患者录入数据（尽量保持“输入态”）：
    - 字段命名偏业务：便于医生/研究者对照
    - 校验在用例中完成（避免模型初始化阶段因 UI 的“半输入态”频繁抛错）
    """

    patient_id: str
    patient_name: str | None
    birth_year: int | None
    birth_month: int | None
    birth_day: int | None
    gender: str
    age_years: int
    phone_number: str | None
    cgm_sensor_id: str | None

    height_cm: float
    weight_kg: float
    waist_cm: float | None

    dm_duration_years: int | None
    dm_duration_months: int | None
    dm_dx_year: int | None
    dm_dx_month: int | None
    complications: dict[str, bool] | None
    complications_other: str | None

    fpg_value: float
    fpg_unit: str
    tg_value: float
    tg_unit: str
    alb_g_l: float
    scr_value: float
    scr_unit: str
    egfr_value: float | None
    hba1c_percent: float | None

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self, default=lambda o: o.__dict__, ensure_ascii=False))


@dataclass(frozen=True)
class DerivedIndicators:
    bmi: float
    tyg: float
    egfr: float
    wwi: float | None


@dataclass(frozen=True)
class PatientReport:
    """
    报告对象：
    - input：原始输入（用于追溯）
    - derived：衍生指标（用于展示/分型）
    - phenotype：两个分型通道输出（用于诊疗提示）
    - operator / version：用于审计追责与科研版本一致性
    """

    input: PatientInput
    derived: DerivedIndicators
    phenotype: dict[str, Any]
    operator_doctor_id: str
    doctor_note: str | None
    generated_at: str
    app_version: str
    model_version: str
    cluster_method: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input.to_dict(),
            "derived": {
                "bmi": self.derived.bmi,
                "tyg": self.derived.tyg,
                "egfr": self.derived.egfr,
                "wwi": self.derived.wwi,
            },
            "phenotype": self.phenotype,
            "operator_doctor_id": self.operator_doctor_id,
            "doctor_note": self.doctor_note,
            "generated_at": self.generated_at,
            "app_version": self.app_version,
            "model_version": self.model_version,
            "cluster_method": self.cluster_method,
            "notes": self.notes,
        }


def require_positive(v: float, name: str) -> None:
    if v <= 0:
        raise ValueError(f"{name} 必须为正数")


def require_int_range(v: int, name: str, lo: int, hi: int) -> None:
    if v < lo or v > hi:
        raise ValueError(f"{name} 必须在 [{lo}, {hi}] 范围内")


def require_float_range(v: float, name: str, lo: float, hi: float) -> None:
    if v < lo or v > hi:
        raise ValueError(f"{name} 必须在 [{lo}, {hi}] 范围内")


def require_length(s: str, name: str, lo: int, hi: int) -> None:
    if len(s) < lo or len(s) > hi:
        raise ValueError(f"{name} 长度必须在 [{lo}, {hi}] 之间")


def validate_phone(phone: str) -> None:
    # 手机号校验：
    # - 允许空值（未填写）
    # - 非空时要求纯数字且长度 11 位
    p = phone.strip()
    if not p:
        return
    if not p.isdigit():
        raise ValueError("手机号必须为纯数字")
    if len(p) not in (11,):
        raise ValueError("手机号长度必须为11位")


def compute_bmi(height_cm: float, weight_kg: float) -> float:
    # BMI 公式：
    # BMI = 体重(kg) / [身高(m)]²
    height_m = height_cm / 100.0
    require_positive(height_m, "身高(m)")
    bmi = weight_kg / (height_m * height_m)
    return round(float(bmi), 3)


def compute_wwi(waist_cm: float, weight_kg: float) -> float:
    # WWI（体重校正腰围指数）公式：
    # WWI = 腰围(cm) / sqrt(体重(kg))
    require_positive(weight_kg, "体重(kg)")
    wwi = waist_cm / math.sqrt(weight_kg)
    return round(float(wwi), 4)


def fpg_to_mg_dl(value: float, unit: str) -> float:
    # 血糖单位换算：
    # - mmol/L -> mg/dL：× 18
    if unit == "mg/dL":
        return float(value)
    if unit == "mmol/L":
        return float(value) * 18.0
    raise ValueError("FPG单位不支持（仅支持 mmol/L 或 mg/dL）")


def tg_to_mg_dl(value: float, unit: str) -> float:
    # 甘油三酯单位换算：
    # - mmol/L -> mg/dL：× 88.57
    if unit == "mg/dL":
        return float(value)
    if unit == "mmol/L":
        return float(value) * 88.57
    raise ValueError("TG单位不支持（仅支持 mmol/L 或 mg/dL）")


def scr_to_mg_dl(value: float, unit: str) -> float:
    # 血清肌酐单位换算：
    # - umol/L -> mg/dL：÷ 88.4
    if unit == "mg/dL":
        return float(value)
    if unit == "umol/L":
        return float(value) / 88.4
    raise ValueError("Scr单位不支持（仅支持 umol/L 或 mg/dL）")


def compute_tyg(tg_mg_dl: float, fpg_mg_dl: float) -> float:
    # TyG 指数公式：
    # TyG = ln( TG(mg/dL) × FPG(mg/dL) / 2 )
    require_positive(tg_mg_dl, "TG")
    require_positive(fpg_mg_dl, "FPG")
    tyg = math.log((tg_mg_dl * fpg_mg_dl) / 2.0)
    return round(float(tyg), 4)


def compute_egfr_ckd_epi_2009(scr_mg_dl: float, age_years: int, gender: str) -> float:
    # eGFR（CKD-EPI 2009）：
    # eGFR = 141 × min(Scr/k,1)^α × max(Scr/k,1)^-1.209 × 0.993^Age × SexFactor
    require_positive(scr_mg_dl, "Scr")
    require_int_range(age_years, "年龄", 10, 120)

    g = gender.strip()
    if g not in ("男", "女"):
        raise ValueError("性别必须为“男”或“女”")

    if g == "女":
        k = 0.7
        alpha = -0.329
        sex_factor = 1.018
    else:
        k = 0.9
        alpha = -0.411
        sex_factor = 1.0

    ratio = float(scr_mg_dl) / float(k)
    egfr = 141.0 * (min(ratio, 1.0) ** alpha) * (max(ratio, 1.0) ** -1.209) * (0.993**age_years)
    egfr *= sex_factor
    return round(float(egfr), 2)


def compute_egfr_mdrd_4var(scr_mg_dl: float, age_years: int, gender: str) -> float:
    # eGFR（MDRD 4变量）：
    # eGFR = 175 × Scr^-1.154 × Age^-0.203 × SexFactor
    require_positive(scr_mg_dl, "Scr")
    require_int_range(age_years, "年龄", 10, 120)
    g = gender.strip()
    if g not in ("男", "女"):
        raise ValueError("性别必须为“男”或“女”")
    sex_factor = 0.742 if g == "女" else 1.0
    egfr = 175.0 * (float(scr_mg_dl) ** -1.154) * (float(age_years) ** -0.203) * sex_factor
    return round(float(egfr), 2)


def compute_crcl_cockcroft_gault(scr_mg_dl: float, age_years: int, gender: str, weight_kg: float) -> float:
    # 肌酐清除率（Cockcroft–Gault）：
    # CrCl = (140 - Age) × Weight / (72 × Scr) × SexFactor
    require_positive(scr_mg_dl, "Scr")
    require_int_range(age_years, "年龄", 10, 120)
    require_float_range(weight_kg, "体重(kg)", 30, 300)
    g = gender.strip()
    if g not in ("男", "女"):
        raise ValueError("性别必须为“男”或“女”")
    base = ((140.0 - float(age_years)) * float(weight_kg)) / (72.0 * float(scr_mg_dl))
    if g == "女":
        base *= 0.85
    return round(float(base), 2)


def _phenotype_meta_egfr(code: int) -> dict[str, str]:
    if code == 1:
        return {
            "cn": "低肌肉储备/低白蛋白型",
            "en": "Low Muscle Reserve with Low Albumin",
            "tips": "稳定优先、夜间波动管理、营养与肌肉储备支持",
        }
    if code == 2:
        return {
            "cn": "代谢相对健康型",
            "en": "Metabolically Healthy",
            "tips": "按常规路径管理、维持达标与并发症筛查",
        }
    if code == 3:
        return {
            "cn": "中度肾功能受损型",
            "en": "Moderate Renal Impairment",
            "tips": "安全优先、低血糖风险控制、肾功能约束下的用药提示",
        }
    if code == 4:
        return {
            "cn": "重度胰岛素抵抗型",
            "en": "Severe Insulin-Resistant",
            "tips": "代谢负荷高、强化降糖与脂代谢/脂肪肝/酮症关注",
        }
    raise ValueError("未知表型编号")


def _phenotype_meta_wwi(code: int) -> dict[str, str]:
    if code == 1:
        return {
            "cn": "重度高甘油三酯胰岛素抵抗型",
            "en": "Severe Hypertriglyceridemic Insulin-Resistant",
            "tips": "强化降糖、关注脂代谢与酮症、快速改善潜力大。管理重点：积极强化胰岛素治疗，快速解除高糖毒性；重点关注脂肪肝、高甘油三酯血症，联合降脂及生活方式干预；酮症风险较高，需监测血酮、避免诱因；低血糖风险相对较低，但快速降糖过程中仍需警惕。",
        }
    if code == 2:
        return {
            "cn": "消耗型（低白蛋白型）",
            "en": "Consumptive (Low-Albumin)",
            "tips": "稳定优先、营养支持、肾脏保护、预期反应慢。管理重点：避免过于激进的降糖目标，优先稳定血糖、减少波动；尽早评估营养状态（低白蛋白、低肌肉储备），启动营养支持与康复训练；强化肾脏保护（控制血压、使用RAS抑制剂、监测UACR）；胰岛素滴定需更谨慎，加强血糖监测。",
        }
    if code == 3:
        return {
            "cn": "代谢代偿型",
            "en": "Metabolically Compensated",
            "tips": "常规路径管理、维持达标与并发症筛查。管理重点：按标准住院血糖管理路径执行；常规并发症筛查（眼底、尿蛋白、神经病变）；维持健康体重、腰围及血脂水平。",
        }
    if code == 4:
        return {
            "cn": "中心性肥胖低体重型",
            "en": "Central Obesity with Low Body Weight",
            "tips": "关注心血管风险、身体成分管理、胰岛素敏感性保留。管理重点：重点控制心血管危险因素（血压、血脂、抗血小板）；评估并干预肌少症性肥胖（增加蛋白质摄入、抗阻训练）；降糖方案中注意避免加重体重下降或肌肉流失；肾功能虽可能轻度下降，但仍需谨慎用药。",
        }
    raise ValueError("未知WWI表型编号")


def phenotype_centroid_nearest_egfr(
    *,
    tyg: float,
    egfr: float,
    alb_g_l: float,
    zscore_mean: dict[str, float],
    zscore_std: dict[str, float],
    centroids_z: list[dict[str, float]],
    model_version: str,
) -> dict[str, Any]:
    mu_tyg = zscore_mean["tyg"]
    mu_egfr = zscore_mean["egfr"]
    mu_alb = zscore_mean["alb"]
    sd_tyg = zscore_std["tyg"]
    sd_egfr = zscore_std["egfr"]
    sd_alb = zscore_std["alb"]

    if sd_tyg == 0 or sd_egfr == 0 or sd_alb == 0:
        raise ValueError("聚类参数错误：标准差σ不能为0")

    z = {
        "tyg": (tyg - mu_tyg) / sd_tyg,
        "egfr": (egfr - mu_egfr) / sd_egfr,
        "alb": (alb_g_l - mu_alb) / sd_alb,
    }

    best_k = 1
    best_d = float("inf")
    for idx, c in enumerate(centroids_z, start=1):
        d = math.sqrt((z["tyg"] - c["tyg"]) ** 2 + (z["egfr"] - c["egfr"]) ** 2 + (z["alb"] - c["alb"]) ** 2)
        if d < best_d:
            best_d = d
            best_k = idx

    meta = _phenotype_meta_egfr(best_k)
    return {
        "phenotype_code": best_k,
        "phenotype_cn": meta["cn"],
        "phenotype_en": meta["en"],
        "key_explanations": [f"聚类原则：质心最近原则（k={best_k}，距离={best_d:.4f}）"],
        "clinical_tips": meta["tips"],
        "method": "centroid_nearest",
        "principle_cn": "质心最近原则",
        "distance": round(best_d, 6),
        "model_version": model_version,
    }


def phenotype_centroid_nearest_wwi(
    *,
    tyg: float,
    wwi: float,
    alb_g_l: float,
    zscore_mean: dict[str, float],
    zscore_std: dict[str, float],
    centroids_z: list[dict[str, float]],
    model_version: str,
) -> dict[str, Any]:
    mu_tyg = zscore_mean["tyg"]
    mu_wwi = zscore_mean["wwi"]
    mu_alb = zscore_mean["alb"]
    sd_tyg = zscore_std["tyg"]
    sd_wwi = zscore_std["wwi"]
    sd_alb = zscore_std["alb"]

    if sd_tyg == 0 or sd_wwi == 0 or sd_alb == 0:
        raise ValueError("聚类参数错误：标准差σ不能为0")

    z = {
        "tyg": (tyg - mu_tyg) / sd_tyg,
        "wwi": (wwi - mu_wwi) / sd_wwi,
        "alb": (alb_g_l - mu_alb) / sd_alb,
    }

    best_k = 1
    best_d = float("inf")
    for idx, c in enumerate(centroids_z, start=1):
        d = math.sqrt((z["tyg"] - c["tyg"]) ** 2 + (z["wwi"] - c["wwi"]) ** 2 + (z["alb"] - c["alb"]) ** 2)
        if d < best_d:
            best_d = d
            best_k = idx

    meta = _phenotype_meta_wwi(best_k)
    return {
        "phenotype_code": best_k,
        "phenotype_cn": meta["cn"],
        "phenotype_en": meta["en"],
        "key_explanations": [f"聚类原则：质心最近原则（k={best_k}，距离={best_d:.4f}）"],
        "clinical_tips": meta["tips"],
        "method": "centroid_nearest",
        "principle_cn": "质心最近原则",
        "distance": round(best_d, 6),
        "model_version": model_version,
    }


@dataclass(frozen=True)
class EvaluatePatient:
    """
    用例：对患者输入信息做校验、单位换算、缺失处理、衍生指标计算、分型与报告输出。
    """

    app_version: str
    cluster_version: str
    cluster_method: str

    zscore_mean: dict[str, float]
    zscore_std: dict[str, float]
    centroids_z: list[dict[str, float]]

    zscore_mean_wwi: dict[str, float]
    zscore_std_wwi: dict[str, float]
    centroids_z_wwi: list[dict[str, float]]

    def _validate_input(self, p: PatientInput) -> None:
        pid = p.patient_id.strip()
        if not pid:
            raise ValueError("Patient_ID 不能为空")
        require_length(pid, "Patient_ID", 2, 40)

        require_int_range(int(p.age_years), "年龄", 10, 120)
        if p.gender.strip() not in ("男", "女"):
            raise ValueError("性别必须为“男”或“女”")

        require_float_range(float(p.height_cm), "身高(cm)", 80, 250)
        require_float_range(float(p.weight_kg), "体重(kg)", 20, 300)
        if p.waist_cm is not None:
            require_float_range(float(p.waist_cm), "腰围(cm)", 30, 200)

        require_float_range(float(p.fpg_value), "FPG", 0.5, 60.0)
        if p.fpg_unit not in ("mmol/L", "mg/dL"):
            raise ValueError("FPG单位必须是 mmol/L 或 mg/dL")

        require_float_range(float(p.tg_value), "TG", 0.1, 100.0)
        if p.tg_unit not in ("mmol/L", "mg/dL"):
            raise ValueError("TG单位必须是 mmol/L 或 mg/dL")

        require_float_range(float(p.alb_g_l), "ALB(g/L)", 10, 60)

        require_float_range(float(p.scr_value), "Scr", 0.1, 2000.0)
        if p.scr_unit not in ("umol/L", "mg/dL"):
            raise ValueError("Scr单位必须是 umol/L 或 mg/dL")

        if p.egfr_value is not None:
            require_float_range(float(p.egfr_value), "eGFR", 1, 200)

        if p.hba1c_percent is not None:
            require_float_range(float(p.hba1c_percent), "HbA1c(%)", 3, 20)

        if p.phone_number is not None:
            validate_phone(p.phone_number)

        if p.birth_year is not None or p.birth_month is not None or p.birth_day is not None:
            if p.birth_year is None or p.birth_month is None or p.birth_day is None:
                raise ValueError("出生日期填写不完整（需要 年/月/日 三项）")
            try:
                b = date(int(p.birth_year), int(p.birth_month), int(p.birth_day))
            except Exception as ex:
                raise ValueError("出生日期不合法") from ex
            if b < date(1926, 1, 1):
                raise ValueError("出生日期不能早于1926年1月1日")

    def execute(self, *, payload: PatientInput, operator_doctor_id: str, doctor_note: str | None) -> PatientReport:
        self._validate_input(payload)

        notes: list[str] = []

        bmi = compute_bmi(payload.height_cm, payload.weight_kg)

        wwi: float | None = None
        if payload.waist_cm is not None:
            try:
                wwi = compute_wwi(float(payload.waist_cm), float(payload.weight_kg))
            except Exception:
                wwi = None

        fpg_mg_dl = fpg_to_mg_dl(float(payload.fpg_value), payload.fpg_unit)
        tg_mg_dl = tg_to_mg_dl(float(payload.tg_value), payload.tg_unit)
        tyg = compute_tyg(tg_mg_dl, fpg_mg_dl)

        egfr_value = payload.egfr_value
        if egfr_value is None:
            mg = scr_to_mg_dl(float(payload.scr_value), payload.scr_unit)
            egfr_value = compute_egfr_ckd_epi_2009(mg, int(payload.age_years), payload.gender)
            notes.append("eGFR未录入，已按CKD-EPI方程自动计算。")
        egfr = float(egfr_value)

        derived = DerivedIndicators(bmi=bmi, tyg=tyg, egfr=egfr, wwi=wwi)

        phenotype: dict[str, Any] = {}
        if self.cluster_method == "centroid_nearest":
            phenotype["tyg_egfr_alb"] = phenotype_centroid_nearest_egfr(
                tyg=float(tyg),
                egfr=float(egfr),
                alb_g_l=float(payload.alb_g_l),
                zscore_mean=self.zscore_mean,
                zscore_std=self.zscore_std,
                centroids_z=self.centroids_z,
                model_version=self.cluster_version,
            )
            if wwi is not None:
                phenotype["tyg_wwi_alb"] = phenotype_centroid_nearest_wwi(
                    tyg=float(tyg),
                    wwi=float(wwi),
                    alb_g_l=float(payload.alb_g_l),
                    zscore_mean=self.zscore_mean_wwi,
                    zscore_std=self.zscore_std_wwi,
                    centroids_z=self.centroids_z_wwi,
                    model_version=self.cluster_version,
                )
            else:
                phenotype["tyg_wwi_alb"] = {
                    "method": "unavailable",
                    "reason": "腰围未录入或无法计算WWI，TyG-WWI-ALB通道不可用",
                    "model_version": self.cluster_version,
                }
        else:
            raise ValueError("暂不支持的分型方法（请在 config.yaml 中使用 centroid_nearest）")

        return PatientReport(
            input=payload,
            derived=derived,
            phenotype=phenotype,
            operator_doctor_id=operator_doctor_id,
            doctor_note=doctor_note,
            generated_at=now_iso(),
            app_version=self.app_version,
            model_version=self.cluster_version,
            cluster_method=self.cluster_method,
            notes=notes,
        )


def report_to_html(report: PatientReport) -> str:
    ph = report.phenotype or {}
    ph_egfr = ph.get("tyg_egfr_alb", {}) or {}
    ph_wwi = ph.get("tyg_wwi_alb", {}) or {}
    payload = report.input.to_dict()

    by = payload.get("birth_year")
    bm = payload.get("birth_month")
    bd = payload.get("birth_day")
    dob = (
        f"{by:04d}-{bm:02d}-{bd:02d}"
        if isinstance(by, int) and isinstance(bm, int) and isinstance(bd, int)
        else "未录入"
    )

    basic_rows = [
        ("Patient_ID", payload.get("patient_id")),
        ("姓名 Name", payload.get("patient_name") or "未录入"),
        ("出生日期 DOB", dob),
        ("性别 Gender", payload.get("gender")),
        ("年龄 Age", payload.get("age_years")),
        ("手机号码 Phone", payload.get("phone_number") or "未录入"),
        ("探头号 Sensor", payload.get("cgm_sensor_id") or "未录入"),
        ("身高(cm)", payload.get("height_cm")),
        ("体重(kg)", payload.get("weight_kg")),
        ("腰围(cm)", payload.get("waist_cm") if payload.get("waist_cm") is not None else "未录入"),
        ("BMI", report.derived.bmi),
        ("WWI", report.derived.wwi if report.derived.wwi is not None else "未录入"),
        ("糖尿病病程", f"{payload.get('dm_duration_years') or 0}年{payload.get('dm_duration_months') or 0}月"),
        ("FPG", f"{payload.get('fpg_value')} {payload.get('fpg_unit')}"),
        ("TG", f"{payload.get('tg_value')} {payload.get('tg_unit')}"),
        ("ALB", f"{payload.get('alb_g_l')} g/L"),
        ("Scr", f"{payload.get('scr_value')} {payload.get('scr_unit')}"),
        ("eGFR", f"{report.derived.egfr} mL/min/1.73m²"),
        ("HbA1c", f"{payload.get('hba1c_percent')} %" if payload.get("hba1c_percent") is not None else "未录入"),
    ]

    rows_html = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in basic_rows)

    exps_egfr = "；".join(ph_egfr.get("key_explanations") or [])
    exps_wwi = "；".join(ph_wwi.get("key_explanations") or [])
    principle = ph_egfr.get("principle_cn") or ("质心最近原则" if ph_egfr.get("method") == "centroid_nearest" else "未知")

    html = f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>报告_{report.input.patient_id}</title>
  <style>
    body {{ font-family: Segoe UI, Microsoft YaHei, Arial; line-height: 1.4; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ border: 1px solid #ccc; padding: 6px 10px; vertical-align: top; }}
    h2, h3 {{ margin: 12px 0 6px; }}
  </style>
</head>
<body>
  <h2>{report.app_version} / {report.model_version}</h2>
  <p>聚类原则：{principle}</p>
  <p>生成时间：{report.generated_at}；操作者：{report.operator_doctor_id}</p>
  <table>
    <tr><th>字段</th><th>数值</th></tr>
    {rows_html}
  </table>

  <h3>TyG-WWI-ALB 分型</h3>
  <p>表型{ph_wwi.get('phenotype_code') or ''}：{ph_wwi.get('phenotype_cn') or ''} / {ph_wwi.get('phenotype_en') or ''}</p>
  <p>分型解释：{exps_wwi}</p>
  <p><b>临床诊疗重点提示：</b>{ph_wwi.get('clinical_tips') or ph_wwi.get('reason') or ''}</p>

  <h3>TyG-eGFR-ALB 分型</h3>
  <p>表型{ph_egfr.get('phenotype_code') or ''}：{ph_egfr.get('phenotype_cn') or ''} / {ph_egfr.get('phenotype_en') or ''}</p>
  <p>分型解释：{exps_egfr}</p>
  <p><b>临床诊疗重点提示：</b>{ph_egfr.get('clinical_tips') or ''}</p>
</body>
</html>
"""
    return html.strip()
