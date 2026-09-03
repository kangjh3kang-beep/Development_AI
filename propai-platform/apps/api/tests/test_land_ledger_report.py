"""토지대장(공부) 보고서 확장 — **미상을 「해당 없음」에 합치지 않는다**.

## 이 락이 막는 것

1. **두 파이프가 각각 원천을 깎는 것** — batch·excel 이 서로 다른 필드 집합을 갖게 되는 것
2. **미상이 「해당 없음」의 옷을 입는 것** — 도로접면 미상을 접도로 세면 맹지 비율이 과소표시된다
3. **배치 재실행이 분모를 부풀리는 것**(2026-09-03 라이브 실측: total 2 → 재제출 4)
4. **같은 판정을 다시 짜는 것** — 맹지 판정기는 이미 3축으로 존재한다
"""

from __future__ import annotations

import pytest

from apps.api.app.foundation.parcel.batch.job_runner import resolve_pnu_status
from apps.api.app.services.report.render.land_adapter import build_report_model_from_land
from apps.api.app.utils.land_characteristics import (
    is_shared_parcel,
    project_land_characteristics,
)

# 라이브 실측 원천(2026-09-03 · VWorld 토지특성 11필드)
_CHARS = {
    "pnu": "4137011000104670001", "year": 2025, "area_sqm": 53.0,
    "land_category": "답", "zone_type": "제2종일반주거지역", "zone_type_2": "",
    "land_use_situation": "답", "road_side": "맹지", "terrain_height": "평지",
    "terrain_form": "부정형", "official_price_per_sqm": 414600,
}


def _kv(model, title="2. 토지정보 집계") -> dict[str, str]:
    """§2 KV 표를 dict 로."""
    for sec in model.sections:
        if sec.title == title:
            for b in sec.blocks:
                rows = getattr(b, "rows", None)
                if rows:
                    return {k: v for k, v in rows}
    raise AssertionError(f"섹션을 못 찾음: {title}")


def _model(parcels):
    return build_report_model_from_land({"project_name": "T", "parcels": parcels})


class Test투영은한곳이고원천을버리지않는다:
    def test_원천_키가_전부_옮겨진다_파생형(self):
        out = project_land_characteristics(dict(_CHARS))
        expected = {k for k in _CHARS if k != "pnu"}  # pnu 는 소비 레코드가 이미 갖는다
        assert set(out) == expected, f"버려진 키: {expected - set(out)}"

    def test_배치_파이프가_그_투영을_쓴다_배선(self):
        """★함수를 만든 것과 배선한 것은 다르다 — 실제 산출물을 본다."""
        r = resolve_pnu_status("4137011000104670001", None, dict(_CHARS))
        assert r.record_ref["road_side"] == "맹지"          # ★종전엔 버려지던 축
        assert r.record_ref["official_price_per_sqm"] == 414600
        assert r.record_ref["source"] == "land_characteristics"  # 기존 소비처 회귀

    def test_빈_원천은_지어내지_않는다(self):
        assert project_land_characteristics(None) == {}
        assert project_land_characteristics({}) == {}


class Test미상을해당없음에합치지않는다:
    """★이 저장소가 반복해서 데인 형태 — 「모름」이 유효값의 옷을 입으면 관측이 된다."""

    def test_맹지_미상이_접도로_세어지지_않는다(self):
        # 맹지 1 · 접도 1 · **도로접면 미상 2**
        kv = _kv(_model([
            {"jibun": "A", "area_sqm": 10, "road_side": "맹지"},
            {"jibun": "B", "area_sqm": 10, "road_side": "광대한면"},
            {"jibun": "C", "area_sqm": 10},
            {"jibun": "D", "area_sqm": 10},
        ]))
        s = kv["맹지(도로 미접)"]
        assert "미상 2필지" in s, f"미상 버킷이 사라졌다: {s}"
        assert "1필지" in s and "접도 1필지" in s
        # ★미상을 분모에 넣으면 25.0% 가 된다 — 제외한 50.0% 여야 한다.
        assert "50.0%" in s, f"미상이 분모에 섞였다: {s}"

    def test_대조군_미상이_없으면_미상_문구도_없다(self):
        """★「항상 미상을 붙이는」 구현과 구별한다."""
        s = _kv(_model([
            {"jibun": "A", "area_sqm": 10, "road_side": "맹지"},
            {"jibun": "B", "area_sqm": 10, "road_side": "광대한면"},
        ]))["맹지(도로 미접)"]
        assert "미상" not in s
        assert "50.0%" in s

    def test_지목_미상이_분포에서_사라지지_않는다(self):
        s = _kv(_model([
            {"jibun": "A", "area_sqm": 10, "jimok": "답"},
            {"jibun": "B", "area_sqm": 10},
        ]))["지목 분포"]
        assert "답 1필지" in s and "미상 1필지" in s

    def test_면적_통계는_산정_분모를_함께_낸다(self):
        s = _kv(_model([
            {"jibun": "A", "area_sqm": 100},
            {"jibun": "B", "area_sqm": None},
            {"jibun": "C", "area_sqm": 0},
        ]))["필지 면적 분포"]
        assert "산정 1/3필지" in s, f"분모가 없다: {s}"

    def test_면적이_전부_미상이면_숫자를_지어내지_않는다(self):
        s = _kv(_model([{"jibun": "A", "area_sqm": None}]))["필지 면적 분포"]
        assert "평균" not in s, f"미상인데 평균을 만들었다: {s}"


class Test맹지판정을다시짜지않는다:
    """★같은 이름의 두 판정이 다른 답을 내면 안 된다 — 3축 SSOT 를 재사용한다."""

    def test_road_contact_False_도_맹지로_센다_문자열_1축이_아님(self):
        # `road_side` 문자열에는 '맹지'가 없지만 `road_contact is False` 다.
        # ★1축 문자열 검사로 다시 짰다면 이 케이스를 **놓친다.**
        s = _kv(_model([
            {"jibun": "A", "area_sqm": 10, "road_side": "광대한면", "road_contact": False},
            {"jibun": "B", "area_sqm": 10, "road_side": "광대한면", "road_contact": True},
        ]))["맹지(도로 미접)"]
        assert "1필지" in s and "접도 1필지" in s, f"3축 판정기를 안 탔다: {s}"


class Test기존집계는회귀하지않는다:
    def test_총면적_용도지역_공시가액이_그대로다(self):
        kv = _kv(_model([
            {"jibun": "A", "area_sqm": 100, "zone_type": "제2종일반주거지역", "official_price_per_sqm": 1000},
            {"jibun": "B", "area_sqm": 200, "zone_type": "일반상업지역"},
        ]))
        assert "제2종일반주거지역 1필지" in kv["용도지역 분포"]
        assert "1/2필지" in kv["개별공시지가 기준 추정 토지가액"], "기존 분모 표기가 사라졌다"


class Test배치재실행이분모를부풀리지않는다:
    """★라이브 실측(2026-09-03): 같은 입력 재제출 → 같은 job_id 인데 total 2 → **4**."""

    @pytest.mark.asyncio
    async def test_같은_잡을_두_번_돌려도_items_가_누적되지_않는다(self):
        from apps.api.app.foundation.parcel.batch.batch_service import BatchService
        from apps.api.app.foundation.parcel.batch.job_store import InMemoryJobStore
        from apps.api.app.foundation.parcel.contracts.batch import BatchInput

        class _FakeVWorld:
            async def get_parcel_by_pnu(self, pnu):  # noqa: ANN001
                return None

            async def get_land_characteristics(self, pnu, year=None):  # noqa: ANN001
                return {**_CHARS, "pnu": pnu}

            async def merge_parcels_gis_union(self, pnus):  # noqa: ANN001
                return None  # ★스텁도 계약이다 — 집계기가 이것을 부른다

        store = InMemoryJobStore()
        svc = BatchService(store=store, vworld=_FakeVWorld())
        job = await svc.submit(BatchInput(pnu_list=["4137011000104670001", "4137011000104930031"]))

        first = await svc.run(job.id)
        assert len(first.items) == 2, "1회차부터 어긋나면 이 락은 아무것도 못 가른다"

        second = await svc.run(job.id)
        assert len(second.items) == 2, f"재실행이 items 를 누적했다: {len(second.items)}"
        assert second.job.counts.total == 2, f"분모가 부풀었다: {second.job.counts.total}"


# ────────────────────────────────────────────────────────────────────────────
# ★토지임야목록(NED `ladfrlList`) — 응답 **래퍼 키가 미지**라 구조로 찾는다.
#   그 파서가 곧 계약이므로 여기서 잠근다.
#   ★내가 "토지대장 원천 0건"이라 적은 것은 **저장소를 뒤진 결과**였지 원천이 없다는 뜻이 아니었다.
#     사용자가 API 카탈로그에서 찾아 줬다 — 「0건」은 조회 결과이지 결론이 아니다.
# ────────────────────────────────────────────────────────────────────────────
class Test토지임야목록응답형태를지어내지않는다:
    @staticmethod
    def _f():
        from apps.api.app.services.external_api.vworld_service import _find_pnu_rows

        return _find_pnu_rows

    # 공식 문서 필드(사용자 제공 화면 실측 2026-09-03)
    _ROW = {
        "pnu": "1111010100100890025", "ldCode": "1111010100",
        "ldCodeNm": "서울특별시 종로구 청운동", "mnnmSlno": "126-25",
        "regstrSeCode": "1", "regstrSeCodeNm": "토지대장",
        "lndcgrCode": "08", "lndcgrCodeNm": "대", "lndpclAr": "376.9",
        "posesnSeCode": "06", "posesnSeCodeNm": "법인", "cnrsPsnCo": "2",
        "ladFrtlSc": "06", "ladFrtlScNm": "1:600", "lastUpdtDt": "2015-11-12",
    }

    @pytest.mark.parametrize("wrapper", [
        {"ladfrlVOList": {"ladfrlVO": [_ROW]}},          # NED 관례 A
        {"ladfrls": {"field": [_ROW]}},                  # NED 관례 B
        {"response": {"result": {"items": [_ROW]}}},     # 관례 C
        [_ROW],                                          # 최상위 리스트
    ])
    def test_래퍼_이름이_무엇이든_행을_찾는다(self, wrapper):
        """★래퍼 키를 **지어내지 않기** 위한 것이다 — 이름이 달라도 구조로 찾는다."""
        rows = self._f()(wrapper)
        assert rows is not None and len(rows) == 1
        assert rows[0]["posesnSeCodeNm"] == "법인"
        assert rows[0]["cnrsPsnCo"] == "2"          # ★공유인수
        assert rows[0]["regstrSeCodeNm"] == "토지대장"
        assert rows[0]["lastUpdtDt"] == "2015-11-12"  # ★시점 문서

    def test_형태_미인식은_None_이지_빈리스트가_아니다(self):
        """★`None`(조회 못 함)과 `[]`(확인 결과 0건)은 **다른 사실**이다.

        뭉개면 "조회 실패"가 "규제 없음"처럼 읽힌다 — 이 파일이 이미 겪은 사고다.
        """
        assert self._f()({"error": {"code": "INVALID_KEY"}}) is None
        assert self._f()({"response": {"status": "ERROR"}}) is None
        assert self._f()("문자열") is None

    def test_대조군_pnu_없는_리스트는_안_집는다(self):
        """★아무 리스트나 집으면 위양성이다 — `pnu` 를 가진 것만."""
        assert self._f()({"rows": [{"a": 1}, {"b": 2}]}) is None


class Test대장필드가배치산출물에실린다:
    """★소비처 0인 메서드를 만들지 않는다 — **배선**을 잠근다.

    나는 오늘 `is_valid_pnu` 소비처 0 을 결함이라 부르며 PR 을 냈고(#944),
    `normalizePnu` 미배선을 고쳤는데(#941), **그 직후 소비처 0인 메서드를 추가했다.**
    이 락이 그것을 막는다.
    """

    _LEDGER = [{
        "pnu": "4137011000104670001", "regstrSeCodeNm": "토지대장",
        "posesnSeCodeNm": "법인", "cnrsPsnCo": "2", "lastUpdtDt": "2015-11-12",
        "ldCodeNm": "서울특별시 종로구 청운동",  # ★선별 밖 필드 — 실리면 안 된다
    }]
    _CHARS2 = {"pnu": "x", "area_sqm": 53.0, "land_category": "답",
               "zone_type": "제2종일반주거지역", "road_side": "맹지",
               "official_price_per_sqm": 414600}

    def test_판단에_쓰는_네_필드가_실린다(self):
        r = resolve_pnu_status("4137011000104670001", None, dict(self._CHARS2), self._LEDGER)
        assert r.record_ref["posesnSeCodeNm"] == "법인"
        assert r.record_ref["cnrsPsnCo"] == "2"          # ★공유인수
        assert r.record_ref["regstrSeCodeNm"] == "토지대장"
        assert r.record_ref["lastUpdtDt"] == "2015-11-12"

    def test_선별_밖_필드는_안_싣는다_대조군(self):
        """★「전부 싣는」 구현과 구별한다 — 이건 파생이 아니라 **선별**이다."""
        r = resolve_pnu_status("4137011000104670001", None, dict(self._CHARS2), self._LEDGER)
        assert "ldCodeNm" not in r.record_ref

    def test_대장이_없어도_토지특성은_그대로다_회귀(self):
        """★대장 조회가 실패해도 배치 전체가 죽지 않는다."""
        r = resolve_pnu_status("4137011000104670001", None, dict(self._CHARS2), None)
        assert r.status.value == "confirmed"
        assert r.record_ref["road_side"] == "맹지"
        assert "posesnSeCodeNm" not in r.record_ref  # 없는 것을 지어내지 않는다

    @pytest.mark.asyncio
    async def test_배치_실행이_대장_API_를_실제로_부른다_배선(self):
        """★함수를 만든 것과 **부르는 것**은 다르다 — 호출 자체를 단언한다."""
        from apps.api.app.foundation.parcel.batch.job_runner import JobRunner

        called: list[str] = []

        class _VW:
            async def get_land_characteristics(self, pnu, year=None):  # noqa: ANN001
                return {"pnu": pnu, "area_sqm": 53.0, "land_category": "답"}

            async def get_land_ledger_list(self, pnu):  # noqa: ANN001
                called.append(pnu)
                return Test대장필드가배치산출물에실린다._LEDGER

            async def get_parcel_by_pnu(self, pnu):  # noqa: ANN001
                return None

        r = await JobRunner(vworld=_VW()).resolve_one("4137011000104670001")
        assert called == ["4137011000104670001"], "대장 API 가 호출되지 않았다(소비처 0)"
        assert r.record_ref["cnrsPsnCo"] == "2"


# ────────────────────────────────────────────────────────────────────────────
# ★공유자 연명부(NED `cnrdlnList`) — 「수」와 「구성」은 다른 사실이다.
#   `ladfrlList.cnrsPsnCo` 는 *"5명"* 까지만 말한다. 그 5명이 **국유를 포함하는지**는
#   말하지 않는데, 그게 포함되면 **협의매수가 아니라 공유재산법 절차**다(다른 법이다).
# ────────────────────────────────────────────────────────────────────────────
class Test공유자구성:
    _CH = {"pnu": "x", "area_sqm": 53.0, "land_category": "답"}

    def test_수가_같아도_구성이_다르면_다른_값이_나온다(self):
        """★두 모집단 — `cnrsPsnCo` 만 보면 둘이 같아 보인다."""
        five_private = [{"posesnSeCodeNm": "개인"} for _ in range(5)]
        with_public = [{"posesnSeCodeNm": "개인"} for _ in range(4)] + [{"posesnSeCodeNm": "국유"}]
        a = resolve_pnu_status("4137011000104670001", None, dict(self._CH), None, five_private)
        b = resolve_pnu_status("4137011000104670001", None, dict(self._CH), None, with_public)
        assert a.record_ref["co_owner_count"] == b.record_ref["co_owner_count"] == 5
        # ★그런데 절차가 갈린다.
        assert a.record_ref["has_public_share"] is False
        assert b.record_ref["has_public_share"] is True

    def test_구성이_소유구분별로_집계된다(self):
        co = [{"posesnSeCodeNm": "법인"}, {"posesnSeCodeNm": "법인"}, {"posesnSeCodeNm": "개인"}]
        r = resolve_pnu_status("4137011000104670001", None, dict(self._CH), None, co)
        assert r.record_ref["co_owner_kinds"] == {"법인": 2, "개인": 1}

    def test_소유구분_미상은_미상으로_센다_0으로_뭉개지_않는다(self):
        r = resolve_pnu_status("4137011000104670001", None, dict(self._CH), None,
                               [{"posesnSeCodeNm": ""}, {"posesnSeCodeNm": "개인"}])
        assert r.record_ref["co_owner_kinds"] == {"미상": 1, "개인": 1}

    def test_조회못함과_공유아님을_뭉개지_않는다(self):
        """★`None`(확인 못 함) → 필드 없음 · `[]`(확인 결과 0건) → count 0."""
        none_r = resolve_pnu_status("4137011000104670001", None, dict(self._CH), None, None)
        empty_r = resolve_pnu_status("4137011000104670001", None, dict(self._CH), None, [])
        assert "co_owner_count" not in none_r.record_ref   # 확인 못 함 = 지어내지 않는다
        assert empty_r.record_ref["co_owner_count"] == 0    # 확인 결과 0건
        assert empty_r.record_ref["has_public_share"] is False

    @pytest.mark.parametrize("cnt,expect", [("5", True), ("2", True), ("1", False), ("0", False),
                                            ("", False), (None, False), ("abc", False)])
    def test_공유판정_경계(self, cnt, expect):
        assert is_shared_parcel([{"cnrsPsnCo": cnt}]) is expect

    def test_대장이_없으면_공유판정은_False(self):
        assert is_shared_parcel(None) is False
        assert is_shared_parcel([]) is False


class Test조건부호출:
    """★단독소유 필지에 세 번째 외부 호출을 넣지 않는다 — 대부분이 낭비다."""

    @pytest.mark.asyncio
    async def test_공유가_아니면_연명부를_부르지_않는다(self):
        from apps.api.app.foundation.parcel.batch.job_runner import JobRunner

        calls: list[str] = []

        class _VW:
            async def get_land_characteristics(self, pnu, year=None):  # noqa: ANN001
                return {"pnu": pnu, "area_sqm": 53.0, "land_category": "답"}

            async def get_land_ledger_list(self, pnu):  # noqa: ANN001
                return [{"cnrsPsnCo": "1", "posesnSeCodeNm": "개인"}]  # ★단독

            async def get_co_owner_list(self, pnu):  # noqa: ANN001
                calls.append(pnu)
                return []

            async def get_parcel_by_pnu(self, pnu):  # noqa: ANN001
                return None

        await JobRunner(vworld=_VW()).resolve_one("4137011000104670001")
        assert calls == [], f"단독소유인데 연명부를 불렀다: {calls}"

    @pytest.mark.asyncio
    async def test_대조군_공유면_부른다(self):
        """★위 테스트만 두면 «절대 안 부르는» 구현도 만점이다."""
        from apps.api.app.foundation.parcel.batch.job_runner import JobRunner

        calls: list[str] = []

        class _VW:
            async def get_land_characteristics(self, pnu, year=None):  # noqa: ANN001
                return {"pnu": pnu, "area_sqm": 53.0, "land_category": "답"}

            async def get_land_ledger_list(self, pnu):  # noqa: ANN001
                return [{"cnrsPsnCo": "3", "posesnSeCodeNm": "개인"}]  # ★공유

            async def get_co_owner_list(self, pnu):  # noqa: ANN001
                calls.append(pnu)
                return [{"posesnSeCodeNm": "개인"}, {"posesnSeCodeNm": "국유"}]

            async def get_parcel_by_pnu(self, pnu):  # noqa: ANN001
                return None

        r = await JobRunner(vworld=_VW()).resolve_one("4137011000104670001")
        assert calls == ["4137011000104670001"]
        assert r.record_ref["has_public_share"] is True


class Test공유가보고서표면에닿는다:
    """★구현했는데 화면에 없으면 없는 것과 같다 — 표면을 잠근다."""

    def test_국공유_지분이_따로_표기된다(self):
        s = _kv(_model([
            {"jibun": "A", "area_sqm": 10, "co_owner_count": 5, "has_public_share": True},
            {"jibun": "B", "area_sqm": 10, "co_owner_count": 3, "has_public_share": False},
            {"jibun": "C", "area_sqm": 10, "co_owner_count": 1},
        ]))["공유 필지"]
        assert "공유 2필지" in s
        assert "국·공유 지분 포함 1필지" in s, f"절차가 다른 것이 한 칸에 묻혔다: {s}"

    def test_대조군_국공유가_없으면_그_문구도_없다(self):
        s = _kv(_model([{"jibun": "A", "area_sqm": 10, "co_owner_count": 3, "has_public_share": False}]))["공유 필지"]
        assert "공유 1필지" in s and "국·공유" not in s

    def test_미확인은_공유없음으로_뭉개지_않는다(self):
        s = _kv(_model([{"jibun": "A", "area_sqm": 10}]))["공유 필지"]
        assert "미확인 1필지" in s, f"조회 못 한 것이 「공유 없음」으로 읽힌다: {s}"

    def test_전부_확인되고_공유가_없으면_공유없음(self):
        s = _kv(_model([{"jibun": "A", "area_sqm": 10, "co_owner_count": 1}]))["공유 필지"]
        assert s == "공유 없음"


# ────────────────────────────────────────────────────────────────────────────
# ★★배선 락 — **두 파이프**가 대장·연명부를 받아야 한다.
#
#   보고서(`land-report`)는 **excel 파이프**(`enrich_parcel_list`)로 데이터를 받는데,
#   나는 처음에 대장·연명부를 **batch 파이프에만** 배선했다. 그러면 보고서의
#   `공유 필지` 행이 **영원히 「미확인」** 이 된다 — "구현했는데 화면에 안 닿는다".
#   ★오늘 그 결함을 두 번 잡아 놓고 **내가 만들었다.**
# ────────────────────────────────────────────────────────────────────────────
class Test두파이프가같은것을받는다:
    _CH = {"pnu": "x", "area_sqm": 53.0, "land_category": "답", "zone_type": "제2종일반주거지역"}
    _LG = [{"cnrsPsnCo": "3", "posesnSeCodeNm": "개인", "regstrSeCodeNm": "토지대장",
            "lastUpdtDt": "2015-11-12"}]
    _CO = [{"posesnSeCodeNm": "개인"}, {"posesnSeCodeNm": "개인"}, {"posesnSeCodeNm": "국유"}]

    class _VW:
        def __init__(self, calls: list[str]) -> None:
            self.calls = calls

        async def get_land_characteristics(self, pnu, year=None):  # noqa: ANN001
            return dict(Test두파이프가같은것을받는다._CH, pnu=pnu)

        async def get_land_ledger_list(self, pnu):  # noqa: ANN001
            self.calls.append("ledger")
            return Test두파이프가같은것을받는다._LG

        async def get_co_owner_list(self, pnu):  # noqa: ANN001
            self.calls.append("co")
            return Test두파이프가같은것을받는다._CO

        async def get_parcel_by_pnu(self, pnu):  # noqa: ANN001
            return None

    @pytest.mark.asyncio
    async def test_batch_파이프가_받는다(self):
        from apps.api.app.foundation.parcel.batch.job_runner import JobRunner

        calls: list[str] = []
        r = await JobRunner(vworld=self._VW(calls)).resolve_one("4137011000104670001")
        assert calls == ["ledger", "co"]
        assert r.record_ref["has_public_share"] is True
        assert r.record_ref["regstrSeCodeNm"] == "토지대장"

    @pytest.mark.asyncio
    async def test_excel_파이프도_받는다_보고서가_이_경로다(self, monkeypatch):
        """★`land-report` 는 이 파이프를 탄다 — 여기가 비면 보고서 행이 영원히 「미확인」이다."""
        # ★`_enrich_fill` 은 `VWorldService()` 를 **내부에서 생성**한다(주입 불가).
        #   그래서 클래스 자체를 갈아 끼운다 — 그 구조 때문에 이 파이프가 여태 안 잠겼다.
        import app.services.external_api.vworld_service as vs
        from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

        calls: list[str] = []
        vw = self._VW(calls)
        monkeypatch.setattr(vs, "VWorldService", lambda *a, **k: vw)
        parcels = [{"pnu": "4137011000104670001", "address": "경기도 오산시 내삼미동",
                    "area_sqm": None, "zone_type": None, "official_price_per_sqm": None}]
        await ParcelExcelService()._enrich_fill(parcels)

        assert calls == ["ledger", "co"], f"excel 파이프가 대장/연명부를 안 불렀다: {calls}"
        assert parcels[0]["has_public_share"] is True
        assert parcels[0]["co_owner_kinds"] == {"개인": 2, "국유": 1}
        assert parcels[0]["regstrSeCodeNm"] == "토지대장"

    @pytest.mark.asyncio
    async def test_그_값이_보고서_표면까지_닿는다(self, monkeypatch):
        """★파이프가 채운 필드를 **보고서가 실제로 읽는가** — 끝에서 끝까지."""
        import app.services.external_api.vworld_service as vs
        from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

        vw = self._VW([])
        monkeypatch.setattr(vs, "VWorldService", lambda *a, **k: vw)
        parcels = [{"pnu": "4137011000104670001", "address": "경기도 오산시 내삼미동",
                    "jibun": "467-1", "area_sqm": None, "zone_type": None,
                    "official_price_per_sqm": None}]
        await ParcelExcelService()._enrich_fill(parcels)

        s = _kv(_model(parcels))["공유 필지"]
        assert "공유 1필지" in s
        assert "국·공유 지분 포함 1필지" in s, f"파이프는 채웠는데 표면에 안 닿는다: {s}"


class Test실패는서로격리된다:
    """★대장 호출이 실패해도 **토지특성 보강은 살아야** 한다(부분성 1급).

    내 초안은 둘을 한 `try` 로 묶어 **대장 실패가 토지특성까지 버렸다** —
    면적·용도지역 보강이 통째로 죽어 기존 회귀 **6건**으로 드러났다.
    """

    @pytest.mark.asyncio
    async def test_대장이_터져도_토지특성은_채워진다(self, monkeypatch):
        import app.services.external_api.vworld_service as vs
        from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

        class _VW:
            async def get_land_characteristics(self, pnu, year=None):  # noqa: ANN001
                return {"pnu": pnu, "area_sqm": 53.0, "land_category": "답",
                        "zone_type": "제2종일반주거지역", "official_price_per_sqm": 414600}

            async def get_land_ledger_list(self, pnu):  # noqa: ANN001
                raise RuntimeError("대장 API 장애")  # ★한쪽만 터진다

            async def get_co_owner_list(self, pnu):  # noqa: ANN001
                return []

        monkeypatch.setattr(vs, "VWorldService", lambda *a, **k: _VW())
        parcels = [{"pnu": "4137011000104670001", "address": "경기도 오산시 내삼미동",
                    "area_sqm": None, "zone_type": None, "official_price_per_sqm": None}]
        await ParcelExcelService()._enrich_fill(parcels)

        # ★토지특성은 살아 있어야 한다 — 이게 회귀 6건의 본체였다.
        assert parcels[0]["area_sqm"] == 53.0
        assert parcels[0]["zone_type"] == "제2종일반주거지역"
        # ★대장은 못 받았으므로 **지어내지 않는다**.
        assert "regstrSeCodeNm" not in parcels[0]

    @pytest.mark.asyncio
    async def test_대장_메서드가_없는_구_스텁에서도_죽지_않는다(self, monkeypatch):
        """★주입 객체가 옛 계약이어도 배치·엑셀이 통째로 죽지 않는다."""
        import app.services.external_api.vworld_service as vs
        from apps.api.app.services.land_intelligence.parcel_excel_service import ParcelExcelService

        class _Old:
            async def get_land_characteristics(self, pnu, year=None):  # noqa: ANN001
                return {"pnu": pnu, "area_sqm": 77.0, "land_category": "전"}

        monkeypatch.setattr(vs, "VWorldService", lambda *a, **k: _Old())
        parcels = [{"pnu": "4137011000104670001", "address": "x",
                    "area_sqm": None, "zone_type": None, "official_price_per_sqm": None}]
        await ParcelExcelService()._enrich_fill(parcels)
        assert parcels[0]["area_sqm"] == 77.0
