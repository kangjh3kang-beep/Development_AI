"""근거·법령링크 공용 계약(전역정책 Phase0) — '모든 결과물에 근거+법령링크 기본 제공'.

설계 배경:
- v2_feasibility(_build_cost_trust_blocks)·auto_zoning(_attach_trust_blocks)이 각자
  evidence[]/legal_refs[]를 만들지만 라우터마다 흩어져 있다. 신규 라우터/서비스가
  동일 계약을 **상속·재사용**만으로 부착하도록 단일 빌더로 공용화한다.

산출 블록(build_evidence_block):
  {
    "evidence":   [{label, value, basis, legal_ref_key?}, ...]   # 호출부가 만든 트레이스 그대로 통과
    "legal_refs": get_legal_refs(legal_ref_keys, sigungu)        # ★URL은 레지스트리 출력만
    "provenance": public_data_registry + FreshnessChecker 집계   # 원천 데이터 신선도
    "trust":      trust.to_dict()(있으면)                        # 교차검증 신뢰도(선택)
  }

절대 원칙(무목업·정직):
- URL은 전적으로 legal_reference_registry.get_legal_refs 출력만 사용한다(여기서 URL 조립 절대 금지).
  레지스트리에 없는 근거는 링크 없이 텍스트만(할루시네이션 링크 금지).
- 모든 단계는 try/except graceful(실패 시 빈 배열/None — 기존 응답 무손상, v2_feasibility 패턴).
- 계정격리/persist 미접촉(읽기 소비만). 과금 없음(법규/근거는 무과금).
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

# 공공데이터 소스명 → FreshnessChecker 데이터타입(신선도 규칙). 미매핑은 'transaction' 기본.
# (public_data_registry.get_stale_sources의 data_type_map과 동일 의미 — 단일 의미 공유.)
_SOURCE_FRESHNESS_TYPE: dict[str, str] = {
    "molit_transactions": "transaction",
    "molit_official_price": "official_price",
    "vworld_zoning": "zoning",
    "vworld_land_info": "zoning",
    "tax_acquisition_rates": "tax_rate",
    "tax_transfer_rates": "tax_rate",
    "tax_comprehensive_rates": "tax_rate",
    "kma_weather": "weather",
    "kepco_energy": "energy_cert",
}


def build_legal_refs(
    legal_ref_keys: Iterable[str] | None, *, sigungu: str | None = None
) -> list[dict[str, Any]]:
    """근거 키 목록 → 레지스트리 직렬화(get_legal_refs 출력 그대로). graceful 빈배열.

    ★URL은 get_legal_refs만이 생성한다(여기서 조립 금지). 미존재 키는 레지스트리가
    건너뛰며, 조례 키는 sigungu로 치환(미상이면 url_status='pending').
    """
    keys = [k for k in (legal_ref_keys or []) if k]
    if not keys:
        return []
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs(keys, sigungu=sigungu)
    except Exception as e:  # noqa: BLE001 — 레지스트리 실패 시 링크 없이(빈배열)
        logger.warning("legal_refs 직렬화 스킵: %s", str(e)[:120])
        return []


def build_provenance(
    sources: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """원천 데이터 출처별 상태·신선도 집계(public_data_registry + FreshnessChecker).

    각 항목: {name, source_type, update_frequency, last_updated, is_healthy,
             freshness?{is_fresh, age_days, max_age_days, warning}}.
    sources 미지정 시 빈 배열(과대 노출 방지 — 결과와 무관한 전체 소스 덤프 금지).
    레지스트리/검증기 실패는 graceful(빈배열) — 기존 응답 무손상.
    """
    names = [s for s in (sources or []) if s]
    if not names:
        return []
    try:
        from app.services.data_validation.public_data_registry import PublicDataRegistry
        from app.services.data_validation.validator import FreshnessChecker

        registry = PublicDataRegistry.get_instance()
        out: list[dict[str, Any]] = []
        for name in names:
            status = registry.get_status(name)
            if status is None:
                # 미등록 소스는 정직하게 이름만(가짜 신선도 단정 금지).
                out.append({"name": name, "source_type": "unknown", "registered": False})
                continue
            entry = status.to_dict()
            # 신선도(마지막 갱신이 있을 때만 — 미갱신은 status에 last_updated=None로 이미 정직 표기).
            if status.last_updated is not None:
                data_type = _SOURCE_FRESHNESS_TYPE.get(name, "transaction")
                try:
                    entry["freshness"] = FreshnessChecker.check(data_type, status.last_updated)
                except Exception:  # noqa: BLE001
                    pass
            out.append(entry)
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("provenance 집계 스킵: %s", str(e)[:120])
        return []


def _clean_evidence(items: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """호출부 evidence 트레이스를 검증·정규화(label 필수). graceful 빈배열.

    각 항목은 {label, value, basis?, legal_ref_key?} 형태를 기대한다. label이 없는
    항목은 제외(빈 패널 방지). value/basis는 그대로 통과(호출부가 산식·출처 책임).
    """
    out: list[dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        label = it.get("label")
        if not label or not str(label).strip():
            continue
        rec: dict[str, Any] = {"label": str(label), "value": it.get("value")}
        basis = it.get("basis")
        if basis is not None and str(basis).strip():
            rec["basis"] = str(basis)
        else:
            rec["basis"] = None
        lrk = it.get("legal_ref_key")
        if lrk:
            rec["legal_ref_key"] = str(lrk)
        out.append(rec)
    return out


def build_evidence_block(
    items: Iterable[dict[str, Any]] | None = None,
    legal_ref_keys: Iterable[str] | None = None,
    *,
    sigungu: str | None = None,
    trust: Any | None = None,
    sources: Iterable[str] | None = None,
) -> dict[str, Any]:
    """근거·법령링크 공용 블록 생성(전역정책 Phase0 단일 빌더).

    Args:
        items:           호출부가 만든 근거 트레이스 [{label, value, basis?, legal_ref_key?}].
        legal_ref_keys:  법령 근거 키 목록(레지스트리 키/별칭). URL은 레지스트리가 생성.
        sigungu:         조례 url 치환용 시군구명(미상이면 조례는 pending).
        trust:           data_validation.trust.TrustResult 또는 .to_dict() 보유 객체(선택).
        sources:         원천 데이터 소스명 목록(provenance 집계 대상).

    Returns:
        {"evidence": [...], "legal_refs": [...], "provenance": [...], "trust": {...}|None}
        — 모든 하위 단계 graceful(실패 시 빈배열/None). 기존 응답에 그대로 가산하면 된다.
    """
    block: dict[str, Any] = {
        "evidence": [],
        "legal_refs": [],
        "provenance": [],
        "trust": None,
    }
    # evidence — 호출부 트레이스 정규화(graceful)
    try:
        block["evidence"] = _clean_evidence(items)
    except Exception as e:  # noqa: BLE001
        logger.warning("evidence 정규화 스킵: %s", str(e)[:120])

    # legal_refs — get_legal_refs 출력만(URL 조립 금지)
    block["legal_refs"] = build_legal_refs(legal_ref_keys, sigungu=sigungu)

    # provenance — 원천 데이터 신선도 집계
    block["provenance"] = build_provenance(sources)

    # trust — to_dict() 보유 객체면 직렬화, 이미 dict면 그대로(graceful)
    if trust is not None:
        try:
            if hasattr(trust, "to_dict") and callable(trust.to_dict):
                block["trust"] = trust.to_dict()
            elif isinstance(trust, dict):
                block["trust"] = trust
        except Exception as e:  # noqa: BLE001
            logger.warning("trust 직렬화 스킵: %s", str(e)[:120])

    return block
