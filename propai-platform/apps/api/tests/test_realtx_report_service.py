"""실거래 신고내역 보고서 — 순수 함수·쿼터 접기·보류 계약을 잠근다.

★이 서비스의 존재 이유: `#837` 이 보존한 **계약상태 6필드**를 읽는 화면이 **하나도 없었다**
  (2026-08-26 실측 — `is_cancelled` 는 세기만 하고 나머지 5필드는 조립에서 버려진다).

★원천 한계(라이브 실측 2026-08-26 · MOLIT 원본 114행): **지번 100% 마스킹**(`"1*"`).
  따라서 이 보고서는 **법정동 단위**이고 그 사유를 응답에 싣는다.
"""

from __future__ import annotations

import ast
import asyncio
import inspect

import pytest

from app.services.land_intelligence import realtx_report_service as svc
from apps.api.app.utils.withheld import validate_withheld_pair


class Test순수함수:
    @pytest.mark.parametrize(
        ("pnu", "expect"),
        [
            # ★라이브 데이터로 검산한 값 — 저장된 `jibun` 필드와 일치함을 확인했다
            ("1159010200102100453", "210-453"),   # jibun="서울특별시 동작구 상도동 210-453"
            ("4711135022200010001", "산 1-1"),    # jibun="… 호미곶면 대보리 산 1-1"
            ("4146510500100560016", "56-16"),     # jibun="용인시 수지구 신봉동 56-16"
        ],
    )
    def test_PNU에서_지번을_파생한다(self, pnu: str, expect: str) -> None:
        assert svc.jibun_from_pnu(pnu) == expect

    @pytest.mark.parametrize("bad", ["", None, "123", "115901020010210045X", "1" * 20])
    def test_형식이_아니면_None(self, bad) -> None:
        assert svc.jibun_from_pnu(bad) is None
        assert svc.lawd_cd_from_pnu(bad) is None
        assert svc.bjdong_cd_from_pnu(bad) is None

    def test_부번_0은_본번만(self) -> None:
        assert svc.jibun_from_pnu("1159010200102100000") == "210"

    def test_본번_0은_지번_없음(self) -> None:
        """본번 0 은 지번이 성립하지 않는다 — 빈 문자열이 아니라 None."""
        assert svc.jibun_from_pnu("1159010200100000001") is None

    def test_월_범위는_오름차순이고_연도를_넘는다(self) -> None:
        assert svc.month_range("202601", 3) == ["202511", "202512", "202601"]
        assert svc.month_range("bad", 3) == []
        assert svc.month_range("202613", 3) == []   # 13월 거부


class Test쿼터접기:
    def test_같은_시군구_N필지가_월당_1회로_접힌다(self) -> None:
        """★쿼터 방어의 핵심 — 이것이 깨지면 일일 쿼터가 죽는다.

        ★라이브 실측(2026-08-26): 필지 **390** → 고유 시군구 **5**(78배 절감).
          필지마다 부르면 `months=6` 에서 2,340회다.
        """
        parcels = [
            {"pnu": f"11590102001021{i:05d}", "jibun": f"서울특별시 동작구 상도동 210-{i}"}
            for i in range(1, 51)
        ]
        calls: list[tuple[str, str]] = []

        class _C:
            async def get_transactions(self, lawd, ym, prop_type="land"):
                calls.append((lawd, ym))
                return []

        asyncio.run(svc.build_realtx_report(parcels, end_ym="202608", months=6, client=_C()))
        assert len(calls) == 6, f"필지 50개인데 {len(calls)}회 호출됐다 — 접기가 깨졌다"
        assert len({c[0] for c in calls}) == 1, "시군구가 하나여야 한다"

    def test_시군구가_늘면_그만큼만_는다(self) -> None:
        """대조군 — 접기가 *항상 1회* 를 반환하는 가짜가 아님을 증명한다."""
        parcels = [
            {"pnu": "1159010200102100453", "jibun": "서울특별시 동작구 상도동 210-453"},
            {"pnu": "4137011000104670001", "jibun": "경기도 오산시 내삼미동 467-1"},
        ]
        calls: list[tuple[str, str]] = []

        class _C:
            async def get_transactions(self, lawd, ym, prop_type="land"):
                calls.append((lawd, ym))
                return []

        asyncio.run(svc.build_realtx_report(parcels, end_ym="202608", months=2, client=_C()))
        assert len(calls) == 4, "시군구 2 × 월 2 = 4회여야 한다"


class Test신고상태집계:
    def test_정상건은_스페이스라_해제로_세지_않는다(self) -> None:
        """★★문서화된 함정 — 정상 건의 `cdealType` 은 `' '`(스페이스)다.

        `strip()` 없이 truthy 로 보면 **전건이 해제**가 된다.
        이 함수는 **자기 입력을 믿지 않고** 다시 `strip()` 한다.
        """
        txs = [{"cancel_type": " "}, {"cancel_type": ""}, {"cancel_type": "O"}]
        s = svc.summarize_contract_state(txs)
        assert s["cancelled"] == 1, f"스페이스를 해제로 셌다: {s}"
        assert s["cancelled_pct"] == pytest.approx(33.33, abs=0.01)

    def test_여섯_필드를_각각_센다(self) -> None:
        txs = [
            {"cancel_type": "O", "dealing_type": "직거래", "registered_date": "26.07.10",
             "buyer_type": "법인", "seller_type": "개인", "share_dealing_type": "지분"},
            {"cancel_type": " ", "dealing_type": "중개거래", "registered_date": "",
             "buyer_type": "개인", "seller_type": "법인", "share_dealing_type": ""},
        ]
        s = svc.summarize_contract_state(txs)
        assert (s["cancelled"], s["direct"], s["brokered"]) == (1, 1, 1)
        assert (s["registered"], s["corporate_buyer"], s["corporate_seller"]) == (1, 1, 1)
        assert s["share_deals"] == 1

    def test_빈_입력에서_0으로_나누지_않는다(self) -> None:
        s = svc.summarize_contract_state([])
        assert s["total"] == 0 and s["cancelled_pct"] == 0.0


class Test보류계약:
    def test_필지단위_매칭불가_사유가_실린다(self) -> None:
        """★이 보고서가 '필지별'이 아닌 이유를 **응답이 말해야** 한다."""
        parcels = [{"pnu": "1159010200102100453", "jibun": "서울특별시 동작구 상도동 210-453"}]

        class _C:
            async def get_transactions(self, lawd, ym, prop_type="land"):
                return [{"dong": "상도동", "deal_date": "2026년 7월 1일"}]

        r = asyncio.run(svc.build_realtx_report(parcels, end_ym="202608", months=1, client=_C()))
        g = r["groups"][0]
        assert g["parcel_level_match"] is None
        assert g["parcel_level_match_absent"] == "masked_by_source"
        assert "마스킹" in g["parcel_level_match_basis"]
        assert validate_withheld_pair(g, "parcel_level_match") == []

    def test_PNU_없는_필지는_사유와_함께_남는다(self) -> None:
        """버리지 않는다 — 조회 불가를 **말한다**."""
        r = asyncio.run(svc.build_realtx_report(
            [{"pnu": None, "jibun": "주소만"}], end_ym="202608", months=1, client=_Empty()))
        u = r["unlocated_parcels"]
        assert len(u) == 1
        assert u[0]["transactions"] is None
        assert u[0]["transactions_absent"] == "source_unavailable"
        assert validate_withheld_pair(u[0], "transactions") == []

    def test_조회_실패를_거래_0건으로_기록하지_않는다(self) -> None:
        """★★가장 중요한 락 — 실패를 0건으로 적으면 *'거래가 없었다'* 는 **거짓 사실**이 생긴다."""
        parcels = [{"pnu": "1159010200102100453", "jibun": "서울특별시 동작구 상도동 210-453"}]

        class _Boom:
            async def get_transactions(self, lawd, ym, prop_type="land"):
                raise RuntimeError("HTTP 429 quota")

        r = asyncio.run(svc.build_realtx_report(parcels, end_ym="202608", months=2, client=_Boom()))
        assert len(r["fetch_errors"]) == 2, "실패가 기록되지 않았다"
        assert r["fetch_errors"][0]["error"] == "RuntimeError"
        # 대조군 — 성공했을 때는 fetch_errors 가 비어야 한다(이 단언이 공허하지 않음을 증명)
        ok = asyncio.run(svc.build_realtx_report(parcels, end_ym="202608", months=2, client=_Empty()))
        assert ok["fetch_errors"] == []


class _Empty:
    async def get_transactions(self, lawd, ym, prop_type="land"):
        return []


class Test배선:
    def test_조회는_접힌_시군구_루프_안에서만_일어난다(self) -> None:
        """★배선 — `build_realtx_report` **함수 안에서** `get_transactions` 를 부르는지 본다.

        ★모듈 전체 스코프로 보면 *"어딘가에서 부르면"* 초록이라, 필지 루프로 되돌리는
          회귀를 못 잡는다(오늘 같은 형태로 뚫린 전례가 있다).
        대조군도 **문법 구조**에 결속한다 — 함수가 사라지면 `StopIteration` 으로 죽는다.
        """
        tree = ast.parse(inspect.getsource(svc))
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
            and n.name == "build_realtx_report"
        )
        assert any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "get_transactions"
            for n in ast.walk(fn)
        ), "build_realtx_report 가 실거래를 조회하지 않는다"
        # 접기 함수를 실제로 쓰는가 — 안 쓰면 쿼터 방어가 사라진다
        called = {
            n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "fold_parcels_by_lawd" in called, "시군구 접기를 쓰지 않는다 — 쿼터가 죽는다"


class Test엔드포인트계약:
    def test_라우트가_등록돼_있다(self) -> None:
        """★배선 — 서비스가 있어도 라우트가 없으면 사용자에게 닿지 않는다."""
        import routers.market_report as m

        paths = {r.path for r in m.router.routes}
        assert "/api/v1/market/realtx-report" in paths, f"라우트 미등록: {sorted(paths)}"
        # 대조군 — 조회기가 살아 있는가(형제 라우트가 보여야 한다)
        assert "/api/v1/market/quick-survey" in paths, "대조군 실패 — 라우터 조회가 죽었다"

    def test_과금_게이트를_걸지_않는다(self) -> None:
        """LLM 미사용 조회다 — 형제(`/quick-survey`·`/trend`)와 같은 취급.

        ★과금 게이트를 잘못 걸면 **무료 조회에 코인이 빠진다.**
        """
        import routers.market_report as m

        route = next(r for r in m.router.routes if r.path == "/api/v1/market/realtx-report")
        dep_names = [
            getattr(d.call, "__name__", "") for d in route.dependant.dependencies
        ]
        assert "enforce_llm_quota" not in dep_names, f"무료 조회에 과금 게이트가 걸렸다: {dep_names}"
        # 대조군 — 실제로 과금 게이트가 걸린 형제가 있다(이 단언이 공허하지 않음을 증명)
        paid = next(r for r in m.router.routes if r.path == "/api/v1/market/report")
        paid_names = [getattr(d.call, "__name__", "") for d in paid.dependant.dependencies]
        assert "enforce_llm_quota" in paid_names, "대조군 실패 — 유료 형제에 게이트가 없다"

    def test_인증을_요구한다(self) -> None:
        import routers.market_report as m

        route = next(r for r in m.router.routes if r.path == "/api/v1/market/realtx-report")
        src = str(route.dependant.dependencies) + str(route.endpoint.__annotations__)
        assert "CurrentUser" in src or any(
            getattr(d.call, "__name__", "") == "get_current_user"
            for d in route.dependant.dependencies
        ), "인증 의존성이 없다"
