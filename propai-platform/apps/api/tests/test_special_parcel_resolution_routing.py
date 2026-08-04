"""해결경로 라우팅 골든 — "이 제약을 푸는 방법" 카드에 틀린 조언이 나가지 않게 잠근다.

★왜 이 파일이 있나(2026-08-03 실측 적발):
  해결경로를 요인 **이름의 부분문자열**로 골랐더니 이름이 겹치는 요인 4건이 엉뚱한
  분기에 먹혔다. 그중 최악은 맹지다 — 도로가 **없어서** 문제인 필지에게
  "도시계획시설(도로) **폐지**·변경"을 첫 번째 해결책으로 제시했다. 정반대다.

  이 값들은 #528(W4-1)이 화면에 표면화한 "이 제약을 푸는 방법" 카드로 그대로 나간다.
  즉 W4가 선재 오류의 노출도를 키웠다. 어떤 테스트도 게이트도 이걸 잡지 못했다.

★이 골든이 잠그는 것: 생산되는 **모든** 요인 이름에 대해 첫 해결경로가 무엇인지.
  분기 순서를 바꾸거나 새 요인을 넣다가 다른 요인을 가로채면 여기서 깨진다.
"""
from app.services.zoning import special_parcel as sp

# (요인 이름, 첫 해결경로에 반드시 들어갈 문구) — 생산자가 실제로 만드는 이름만 적는다.
# 왼쪽은 특정 분기가 **가로채기 쉬운** 이름들(도로·소방이 이름에 들어간다)이 앞에 온다.
GOLDEN_FIRST_PATH = [
    # ── 가로채기 사고가 실제로 났던 4건 ──
    ("맹지(도로 미접)", "진입도로 확보"),
    ("막다른 도로(길이별 최소 너비)", "막다른 도로 길이별 최소 너비 확보"),
    ("자루형(旗竿) 대지 통로부", "통로부(자루목) 최소너비 확보"),
    ("소방·응급·공사차량 접근", "소방자동차 진입로 폭"),
    # ── 가로채면 안 되는 쪽(정상 동작 — 오탐 0 확인용) ──
    ("공공·기반시설 용지(도로)", "도시계획시설(도로) 폐지·변경"),
    ("도로법 접도구역·연결허가 대상", "도로관리청 접도구역 협의"),
    ("소방 성능위주설계(PBD) 대상", "소방 성능위주설계 평가단"),
    ("학교용지(도시계획시설 가능성)", "도시계획시설 폐지/변경"),
    ("임야(산지)", "산지전용허가"),
    ("농지(전)", "농지전용허가"),
    ("개발제한구역(GB)", "GB 해제는"),
    ("묘지", "분묘 개장"),
    ("하천구역·소하천구역(점용허가)", "하천(소하천) 점용허가"),
]


def test_golden_first_resolution_path_per_category():
    """요인 이름별 첫 해결경로 고정 — 분기 순서가 바뀌면 여기서 깨진다."""
    for category, expected in GOLDEN_FIRST_PATH:
        got = sp._resolution_for(category, "CONDITIONAL")["resolution_paths"][0]
        assert expected in got, f"{category!r} → {got!r} (기대: {expected!r} 포함)"


def test_maengji_never_gets_road_abolition_advice():
    """★도로가 없어서 문제인 필지에 '도로 폐지'를 권하지 않는다 — 실제 사고의 직접 재현."""
    result = sp.detect_special_parcel({
        "land_category": "대", "zone_type": "제1종일반주거지역", "road_contact": False,
    })
    factor = next(f for f in result["factors"] if "맹지" in f["category"])
    joined = " ".join(factor["resolution_paths"])
    assert "폐지" not in joined and "폐도" not in joined, joined
    assert "진입도로 확보" in factor["resolution_paths"][0]


def test_producers_stamp_resolution_key():
    """생산자가 판정 코드를 실제로 심는다 — 이름이 바뀌어도 해결경로가 안 흔들리게."""
    result = sp.detect_special_parcel({
        "land_category": "대", "zone_type": "제1종일반주거지역", "road_contact": False,
    })
    factor = next(f for f in result["factors"] if "맹지" in f["category"])
    assert factor.get("resolution_key") == "ROAD_NO_ACCESS"


def test_code_wins_over_name():
    """코드가 있으면 이름이 무엇이든 코드가 이긴다 — 이름을 쉬운 말로 바꿔도 안전.

    ★이 단언이 없으면 '코드를 심었다'는 사실만 남고 코드가 실제로 판정에 쓰이는지는
    아무도 확인하지 않는다(코드를 읽지 않아도 이름 분기가 정답을 내면 통과해버린다).
    그래서 이름은 일부러 **다른 분기로 갈 이름**을 준다.
    """
    got = sp._resolution_for("공공·기반시설 용지(도로)", "CONDITIONAL", "ROAD_NO_ACCESS")
    assert "진입도로 확보" in got["resolution_paths"][0]


def test_unknown_key_falls_back_to_name():
    """모르는 코드가 오면 이름 판정으로 내려간다 — 구버전/신버전 혼재에서 무회귀."""
    got = sp._resolution_for("임야(산지)", "CONDITIONAL", "NOT_A_REAL_KEY")
    assert "산지전용허가" in got["resolution_paths"][0]


def test_every_key_in_table_is_reachable_from_a_producer_name():
    """표에 있는 코드는 전부 이름 힌트로도 닿는다 — 저장된 구 payload가 기본값으로 떨어지지 않게.

    ★공허진리 방지: 표가 비면 이 테스트는 통과해버리므로 최소 개수를 함께 단언한다.
    """
    assert len(sp._RESOLUTION_BY_KEY) >= 4
    reachable = {key for _, key in sp._KEY_BY_NAME_HINT}
    assert set(sp._RESOLUTION_BY_KEY) == reachable
