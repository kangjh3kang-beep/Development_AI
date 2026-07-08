"""플랫폼 표준 근거 계약 → 정본 EvidenceBlock 변환 브리지(evidence dead-path 해소).

배경(P1 확정 버그):
- 렌더러·모델·테스트는 EvidenceBlock 을 완비했지만, 어댑터들이 도메인 결과 안의
  표준 근거 계약(evidence_contract.build_evidence_block 출력)을 전혀 옮겨 담지 않아
  실보고서에 '구조화 근거 + 법령링크' 블록이 부재했다. 이 브리지가 그 다리를 놓는다.

입력(플랫폼 표준 계약 — 재구현 없이 그대로 소비):
- 풀 블록: {"evidence":[{label,value,basis?,legal_ref_key?}], "legal_refs":[레지스트리 레코드],
            "provenance":[...], "trust":...}  (evidence_contract.build_evidence_block 출력)
- 단독 legal_refs 배열: [{key,law_name,article,title,url,url_status}, ...]
  (legal_reference_registry.get_legal_refs 출력 — 설계심사 finding 등이 직접 들고 다님)
- 키만 있는 경우: {"legal_ref_keys":["far_limit", ...]} → 표준 빌더
  evidence_contract.build_legal_refs 로 해석(★레지스트리만 URL 생성 — 여기서 조립 금지).

절대 원칙(무목업·정직):
- legal_link 는 레지스트리가 url_status='verified' 로 준 URL 만 그대로 통과한다.
  pending/빈 URL 은 링크 없이 법령명 텍스트만(할루시네이션 링크 금지, URL 조립·날조 금지).
- confidence 는 계약 값 그대로(추정·기본값 주입 금지 — 없으면 None).
- 실데이터가 하나도 없으면 None 을 반환한다(빈 블록·가짜값 금지 — 호출부는 섹션 생략).
"""

from __future__ import annotations

import logging
from typing import Any

from .model import Evidence, EvidenceBlock, fmt_value

logger = logging.getLogger(__name__)


def _verified_url(ref: dict[str, Any]) -> str | None:
    """레지스트리 레코드에서 verified URL 만 꺼낸다(그 외는 None — 링크 날조 금지)."""
    if not isinstance(ref, dict):
        return None
    url = ref.get("url")
    if url and ref.get("url_status") == "verified":
        return str(url)
    return None


def _ref_text(ref: dict[str, Any]) -> str:
    """레지스트리 레코드의 표시 텍스트('법령명 조문'). 둘 다 없으면 title 폴백."""
    law = str(ref.get("law_name") or "").strip()
    art = str(ref.get("article") or "").strip()
    text = f"{law} {art}".strip()
    return text or str(ref.get("title") or "").strip()


def _looks_like_legal_ref(item: Any) -> bool:
    """dict 하나가 레지스트리 레코드(law_name/url_status 보유)처럼 생겼는지 판별."""
    return isinstance(item, dict) and ("law_name" in item or "url_status" in item)


def _resolve_ref_keys(keys: list[str], *, sigungu: str | None = None) -> list[dict[str, Any]]:
    """법령키 목록 → 레지스트리 레코드(★표준 빌더 evidence_contract.build_legal_refs 재사용).

    URL 은 전적으로 레지스트리 출력만 사용한다. 실패는 graceful 빈 배열(보고서 무손상).
    """
    clean = [str(k) for k in keys if k]
    if not clean:
        return []
    try:
        from app.services.data_validation.evidence_contract import build_legal_refs

        return build_legal_refs(clean, sigungu=sigungu)
    except Exception as e:  # noqa: BLE001 — 레지스트리 실패는 링크 없이(텍스트도 없음)
        logger.warning("evidence_bridge 법령키 해석 스킵: %s", str(e)[:120])
        return []


def evidence_block_from_contract(
    payload: Any, *, title: str | None = "근거·법령 링크", sigungu: str | None = None
) -> EvidenceBlock | None:
    """플랫폼 표준 근거 계약(payload) → 정본 EvidenceBlock. 실데이터 없으면 None.

    Args:
        payload: 표준 풀 블록 dict / 단독 legal_refs 배열 / {"legal_ref_keys":[...]} dict.
        title:   블록 제목(렌더러가 소제목으로 표기).
        sigungu: 법령키 해석 시 조례 URL 치환용 시군구명(선택).

    매핑 규칙(model.Evidence: value/basis/source/provenance/legal_link/confidence):
    - evidence 항목 {label,value} → value="라벨: 값"(라벨 없는 항목은 제외 — 표준과 동일).
    - legal_ref_key 로 legal_refs 레코드를 짝지어 verified URL 만 legal_link 로 통과.
      source 미지정 항목은 짝지어진 법령의 '법령명 조문' 텍스트를 source 로(텍스트 폴백 — 정직).
    - 어느 evidence 에도 안 쓰인 legal_refs 는 법령 자체를 1행씩 노출(근거 법령 목록).
    - confidence 는 계약 값 그대로 통과(없으면 None — 추정 금지).
    """
    ev_items: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        raw_ev = payload.get("evidence")
        if isinstance(raw_ev, list):
            ev_items = [it for it in raw_ev if isinstance(it, dict)]
        raw_refs = payload.get("legal_refs")
        if isinstance(raw_refs, list):
            refs = [r for r in raw_refs if isinstance(r, dict)]
        raw_keys = payload.get("legal_ref_keys")
        if isinstance(raw_keys, (list, tuple)) and raw_keys:
            refs = refs + _resolve_ref_keys(list(raw_keys), sigungu=sigungu)
    elif isinstance(payload, list):
        # 단독 배열: 레지스트리 레코드면 legal_refs, {label,...} 트레이스면 evidence 로 취급.
        for it in payload:
            if _looks_like_legal_ref(it):
                refs.append(it)
            elif isinstance(it, dict) and it.get("label"):
                ev_items.append(it)
    else:
        return None

    # 법령키 → 레코드 색인(evidence 항목과 짝짓기용). 같은 키 중복은 첫 레코드 우선.
    ref_by_key: dict[str, dict[str, Any]] = {}
    for r in refs:
        k = r.get("key")
        if k and k not in ref_by_key:
            ref_by_key[str(k)] = r

    items: list[Evidence] = []
    used_keys: set[str] = set()

    # ── ① 근거 트레이스(evidence 항목) → Evidence 행 ──
    for it in ev_items:
        label = str(it.get("label") or "").strip()
        if not label:
            continue  # 라벨 없는 항목 제외(표준 _clean_evidence 와 동일 — 빈 행 방지)
        raw_value = it.get("value")
        value_str = raw_value if isinstance(raw_value, str) else fmt_value(raw_value)
        ref = None
        ref_key = it.get("legal_ref_key")
        if ref_key:
            ref = ref_by_key.get(str(ref_key))
            if ref is not None:
                used_keys.add(str(ref_key))
        source = it.get("source")
        if not source and ref is not None:
            source = _ref_text(ref) or None  # 링크 미확보(pending)여도 법령명 텍스트는 정직 노출
        provenance = it.get("provenance")
        items.append(Evidence(
            value=f"{label}: {value_str}",
            basis=str(it["basis"]) if it.get("basis") else None,
            source=str(source) if source else None,
            provenance=str(provenance) if isinstance(provenance, str) and provenance else None,
            legal_link=_verified_url(ref) if ref is not None else None,
            confidence=str(it["confidence"]) if it.get("confidence") else None,  # 계약값 그대로
        ))

    # ── ② 어느 트레이스에도 안 쓰인 법령 레코드 → 법령 목록 행(중복 키 1회) ──
    seen: set[str] = set(used_keys)
    for r in refs:
        text = _ref_text(r)
        if not text:
            continue  # 표시할 법령명조차 없으면 행 생성 금지(빈 행·가짜값 방지)
        dedup_key = str(r.get("key") or text)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        title_txt = str(r.get("title") or "").strip()
        items.append(Evidence(
            value=text,
            basis=title_txt or None,
            legal_link=_verified_url(r),  # verified 만 — pending 은 텍스트만(정직)
        ))

    if not items:
        return None  # 실데이터 부재 → 블록 미부착(호출부가 섹션 생략)
    return EvidenceBlock(items=items, title=title)
