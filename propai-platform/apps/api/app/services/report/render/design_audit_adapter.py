"""설계심사(Design Audit) 결과 → 정본 ReportModel 어댑터.

★design_audit_pdf.build_design_audit_pdf(audit)가 읽던 audit dict(design_audits 행: overall/
  findings/blindspot/inputs)를 그대로 S0~S7 Block 으로 '옮겨 담기'만 한다(산식 복제 0).
  세 렌더러(PDF/PPTX/DOCX)는 이 정본 ReportModel 하나만 읽어 같은 문서를 만든다.

무목업/정직: findings·비교표본이 0건이면 design_audit_pdf.py 와 동일한 문구로 정직 표기한다.
법령 근거는 finding 이 이미 들고 있는 레지스트리 레코드(make_finding 이 get_legal_refs 로
해석해 넣은 legal_refs[])를 evidence_bridge 로 옮겨 담기만 한다 — 여기서 URL 을 조립하거나
새 법령키를 발명하지 않는다(verified 만 링크, 나머지는 텍스트). DB/외부서비스 임포트는 금지.
"""

from __future__ import annotations

from typing import Any

from .evidence_bridge import evidence_block_from_contract
from .model import (
    DataTableBlock,
    GradeBadgeBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    fmt_value,
)

# 심각도/상태 원문 코드 → 한글 라벨(design_audit_pdf._SEVERITY_LABEL 과 동일).
# ★실 U5 오케스트레이터 status 어휘(warning·skipped)를 포함해 정렬(과거 warn/pass만 매핑돼
#   실엔진 status가 원문 그대로 노출되던 절단 수정).
_SEVERITY_LABEL = {
    "high": "높음", "medium": "중간", "low": "낮음",
    "fail": "부적합", "warn": "주의", "warning": "주의",
    "pass": "적합", "info": "정보", "skipped": "생략", "not_checked": "미검사",
}


def _sev(f: dict[str, Any]) -> str:
    """finding 하나의 심각도/상태 값을 한글 라벨로 바꾼다(모르는 값은 원문 그대로)."""
    raw = str(f.get("severity") or f.get("status") or "-").lower()
    return _SEVERITY_LABEL.get(raw, raw)


def _finding_id(f: dict[str, Any]) -> str:
    """finding 식별자 — 여러 키 이름을 관용적으로 허용(check_id/rule_id/id/code)."""
    return str(f.get("check_id") or f.get("rule_id") or f.get("id") or f.get("code") or "—")


def _finding_text(f: dict[str, Any]) -> str:
    """finding 표시 문구 — 제목과 상세를 이어붙인다(계산이 아니라 표시용 이어붙이기)."""
    title = str(f.get("title") or f.get("message") or f.get("claim") or "").strip()
    detail = str(f.get("detail") or f.get("note") or "").strip()
    if title and detail and detail != title:
        return f"{title} — {detail}"
    return title or detail or "—"


def _group_findings(findings: Any) -> dict[str, list[dict[str, Any]]]:
    """findings(list 또는 {그룹: [...]} dict) → 섹션별 그룹.

    design_audit_pdf._group_findings 와 동일한 분류 휴리스틱: category/kind 문자열 →
    check_id 접두 → severity 순. 모호한 항목은 other 로 보존한다(정보 유실 금지).
    """
    groups: dict[str, list[dict[str, Any]]] = {
        "comparison": [], "engineering": [], "strength": [],
        "legal": [], "efficiency": [], "other": [],
    }
    if isinstance(findings, dict):
        for key, value in findings.items():
            if not isinstance(value, list):
                continue
            target = key if key in groups else "other"
            groups[target].extend(f for f in value if isinstance(f, dict))
        return groups
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        cat = str(f.get("category") or f.get("kind") or "").lower()
        cid = _finding_id(f).upper()
        sev = str(f.get("severity") or "").lower()
        # ★실 U5 오케스트레이터 정본 스키마 정렬: finding.engine으로 1차 분류(과거 ENG-/CMP- 접두는
        #   모킹 _FAKE_RESULT 계약이라 실 check_id[rules8_*/parking/permit_feasibility 등]와 절단됐다).
        eng = str(f.get("engine") or "").lower()
        if eng in {"rules8", "design_review", "solar_envelope", "parking",
                   "change_risk", "grammar", "bl_rules"}:
            groups["engineering"].append(f)
        elif eng == "case_compare":
            groups["comparison"].append(f)
        elif eng in {"permit", "incentives"}:
            groups["legal"].append(f)
        elif cat in {"engineering", "eng", "공학"} or cid.startswith("ENG"):
            groups["engineering"].append(f)
        elif cat in {"comparison", "deviation", "comparable", "사례", "비교"} or cid.startswith(("CMP", "REF")):
            groups["comparison"].append(f)
        elif (
            cat in {"legal", "incentive", "법규", "정책"}
            or cid.startswith(("LAW", "LEG", "INC"))
            or f.get("legal_ref_key") or f.get("legal_key") or f.get("legal_ref")
        ):
            groups["legal"].append(f)
        elif cat in {"efficiency", "효율"} or cid.startswith("EFF"):
            groups["efficiency"].append(f)
        elif sev in {"positive", "strength", "good"} or cat in {"strength", "장점"}:
            groups["strength"].append(f)
        else:
            groups["other"].append(f)
    return groups


def _comparables(audit: dict[str, Any]) -> list[dict[str, Any]]:
    """비교표본 목록 — inputs.derived_signals → inputs → overall 순 탐색(없으면 빈 목록 정직)."""
    inputs = audit.get("inputs") or {}
    overall = audit.get("overall") or {}
    for source in (
        (inputs.get("derived_signals") or {}) if isinstance(inputs, dict) else {},
        inputs if isinstance(inputs, dict) else {},
        overall if isinstance(overall, dict) else {},
    ):
        comps = source.get("comparables")
        if isinstance(comps, list):
            return [c for c in comps if isinstance(c, dict)]
    return []


def _metrics(audit: dict[str, Any], efficiency_findings: list[dict[str, Any]]) -> dict[str, Any]:
    """S7 설계 효율 지표 — overall.metrics/efficiency·derived_signals.metrics 순 탐색.

    어디에도 없으면 efficiency 그룹 findings 를 (id → 내용) 표로 폴백한다.
    """
    overall = audit.get("overall") or {}
    inputs = audit.get("inputs") or {}
    derived = inputs.get("derived_signals") if isinstance(inputs, dict) else {}
    for source in (overall, derived or {}):
        if not isinstance(source, dict):
            continue
        for key in ("metrics", "efficiency", "efficiency_metrics"):
            m = source.get(key)
            if isinstance(m, dict) and m:
                return m
    return {_finding_id(f): _finding_text(f) for f in efficiency_findings}


def _collect_legal_refs(findings: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """모든 finding 에서 법령 근거를 수집해 (레코드 목록, 키 목록)으로 반환(수집만, 해석 없음).

    - make_finding 산출 finding 은 이미 해석된 레지스트리 레코드(legal_refs[])를 들고 있다
      → 그대로 모은다(레코드의 url/url_status 를 신뢰 — 여기서 재조립 금지).
    - 레코드 없이 참조키만 가진 finding(legal_ref_key/legal_key/ref_key)은 키를 모아
      브리지가 표준 빌더(evidence_contract.build_legal_refs)로 해석하게 한다.
    """
    records: list[dict[str, Any]] = []
    keys: list[str] = []
    flat: list[dict[str, Any]] = []
    if isinstance(findings, dict):
        for value in findings.values():
            if isinstance(value, list):
                flat.extend(f for f in value if isinstance(f, dict))
    elif isinstance(findings, list):
        flat = [f for f in findings if isinstance(f, dict)]
    for f in flat:
        refs = f.get("legal_refs")
        if isinstance(refs, list):
            records.extend(r for r in refs if isinstance(r, dict))
        for key_field in ("legal_ref_key", "legal_key", "ref_key"):
            k = f.get(key_field)
            if k and str(k) not in keys:
                keys.append(str(k))
    return records, keys


def _grade_from_overall(overall: dict[str, Any]) -> str | None:
    """overall dict에 이미 있는 종합판정/등급 필드를 그대로 읽는다(산식·추정 없음)."""
    for key in ("grade", "overall_grade", "decision", "verdict"):
        v = overall.get(key)
        if v not in (None, ""):
            return str(v)
    return None


def _finding_table(items: list[dict[str, Any]], limit: int = 30) -> DataTableBlock:
    """findings 목록 → (ID, 내용, 심각도) 3열 표. design_audit_pdf._finding_table 과 동일 구성."""
    rows = [[_finding_id(f), _finding_text(f), _sev(f)] for f in items[:limit]]
    return DataTableBlock(headers=["ID", "내용", "심각도"], rows=rows)


def build_report_model_from_design_audit(data: dict[str, Any]) -> ReportModel:
    """설계심사 audit dict(design_audits 행) → 정본 ReportModel.

    build_design_audit_pdf 가 읽던 overall/findings/blindspot/inputs 을 그대로 Block 으로
    옮겨 담는다. 섹션 순서는 원본 PDF의 S0~S7 을 그대로 유지한다(제목에 번호가 이미 있어
    section_no 는 비운다).
    """
    overall = data.get("overall") if isinstance(data.get("overall"), dict) else {}
    groups = _group_findings(data.get("findings"))
    blindspot = data.get("blindspot") if isinstance(data.get("blindspot"), dict) else None
    comps = _comparables(data)

    meta = ReportMeta(
        title="설계심사 리포트",
        subtitle=f"프로젝트 {fmt_value(data.get('project_id'))}",
        doc_no=f"DA-{data['id']}" if data.get("id") else None,
        generated_at=fmt_value(data.get("created_at")) if data.get("created_at") else None,
        confidential=False,
    )

    sections: list[Section] = []

    # ── S0. 종합판정·요약 ──
    s0_blocks: list[Any] = []
    grade = _grade_from_overall(overall)
    if grade:
        s0_blocks.append(GradeBadgeBlock(grade=grade, label="종합판정"))
    if overall:
        s0_blocks.append(KVTableBlock(rows=[(str(k), v) for k, v in overall.items()]))
    else:
        s0_blocks.append(NarrativeBlock(paragraphs=["종합판정 데이터 없음."]))
    sections.append(Section(title="S0. 종합판정·요약", blocks=s0_blocks))

    # ── S1. 비교표본 명세 ──
    if comps:
        rows = []
        for i, c in enumerate(comps[:15], start=1):
            label = str(c.get("title") or c.get("id") or f"표본 {i}")
            desc = ", ".join(f"{k}: {fmt_value(v)}" for k, v in c.items() if k not in {"title", "id"})
            rows.append([label, desc or "—"])
        s1_blocks: list[Any] = [DataTableBlock(headers=["표본", "내용"], rows=rows)]
    else:
        # 표본 0건 — 가짜 비교 금지, 정직 명시(design_audit_pdf.py와 동일 문구).
        s1_blocks = [NarrativeBlock(paragraphs=[
            "비교 사례 없음 — 등록된 비교 표본이 없어 사례 기반 비교 진단은 제공하지 않습니다."])]
    sections.append(Section(title="S1. 비교표본 명세", blocks=s1_blocks))

    # ── S2. 문제점 — 비교 사례 편차 ──
    problems = list(groups["comparison"])
    problems += [
        f for f in groups["other"]
        # severity(모킹 계약) 또는 status(실 U5 — fail/warning) 어느 쪽이든 문제군으로 편입.
        if str(f.get("severity") or f.get("status") or "").lower()
        in {"high", "medium", "fail", "warn", "warning"}
    ]
    s2_blocks = [_finding_table(problems)] if problems else [
        NarrativeBlock(paragraphs=["확인된 문제점(사례 편차) 없음."])]
    sections.append(Section(title="S2. 문제점 — 비교 사례 편차", blocks=s2_blocks))

    # ── S3. 장점 ──
    s3_blocks = [_finding_table(groups["strength"])] if groups["strength"] else [
        NarrativeBlock(paragraphs=["데이터로 확인된 장점 항목 없음."])]
    sections.append(Section(title="S3. 장점", blocks=s3_blocks))

    # ── S4. 적용 가능 법규·정책 인센티브 ──
    # ★법령 링크는 legal_reference_registry 조회 결과라 여기서 조립하지 않는다(참조키만 전달).
    if groups["legal"]:
        rows = []
        for f in groups["legal"][:20]:
            ref_key = f.get("legal_ref_key") or f.get("legal_key") or f.get("ref_key")
            rows.append([_finding_id(f), _finding_text(f), fmt_value(ref_key)])
        s4_blocks: list[Any] = [DataTableBlock(headers=["ID", "내용", "법령 참조키"], rows=rows)]
    else:
        s4_blocks = [NarrativeBlock(paragraphs=["확인된 적용 가능 법규·정책 인센티브 항목 없음."])]
    sections.append(Section(title="S4. 적용 가능 법규·정책 인센티브", blocks=s4_blocks))

    # ── S5. 공학적 문제점 — 정량 룰 점검표 ──
    s5_blocks: list[Any] = []
    if groups["engineering"]:
        s5_blocks.append(_finding_table(groups["engineering"]))
    else:
        s5_blocks.append(NarrativeBlock(paragraphs=["공학 룰 점검 결과 없음(입력 데이터 부족)."]))
    # 고정 고지 — 자동 점검 범위 한계(항상 출력, design_audit_pdf.py와 동일).
    s5_blocks.append(NarrativeBlock(paragraphs=[
        "※ 구조상세·설비(기계·전기·소방)는 본 자동 점검 범위 밖입니다 — 해당 분야 기술사 확인 필요."]))
    sections.append(Section(title="S5. 공학적 문제점 — 정량 룰 점검표", blocks=s5_blocks))

    # ── S6. 심의 예상 쟁점 — [AI 추정] ──
    bs_items = (blindspot or {}).get("items") if isinstance(blindspot, dict) else None
    s6_blocks: list[Any] = []
    if bs_items:
        for it in bs_items[:10]:
            if not isinstance(it, dict):
                continue
            gate = it.get("citation_gate") or {}
            claim = f"[AI 추정] {fmt_value(it.get('claim'))}"
            note = f"근거: {fmt_value(it.get('basis'))} · 신뢰도: {fmt_value(it.get('confidence'))}"
            if gate.get("gated"):
                note += " · 인용검문: 치환됨"
            s6_blocks.append(NarrativeBlock(paragraphs=[claim, note]))
        if isinstance(blindspot, dict) and blindspot.get("summary"):
            s6_blocks.append(NarrativeBlock(paragraphs=[f"요약: {fmt_value(blindspot['summary'])}"]))
        s6_blocks.append(NarrativeBlock(paragraphs=[
            "※ 본 섹션은 AI 추정이며 확정이 아닙니다. 실제 심의 쟁점은 위원회 구성·지역 여건에 따라 달라집니다."]))
    else:
        s6_blocks.append(NarrativeBlock(paragraphs=["AI 추정 쟁점이 생성되지 않아 본 섹션은 생략합니다."]))
    sections.append(Section(title="S6. 심의 예상 쟁점 — [AI 추정]", blocks=s6_blocks))

    # ── S7. 설계 효율 지표 ──
    metrics = _metrics(data, groups["efficiency"])
    if metrics:
        s7_blocks: list[Any] = [KVTableBlock(rows=[(str(k), v) for k, v in list(metrics.items())[:20]])]
    else:
        s7_blocks = [NarrativeBlock(paragraphs=["설계 효율 지표 데이터 없음."])]
    sections.append(Section(title="S7. 설계 효율 지표", blocks=s7_blocks))

    # ── S8. 인용 법령 근거·링크 — finding 이 실제 들고 있는 법령 근거가 있을 때만(정직) ──
    # make_finding 이 각 finding 에 넣어 둔 레지스트리 레코드(legal_refs[]) + 키만 가진
    # finding 의 참조키를 브리지로 옮겨 담는다(verified URL 만 링크, pending 은 텍스트).
    ref_records, ref_keys = _collect_legal_refs(data.get("findings"))
    ev_block = evidence_block_from_contract(
        {"legal_refs": ref_records, "legal_ref_keys": ref_keys}, title=None)
    if ev_block is not None:
        sections.append(Section(title="S8. 인용 법령 근거·링크", blocks=[ev_block]))

    # ── 책임한계·면책(ReportModel.disclaimer — 렌더러가 공통 위치에 표기) ──
    disclaimer = (
        "본 리포트는 공개데이터·결정론 룰체크·AI 보조 분석 기반의 참고 자료이며 법적 효력이 없습니다. "
        "인허가 적합 여부의 최종 판단은 허가권자(지자체) 소관이고, 심의 결과를 보장하지 않습니다. "
        "구조 안전·상세 설계, 기계·전기·소방 설비는 본 자동 심사 범위 밖이며 반드시 해당 분야 "
        "기술사(건축구조기술사 등)와 건축사의 확인을 받아야 합니다. "
        "[AI 추정] 라벨 항목은 생성형 AI의 추정으로 오류가 있을 수 있으며, 인용 검문(citation gate)에서 "
        "근거가 확인되지 않은 수치·법조문은 '전문가 확인 필요'로 치환되어 있습니다. "
        "최종 의사결정 책임은 사용자에게 있습니다."
    )

    return ReportModel(meta=meta, sections=sections, disclaimer=disclaimer)
