"""예상 탁상감정(Desk Appraisal) — 정식 감정평가가 아닌 사전 추정(은행 탁상가액 성격).

감정평가에 관한 규칙 기준 방법론을 우리 데이터에 매핑:
 1) 공시지가기준법(원칙, 제14조): 개별공시지가 × 시점수정 × 개별요인(접도·면적) × 그 밖의 요인(기타요인) 보정.
    - '그 밖의 요인'은 공시지가↔시세 괴리 보정으로, 지역 시세보정계수(MARKET_MULTIPLIER)를 사용.
 2) 거래사례비교법(보조, 제14조): 인근 토지 실거래 평균단가(있을 때) 비교.
 3) 결합: 공시지가기준법 주(主) + 거래사례 보조 가중, 신뢰도·근거 제시.

⚠ 정식 감정평가가 아닌 참고용 탁상 추정치(사용자 수정 가능). 실제 평가는 감정평가사 의뢰 필요.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.land_intelligence.land_price_estimator import _market_multiplier
from app.services.market.land_dong_stats import stats_note as land_stats_note
from app.utils.pnu import lawd_cd_from_pnu

logger = structlog.get_logger(__name__)

# 개별요인 — 접도(road_side) 보정율(감정평가 개별요인의 가로조건 근사)
_ROAD_FACTOR = [
    (("광대",), 1.10, "광대로 접면(가로조건 우세)"),
    (("중로",), 1.02, "중로 접면"),
    (("소로",), 0.97, "소로 접면"),
    (("세로(가)", "세로가"), 0.93, "세로(가) 접면"),
    (("세로(불)", "세로불", "맹지"), 0.85, "세로(불)/맹지(가로조건 열세)"),
]


def _road_factor(road_side: str | None) -> tuple[float, str]:
    rs = road_side or ""
    for keys, f, label in _ROAD_FACTOR:
        if any(k in rs for k in keys):
            return f, label
    return 1.0, "접도 보통(기본)"


def _area_factor(area_sqm: float | None) -> tuple[float, str]:
    """면적 개별요인(과대·과소 획지 감가) 근사."""
    if not area_sqm:
        return 1.0, "면적요인 미적용"
    if area_sqm < 60:
        return 0.95, "과소획지(60㎡ 미만) 소폭 감가"
    if area_sqm > 3000:
        return 0.97, "대규모 획지 환금성 감가"
    return 1.0, "표준 규모"


# 건물 재조달원가(원/㎡, 2026 근사)·내용연수 — 원가법 건물가치 산정용
_REPLACEMENT_COST = {
    "SRC": (2_500_000, 50), "철골철근콘크리트": (2_500_000, 50),
    "RC": (2_000_000, 50), "철근콘크리트": (2_000_000, 50),
    "철골": (1_800_000, 40), "S조": (1_800_000, 40),
    "조적": (1_500_000, 45), "벽돌": (1_500_000, 45),
    "목조": (1_400_000, 40), "목": (1_400_000, 40),
}
_RESIDUAL_FLOOR = 0.2  # 잔가율 하한(잔존가치 20%)


def _building_value(gfa: float | None, structure: str | None, year_built: int | None, now_year: int) -> dict[str, Any] | None:
    """원가법 건물가치 = 재조달원가 × 연면적 × 잔가율(1 − 경과/내용연수, 하한 20%)."""
    if not gfa or gfa <= 0:
        return None
    rc, life = 1_800_000, 45
    matched = "기본(RC 가정)"
    for key, (cost, yrs) in _REPLACEMENT_COST.items():
        if structure and key in structure:
            rc, life, matched = cost, yrs, key
            break
    age = max(0, now_year - year_built) if year_built else 0
    residual = max(_RESIDUAL_FLOOR, 1 - age / life) if life else _RESIDUAL_FLOOR
    value = int(rc * gfa * residual)
    return {
        "method": "원가법(건물)",
        "replacement_cost_per_sqm": rc,
        "structure": matched, "useful_life_yrs": life,
        "age_yrs": age, "residual_ratio": round(residual, 3),
        "building_value_won": value,
        "rationale": f"재조달원가 {rc:,}원/㎡ × 연면적 {gfa:,.0f}㎡ × 잔가율 {residual:.2f}(경과 {age}년/내용 {life}년) = {value:,}원",
    }


def _income_value(
    monthly_rent_won: float | None, deposit_won: float | None,
    vacancy_rate: float, opex_ratio: float, cap_rate: float,
    deposit_conv_rate: float = 0.055, cap_source: str = "기본", conv_source: str = "기본",
) -> dict[str, Any] | None:
    """수익환원법 — 부동산 가치 = 순영업소득(NOI) / 자본환원율.

    NOI = (월임대료 + 보증금 운용수익) × 12 × (1−공실률) × (1−운영경비율).
    보증금은 전월세전환율로 운용수익 환산(R-ONE 실측 가용 시 실데이터).
    """
    if not monthly_rent_won or monthly_rent_won <= 0:
        return None
    conv = deposit_conv_rate if deposit_conv_rate and deposit_conv_rate > 0 else 0.055
    deposit_monthly = (deposit_won or 0) * conv / 12  # 보증금 월 운용수익
    pgi = (monthly_rent_won + deposit_monthly) * 12      # 가능총수익(연)
    noi = pgi * (1 - vacancy_rate) * (1 - opex_ratio)    # 순영업소득
    cap = cap_rate if cap_rate > 0 else 0.045
    value = int(noi / cap)
    return {
        "method": "수익환원법",
        "noi_won": int(noi), "cap_rate": cap, "cap_rate_source": cap_source,
        "deposit_conv_rate": round(conv, 4), "deposit_conv_source": conv_source,
        "vacancy_rate": vacancy_rate, "opex_ratio": opex_ratio,
        "income_value_won": value,
        "rationale": f"NOI {int(noi):,}원(월임대 {int(monthly_rent_won):,}×12, 보증금 전환율 {conv*100:.1f}%[{conv_source}], 공실 {vacancy_rate*100:.0f}%·경비 {opex_ratio*100:.0f}% 차감) ÷ 자본환원율 {cap*100:.1f}%[{cap_source}] = {value:,}원",
    }


def _shape_factor(irregularity: float | None) -> tuple[float, str]:
    """형상 개별요인 — 부정형도(1-실면적/bbox)로 형상 감가(정형 우세, 부정형 열세)."""
    if irregularity is None:
        return 1.0, "형상 미상(정형 가정)"
    if irregularity >= 0.5:
        return 0.90, "심한 부정형(가로/이용 효율 열세)"
    if irregularity >= 0.3:
        return 0.95, "부정형(소폭 감가)"
    if irregularity >= 0.15:
        return 0.98, "준정형"
    return 1.0, "정형(효율 우세)"


async def desk_appraisal(
    *,
    pnu: str | None = None,
    address: str = "",
    area_sqm: float | None = None,
    official_price_per_sqm: float | None = None,
    comparable_avg_per_sqm: float | None = None,   # 거래사례 평균단가(주변 토지 실거래)
    time_adjust: float | None = None,                # 시점수정(미지정 시 지가변동률로 산정)
    base_year: int | None = None,   # 미지정 시 **실제 공시연도**에서 유도(아래 주석)
    building_gfa_sqm: float | None = None,           # 건물 연면적(주면 토지+건물 복합 추정)
    building_structure: str | None = None,           # 구조(RC/SRC/철골/조적/목조)
    building_year_built: int | None = None,          # 준공연도(감가상각)
    monthly_rent_won: float | None = None,           # 월 임대료(주면 수익환원법 병행)
    deposit_won: float | None = None,                # 보증금
    vacancy_rate: float = 0.05,                      # 공실률
    opex_ratio: float = 0.25,                        # 운영경비율
    cap_rate: float | None = None,                   # 자본환원율(미지정 시 R-ONE 실측→0.045)
) -> dict[str, Any]:
    """예상 탁상감정가 산출(공시지가기준법 + 거래사례비교법 결합)."""
    op = official_price_per_sqm
    area = area_sqm
    road_side = None
    src = "입력값"
    subject: dict[str, Any] = {}   # 대상물건 표시(지목·용도지역·이용상황 등)

    # ★★라이브 검증(2026-08-06)에서 적발 — 이 조건이 **거래사례비교법을 통째로 삼킨다**.
    #   종전엔 "공시지가나 면적이 없을 때만" 이 블록을 탔다. 그런데 PNU 는 여기서만 해석되고,
    #   아래 거래사례 블록은 `pnu` 를 요구한다. 그래서 **사용자가 공시지가와 면적을 둘 다
    #   입력하면** PNU 가 안 잡히고 → 주변 실거래를 조회조차 못 하고 → 사유도 없이 조용히
    #   공시지가 단독으로 떨어졌다.
    #   ★프로덕션 실측(강남 논현동 1-1):
    #     · 공시지가 비움 → pnu=1168010800100010001 · "286건 전부 마스킹 지번" 사유 표시
    #     · 면적 비움     → 같음
    #     · **둘 다 입력  → pnu=None · 사유 None(완전 침묵)**
    #   ★사용자가 정보를 **더 줄수록 분석이 줄어드는** 역설이었다. 공시지가·면적 입력은
    #   공시지가기준법의 정확도를 높일 뿐, 거래사례비교법을 포기할 이유가 되지 못한다.
    #   → 거래사례 단가를 아직 못 받았으면 PNU 해석을 **시도한다**(이미 받았으면 불필요).
    if op is None or not area or pnu or comparable_avg_per_sqm is None:
        try:
            import asyncio as _asyncio

            from app.services.external_api.vworld_service import VWorldService
            vw = VWorldService()
            if not pnu and address:
                # VWorld 지오코딩 간헐 실패 대비 최대 3회 재시도(공시지가 미조회 빈도↓)
                for _attempt in range(3):
                    geo = await vw.geocode_address(address)
                    pnu = (geo or {}).get("pnu") or pnu
                    if pnu:
                        break
                    await _asyncio.sleep(0.4)
            lc = None
            if pnu:
                for _attempt in range(3):
                    lc = await vw.get_land_characteristics(pnu)
                    if lc and lc.get("official_price_per_sqm"):
                        break
                    await _asyncio.sleep(0.4)
                if lc:
                    op = op if op is not None else lc.get("official_price_per_sqm")
                    area = area or lc.get("area_sqm")
                    road_side = lc.get("road_side") or None
                    src = "NED 토지특성(주소→PNU)"
                    subject = {
                        "land_category": lc.get("land_category") or None,      # 지목
                        "zone_type": lc.get("zone_type") or None,              # 용도지역
                        "zone_type_2": lc.get("zone_type_2") or None,
                        "land_use_situation": lc.get("land_use_situation") or None,  # 이용상황
                        "terrain_height": lc.get("terrain_height") or None,
                        "terrain_form": lc.get("terrain_form") or None,
                        "official_price_year": lc.get("year") or None,
                    }
        except Exception:  # noqa: BLE001
            pass

    if not op or op <= 0:
        return {"ok": False, "message": "공시지가를 확인할 수 없습니다. PNU 또는 공시지가를 입력하세요."}

    # 거래사례 자동 연동: 미입력 시 주변 토지 실거래 평균단가(/㎡)를 자동 추출
    # ★자동 연동으로 만든 표본의 근거(범위·제외건수). 사용자가 단가를 직접 넣었거나 연동이
    #   실패하면 None 으로 남고, 그때는 rationale 이 "인근"을 주장하지 않는다.
    comparable_basis = None
    # 거래사례비교법을 **왜 못 썼는지**. 값이 사라진 이유를 말하지 않으면 사용자는 그냥
    # "그런 방법이 없나 보다"로 읽는다(무자료와 판정불가는 다른 상태다).
    comparable_skip_note: str | None = None
    # ★토지 층화 통계(참고) — 좌표가 없어 반경으로는 못 말하는 것을 행정구역+용도 축으로.
    land_dong_stats_out: dict | None = None
    if comparable_avg_per_sqm is None and lawd_cd_from_pnu(pnu):
        try:
            from app.services.land_intelligence.nearby_map_service import NearbyMapService
            from app.services.market.comparable_sample import (
                no_sample_reason,
                select_located_groups,
                weighted_unit_price_per_sqm,
            )
            payload = await NearbyMapService().build(
                address=address or "", lawd_cd=pnu[:5], months=6, radius_m=1500,
                # ★용도지역을 넘겨 토지 층화 통계가 `동+용도` 층까지 내려갈 수 있게 한다.
                #   모르면 빈 값 — 그때는 `동` 층부터 시작한다(빈값끼리 매칭하지 않는다).
                target_land_use=str((subject or {}).get("zone_type") or ""),
                # ★지목(`land_category`)도 넘긴다 — 같은 동에서도 `대` 와 `도로` 는 단가가
                #   자릿수로 다르다. 안 넘기면 섞인 값이 나온다(라이브에서 실제로 겪었다:
                #   논현동 실거래 중앙값이 공시지가의 0.54배).
                target_jimok=str((subject or {}).get("land_category") or ""),
            )
            land_dong_stats_out = payload.get("land_dong_stats")
            land_cat = (payload.get("categories") or {}).get("land_trade") or {}
            # ★W1-b 근본수정 — 종전엔 `land_cat["groups"]` 를 통째로 순회해 **위치가 확인되지
            #   않은**(지오코딩 실패) 거래까지 거래사례비교법 단가에 넣었다. 그래놓고 rationale 은
            #   그 값을 "인근 토지 실거래 평균"이라고 **적극 주장**했다.
            #   호미곶 대보리 산1-1 라이브 실측(2026-08-02): land_trade 는 count_in_radius=0,
            #   즉 반경 1.5km 안에서 위치가 확인된 토지 거래가 **한 건도 없는데** 20~30km 밖
            #   오천읍 거래로 304,979원/㎡ 를 만들었고, 그 결과 채택 단가가 공시지가 기준
            #   3,264원/㎡ 대비 117,467원/㎡(**36배**)가 됐다. 강남 역삼동에서는 같은 오염이
            #   반대로 감정단가를 38.5% **낮췄다** — 방향이 일정하지 않아 "보수적이라 안전"이
            #   성립하지 않는다. 이 단가는 개략수지 토지비 1순위 SSOT 로도 흘러간다.
            located, basis = select_located_groups(land_cat)
            # ★W1-b 리뷰(M-2) — **근접성 보증이 없으면 감정 단가를 만들지 않는다.**
            #   중심 주소 지오코딩이 실패하면 `radius_applied=False` 가 되고, 그때 `located` 는
            #   "반경 안"이 아니라 **시군구 전역의 정밀 좌표분**이다. 종전 봉합은 그 값을 그대로
            #   쓰고 rationale 문구만 "시군구 전체"로 바꿨는데, 그러면 호미곶 케이스의 20~30km
            #   밖 단가(304,979원/㎡)가 이름만 바꾼 채 그대로 재생산된다.
            #   ★시세 **표시**는 caveat 로 정직해질 수 있지만, 감정 **단가**는 다르다 —
            #   이 값은 `firm_vals` 가중에 들어가 채택단가가 되고, 개략수지 토지비 1순위
            #   SSOT 로 전파돼 NPV·IRR·분양가 역산까지 흔든다. 근거가 약하면 만들지 않는다.
            if basis.scope == "radius":
                comparable_avg_per_sqm = weighted_unit_price_per_sqm(located)
                comparable_basis = basis
                # ★★침묵 봉합 — 반경은 적용됐는데 **표본이 0** 이면 종전엔 아무 사유 없이
                #   공시지가 기준으로 폴백했다(`comparable_skip_note` 는 반경 **미적용**
                #   가지에만 있었다). 사용자는 "왜 거래사례비교를 안 썼는지" 알 수 없었다.
                #   ★라이브 실측: 토지·단독다가구는 원천(MOLIT)이 지번을 가려서 주므로
                #     (`"5*"`·`"1**"`) 위치 확인분이 **구조적으로 0** 이다 — 이 침묵 구간의
                #     지배적 원인이고, 우리가 고칠 수 없는 **데이터 한계**다. 그러면 그 사실을
                #     말하는 것이 정직이다("거래가 없다"와 전혀 다른 상태다).
                if comparable_avg_per_sqm is None:
                    # ★R1 리뷰(m-6)는 이 줄을 **죽은 대입**이라 지적했고 사실이다 — 아래
                    #   `method_cmp` 블록은 단가가 있어야 실행되므로 이 값은 관측되지 않는다.
                    #   그럼에도 남긴다: "값이 없으면 근거도 없다"는 불변식을 코드로 말하는
                    #   자리이고, 나중에 이 아래에서 basis 를 읽는 소비처가 생기면 삭제된
                    #   상태에서는 **표본 0 인데 근거는 있음**이 된다. 죽은 줄이라는 사실을
                    #   주석으로 밝히는 편이 조용히 지우는 것보다 안전하다.
                    comparable_basis = None
                    comparable_skip_note = no_sample_reason(basis)
            else:
                comparable_avg_per_sqm = None
                comparable_basis = None
                comparable_skip_note = (
                    "대상지 중심좌표를 확보하지 못해 반경 필터가 적용되지 않았습니다 — "
                    "근접성이 보증되지 않는 거래를 감정 단가에 쓰지 않고 공시지가기준법 단독으로 "
                    "산정했습니다."
                )
        except Exception:  # noqa: BLE001
            # ★R6 리뷰(F-G) — 사유는 **사용자** 몫이고, 원인은 **운영자** 몫이다.
            #   이 모듈엔 logger 참조가 0건이라 MOLIT·지오코더 장애 때 스택트레이스가
            #   어디에도 남지 않았다(F-3 의 논거 자체가 관측성인데 정작 관측이 없었다).
            # ★정직 표기 — 이 로그 문구는 **변이로 잠기지 않는다**(전수 감사 실측).
            #   로그는 운영자용 관측이지 사용자 계약이 아니라, 문구를 테스트로 고정하면
            #   관측을 개선할 때마다 테스트가 깨진다. 사용자가 읽는 문구(아래 사유)는
            #   전문 리터럴로 잠갔다 — 잠글 것과 잠그지 않을 것을 구분한다.
            logger.warning("desk_appraisal.comparable_lookup_failed", exc_info=True)
            # ★★R5 리뷰(F-3) — 여기서 그냥 삼키면 `comparable_skip_note` 가 **None 인 채로**
            #   빠져나가 봉합 이전과 **똑같은 완전 침묵**이 된다. MOLIT 장애·지오코더 장애가
            #   정확히 이 경로다 — 즉 침묵 봉합에 구멍이 남아 있었다.
            #   ★사유를 만들되 원인을 **아는 만큼만** 말한다: 우리 연동이 실패했다는 사실은
            #   확실하고, 그 지역에 거래가 있는지 없는지는 **모른다**(그걸 알 방법이 없어서
            #   실패한 것이다). "거래가 없다"로 읽히지 않게 쓰는 것이 요점이다.
            comparable_avg_per_sqm = None
            comparable_basis = None
            comparable_skip_note = (
                "실거래 자료를 불러오지 못해 거래사례비교법을 쓰지 못했습니다 — "
                "이 지역에 거래가 없다는 뜻이 아니라 조회가 실패했다는 뜻입니다. "
                "공시지가기준법 단독으로 산정했습니다."
            )

    elif comparable_avg_per_sqm is None:
        # ★R5 리뷰(F-3) — `pnu` 가 없거나 짧으면 위 블록을 **아예 타지 않아** 사유가 없다.
        #   조회를 시도조차 못 한 것도 "왜 안 썼는지"의 한 갈래다.
        comparable_skip_note = (
            "대상지 필지번호(PNU)를 확정하지 못해 주변 실거래를 조회하지 못했습니다 — "
            "공시지가기준법 단독으로 산정했습니다."
        )

    # 형상 개별요인 — 필지 폴리곤 부정형도로 형상 감가
    irregularity = None
    if pnu:
        try:
            from app.services.external_api.vworld_service import VWorldService
            from app.services.site_score.solar_envelope_service import dims_from_polygon
            parcel = await VWorldService().get_parcel_by_pnu(pnu)
            dims = dims_from_polygon((parcel or {}).get("geometry"))
            if dims:
                irregularity = dims.get("irregularity")
        except Exception:  # noqa: BLE001
            pass

    op = float(op)
    area_f = float(area) if area else None

    # ★공시지가 **값**과 시점수정 **기준연도**는 한 쌍이다(2026-08-22).
    #   시점수정은 `공시기준일(base_year-01-01) → 가격시점` 경과연수로 계산되므로,
    #   공시지가를 어느 연도에서 가져왔는지와 **반드시 일치**해야 한다.
    #   종전엔 base_year=2025 가 박혀 있었다. 같은 PR 에서 NED 기준연도 하드코딩을 걷어내
    #   공시지가가 2026년치로 올라가는데 이걸 두면 경과연수가 **1년 과다** 계산돼
    #   토지가액이 조용히 부푼다(연 지가변동률 2~3% → 400억 부지면 8~12억).
    if base_year is None:
        from app.services.external_api.vworld_service import _current_year
        base_year = subject.get("official_price_year") or _current_year()

    # 시점수정: 미지정 시 R-ONE 지가변동률 실데이터(가용 시)→근사 폴백
    from app.services.land_intelligence.land_price_index import time_adjust_factor_async
    ta = await time_adjust_factor_async(address, base_year)
    time_adjust = float(time_adjust) if time_adjust is not None else ta["factor"]

    # R-ONE 부동산통계 인제스션: cap rate·전월세전환율 실데이터 주입(가용 시)
    cap_source, conv_source = "기본", "기본"
    cap_resolved = float(cap_rate) if cap_rate is not None else 0.045
    if cap_rate is not None:
        cap_source = "사용자"
    deposit_conv = 0.055
    market_stats: dict[str, Any] = {}
    try:
        from app.services.land_intelligence.reb_statistics_service import get_market_stats
        # ★위 시점수정(ta)과 **같은 기준연도**를 넘긴다 — 한 함수 안에서 두 기준이 갈리면
        #   응답에 실린 두 값이 서로 모순된다.
        market_stats = await get_market_stats(address, base_year=base_year)
        if cap_rate is None and (market_stats.get("cap_rate") or {}).get("cap_rate"):
            cap_resolved = market_stats["cap_rate"]["cap_rate"]
            cap_source = "R-ONE"
        if (market_stats.get("jeonse_conversion_rate") or {}).get("rate"):
            deposit_conv = market_stats["jeonse_conversion_rate"]["rate"]
            conv_source = "R-ONE"
    except Exception:  # noqa: BLE001
        market_stats = {}

    # ── 1) 공시지가기준법 ──
    other_factor, other_rationale = _market_multiplier(address)   # 그 밖의 요인(기타요인) 보정
    road_f, road_label = _road_factor(road_side)
    area_fac, area_label = _area_factor(area_f)
    shape_f, shape_label = _shape_factor(irregularity)
    pub_unit_price = int(op * time_adjust * road_f * area_fac * shape_f * other_factor)
    method_pub = {
        "method": "공시지가 기준 추정",
        "unit_price": pub_unit_price,
        "factors": {
            "개별공시지가": int(op), "시점수정": time_adjust,
            "개별요인_접도": road_f, "개별요인_면적": area_fac, "개별요인_형상": shape_f,
            "그밖의요인": other_factor,
        },
        "rationale": f"개별공시지가 {int(op):,}원/㎡ × 시점수정 {time_adjust} × 접도 {road_f}({road_label}) × 면적 {area_fac} × 형상 {shape_f}({shape_label}) × 그밖의요인 {other_factor}({other_rationale})",
    }

    # ── 2) 거래사례비교법 ──
    method_cmp = None
    cmp_unit_price = 0
    if comparable_avg_per_sqm and comparable_avg_per_sqm > 0:
        cmp_unit_price = int(float(comparable_avg_per_sqm) * road_f * area_fac * shape_f)  # 개별요인 보정
        # ★W1-b — "인근"이라고 부를 수 있는지는 표본이 정한다. 자동 연동 표본이면 그 근거
        #   (`SampleBasis`)로 문구를 만들고, 사용자가 직접 넣은 값이면 출처를 우리가 모르므로
        #   "인근"이라 단정하지 않는다. 종전엔 어느 경우든 "인근 토지 실거래 평균"이라 적었다.
        _sample_label = comparable_basis.label() if comparable_basis else "입력된 거래사례"
        _excluded = comparable_basis.exclusion_note() if comparable_basis else None
        method_cmp = {
            "method": "실거래 비교 추정",
            "unit_price": cmp_unit_price,
            "comparable_avg_per_sqm": int(comparable_avg_per_sqm),
            "comparable_sample": (
                {
                    "scope": comparable_basis.scope,
                    "located_count": comparable_basis.located_count,
                    "unlocated_count": comparable_basis.unlocated_count,
                }
                if comparable_basis
                else None
            ),
            "rationale": (
                f"{_sample_label} 평균 {int(comparable_avg_per_sqm):,}원/㎡"
                f"{' (' + _excluded + ')' if _excluded else ''}"
                f" × 접도 {road_f} × 면적 {area_fac} × 형상 {shape_f}"
            ),
        }

    # ── 3) 결정적 민감도 봉투 — **난수 없음** ──
    # ★★라이브 실측 결함(2026-08-25) — 여기엔 원래 `random.Random(seed)` 가 있었고
    #   `seed = abs(hash(문자열)) % 2**31` 였다. CPython 은 `PYTHONHASHSEED` 미설정 시
    #   str `hash()` 를 **프로세스마다 솔팅**하는데, 프로덕션 168 컨테이너의
    #   `PYTHONHASHSEED` 는 **빈 값**이었다(실측). 결과:
    #     · 같은 필지의 채택단가가 **재시작마다 최대 5.66% 이동**(원문 소스를 실제
    #       hash 시드 40개로 태워 실측). 라이브 논현동 1-1 1,000㎡ = 62.6억 → **약 3.5억원**
    #     · `rough_feasibility_orchestrator:813` 이 이 값을 **수지 토지비**로 쓴다
    #   ★한 프로세스 안에서는 완벽히 결정적이라(라이브 8/8 동일) 반복 호출 테스트는 전부
    #     초록이었다. 그래서 `tests/test_desk_appraisal_determinism.py` 는 **서로 다른
    #     PYTHONHASHSEED 하위프로세스**에서 잰다.
    #
    # 이제 난수 대신 **가정 격자**를 결정적으로 편다. 보여 주는 값의 뜻이 달라졌다 —
    # "5개 법인이 따로 평가했다"가 아니라 **"가정을 흔들면 이만큼 움직인다"**(민감도)이다.
    _OF_STEPS = (-0.05, 0.0, 0.05)      # 그밖의요인 가정 폭
    _W_STEPS = (0.5, 0.6, 0.7)          # 공시지가 경로 가중(거래사례가 있을 때만 의미)

    def _scenario_value(of_delta: float, w: float) -> int:
        pub_i = op * time_adjust * road_f * area_fac * shape_f * (other_factor * (1 + of_delta))
        if cmp_unit_price > 0:
            return int(pub_i * w + cmp_unit_price * (1 - w))
        return int(pub_i)

    if cmp_unit_price > 0:
        _grid = [(of, w) for of in _OF_STEPS for w in _W_STEPS]
    else:
        _grid = [(of, 0.6) for of in _OF_STEPS]   # 가중은 무의미 — 축을 늘리지 않는다
    scenario_vals = sorted({_scenario_value(of, w) for of, w in _grid})
    # ★채택가는 **중심 가정**의 값이다(난수 평균이 아니다).
    central_unit = _scenario_value(0.0, 0.6)
    band_mean = sum(scenario_vals) / len(scenario_vals)
    band_std = (sum((v - band_mean) ** 2 for v in scenario_vals) / len(scenario_vals)) ** 0.5
    cv = band_std / band_mean if band_mean else 0
    cross_check = {
        "firms": scenario_vals,   # ★부채: 키 이름이 아직 `firms` 다(소비처 6파일) — PLAN §5
        "mean": int(band_mean),
        "std": int(band_std),
        "cv_pct": round(cv * 100, 1),
        "min": min(scenario_vals), "max": max(scenario_vals),
        "note": (
            "가정 민감도 — 그밖의요인 ±5%·실거래 가중 0.3~0.5 를 편 결정적 범위입니다. "
            "독립된 평가 주체의 교차검증이 아니라 같은 산식의 가정 변동입니다."
            if cmp_unit_price > 0 else
            "가정 민감도 — 그밖의요인 ±5% 를 편 결정적 범위입니다. 거래사례를 확보하지 못해 "
            "공시지가 기준 경로 하나만 계산했으며, 이는 **교차검증이 아닙니다**."
        ),
    }

    # ── 채택가·신뢰도 ──
    # ★★종전엔 `confidence = max(0.4, 1 - cv*3)` 였다. 그 `cv` 는 **자기가 주입한 난수**의
    #   변동계수라, 데이터 구성이 완전히 달라져도 0.83~0.94 안에 머무는 반면(실측)
    #   **같은 구성에서 프로세스만 바뀌면 0.78~0.98** 로 더 크게 흔들렸다 — 잡음 > 신호.
    #   이제 신뢰도는 **독립 추정이 2개일 때만**, 그 둘의 **실제 불일치**에서 나온다.
    appraised_unit = central_unit
    pub_central = int(op * time_adjust * road_f * area_fac * shape_f * other_factor)
    if cmp_unit_price > 0 and pub_central > 0:
        _gap = abs(pub_central - cmp_unit_price) / max(pub_central, cmp_unit_price)
        confidence: float | None = round(max(0.4, 1 - _gap), 2)
        confidence_basis = (
            f"독립 추정 2개(공시지가기준법 {pub_central:,}원/㎡ · 거래사례비교법 "
            f"{int(cmp_unit_price):,}원/㎡)의 불일치 {_gap * 100:.1f}% → 신뢰도 = 1 − 불일치(하한 0.4)"
        )
    else:
        # ★정답이 '값'이 아니라 '보류'일 수 있다 — 독립 추정 1개는 교차검증이 아니다.
        confidence = None
        confidence_basis = (
            "단일 경로(공시지가기준법)만 산출돼 신뢰도를 보류합니다 — 독립 추정이 1개면 "
            "교차검증이 아닙니다. 주변 거래사례를 확보하면 두 방법의 불일치로 산출합니다."
        )
    weight_note = (
        "공시지가 기준 + 실거래 비교 결합(중심 가정) 채택"
        if method_cmp else
        "공시지가 기준(중심 가정) 채택 — 실거래 확보 시 교차검증 가능"
    )
    appraised_total = int(appraised_unit * area_f) if area_f else None
    # ★± 범위는 **결정적 가정 봉투**에서 나온다(종전엔 주입 잡음에서 나왔다).
    range_low, range_high = min(scenario_vals), max(scenario_vals)

    # ── 토지+건물 복합 추정(건물 입력 시): 토지가치 + 원가법 건물가치 ──
    building = _building_value(building_gfa_sqm, building_structure, building_year_built, base_year + 1)
    complex_total = None
    if building and appraised_total is not None:
        complex_total = appraised_total + building["building_value_won"]

    # ── 수익환원법(임대료 입력 시): 부동산 전체 수익가치(원가법 복합과 병행 제시) ──
    income = _income_value(
        monthly_rent_won, deposit_won, vacancy_rate, opex_ratio, cap_resolved,
        deposit_conv_rate=deposit_conv, cap_source=cap_source, conv_source=conv_source,
    )
    income_total = income["income_value_won"] if income else None
    complex_note = None
    if complex_total is not None and income_total is not None:
        complex_note = (
            f"원가법 복합 {complex_total:,}원 vs 수익환원법 {income_total:,}원 — "
            "수익형은 임대수익 기준, 원가법은 토지+건물 재조달 기준. 용도·임대안정성에 따라 채택."
        )

    # ── 표준 근거 블록(#5): 탁상감정의 채택가·산식·교차검증·법령을 표준 계약으로 가산(graceful). ──
    # 무목업: 실제 산출한 채택 단가/총액·공시지가기준법 산식·교차검증 편차만 트레이스(실값).
    # 법령(verified): 감정평가법 제3조(land_appraisal)·부동산공시법 제10조(official_land_price).
    # build_evidence_block 실패해도 탁상감정 결과는 그대로 반환(가산·정직).
    evidence_block: dict[str, Any] | None = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        ev_items: list[dict[str, Any]] = [
            {
                "label": "채택 단가",
                "value": f"{appraised_unit:,}원/㎡",
                "basis": weight_note,
            },
            {
                "label": "공시지가기준법 단가",
                "value": f"{pub_unit_price:,}원/㎡",
                "basis": method_pub["rationale"],
            },
        ]
        if appraised_total is not None:
            ev_items.append({
                "label": "채택 총액",
                "value": f"{appraised_total:,}원",
                "basis": f"채택 단가 {appraised_unit:,}원/㎡ × 면적 {round(area_f or 0, 1):,}㎡ (참고용 추정, 수정 가능)",
            })
        if method_cmp:
            ev_items.append({
                "label": "거래사례비교법 단가",
                "value": f"{cmp_unit_price:,}원/㎡",
                "basis": method_cmp["rationale"],
            })
        ev_items.append({
            "label": "교차검증 신뢰도" if confidence is not None else "신뢰도(보류)",
            "value": confidence if confidence is not None else "산출 보류",
            # ★근거는 **신뢰도를 실제로 만든 것**을 말한다(종전엔 주입 잡음의 CV 였다).
            "basis": confidence_basis,
        })
        if building:
            ev_items.append({
                "label": "건물가치(원가법)",
                "value": f"{building['building_value_won']:,}원",
                "basis": building["rationale"],
            })
        if income:
            ev_items.append({
                "label": "수익환원법 가치",
                "value": f"{income['income_value_won']:,}원",
                "basis": income["rationale"],
            })
        evidence_block = build_evidence_block(
            items=ev_items,
            legal_ref_keys=["land_appraisal", "official_land_price"],
            sources=["molit_official_price", "vworld_land_info"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 탁상감정 결과를 막지 않음.
        evidence_block = None

    return {
        "ok": True,
        "appraised_price_per_sqm": appraised_unit,
        "appraised_total_won": appraised_total,
        "subject": subject,                              # 대상물건 표시(지목·용도지역·이용상황 등)
        "official_price_per_sqm": int(op),               # 적용 개별공시지가(원/㎡)
        "pnu": pnu,
        "building": building,
        "complex_total_won": complex_total,   # 토지+건물 복합 예상가치(원가법, 건물 입력 시)
        "income": income,                      # 수익환원법(임대료 입력 시)
        "income_total_won": income_total,
        "complex_note": complex_note,
        "area_sqm": round(area_f, 1) if area_f else None,
        "confidence": confidence,
        "range_per_sqm": {"low": range_low, "high": range_high},
        # ★신뢰도를 보류했으면 **사유**를 말한다(무언 보류 금지).
        "confidence_basis": confidence_basis,
        "cross_check": cross_check,
        "irregularity": irregularity,
        "methods": [m for m in (method_pub, method_cmp) if m],
        "weight_note": weight_note,
        # ★W1-b 리뷰(M-2) — 거래사례비교법이 빠진 **사유**. 값이 조용히 사라지면 사용자는
        #   "이 지역엔 거래가 없나 보다"로 오독한다(실제로는 근접성 판정 불가라 안 쓴 것).
        "comparable_skipped_reason": comparable_skip_note,
        # ★★토지 층화 통계 — **참고값**이다. 채택 단가에 넣지 않았다.
        #   토지 실거래는 지번이 100% 마스킹돼 좌표를 만들 수 없어(실측 3지역 30개월
        #   3,113건 전수) 반경으로는 아무 말도 못 한다. 대신 원천이 100% 채워 주는
        #   법정동·용도지역 축으로 "이 동네 이 용도지역의 실거래는 이렇다"를 말한다.
        #   ★값만 주면 "내 땅 시세"로 오독한다 — `note` 가 **개별 필지 위치가 반영되지
        #   않았다**는 것을 같은 자리에서 말한다.
        "land_market_stats": land_dong_stats_out,
        "land_market_stats_note": land_stats_note(land_dong_stats_out, window_months=6),
        "road_side": road_side,
        "source": src,
        "base_year": base_year,
        "time_adjust": round(time_adjust, 4),
        "time_adjust_basis": ta["rationale"],
        "market_stats": market_stats,   # R-ONE 부동산통계(시점수정·cap rate·전환율) 출처 투명화
        "disclaimer": "본 추정치는 「감정평가 및 감정평가사에 관한 법률」상 감정평가가 아니며, "
                      "공시지가·실거래 등 공개데이터에 기반한 참고용 예상 시세 추정입니다. "
                      "법적 효력이 있는 가치 산정은 감정평가법인에 의뢰해야 하며, 본 값은 사용자가 수정할 수 있습니다.",
        # ★표준 근거 블록(#5, 가산) — 채택가 산식·교차검증·법령(verified) 트레이스. 기존 키 무손상.
        "evidence": evidence_block,
    }
