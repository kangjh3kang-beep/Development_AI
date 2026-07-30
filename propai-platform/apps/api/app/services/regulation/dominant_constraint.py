"""지배 제약(무엇이 발목인가) 한 줄 + 높이 상한 — 사통맵 v2 W1.

설계사·디벨로퍼가 필지를 보고 공통으로 묻는 것은 하나다: **"무엇이 발목인가."**
이 모듈은 이미 플랫폼이 가진 재료만 조합해 그 질문에 한 문장으로 답한다(신규 데이터 0):

  - severity 랭킹 → `protection_zone_severity`(SSOT). **새 등급을 만들지 않는다.**
  - 정북일조 최고높이 → `common/sunlight_setback.max_height_for_north_distance_m`(공용 산식)
  - 필지 남북깊이 → `site_score/solar_envelope_service.dims_from_polygon`(실측 geometry)

★정직 경계(가장 중요) — 이 모듈이 **수치를 만들어내지 않는 지점**:
  고도지구·비행안전구역·대공방어협조구역은 건축물 높이를 제한하지만, 플랫폼에 그 **수치
  룩업이 없다**(고도지구는 WMS 타일=그림이고 조례 높이 테이블 부재, 비행안전은 severity만
  보유). 그래서 min() 통합에 끼워 넣지 않고 `limit_m=None` + "지정됨 — 수치는 조례 확인
  필요"로 표기한다. 추정치를 채우면 "18m가 최종"이라는 거짓 확신을 준다 — 오히려 "고도지구에
  걸렸는데 수치는 조례를 봐야 한다"는 사실 자체가 설계사에게 필요한 정보다.
  (부수 티켓: 고도지구 조례 수치 수집 → 그때 이 items에 숫자가 들어오면 자동으로 min에 참여.)
"""

from __future__ import annotations

from typing import Any

from app.services.common.sunlight_setback import max_height_for_north_distance_m
from app.services.regulation.protection_zone_severity import (
    classify,
    severity_rank,
)

# ── 경사도 → severity 임계(%). 등급 라벨은 protection_zone_severity.SEVERITY_ORDER를 그대로
#    재사용한다(새 등급 정의 금지 — SSOT 이중화는 이 저장소의 반복 결함).
#    임계는 상수로 노출해 조례·현장 감각에 맞춰 한 곳에서 조정 가능하게 한다.
SLOPE_HIGH_PCT = 20.0   # 이상 → "높음"(개발행위허가 경사도 기준선 근방·토공비 급증)
SLOPE_MID_PCT = 10.0    # 이상 → "보통"(옹벽·단지 정지계획 필요)

# ── 경사도를 랭킹에 실을 최소 severity. ★규제 designation에는 이 하한을 적용하지 않는다:
#    경사도 "낮음"은 **측정값이 임계 미달**(= 제약이 없다)이지만, 경관지구·방화지구 같은
#    "낮음" 지정은 **실제로 지정되어 있다**(= 심의·내화구조라는 진짜 제약). 둘을 같은 하한으로
#    자르면 경관지구만 걸린 필지가 배너 없이 조용히 넘어간다(정보 소실). 성질이 다르므로
#    하한도 경사도에만 적용한다.
SLOPE_RANKED_FLOOR = "보통"
# 한 줄 답 + 그다음 몇 개까지 보여줄지(상세 목록은 종합 부지분석이 담당).
RANKED_LIMIT = 3

# ── 정북일조(건축법 제61조·시행령 제86조 제1항)가 적용되는 용도지역 = 전용/일반주거지역.
#    ★그 외(상업·공업·녹지·관리·농림 등)에 일조 상한을 붙이면 **없는 제약을 만드는 날조**다.
#    호미곶 보전관리지역·임야가 바로 그 사례 — 여기엔 정북일조 항목이 나오지 않아야 한다.
_SUNLIGHT_ZONE_KEYWORDS = ("전용주거지역", "일반주거지역")

_SUNLIGHT_BASIS = "건축법 제61조·시행령 제86조 제1항(정북 인접대지경계선 일조 확보)"
_NO_NUMBER_NOTE = "지정됨 — 수치는 조례 확인 필요(플랫폼 미보유)"


def slope_severity(slope_pct: float | None) -> str | None:
    """평균 경사도(%) → severity 라벨. 미상(None)·비수치는 None(무날조 — 없는 값 만들지 않음)."""
    if slope_pct is None or isinstance(slope_pct, bool) or not isinstance(slope_pct, (int, float)):
        return None
    pct = float(slope_pct)
    if pct >= SLOPE_HIGH_PCT:
        return "높음"
    if pct >= SLOPE_MID_PCT:
        return "보통"
    return "낮음"


def _build_height(
    north_distance_m: float | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """높이 상한 블록 — **수치 보유 항목만** min()에 참여시키고, 미보유는 정직 표기로 남긴다.

    반환 None = 높이를 제약하는 항목이 하나도 없음(빈 블록을 만들지 않는다).
    """
    items: list[dict[str, Any]] = []

    # ① 정북일조 — 수치 산출 가능(공용 산식). 남북깊이는 호출측이 용도지역 게이트를 통과한
    #    경우에만 넘겨준다(north_distance_for_sunlight).
    if north_distance_m is not None and float(north_distance_m) > 0:
        d = float(north_distance_m)
        items.append({
            "source": "정북일조",
            "limit_m": round(max_height_for_north_distance_m(d), 1),
            "basis": _SUNLIGHT_BASIS,
            # 근사임을 문구로 명시 — 실제 배치·인접지 관계(북측이 도로·공지면 완화)로 달라진다.
            "note": f"필지 남북깊이 {round(d, 1)}m 기준 상한(직사각 근사 — 실제 배치로 낮아질 수 있음)",
        })

    # ② 높이를 제한하지만 플랫폼이 수치를 못 가진 지정 — 숫자 대신 "확인 필요"를 남긴다.
    for cand in candidates:
        if cand.get("height_constraining"):
            items.append({
                "source": cand["name"],
                "limit_m": None,
                "basis": None,
                "note": _NO_NUMBER_NOTE,
            })

    if not items:
        return None

    numeric = [i for i in items if i["limit_m"] is not None]
    governing = min(numeric, key=lambda i: float(i["limit_m"])) if numeric else None
    return {
        "governing_m": governing["limit_m"] if governing else None,
        "governing_source": governing["source"] if governing else None,
        # ★수치 미보유 항목이 하나라도 있으면 governing_m은 최종값이 아니다 — 화면이 "일부
        #   미반영" 배지를 띄우는 근거. 이 플래그를 빼면 18m가 확정처럼 읽힌다.
        "incomplete": any(i["limit_m"] is None for i in items),
        "items": items,
    }


def resolve_dominant_constraint(
    regulations: list[str] | None,
    *,
    north_distance_m: float | None = None,
    slope_pct: float | None = None,
) -> dict[str, Any]:
    """이 필지에서 '무엇이 가장 발목인가'를 한 줄로 답한다(순수함수 — 외부 I/O 0).

    Args:
        regulations: 규제 designation 이름 목록(기존 land_use districts·special_districts).
        north_distance_m: 정북 인접지까지의 거리(m). **정북일조가 적용되는 용도지역일 때만**
            넘긴다 — 판정은 north_distance_for_sunlight가 소유(여기서 용도지역을 다시 보지 않음).
        slope_pct: terrain 평균 경사도(%). 미상은 None.

    Returns:
        {"headline", "severity", "ranked": [...], "height": {...}|None}
        제약이 하나도 없으면 headline/severity=None·ranked=[]로 정직 반환(빈 dict가 아니라
        "없음"을 명시). 배너를 숨기는 판단은 build_for_parcel/화면이 한다.
    """
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in regulations or []:
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        hit = classify(name)  # SSOT — severity·조치·높이제약 여부를 한 번에
        if hit is None:
            continue
        candidates.append({
            "name": name,
            "severity": hit["severity"],
            "action": hit["action"],
            "reason": hit["reason"],
            "height_constraining": hit["height_constraining"],
        })

    # 경사도는 규제 designation이 아니지만 실무에서 같은 질문("발목")의 답이라 함께 랭킹한다.
    #   단 "낮음"(임계 미달 = 제약 없음)은 넣지 않는다 — SLOPE_RANKED_FLOOR 주석 참조.
    _slope_sev = slope_severity(slope_pct)
    if _slope_sev and severity_rank(_slope_sev) >= severity_rank(SLOPE_RANKED_FLOOR):
        candidates.append({
            "name": f"경사도 {round(float(slope_pct or 0))}%",
            "severity": _slope_sev,
            "action": "토공 계획 검토",
            "reason": "경사도가 커 토공·옹벽 비용과 개발행위허가 부담이 커짐",
            "height_constraining": False,
        })

    # severity 내림차순(동순위는 입력 순서 보존 — sorted는 stable).
    candidates.sort(key=lambda c: -severity_rank(c["severity"]))

    ranked = [
        {"name": c["name"], "severity": c["severity"], "action": c["action"]}
        for c in candidates[:RANKED_LIMIT]
    ]
    top = candidates[0] if candidates else None
    return {
        "headline": (f"{top['name']} — {top['reason']}" if top and top.get("reason") else
                     (top["name"] if top else None)),
        "severity": top["severity"] if top else None,
        "ranked": ranked,
        "height": _build_height(north_distance_m, candidates),
    }


def north_distance_for_sunlight(
    zone_type: str | None,
    geometry: dict[str, Any] | None,
) -> float | None:
    """정북일조 산출에 쓸 남북깊이(m) — **적용 용도지역 + 실측 geometry가 둘 다 있을 때만**.

    ★이 게이트가 단일 소유자다: 소비처(지도 경계·종합분석)가 각자 용도지역을 판정하면 한쪽만
    고쳐지는 발산이 생긴다. 적용 대상이 아니거나 geometry 미보유면 None → 높이 항목 미생성.
    """
    if not zone_type or not geometry:
        return None
    z = str(zone_type).replace(" ", "")
    if not any(kw in z for kw in _SUNLIGHT_ZONE_KEYWORDS):
        return None
    try:
        from app.services.site_score.solar_envelope_service import dims_from_polygon

        dims = dims_from_polygon(geometry)
    except Exception:  # noqa: BLE001 — 기하 파싱 실패는 미상(None) 정직 반환
        return None
    depth = (dims or {}).get("depth_m")
    if isinstance(depth, bool) or not isinstance(depth, (int, float)) or float(depth) <= 0:
        return None
    return float(depth)


def build_for_parcel(
    *,
    regulations: list[str] | None,
    zone_type: str | None = None,
    geometry: dict[str, Any] | None = None,
    slope_pct: float | None = None,
) -> dict[str, Any] | None:
    """필지 1건의 지배 제약 블록 — **모든 소비처의 단일 진입점**.

    용도지역 게이트(정북일조 적용 여부)와 "말할 것이 없으면 None" 규약을 여기서 한 번만
    정하고, 지도 경계 응답·종합분석이 같은 함수를 부른다(로직 복제 금지 — 한 곳을 고치면
    전역이 따라온다). None을 돌려주면 화면은 배너를 렌더하지 않는다(빈 배너 금지 원칙을
    표면이 아니라 계약 수준에서 보장).
    """
    dc = resolve_dominant_constraint(
        regulations,
        north_distance_m=north_distance_for_sunlight(zone_type, geometry),
        slope_pct=slope_pct,
    )
    if not dc.get("headline") and not dc.get("height"):
        return None
    return dc
