"""실거래 **신고내역 현황분석** 결과 → 정본 `ReportModel` 어댑터.

★`render/__init__` 이 못박은 규칙을 따른다 — **산식을 여기서 계산하지 않는다.**
  `realtx_report_service.build_realtx_report` 가 만든 값을 **Block 으로 옮겨 담기만** 한다.

## ★이 보고서가 말하면 안 되는 것 (서비스와 같은 계약을 문서에서도 지킨다)

1. **"필지별"** — 국토부는 토지 거래의 **지번을 마스킹**한다(라이브 실측 2026-08-26: 114/114).
   그래서 집계는 **법정동 단위**이고, 그 사유를 **면책이 아니라 본문 서술로** 싣는다.
   *면책 문구에만 적으면 아무도 안 읽는다.*
2. **"거래 0건"** — 조회 실패는 `fetch_errors` 로 **따로** 적는다. 0건과 섞으면
   *"그 달엔 거래가 없었다"* 는 **거짓 사실**이 생긴다.
3. **"미등기"** — 등기일자는 원천에서 약 30%만 채워진다. 공란은 **"미기재"** 다.

## 승인 등급

`approval_state="DRAFT"` 로 낸다 — 이 산출물은 **원천 공개자료의 정리**이지 전문가 검토물이
아니다. `publish_gate` 는 DRAFT 에서 금지어를 **soft(경고)** 로만 다루므로 차단되지 않는다.
"""

from __future__ import annotations

from typing import Any

from app.services.report.render.model import (
    DataTableBlock,
    KPITile,
    KPITileBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
)

#: 표 헤더 — 화면(패널)과 **같은 축**을 쓴다(두 표면이 다른 말을 하지 않게).
_TX_HEADERS = [
    "거래일", "지목", "면적(㎡)", "거래가(만원)",
    # ★단가는 **화면과 같은 서버 값**을 옮겨 담기만 한다 — 여기서 다시 나누지 않는다.
    #   `market_report.py:554` 가 *"산식을 여기서 다시 계산하지 않는다"* 를 선언한 그 계약이다.
    "만원/평",
    "거래유형", "등기일자", "매수/매도", "상태",
]


def _fmt_won_man(v: Any) -> str:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return "—"
    return f"{n:,}"


#: 보류 사유 → 문서에 찍을 짧은 말. ★`"—"` 하나로 뭉개지 않는다 —
#: 면적 결측 열이 이미 `"—"` 를 쓰므로, 같은 글리프를 쓰면 「해제라 해당 없음」과
#: 「원천이 가림」이 구별되지 않는다(이 저장소가 `0㎡ × 0원/㎡` 로 값을 치른 형태).
_PP_ABSENT_SHORT = {
    # ★"해제" 금지 — **상태 열이 이미 그 말을 한다**(화면과 같은 이유).
    "not_applicable": "해당없음",
    "masked_by_source": "원천미제공",
    "source_unavailable": "조회실패",
}


def _fmt_per_pyeong(t: dict[str, Any]) -> str:
    """만원/평 — 서버가 실은 값을 그대로. 없으면 **왜 없는지**를 짧게 찍는다."""
    v = t.get("price_per_pyeong_10k")
    if isinstance(v, (int, float)) and v > 0:
        return f"{int(v):,}"
    code = str(t.get("price_per_pyeong_10k_absent") or "").strip()
    return _PP_ABSENT_SHORT.get(code, "—")


def _tx_row(t: dict[str, Any]) -> list[Any]:
    """거래 1건 → 표 행. ★정상 건의 `cancel_type` 은 `' '`(스페이스)라 `strip()` 필수."""
    cancelled = bool(str(t.get("cancel_type") or "").strip())
    state = "해제"
    if cancelled and str(t.get("cancel_date") or "").strip():
        state = f"해제({str(t.get('cancel_date')).strip()})"
    elif not cancelled:
        state = "정상"
    dealing = str(t.get("dealing_type") or "").strip() or "—"
    if str(t.get("share_dealing_type") or "").strip() == "지분":
        dealing += "·지분"
    return [
        str(t.get("deal_date") or "—"),
        str(t.get("jimok") or "—"),
        f"{float(t.get('area_m2') or 0):,.1f}" if t.get("area_m2") else "—",
        _fmt_won_man(t.get("price_10k_won")),
        _fmt_per_pyeong(t),
        dealing,
        # ★"미등기"라고 쓰지 않는다 — 원천 미기재일 뿐이다.
        str(t.get("registered_date") or "").strip() or "미기재",
        f"{str(t.get('buyer_type') or '—')}/{str(t.get('seller_type') or '—')}",
        state,
    ]


def _summary_tiles(s: dict[str, Any]) -> KPITileBlock:
    total = int(s.get("total") or 0)
    cancelled = int(s.get("cancelled") or 0)
    return KPITileBlock(tiles=[
        KPITile(label="신고 건수", value=f"{total}건"),
        KPITile(
            label="계약 해제", value=f"{cancelled}건",
            basis=f"{s.get('cancelled_pct', 0)}%",
            # ★이름을 줘도 계약이 hex 로 정규화한다(model._validate_signal).
            signal="danger" if cancelled else "safe",
        ),
        KPITile(
            label="등기 기재", value=f"{int(s.get('registered') or 0)}건",
            basis=f"{s.get('registered_pct', 0)}% · 원천 기재율(미기재가 미등기는 아님)",
        ),
        KPITile(
            label="직거래/중개",
            value=f"{int(s.get('direct') or 0)}/{int(s.get('brokered') or 0)}",
        ),
    ])


def build_report_model_from_realtx(
    payload: dict[str, Any], *, project_name: str | None = None,
) -> ReportModel:
    """`build_realtx_report` 결과 → 정본 `ReportModel`. **값을 새로 계산하지 않는다.**"""
    meta_in = payload.get("meta") or {}
    months = payload.get("months") or []
    groups = payload.get("groups") or []
    errors = payload.get("fetch_errors") or []
    unlocated = payload.get("unlocated_parcels") or []

    period = f"{months[0]}~{months[-1]}" if months else "—"
    meta = ReportMeta(
        title="실거래 신고내역 현황분석 보고서",
        subtitle=f"{project_name or '프로젝트'} · 조회기간 {period}",
        completeness={
            "total": int(meta_in.get("parcel_count") or 0),
            "filled": int(meta_in.get("parcel_count") or 0) - int(meta_in.get("unlocated_count") or 0),
            "empty": int(meta_in.get("unlocated_count") or 0),
        },
        approval_state="DRAFT",
    )

    sections: list[Section] = []

    # ── ① 조회 범위 — **무엇을 몇 번 조회했는지**를 먼저 밝힌다(관측 가능성)
    scope = Section(title="조회 범위", section_no=1, blocks=[
        KVTableBlock(rows=[
            ("대상 필지", f"{meta_in.get('parcel_count', 0)}필지"),
            ("조회 지역", f"시군구 {meta_in.get('lawd_count', 0)}개"),
            ("조회 기간", f"{period} ({meta_in.get('month_count', 0)}개월)"),
            ("국토부 조회 횟수", f"{meta_in.get('molit_calls', 0)}회"),
            ("측위 불가 필지", f"{meta_in.get('unlocated_count', 0)}필지"),
        ]),
        # ★귀속 한계를 **본문**에 쓴다 — 면책에만 적으면 아무도 안 읽는다.
        NarrativeBlock(
            title="집계 단위에 대한 고지",
            claim_type="FACT",
            paragraphs=[
                "국토교통부 실거래 공개자료는 **토지 거래의 지번을 마스킹**합니다. "
                "따라서 개별 신고 건을 특정 필지에 귀속시킬 수 없어, 이 보고서는 "
                "**법정동 단위**로 집계했습니다 — 각 절의 표는 그 동에 속한 프로젝트 필지의 "
                "주변 신고내역입니다.",
                "등기일자는 원천에서 일부만 기재됩니다. 공란은 **'미기재'** 이며 "
                "미등기를 뜻하지 않습니다.",
            ],
        ),
    ])
    # ★조회 실패는 **0건과 섞지 않는다** — 별도 표로 남긴다.
    if errors:
        scope.blocks.append(DataTableBlock(
            title="조회하지 못한 기간",
            headers=["시군구", "조회월", "사유"],
            rows=[[e.get("lawd_cd", "—"), e.get("deal_ym", "—"), e.get("error", "—")] for e in errors],
            caption="아래 집계에서 이 기간은 **빠져 있습니다** — 거래가 없었던 것이 아닙니다.",
        ))
    sections.append(scope)

    # ── ② 법정동별 현황 + 날짜별 내역
    for i, g in enumerate(groups, start=2):
        s = g.get("summary") or {}
        txs = g.get("transactions") or []
        blocks: list[Any] = [_summary_tiles(s)]
        extra = []
        if int(s.get("corporate_buyer") or 0):
            extra.append(f"법인 매수 {s['corporate_buyer']}건")
        if int(s.get("corporate_seller") or 0):
            extra.append(f"법인 매도 {s['corporate_seller']}건")
        if int(s.get("share_deals") or 0):
            extra.append(f"지분거래 {s['share_deals']}건")
        if extra:
            blocks.append(NarrativeBlock(claim_type="FACT", paragraphs=[" · ".join(extra)]))
        if txs:
            blocks.append(DataTableBlock(
                title="날짜별 신고 내역",
                headers=list(_TX_HEADERS),
                rows=[_tx_row(t) for t in txs],
                numeric_cols=[2, 3],
                caption=f"이 동에 속한 프로젝트 필지 {len(g.get('parcels') or [])}필지 · 신고 {len(txs)}건",
            ))
        # ★백엔드가 말한 귀속 불가 사유를 **그대로** 싣는다(문서가 지어내지 않는다).
        basis = g.get("parcel_level_match_basis")
        if basis:
            blocks.append(NarrativeBlock(title="필지 단위 귀속 불가", claim_type="FACT",
                                         paragraphs=[str(basis)]))
        sections.append(Section(title=f"{g.get('dong') or '—'} 신고 현황", section_no=i, blocks=blocks))

    # ── ③ 조회 대상에서 빠진 필지 — 버리지 않고 적는다
    if unlocated:
        sections.append(Section(
            title="조회 대상에서 제외된 필지", section_no=len(sections) + 1,
            blocks=[DataTableBlock(
                headers=["PNU", "지번", "사유"],
                rows=[[u.get("pnu") or "—", u.get("jibun_label") or "—",
                       u.get("transactions_basis") or "—"] for u in unlocated],
            )],
        ))

    return ReportModel(
        meta=meta,
        sections=sections,
        disclaimer=str(payload.get("note") or ""),
    )
