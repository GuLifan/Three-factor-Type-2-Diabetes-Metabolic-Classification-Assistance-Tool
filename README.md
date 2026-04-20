# TTCAS（PySide6 / Windows）

TTCAS 为 Windows 离线桌面端应用（PySide6 + PySide6-Fluent-Widgets / qfluentwidgets），用于住院/门诊患者信息录入、指标计算、分型推断、报告导出与本地归档。  
项目采用 UI 与业务逻辑分离的架构，算法参数与界面信息外置 YAML，所有数据落盘到用户 AppData，便于升级/迁移与权限隔离。

---

## 功能概览

- 医师账号：本地注册/登录（离线），账号库落盘到 AppData
- 患者信息页：
  - 严格输入校验（年龄/身高/体重/腰围/化验指标等，离开输入框即提示）
  - 指标计算（BMI、TyG、eGFR 自动补齐、WWI 等）
  - 生成并归档（同一 Patient_ID 在 3 分钟内重复归档只保留最后一次）
  - 导出 HTML、导出 PDF（文件名默认 PatientID+时间）
- 常用计算（Tools）：
  - BMI/WWI、病程估算、eGFR 多公式、血糖单位换算与 HbA1c 估算、CGM 动态指标计算
- 患者归档（Archive）：
  - AppData patients 目录列表
  - 右侧预览 JSON 内容，支持加载回患者页
- 设置（Settings）：
  - 字体大小、主题模式、语言切换（中/英）
  - 快捷入口（打开目录/外部归档/说明与手册/关于信息）

---

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.10+（开发环境可用 3.13+）

### 安装依赖

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 启动

```bash
.\.venv\Scripts\python.exe main.py
```

---

## 配置（config.yaml）

- 默认读取：仓库根目录 `config.yaml`
- 可选环境变量：`TTCAS_CONFIG` 指向配置文件绝对路径

常用配置字段（摘要）：
- `app.*`：应用信息（组织/应用名、展示名、窗口标题、版本号）
- `model.*`：分型参数（μ/σ、质心、版本号、方法）
- `ui.*`：默认主题/字体、图标路径、说明与关于信息

---

## 数据落盘（AppData）

默认写入 `QStandardPaths.AppDataLocation`（受 `organization_name/application_name` 影响），典型路径：

`C:\Users\<User>\AppData\Roaming\TTCAS\TTCASApp\`

目录结构：
- `logs/app.log`：滚动日志（错误堆栈与关键操作链路）
- `config/doctor_accounts.json`：医师账号库
- `data/patients/*.json`：患者归档（每次生成一个文件）

---

## 项目结构

```
TTCAS/
  main.py
  config.yaml
  requirements.txt
  assets/
  src/
    ttcas_app/
      app.py                 # 应用启动与全局初始化（DPI/主题/字体/异常处理）
      ui_main.py             # 主窗口（导航/页面切换/主题语言联动）
      ui_pages_patient.py    # 患者信息/报告页
      ui_pages_tools.py      # 常用计算/CGM
      ui_pages_archive.py    # 归档页（列表+预览）
      ui_pages_settings.py   # 设置页
      domain.py              # 业务逻辑（校验/计算/分型/报告导出）
      storage.py             # 本地存储（账号库/归档）
      cgm_metrics.py         # CGM 计算（Excel/CSV）
      core_settings.py       # QSettings（字体/主题/语言）
      core_paths.py          # AppData 路径约定
      core_logging.py        # 滚动日志
  tests/
    test_ui_smoke.py         # UI 冒烟：主题/语言/字体/校验/生成归档
    test_domain_fuzz.py      # 业务层模糊/边界测试
    test_storage_extreme.py  # 存储极限测试
    stress_tester.py         # 极限压力测试器（随机操作/非法字符/截图/报告）
```

---


## 常见问题

- 主题/字体/语言切换后控件颜色不一致：优先查看 `logs/app.log`；压力测试器也会保留截图与报告便于复现。
- CGM 计算依赖：需要 `numpy`、`pandas`、`openpyxl`，缺失会在界面提示并写入日志。

---

## License

GNU GPL v3
