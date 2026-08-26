"""실거래 **계약 상태** — 원천이 주는데 우리가 버리던 필드(해제·거래유형·등기).

★라이브 원문 실측(2026-08-26 · `RTMSDataSvcAptTradeDev` · 강남/용인수지/서울중구 × 3개월
**3,482건**):

    cdealType  공백 3,414 · **'O' 68건(1.95%)**      ← 계약 해제
    cdealDay   해제일(예: '26.07.02')
    dealingGbn 중개거래 3,381 · 직거래 101
    rgstDate   공백 2,430 · 있음 1,052(30.2%)         ← 소유권(등기) 신호
    buyerGbn   개인 3,475 · 법인 7                     ← 법인/개인

★**정상 건은 `cdealType=' '`(공백)** 이다 — 공백을 해제로 오판하면 전건이 해제가 된다.
★가격 영향(정직): 해제 평균이 정상 대비 **+11.5%**(고가 편향). 전체 평균 왜곡은 **+0.22%**
  로 작지만, **개별 표시가 거짓**이고 소표본(AVM·탁상감정 반경 표본)에서 증폭된다.

★설계 원칙은 형제(`share_dealing_type`, 2026-08-06)를 따른다 —
  **읽어서 보존만 한다(무날조). 제외·가중은 소비처 판단이다.**
"""

from __future__ import annotations

from apps.api.integrations.molit_client import MolitClient

# ★양성 대조군 — **실제 라이브 응답 형상**(합성 아님). 강남 삼성 아파트 해제 건.
_CANCELLED = {
    "aptNm": "삼성", "dealAmount": "230,000", "excluUseAr": "84.99",
    "dealYear": "2026", "dealMonth": "7", "dealDay": "21", "floor": "5",
    "umdNm": "삼성동", "jibun": "42", "buildYear": "1999",
    "estateAgentSggNm": "서울 강남구",
    "cdealType": "O", "cdealDay": "26.07.02",
    "dealingGbn": "중개거래", "rgstDate": " ", "buyerGbn": "개인", "slerGbn": "개인",
}
# ★음성 대조군 — 정상 건은 해제 필드가 **공백**이다(빈 문자열이 아니라 스페이스).
_NORMAL = {**_CANCELLED, "cdealType": " ", "cdealDay": " ",
           "dealingGbn": "직거래", "rgstDate": "26.07.30", "buyerGbn": "법인"}


def _parse(item: dict) -> dict:
    rows = MolitClient()._parse_trade_items(
        {"response": {"body": {"items": {"item": [item]}}}}, "apt")
    assert rows, "파서가 행을 하나도 내지 않았다 — 아래 단언이 공허해진다"
    return rows[0]


class Test해제:
    def test_해제건을_해제로_읽는다(self) -> None:
        r = _parse(_CANCELLED)
        assert r["is_cancelled"] is True, f"실제 해제 건을 정상으로 읽는다: {r}"
        assert r["cancel_date"] == "26.07.02", r["cancel_date"]

    def test_정상건의_공백을_해제로_오판하지_않는다(self) -> None:
        """★정상 건은 `' '`(스페이스)다 — strip 하지 않으면 truthy 라 전건이 해제가 된다."""
        r = _parse(_NORMAL)
        assert r["is_cancelled"] is False, f"공백을 해제로 읽었다: {r}"
        assert not r["cancel_date"], r["cancel_date"]

    def test_두_모집단이_실제로_갈린다(self) -> None:
        assert _parse(_CANCELLED)["is_cancelled"] != _parse(_NORMAL)["is_cancelled"]


class Test거래유형과소유권:
    def test_거래유형을_보존한다(self) -> None:
        assert _parse(_CANCELLED)["dealing_type"] == "중개거래"
        assert _parse(_NORMAL)["dealing_type"] == "직거래"

    def test_등기일자를_보존한다(self) -> None:
        """★3층(소유권 추적)의 재료 — 별도 등기 API 없이 **같은 응답**에 있다."""
        assert _parse(_NORMAL)["registered_date"] == "26.07.30"
        assert not _parse(_CANCELLED)["registered_date"], "공백이 값으로 새면 안 된다"

    def test_법인_개인을_보존한다(self) -> None:
        assert _parse(_NORMAL)["buyer_type"] == "법인"
        assert _parse(_CANCELLED)["buyer_type"] == "개인"

    def test_보존만_한다_행을_버리지_않는다(self) -> None:
        """★무날조·무삭제 — 해제 건도 **행은 남긴다**. 제외는 소비처 판단이다
        (형제 `share_dealing_type` 과 같은 원칙)."""
        assert _parse(_CANCELLED)["price_10k_won"] == 230000
        assert _parse(_CANCELLED)["area_m2"] == 84.99


class Test배선:
    """★파서만 잠그면 **소비처 0**이어도 초록이다 — 이 세션에서 두 번 겪었다."""

    def test_지도_서비스가_해제를_세고_노출한다(self) -> None:
        import sys
        from pathlib import Path as _P

        sys.path.insert(0, str(_P(__file__).resolve().parents[3] / "tests"))
        from _scan_guard import code_lines, read  # noqa: PLC0415

        svc = (_P(__file__).resolve().parents[1] / "app" / "services"
               / "land_intelligence" / "nearby_map_service.py")
        raw = read(svc, must_exist_reason="nearby_map 서비스가 사라졌다")

        # ★★이 락이 **깨진 파일을 통과시켰다**(2026-08-26 실증). 내가 `sum(...)` 표현식
        #   **안**에 키를 잘못 끼워 넣어 파일이 `SyntaxError` 였는데, 문자열 검사는
        #   `"cancelled_count"` 가 있으니 **초록**이었다(8 passed).
        #   → **문법을 먼저 태운다.** 소스 검사는 파싱되는 파일에 대해서만 의미가 있다.
        import ast  # noqa: PLC0415

        try:
            ast.parse(raw)
        except SyntaxError as e:  # pragma: no cover - 회귀 시에만 도달
            raise AssertionError(
                f"nearby_map_service 가 **파싱되지 않는다**(line {e.lineno}: {e.msg}) — "
                "문자열 검사만 하면 깨진 파일이 초록으로 통과한다"
            ) from e

        src = code_lines(raw)
        # 대조군 — 형제(지분)가 반드시 있어야 한다. 없으면 경로·패턴이 틀린 것이다.
        assert 'share_deal_count' in src, "대상 파일이 틀렸다(조회기 사망)"
        assert '"cancelled_count"' in src, "해제 건수를 그룹 응답에 노출하지 않는다"

    def test_그룹핑이_해제를_실제로_센다(self) -> None:
        """★**행동**으로 잠근다 — 소스 문자열 검사는 뚫렸다(변이 실증).

        계수 라인(`g["_cancelled"] += 1`)을 `pass` 로 바꿔도 문자열 락 8건이 **전부 통과**
        했다(`r.get("is_cancelled")` 라인은 그대로 남으니까). `_group_trade` 는 동기 순수
        메서드라 **직접 태울 수 있다.**
        """
        rows = [
            {**_CANCELLED, "prop_type": "apt", "price_10k_won": 230000, "area_m2": 84.99,
             "sigungu": "서울 강남구", "dong": "삼성동", "jibun": "42",
             "building_name": "삼성", "is_cancelled": True},
            {**_NORMAL, "prop_type": "apt", "price_10k_won": 200000, "area_m2": 84.99,
             "sigungu": "서울 강남구", "dong": "삼성동", "jibun": "42",
             "building_name": "삼성", "is_cancelled": False},
        ]
        from apps.api.app.services.land_intelligence.nearby_map_service import (  # noqa: PLC0415
            NearbyMapService,
        )

        out = NearbyMapService()._group_trade("apt_trade", "아파트 매매", rows, "서울 강남구")
        groups = out.get("groups") or []
        assert groups, f"그룹이 만들어지지 않았다 — 아래 단언이 공허해진다: {out}"
        total = sum(int(g.get("cancelled_count") or 0) for g in groups)
        assert total == 1, (
            f"해제 1건·정상 1건을 넣었는데 해제 계수가 {total} 이다 — 세지 않고 있다"
        )
        # ★음성 대조군 — 정상만 넣으면 0이어야 한다(항상 1을 반환하는 구현이 아님을 증명)
        only_normal = NearbyMapService()._group_trade(
            "apt_trade", "아파트 매매", [rows[1]], "서울 강남구")
        assert sum(int(g.get("cancelled_count") or 0)
                   for g in (only_normal.get("groups") or [])) == 0
