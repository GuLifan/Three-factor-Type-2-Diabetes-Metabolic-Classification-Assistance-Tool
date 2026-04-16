from __future__ import annotations

# CGM 动态计算器（TTCAS）
# 目标：
# - 读取 Excel/CSV，自动识别“时间列”和“血糖值列”
# - 计算整段记录期的常用指标（MEAN/SD/CV/GMI/TIR/TAR/TBR/LBGI/HBGI/ADRR/MODD/LAGE/MAGE 等）
# - 该模块保持“纯业务层”：不依赖 PySide6，便于单元测试与复用

import math
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


class CgmError(Exception):
    pass


class CgmCancelledError(CgmError):
    pass


class CgmInputError(CgmError, ValueError):
    pass


class CgmFileNotFoundError(CgmInputError):
    pass


class CgmHeaderMismatchError(CgmInputError):
    pass


def _check_cancel(cancel_check) -> None:
    if cancel_check is None:
        return
    cancel_check()


def _require_deps() -> tuple[Any, Any]:
    try:
        import numpy as np  # type: ignore
        import pandas as pd  # type: ignore
    except Exception as ex:
        raise RuntimeError("CGM动态计算器依赖未安装：请安装 numpy、pandas、openpyxl 后重试。") from ex
    return np, pd


def load_cgm_dataframe(file_path: str | Path, *, strict_header: bool = True, cancel_check=None):
    np, pd = _require_deps()
    _check_cancel(cancel_check)
    path = Path(file_path)
    if not path.exists():
        raise CgmFileNotFoundError(f"文件不存在：{path}")
    suffix = path.suffix.lower()

    def _infer_time_glucose_indices(df0) -> tuple[int, int, float, float, bool]:
        cols_lower = [str(c).strip().lower() for c in df0.columns]
        ts_idx: int | None = None
        gl_idx: int | None = None
        ts_score_by_name = 0.0
        gl_score_by_name = 0.0

        for i, name in enumerate(cols_lower):
            if name in ["t"] or any(k in name for k in ["timestamp", "time", "datetime", "日期", "时间"]):
                ts_idx = i
                ts_score_by_name = 1.0
            if name in ["v"] or any(k in name for k in ["glucose", "bg", "sg", "血糖", "value", "val"]):
                gl_idx = i
                gl_score_by_name = 1.0

        sample = df0.head(50)
        ts_score = ts_score_by_name
        if ts_idx is None:
            best_score = -1.0
            best_i = 0
            for i in range(df0.shape[1]):
                dt = pd.to_datetime(sample.iloc[:, i], errors="coerce")
                score = float(dt.notna().mean()) if len(dt) else 0.0
                if score > best_score:
                    best_score = score
                    best_i = i
            if best_score >= 0.6:
                ts_idx = best_i
                ts_score = best_score
        else:
            dt = pd.to_datetime(sample.iloc[:, ts_idx], errors="coerce")
            ts_score = max(ts_score_by_name, float(dt.notna().mean()) if len(dt) else 0.0)

        gl_score = gl_score_by_name
        if gl_idx is None:
            best_score = -1.0
            best_i = 1 if df0.shape[1] > 1 else 0
            for i in range(df0.shape[1]):
                if ts_idx is not None and i == ts_idx:
                    continue
                nums = pd.to_numeric(sample.iloc[:, i], errors="coerce")
                score = float(nums.notna().mean()) if len(nums) else 0.0
                if score > best_score:
                    best_score = score
                    best_i = i
            if best_score >= 0.6:
                gl_idx = best_i
                gl_score = best_score
        else:
            nums = pd.to_numeric(sample.iloc[:, gl_idx], errors="coerce")
            gl_score = max(gl_score_by_name, float(nums.notna().mean()) if len(nums) else 0.0)

        if ts_idx is None:
            ts_idx = 0
        if gl_idx is None:
            gl_idx = 1 if df0.shape[1] > 1 else 0
        if gl_idx == ts_idx and df0.shape[1] > 1:
            gl_idx = 1 if ts_idx != 1 else 0
        return ts_idx, gl_idx, ts_score, gl_score, bool(ts_score_by_name >= 1.0 and gl_score_by_name >= 1.0)

    def _validate_columns(ts_s, gl_s) -> None:
        if not strict_header:
            return
        if len(ts_s) == 0 or len(gl_s) == 0:
            raise CgmHeaderMismatchError("表头不匹配：无法识别时间列/血糖列（空列）")
        ts_ok = float(pd.to_datetime(ts_s, errors="coerce").notna().mean())
        gl_ok = float(pd.to_numeric(gl_s, errors="coerce").notna().mean())
        if ts_ok < 0.5 or gl_ok < 0.5:
            raise CgmHeaderMismatchError("表头不匹配：无法识别时间列/血糖列（请使用包含 t/v 或 时间/血糖 的表头）")

    if suffix == ".csv":
        _check_cancel(cancel_check)
        df = pd.read_csv(path)
        if df.shape[1] < 2:
            raise ValueError("CSV列数不足，至少需要两列：时间、血糖")

        cols = [str(c).strip().lower() for c in df.columns]
        ts_idx = None
        gl_idx = None
        for i, name in enumerate(cols):
            if name in ["t"] or any(k in name for k in ["timestamp", "time", "datetime", "日期", "时间"]):
                ts_idx = i
            if name in ["v"] or any(k in name for k in ["glucose", "bg", "sg", "血糖"]):
                gl_idx = i
        if ts_idx is None or gl_idx is None:
            if strict_header:
                raise CgmHeaderMismatchError("表头不匹配：请使用包含 t/v 或 时间/血糖 的表头（CSV）")
            ts_idx2, gl_idx2, _, _, _ = _infer_time_glucose_indices(df)
            ts_idx, gl_idx = ts_idx2, gl_idx2
        df = df.iloc[:, [int(ts_idx), int(gl_idx)]].copy()
        df.columns = ["timestamp", "glucose"]
    else:
        _check_cancel(cancel_check)
        try:
            raw0 = pd.read_excel(path, header=0)
        except Exception:
            raw0 = None

        if raw0 is not None and raw0.shape[1] >= 2:
            ts_idx, gl_idx, _, _, by_name = _infer_time_glucose_indices(raw0)
            if strict_header and not by_name:
                raise CgmHeaderMismatchError("表头不匹配：请使用包含 t/v 或 时间/血糖 的表头（Excel）")
            df = raw0.iloc[:, [ts_idx, gl_idx]].copy()
            df.columns = ["timestamp", "glucose"]
        else:
            _check_cancel(cancel_check)
            raw = pd.read_excel(path, header=None)
            if raw.shape[1] < 2:
                raise ValueError("Excel列数不足，至少需要两列：时间、血糖")

            if raw.shape[0] >= 1:
                dropped = False
                a0 = raw.iloc[0, 0]
                a1 = raw.iloc[0, 1]
                if isinstance(a0, str) or isinstance(a1, str):
                    head = f"{a0} {a1}".lower()
                    if any(
                        k in head
                        for k in [
                            "timestamp",
                            "time",
                            "datetime",
                            "日期",
                            "时间",
                            "glucose",
                            "血糖",
                            " t ",
                            " v ",
                        ]
                    ):
                        raw = raw.drop(index=0).reset_index(drop=True)
                        dropped = True
                if strict_header and not dropped:
                    raise CgmHeaderMismatchError("表头不匹配：请使用包含 t/v 或 时间/血糖 的表头（Excel）")

            raw = raw.iloc[:, :2].copy()
            raw.columns = ["timestamp", "glucose"]
            df = raw

    _validate_columns(df["timestamp"], df["glucose"])

    _check_cancel(cancel_check)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df["glucose"] = pd.to_numeric(df["glucose"], errors="coerce")
    df = df.dropna(subset=["glucose"]).copy()
    df["glucose"] = df["glucose"].clip(1.8, 33.3)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _calc_basic_stats(df) -> dict[str, float | None]:
    np, _ = _require_deps()
    if df.empty:
        return {"MEAN": None, "SD": None, "CV": None, "GMI": None}

    g = df["glucose"]
    mean_val = float(g.mean())
    std_val = float(g.std())
    cv_val = round(std_val / mean_val, 4) if mean_val and not np.isnan(mean_val) else None
    gmi_val = round(3.31 + 0.02392 * 18 * mean_val, 4) if not np.isnan(mean_val) else None

    return {
        "MEAN": round(mean_val, 4) if not np.isnan(mean_val) else None,
        "SD": round(std_val, 4) if not np.isnan(std_val) else None,
        "CV": cv_val,
        "GMI": gmi_val,
    }


def _calc_lbgi_hbgi_adrr(df) -> tuple[float | None, float | None, float | None]:
    np, _ = _require_deps()
    if df.empty:
        return None, None, None

    df = df.sort_values("timestamp").copy()
    start_time = df["timestamp"].iloc[0]
    df["day_idx"] = ((df["timestamp"] - start_time).dt.total_seconds() // 86400).astype(int)
    total_seconds = float((df["timestamp"].iloc[-1] - start_time).total_seconds())
    num_full_days = int(total_seconds // 86400)
    valid_df = df[df["day_idx"] < num_full_days].copy()
    if valid_df.empty:
        return None, None, None

    valid_df = valid_df[valid_df["glucose"] >= 1.0].copy()
    if valid_df.empty:
        return None, None, None

    valid_df["fBG"] = 1.794 * (np.log(valid_df["glucose"]) ** 1.026 - 1.861)
    valid_df["risk"] = 10 * (valid_df["fBG"] ** 2)
    valid_df["rl"] = np.where(valid_df["fBG"] < 0, valid_df["risk"], 0)
    valid_df["rh"] = np.where(valid_df["fBG"] > 0, valid_df["risk"], 0)

    daily_stats = valid_df.groupby("day_idx").agg(
        mean_rl=("rl", "mean"),
        mean_rh=("rh", "mean"),
        max_rl=("rl", "max"),
        max_rh=("rh", "max"),
    )
    daily_stats["daily_adrr"] = daily_stats["max_rl"] + daily_stats["max_rh"]

    final_lbgi = float(daily_stats["mean_rl"].mean())
    final_hbgi = float(daily_stats["mean_rh"].mean())
    final_adrr = float(daily_stats["daily_adrr"].mean())

    return round(final_lbgi, 4), round(final_hbgi, 4), round(final_adrr, 4)


def _calc_modd(df) -> float | None:
    np, _ = _require_deps()
    if df.empty:
        return None

    df = df.sort_values("timestamp").copy()
    start_time = df["timestamp"].iloc[0]
    total_seconds = float((df["timestamp"].iloc[-1] - start_time).total_seconds())
    num_full_days = int(total_seconds // 86400)
    if num_full_days < 2:
        return None

    df["day_idx"] = ((df["timestamp"] - start_time).dt.total_seconds() // 86400).astype(int)
    valid_df = df[df["day_idx"] < num_full_days].copy()
    valid_df["time_key"] = valid_df["timestamp"].dt.strftime("%H:%M")
    pivot = valid_df.pivot_table(index="time_key", columns="day_idx", values="glucose")
    diffs = pivot.diff(axis=1).abs()
    daily_modd = diffs.mean()
    valid_modds = daily_modd.dropna()
    if valid_modds.empty:
        return None
    val = float(valid_modds.mean())
    return round(val, 4) if not np.isnan(val) else None


def _calc_mage_daily(glucose_series) -> float | None:
    np, _ = _require_deps()
    data = glucose_series.dropna().values
    if len(data) < 3:
        return None

    sd = float(np.std(data, ddof=1))
    if sd == 0:
        return 0.0

    peaks: list[tuple[int, float]] = []
    nadirs: list[tuple[int, float]] = []
    for i in range(1, len(data) - 1):
        if data[i] > data[i - 1] and data[i] > data[i + 1]:
            peaks.append((i, float(data[i])))
        elif data[i] < data[i - 1] and data[i] < data[i + 1]:
            nadirs.append((i, float(data[i])))

    if not peaks or not nadirs:
        return None

    turning_points = sorted(peaks + nadirs, key=lambda x: x[0])
    first_valid_direction: int | None = None
    mage_sum = 0.0
    mage_count = 0

    for i in range(1, len(turning_points)):
        current_val = turning_points[i][1]
        prev_val = turning_points[i - 1][1]
        diff = current_val - prev_val
        amplitude = abs(diff)
        if amplitude > sd:
            direction = 1 if diff > 0 else -1
            if first_valid_direction is None:
                first_valid_direction = direction
                mage_sum += amplitude
                mage_count += 1
            elif direction == first_valid_direction:
                mage_sum += amplitude
                mage_count += 1

    if mage_count == 0:
        return None
    return mage_sum / mage_count


def _calc_lage_mage(df) -> tuple[float | None, float | None]:
    np, _ = _require_deps()
    if df.empty:
        return None, None

    df = df.sort_values("timestamp").copy()
    start_time = df["timestamp"].iloc[0]
    total_seconds = float((df["timestamp"].iloc[-1] - start_time).total_seconds())
    num_full_days = int(total_seconds // 86400)
    df["day_idx"] = ((df["timestamp"] - start_time).dt.total_seconds() // 86400).astype(int)
    valid_df = df[df["day_idx"] < num_full_days].copy()
    if valid_df.empty:
        return None, None

    daily_lages: list[float] = []
    daily_mages: list[float] = []
    for day in sorted(valid_df.groupby("day_idx").groups.keys()):
        day_df = valid_df[valid_df["day_idx"] == day]
        g = day_df["glucose"]
        if len(g.dropna()) < 144:
            continue
        daily_lages.append(float(g.max() - g.min()))
        mage = _calc_mage_daily(g)
        if mage is not None:
            daily_mages.append(float(mage))

    mean_lage = float(np.mean(daily_lages)) if daily_lages else None
    mean_mage = float(np.mean(daily_mages)) if daily_mages else None
    return (
        round(mean_lage, 4) if mean_lage is not None else None,
        round(mean_mage, 4) if mean_mage is not None else None,
    )


def _calc_range_stats(df, prefix: str = "") -> dict[str, float]:
    np, _ = _require_deps()
    if df.empty:
        return {}

    total = int(len(df))
    g = df["glucose"].values

    def ratio(count: int) -> float:
        return round(float(count) / float(total), 4) if total > 0 else 0.0

    res: dict[str, float] = {}
    res[f"TIR{prefix}"] = ratio(int(np.sum((g >= 3.9) & (g <= 10.0))))
    res[f"TAR{prefix}"] = ratio(int(np.sum(g > 10.0)))
    res[f"TBR{prefix}"] = ratio(int(np.sum(g < 3.9)))

    res[f"TAR1{prefix}"] = ratio(int(np.sum((g > 10.0) & (g <= 13.9))))
    res[f"TAR2{prefix}"] = ratio(int(np.sum(g > 13.9)))
    res[f"TBR1{prefix}"] = ratio(int(np.sum((g >= 3.0) & (g < 3.9))))
    res[f"TBR2{prefix}"] = ratio(int(np.sum(g < 3.0)))
    res[f"GRI{prefix}"] = round(
        3.0 * res[f"TBR2{prefix}"] + 2.4 * res[f"TBR1{prefix}"] + 1.6 * res[f"TAR2{prefix}"] + 0.8 * res[f"TAR1{prefix}"],
        4,
    )
    res[f"TITR{prefix}"] = ratio(int(np.sum((g >= 3.9) & (g <= 7.8))))
    res[f"TIR-TITR{prefix}"] = round(res[f"TIR{prefix}"] - res[f"TITR{prefix}"], 4)
    return res


def _find_simple_events(df, threshold: float, compare_func, min_duration_min: int = 15) -> list[tuple[datetime, datetime]]:
    if df.empty:
        return []

    df = df.sort_values("timestamp").copy()
    times = df["timestamp"].tolist()
    values = df["glucose"].tolist()

    events: list[tuple[datetime, datetime]] = []
    in_event = False
    start_time: datetime | None = None
    current_event_times: list[datetime] = []

    for i in range(len(values)):
        val = values[i]
        t = times[i]
        if compare_func(val, threshold):
            if not in_event:
                in_event = True
                start_time = t
                current_event_times = [t]
            else:
                prev_t = current_event_times[-1]
                if (t - prev_t).total_seconds() > 15 * 60:
                    duration = (current_event_times[-1] - start_time).total_seconds() / 60  # type: ignore[arg-type]
                    if duration >= min_duration_min:
                        events.append((start_time, current_event_times[-1]))  # type: ignore[arg-type]
                    start_time = t
                    current_event_times = [t]
                else:
                    current_event_times.append(t)
        else:
            if in_event:
                duration = (current_event_times[-1] - start_time).total_seconds() / 60  # type: ignore[arg-type]
                if duration >= min_duration_min:
                    events.append((start_time, current_event_times[-1]))  # type: ignore[arg-type]
                in_event = False
                current_event_times = []

    if in_event:
        duration = (current_event_times[-1] - start_time).total_seconds() / 60  # type: ignore[arg-type]
        if duration >= min_duration_min:
            events.append((start_time, current_event_times[-1]))  # type: ignore[arg-type]

    return events


def _find_complex_events(df, start_func, end_condition_func, min_event_duration: int = 120):
    if df.empty:
        return []

    df = df.sort_values("timestamp").copy()
    times = df["timestamp"].tolist()
    values = df["glucose"].tolist()
    n = len(values)
    events = []

    i = 0
    while i < n:
        if start_func(values[i]):
            start_idx = i
            start_time = times[i]
            end_idx = -1
            j = start_idx + 1
            while j < n:
                is_terminated, _ = end_condition_func(values, times, j)
                if is_terminated:
                    end_idx = j
                    break
                if j > start_idx and (times[j] - times[j - 1]).total_seconds() > 30 * 60:
                    end_idx = j
                    break
                j += 1

            if end_idx == -1:
                end_idx = n

            event_end_time = times[end_idx] if end_idx < n else times[n - 1]
            duration = (event_end_time - start_time).total_seconds() / 60
            if duration >= min_event_duration:
                events.append((start_time, event_end_time))
            i = end_idx
        else:
            i += 1

    return events


def _calc_event_stats(df) -> dict[str, int | str | None]:
    if df.empty:
        return {}

    df = df.sort_values("timestamp").copy()

    def fmt_events(evt_list):
        if not evt_list:
            return 0, None
        count = len(evt_list)
        time_strs = [f"{s:%Y-%m-%d %H:%M:%S}~{e:%Y-%m-%d %H:%M:%S}" for s, e in evt_list]
        return count, ",".join(time_strs)

    stats: dict[str, int | str | None] = {}
    hypo_events = _find_simple_events(df, threshold=3.9, compare_func=lambda x, th: x < th, min_duration_min=15)
    c, t = fmt_events(hypo_events)
    stats["HYPO"] = c
    stats["Time-HYPO"] = t

    hypo_0to6 = [e for e in hypo_events if 0 <= e[0].hour < 6]
    c, t = fmt_events(hypo_0to6)
    stats["HYPO 0TO6AM"] = c
    stats["Time-HYPO 0TO6AM"] = t

    def check_hypo_recovery(vals, ts, idx):
        if idx >= len(vals):
            return False, 0
        start_t = ts[idx]
        curr_idx = idx
        while curr_idx < len(vals):
            if vals[curr_idx] < 3.9:
                return False, 0
            span = (ts[curr_idx] - start_t).total_seconds() / 60
            if span >= 15:
                return True, 0
            curr_idx += 1
        return False, 0

    ex_hypo_events = _find_complex_events(
        df, start_func=lambda x: x < 3.9, end_condition_func=check_hypo_recovery, min_event_duration=120
    )
    c, t = fmt_events(ex_hypo_events)
    stats["EX HYPO"] = c
    stats["Time-EX HYPO"] = t

    ex_hypo_0to6 = [e for e in ex_hypo_events if 0 <= e[0].hour < 6]
    c, t = fmt_events(ex_hypo_0to6)
    stats["EX HYPO 0TO6AM"] = c
    stats["Time-EX HYPO 0TO6AM"] = t

    def check_hyper_recovery(vals, ts, idx):
        if idx >= len(vals):
            return False, 0
        start_t = ts[idx]
        curr_idx = idx
        while curr_idx < len(vals):
            if vals[curr_idx] > 10.0:
                return False, 0
            span = (ts[curr_idx] - start_t).total_seconds() / 60
            if span >= 15:
                return True, 0
            curr_idx += 1
        return False, 0

    ex_hyper_events = _find_complex_events(
        df, start_func=lambda x: x > 13.9, end_condition_func=check_hyper_recovery, min_event_duration=120
    )
    c, t = fmt_events(ex_hyper_events)
    stats["EX HYPER"] = c
    stats["Time-EX HYPER"] = t

    return stats


def _time_period_stats(df, start_hour: int, end_hour: int) -> dict[str, float | str | None]:
    np, _ = _require_deps()
    start_time = datetime.strptime(f"{start_hour:02d}:00:00", "%H:%M:%S").time()
    end_time = datetime.strptime(f"{end_hour:02d}:59:59", "%H:%M:%S").time()
    mask = (df["timestamp"].dt.time >= start_time) & (df["timestamp"].dt.time <= end_time)
    period_df = df[mask].copy()
    if period_df.empty:
        return {"mean": None, "std": None, "cv": None, "median": None, "vv_list": None, "vv_time_list": None}

    glucose_series = period_df["glucose"].dropna()
    if glucose_series.empty:
        return {"mean": None, "std": None, "cv": None, "median": None, "vv_list": None, "vv_time_list": None}

    mean_val = float(glucose_series.mean())
    std_val = float(glucose_series.std())
    cv_val = float(std_val / mean_val) if mean_val else None
    median_val = float(glucose_series.median())

    vv_mask = glucose_series.diff().abs() >= 2.8
    vv_times = period_df.loc[vv_mask.fillna(False), "timestamp"]
    vv_values = glucose_series.loc[vv_mask.fillna(False)]

    vv_list = ",".join([f"{v:.2f}" for v in vv_values.tolist()]) if len(vv_values) else None
    vv_time_list = ",".join([t.strftime("%Y-%m-%d %H:%M:%S") for t in vv_times.tolist()]) if len(vv_times) else None

    return {
        "mean": round(mean_val, 4) if not np.isnan(mean_val) else None,
        "std": round(std_val, 4) if not np.isnan(std_val) else None,
        "cv": round(cv_val, 4) if (cv_val is not None and not np.isnan(cv_val)) else None,
        "median": round(median_val, 4) if not np.isnan(median_val) else None,
        "vv_list": vv_list,
        "vv_time_list": vv_time_list,
    }


def _daily_closest_time_stats(df, target_times: list[str]) -> dict[str, float | None]:
    np, _ = _require_deps()
    if df.empty:
        return {}

    df = df.sort_values("timestamp").copy()
    df["date"] = df["timestamp"].dt.date
    res: dict[str, float | None] = {}

    for t in target_times:
        target = datetime.strptime(t, "%H:%M:%S").time()
        values: list[float] = []
        for _, group in df.groupby("date"):
            group = group.copy()
            group["abs_diff"] = group["timestamp"].dt.time.apply(
                lambda x: abs(datetime.combine(datetime.today(), x) - datetime.combine(datetime.today(), target)).total_seconds()
            )
            closest_row = group.sort_values("abs_diff").head(1)
            if not closest_row.empty:
                values.append(float(closest_row["glucose"].iloc[0]))
        if len(values) >= 2:
            res[f"{t.replace(':', '')}_cv"] = round(float(np.std(values, ddof=1) / np.mean(values)), 4)
        else:
            res[f"{t.replace(':', '')}_cv"] = None
    return res


def _sampling_interval_minutes(df) -> float | None:
    np, _ = _require_deps()
    if df.shape[0] < 2:
        return None
    diffs = df["timestamp"].diff().dt.total_seconds().dropna().values
    diffs = diffs[(diffs > 0) & (diffs <= 3600)]
    if len(diffs) == 0:
        return None
    return float(np.median(diffs) / 60.0)


def compute_cgm_metrics(df, *, cancel_check=None) -> dict[str, object]:
    np, _ = _require_deps()
    _check_cancel(cancel_check)
    if df.empty:
        return {"error": "空数据"}

    start = df["timestamp"].min()
    end = df["timestamp"].max()
    unique_days = int(df["timestamp"].dt.date.nunique())
    span_days = int((end.date() - start.date()).days + 1)
    points = int(len(df))
    interval_min = _sampling_interval_minutes(df)
    expected = span_days * 288 if interval_min and abs(interval_min - 5.0) < 1.5 else None

    stats: dict[str, object] = {
        "start_time": start,
        "end_time": end,
        "days_recorded": unique_days,
        "days_span": span_days,
        "points": points,
        "median_interval_min": round(interval_min, 2) if interval_min is not None else None,
        "expected_points_if_5min": expected,
        "coverage_if_5min": round(points / expected, 4) if expected else None,
    }

    _check_cancel(cancel_check)
    stats.update(_calc_basic_stats(df))

    _check_cancel(cancel_check)
    lbgi, hbgi, adrr = _calc_lbgi_hbgi_adrr(df)
    stats["LBGI"] = lbgi
    stats["HBGI"] = hbgi
    stats["ADRR"] = adrr
    stats["MODD"] = _calc_modd(df)

    _check_cancel(cancel_check)
    lage, mage = _calc_lage_mage(df)
    stats["LAGE"] = lage
    stats["MAGE"] = mage

    _check_cancel(cancel_check)
    stats.update(_calc_range_stats(df, prefix=""))
    stats.update(_calc_range_stats(df[df["timestamp"].dt.hour < 6], prefix="-0TO6AM"))
    stats.update(_calc_range_stats(df[df["timestamp"].dt.hour >= 6], prefix="-6AMTO0"))

    _check_cancel(cancel_check)
    period_00_06 = _time_period_stats(df, 0, 5)
    period_06_24 = _time_period_stats(df, 6, 23)
    stats["MEAN-0TO6AM"] = period_00_06["mean"]
    stats["SD-0TO6AM"] = period_00_06["std"]
    stats["CV-0TO6AM"] = period_00_06["cv"]
    stats["VV-0TO6AM"] = period_00_06["vv_list"]
    stats["VVtime-0TO6AM"] = period_00_06["vv_time_list"]
    stats["MEAN-6AMTO0"] = period_06_24["mean"]
    stats["SD-6AMTO0"] = period_06_24["std"]
    stats["CV-6AMTO0"] = period_06_24["cv"]

    _check_cancel(cancel_check)
    closest_time_stats = _daily_closest_time_stats(df, ["06:30:00"])
    stats["FBS-CV"] = closest_time_stats.get("063000_cv")

    _check_cancel(cancel_check)
    stats.update(_calc_event_stats(df))

    _check_cancel(cancel_check)
    l2_hypo_events = _find_simple_events(df, threshold=3.0, compare_func=lambda x, th: x < th, min_duration_min=15)

    def fmt_events(evt_list):
        if not evt_list:
            return 0, None
        count = len(evt_list)
        time_strs = [f"{s:%Y-%m-%d %H:%M:%S}~{e:%Y-%m-%d %H:%M:%S}" for s, e in evt_list]
        return count, ",".join(time_strs)

    c, t = fmt_events(l2_hypo_events)
    stats["LV2 HYPO"] = c
    stats["Time-LV2 HYPO"] = t

    l2_hypo_0to6 = [e for e in l2_hypo_events if 0 <= e[0].hour < 6]
    c_night, t_night = fmt_events(l2_hypo_0to6)
    stats["LV2 HYPO 0TO6AM"] = c_night
    stats["Time-LV2 HYPO 0TO6AM"] = t_night

    global_min = float(df["glucose"].min()) if not df.empty else None

    def get_conditional_stats(events, min_condition: float, is_night_only: bool):
        if global_min is None or global_min >= min_condition:
            return "#N/A", "#N/A"
        filtered = [e for e in events if 0 <= e[0].hour < 6] if is_night_only else events
        return fmt_events(filtered)

    c, t = get_conditional_stats(l2_hypo_events, min_condition=3.0, is_night_only=False)
    stats["HYPO_COND_3.0"] = c
    stats["Time-HYPO_COND_3.0"] = t
    c, t = get_conditional_stats(l2_hypo_events, min_condition=3.0, is_night_only=True)
    stats["HYPO_COND_3.0 0TO6AM"] = c
    stats["Time-HYPO_COND_3.0 0TO6AM"] = t

    c, t = get_conditional_stats(l2_hypo_events, min_condition=3.5, is_night_only=False)
    stats["HYPO_COND_3.5"] = c
    stats["Time-HYPO_COND_3.5"] = t
    c, t = get_conditional_stats(l2_hypo_events, min_condition=3.5, is_night_only=True)
    stats["HYPO_COND_3.5 0TO6AM"] = c
    stats["Time-HYPO_COND_3.5 0TO6AM"] = t

    return stats


def compute_cgm_metrics_from_file(file_path: str | Path, *, strict_header: bool = True, cancel_check=None) -> dict[str, object]:
    df = load_cgm_dataframe(file_path, strict_header=strict_header, cancel_check=cancel_check)
    _check_cancel(cancel_check)
    return compute_cgm_metrics(df, cancel_check=cancel_check)
