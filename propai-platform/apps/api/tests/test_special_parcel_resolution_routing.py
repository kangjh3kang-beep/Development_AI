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

# ★정정(2026-08-05, R3 독립 적대검증 C-1): 최초 작성 시 "가로채기 사고가 실제로 났던 4건"
#   이라고 적었으나 **틀렸다.** `detect_special_parcel`이 실제로 생산하는 category를 전수
#   열거해 보니 24종이고 그중 아래 3종은 **하나도 도달하지 않는다** —
#     막다른 도로 / 자루형 대지 통로부 / 소방·응급·공사차량 접근
#   이들을 만드는 룰(_rule_by_cul_de_sac·_rule_by_flag_lot·_rule_by_emergency_access)은
#   `access_basis_service`에서만 호출되고, 그 서비스는 `_resolution_for`를 부르지 않는다.
#   즉 **프로덕션에서 틀린 조언이 나간 것은 맹지 1건뿐**이었다.
#
#   그래도 계약은 남긴다 — 세 룰이 요인 체인에 편입되는 순간 곧바로 오답이 나가기 때문이다.
#   다만 "실측된 사고"가 아니라 **미도달 방어 계약**임을 여기 명시한다. 죽은 경로를 잠그면서
#   살아 있다고 적어두면 다음 사람이 속는다(이 저장소가 반복해 당한 '가짜 골든').
GOLDEN_FIRST_PATH = [
    # ── 실측 사고(프로덕션 도달) ──
    ("맹지(도로 미접)", "진입도로 확보"),
    # ── 미도달 방어 계약(현재 detect_special_parcel 체인이 생산하지 않음) ──
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


# ── ★근원 불변식(R3 C-2) — 카테고리 목록이 아니라 **전수 스윕**으로 잡는다 ──────────────
#
# 위 골든은 "내가 아는 이름"만 검사한다. 그래서 **새 요인을 하나 추가하면** 이름에 "도로"가
# 들어간다는 이유로 다시 '도로 폐지' 오답이 나가는데도 전부 통과한다(R3가 변이로 실증).
#
# 그래서 생산되는 category를 **실행으로 열거**해, 그중 하나라도 (a) 도시계획시설 도로가
# 아닌데 폐도 경로를 받거나 (b) 내용 없는 기본값으로 떨어지면 실패시킨다. 새 요인이 추가되면
# 이 검사가 자동으로 발화한다 — 목록을 손으로 갱신할 필요가 없다.

_SIGNAL_PROBES = [
    {"land_category": lc} for lc in
    ["대", "임야", "전", "답", "도로", "구거", "하천", "제방", "묘지", "학교용지", "종교용지", "공원"]
] + [
    {"special_districts": [d]} for d in
    ["개발제한구역", "문화재보호구역", "군사기지", "상수원보호구역", "성장관리계획구역",
     "비오톱1등급", "급경사지", "하천구역", "수변구역", "매장유산", "접도구역"]
] + [
    {"zone_type": "개발제한구역"}, {"road_contact": False}, {"road_width_m": 0},
    {"area_sqm": 60000},
]


def _produced_categories() -> set[str]:
    """detect_special_parcel이 **실제로** 만드는 요인 이름 전수."""
    found: set[str] = set()
    for probe in _SIGNAL_PROBES:
        payload = {"land_category": "대", "zone_type": "제2종일반주거지역", **probe}
        result = sp.detect_special_parcel(payload)
        if not isinstance(result, dict):
            continue
        for factor in result.get("factors") or []:
            if factor.get("category"):
                found.add(factor["category"])
    return found


def test_probe_set_actually_produces_factors():
    """공허진리 방지 — 스윕이 실제로 다수의 요인을 만들어낸다."""
    assert len(_produced_categories()) >= 15


def test_no_produced_category_falls_to_road_abolition_by_accident():
    """★이름에 '도로'가 있다는 이유로 폐도 경로를 받는 요인이 없다(새 요인 추가 시 자동 발화)."""
    offenders = []
    for category in sorted(_produced_categories()):
        first = sp._resolution_for(category, "CONDITIONAL")["resolution_paths"][0]
        if "폐지·변경" in first and "도시계획시설" in first:
            # 도시계획시설 '도로' 지목 자체는 폐도가 정답이다.
            if not category.startswith("공공·기반시설 용지(도로"):
                offenders.append((category, first))
    assert offenders == [], f"폐도 경로를 잘못 받은 요인: {offenders}"


def test_no_produced_category_falls_to_contentless_default():
    """★생산되는 요인은 전부 실질적인 해결경로를 갖는다 — 기본값('관계기관 협의')로 새지 않는다."""
    fallbacks = []
    for category in sorted(_produced_categories()):
        first = sp._resolution_for(category, "CONDITIONAL")["resolution_paths"][0]
        if first.strip() == "관계기관 협의":
            fallbacks.append(category)
    assert fallbacks == [], f"해결경로가 기본값으로 떨어진 요인: {fallbacks}"
