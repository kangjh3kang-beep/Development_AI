"""실거래 신고내역의 **만원/평** 열을 잠근다.

## 왜 (2026-08-28 라이브 실측 · 역삼동 6개월 71건)

원천의 1차 자료는 ㎡ 가 아니라 **평당 단가**다:

    area= 3.31㎡ → 1.001275평 | 2,000만원 | 1,997.45 만원/평 | 33건
    area= 6.61㎡ → 1.999525평 | 4,000만원 | 2,000.48 만원/평 | 12건

면적이 평의 정수배에 소수 여섯째 자리까지 붙는다. 결정적 대조군 — **같은 날 서로 다른 면적
3건이 소수 둘째 자리까지 동일 단가**(182.9/139.0/136.2㎡ → 전부 14,623.39). 전수로
만원/평이 정수·10단위에 붙는 행이 **71/71**.

★그래서 「금액 ÷ 면적」을 그대로 찍으면 원천의 ㎡ 반올림(±0.15%) 탓에 **같은 2,000만원/평
거래 45건이 1,997 과 2,000 두 값으로 갈린다** — 우리가 만든 가짜 가격차다.
이 파일의 첫 테스트가 정확히 그것을 잠근다.
"""

from __future__ import annotations

import pytest

from apps.api.app.services.land_intelligence.realtx_report_service import (
    attach_per_pyeong,
    per_pyeong_10k,
)
from apps.api.app.services.market.market_report_service import PYEONG_SQM


class Test파생이_살아있다:
    """★대조군 — 이게 죽으면 아래 「위반 0」이 전부 공허해진다."""

    def test_계수가_정본에서_온다(self) -> None:
        # ★뿌리를 늘리지 않는다. `3.3058`(121배 부정확)이 저장소에 공존한다.
        assert PYEONG_SQM == pytest.approx(3.305785, abs=1e-9)

    def test_정상값이_실제로_나온다(self) -> None:
        # 대조군이 없으면 "전부 None" 인 구현도 아래 보류 테스트를 통과한다.
        assert per_pyeong_10k(2_000, 3.31) is not None
        assert per_pyeong_10k(2_070_000, 330.5) == 20_700


class Test허위정밀도를_만들지_않는다:
    """★이 열의 존재 이유 — **없는 가격차를 만들지 않는다.**"""

    def test_같은_평당단가_거래는_같은_값으로_표시된다(self) -> None:
        # 1평(3.31㎡)/2,000만 과 2평(6.61㎡)/4,000만 은 **둘 다 2,000만원/평 거래**다.
        # 원시 나눗셈은 1,997.45 와 2,000.48 로 갈린다(라이브 45건).
        한평 = per_pyeong_10k(2_000, 3.31)
        두평 = per_pyeong_10k(4_000, 6.61)
        assert 한평 == 두평, f"같은 단가 거래가 다른 값으로 표시된다: {한평} vs {두평}"
        assert 한평 == 2_000

    def test_같은_날_다른_면적_3필지가_한_값으로_모인다(self) -> None:
        # 라이브: 총액이 `평 × 14,623` 으로 생성된 것(일괄 매수 추정).
        vals = {per_pyeong_10k(p, a) for a, p in ((182.9, 809_072), (139.0, 614_877), (136.2, 602_491))}
        assert len(vals) == 1, f"같은 단가인데 {len(vals)}개 값으로 갈렸다: {sorted(vals)}"

    def test_원시_나눗셈과_다르다(self) -> None:
        """★음성 대조군 — 반올림을 지우면(원시값 그대로) 위 두 테스트가 깨져야 한다.

        이 단언이 없으면 «반올림을 한다» 가 아니라 «우연히 같다» 로도 통과한다.
        """
        raw_한평 = 2_000 / (3.31 / PYEONG_SQM)
        raw_두평 = 4_000 / (6.61 / PYEONG_SQM)
        assert round(raw_한평) != round(raw_두평), (
            "원시 나눗셈이 이미 같은 값을 준다면 이 열엔 문제가 없었다는 뜻이다 — "
            "그러면 위 테스트는 아무것도 잠그지 않는다"
        )


class Test모름을_유효값으로_표현하지_않는다:
    """★「해제라 해당 없음」과 「원천이 가림」은 **다른 사유**다 — 한 글리프로 뭉개지 않는다."""

    def test_해제_행은_해당없음이다(self) -> None:
        (row,) = attach_per_pyeong([
            {"price_10k_won": 20_150, "area_m2": 102.3, "cancel_type": "O"},
        ])
        assert row["price_per_pyeong_10k"] is None
        assert row["price_per_pyeong_10k_absent"] == "not_applicable"
        assert row["price_per_pyeong_10k_basis"]

    def test_면적_결측은_원천가림이다(self) -> None:
        (row,) = attach_per_pyeong([{"price_10k_won": 2_000, "area_m2": None}])
        assert row["price_per_pyeong_10k"] is None
        assert row["price_per_pyeong_10k_absent"] == "masked_by_source"

    def test_두_보류가_서로_구별된다(self) -> None:
        """★파티션형 — 「전부 같은 사유」인 구현을 잡는다(존재 검사로는 못 잡는다)."""
        해제, 결측, 정상 = attach_per_pyeong([
            {"price_10k_won": 20_150, "area_m2": 102.3, "cancel_type": "O"},
            {"price_10k_won": 2_000, "area_m2": 0},
            {"price_10k_won": 2_000, "area_m2": 3.31},
        ])
        assert 해제["price_per_pyeong_10k_absent"] != 결측["price_per_pyeong_10k_absent"]
        assert 해제["price_per_pyeong_10k_basis"] != 결측["price_per_pyeong_10k_basis"]
        # ★그리고 정상 행은 **값이 실린다**(보류만 잠그면 "전부 보류"가 만점을 받는다).
        assert 정상["price_per_pyeong_10k"] == 2_000
        assert "price_per_pyeong_10k_absent" not in 정상

    def test_0원과_모름이_구별된다(self) -> None:
        """★`0` 은 「모름」이 아니다 — 이 저장소가 `0㎡ × 0원/㎡` 로 값을 치렀다."""
        (row,) = attach_per_pyeong([{"price_10k_won": 0, "area_m2": 3.31}])
        assert row["price_per_pyeong_10k"] is None
        assert row["price_per_pyeong_10k_absent"], "0 을 값으로 흘려보내면 안 된다"


class Test두_표면이_같은_말을_한다:
    """★화면에만 열이 생기고 **문서(PDF·PPTX·DOCX)에는 없는** 상태를 막는다."""

    def test_문서_헤더에_단가열이_있다(self) -> None:
        from apps.api.app.services.report.render.realtx_adapter import _TX_HEADERS

        assert "만원/평" in _TX_HEADERS, (
            "문서 어댑터에 단가 열이 없다 — 화면에서 본 근거가 제출 문서에서 사라진다"
        )

    def test_문서_행의_열수가_헤더와_같다(self) -> None:
        from apps.api.app.services.report.render.realtx_adapter import _TX_HEADERS, _tx_row

        row = _tx_row({"price_10k_won": 2_000, "area_m2": 3.31})
        assert len(row) == len(_TX_HEADERS), f"열 {len(row)} vs 헤더 {len(_TX_HEADERS)}"

    def test_문서가_보류_사유를_구별해_찍는다(self) -> None:
        from apps.api.app.services.report.render.realtx_adapter import _TX_HEADERS, _tx_row

        i = _TX_HEADERS.index("만원/평")
        해제 = _tx_row(attach_per_pyeong([
            {"price_10k_won": 20_150, "area_m2": 102.3, "cancel_type": "O"}])[0])
        결측 = _tx_row(attach_per_pyeong([{"price_10k_won": 2_000, "area_m2": None}])[0])
        정상 = _tx_row(attach_per_pyeong([{"price_10k_won": 2_000, "area_m2": 3.31}])[0])
        assert 해제[i] != 결측[i], "문서에서 두 보류가 같은 글자로 뭉개진다"
        assert 정상[i] == "2,000"
        # ★면적 열이 이미 쓰는 `"—"` 로 되돌아가지 않는지(글리프 충돌)
        assert 해제[i] != "—" and 결측[i] != "—"


class Test평균을_만들지_않는다:
    """★층화 없는 평균은 이 표본에서 거짓이다 — 요약 타일에 단가를 넣지 않는다.

    라이브 실측(역삼동 71건): 최빈 행이 **「도로 지분」 52/71 = 73%** 이고,
    지목 안에서 방향이 뒤집힌다(도로 지분/일반 **5.12배** · 대 지분/일반 **0.41배**).
    `molit_client.py:459` 도 *"섞으면 그 값은 무의미하다"* 라고 적어 두었다.
    """

    def test_요약에_평균단가가_없다(self) -> None:
        from apps.api.app.services.land_intelligence.realtx_report_service import (
            summarize_contract_state,
        )

        s = summarize_contract_state([
            {"price_10k_won": 2_000, "area_m2": 3.31, "share_dealing_type": "지분"},
            {"price_10k_won": 2_070_000, "area_m2": 330.5},
        ])
        leaked = [k for k in s if "pyeong" in k or "단가" in k]
        assert not leaked, f"요약에 단가가 샜다: {leaked} — 층화 없는 평균은 거짓이다"
