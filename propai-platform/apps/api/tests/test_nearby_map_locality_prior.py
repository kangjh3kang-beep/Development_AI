"""사전컷 **지역 프라이어(읍·면 2단)** 계약.

★왜: `lawd_cd` 가 시군구라 MOLIT 은 시군구 전체 거래를 준다. 사전컷 2순위가 `-거래건수`라
   10~20km 밖 신도시 대단지가 지오코딩 예산을 쓸어가고 인근 소규모 단지가 잘렸다.
   라이브 실측(2026-09-05 · 남양주 마석): 1km 내 실재 아파트 **25곳** 중 화면에 **4곳**
   (= 대상 리 일치분). 손실의 **84% 가 「리 사이」** 였고 그 25곳의 리가 **전부 같은 읍**이었다.

★이 파일이 잠그는 것은 「함수가 불렸다」가 아니라 **「누가 살아남았는가」**다.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.services.land_intelligence import nearby_map_service as nm
from app.services.land_intelligence.nearby_map_service import (
    _eupmyeon_from_address,
    _eupmyeon_head,
    _locality_rank,
    select_precut_survivors,
)


def _g(dong: str, count: int, name: str) -> dict:
    return {"dong": dong, "count": count, "name": name}


# 다산·별내는 남양주 신도시(10~20km 밖·거래 많음), 창현·마석우리는 인근(거래 적음)
FIXTURE = [
    _g("다산동", 99, "다산대단지"),
    _g("별내동", 80, "별내대단지"),
    _g("화도읍 창현리", 5, "창현주공"),
    _g("화도읍 마석우리", 3, "마석소형"),
]


def test_두_모집단_켜면_인근이_살고_끄면_잘린다():
    on = [x["name"] for x in select_precut_survivors(FIXTURE, 3, "마석우리", "화도읍")]
    off = [x["name"] for x in select_precut_survivors(FIXTURE, 3, "마석우리", "")]
    # 켜짐엔 같은 읍(창현주공)이 살아남고, 꺼짐엔 잘린다 — 이 대비가 배선을 잠근다.
    assert "창현주공" in on
    assert "창현주공" not in off
    assert on != off
    # 대상 리는 **양쪽 모두** 1순위(프라이어 1단은 옵트인과 무관하다)
    assert on[0] == "마석소형" and off[0] == "마석소형"


def test_옵트인_꺼짐은_종전과_순서가_같다_계산층_불변_보장():
    """탁상감정 등 계산층은 기본값(꺼짐)을 쓴다. 여기가 바뀌면 감정단가가 바뀐다."""
    legacy = sorted(
        FIXTURE, key=lambda x: (0 if _nm_tail(x["dong"]) == "마석우리" else 1, -x["count"])
    )[:3]
    off = select_precut_survivors(FIXTURE, 3, "마석우리", "")
    assert [x["name"] for x in off] == [x["name"] for x in legacy]


def _nm_tail(v: str) -> str:
    return nm._dong_tail(v)


def test_지역순위는_3단이다():
    assert _locality_rank(_g("화도읍 마석우리", 1, "a"), "마석우리", "화도읍") == 0
    assert _locality_rank(_g("화도읍 창현리", 1, "b"), "마석우리", "화도읍") == 1
    assert _locality_rank(_g("다산동", 1, "c"), "마석우리", "화도읍") == 2
    # 옵트인 꺼짐이면 1단이 발화하지 않는다(0/2 = 종전 0/1 과 순서 동일)
    assert _locality_rank(_g("화도읍 창현리", 1, "b"), "마석우리", "") == 2


def test_예산_이하면_정렬조차_하지_않는다_순서보존():
    out = select_precut_survivors(FIXTURE, 99, "마석우리", "화도읍")
    assert [x["name"] for x in out] == [x["name"] for x in FIXTURE]


def test_읍면_파싱은_양방향():
    assert _eupmyeon_head("화도읍 창현리") == "화도읍"
    assert _eupmyeon_head("역삼동") == ""          # 동 지역엔 읍·면이 없다
    assert _eupmyeon_from_address("경기도 남양주시 화도읍 마석우리 265-1") == "화도읍"
    assert _eupmyeon_from_address("서울특별시 강남구 역삼동 736") == ""
    # ★못 찾으면 빈 문자열 = 2단 프라이어 **꺼짐**. 추측해서 엉뚱한 읍을 우대하지 않는다.
    assert _locality_rank(_g("화도읍 창현리", 1, "b"), "역삼동", "") == 2


def test_캐시키에_옵트인이_들어간다_안_넣으면_계산층으로_샌다():
    """지도(켜짐)와 계산층(꺼짐)이 같은 캐시 항목을 공유하면 정렬이 새어 나간다."""
    src = inspect.getsource(nm.NearbyMapService.build)
    line = next(l for l in src.split("\n") if "cache_key = ((address" in l or "cache_key = (" in l)
    tail = src[src.index(line): src.index(line) + 400]
    assert "locality_prior" in tail, "캐시 키에 locality_prior 가 없다 — 옵트인이 새어 나간다"


def test_배선_지도는_켜고_계산층은_켜지_않는다():
    """소스에 이름이 있는 것과 그것이 켜지는 것은 다르다 — 인자로 판정한다(ast)."""
    api = Path(__file__).resolve().parents[1]

    def turns_on(path: str) -> bool:
        tree = ast.parse((api / path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "locality_prior" and isinstance(kw.value, ast.Constant):
                        if kw.value.value is True:
                            return True
        return False

    assert turns_on("routers/auto_zoning.py"), "지도 라우터가 켜지 않는다"
    assert not turns_on(
        "app/services/land_intelligence/desk_appraisal_service.py"
    ), "★계산층이 켜졌다 — 감정단가가 바뀐다(토지비 SSOT→NPV·IRR 로 흐른다)"


def test_기본값이_꺼짐이어야_한다_계산층은_인자를_안_준다():
    """★계산층(탁상감정)은 `locality_prior` 를 **넘기지 않는다.** 그러니 기본값이 켜지면
    호출부를 하나도 안 고쳐도 감정단가가 바뀐다 — 배선 락(호출부 검사)이 못 잡는 축이다.
    """
    sig = inspect.signature(nm.NearbyMapService.build)
    assert sig.parameters["locality_prior"].default is False
