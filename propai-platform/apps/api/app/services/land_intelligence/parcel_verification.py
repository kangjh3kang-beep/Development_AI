"""필지 면적 3원 교차검증 + 수렴 정책 — S4 반복 검증 루프(계획서 2026-07-03 §S4).

신호 3원(전부 주입 — 이 모듈은 네트워크를 직접 호출하지 않는다):
  ① 공부 면적: parcels-info 계열 결과 dict의 area_sqm/land_area_sqm/total_area_sqm/area
     (special_parcel._AREA_KEYS 와 동일 관례 — 키 정합).
  ② 좌표 면적: 필지 GeoJSON geometry → dims_from_polygon(solar_envelope_service) 재사용.
  ③ 사용자 입력: area_input_sqm(parcel_excel_service 관례) 또는 areaInputSqm.

판정: data_validation/trust.cross_validate() 재사용(anchor=공부, 괴리 임계=기본 10%).
  - consistent    : 신호 2개 이상이 임계 내 정합.
  - discrepancy   : 임계 초과 괴리 신호 존재(또는 fail) — 지적측량 확인 권고.
  - insufficient  : 유효 신호 1개 이하 — 교차검증 불가(정직 표기).

수렴 정책(무날조): refresh_fn 주입 시 괴리 필지만 1회 재보강 후 재판정.
  여전히 괴리면 discrepancy 정직 표기 — ★면적 자동 보정 금지(입력 parcel 불변,
  consensus_area_sqm 은 참고치일 뿐 공부·입력값을 덮어쓰지 않는다).

설명가능성: 필지별 rationale(도출이유)·limitations(한계)·recommendation(권고) 동반.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.data_validation.trust import Signal, TrustResult, cross_validate

# 신호 이름(공개 상수 — W2 배선·프론트 라벨에서 참조)
SIGNAL_CADASTRAL = "cadastral_area"      # 공부(지적공부 등재 면적)
SIGNAL_POLYGON = "polygon_area"          # 좌표(VWorld 폴리곤 실측 근사)
SIGNAL_USER_INPUT = "user_input_area"    # 사용자 입력

DEFAULT_DISCREPANCY_THRESHOLD_PCT = 10.0  # 괴리 임계(%) — 계획서 예시값

# special_parcel._AREA_KEYS 와 동일 순서(키 정합 — 재계산·재정의 금지)
_CADASTRAL_KEYS = ("area_sqm", "land_area_sqm", "total_area_sqm", "area")
_INPUT_KEYS = ("area_input_sqm", "areaInputSqm")

_LIMITATIONS = [
    "좌표면적은 경위도 등거리 근사 기반 참고값으로, 지적공부·확정측량을 대체하지 않습니다.",
    "본 검증은 신호 간 정합성 판단만 수행하며 면적을 자동 보정하지 않습니다(무날조).",
    "consensus_area_sqm 은 교차검증 참고치이며 법적 면적이 아닙니다 — 확정은 지적공부·측량 기준.",
]


def _num(value: Any) -> float | None:
    """양수 float 만 채택 — 0·음수·비수치는 신호로 쓰지 않는다."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def collect_area_signals(parcel: dict[str, Any]) -> list[Signal]:
    """한 필지 dict에서 면적 3원 신호를 수집한다(있는 것만 — 날조 없음)."""
    signals: list[Signal] = []

    cadastral = next((v for k in _CADASTRAL_KEYS if (v := _num(parcel.get(k))) is not None), None)
    if cadastral is not None:
        # 공부가 앵커 — 가중 최상(지적공부 등재값).
        signals.append(Signal(SIGNAL_CADASTRAL, cadastral, sample_size=1,
                              source="official_record", weight=2.0))

    geometry = parcel.get("geometry")
    if geometry:
        # 기존 결정론 기하 함수 재사용(지연 import — shapely 의존을 모듈 로드에서 분리).
        from app.services.site_score.solar_envelope_service import dims_from_polygon
        dims = dims_from_polygon(geometry)
        poly_area = _num((dims or {}).get("area_sqm"))
        if poly_area is not None:
            signals.append(Signal(SIGNAL_POLYGON, poly_area, sample_size=1,
                                  source="derived_geometry", weight=1.0))

    user_input = next((v for k in _INPUT_KEYS if (v := _num(parcel.get(k))) is not None), None)
    if user_input is not None:
        signals.append(Signal(SIGNAL_USER_INPUT, user_input, sample_size=1,
                              source="user_input", weight=0.8))

    return signals


def _recommendation(status: str, threshold_pct: float) -> str:
    if status == "consistent":
        return "가용 면적 신호가 정합 — 공부 면적 기준 사용 가능."
    if status == "insufficient":
        return ("교차검증 신호 부족(1개 이하) — 공부 면적·필지 폴리곤·입력 면적을 확보한 뒤 "
                "재검증하십시오(검증 전 면적 의존 산정은 잠정치).")
    return (f"면적 신호 간 괴리가 임계({threshold_pct:g}%)를 초과 — 지적측량(경계·면적 확정측량)으로 "
            "확인을 권고합니다. 확정 전 면적 의존 산정(용적·수지)은 잠정치로 취급하십시오.")


def _verify_once(parcel: dict[str, Any], threshold_pct: float) -> dict[str, Any]:
    """1회 검증 — 신호 수집 → cross_validate → status 판정(순수·부작용 없음)."""
    signals = collect_area_signals(parcel)
    signal_values = [{"name": s.name, "value": s.value, "source": s.source} for s in signals]
    ratio_threshold = 1.0 + threshold_pct / 100.0

    if len(signals) < 2:
        missing = ({SIGNAL_CADASTRAL, SIGNAL_POLYGON, SIGNAL_USER_INPUT}
                   - {s.name for s in signals})
        return {
            "status": "insufficient",
            "signals": signal_values,
            "consensus_area_sqm": None,
            "consensus_ratio": None,
            "confidence": 0.0,
            "verdict": "fail",
            "excluded_signals": [],
            "recommendation": _recommendation("insufficient", threshold_pct),
            "rationale": (f"유효 면적 신호 {len(signals)}개 — 2개 미만이라 교차검증 불가. "
                          f"부재 신호: {', '.join(sorted(missing))}."),
            "limitations": list(_LIMITATIONS),
        }

    tr: TrustResult = cross_validate(
        signals,
        anchor=SIGNAL_CADASTRAL,
        outlier_ratio=ratio_threshold,   # 임계 초과 괴리 신호를 이상치로 적발
        min_anchor_samples=1,            # 공부는 단일 등재값 — 표본 1로 앵커 성립
    )
    discrepant = bool(tr.excluded) \
        or (tr.consensus_ratio is not None and tr.consensus_ratio > ratio_threshold) \
        or tr.verdict == "fail"
    status = "discrepancy" if discrepant else "consistent"

    return {
        "status": status,
        "signals": signal_values,
        "consensus_area_sqm": tr.trusted_value,  # 참고치 — 자동 보정에 사용 금지
        "consensus_ratio": round(tr.consensus_ratio, 3) if tr.consensus_ratio else None,
        "confidence": round(tr.confidence, 3),
        "verdict": tr.verdict,
        "excluded_signals": tr.excluded,
        "recommendation": _recommendation(status, threshold_pct),
        "rationale": (f"신호 {len(signals)}개({', '.join(s.name for s in signals)})를 "
                      f"공부(cadastral_area) 앵커로 교차검증 — 임계 {threshold_pct:g}% "
                      f"기준 {'괴리 검출' if discrepant else '정합'}. "
                      f"채택 {tr.used}, 제외 {len(tr.excluded)}건."),
        "limitations": list(_LIMITATIONS),
    }


def verify_parcel_areas(
    parcels: list[dict[str, Any]],
    refresh_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    *,
    discrepancy_threshold_pct: float = DEFAULT_DISCREPANCY_THRESHOLD_PCT,
) -> dict[str, Any]:
    """필지 리스트의 면적 3원 정합을 필지별로 판정한다(detect_multi_parcel 전 단계 훅용).

    refresh_fn: 괴리 필지 재보강 콜러블(주입) — refresh_fn(parcel) -> 갱신 필드 dict | None.
      괴리 필지에만 필지당 최대 1회 호출. 반환 dict는 원본과 병합해 재판정에만 쓰며,
      원본 parcel 은 절대 변형하지 않는다(자동 보정 금지 — 무날조).

    반환: {parcel_count, consistent_count, discrepancy_count, insufficient_count,
           all_consistent, per_parcel: [필지별 판정], policy}
    """
    per: list[dict[str, Any]] = []
    for i, parcel in enumerate(parcels or []):
        entry = _verify_once(parcel, discrepancy_threshold_pct)
        entry.update({"index": i, "pnu": parcel.get("pnu"),
                      "refresh_attempted": False, "converged_after_refresh": None})

        if entry["status"] == "discrepancy" and refresh_fn is not None:
            entry["refresh_attempted"] = True
            try:
                refreshed = refresh_fn(parcel)
            except Exception as exc:  # noqa: BLE001 — 재보강 실패는 정직 기록 후 원판정 유지
                refreshed = None
                entry["refresh_error"] = f"재보강 실패: {exc}"
            if isinstance(refreshed, dict) and refreshed:
                merged = {**parcel, **{k: v for k, v in refreshed.items() if v is not None}}
                second = _verify_once(merged, discrepancy_threshold_pct)
                if second["status"] == "consistent":
                    second.update({"index": i, "pnu": parcel.get("pnu"),
                                   "refresh_attempted": True, "converged_after_refresh": True})
                    second["rationale"] += " 1회 재보강 후 재판정에서 수렴(consistent)."
                    entry = second
                else:
                    entry["converged_after_refresh"] = False
                    entry["signals_after_refresh"] = second["signals"]
                    entry["rationale"] += " 1회 재보강 후에도 괴리 지속 — 불수렴 정직 표기."
            else:
                entry["converged_after_refresh"] = False

        per.append(entry)

    consistent = sum(1 for e in per if e["status"] == "consistent")
    discrepancy = sum(1 for e in per if e["status"] == "discrepancy")
    insufficient = sum(1 for e in per if e["status"] == "insufficient")
    return {
        "parcel_count": len(per),
        "consistent_count": consistent,
        "discrepancy_count": discrepancy,
        "insufficient_count": insufficient,
        "all_consistent": len(per) > 0 and consistent == len(per),
        "per_parcel": per,
        "policy": {
            "discrepancy_threshold_pct": discrepancy_threshold_pct,
            "auto_correction": False,          # 자동 보정 금지(무날조)
            "refresh_max_attempts": 1,         # 괴리 필지당 재보강 1회
            "anchor": SIGNAL_CADASTRAL,
            "note": "괴리·신호부족은 정직 표기 — 확정은 지적공부·지적측량 기준.",
        },
    }
