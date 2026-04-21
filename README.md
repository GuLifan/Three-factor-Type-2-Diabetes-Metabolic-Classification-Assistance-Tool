# TTCAS（PySide6 / Windows）

TTCAS 为 Windows 离线桌面端应用（PySide6 + PySide6-Fluent-Widgets / qfluentwidgets），用于住院/门诊患者信息录入、指标计算、分型推断、报告导出与本地归档。  
项目采用 UI 与业务逻辑分离的架构，算法参数与界面信息外置 YAML，所有数据落盘到用户 AppData，便于升级/迁移与权限隔离。

**版本信息**：1.0.0.0  
**版权所有**：Copyright © 2026 GuLifan. All rights reserved.  
**开发单位**：The First Affiliated Hospital of Xi'an Jiaotong University  
**文件描述**：A Prediction System for Metabolic Subtypes and Treatment Responses in T2DM Patients

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

## 发布与分发

### Windows EXE 打包

TTCAS 支持打包为独立的 Windows 可执行文件，无需安装 Python 环境即可运行。

#### 打包步骤

TTCAS 支持两种打包方式：**PyInstaller**（推荐）和 **Nuitka**（备选）。PyInstaller 打包速度较快，Nuitka 生成的可执行文件性能更好但打包时间较长。

##### 使用 PyInstaller（推荐）

1. **生成可执行文件**：
   ```bash
   .\.venv\Scripts\pyinstaller.exe TTCAS_PyInstaller.spec --clean
   ```

2. **代码签名**（可选，推荐减少安全中心误报）：
   ```powershell
   # 使用 Windows SDK signtool 签名
   & "C:\Program Files (x86)\Windows Kits\10\bin\<版本>\x64\signtool.exe" sign /f "ttcas_cert.pfx" /p TTCAS123 /fd SHA256 /t "http://timestamp.digicert.com" /v "dist\TTCAS_PyInstaller.exe"
   ```

##### 使用 Nuitka（备选）

1. **安装 Nuitka**：
   ```bash
   .\.venv\Scripts\python.exe -m pip install nuitka zstandard
   ```

2. **打包为单体 EXE**：
   ```bash
   .\.venv\Scripts\python.exe -m nuitka --standalone --onefile --windows-icon-from-ico=assets\app.ico --windows-file-version=1.0.0.0 --windows-product-version=1.0.0.0 --windows-company-name="The First Affiliated Hospital of Xi'an Jiaotong University" --windows-file-description="A Prediction System for Metabolic Subtypes and Treatment Responses in T2DM Patients" --windows-legal-copyright="Copyright © 2026 GuLifan. All rights reserved." --output-filename=TTCAS.exe main.py
   ```

   > **注意**：Nuitka 打包可能需要较长时间（10-30分钟），且生成的 EXE 文件可能触发 Windows 安全中心误报，建议使用代码签名减少误报。

#### 代码签名与安全中心误报解决

新打包的 Windows EXE 文件可能被 Windows Defender 错误标记为威胁。通过以下措施可显著减少误报：

1. **嵌入完整的版本资源**：确保 EXE 文件包含公司名称、版权信息、文件描述等资源信息（通过 `version_info.txt` 实现）。
2. **代码签名**：使用数字证书对 EXE 文件进行签名，验证发布者身份。
   - **自签名证书**（测试用途）：
     ```powershell
     # 创建自签名证书
     $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=TTCAS" -KeyUsage DigitalSignature -FriendlyName "TTCAS Code Signing" -CertStoreLocation "Cert:\CurrentUser\My" -KeyExportPolicy Exportable -NotAfter (Get-Date).AddYears(1)
     Export-PfxCertificate -Cert $cert -FilePath "ttcas_cert.pfx" -Password (ConvertTo-SecureString -String "TTCAS123" -Force -AsPlainText)
     ```
   - **商业证书**（正式分发）：建议购买 DigiCert、Sectigo 等受信任的代码签名证书。
   - **签名命令**：
     ```powershell
     & "C:\Program Files (x86)\Windows Kits\10\bin\<版本>\x64\signtool.exe" sign /f "ttcas_cert.pfx" /p TTCAS123 /fd SHA256 /t "http://timestamp.digicert.com" /v "dist\TTCAS_PyInstaller.exe"
     ```
3. **提交误报报告**：若仍被误报，可向 Microsoft Defender 提交误报报告（https://www.microsoft.com/en-us/wdsi/filesubmission）。

#### 分发说明

- **打包文件**：`dist\TTCAS_PyInstaller.exe`（PyInstaller）或 `TTCAS.exe`（Nuitka）
- **版本信息**：已嵌入公司、版权、版本号等完整资源信息
- **签名状态**：支持自签名和商业证书签名
- **安全中心兼容**：通过完整版本资源和代码签名减少 Windows Defender 误报

#### 运行打包后的应用

打包生成的 EXE 文件（`dist\TTCAS_PyInstaller.exe` 或 `TTCAS.exe`）是独立的 Windows 可执行文件，无需安装 Python 环境即可运行。

1. **首次运行**：Windows 可能会显示“Windows 保护了你的电脑”警告，点击“更多信息”→“仍要运行”即可。
2. **数据目录**：应用数据仍保存在 `%APPDATA%\TTCAS\TTCASApp\` 目录下，与源码运行时的位置相同。
3. **字体与主题**：打包后的应用支持完整的字体调整、主题切换和语言切换功能。

#### 打包配置说明

- **版本资源**：`version_info.txt` 定义文件版本、公司名称、版权信息等
- **包含资源**：自动包含 `config.yaml`、`assets/` 目录、用户手册等文件
- **应用图标**：使用 `assets\app.ico` 作为 Windows 图标

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

## 测试（push 前强烈建议）

### 全量单元/冒烟测试

```bash
.\.venv\Scripts\python.exe -m unittest -v
```

### 极限压力测试（默认至少 1800s）

```bash
.\.venv\Scripts\python.exe .\tests\stress_tester.py --min-seconds 1800 --iterations 5000 --snapshot-interval 120
```

输出目录：`tests/_artifacts/`（已在 `.gitignore` 忽略）
- `stress_report.json`：动作序列与异常记录
- `snapshot_*.png`：周期截图
- `crash_*.png`：异常现场截图（若发生）
- `app.log`：压力测试器日志（独立于 AppData）

---

## 常见问题

- 主题/字体/语言切换后控件颜色不一致：优先查看 `logs/app.log`；压力测试器也会保留截图与报告便于复现。
- CGM 计算依赖：需要 `numpy`、`pandas`、`openpyxl`，缺失会在界面提示并写入日志。

---

## License

GNU GPL v3
