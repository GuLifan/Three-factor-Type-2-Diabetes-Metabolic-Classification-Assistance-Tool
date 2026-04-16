from __future__ import annotations

# i18n 文案表（TTCAS）
# - 约定：全局中英切换；中文界面关键标签带英文（按需求）
# - TextPair 负责按 lang 输出对应语言文本

from dataclasses import dataclass


Lang = str


@dataclass(frozen=True)
class TextPair:
    # 一条文案的中英文版本
    zh: str
    en: str

    def render(self, lang: Lang) -> str:
        # lang == "en" 输出英文，否则默认输出中文
        if lang == "en":
            return self.en
        return self.zh


TEXT: dict[str, TextPair] = {
    "nav_patient": TextPair("患者信息", "Patient"),
    "nav_tools": TextPair("常用计算", "Tools"),
    "nav_archive": TextPair("患者归档", "Archive"),
    "nav_settings": TextPair("设置", "Settings"),
    "nav_about_version": TextPair("版本信息", "Version"),
    "nav_about_dev": TextPair("开发信息", "Development"),
    "nav_about_contact": TextPair("联系开发者", "Contact"),
    "login_title": TextPair("医师登录", "Doctor Sign In"),
    "login_doctor_id": TextPair("账号", "Account"),
    "login_password": TextPair("密码", "Password"),
    "login_btn": TextPair("登录", "Sign In"),
    "register_btn": TextPair("注册", "Sign Up"),
    "register_title": TextPair("注册新账号", "Create Account"),
    "org_label": TextPair("单位", "Organization"),
    "dept_label": TextPair("科室", "Department"),
    "confirm_password": TextPair("确认密码", "Confirm Password"),
    "btn_save": TextPair("保存", "Save"),
    "btn_cancel": TextPair("取消", "Cancel"),
    "patient_title": TextPair("患者信息与分型报告", "Patient Profile & Report"),
    "section_basic": TextPair("基本信息", "Basic Info"),
    "section_body": TextPair("体格指标", "Anthropometrics"),
    "section_history": TextPair("病史/并发症", "History / Complications"),
    "section_labs": TextPair("检验指标（用于分型）", "Labs (for typing)"),
    "pid_label": TextPair("住院号/门诊号", "Patient ID"),
    "name_label": TextPair("姓名", "Name"),
    "gender_label": TextPair("性别", "Gender"),
    "dob_label": TextPair("出生日期", "DOB"),
    "age_label": TextPair("年龄", "Age"),
    "phone_label": TextPair("手机号", "PhoneNo."),
    "sensor_label": TextPair("探头号", "SensorNo."),
    "height_label": TextPair("身高(cm)", "Height (cm)"),
    "weight_label": TextPair("体重(kg)", "Weight (kg)"),
    "bmi_label": TextPair("BMI", "BMI"),
    "waist_label": TextPair("腰围(cm)", "Waist (cm)"),
    "history_title": TextPair("病史/并发症", "History / Complications"),
    "dm_duration_label": TextPair("糖尿病病程", "DM Duration"),
    "dm_dx_date_label": TextPair("首次确诊年月", "Dx Year/Month"),
    "dm_year_label": TextPair("年", "Year"),
    "dm_month_label": TextPair("月", "Month"),
    "lab_title": TextPair("检验指标（用于分型）", "Labs (for typing)"),
    "fpg_label": TextPair("FPG", "FPG"),
    "tg_label": TextPair("TG", "TG"),
    "alb_label": TextPair("ALB(g/L)", "ALB (g/L)"),
    "scr_label": TextPair("Scr", "Scr"),
    "egfr_label": TextPair("eGFR", "eGFR"),
    "hba1c_label": TextPair("HbA1c(%)", "HbA1c (%)"),
    "note_title": TextPair("医师备注", "Doctor Notes"),
    "result_title": TextPair("报告摘要（界面预览）", "Report Summary (Preview)"),
    "gen_archive_btn": TextPair("生成并归档", "Generate & Archive"),
    "export_html_btn": TextPair("导出HTML", "Export HTML"),
    "print_pdf_btn": TextPair("导出PDF", "Export PDF"),
    "tools_bmi_title": TextPair("BMI 与 WWI（体重校正腰围指数）", "BMI & WWI"),
    "tools_duration_title": TextPair("病程估算（首次确诊日期 → 当前）", "DM Duration Estimator"),
    "tools_egfr_title": TextPair("eGFR / CrCl 计算器（多公式）", "eGFR / CrCl (Multi-Formula)"),
    "tools_unit_title": TextPair("血糖单位换算与HbA1c估算", "Glucose Unit & HbA1c Estimation"),
    "tools_cgm_title": TextPair("CGM 动态计算器（后台线程）", "CGM Metrics (Background)"),
    "settings_title": TextPair("全局控制中心", "Control Center"),
    "settings_block_ui": TextPair("界面（字体/主题/语言）", "UI (Font/Theme/Language)"),
    "settings_block_paths": TextPair("快捷入口（目录/外部归档）", "Shortcuts (Folders/External JSON)"),
    "settings_block_docs": TextPair("说明与手册", "Guides"),
    "settings_font": TextPair("界面字体大小", "Font Size"),
    "settings_theme": TextPair("主题模式", "Theme"),
    "settings_theme_light": TextPair("浅色", "Light"),
    "settings_theme_dark": TextPair("深色", "Dark"),
    "settings_lang": TextPair("语言", "Language"),
    "settings_lang_zh": TextPair("中文", "Chinese"),
    "settings_lang_en": TextPair("英语", "English"),
    "btn_open_external_archive": TextPair("打开外部归档JSON", "Open External Archive JSON"),
    "btn_open_config": TextPair("打开config目录", "Open config folder"),
    "btn_open_patients": TextPair("打开patients目录", "Open patients folder"),
    "btn_open_logs": TextPair("打开log目录", "Open logs folder"),
    "btn_cluster": TextPair("聚类原则说明", "Typing Principle"),
    "btn_tools": TextPair("计算器说明", "Tools Guide"),
    "btn_manual": TextPair("用户手册(PDF)", "User Manual (PDF)"),
    "archive_title": TextPair("患者归档", "Archive"),
    "archive_refresh": TextPair("刷新", "Refresh"),
    "archive_load": TextPair("加载到患者页", "Load to Patient"),
    "archive_preview": TextPair("右侧预览", "Preview"),
}


def ui_text(key: str, lang: Lang) -> str:
    p = TEXT.get(key)
    if p is None:
        return key
    return p.render(lang)


def gender_items(lang: Lang) -> list[tuple[str, str]]:
    if lang == "en":
        return [("男", "Male"), ("女", "Female")]
    return [("男", "男"), ("女", "女")]
