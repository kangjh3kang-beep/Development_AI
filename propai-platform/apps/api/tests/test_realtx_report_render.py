"""실거래 보고서 렌더 — **문서가 말하면 안 되는 것**을 잠근다(모양이 아니라 주장).

★화면(패널)과 **같은 계약**을 문서에서도 지켜야 한다. 두 표면이 다른 말을 하면
  어느 쪽이 맞는지 사용자가 알 수 없다.
"""

from __future__ import annotations

import pytest

from app.services.report.render.engine import render_report
from app.services.report.render.model import DataTableBlock, KPITileBlock, NarrativeBlock
from app.services.report.render.realtx_adapter import build_report_model_from_realtx


def _payload(**over):
    base = {
        "months": ["202603", "202608"],
        "groups": [{
            "lawd_cd": "11590", "dong": "상도동", "parcels": [{}, {}],
            "summary": {"total": 2, "cancelled": 1, "cancelled_pct": 50.0, "direct": 1,
                        "brokered": 1, "registered": 1, "registered_pct": 50.0,
                        "corporate_buyer": 1, "corporate_seller": 0, "share_deals": 1},
            "transactions": [
                {"deal_date": "2026년 7월 1일", "jimok": "임야", "area_m2": 1795.0,
                 "price_10k_won": 12000, "dealing_type": "직거래", "registered_date": "",
                 "buyer_type": "법인", "seller_type": "개인", "cancel_type": "O",
                 "cancel_date": "26.07.20", "share_dealing_type": "지분"},
                {"deal_date": "2026년 7월 5일", "jimok": "전", "area_m2": 300.0,
                 "price_10k_won": 5000, "dealing_type": "중개거래", "registered_date": "26.07.10",
                 "buyer_type": "개인", "seller_type": "개인", "cancel_type": " ",
                 "share_dealing_type": ""},
            ],
            "parcel_level_match": None, "parcel_level_match_absent": "masked_by_source",
            "parcel_level_match_basis": "ZZ고유사유토큰: 국토부가 지번을 마스킹합니다.",
        }],
        "unlocated_parcels": [], "fetch_errors": [],
        "meta": {"parcel_count": 3, "lawd_count": 1, "month_count": 6,
                 "molit_calls": 6, "unlocated_count": 0},
        "note": "국토교통부 공개자료 기준입니다.",
    }
    base.update(over)
    return base


def _all_text(model) -> str:
    """모델 전체의 사람이 읽는 텍스트를 모은다(어느 블록에 있든)."""
    out: list[str] = [model.meta.title, model.meta.subtitle or "", model.disclaimer or ""]
    for sec in model.sections:
        out.append(sec.title)
        for b in sec.blocks:
            if isinstance(b, NarrativeBlock):
                out += b.paragraphs + [b.title or ""]
            elif isinstance(b, DataTableBlock):
                out += b.headers + [b.caption or "", b.title or ""]
                out += [str(c) for r in b.rows for c in r]
            elif isinstance(b, KPITileBlock):
                out += [f"{t.label}{t.value}{t.basis or ''}" for t in b.tiles]
            else:
                out.append(str(getattr(b, "text", "") or ""))
                for r in getattr(b, "rows", []) or []:
                    out += [str(x) for x in r]
    return "\n".join(out)


class Test문서금지주장:
    def test_귀속불가_사유를_본문에_싣는다(self) -> None:
        """★면책 문구에만 적으면 아무도 안 읽는다 — **본문 서술**이어야 한다."""
        m = build_report_model_from_realtx(_payload())
        narratives = [
            p for sec in m.sections for b in sec.blocks
            if isinstance(b, NarrativeBlock) for p in b.paragraphs
        ]
        assert any("마스킹" in p for p in narratives), "귀속 불가 사유가 본문 서술에 없다"
        # 백엔드가 준 문구를 **그대로** 싣는지(문서가 지어내지 않는지)
        assert any("ZZ고유사유토큰" in p for p in narratives), "백엔드 사유 문구를 버렸다"

    def test_미등기라고_단정하지_않는다(self) -> None:
        """등기일자 공란은 **'미기재'** 다 — 데이터 셀이 '미등기'라고 단정하면 안 된다.

        ★단언을 **데이터 셀로 좁힌다.** 처음엔 문서 전체에서 `"미등기" not in t` 로 봤는데
          **내가 쓴 설명 문장**(*"…미기재이며 미등기를 뜻하지 않습니다"*)이 걸려 **위양성**이 났다.
          설명이 그 단어를 쓰는 것은 정당하다 — 금지 대상은 **값 자리**다.
          (메모리 「내 패턴이 내 텍스트를 집는다」의 재발 — 이번엔 내 테스트가 잡았다.)
        """
        m = build_report_model_from_realtx(_payload())
        tbl = next(b for sec in m.sections for b in sec.blocks
                   if isinstance(b, DataTableBlock) and b.title == "날짜별 신고 내역")
        reg_col = tbl.headers.index("등기일자")
        cells = [str(r[reg_col]) for r in tbl.rows]
        assert "미기재" in cells, f"공란을 '미기재'로 안 썼다: {cells}"
        assert not any("미등기" in c for c in cells), f"값 자리에 '미등기'를 썼다: {cells}"
        # 대조군 — 실제 등기일자가 있는 행은 그대로 실린다(이 단언이 공허하지 않음을 증명)
        assert "26.07.10" in cells

    def test_조회실패를_거래0건과_섞지_않는다(self) -> None:
        """★실패를 0건으로 적으면 *'그 달엔 거래가 없었다'* 는 거짓 사실이 된다."""
        m = build_report_model_from_realtx(_payload(
            groups=[], fetch_errors=[{"lawd_cd": "11590", "deal_ym": "202607", "error": "RuntimeError"}]))
        t = _all_text(m)
        assert "조회하지 못한 기간" in t
        assert "빠져 있습니다" in t and "거래가 없었던 것이 아닙니다" in t
        # 대조군 — 실패가 없으면 그 표가 없어야 한다(항상 뜨는 상수가 아님을 증명)
        assert "조회하지 못한 기간" not in _all_text(build_report_model_from_realtx(_payload()))

    def test_정상건은_스페이스라_해제로_적지_않는다(self) -> None:
        """★★문서화된 함정 — 정상 건의 `cancel_type` 은 `' '`(스페이스)다."""
        m = build_report_model_from_realtx(_payload())
        tbl = next(b for sec in m.sections for b in sec.blocks
                   if isinstance(b, DataTableBlock) and b.title == "날짜별 신고 내역")
        states = [r[-1] for r in tbl.rows]
        assert states.count("정상") == 1, f"스페이스를 해제로 적었다: {states}"
        assert any(s.startswith("해제") for s in states)

    def test_조회횟수를_문서에_남긴다(self) -> None:
        """관측 가능성 — 쿼터 접기가 작동했는지 문서만 보고도 확인된다."""
        t = _all_text(build_report_model_from_realtx(_payload()))
        assert "국토부 조회 횟수" in t and "6회" in t

    def test_측위불가_필지를_버리지_않는다(self) -> None:
        m = build_report_model_from_realtx(_payload(
            unlocated_parcels=[{"pnu": None, "jibun_label": "주소만", "transactions_basis": "PNU 없음"}],
            meta={"parcel_count": 3, "lawd_count": 1, "month_count": 6,
                  "molit_calls": 6, "unlocated_count": 1}))
        assert "조회 대상에서 제외된 필지" in _all_text(m)


class Test정본통로:
    @pytest.mark.parametrize("fmt", ["pdf", "docx", "pptx"])
    def test_세_포맷이_실제로_렌더된다(self, fmt: str) -> None:
        """★`publish_gate` 를 통과하고 **바이트가 나오는지**까지 태운다.

        어댑터 단위 테스트만으로는 렌더러 계약 위반을 못 잡는다(선례: `signal` 이름을
        넣어 PDF 가 500 으로 죽었는데 docx 는 조용히 통과했다).
        """
        m = build_report_model_from_realtx(_payload())
        data, media_type, ext = render_report(m, fmt)
        assert len(data) > 1000, f"{fmt} 산출물이 비정상적으로 작다: {len(data)}"
        assert ext == fmt and media_type

    def test_KPI_신호색이_hex로_정규화된다(self) -> None:
        """★렌더러는 hex 만 받는다 — 이름을 넘기면 PDF 가 500 으로 죽는다(문서화된 실사고)."""
        m = build_report_model_from_realtx(_payload())
        tiles = next(b for sec in m.sections for b in sec.blocks
                     if isinstance(b, KPITileBlock)).tiles
        sigs = [t.signal for t in tiles if t.signal]
        assert sigs, "신호색이 하나도 없다 — 이 테스트가 공허해진다"
        assert all(s.startswith("#") for s in sigs), f"hex 가 아니다: {sigs}"

    def test_승인등급은_DRAFT다(self) -> None:
        """원천 공개자료 정리물이지 전문가 검토물이 아니다 — 등급을 사칭하지 않는다."""
        assert build_report_model_from_realtx(_payload()).meta.approval_state == "DRAFT"
