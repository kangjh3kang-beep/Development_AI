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
    _round_sig,
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


class Test배선이_실제로_돈다:
    """★**함수만 태우면 배선은 무잠금이다.**

    2026-08-28 실측: 위 테스트들이 `attach_per_pyeong` 을 **직접** 부르기만 해서,
    `build_realtx_report` 의 `"transactions": attach_per_pyeong(...)` 를
    `txs_sorted` 로 되돌리는 변이가 **SURVIVED** 했다. 조립 경로를 태운다.
    """

    @staticmethod
    def _run(txs: list[dict]) -> list[dict]:
        import asyncio

        from apps.api.app.services.land_intelligence import realtx_report_service as svc

        class _C:
            async def get_transactions(self, lawd, ym, prop_type="land"):
                return txs

        r = asyncio.run(svc.build_realtx_report(
            [{"pnu": "1159010200102100453", "jibun": "서울특별시 동작구 상도동 210-453"}],
            end_ym="202608", months=1, client=_C(),
        ))
        return r["groups"][0]["transactions"]

    def test_조립된_응답에_단가가_실린다(self) -> None:
        (row,) = self._run([{
            "dong": "상도동", "deal_date": "2026년 7월 1일",
            "area_m2": 3.31, "price_10k_won": 2_000,
        }])
        assert row["price_per_pyeong_10k"] == 2_000, (
            "조립 경로가 단가를 싣지 않는다 — 배선이 끊겼다"
        )

    def test_조립된_응답에서_해제행은_사유를_싣는다(self) -> None:
        """★두 모집단 — 「전부 값이 실린다」인 구현도 위 테스트는 통과한다."""
        정상, 해제 = self._run([
            {"dong": "상도동", "deal_date": "d1", "area_m2": 3.31, "price_10k_won": 2_000},
            {"dong": "상도동", "deal_date": "d2", "area_m2": 102.3, "price_10k_won": 20_150,
             "cancel_type": "O"},
        ])
        assert 정상["price_per_pyeong_10k"] == 2_000
        assert 해제["price_per_pyeong_10k"] is None
        assert 해제["price_per_pyeong_10k_absent"] == "not_applicable"

    def test_계수가_이_모듈에서도_정본이다(self) -> None:
        """★위 `test_계수가_정본에서_온다` 는 **뿌리**만 단언해서, 이 모듈이 로컬 상수를
        선언해 버리는 변이가 **SURVIVED** 했다(2026-08-28 실측).
        **코드가 실제로 쓰는 값**을 본다 — 3자리 반올림 뒤에는 두 계수의 차가 보이지 않으므로
        출력값으로는 원리적으로 잡을 수 없고, **모듈 속성 동일성**으로만 잠긴다.
        """
        from apps.api.app.services.land_intelligence import realtx_report_service as svc
        from apps.api.app.services.market import market_report_service as mrs

        assert svc.PYEONG_SQM == mrs.PYEONG_SQM, (
            f"이 모듈이 정본과 다른 계수를 쓴다: {svc.PYEONG_SQM} vs {mrs.PYEONG_SQM} — "
            "뿌리를 늘리지 마라(저장소에 3.3058 이 공존한다)"
        )


class Test리뷰가_찾은_구멍:
    """★독립 적대 리뷰(2026-08-28)가 **생존시킨 변이 5종**을 잠근다.

    내 «7종 전부 CAUGHT» 는 **내가 고른 7종에만** 참이었다.
    """

    def test_1만원_평_미만이_0으로_사라지지_않는다(self) -> None:
        """★HIGH-1 — 앞 판은 `int()` 절단이라 **저가 토지가 값 `0` 으로** 나갔다.

        임야 1ha / 3,000만원 = 3,000원/㎡ 는 지방 토지에 흔하고, 이 플랫폼의
        핵심 유스케이스(태양광·물류·전원주택)가 바로 그 대역이다.
        """
        v = per_pyeong_10k(3_000, 10_000.0)
        assert v is not None and v > 0, "저가 토지 단가가 사라졌다"
        assert v == pytest.approx(0.992, abs=1e-9)

    def test_0이_값처럼_실려_나가지_않는다(self) -> None:
        """★계약 검사가 통과시킨 그 자리 — `is_withheld` 로 판정한다."""
        from apps.api.app.utils.withheld import is_withheld

        (row,) = attach_per_pyeong([{"price_10k_won": 3_000, "area_m2": 10_000.0}])
        assert row["price_per_pyeong_10k"] != 0
        # 값이 있으면 보류가 아니어야 하고, 없으면 반드시 보류여야 한다(파티션형).
        if row.get("price_per_pyeong_10k") is None:
            assert is_withheld(row, "price_per_pyeong_10k")

    def test_1과_10_사이에서_자릿수를_잃지_않는다(self) -> None:
        """★`int()` 절단은 `9.99 → 9` 로 유효숫자를 하나 깎았다."""
        assert _round_sig(9.99) == pytest.approx(9.99)
        # ★1.005 → 1.00 은 **옳다**(유효숫자 3자리). 처음에 `> 1.0` 이라 썼는데
        #   그건 「3자리」가 아니라 「올림」을 기대한 것이었다 — 내 단언이 틀렸다.
        assert _round_sig(1.005) == pytest.approx(1.0)
        # 절단이었으면 아래가 1 이 된다(원래 결함을 되살리는 방향).
        assert _round_sig(1.29) == pytest.approx(1.29)

    def test_정상_해제표기_공백을_해제로_읽지_않는다(self) -> None:
        """★HIGH-3 — 형제 어댑터가 *"정상 건의 `cancel_type` 은 `' '`(스페이스)라 `strip()` 필수"*
        라고 **이미 적어 둔** 함정인데, 새 코드에서는 무잠금이었다(`.strip()` 제거 변이 SURVIVED).
        회귀하면 **정상 행 전부가 「해당없음」** 이 되어 표가 조용히 빈다.
        """
        (row,) = attach_per_pyeong([
            {"price_10k_won": 2_000, "area_m2": 3.31, "cancel_type": " "},
        ])
        assert row["price_per_pyeong_10k"] == pytest.approx(2_000), (
            "공백 cancel_type 을 해제로 읽었다 — 정상 거래가 전부 사라진다"
        )
        assert "price_per_pyeong_10k_absent" not in row

    def test_비정상_입력이_터지지_않고_거부된다(self) -> None:
        """★앞 판은 `inf` 에서 `OverflowError` 로 **터졌다**(문자열 `"inf"` 포함)."""
        assert per_pyeong_10k(float("inf"), 3.31) is None
        assert per_pyeong_10k("inf", "1") is None
        assert per_pyeong_10k(float("nan"), 3.31) is None
        # bool 은 파이썬에서 1/0 이라 조용히 통과한다 — 거부해야 한다.
        assert per_pyeong_10k(True, True) is None
        # 음수도(상·하한은 한 쌍이다)
        assert per_pyeong_10k(-2_000, 3.31) is None
        assert per_pyeong_10k(2_000, -3.31) is None

    def test_0원과_면적결측의_사유가_다르다(self) -> None:
        """★「원천이 안 줬다」와 「값은 왔는데 산정 불가」는 다른 사실이다.

        앞 판은 둘 다 `masked_by_source` 라, 조사자가 **원천을 의심하러** 가게 만들었다.
        """
        영원, 결측 = attach_per_pyeong([
            {"price_10k_won": 0, "area_m2": 3.31},
            {"price_10k_won": 2_000, "area_m2": None},
        ])
        assert 영원["price_per_pyeong_10k_absent"] == "insufficient_coverage"
        assert 결측["price_per_pyeong_10k_absent"] == "masked_by_source"
        assert 영원["price_per_pyeong_10k_absent"] != 결측["price_per_pyeong_10k_absent"]

    def test_비dict_원소를_조용히_버리지_않는다(self) -> None:
        """★행이 소리 없이 줄면 *"거래가 적었다"* 는 거짓이 된다."""
        rows = attach_per_pyeong([{"price_10k_won": 2_000, "area_m2": 3.31}, "쓰레기", None])
        assert len(rows) == 3, f"입력 3건인데 {len(rows)}건만 나왔다 — 조용한 소실"

    def test_문서_단가열이_우측정렬이다(self) -> None:
        """★HIGH-2 — 화면은 우측인데 **문서만 좌측**이었다. 쉼표 숫자 열이 좌측이면
        자릿수 비교가 불가능하고, 그게 이 열의 존재 이유다.
        ★목록형으로 단언하지 않는다 — 헤더 위치에서 **파생**시켜야 열이 또 늘 때 따라온다.
        """
        from apps.api.app.services.report.render import realtx_adapter as ad

        model = ad.build_report_model_from_realtx({"groups": [{
            "lawd_cd": "11680", "dong": "역삼동", "parcels": [],
            "summary": {"total": 1},
            "transactions": attach_per_pyeong([{"price_10k_won": 2_000, "area_m2": 3.31}]),
        }], "months": ["202608"]})
        blocks = [b for s in model.sections for b in s.blocks]
        tables = [b for b in blocks if getattr(b, "numeric_cols", None) is not None]
        assert tables, "표 블록을 못 찾았다(수집기 사망)"
        idx = ad._TX_HEADERS.index("만원/평")
        tx_tables = [b for b in tables if list(getattr(b, "headers", [])) == list(ad._TX_HEADERS)]
        assert tx_tables, "거래 표를 못 찾았다"
        for b in tx_tables:
            assert idx in b.numeric_cols, (
                f"단가 열({idx})이 numeric_cols={b.numeric_cols} 에 없다 — 문서에서 좌측 정렬된다"
            )
