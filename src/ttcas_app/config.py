from __future__ import annotations

# 配置读取与结构化（TTCAS）
# - 入口：load_config(repo_root=...)
# - 约定：默认读取仓库根目录 config.yaml；也可用环境变量 TTCAS_CONFIG 指定绝对路径
# - 输出：AppConfig（强类型 dataclass），供 UI/业务层统一使用

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppMeta:
    organization_name: str
    application_name: str
    application_display_name: str
    window_title: str
    app_version: str


@dataclass(frozen=True)
class ModelConfig:
    cluster_version: str
    method: str

    zscore_mean: dict[str, float]
    zscore_std: dict[str, float]
    centroids_z: list[dict[str, float]]

    zscore_mean_wwi: dict[str, float]
    zscore_std_wwi: dict[str, float]
    centroids_z_wwi: list[dict[str, float]]


@dataclass(frozen=True)
class AboutConfig:
    version_info: str
    dev_info: str
    contact_dev: str


@dataclass(frozen=True)
class UiConfig:
    icon_path: str
    font_point_size: int
    theme_default: str
    cluster_principle_image: str
    about: AboutConfig


@dataclass(frozen=True)
class AppConfig:
    app: AppMeta
    model: ModelConfig
    ui: UiConfig
    config_file: Path
    repo_root: Path

    def resolve_path(self, path_value: str) -> Path:
        p = Path(path_value)
        if p.is_absolute():
            return p
        return (self.repo_root / p).resolve()


def _require_yaml() -> Any:
    try:
        import yaml  # type: ignore
    except Exception as ex:
        raise RuntimeError("缺少依赖 PyYAML：请先安装 requirements.txt 后再运行。") from ex
    return yaml


def _as_float_dict(d: Any, *, name: str) -> dict[str, float]:
    if not isinstance(d, dict):
        raise ValueError(f"配置字段 {name} 必须是 dict")
    out: dict[str, float] = {}
    for k, v in d.items():
        if v is None:
            continue
        out[str(k)] = float(v)
    return out


def _as_centroids(lst: Any, *, name: str) -> list[dict[str, float]]:
    if not isinstance(lst, list) or not lst:
        raise ValueError(f"配置字段 {name} 必须是非空 list")
    out: list[dict[str, float]] = []
    for i, item in enumerate(lst):
        if not isinstance(item, dict):
            raise ValueError(f"配置字段 {name}[{i}] 必须是 dict")
        out.append({str(k): float(v) for k, v in item.items() if v is not None})
    return out


def load_config(*, repo_root: Path) -> AppConfig:
    env_path = os.environ.get("TTCAS_CONFIG", "").strip()
    if env_path:
        cfg_path = Path(env_path)
    else:
        cfg_path = repo_root / "config.yaml"

    if not cfg_path.exists():
        raise FileNotFoundError(f"未找到配置文件：{cfg_path}")

    yaml = _require_yaml()
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("配置文件根节点必须是 dict")

    app0 = raw.get("app") or {}
    model0 = raw.get("model") or {}
    ui0 = raw.get("ui") or {}
    about0 = (ui0.get("about") or {}) if isinstance(ui0, dict) else {}

    app = AppMeta(
        organization_name=str(app0.get("organization_name") or "TTCAS"),
        application_name=str(app0.get("application_name") or "TTCASApp"),
        application_display_name=str(app0.get("application_display_name") or "TTCAS"),
        window_title=str(app0.get("window_title") or "TTCAS"),
        app_version=str(app0.get("app_version") or "2.0"),
    )

    model = ModelConfig(
        cluster_version=str(model0.get("cluster_version") or "2.0"),
        method=str(model0.get("method") or "centroid_nearest"),
        zscore_mean=_as_float_dict(model0.get("zscore_mean") or {}, name="model.zscore_mean"),
        zscore_std=_as_float_dict(model0.get("zscore_std") or {}, name="model.zscore_std"),
        centroids_z=_as_centroids(model0.get("centroids_z") or [], name="model.centroids_z"),
        zscore_mean_wwi=_as_float_dict(model0.get("zscore_mean_wwi") or {}, name="model.zscore_mean_wwi"),
        zscore_std_wwi=_as_float_dict(model0.get("zscore_std_wwi") or {}, name="model.zscore_std_wwi"),
        centroids_z_wwi=_as_centroids(model0.get("centroids_z_wwi") or [], name="model.centroids_z_wwi"),
    )

    about = AboutConfig(
        version_info=str(about0.get("version_info") or ""),
        dev_info=str(about0.get("dev_info") or ""),
        contact_dev=str(about0.get("contact_dev") or ""),
    )

    ui = UiConfig(
        icon_path=str(ui0.get("icon_path") or ""),
        font_point_size=int(ui0.get("font_point_size") or 11),
        theme_default=str(ui0.get("theme_default") or "light"),
        cluster_principle_image=str(ui0.get("cluster_principle_image") or ""),
        about=about,
    )

    return AppConfig(app=app, model=model, ui=ui, config_file=cfg_path.resolve(), repo_root=repo_root)
