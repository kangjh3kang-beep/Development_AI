"""등기 **권리분석 보고서** 어댑터 — 다필지 일괄분석 결과 → 정본 `ReportModel`.

## 왜 새 PDF 경로를 만들지 않았나

이 저장소에는 이미 `ReportModel` + PDF/PPTX/DOCX 렌더러 + 발행 게이트가 있다. 새 PDF 를
직접 그리면 표지·정직 채움도·승인등급·미검증 단정 경고가 전부 따라오지 않는다. 그래서
**어댑터 한 벌**만 더한다 — 세 포맷이 함께 생긴다.

## 이 어댑터가 지키는 것 (실장애에서 나온 요구)

1. **분석되지 않은 필지를 숨기지 않는다.** 2026-08-24 라이브에서 오산 내삼미동 448-2·347-8 은
   등기부가 **정상 발급**됐는데 권리분석(LLM)만 실패했다. 그런 건을 표에서 빼면 보고서는
   "N필지 전부 안전"이라고 말하게 된다 — **없는 안전을 만든다.** 그래서 §미분석 섹션을
   **항상** 두고, 요약 타일도 `분석 N / 전체 M` 으로 분모를 드러낸다.
2. **`ai.generated` 로만 성공을 센다.** LLM 폴백도 `ai` 를 dict 로 돌려주고
   `safety_grade:"주의"` 까지 담는다 — 존재로 세면 실패가 성공으로 잡힌다.
   (프론트 `isAnalyzed()` · 서버 `_cache_success()` 와 **같은 계약**이다.)
3. **합계는 분석된 건에서만 낸다.** 미분석 필지를 0으로 깔고 더하면 "근저당 총액"이
   실제보다 작게 나와 낙관 쪽으로 틀린다 — 그 방향의 오차가 가장 위험하다.
"""

from __future__ import annotations

import re
from typing import Any

from .model import (
    DataTableBlock,
    KPITile,
    KPITileBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
)
from .tokens import SIGNAL

# 등급 → 타일 신호색. 알 수 없는 등급은 **색을 칠하지 않는다**(임의로 안전/위험에 몰지 않는다).
# ★값은 `tokens.SIGNAL` 의 **hex** 여야 한다. `"warn"` 같은 이름을 넣으면 PDF 렌더러가
#   reportlab 색 파서에 그대로 넘겨 **다운로드가 500 으로 죽는다**(docx 는 색을 안 써서
#   조용히 통과한다 — 어댑터 단위 테스트만으로는 절대 안 잡힌다. 실측으로 잡았다).
_SIGNAL = {"안전": SIGNAL["safe"], "주의": SIGNAL["warn"], "위험": SIGNAL["danger"]}

_DASH = "—"


def _is_analyzed(result: Any) -> bool:
    """권리분석이 **실제로 생성됐는가**. 서버 `_cache_success` 와 같은 기준."""
    if not isinstance(result, dict):
        return False
    ai = result.get("ai")
    return bool(isinstance(ai, dict) and ai.get("generated"))


def _reason(result: Any) -> str:
    """왜 분석되지 않았는지. 구체적인 것부터 읽고, **없으면 없다고 말한다**(지어내지 않는다)."""
    if not isinstance(result, dict):
        return "요청 실패 — 응답을 받지 못했습니다"
    ai = result.get("ai")
    if isinstance(ai, dict):
        fr = str(ai.get("failure_reason") or "").strip()
        if fr:
            return f"권리분석 실패 — {fr}"
    msg = str(result.get("message") or "").strip()
    if msg:
        return msg
    return "사유 미제공(공급자가 이유를 주지 않음)"


_NUM = re.compile(r"[0-9]+")


def _won_to_int(v: Any) -> int | None:
    """'채권최고액 1억 2,000만원' 같은 자유 문자열에서 원 단위 정수를 뽑는다.

    ★뽑지 못하면 **None** 이다. 0 으로 만들면 "근저당 없음"과 구분이 사라져
    합계가 조용히 작아진다(낙관 방향 오차).
    """
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    s = str(v or "").strip()
    if not s:
        return None
    digits = "".join(_NUM.findall(s.replace(",", "")))
    if not digits:
        return None
    n = int(digits)
    # '억'·'만' 표기는 자릿수를 바꾼다 — 잘못 곱하느니 **판단을 보류**한다.
    if "억" in s or "만" in s:
        return None
    return n


def _rows_of(ai: dict[str, Any], key: str) -> list[dict[str, Any]]:
    v = ai.get(key)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def build_report_model_from_registry_rights(
    items: list[dict[str, Any]],
    *,
    project_address: str | None = None,
    generated_at: str | None = None,
) -> ReportModel:
    """일괄 등기분석 결과 → 권리분석 보고서 모델.

    Args:
        items: `[{"jibun": str, "result": {...analyze() 응답...}}, ...]` 순서 유지.
        project_address: 표지에 쓸 사업지 주소(없으면 첫 지번).
        generated_at: 생성 시각 문자열(호출측이 넣는다 — 어댑터는 시계를 읽지 않는다).
    """
    rows = [it for it in items if isinstance(it, dict)]
    total = len(rows)

    analyzed: list[tuple[str, dict[str, Any]]] = []
    unanalyzed: list[tuple[str, str]] = []
    for i, it in enumerate(rows):
        label = str(it.get("jibun") or "").strip() or f"필지{i + 1}"
        result = it.get("result")
        if _is_analyzed(result):
            analyzed.append((label, result["ai"]))
        else:
            unanalyzed.append((label, _reason(result)))

    n_ok = len(analyzed)

    # ── 요약 타일 ───────────────────────────────────────────────────────
    grades: dict[str, int] = {}
    n_mortgage = 0
    n_seizure = 0
    mortgage_sum = 0
    mortgage_unknown = 0
    for _, ai in analyzed:
        g = str(ai.get("safety_grade") or "").strip()
        if g:
            grades[g] = grades.get(g, 0) + 1
        ms = _rows_of(ai, "mortgage")
        n_mortgage += len(ms)
        n_seizure += len(_rows_of(ai, "seizure"))
        for m in ms:
            won = _won_to_int(m.get("max_claim"))
            if won is None:
                mortgage_unknown += 1
            else:
                mortgage_sum += won

    worst = "위험" if grades.get("위험") else "주의" if grades.get("주의") else "안전" if n_ok else ""
    # ★합계 근거에 **집계 모집단**을 적는다 — 분모를 감추면 부분 합계가 전체로 읽힌다.
    money_basis = f"분석된 {n_ok}필지 기준"
    if mortgage_unknown:
        money_basis += f" · 금액 판독 불가 {mortgage_unknown}건 제외"

    tiles = [
        KPITile(
            label="권리분석 완료",
            value=f"{n_ok} / {total} 필지",
            basis="미분석 필지는 아래 §미분석 참조" if n_ok < total else "전 필지 분석 완료",
            signal=SIGNAL["warn"] if n_ok < total else SIGNAL["safe"],
        ),
        KPITile(
            label="최고 위험등급",
            value=worst or _DASH,
            basis=" · ".join(f"{k} {v}" for k, v in sorted(grades.items())) or "분석 결과 없음",
            signal=_SIGNAL.get(worst),
        ),
        KPITile(label="근저당 설정", value=f"{n_mortgage}건", basis=money_basis),
        KPITile(label="압류·가압류", value=f"{n_seizure}건", basis=money_basis),
    ]

    lead = (
        f"대상 {total}필지 중 **{n_ok}필지**의 등기 권리관계를 분석했습니다."
        if n_ok
        else f"대상 {total}필지 중 권리분석이 완료된 필지가 **없습니다**."
    )
    if unanalyzed:
        lead += (
            f" 나머지 **{len(unanalyzed)}필지는 분석되지 않았습니다** — 아래 §미분석 필지에"
            " 필지별 사유를 적었습니다. **이 보고서의 판단은 분석된 필지에 한합니다.**"
        )
    exec_summary = Section(
        title="요약",
        blocks=[KPITileBlock(tiles=tiles), NarrativeBlock(paragraphs=[lead], claim_type="INTERPRETATION")],
    )

    sections: list[Section] = []

    # ── §1 필지별 권리 요약 ─────────────────────────────────────────────
    if analyzed:
        sections.append(
            Section(
                title="필지별 권리 요약",
                section_no=1,
                blocks=[
                    DataTableBlock(
                        headers=["지번", "소유자", "지분", "안전성", "근저당", "압류", "요약"],
                        rows=[
                            [
                                label,
                                (ai.get("ownership") or {}).get("current_owner") or _DASH,
                                (ai.get("ownership") or {}).get("share") or _DASH,
                                ai.get("safety_grade") or _DASH,
                                f"{len(_rows_of(ai, 'mortgage'))}건",
                                f"{len(_rows_of(ai, 'seizure'))}건",
                                ai.get("summary") or _DASH,
                            ]
                            for label, ai in analyzed
                        ],
                        numeric_cols=[4, 5],
                        caption="등기사항전부증명서 기재 사항에 대한 AI 해석입니다.",
                    )
                ],
            )
        )

    # ── §2 근저당·압류 상세 ─────────────────────────────────────────────
    detail: list[list[Any]] = []
    for label, ai in analyzed:
        for m in _rows_of(ai, "mortgage"):
            detail.append([label, "근저당", m.get("mortgagee") or _DASH, m.get("max_claim") or _DASH, m.get("date") or _DASH])
        for s in _rows_of(ai, "seizure"):
            detail.append([label, s.get("type") or "압류", s.get("holder") or _DASH, s.get("detail") or _DASH, s.get("date") or _DASH])
    if detail:
        sections.append(
            Section(
                title="근저당·압류 상세",
                section_no=len(sections) + 1,
                blocks=[
                    DataTableBlock(
                        headers=["지번", "구분", "권리자", "금액·내용", "일자"],
                        rows=detail,
                    )
                ],
            )
        )

    # ── §3 매도청구 가능성 ──────────────────────────────────────────────
    demand = [
        [label, (ai.get("right_to_demand_sale") or {}).get("possible") or _DASH,
         (ai.get("right_to_demand_sale") or {}).get("reason") or _DASH]
        for label, ai in analyzed
        if isinstance(ai.get("right_to_demand_sale"), dict)
    ]
    if demand:
        sections.append(
            Section(
                title="매도청구 가능성",
                section_no=len(sections) + 1,
                blocks=[
                    DataTableBlock(headers=["지번", "가능여부", "근거"], rows=demand),
                    NarrativeBlock(
                        paragraphs=[
                            "가능여부는 등기 기재사항만으로 본 예비 판단입니다. "
                            "실제 매도청구는 사업 유형·동의율·기간 요건을 함께 봐야 합니다."
                        ],
                        claim_type="INTERPRETATION",
                    ),
                ],
            )
        )

    # ── §4 ★미분석 필지 — 항상 만든다 ──────────────────────────────────
    if unanalyzed:
        sections.append(
            Section(
                title="미분석 필지 (권리분석이 완료되지 않음)",
                section_no=len(sections) + 1,
                blocks=[
                    NarrativeBlock(
                        paragraphs=[
                            "아래 필지는 권리분석 결과가 없습니다. 등기부가 발급된 경우에도 "
                            "해석 단계에서 실패하면 여기에 표시됩니다. 위 표의 판단은 이 필지들을 "
                            "포함하지 않습니다 — 안전하다는 뜻이 아닙니다."
                        ],
                        claim_type="FACT",
                    ),
                    DataTableBlock(headers=["지번", "사유"], rows=[[a, b] for a, b in unanalyzed]),
                ],
            )
        )

    filled = n_ok
    completeness = {
        "total": total,
        "filled": filled,
        "empty": total - filled,
        "pct": round(filled * 100 / total, 1) if total else 0.0,
    }

    meta = ReportMeta(
        title="등기 권리분석 보고서",
        subtitle=f"{total}필지 일괄 분석",
        project_address=project_address or (rows[0].get("jibun") if rows else None),
        generated_at=generated_at,
        completeness=completeness,
        # LLM 해석 산출물이다 — 승인 트랙에 올리지 않는다(정직 등급).
        approval_state="DRAFT",
    )

    return ReportModel(
        meta=meta,
        exec_summary=exec_summary,
        sections=sections,
        disclaimer=(
            "본 보고서는 등기사항전부증명서 기재사항에 대한 AI 해석이며 법률자문이 아닙니다. "
            "권리관계의 최종 확인은 등기부 원본과 전문가(법무사·변호사) 검토에 따르십시오. "
            "발급 시점 이후의 변동은 반영되지 않습니다."
        ),
    )


__all__ = ["build_report_model_from_registry_rights"]
