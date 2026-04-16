from __future__ import annotations

# 本地存储（TTCAS）
# - 账号库：AppData/config/doctor_accounts.json
# - 患者归档：AppData/data/patients/*.json
# - 目标：保证“写入原子性/可恢复性”，并兼容部分历史格式

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ttcas_app.domain import DoctorAccount, PatientReport, now_iso


def _read_json_file(path: Path) -> Any:
    # 读取 JSON 文件（不存在/空内容时返回 None）
    if not path.exists():
        return None
    txt = path.read_text(encoding="utf-8")
    if not txt.strip():
        return None
    return json.loads(txt)


def _write_json_file(path: Path, data: Any) -> None:
    # 写入 JSON 文件（确保父目录存在；格式化缩进便于人工排查）
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _backup_file(path: Path) -> Path:
    # 对“将要被覆盖”的文件做备份：用于现场应急回滚
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak_{ts}")
    if path.exists():
        shutil.copy2(path, backup)
    return backup


def sha256_hex(text: str) -> str:
    # 密码哈希：单向不可逆（注意：此处未加盐，仅用于离线场景基础保护）
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _password_matches(stored: str, plain: str) -> bool:
    """
    兼容两种存储形态：
    - 明文（早期/临时）：stored == plain
    - sha256 前缀：stored == "sha256:<hex>"
    """

    s = str(stored).strip()
    p = str(plain).strip()
    if s.startswith("sha256:"):
        return s == f"sha256:{sha256_hex(p)}"
    return s == p


@dataclass
class DoctorAccountsStore:
    """
    医师账号库（本地 JSON）：
    - 设计目标：完全离线可用
    - 安全说明：当前为“轻量方案”，仅满足本机离线使用场景（并非强安全）
    """

    file_path: Path

    def ensure_default_file(self) -> None:
        if self.file_path.exists():
            return
        demo = DoctorAccount(
            doctor_id="demo_doctor",
            organization=None,
            department=None,
            password=f"sha256:{sha256_hex('123456')}",
            created_at=now_iso(),
        )
        _write_json_file(self.file_path, {"accounts": [demo.to_dict()]})

    def list_accounts(self) -> list[DoctorAccount]:
        raw = _read_json_file(self.file_path)
        if raw is None:
            return []

        # 兼容旧结构：可能直接是 list，也可能键名不同
        items: list[Any]
        if isinstance(raw, dict):
            items = list(raw.get("accounts") or raw.get("doctors") or [])
        elif isinstance(raw, list):
            items = raw
        else:
            raise ValueError("账号库格式错误：根节点必须是 dict 或 list")

        out: list[DoctorAccount] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            try:
                out.append(DoctorAccount.from_dict(it))
            except Exception:
                continue
        return out

    def _save_accounts(self, accounts: list[DoctorAccount]) -> None:
        _write_json_file(self.file_path, {"accounts": [a.to_dict() for a in accounts]})

    def register(
        self, *, doctor_id: str, password: str, organization: str | None = None, department: str | None = None
    ) -> DoctorAccount:
        did = str(doctor_id).strip()
        pwd = str(password).strip()
        if not did:
            raise ValueError("Doctor_ID 不能为空")
        if not pwd:
            raise ValueError("Password 不能为空")
        if len(did) < 6 or len(did) > 20:
            raise ValueError("Doctor_ID 长度必须在 6~20 之间")
        if len(pwd) < 6 or len(pwd) > 20:
            raise ValueError("Password 长度必须在 6~20 之间")

        accounts = self.list_accounts()
        if any(a.doctor_id == did for a in accounts):
            raise ValueError("该 Doctor_ID 已存在")

        org = str(organization).strip() if organization is not None else None
        dep = str(department).strip() if department is not None else None
        acct = DoctorAccount(
            doctor_id=did,
            organization=org or None,
            department=dep or None,
            password=f"sha256:{sha256_hex(pwd)}",
            created_at=now_iso(),
        )
        accounts.append(acct)
        self._save_accounts(accounts)
        return acct

    def authenticate(self, *, doctor_id: str, password: str) -> bool:
        did = str(doctor_id).strip()
        pwd = str(password).strip()
        for a in self.list_accounts():
            if a.doctor_id == did and _password_matches(a.password, pwd):
                return True
        return False

    def migrate_from_old_file_if_needed(self, old_path: Path) -> bool:
        """
        自动迁移旧版账号库：
        - 条件：新文件不存在，旧文件存在且可解析出账号
        - 行为：备份旧文件，然后把可解析账号写入新结构
        """

        if self.file_path.exists():
            return False
        if not old_path.exists():
            return False

        raw = _read_json_file(old_path)
        if raw is None:
            return False

        candidates: list[Any]
        if isinstance(raw, dict):
            candidates = list(raw.get("accounts") or raw.get("doctors") or raw.get("items") or [])
        elif isinstance(raw, list):
            candidates = raw
        else:
            return False

        accounts: list[DoctorAccount] = []
        for it in candidates:
            if not isinstance(it, dict):
                continue
            try:
                accounts.append(DoctorAccount.from_dict(it))
            except Exception:
                continue

        if not accounts:
            return False

        _backup_file(old_path)
        self._save_accounts(accounts)
        return True


@dataclass
class PatientArchiveStore:
    """
    患者归档（每次评估写一个 JSON 文件）：
    - 每个 Patient_ID 在 3 分钟内重复归档：覆盖最近一次（便于“纠错后重存”）
    - 文件名包含时间戳，便于按时间顺序展示
    """

    patients_dir: Path

    def list_files(self) -> list[Path]:
        if not self.patients_dir.exists():
            return []
        return sorted(self.patients_dir.glob("*.json"), key=lambda p: p.name, reverse=True)

    def load(self, path: Path) -> dict[str, Any]:
        raw = _read_json_file(path)
        if not isinstance(raw, dict):
            raise ValueError("归档文件格式错误：根节点必须是 dict")
        return raw

    def save_report(self, report: PatientReport) -> Path:
        self.patients_dir.mkdir(parents=True, exist_ok=True)
        pid = report.input.patient_id.strip()
        if not pid:
            raise ValueError("Patient_ID 不能为空")

        overwrite_target: Path | None = None
        now_dt = datetime.now()
        window = timedelta(minutes=3)

        for p in self.list_files():
            try:
                d = self.load(p)
            except Exception:
                continue
            inp = d.get("input") or {}
            if isinstance(inp, dict) and str(inp.get("patient_id") or "").strip() == pid:
                ts = str(d.get("generated_at") or d.get("generatedAt") or "").strip()
                try:
                    gen_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    gen_dt = None
                if gen_dt is not None and abs(now_dt - gen_dt) <= window:
                    overwrite_target = p
                break

        if overwrite_target is None:
            stamp = now_dt.strftime("%Y%m%d_%H%M%S")
            safe_pid = "".join(ch for ch in pid if ch.isalnum() or ch in ("-", "_"))
            if not safe_pid:
                safe_pid = "patient"
            overwrite_target = self.patients_dir / f"{safe_pid}_{stamp}.json"

        data = report.to_dict()
        _write_json_file(overwrite_target, data)
        return overwrite_target

    def find_latest_record_for_patient(self, patient_id: str) -> tuple[str, dict[str, Any]] | None:
        pid = str(patient_id).strip()
        if not pid:
            return None
        for p in self.list_files():
            try:
                d = self.load(p)
            except Exception:
                continue
            inp = d.get("input") or {}
            if isinstance(inp, dict) and str(inp.get("patient_id") or "").strip() == pid:
                return p.name, d
        return None
