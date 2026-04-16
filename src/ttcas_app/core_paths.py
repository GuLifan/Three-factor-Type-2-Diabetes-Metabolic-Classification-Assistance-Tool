from __future__ import annotations

# AppData 路径约定（TTCAS）
# - 所有“用户数据/日志/归档”都写入 QStandardPaths.AppDataLocation
# - 这样可以避免写入安装目录导致权限问题，也方便迁移与升级

from dataclasses import dataclass
from pathlib import Path

# QStandardPaths：Qt 提供的跨平台“标准目录”定位（会受到组织名/应用名影响）
from PySide6.QtCore import QStandardPaths


@dataclass(frozen=True)
class AppPaths:
    """
    约定：所有落盘数据都写入 AppData（Roaming），便于：
    - 免管理员权限写入
    - 与打包后的安装目录解耦
    - 升级/卸载不丢数据（取决于安装器策略）
    """

    app_data_dir: Path
    logs_dir: Path
    data_dir: Path
    config_dir: Path
    patients_dir: Path

    def ensure_dirs(self) -> None:
        # 确保所有目录存在：日志、数据、配置、患者归档
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.patients_dir.mkdir(parents=True, exist_ok=True)


def get_app_paths() -> AppPaths:
    """
    这里依赖 Qt：因为 QStandardPaths 会受到 organization/application 的影响。
    因此调用顺序必须是：
    - QApplication.setOrganizationName / setApplicationName 之后
    - 再调用本函数
    """

    # AppDataLocation 通常是：
    # C:\Users\<User>\AppData\Roaming\<Organization>\<Application>\
    base = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    # 日志目录：滚动日志 app.log
    logs_dir = base / "logs"
    # 数据目录：业务数据根目录
    data_dir = base / "data"
    # 配置目录：账号库等
    config_dir = base / "config"
    # 患者归档目录：每次生成一个 JSON
    patients_dir = data_dir / "patients"
    return AppPaths(
        app_data_dir=base,
        logs_dir=logs_dir,
        data_dir=data_dir,
        config_dir=config_dir,
        patients_dir=patients_dir,
    )
