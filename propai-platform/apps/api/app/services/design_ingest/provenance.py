"""설계생성 결과의 근거(provenance) 레이어 — 모든 산출 값에 근거·출처·신뢰도·링크 부착.

전역 원칙(★): 모든 결과물은 근거를 제시하고 필요시 링크를 제공한다([[feedback_evidence_and_links]]).
- 링크/출처는 canonical 레지스트리 get_legal_refs()만 사용한다(★URL 직접조립 절대금지·할루시네이션
  링크 금지·죽은링크 방지). 조례는 sigungu 확정 시에만 verified, 아니면 pending(링크 없음·정직).
- 추정값(휴리스틱) → 근거(산식) + confidence='estimated', 링크 없음(추정 명시, 값 지어내기 금지).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.legal.legal_reference_registry import get_legal_refs


@dataclass
class Evidence:
    """결과 값 1건의 근거.

    confidence: ordinance(실효 조례) | statutory(법정상한) | rule(규칙엔진) |
                measured(실측/실데이터) | estimated(추정) | unknown(미확인)
    """

    claim: str                 # 무엇에 대한 근거인지(예: '최대 연면적')
    basis: str                 # 어떻게 도출했는지(산식·사유)
    source: str                # 출처(법령명·조문·규칙·추정 등)
    confidence: str            # 위 enum
    value: object | None = None
    link: str | None = None

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "value": self.value,
            "basis": self.basis,
            "source": self.source,
            "confidence": self.confidence,
            "link": self.link,
        }


def _ref_link(key: str, sigungu: str | None = None) -> tuple[str, str | None]:
    """레지스트리 키 → (출처표기, url|None). canonical get_legal_refs 단일 출처.

    미존재 키는 (key, None). url 없으면(조례 sigungu 미상 등) None(pending·링크 없음).
    """
    # 공백전용 sigungu('   ')는 truthy라 치환을 통과해 '    도시계획 조례'(미상태그 없음)로 누출 →
    # 단일 초크포인트(_ref_link·모든 근거링크 경유)에서 strip-then-empty 정규화(정직·입력위생).
    if isinstance(sigungu, str) and not sigungu.strip():
        sigungu = None
    refs = get_legal_refs([key], sigungu=sigungu)
    if not refs:
        return key, None
    r = refs[0]
    label = r.get("law_name") or key
    article = r.get("article")
    if article:
        label = f"{label} {article}"
    # 미치환 플레이스홀더({sigungu} 등) 리터럴 노출 방지 — sigungu 미상 시 정직 표기(근거 품질).
    if "{sigungu}" in label:
        label = label.replace("{sigungu}", "해당 지자체").strip() + " (시군구 미상)"
    return label, (r.get("url") or None)


def _far_attrs(far_source: str, sigungu: str | None) -> tuple[str, str | None, str]:
    """용적률(FAR) 출처 → (출처표기, link, confidence). 실효(조례) 우선 표기."""
    if far_source == "ordinance":
        label, link = _ref_link("ordinance_far", sigungu)
        return label, link, "ordinance"
    if far_source in ("statutory", "statutory_fallback"):
        label, link = _ref_link("far_law", sigungu)
        if far_source == "statutory_fallback":
            label += " (미지정 용도지역 기본값 폴백)"
        return label, link, "statutory"
    return "용적률 출처 미확인", None, "unknown"


def _bcr_attrs(far_source: str, sigungu: str | None) -> tuple[str, str | None, str]:
    """건폐율(BCR) 출처 → (출처표기, link, confidence). v1은 far_source 계열로 표기."""
    if far_source == "ordinance":
        label, link = _ref_link("ordinance_bcr", sigungu)
        return label, link, "ordinance"
    if far_source in ("statutory", "statutory_fallback"):
        label, link = _ref_link("bcr_law", sigungu)
        if far_source == "statutory_fallback":
            label += " (미지정 용도지역 기본값 폴백)"
        return label, link, "statutory"
    return "건폐율 출처 미확인", None, "unknown"


def legal_envelope_evidence(site, *, sigungu: str | None = None) -> list[Evidence]:
    """부지 법적 한도(용적률→연면적, 건폐율→건축면적)의 근거. 출처는 far_source 기준."""
    out: list[Evidence] = []
    far_source = getattr(site, "far_source", "unknown")
    area = getattr(site, "area_sqm", None)

    far_pct = getattr(site, "legal_far_pct", None)
    max_gfa = getattr(site, "max_gfa_sqm", None)
    if far_pct is not None and max_gfa is not None:
        src, link, conf = _far_attrs(far_source, sigungu)
        out.append(Evidence(
            claim="최대 연면적(용적률 상한)",
            value=max_gfa,
            basis=f"용적률 {far_pct}% × 대지면적 {area}㎡",
            source=src, confidence=conf, link=link,
        ))

    bcr_pct = getattr(site, "legal_bcr_pct", None)
    footprint = getattr(site, "buildable_footprint_sqm", None)
    if bcr_pct is not None and footprint is not None:
        src, link, conf = _bcr_attrs(far_source, sigungu)
        out.append(Evidence(
            claim="최대 건축면적(건폐율 상한)",
            value=footprint,
            basis=f"건폐율 {bcr_pct}% × 대지면적 {area}㎡",
            source=src, confidence=conf, link=link,
        ))

    if not out:
        out.append(Evidence(
            claim="법적 한도",
            basis=f"용도지역 한도 미확인(zone={getattr(site, 'zone_code', '?')})",
            source="미확인", confidence="unknown",
        ))
    return out


def permit_evidence(permit: dict | None, *, sigungu: str | None = None) -> Evidence:
    """인허가 가능성 판정의 근거(규칙엔진). permit None이면 미확인(정직). 링크=용도지역 행위제한."""
    if not permit:
        return Evidence(
            claim="인허가 가능성",
            basis="용도지역명 미제공 — 인허가 판정 미실행",
            source="미확인", confidence="unknown",
        )
    label, link = _ref_link("zone_use", sigungu)  # 국토계획법 용도지역 건축물 제한
    return Evidence(
        claim="인허가 가능성",
        value=permit.get("is_permitted"),
        basis=permit.get("reason") or "용도지역 행위제한 규칙 대조",
        source=label, confidence="rule", link=link,
    )


def proposal_evidence(candidate: dict, site, *, sigungu: str | None = None) -> list[Evidence]:
    """설계 후보(조합 결과)의 추정·적합성 근거. 추정은 estimated로 정직 표기(링크 없음)."""
    out: list[Evidence] = []
    far_source = getattr(site, "far_source", "unknown")

    gfa = candidate.get("estimated_gfa_sqm")
    floors = candidate.get("estimated_floors")
    if gfa is not None:
        out.append(Evidence(
            claim="추정 연면적", value=gfa,
            basis=f"층면적 × 층수({floors}) — 법적 용적률 상한으로 클램프",
            source="설계엔진 추정(법적 상한 적용)", confidence="estimated",
        ))
    units = candidate.get("estimated_units")
    if units is not None:
        out.append(Evidence(
            claim="추정 세대수", value=units,
            basis="연면적 × 전용률 0.75 ÷ 평균 평형 — 실제 평면 세대분할과 다를 수 있음",
            source="설계엔진 추정(휴리스틱)", confidence="estimated",
        ))
    parking = candidate.get("parking_required")
    if parking is None:
        parking = candidate.get("estimated_parking")  # 하위호환
    if parking is not None:
        label, link = _ref_link("parking_min", sigungu)  # 주차장법 제19조 부설주차장
        p_area = candidate.get("parking_area_sqm")
        basis = "법정 부설주차 산정(주차장법 단순화·대당 33㎡·지역/전용별 세부기준 미반영)"
        if p_area is not None:
            basis += f" — 소요 주차면적 {p_area}㎡"
        out.append(Evidence(
            claim="법정 주차대수(부설주차장)", value=parking,
            basis=basis, source=label, confidence="rule", link=link,
        ))
        # 주차 배치 가능성(부지 footprint 기준 지하주차 층수) — 추정(footprint 기준).
        feasible = candidate.get("parking_feasible")
        if feasible is not None:
            bf = candidate.get("parking_basement_floors")
            note = "" if feasible else " — 비현실(지상주차·필로티·대지 재검토)"
            out.append(Evidence(
                claim="주차 배치 가능성", value=feasible,
                basis=f"소요 주차면적 ÷ 건축면적(footprint) ≈ 지하 {bf}층 필요{note}",
                source="설계엔진 산정(footprint 기준)", confidence="estimated",
            ))

    # 적합성(compliant) 근거 — 법적 한도 출처(레지스트리)에 연동.
    src, link, conf = _far_attrs(far_source, sigungu)
    out.append(Evidence(
        claim="법적 한도 적합성",
        value=candidate.get("compliant"),
        basis="조합 결과를 건폐율·용적률 상한과 대조(초과 시 부적합)",
        source=src, confidence=conf, link=link,
    ))
    return out
