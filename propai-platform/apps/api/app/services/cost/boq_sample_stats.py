"""N1 — 실적 N건 누적 → 원단위(qty/driver) 표본 통계(평균·CV·n). 인프라(코드 경로)만.

실적 공내역서가 1건일 때는 모든 원단위가 단일표본(n=1)이므로 일반화하지 않는다
(섣부른 일반화 금지 — §1 정직성). 실적이 누적되어 동일 항목(name,spec,unit)의
표본이 n≥3 가 되면, 엔진(generate_draft)이 단일표본 스케일링 대신 표본평균 원단위를
쓰고 신뢰도 배지를 "실적 N건 기반·CV xx%"로 자동 전환한다.

본 모듈은 결정론(LLM 0) 순수 계산이며, 데이터 소스는 data/boq_master 의:
  - 프로젝트별 누적 구조: data/boq_master/<project>/{*.json,_meta.json}
  - 단일 플랫 구조(현행): data/boq_master/{*.json,_meta.json} → default 프로젝트 1건
둘 다 하위호환으로 로드한다.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# 일반화(표본평균 전환) 최소 표본수. n<REF_MIN_N 이면 단일표본(n=1) 보류.
REF_MIN_N = 3

_DATA_DIR = Path(__file__).resolve().parent / "data" / "boq_master"

_DISCIPLINE_FILES: dict[str, str] = {
    "건축": "architecture.json",
    "기계소방": "mechanical.json",
    "전기통신소방": "electrical.json",
    "조경": "landscape.json",
    "토목": "civil.json",
}
_FILE_TO_DISCIPLINE = {v: k for k, v in _DISCIPLINE_FILES.items()}

# driver → 프로젝트 파라미터 키(원단위 분모).
_DRIVER_PARAM: dict[str, str] = {
    "gfa": "gfa_sqm",
    "households": "households",
    "landscape_area": "landscape_area_sqm",
}


def unit_rate_stats(samples: list[float]) -> dict[str, Any]:
    """원단위 표본 리스트 → {n, mean, std, cv}. 표본표준편차는 ddof=1(불편추정)."""
    vals = [float(s) for s in samples
            if isinstance(s, (int, float)) and not isinstance(s, bool)]
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "cv": None}
    mean = sum(vals) / n
    if n == 1:
        return {"n": 1, "mean": mean, "std": 0.0, "cv": 0.0}
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    std = math.sqrt(var)
    cv = (std / mean) if mean else 0.0
    return {"n": n, "mean": mean, "std": std, "cv": cv}


def is_generalizable(stat: dict[str, Any] | None) -> bool:
    """표본이 일반화 가능한가(n≥REF_MIN_N) — 미만이면 단일표본 유지."""
    return bool(stat) and int(stat.get("n") or 0) >= REF_MIN_N


def _driver_value(params: dict[str, Any], driver: str) -> float | None:
    key = _DRIVER_PARAM.get(driver)
    if not key:
        return None
    v = params.get(key)
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return float(v)
    return None


def aggregate_item_unit_rates(
    projects: list[dict[str, Any]],
) -> dict[tuple[Any, Any, Any], dict[str, Any]]:
    """프로젝트 리스트 → (name,spec,unit)별 원단위(qty_sample/driver_value) 표본 통계.

    projects: [{params:{gfa_sqm,households,landscape_area_sqm}, items:[{name,spec,unit,
               qty_sample, driver}]}]. driver 없으면 'gfa' 가정. driver=='fixed'(횟수성)은
    스케일 대상이 아니므로 제외한다.
    """
    buckets: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for proj in projects:
        params = proj.get("params") or {}
        for it in proj.get("items") or []:
            driver = it.get("driver") or "gfa"
            if driver == "fixed":
                continue
            dv = _driver_value(params, driver)
            if not dv:
                continue
            qs = it.get("qty_sample")
            if not isinstance(qs, (int, float)) or isinstance(qs, bool):
                continue
            key = (it.get("name"), it.get("spec", ""), it.get("unit"))
            b = buckets.setdefault(key, {"rates": [], "driver": driver})
            b["rates"].append(float(qs) / dv)
    out: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for key, b in buckets.items():
        st = unit_rate_stats(b["rates"])
        st["driver"] = b["driver"]
        out[key] = st
    return out


def _load_one_project(dir_path: Path, name: str) -> dict[str, Any] | None:
    """단일 프로젝트 디렉터리(*.json + _meta.json) → {name, params, items(+driver)}."""
    masters = [p for p in dir_path.glob("*.json") if p.name != "_meta.json"]
    if not masters:
        return None
    params: dict[str, Any] = {}
    meta_path = dir_path / "_meta.json"
    if meta_path.exists():
        try:
            proj = json.loads(meta_path.read_text(encoding="utf-8")).get("project") or {}
            params = {k: proj.get(k) for k in ("gfa_sqm", "households", "landscape_area_sqm")
                      if proj.get(k) is not None}
        except Exception:  # noqa: BLE001 — 메타 손상 시 빈 params(원단위 계산만 제한)
            params = {}
    # driver 배정은 엔진 규칙 재사용(없으면 'gfa' 폴백 — 결정론 일관).
    try:
        from app.services.cost.boq_parametric_engine import assign_driver
    except Exception:  # noqa: BLE001
        assign_driver = None  # type: ignore[assignment]

    items: list[dict[str, Any]] = []
    for mp in sorted(masters):
        disc = _FILE_TO_DISCIPLINE.get(mp.name, "")
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for it in data.get("items") or []:
            driver = it.get("driver")
            if driver is None and assign_driver is not None and disc:
                try:
                    driver = assign_driver(it, disc)
                except Exception:  # noqa: BLE001
                    driver = "gfa"
            items.append({
                "name": it.get("name"), "spec": it.get("spec", ""), "unit": it.get("unit"),
                "qty_sample": it.get("qty_sample"), "driver": driver or "gfa",
            })
    return {"name": name, "params": params, "items": items}


def load_projects(data_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """누적 구조(<project>/) 우선, 없으면 단일 플랫 구조를 default 프로젝트로 로드(하위호환)."""
    base = Path(data_dir) if data_dir else _DATA_DIR
    if not base.exists():
        return []
    # 하위 디렉터리(프로젝트별 누적 구조) 탐지.
    subdirs = [d for d in sorted(base.iterdir())
               if d.is_dir() and any(d.glob("*.json"))]
    projects: list[dict[str, Any]] = []
    if subdirs:
        for d in subdirs:
            proj = _load_one_project(d, d.name)
            if proj:
                projects.append(proj)
        return projects
    # 단일 플랫 구조 → default 프로젝트 1건.
    proj = _load_one_project(base, "default")
    return [proj] if proj else []


def load_sample_stats(
    data_dir: Path | str | None = None,
) -> dict[tuple[Any, Any, Any], dict[str, Any]]:
    """데이터 디렉터리에서 (name,spec,unit)별 원단위 표본 통계를 산출한다."""
    return aggregate_item_unit_rates(load_projects(data_dir))
