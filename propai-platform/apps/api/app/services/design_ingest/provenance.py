"""설계생성 결과의 근거(provenance) 레이어 — 모든 산출 값에 근거·출처·신뢰도·링크 부착.

전역 원칙(★): 모든 결과물은 근거를 제시하고 필요시 링크를 제공한다.
- 법정/조례 한도 등 권위 있는 값 → 출처 + 법령 링크.
- 추정값(휴리스틱) → 근거(산식) + confidence='estimated', 링크 없음(정직, 추정 명시).
값을 지어내지 않으며, 출처 없는 추정은 추정이라고 정직하게 표기한다.
"""

from __future__ import annotations

from dataclasses import dataclass

# 권위 출처 → (출처표기, 링크). 정확한 조문 deep-link은 변동성이 커, 안정적인 포털/법령 단위로
# 링크하고 조문은 source 텍스트에 명시한다(허위 링크 금지).
_SOURCE_LINKS: dict[str, tuple[str, str]] = {
    "statutory": (
        "국토의 계획 및 이용에 관한 법률 시행령(용도지역 건폐율·용적률 상한)",
        "https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령",
    ),
    "ordinance": (
        "지자체 도시계획조례(실효 건폐율·용적률 한도)",
        "https://www.elis.go.kr",  # 자치법규정보시스템
    ),
    "permit": (
        "국토계획법 용도지역 행위제한(인허가 가능 개발유형)",
        "https://www.law.go.kr/법령/국토의계획및이용에관한법률",
    ),
}


@dataclass
class Evidence:
    """결과 값 1건의 근거.

    confidence: ordinance(실효 조례) | statutory(법정상한) | rule(규칙엔진) |
                measured(실측/실데이터) | estimated(추정) | unknown(미확인)
    """

    claim: str                 # 무엇에 대한 근거인지(예: '최대 연면적')
    basis: str                 # 어떻게 도출했는지(산식·사유)
    source: str                # 출처(법령명·규칙·추정 등)
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


def _link_for(key: str) -> tuple[str, str | None]:
    """출처키 → (출처표기, 링크). 미등록이면 (키, None)."""
    if key in _SOURCE_LINKS:
        label, url = _SOURCE_LINKS[key]
        return label, url
    return key, None


def legal_envelope_evidence(site) -> list[Evidence]:
    """부지 법적 한도(용적률→연면적, 건폐율→건축면적)의 근거. 출처는 far_source 기준."""
    out: list[Evidence] = []
    far_source = getattr(site, "far_source", "unknown")
    area = getattr(site, "area_sqm", None)

    # 용적률 → 최대 연면적
    far_pct = getattr(site, "legal_far_pct", None)
    max_gfa = getattr(site, "max_gfa_sqm", None)
    if far_pct is not None and max_gfa is not None:
        if far_source == "ordinance":
            src_label, link = _link_for("ordinance")
            conf = "ordinance"
        elif far_source in ("statutory", "statutory_fallback"):
            src_label, link = _link_for("statutory")
            conf = "statutory"
            if far_source == "statutory_fallback":
                src_label += " (미지정 용도지역 기본값 폴백)"
        else:
            src_label, link, conf = "용적률 출처 미확인", None, "unknown"
        out.append(Evidence(
            claim="최대 연면적(용적률 상한)",
            value=max_gfa,
            basis=f"용적률 {far_pct}% × 대지면적 {area}㎡",
            source=src_label,
            confidence=conf,
            link=link,
        ))

    # 건폐율 → 최대 건축면적(footprint)
    bcr_pct = getattr(site, "legal_bcr_pct", None)
    footprint = getattr(site, "buildable_footprint_sqm", None)
    if bcr_pct is not None and footprint is not None:
        # BCR 출처는 v1에서 far_source와 동일 계열로 표기(별도 추적 안 함).
        if far_source == "ordinance":
            src_label, link = _link_for("ordinance")
            conf = "ordinance"
        elif far_source in ("statutory", "statutory_fallback"):
            src_label, link = _link_for("statutory")
            conf = "statutory"
        else:
            src_label, link, conf = "건폐율 출처 미확인", None, "unknown"
        out.append(Evidence(
            claim="최대 건축면적(건폐율 상한)",
            value=footprint,
            basis=f"건폐율 {bcr_pct}% × 대지면적 {area}㎡",
            source=src_label,
            confidence=conf,
            link=link,
        ))

    if not out:
        out.append(Evidence(
            claim="법적 한도",
            basis=f"용도지역 한도 미확인(zone={getattr(site, 'zone_code', '?')})",
            source="미확인",
            confidence="unknown",
        ))
    return out


def permit_evidence(permit: dict | None) -> Evidence:
    """인허가 가능성 판정의 근거(규칙엔진). permit None이면 미확인(정직)."""
    if not permit:
        return Evidence(
            claim="인허가 가능성",
            basis="용도지역명 미제공 — 인허가 판정 미실행",
            source="미확인",
            confidence="unknown",
        )
    src_label, link = _link_for("permit")
    return Evidence(
        claim="인허가 가능성",
        value=permit.get("is_permitted"),
        basis=permit.get("reason") or "용도지역 행위제한 규칙 대조",
        source=src_label,
        confidence="rule",
        link=link,
    )


def proposal_evidence(candidate: dict, site) -> list[Evidence]:
    """설계 후보(조합 결과)의 추정·적합성 근거. 추정은 estimated로 정직 표기(링크 없음)."""
    out: list[Evidence] = []
    far_source = getattr(site, "far_source", "unknown")

    gfa = candidate.get("estimated_gfa_sqm")
    floors = candidate.get("estimated_floors")
    if gfa is not None:
        out.append(Evidence(
            claim="추정 연면적",
            value=gfa,
            basis=f"층면적 × 층수({floors}) — 법적 용적률 상한으로 클램프",
            source="설계엔진 추정(법적 상한 적용)",
            confidence="estimated",
        ))
    units = candidate.get("estimated_units")
    if units is not None:
        out.append(Evidence(
            claim="추정 세대수",
            value=units,
            basis="연면적 × 전용률 0.75 ÷ 평균 평형 — 실제 평면 세대분할과 다를 수 있음",
            source="설계엔진 추정(휴리스틱)",
            confidence="estimated",
        ))
    parking = candidate.get("estimated_parking")
    if parking is not None:
        out.append(Evidence(
            claim="추정 주차대수",
            value=parking,
            basis="세대당 1대 규칙(법정 주차기준·조례 미반영 추정)",
            source="설계엔진 추정(규칙)",
            confidence="estimated",
        ))

    # 적합성(compliant) 근거 — 법적 한도 출처에 연동.
    compliant = candidate.get("compliant")
    if far_source in ("statutory", "statutory_fallback"):
        comp_src, comp_link = _link_for("statutory")
        comp_conf = "statutory"
    elif far_source == "ordinance":
        comp_src, comp_link = _link_for("ordinance")
        comp_conf = "ordinance"
    else:
        comp_src, comp_link, comp_conf = "법적 한도 미확인", None, "unknown"
    out.append(Evidence(
        claim="법적 한도 적합성",
        value=compliant,
        basis="조합 결과를 건폐율·용적률 상한과 대조(초과 시 부적합)",
        source=comp_src,
        confidence=comp_conf,
        link=comp_link,
    ))
    return out
