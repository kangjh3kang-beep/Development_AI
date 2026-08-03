"""주변 실거래 지도 데이터 서비스.

대상 지번 중심좌표 + 반경 + 카테고리별(매매6·전월세4) 실거래를 건물단위로
그룹핑·집계하고, 각 건물을 카카오 로컬 지오코딩으로 좌표화하여 지도에 표시할
페이로드를 만든다.

- 실거래: 검증된 MolitClient(apis.data.go.kr/1613000) 재사용
- 지오코딩: 카카오 로컬 API(주소→좌표, 지번·도로명·키워드 모두 처리), Redis 캐시
- 성능: 카테고리별 그룹 상한 + 고유 쿼리 dedupe + 병렬(semaphore) + 7일 캐시
"""

import asyncio
import json
import math
import time
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.core.db_utils import PostGISHelper
from app.services.data_validation.deal_date import parse_deal_date
from app.services.data_validation.price_stats import robust_price_stats
from apps.api.config import get_settings
from apps.api.integrations.molit_client import MolitClient

logger = structlog.get_logger(__name__)

PYEONG_SQM = 3.305785  # 1평 = 3.305785㎡ (프론트 lib/formatters.ts PYEONG_SQM 상수 미러)

_TRADE_TYPES = [
    ("apt", "아파트"),
    ("villa", "연립다세대"),
    ("house", "단독다가구"),
    ("officetel", "오피스텔"),
    ("land", "토지"),
    ("commercial", "상업업무용"),
]
_RENT_TYPES = [
    ("apt", "아파트"),
    ("villa", "연립다세대"),
    ("house", "단독다가구"),
    ("officetel", "오피스텔"),
]

_MAX_GROUPS_PER_CAT = 28  # 카테고리별 마커 상한(건물 수) — 지오코딩 부하·페이로드 축소(40→28)
# 지오코딩 '사전 컷' 상한 — 반경 필터가 캡(28)보다 먼저 돌게 되면서(순서: 지오코딩→필터→캡)
# 지오코딩 대상이 시군구 전체로 커지는 것을 막는 콜드로드 안전판. 최종 캡(28)보다 충분히 넓게.
_MAX_GEOCODE_GROUPS_PER_CAT = 80
_GEOCODE_CONCURRENCY = 12  # 지오코딩 병렬도(6→12) — 첫 로딩 시간 단축

# ── 결과 캐시(프로세스 메모리, TTL) ──
# 같은 지역(주소·lawd_cd·기간)을 재조회하면 MOLIT 수집+지오코딩(수 초)을 건너뛰고 즉시 반환.
# Redis가 degraded여도 동작(인프로세스). 단일 워커 운영이라 적중률 높음.
_BUILD_CACHE: dict[tuple, tuple[float, "dict[str, Any]"]] = {}
_BUILD_CACHE_TTL = 1800.0  # 30분
_BUILD_CACHE_MAX = 128     # 메모리 상한(초과 시 가장 오래된 항목부터 제거)
# VWorld 지오코딩(서버에 키 설정·운영중). 지번주소=PARCEL, 도로명=ROAD.
_VWORLD_GEOCODE_URL = "https://api.vworld.kr/req/address"
# 지오코딩 캐시 TTL(초):
#   - 성공(좌표 확보): 7일 — 좌표는 사실상 불변이라 길게 캐시해 재조회 비용 절감.
#   - 실패/미해결(빈 결과): 5분 — ★일시적 VWorld 무응답·키 누락을 7일간 "빈 좌표"로 고착시키면
#     복구 후에도 지도가 계속 서울 폴백에 갇힌다. 짧게만 캐시해 곧 재시도되게 한다.
_GEOCODE_CACHE_TTL_OK = 604800  # 7일
_GEOCODE_CACHE_TTL_MISS = 300   # 5분

# AVM 신뢰도 소표본 기준 — 이 미만이면 신뢰도에 하드 캡을 걸고 `small_sample` 로 고지한다.
# ★근거: 신뢰도 산식의 표본 항이 log 스케일(`log10(n+1)/2`)이라 표본이 급감해도 거의
#   떨어지지 않고, 표본 1건은 분산이 0이라 분산 항이 만점을 받는다(실측 1건 → 74.5%).
#   값 자체는 참일 수 있으나 "얼마나 믿을 만한가"를 그 숫자가 대변하지 못한다.
#   5는 자의적 상수가 아니라 "분산을 말할 수 있는 최소 표본"의 통상 하한을 택한 것이며,
#   차단이 아니라 **강등 + 고지**이므로 과소경고 쪽으로 안전하다.
_MIN_RELIABLE_DEALS = 5


# 시/도 단축표기(주소 앞머리에 자주 온다) — 접미사 규칙만으로는 못 잡는다.
_SIDO_TOKENS = frozenset({
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
})
_SIGUNGU_SUFFIXES = ("도", "시", "군", "구")
# ★F-1 — `endswith("시")` 는 **시도와 시군구를 구분하지 못한다**. 광역시 축약형이 단일 토큰
#   시군구인 척 통과했다: "서울시 역삼동 736" → "서울시", "부산시 우동 1" → "부산시".
#   특히 **"광주시" 는 광주광역시 축약형과 경기도 광주시(진짜 시군구)가 문자열로 충돌**해
#   광주광역시 주소가 경기 광주시로 해석될 여지가 있다.
#   차단 비용은 경기 광주시 단독 입력이 행 폴백되는 것뿐이고 `sigungu_source` 로 관측된다 —
#   오염 대신 폴백으로 틀리는 쪽이 옳다(C-1·R-1 과 같은 판단).
_SIDO_SHORT_SI = frozenset({"서울시", "부산시", "대구시", "인천시", "광주시", "대전시", "울산시"})


def sigungu_hint_from_address(address: str) -> str:
    """주소 앞머리에서 **시군구 레벨까지** 취한다. 도달 못 하면 빈 문자열.

    ★리뷰 H-3 봉합 — 이 함수는 원래 라우터에만 있었고, `build()` 의 다른 호출부
    (`desk_appraisal_service` · `assistant_agent`)는 힌트를 넘기지 않아 **중개사무소 소재지로
    폴백**했다. 하필 이 진단의 발단인 호미곶 사례가 `desk_appraisal` 경로다 — 라우터만
    고치면 헤드라인 증상이 안 고쳐진다. 생산처(`build`)로 옮겨 세 호출부가 자동으로 따라오게
    한다(CLAUDE.md: 한 곳을 고치면 전역이 따라오게).

    ★시군구 레벨 도달 검사가 핵심이다(리뷰 C-1) — 시·도만 뽑힌 반쪽 힌트를 내보내면,
    그 값이 행의 값을 이겨 전 행에 전파되고 "다른 시군구의 동명 지번"으로 매칭될 수 있다.
    그러면 좌표는 틀렸는데 refined 대조도 통과해 '위치 확인' 도장을 받는다 —
    **무해한 실패를 유해한 성공으로** 바꾼다.
    """
    out: list[str] = []
    for i, tok in enumerate((address or "").split()):
        if tok.endswith(_SIGUNGU_SUFFIXES) or (i == 0 and tok in _SIDO_TOKENS):
            out.append(tok)
            continue
        break
    if not out or not out[-1].endswith(("시", "군", "구")):
        return ""
    # ★리뷰 R-1 — **시·도 없는 자치구 단독**은 판정 불가다. "남구"는 부산·대구·인천·광주·울산·
    #   포항 6곳, "중구"·"동구"·"서구"·"북구"도 전국에 중복된다. 그 반쪽 힌트가 행의 값을 이겨
    #   전 행에 전파되면 질의 "남구 대보리 산1-1" 이 되고, VWorld 가 **다른 광역시의 동명 지번**을
    #   줄 수 있다 — 좌표는 틀렸는데 refined 대조도 통과해(동·지번이 들어 있다) "위치 확인"
    #   도장을 받는다. C-1 과 **정확히 같은 기전**이고 트리거 입력만 좁다.
    #   ★H-3(build 내 도출)이 이 구멍의 노출면을 새로 열었다 — assistant_agent 의 address 는
    #   LLM 이 자연어에서 뽑은 툴 인자고, desk_appraisal 은 pnu 가 있으면 address 를 검증하지
    #   않는다. 종전엔 두 경로가 힌트를 안 썼으므로 무관했다.
    #   단일 토큰은 시 계층(세종특별자치시·광역시 등)만 허용한다. 비용은 "강남구 대치동 316"
    #   같은 입력이 힌트를 잃는 것인데, 그건 **행 폴백(종전 동작)**이고 `sigungu_source` 로
    #   관측된다 — 오염 대신 폴백으로 틀리는 쪽이 옳다.
    if len(out) == 1 and (not out[0].endswith("시") or out[0] in _SIDO_SHORT_SI):
        return ""
    return " ".join(out)


def _dong_tail(value: str | None) -> str:
    """법정동 표기의 **마지막 토큰**만 취한다.

    ★리뷰 H-4 봉합 — MOLIT `umdNm` 은 읍·면 지역에서 `"호미곶면 대보리"` 처럼 **두 토큰**으로
    온다(이 저장소 테스트 픽스처가 그 형태를 쓴다). 그런데 사전컷 프라이어가 완전일치
    비교였다: `"호미곶면 대보리" != "대보리"` → 프라이어가 **한 그룹도 앞당기지 못하고**
    종전 건수 정렬로 조용히 되돌아갔다. 하필 이 PR 의 동기가 된 호미곶이 정확히 그 형태다.
    `_refined_mismatch` 는 이미 같은 규약(`dong.split()[-1]`)을 쓰고 있었다 — 재사용한다.
    """
    v = (value or "").strip()
    return v.split()[-1] if v else ""


class NearbyMapService:
    """주변 실거래 지도 페이로드 생성기."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.molit = MolitClient()
        self._geo_key = getattr(self.settings, "vworld_api_key", "") or ""
        # ★W2 계측 — 지오코딩 실패를 **원인별로** 센다. 종전엔 `continue` 뿐이라 실패가
        #   일시장애(429/5xx/타임아웃 → 재시도로 회복 가능)인지 영구 오류(NOT_FOUND →
        #   주소 자체가 틀림)인지 구분할 수단이 0이었고, 그 위에서 세운 처방은 검증 불가였다.
        self._geo_failures: dict[str, int] = {}
        self._geo_fail_samples: list[str] = []

    def _geo_attempt_fail(self, reason: str) -> None:
        """시도(PARCEL/ROAD) 단위 실패를 전량 집계한다 — 질의 단위 대표사유와 **별개 관점**."""
        try:
            if not hasattr(self, "_geo_attempt_failures"):
                self._geo_attempt_failures = {}
            self._geo_attempt_failures[reason] = self._geo_attempt_failures.get(reason, 0) + 1
        except Exception:  # noqa: BLE001 — 계측이 본로직을 깨지 않는다
            pass

    def _geo_fail(self, reason: str, query: str = "") -> None:
        """지오코딩 실패 1건을 원인별로 적재(예외 안전 — 계측이 본로직을 깨지 않는다).

        ★지연 초기화: 이 저장소의 테스트는 `NearbyMapService.__new__(...)` 로 `__init__` 을
        우회해 인스턴스를 만든다(외부 의존 없이 순수 로직만 태우려는 의도). 계측이 그 경로에서
        AttributeError 를 내면 **계측 때문에 본로직이 죽는다** — 관측 장치의 제1원칙 위반이다.
        """
        try:
            if not hasattr(self, "_geo_failures"):
                self._geo_failures = {}
                self._geo_fail_samples = []
            self._geo_failures[reason] = self._geo_failures.get(reason, 0) + 1
            if query and len(self._geo_fail_samples) < 5:
                self._geo_fail_samples.append(f"{reason}:{query}")
        except Exception:  # noqa: BLE001 — 계측 실패가 응답을 죽이면 안 된다
            pass

    # ── 공개 진입점 ──
    async def build(
        self,
        address: str,
        lawd_cd: str,
        months: int = 3,
        radius_m: int = 1000,
        sigungu_hint: str = "",
        center_hint: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        # center_hint: 라우터가 PNU/좌표 확보 과정(주소 지오코딩·point→parcel)에서 이미 얻은
        #   중심좌표. 여기서 다시 주소 지오코딩이 실패해도 이 힌트로 center를 채워, 지도가
        #   선택 필지 위치로 이동한다(백엔드 지오코딩 실패와 무관하게 서울 폴백 제거).
        # ★리뷰 H-3 — 호출부가 힌트를 안 줘도 **여기서 스스로 도출**한다. 종전엔 라우터만
        #   힌트를 넘겨, desk_appraisal·assistant_agent 경로는 중개사무소 소재지로 폴백했다.
        sigungu_hint = (sigungu_hint or "").strip() or sigungu_hint_from_address(address)
        # 계측은 요청 단위다 — 인스턴스를 재사용하는 소비처가 생겨도 수치가 섞이지 않게 한다.
        self._geo_failures = {}
        self._geo_attempt_failures = {}
        self._geo_fail_samples = []
        hint_lat = (center_hint or {}).get("lat")
        hint_lon = (center_hint or {}).get("lon")
        has_hint = bool(hint_lat and hint_lon)

        # 0) 결과 캐시 조회 — 동일 조건 재조회는 즉시 반환(수 초 → 수 ms)
        cache_key = ((address or "").strip(), f"{lawd_cd}", months, radius_m)
        hit = _BUILD_CACHE.get(cache_key)
        if hit and (time.monotonic() - hit[0]) < _BUILD_CACHE_TTL:
            cached = hit[1]
            # 캐시된 결과에 center가 비어 있고(과거 지오코딩 실패분) 지금은 힌트가 있으면 보강.
            if has_hint and not (cached.get("center") or {}).get("lat"):
                cached = {**cached, "center": {"lat": hint_lat, "lon": hint_lon, "address": address}}
            return cached

        ym_list = self._recent_months(months)

        # 1) 카테고리별 실거래 수집(병렬) + 시도/실패 집계
        trade_res, rent_res = await asyncio.gather(
            self._collect(self.molit.get_transactions, _TRADE_TYPES, lawd_cd, ym_list),
            self._collect(self.molit.get_rent_transactions, _RENT_TYPES, lawd_cd, ym_list),
        )
        trade_raw, t_fail, t_att = trade_res
        rent_raw, r_fail, r_att = rent_res

        # 2) 건물단위 그룹핑
        categories: dict[str, dict[str, Any]] = {}
        for tkey, tlabel in _TRADE_TYPES:
            categories[f"{tkey}_trade"] = self._group_trade(
                tkey, f"{tlabel} 매매", trade_raw.get(tkey, []), sigungu_hint
            )
        for tkey, tlabel in _RENT_TYPES:
            categories[f"{tkey}_rent"] = self._group_rent(
                tkey, f"{tlabel} 전월세", rent_raw.get(tkey, []), sigungu_hint
            )

        # 3) 고유 지오코딩 쿼리 수집 → dedupe → 병렬 지오코딩
        # ★지오코딩 사전 컷(R1 P2): 캡(28)을 반경 필터 뒤로 옮기면서 지오코딩 대상이 시군구
        #   전체 건물로 확대될 수 있다(대형 시군구 콜드로드에서 수백~천 건 → 수십 초 지연·쿼터
        #   소모). 카테고리별 거래건수 상위 _MAX_GEOCODE_GROUPS_PER_CAT 건만 지오코딩 대상으로
        #   사전 컷해 콜드 비용을 상수로 묶는다. 반경 내 상위 28건 정합성은 사전 컷 폭(80)이
        #   최종 캡(28)보다 충분히 넓어 실용상 유지된다. 컷된 그룹 수는 정직 카운트로 노출.
        geocode_precut = 0
        # ★W2 근본수정 — 사전컷 정렬에 **공간 사전확률**을 넣는다.
        #   종전엔 거래건수만으로 상위 80을 남겼다. 그런데 우리가 원하는 건 "많이 팔린 단지"가
        #   아니라 "대상지 **가까이** 있는 물건"이다. 라이브 실측(역삼동): 지오코딩한 520개
        #   그룹 중 **414개(79.6%)가 반경 밖으로 폐기**됐다 — 지오코딩 예산의 80%를 버릴
        #   후보에 썼다. 게다가 사전컷 자체가 전체 그룹 손실의 **73.8%**(1,629/2,207)로
        #   지오코딩 실패(2.6%)보다 28배 크다.
        #   대상지 법정동은 주소에서 **이미 알고 있다** — 추가 호출 0으로 같은 예산에서
        #   수율을 올린다. 동이 같은 그룹을 앞에 두고, 그 안에서 거래 많은 순으로 자른다.
        target_dong = self._dong_from_address(address)
        for cat in categories.values():
            if len(cat["groups"]) > _MAX_GEOCODE_GROUPS_PER_CAT:
                cat["groups"].sort(
                    key=lambda x: (
                        0 if (target_dong and _dong_tail(x.get("dong")) == target_dong) else 1,
                        -x["count"],
                    )
                )
                geocode_precut += len(cat["groups"]) - _MAX_GEOCODE_GROUPS_PER_CAT
                cat["groups"] = cat["groups"][:_MAX_GEOCODE_GROUPS_PER_CAT]
        queries: set[str] = set()
        for cat in categories.values():
            for grp in cat["groups"]:
                queries.add(grp["_query"])
        coords = await self._geocode_many(sorted(queries))
        # ★리뷰 R-5 — 샘플을 수집만 하고 아무도 읽지 않으면 관측 장치를 넣고 관측구를 안 뚫은
        #   것이다. 프로덕션에서 "어떤 주소가 왜 깨지는지" 눈으로 보게 한다(이번 진단의 결정타가
        #   실패 쿼리의 시군구를 본 것이었다). 질의는 MOLIT 공개 물건 주소라 개인정보가 아니다.
        if getattr(self, "_geo_failures", None):
            logger.info(
                "지오코딩 실패 분해",
                breakdown=dict(self._geo_failures),
                samples=list(self._geo_fail_samples),
                queries=len(queries),
            )

        # 4) 중심좌표 확보: (1) 이미 지오코딩된 주소 좌표 → (2) 주소 재지오코딩 → (3) 라우터 힌트.
        #   ★(3) 힌트가 있으면 자체 지오코딩이 실패해도 center가 null로 남지 않는다(서울 폴백 방지).
        center = coords.get(address.strip()) or await self._geocode_one(address.strip())
        if not center and has_hint:
            center = {"lat": hint_lat, "lon": hint_lon, "address": address}
        center_lat = (center or {}).get("lat")
        center_lon = (center or {}).get("lon")
        # 반경 필터는 중심좌표와 radius_m 이 모두 있어야 의미가 있다. 중심좌표가 없으면
        # (지오코딩 전면 실패 + 힌트도 없음) radius_m 은 여전히 "요청값"으로만 에코되고
        # 실제 필터링은 하지 않는다 — 그 사실을 radius_applied=False 로 정직 표기한다.
        radius_applied = bool(center_lat and center_lon and radius_m)

        # 5) 좌표 주입 + 반경 필터(★실구현 — 종전엔 radius_m 을 필터에 전혀 쓰지 않고
        #    result["radius_m"]에 요청값을 에코만 해 라벨이 거짓이었다) + 좌표 미확보 그룹 보존
        #    (반경 밖으로 단정하지 않는다 — 무날조) + 상한(_MAX_GROUPS_PER_CAT)은 반경 필터
        #    이후에 적용한다(순서: 지오코딩 → 반경 필터 → 캡).
        groups_evaluated = 0   # 좌표 확보 후 반경 판정 대상이 된 그룹 수(필터 "전")
        filtered_out = 0       # 반경 밖으로 제외된 그룹 수
        coords_unresolved = 0  # 좌표 미확보로 반경 판정 자체가 불가능했던 그룹 수(보존)
        for cat in categories.values():
            resolved: list[dict] = []
            unresolved: list[dict] = []
            for grp in cat["groups"]:
                c = coords.get(grp.pop("_query"))
                if not c:
                    # 좌표 미확보 — 제외하지 않고 보존한다(반경 밖 단정 금지). 지도 마커로는
                    # 못 찍지만(lat/lon 없음), 실거래 데이터 자체는 응답에 남는다.
                    unresolved.append(grp)
                    continue
                grp["lat"], grp["lon"] = c["lat"], c["lon"]
                # ★W1-b 리뷰(H-3) 봉합 — 정밀도를 **질의 형태**가 아니라 **매칭 결과**로 최종
                #   확정한다. 질의만 보면 "지번이 들어갔으니 parcel"이라고 추정하게 되는데,
                #   `sigungu` 가 결측이거나(중개사무소 소재지에서 오므로 자주 빈다) 힌트가
                #   시군구가 아닌 값이면 VWorld 가 **다른 시군구의 동명 지번**을 돌려줄 수 있다.
                #   그때 좌표는 완전히 틀린데 정밀도는 parcel 이라 라벨이 그것을 승인해버린다.
                #   refined(매칭 주소)에 이 그룹의 법정동·지번이 실제로 들어있는지 대조해
                #   불일치면 강등한다. refined 가 없으면(구 캐시) 판정을 바꾸지 않는다.
                if self._refined_mismatch(grp, c.get("refined")):
                    grp["coord_precision"] = "dong"
                resolved.append(grp)
            coords_unresolved += len(unresolved)

            if radius_applied:
                groups_evaluated += len(resolved)
                in_radius = []
                for grp in resolved:
                    dist_km = PostGISHelper.st_distance(center_lat, center_lon, grp["lat"], grp["lon"])
                    if dist_km * 1000.0 <= radius_m:
                        in_radius.append(grp)
                filtered_out += len(resolved) - len(in_radius)
                resolved = in_radius

            # 거래 많은 순 정렬 후 상한 — ★반경 필터 이후에 캡을 적용해야 "반경 내 상위 N건"이
            # 된다(캡을 필터보다 먼저 적용하면 시군구 전체 상위 N건이 되어 radius_m 이 무의미).
            # ★W1-b 리뷰(H-1) 봉합 — 정렬 키에 **정밀도를 1순위**로 넣는다.
            #   종전엔 거래건수만으로 정렬해 상위 28을 자른 뒤 그 안에서 정밀도를 갈랐다.
            #   그래서 상위 28이 전부 동 대표점이면 29위의 지번 그룹이 **반경 안에 있어도**
            #   통째로 사라지고 `located_count=0` 이 된다 → 화면은 "반경 1km 내 위치 확인
            #   거래를 찾지 못했습니다"라고 말한다. 오염과 **정반대 방향의 거짓 진술**이며,
            #   토지 매매(동 폴백이 흔하고 건수도 크다)가 정확히 이 순서에 노출된다.
            #   (리뷰어 실측: 반경 안 지번 그룹 5개가 있는데 located_count=0)
            _precise_first = {"parcel": 0, "building": 0}
            resolved.sort(
                key=lambda x: (_precise_first.get(x.get("coord_precision"), 1), -x["count"])
            )
            capped = resolved[:_MAX_GROUPS_PER_CAT]
            # ★절단 정직 고지: 캡(28)에 걸려 응답에서 빠진 그룹 수를 카테고리별로 센다.
            #   종전엔 이 절단을 아무도 세지 않아 프론트가 "다 보여준다"고 오인할 여지가 있었다
            #   (geocode_precut_count·radius_filtered_out_count와 동일한 정직 원칙 — #459 계보).
            #   ★W1-b 리뷰(H-4): `sample_basis` 의 다른 카운트는 전부 **거래 건수**인데 이것만
            #   그룹 수였다. 같은 dict·같은 문장에서 단위가 섞여 "표시 상한 초과 7건"이라고
            #   써놓고 실제로는 15건이 잘린 상태가 나왔다(evidence 는 verified 만 원칙 위반).
            #   그룹 수는 이름을 분리해 보존하고, 라벨이 쓰는 값은 건수로 준다.
            _dropped = resolved[_MAX_GROUPS_PER_CAT:]
            cat["capped_count"] = sum(g["count"] for g in _dropped)
            cat["capped_group_count"] = len(_dropped)
            # ★W1-b — 그룹마다 "이 그룹이 위치 판정을 통과했는가"를 **명시 필드**로 박는다.
            #   종전엔 `lat is None` 으로 소비처가 **추론**해야 했고, 그 추론을 안 한 소비처가
            #   전부 오염됐다(시장분석 헤드라인 평균가·탁상감정 거래사례·AI비서 프롬프트·
            #   대화형 시장분석). 추론 대신 계약으로 바꿔야 감사 규칙도 판정할 수 있다.
            #   ★배열을 `groups_located`/`groups_unlocated`로 **쪼개지 않는** 이유: 혼합
            #   `groups`를 남긴 채 분리 배열을 병기하면 같은 그룹이 JSON에 두 번 실려 응답이
            #   정확히 2배가 된다(암사동 실측 286KB → 약 570KB). 플래그는 +3.5%면 끝난다.
            #   혼합 배열 제거는 소비처가 전부 셀렉터로 이전한 뒤에 한다(그때는 복제가 없다).
            #   ★★그리고 좌표가 있다고 다 같은 좌표가 아니다. `coord_precision == "dong"` 인
            #   그룹은 법정동 대표점이거나 여러 동이 병합된 것이라, 그 점으로 반경 안팎을
            #   통과시켜도 **그룹 자체가 반경 안이라는 보장이 없다**. 이걸 "located"로 부르면
            #   호미곶과 같은 클래스의 오염이 이번엔 "위치 확인" 도장을 받고 나간다 —
            #   `lat is not None` 검사로는 절대 안 걸리는 종류라 더 나쁘다.
            precise = [g for g in capped if g.get("coord_precision") != "dong"]
            approximate = [g for g in capped if g.get("coord_precision") == "dong"]
            for _g in precise:
                _g["location_status"] = "located"
            for _g in approximate:
                _g["location_status"] = "approximate"
            for _g in unresolved:
                _g["location_status"] = "unlocated"
            cat["groups"] = capped + unresolved
            cat["count"] = sum(g["count"] for g in cat["groups"])
            # ★근본수정(P0) — 반경을 **실제로 통과한** 그룹을 따로 보관한다.
            #   종전엔 `capped + unresolved`를 한 리스트로만 내보내 소비처가 둘을 구분할 수
            #   없었고, 그 결과 AVM이 **반경 판정을 받은 적도 없는** 그룹으로 계산됐다
            #   (호미곶 실측: 반경 통과 0건인데 AVM 표본 32건 — 전부 좌표미확보분).
            #   ★W1-b 강화 — AVM 도 **정밀 좌표분만** 쓴다. `avm_caveat` 문구가 스스로
            #   "반경 N 안에서 **위치가 확인된**"이라고 주장하므로, 동 대표점·다동 병합
            #   그룹을 넣으면 그 문장이 거짓이 된다(W1이 프론트에서 봉합한 것과 동일 결함).
            cat["_in_radius_groups"] = precise
            # 카운트도 분리 노출한다. 하나로 합치면 프론트가 "반경 내 N건"으로 오독한다.
            #   ★`count_in_radius` 는 **정밀 좌표분**만 센다 — 이 이름으로 소비되는 곳이
            #   전부 "반경 안이라고 말해도 되는 건수"를 원하기 때문이다.
            cat["count_in_radius"] = sum(g["count"] for g in precise)
            cat["count_approximate"] = sum(g["count"] for g in approximate)
            cat["count_unresolved"] = sum(g["count"] for g in unresolved)
            # ★W1-b — 집계값에 붙일 **라벨의 근거**를 카테고리마다 실어 보낸다.
            #   소비처가 "반경 N km"라고 쓰려면 그 주장이 참인지 알아야 하는데, 종전엔
            #   판단 재료가 최상위에만 있어(`radius_applied`) 카테고리 단위 소비처가
            #   요청 radius_m 을 그대로 에코해 라벨을 지어냈다. scope 가 "sigungu"면
            #   어떤 소비처도 반경 문구를 만들 수 없다 — 라벨 생성의 단일 근거다.
            cat["sample_basis"] = {
                "scope": "radius" if radius_applied else "sigungu",
                "radius_applied": radius_applied,
                # 반경을 실제로 적용하지 않았으면 숫자를 주지 않는다(주면 또 에코된다).
                "radius_m": radius_m if radius_applied else None,
                "located_count": cat["count_in_radius"],
                # 좌표는 있으나 동 입도라 반경 안팎을 단정할 수 없는 분. 집계에서 빼되
                # "없는 것"처럼 감추지 않는다 — 사용자가 표본이 왜 얇은지 알아야 한다.
                "approximate_count": cat["count_approximate"],
                "unlocated_count": cat["count_unresolved"],
                "capped_count": cat["capped_count"],
            }

        # ★내부 전용 필드 정리 — `_in_radius_groups`는 AVM 계산용이고 그대로 두면 응답
        #   페이로드가 그룹만큼 중복된다(대형 시군구에서 수 MB). 소비 후 제거한다.
        avm_summary = self._compute_avm_summary(
            categories.get("apt_trade"), radius_applied=radius_applied, radius_m=radius_m,
        )
        avm_caveat = self._avm_caveat(
            categories.get("apt_trade"), radius_applied=radius_applied, radius_m=radius_m,
        )
        # ★계약 불변식(R3-MED-2) — **거래가 있는데 시세도 없고 사유도 없는** 상태를 봉인한다.
        #   `_compute_avm_summary`와 `_avm_caveat`은 서로를 모른 채 독립 계산하므로,
        #   예컨대 반경 통과 그룹은 있는데 그 그룹의 가격·면적이 전부 결측이면
        #   전자는 None, 후자도 None이 되어 화면이 다시 "실거래가 없어 추정 불가"라는
        #   **거짓 문장**을 낸다(거래는 있는데). 이 모순은 R1→R2→R3에서 **세 번 다른 경로로**
        #   나왔다 — 개별 분기를 땜질하지 말고 여기서 한 번에 막는다.
        _apt = categories.get("apt_trade") or {}
        if avm_summary is None and (_apt.get("groups") or []) and not avm_caveat:
            avm_caveat = (
                "수집된 아파트 실거래는 있으나 가격·면적 정보가 부족해 시세를 산정하지 "
                "못했습니다(거래가 없는 것이 아닙니다)."
            )
        for _cat in categories.values():
            _cat.pop("_in_radius_groups", None)

        result: dict[str, Any] = {
            "center": center or {"lat": None, "lon": None, "address": address},
            "radius_m": radius_m,
            # ★프론트 라벨 연동용 additive 필드 — 반경 필터가 실제로 적용됐는지와 그 전/후 카운트.
            "radius_applied": radius_applied,
            "groups_evaluated_count": groups_evaluated,
            "radius_filtered_out_count": filtered_out,
            "coords_unresolved_count": coords_unresolved,
            # ★W2 계측 — "좌표를 못 얻었다"만으로는 무엇을 고쳐야 할지 알 수 없다.
            #   원인별 분해가 있어야 재시도(일시장애)와 주소 교정(영구 오류) 중 무엇이
            #   지렛대인지 **숫자로** 판정할 수 있다.
            "geocode_failure_breakdown": dict(getattr(self, "_geo_failures", {})),
            # ★F-3 — 질의 단위(위)와 **시도 단위**(아래)를 병기한다. 재시도 착수 판정은
            #   두 숫자를 대조해서 내려야 한다(한쪽만 보면 반대 방향으로 가려진다).
            "geocode_attempt_breakdown": dict(getattr(self, "_geo_attempt_failures", {})),
            # ★분모가 없으면 "비중"을 계산할 수 없다 — breakdown 만으로는 판정 불가였다.
            "geocode_attempted_count": len(queries),
            # ★리뷰 M-1 — 이번 PR 이 새로 넣은 변수(힌트)도 관측 대상이다. 힌트가 비면
            #   전 행이 조용히 중개사 시군구로 회귀하는데, 응답만 봐서는 구분이 안 됐다.
            "sigungu_hint": sigungu_hint,
            "sigungu_source": "hint" if sigungu_hint else "row_fallback",
            "geocode_precut_count": geocode_precut,
            "lawd_cd": lawd_cd,
            "months": ym_list,
            "categories": categories,
            # ★AVM SSOT 일원화(PropAI#3): 아파트 매매 실거래 그룹(반경 필터·캡 적용 후,
            #   위 categories와 동일 객체) 통계로 AI 시세를 계산해 함께 싣는다 — 프론트가
            #   같은 payload를 재가공(평당가 가중평균+CV)하던 것을 여기로 이동(SSOT).
            # ★근본수정(P0): AVM은 **반경을 통과한 그룹만**으로 계산한다. 통과분이 없으면
            #   시세를 만들지 않고 사유를 말한다(무날조 — 기존 "표본 0건이면 None" 원칙을
            #   반경 기준으로 확장). 종전엔 위치를 모르는 원거리 아파트로 임야 시세를 냈다.
            "avm": avm_summary,
            # ★AVM **신뢰성 단서**(additive) — 없으면 None.
            #   ★R2 HIGH-1 교훈: 종전 이름 `avm_unavailable_reason`은 "AVM이 **없을** 때의
            #   사유"라는 **잘못된 멘탈모델을 인코딩**했고, 그 탓에 프론트 배선이 자연스럽게
            #   빈 상태 가지로만 갔다. 그런데 가장 위험한 단서(반경 필터 미적용)는 **AVM이
            #   존재할 때** 붙는다 — 즉 경고가 구조적으로 도달 불가능해졌다.
            #   이름이 곧 계약이다: 이 필드는 **AVM 유무와 무관하게** 붙을 수 있고,
            #   소비처는 **두 경우 모두** 표시해야 한다.
            "avm_caveat": avm_caveat,
            # 구 이름 호환(같은 값) — 외부 소비처가 있을 수 있어 한 릴리스 유지.
            "avm_unavailable_reason": avm_caveat,
        }

        # ★정직 표기: 공공데이터 조회 실패와 "거래 0건(실제 없음)"을 구분한다.
        #   - 전건 실패 = 국토부 실거래 API 무응답/서킷OPEN → data_source=unavailable(빈 표시는 거짓).
        #   - 일부 실패 = 표시 건수가 일부일 수 있음.
        total_att = t_att + r_att
        total_fail = t_fail + r_fail
        fetch_failed = total_att > 0 and total_fail >= total_att
        if fetch_failed:
            result["data_source"] = "unavailable"
            result["fetch_failed"] = True
            result["note"] = (
                "국토부 실거래 공공데이터가 응답하지 않습니다(데이터포털 지연·점검 추정). "
                "거래가 없는 것이 아니라 일시적 조회 실패이며, 잠시 후 다시 시도해 주세요."
            )
        else:
            result["data_source"] = "molit_live"
            if total_fail > 0:
                result["partial_failed"] = True
                result["note"] = (
                    "일부 유형의 실거래 데이터를 불러오지 못했습니다(공공데이터 응답 지연). "
                    "표시된 건수는 일부일 수 있습니다."
                )

        # 결과 캐시 저장(+ 상한 초과 시 가장 오래된 항목 제거).
        # ★실패 결과는 캐싱하지 않는다 — 복구 후에도 TTL 동안 거짓 빈값이 고정되는 것 방지.
        if not fetch_failed:
            _BUILD_CACHE[cache_key] = (time.monotonic(), result)
            if len(_BUILD_CACHE) > _BUILD_CACHE_MAX:
                oldest = min(_BUILD_CACHE, key=lambda k: _BUILD_CACHE[k][0])
                _BUILD_CACHE.pop(oldest, None)
        return result

    # ── 수집 ──
    @staticmethod
    def _recent_months(months: int) -> list[str]:
        # 현재월은 신고지연으로 데이터가 거의 없음 → 직전월부터 수집
        now = datetime.now()
        y, m = now.year, now.month
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        out = []
        for _ in range(months):
            out.append(f"{y}{m:02d}")
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return out

    async def _collect(self, fetch, types, lawd_cd, ym_list) -> tuple[dict[str, list], int, int]:
        # 호출 시도/실패 수를 함께 집계한다. MOLIT 클라이언트는 타임아웃·서킷OPEN 시
        # ExternalServiceError 를 던지므로(그것이 여기 except 로 옴), 이를 세어
        # "거래 0건(실제 없음)" 과 "공공데이터 조회 실패(빈 표시는 거짓)" 를 구분한다.
        stats = {"fail": 0, "attempt": 0}

        async def one(pt: str) -> tuple[str, list]:
            rows: list = []
            for ym in ym_list:
                stats["attempt"] += 1
                try:
                    rows.extend(await fetch(lawd_cd, ym, prop_type=pt, num_rows=1000))
                except Exception as e:  # noqa: BLE001
                    stats["fail"] += 1
                    logger.debug("실거래 수집 실패", pt=pt, ym=ym, err=str(e)[:60])
            return pt, rows

        results = await asyncio.gather(*[one(pt) for pt, _ in types])
        return dict(results), stats["fail"], stats["attempt"]

    # ── 그룹핑 ──
    def _query_for(self, sigungu: str, dong: str, jibun: str, name: str) -> str:
        sgg = (sigungu or "").strip()
        if jibun:
            return f"{sgg} {dong} {jibun}".strip()
        if name:
            # ★W1-b 리뷰(H-3) — 종전엔 `f"{dong} {name}"` 이라 **시군구가 없었다**. 같은 동명이
            #   전국에 흔해(역삼동·중앙동 등) VWorld 가 다른 시군구의 동명 단지로 매칭할 수
            #   있고, 그러면 좌표가 완전히 틀린 채 정밀도만 building 으로 남는다.
            return f"{sgg} {dong} {name}".strip()
        return f"{sgg} {dong}".strip()

    @staticmethod
    def _dong_from_address(address: str) -> str:
        """주소에서 **법정동 토큰**을 뽑는다(사전컷 우선순위용).

        MOLIT 의 `dong` 은 `umdNm`(법정동명)이므로 같은 표기를 골라야 한다:
          "서울특별시 강남구 역삼동 736"            → "역삼동"
          "경상북도 포항시 남구 호미곶면 대보리 산1-1" → "대보리"
        지번 앞에서 마지막으로 나오는 동/리/가 토큰이 법정동이다. 못 찾으면 빈 문자열 —
        그때는 종전처럼 거래건수 순으로만 자른다(추측해서 엉뚱한 동을 우대하지 않는다).
        """
        best = ""
        for tok in (address or "").split():
            if tok.endswith(("동", "리", "가")) and not tok.endswith(("로", "길")):
                best = tok
        return best

    @staticmethod
    def _refined_mismatch(grp: dict[str, Any], refined: str | None) -> bool:
        """지오코딩이 **엉뚱한 주소로 매칭됐는지** 판정한다(정밀도 강등 트리거).

        VWorld 는 질의를 관대하게 해석한다 — `sigungu` 가 빠진 `"대보리 산1-1"` 같은 질의는
        전국의 동명 지번 중 하나로 매칭될 수 있다. 좌표는 정상적으로 돌아오므로 `lat` 검사는
        물론이고 질의 형태 기반 정밀도 판정도 이 오매칭을 **구조적으로 못 잡는다**.

        판정: 그룹이 아는 법정동·지번이 매칭 주소 문자열에 실제로 들어있는가.
        - `refined` 가 없으면(구 캐시 엔트리) **판정하지 않는다**(False) — 모르는 것을 근거로
          강등하면 그것도 날조다. 캐시가 돌면 자연히 해소된다.
        - 법정동은 마지막 토큰만 본다(`"호미곶면 대보리"` → `"대보리"`) — 행정 표기가
          `"경북 포항시 남구 호미곶면 대보리"` 처럼 앞부분이 달라지는 경우가 흔하다.
        """
        if not refined:
            return False
        dong = (grp.get("dong") or "").strip()
        jibun = (grp.get("jibun") or "").strip()
        if dong:
            tail = dong.split()[-1]
            if tail and tail not in refined:
                return True
        if jibun and jibun not in refined:
            return True
        return False

    @staticmethod
    def _query_grain(jibun: str, name: str) -> str:
        """`_query_for` 가 만든 질의가 **어느 입도**를 가리키는지. 좌표의 의미가 여기서 갈린다.

        ★이 구분이 없으면 "좌표가 있다"를 "이 그룹이 어디인지 안다"로 착각한다.
        지번·건물명 질의는 **그 물건**을 가리키지만, 마지막 폴백(`시군구 동`)은 VWorld 가
        **법정동 대표점**을 준다 — 동 전체를 한 점으로 뭉갠 좌표라 반경 안팎 판정에 쓸 수 없다
        (토지 매매는 건물명이 없어 이 폴백에 자주 걸린다).
        """
        if jibun:
            return "jibun"
        if name:
            return "name"
        return "dong"

    def _group_trade(self, type_key, label, rows, sigungu_hint) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for r in rows:
            name = (r.get("building_name") or "").strip()
            jibun = (r.get("jibun") or "").strip()
            dong = (r.get("dong") or "").strip()
            # ★W2 근본수정 — 우선순위를 뒤집는다. `r["sigungu"]` 는 MOLIT 매매 응답의
            #   `estateAgentSggNm`, 즉 **중개사무소 소재지**이지 물건 소재지가 아니다
            #   (molit_client.py 매매 파서). 강남 물건을 서초 중개사가 거래하면 질의가
            #   "서초구 대치동 316" 이 되어 **영구 NOT_FOUND** 다(실측 확증: 시군구를 바꾸면
            #   VWorld 가 정확히 실패한다).
            #   ★자연실험 — 같은 지오코더·같은 질의 빌더인데 전월세만 성공률이 압도적이었다:
            #     apt_rent(sggNm 폴백 있음) located 93/93(100%) vs apt_trade(중개사 단독) 18/105(17%).
            #     파이프라인 전체에서 코드 차이는 시군구 출처 한 곳뿐이었다.
            #   MOLIT 은 우리가 넘긴 `lawd_cd` 로 조회되므로 **대상지 시군구가 곧 모든 행의
            #   시군구**다 — 추측할 필요조차 없이 요청 파라미터로 이미 확정돼 있다.
            sigungu = (sigungu_hint or r.get("sigungu") or "").strip()
            key = name or jibun or dong
            if not key:
                continue
            g = groups.setdefault(key, {
                "name": name or (f"{dong} {jibun}".strip() or "물건"),
                "dong": dong, "jibun": jibun,
                "_query": self._query_for(sigungu, dong, jibun, name),
                # ★실무 판단정보(그룹 대표값) — molit_client가 이미 파싱해 넘기는 build_year/
                #   jimok/land_use(토지 매매 전용)를 종전엔 여기서 폐기했다. 관측된 고유값을
                #   집합으로 모아두고(대표값 확정은 _finalize에서 — 혼재 검출을 위해), 원천에
                #   없으면 빈 채로 남는다(무날조).
                "_build_years": set(), "_jimoks": set(), "_land_uses": set(),
                # ★W1-b — 좌표의 **의미**를 판정할 재료. 그룹 키가 `name or jibun or dong`
                #   이라 같은 건물명이 여러 법정동에 있으면 한 그룹으로 병합되는데, 좌표는
                #   위 `_query`(첫 행 기준) 하나뿐이다. 병합이 일어났는데 그 좌표로 반경
                #   안팎을 판정하면 다른 동의 거래까지 "반경 내"가 된다 — 좌표가 있으니
                #   `lat is not None` 검사로는 절대 걸러지지 않는 종류의 오염이다.
                "_query_grain": self._query_grain(jibun, name),
                "_dongs": set(),
                "deals": [], "_prices": [], "_areas": [],
            })
            # ★W1-b 리뷰(H-3) — 빈 dong 도 **센티널로 기록**한다. 종전엔 빈 값을 그냥 건너뛰어,
            #   "법정동을 모르는 행"이 섞여도 `_dongs` 크기가 1로 남아 정밀 좌표로 분류됐다.
            #   동을 모르는 행이 섞인 것과 여러 동이 섞인 것은 **같은 위험**이다(그룹 대표
            #   좌표가 일부 행만 대표한다).
            g["_dongs"].add(dong)
            price = int(r.get("price_10k_won") or 0)
            area = float(r.get("area_m2") or 0)
            if price > 0:
                g["_prices"].append(price)
            if area > 0:
                g["_areas"].append(area)
            if r.get("build_year"):
                g["_build_years"].add(r.get("build_year"))
            jimok_v = (r.get("jimok") or "").strip()
            if jimok_v:
                g["_jimoks"].add(jimok_v)
            land_use_v = (r.get("land_use") or "").strip()
            if land_use_v:
                g["_land_uses"].add(land_use_v)
            g["deals"].append({
                "price_10k_won": price, "area_m2": area,
                "floor": r.get("floor"), "deal_date": r.get("deal_date"),
            })
        return self._finalize(type_key, label, "trade", groups)

    def _group_rent(self, type_key, label, rows, sigungu_hint) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for r in rows:
            name = (r.get("building_name") or "").strip()
            jibun = (r.get("jibun") or "").strip()
            dong = (r.get("dong") or "").strip()
            # ★W2 근본수정 — 우선순위를 뒤집는다. `r["sigungu"]` 는 MOLIT 매매 응답의
            #   `estateAgentSggNm`, 즉 **중개사무소 소재지**이지 물건 소재지가 아니다
            #   (molit_client.py 매매 파서). 강남 물건을 서초 중개사가 거래하면 질의가
            #   "서초구 대치동 316" 이 되어 **영구 NOT_FOUND** 다(실측 확증: 시군구를 바꾸면
            #   VWorld 가 정확히 실패한다).
            #   ★자연실험 — 같은 지오코더·같은 질의 빌더인데 전월세만 성공률이 압도적이었다:
            #     apt_rent(sggNm 폴백 있음) located 93/93(100%) vs apt_trade(중개사 단독) 18/105(17%).
            #     파이프라인 전체에서 코드 차이는 시군구 출처 한 곳뿐이었다.
            #   MOLIT 은 우리가 넘긴 `lawd_cd` 로 조회되므로 **대상지 시군구가 곧 모든 행의
            #   시군구**다 — 추측할 필요조차 없이 요청 파라미터로 이미 확정돼 있다.
            sigungu = (sigungu_hint or r.get("sigungu") or "").strip()
            key = name or jibun or dong
            if not key:
                continue
            g = groups.setdefault(key, {
                "name": name or (f"{dong} {jibun}".strip() or "물건"),
                "dong": dong, "jibun": jibun,
                "_query": self._query_for(sigungu, dong, jibun, name),
                # ★W1-b — 매매(_group_trade)와 동일한 좌표 정밀도 재료. 전월세도 같은 그룹핑
                #   규칙을 쓰므로 같은 병합 오염에 노출된다(한쪽만 고치면 비대칭이 남는다).
                "_query_grain": self._query_grain(jibun, name),
                "_dongs": set(),
                "deals": [], "_deposits": [], "_monthlies": [], "_areas": [],
            })
            # ★W1-b 리뷰(H-3) — 빈 dong 도 **센티널로 기록**한다. 종전엔 빈 값을 그냥 건너뛰어,
            #   "법정동을 모르는 행"이 섞여도 `_dongs` 크기가 1로 남아 정밀 좌표로 분류됐다.
            #   동을 모르는 행이 섞인 것과 여러 동이 섞인 것은 **같은 위험**이다(그룹 대표
            #   좌표가 일부 행만 대표한다).
            g["_dongs"].add(dong)
            dep = int(r.get("deposit_10k_won") or 0)
            mon = int(r.get("monthly_rent_10k_won") or 0)
            area = float(r.get("area_m2") or 0)
            if dep > 0:
                g["_deposits"].append(dep)
            if mon > 0:
                g["_monthlies"].append(mon)
            if area > 0:
                g["_areas"].append(area)
            g["deals"].append({
                "deposit_10k_won": dep, "monthly_rent_10k_won": mon,
                "area_m2": area, "floor": r.get("floor"), "deal_date": r.get("deal_date"),
            })
        return self._finalize(type_key, label, "rent", groups)

    def _finalize(self, type_key, label, kind, groups) -> dict[str, Any]:
        out = []
        for g in groups.values():
            cnt = len(g["deals"])
            areas = g.pop("_areas", [])
            g["count"] = cnt
            g["avg_area_m2"] = round(sum(areas) / len(areas), 1) if areas else 0
            # ★대표값 혼재 완화(R1 후속 — 레인G R2 항목3): 그룹 키가 건물명·지번 없이 법정동
            #   (dong)으로만 폴백되면 서로 다른 필지의 거래가 한 그룹에 섞일 수 있다(주로 토지
            #   매매에서 건물명이 없는 행). 이 경우 build_year/jimok/land_use "첫 값"만 대표로
            #   보이면 실제로는 여러 필지가 섞였는데 그중 하나의 속성만 그룹 전체인 것처럼
            #   오도한다 — 지목·용도지역은 개발 판단에 직결되는 정보라 피해가 크다.
            #   무음 위험 비교: (a)혼재 시 미표기(None)는 "정보 없음"으로만 보이는 결측 —
            #   기존 age_status 무자료 패턴과 동일한 안전한 실패 모드. (b)"대표 필지 기준"
            #   캡션 부기는 사용자가 캡션을 놓치면 그룹 전체 속성으로 오인하는 정보 왜곡
            #   실패 모드라 더 위험하다. 따라서 (a) 미표기를 채택 — 고유값이 정확히 1개일
            #   때만 대표값을 확정하고, 0개(무자료) 또는 2개 이상(혼재)이면 None.
            build_years = g.pop("_build_years", set())
            jimoks = g.pop("_jimoks", set())
            land_uses = g.pop("_land_uses", set())
            g["build_year"] = next(iter(build_years)) if len(build_years) == 1 else None
            g["jimok"] = next(iter(jimoks)) if len(jimoks) == 1 else None
            g["land_use"] = next(iter(land_uses)) if len(land_uses) == 1 else None
            # ★W1-b — 이 그룹의 좌표가 **무엇을 가리키는지**를 공개 계약으로 박는다.
            #   위 build_year/jimok 혼재 처리와 정확히 같은 논리를 좌표에 적용한 것이다:
            #   여러 법정동이 한 키로 병합됐는데 좌표는 첫 행 하나뿐이면, 그 좌표는 그룹을
            #   대표하지 않는다. 그런데 `lat` 은 멀쩡히 채워지므로 좌표 유무 검사로는
            #   영원히 안 걸린다 — 반경 판정을 "통과"하고 라벨이 그것을 승인해버린다.
            #     parcel  : 지번 질의 — 그 필지를 가리킨다. 반경 판정에 쓸 수 있다.
            #     building: 건물명 질의 — 그 단지를 가리킨다. 반경 판정에 쓸 수 있다.
            #     dong    : 법정동 대표점 폴백이거나 **여러 동이 병합**된 그룹. 동 전체를
            #               한 점으로 뭉갠 좌표라 반경 안팎을 단정할 수 없다.
            _dongs = g.pop("_dongs", set())
            _grain = g.pop("_query_grain", "dong")
            if len(_dongs) > 1:
                g["coord_precision"] = "dong"
            elif _grain == "jibun":
                g["coord_precision"] = "parcel"
            elif _grain == "name":
                g["coord_precision"] = "building"
            else:
                g["coord_precision"] = "dong"
            if kind == "trade":
                p = g.pop("_prices", [])
                # ★대표통계(이상치 제거) — 지분·정정 등 미미거래·초고가 왜곡 방지(공용 헬퍼).
                _s = robust_price_stats(p)
                g["avg_price_10k"] = _s["avg"]
                g["min_price_10k"] = _s["min"]
                g["max_price_10k"] = _s["max"]
                g["excluded_outliers"] = _s["excluded"]
            else:
                d = g.pop("_deposits", [])
                m = g.pop("_monthlies", [])
                g["avg_deposit_10k"] = round(sum(d) / len(d)) if d else 0
                g["avg_monthly_10k"] = round(sum(m) / len(m)) if m else 0
            # ★최신순 정렬 후 절단 — 무정렬 [:10]은 최신 거래를 잘라낼 수 있다(수집 순서는
            #   MOLIT 응답 순서일 뿐 날짜순이 아님). 파싱 실패분(날짜 없음)은 최하위로 보존.
            g["deals"].sort(key=lambda d: parse_deal_date(d.get("deal_date")) or (0, 0, 0), reverse=True)
            g["deals"] = g["deals"][:10]
            out.append(g)
        # 거래 많은 순 정렬. ★상한(_MAX_GROUPS_PER_CAT)은 여기서 적용하지 않는다 — build()가
        #   지오코딩·반경 필터 이후에 적용한다. 여기서 캡을 걸면 "반경 내 상위 N건"이 아니라
        #   "시군구 전체 상위 N건"이 되어 radius_m 라벨이 실제 필터와 무관한 거짓 표기가 된다.
        out.sort(key=lambda x: x["count"], reverse=True)
        return {"label": label, "type": type_key, "kind": kind,
                "count": sum(x["count"] for x in out), "groups": out}

    # ── AI 시세(AVM) 요약 ──
    @staticmethod
    def _js_round(x: float) -> int:
        """JS `Math.round` 방식(0.5는 항상 올림)으로 반올림한다.

        Python 내장 `round()`는 banker's rounding(가장 가까운 짝수로 반올림)이라 종전
        프론트 계산(Math.round)과 .5 경계에서 값이 어긋날 수 있다 — 이 함수는 값 동일성
        (프론트 재구현 이전과 이후 산출값이 정확히 같아야 함)을 보장하기 위한 것.
        본 서비스에서 다루는 값(가격·면적·CV%)은 항상 0 이상이라 이 구현으로 충분하다.
        """
        return math.floor(x + 0.5)

    @staticmethod
    def _avm_caveat(
        apt_trade_category: dict[str, Any] | None,
        *,
        radius_applied: bool,
        radius_m: int | None,
    ) -> str | None:
        """AVM의 **신뢰성 단서**를 말한다(무날조 — 침묵 대신 사유).

        ★AVM이 **없을 때**(사유)와 **있지만 반경 보증이 없을 때**(경고)를 모두 반환한다.
          후자가 더 위험하다 — 확신에 찬 숫자에 아무 표시가 없으면 사용자는 그대로 믿는다.

        ★"거래가 아예 없다"와 "거래는 있는데 반경 안에서 위치가 확인된 게 없다"는 전혀 다른
          상태다. 종전엔 둘 다 조용히 null이라 사용자는 구분할 수 없었고, 그 사이 화면은
          **위치를 모르는 원거리 거래로 만든 시세**를 보여주고 있었다.
        """
        cat = apt_trade_category or {}
        all_groups = cat.get("groups") or []
        if not all_groups:
            return None  # 진짜로 거래가 없다 — 기존 "무자료" 표기로 충분
        if radius_applied:
            if not (cat.get("_in_radius_groups") or []):
                # ★W1-b 리뷰(M-7) — `all_groups` 는 좌표가 **있는** 개략 그룹까지 포함하므로
                #   전부 "위치 미확인"이라 부르면 거짓이다. 상태별로 나눠 말한다.
                _approx = sum(
                    1 for g in all_groups
                    if g.get("lat") is not None
                    and g.get("coord_precision") == "dong"
                )
                _unlocated = sum(1 for g in all_groups if g.get("lat") is None)
                _detail = " · ".join(
                    bit for bit in (
                        f"위치 미확인 {_unlocated}곳" if _unlocated else "",
                        f"동 단위까지만 확인 {_approx}곳" if _approx else "",
                    ) if bit
                )
                return (
                    f"반경 {radius_m}m 안에서 위치가 확인된 아파트 실거래를 찾지 못했습니다"
                    f"({_detail}은 시세 산정에 쓰지 않습니다)."
                )
            return None
        # ★반경 미적용(중심좌표 확보 실패) — 좌표가 있는 그룹만 쓰되, **반경 보증이 없다는
        #   사실**을 반드시 말한다. 종전엔 이 경로에서 사유가 None이라 사용자에게 아무
        #   경고도 없이 시군구 전역 거래로 만든 시세가 나갔다.
        # ★W1-b 리뷰(C-1·M-7) — 판정 기준을 `_compute_avm_summary` 와 **한 식으로 통일**한다.
        #   둘이 갈라지면 "시세는 만들었는데 사유가 없다" 또는 그 반대가 나온다(계약 불변식이
        #   막는 것도 바로 그 모순인데, 기준이 다르면 불변식을 통과하면서 문구만 거짓이 된다).
        resolved = [
            g for g in all_groups
            if g.get("lat") is not None and g.get("coord_precision") != "dong"
        ]
        if not resolved:
            # ★"위치 미확인"과 "동 단위까지만 확인"은 다른 상태다 — 뭉뚱그리면 이 PR 이 만든
            #   3분류 어휘와 표면 문구가 어긋난다(리뷰 M-7).
            approx = sum(
                1 for g in all_groups
                if g.get("lat") is not None and g.get("coord_precision") == "dong"
            )
            if not approx:
                # 개략분이 없으면 종전 문구를 그대로 쓴다 — 새 어휘를 도입한다고 기존에
                # 잠긴 계약 문구를 흔들 이유가 없다(회귀락이 그 문구를 고정하고 있다).
                return (
                    "위치가 확인된 아파트 실거래가 없어 시세를 산정하지 않았습니다"
                    f"(수집 {len(all_groups)}곳 전부 위치 미확인)."
                )
            unlocated = sum(1 for g in all_groups if g.get("lat") is None)
            detail = " · ".join(
                bit for bit in (
                    f"위치 미확인 {unlocated}곳" if unlocated else "",
                    f"동 단위까지만 확인 {approx}곳" if approx else "",
                ) if bit
            )
            return (
                "위치가 확인된 아파트 실거래가 없어 시세를 산정하지 않았습니다"
                f"({detail})."
            )
        return (
            "대상지 중심좌표를 확보하지 못해 반경 필터를 적용하지 못했습니다 — "
            f"아래 시세는 시군구 범위의 위치 확인분 {len(resolved)}곳 기준이며 "
            "대상지 인근이라는 보증이 없습니다."
        )

    def _compute_avm_summary(
        self,
        apt_trade_category: dict[str, Any] | None,
        *,
        radius_applied: bool = False,
        radius_m: int | None = None,
    ) -> dict[str, Any] | None:
        """아파트 매매 실거래 그룹(**반경 통과분만**) 통계로 AI 시세(AVM) 요약을 계산한다.

        ★근본수정(P0) — 종전 도크스트링은 "반경 필터·캡 적용 후"라고 적혀 있었으나 실제
          입력은 `capped + unresolved`였다(주석과 코드 불일치). 그래서 **반경 판정을 받은
          적조차 없는** 좌표미확보 그룹이 시세를 만들었다. 호미곶 임야 실측: 반경 통과 0건인데
          AVM 1,490,069원/㎡ — 근거는 20km 밖 아파트였다. 이제 `_in_radius_groups`만 쓴다.

        SSOT 일원화(PropAI 아이디어#3): 종전엔 프론트(MarketInsightsWorkspaceClient.tsx
        deriveResults :196-238)가 이 서비스의 apt_trade 응답을 다시 순회해 재계산했다 —
        그 로직을 그대로(재구현 아님) 이 메서드로 이식했을 뿐 계산방식은 불변이다.

        - 시세: 그룹별 평당가(avg_price_10k / (avg_area_m2/평)) 를 그룹 거래건수(count)로
          가중평균 → 84㎡ 환산 총액·㎡당 시세.
        - 신뢰도: 개별 거래가(price_10k_won) 표본의 변동계수(CV=표준편차/평균) 기반 —
          표본이 많고(count 항) 가격이 고르게 형성될수록(CV 항, 낮을수록 가산) 신뢰도가
          높다. 두 항을 절반씩 반영해 0.3~0.98로 클램프.
        - 표본(비교 가능한 그룹) 0건이면 None — 무날조.
        """
        cat = apt_trade_category or {}
        # ★반경 필터가 적용된 경우에만 통과분으로 한정한다. 미적용(중심좌표 없음 등)이면
        #   반경 개념 자체가 없으므로 종전처럼 전체를 쓰되, 아래 basis가 그 사실을 밝힌다.
        if radius_applied:
            groups = cat.get("_in_radius_groups") or []
            if not groups:
                # ★반경 안에 비교 대상이 없다 → **None**(기존 계약 유지 — 소비처가
                #   `payload.avm ?? null`로 읽어 "미제공"으로 graceful 처리한다).
                #   사유는 응답 최상위 `avm_unavailable_reason`으로 **additive** 제공한다.
                #   여기서 truthy 객체를 돌려주면 기존 소비처가 0원·NaN을 그린다.
                return None
        else:
            # ★R1 HIGH-2 봉합 — 종전 `else` 가지는 **좌표 미확인 그룹을 포함한 전체**를 썼다.
            #   즉 봉합 대상 결함(위치를 모르는 거래로 시세를 만든다)이 이 가지에 그대로
            #   살아 있었고, 게다가 이 경로는 **생산에서 도달 가능**하다:
            #   라우터의 `center_hint`는 `lawd_cd`가 없을 때만 계산되므로, 프론트가 pnu/bcode를
            #   정상 공급하는 주경로(사통맵 필지 선택)에서는 힌트가 없고, 내부 주소 지오코딩이
            #   실패하면 `radius_applied=False`가 된다 — 지오코딩이 잘 실패하는 모집단이
            #   바로 산 지번·농어촌 주소(호미곶이 속한 그 모집단)다.
            #   반경 판정은 못 해도 **좌표조차 없는 그룹은 배제**한다(무날조는 반경 적용
            #   여부에 따라 켜졌다 꺼졌다 하면 안 된다).
            #   ★W1-b 리뷰(C-1) 봉합 — 위 원칙을 **정밀도 축에서 어기고 있었다**. 이 가지가
            #   `lat is not None` 만 보는 동안 True 가지만 정밀분으로 좁혀서, 같은 응답 안에
            #   `sample_basis.located_count=0` 과 "위치 확인분 N곳 기준"이라는 caveat 가
            #   동시에 나갔다(리뷰어 실측: comparable_count=2 vs located_count=0·신뢰도 0.768).
            #   하필 이 가지가 지오코딩이 잘 실패하는 모집단 — 이 PR 이 겨냥한 그 대상이다.
            groups = [
                g
                for g in (cat.get("groups") or [])
                if g.get("lat") is not None
                and g.get("coord_precision") != "dong"
            ]
        if not groups:
            return None

        pp_sum = 0.0
        pp_n = 0
        for g in groups:
            avg_price_10k = g.get("avg_price_10k")
            avg_area_m2 = g.get("avg_area_m2") or 0
            if avg_price_10k and avg_area_m2 > 0:
                per_pyeong = avg_price_10k / (avg_area_m2 / PYEONG_SQM)
                cnt = g.get("count") or 1
                pp_sum += per_pyeong * cnt
                pp_n += cnt
        if pp_n <= 0:
            return None

        per_pyeong = pp_sum / pp_n          # 만원/평
        per_m2_man = per_pyeong / PYEONG_SQM  # 만원/㎡

        deal_prices = [
            d.get("price_10k_won")
            for g in groups
            for d in (g.get("deals") or [])
            if isinstance(d.get("price_10k_won"), (int, float)) and d.get("price_10k_won") > 0
        ]

        confidence = 0.5  # 개별 거래가 표본이 없는 비정상 케이스 폴백(프론트와 동일)
        cv_percent = 0.0
        if deal_prices:
            n = len(deal_prices)
            mean = sum(deal_prices) / n
            variance = sum((p - mean) ** 2 for p in deal_prices) / n
            cv = (math.sqrt(variance) / mean) if mean > 0 else 0.0
            cv_percent = cv * 100
            count_factor = min(1.0, math.log10(n + 1) / 2)  # 표본 ~100건에서 포화
            dispersion_factor = max(0.0, 1 - cv / 0.5)  # CV 0~50% 구간을 1→0으로 선형 감산
            confidence = 0.4 + 0.3 * count_factor + 0.3 * dispersion_factor
            # ★W1-b 리뷰(H-5) — **소표본 하드 캡**. 위 산식은 log 스케일이라 표본이 105→18로
            #   83% 줄어도 신뢰도는 0.820→0.772(−6%p)에 그치고, 표본이 1건이면 분산이 0이라
            #   `dispersion_factor` 가 **만점**을 받아 다건보다 높아질 수도 있다(실측 1건 74.5%).
            #   이번 변경은 표본을 구조적으로 줄이므로(위치 확인분만 사용) 붕괴가 일상화되는데,
            #   그것을 알릴 축이 없으면 "표본 1건 74.5%"가 사용자에게 그대로 나간다.
            if n < _MIN_RELIABLE_DEALS:
                confidence = min(confidence, 0.5)

        return {
            "estimated_price": self._js_round(per_m2_man * 84 * 10000),
            "price_per_sqm": self._js_round(per_m2_man * 10000),
            "confidence_score": min(0.98, max(0.3, confidence)),
            # ★소표본 여부를 **값 옆에 실어** 소비처가 반드시 알 수 있게 한다(신뢰도 숫자만
            #   보고는 표본이 몇 건인지 알 수 없다 — 그게 이 산식의 은폐 지점이었다).
            "small_sample": len(deal_prices) < _MIN_RELIABLE_DEALS,
            "min_reliable_deals": _MIN_RELIABLE_DEALS,
            # ★`comparable_count`는 이름과 달리 "비교 **거래** 건수"였다(그룹 수 아님).
            #   기존 소비처 무회귀를 위해 값은 유지하되, 이제 **반경 통과분 기준**이고
            #   의미가 분명한 별칭을 함께 낸다.
            "comparable_count": sum(g.get("count") or 0 for g in groups),
            "comparable_deal_count": sum(g.get("count") or 0 for g in groups),
            "comparable_group_count": len(groups),
            "sample_count": len(deal_prices),
            "price_cv_percent": self._js_round(cv_percent),
            # ★근거 표기 — 이 시세가 **무엇으로부터** 나왔는지 소비처가 알 수 있어야 한다.
            "basis": {
                "radius_applied": radius_applied,
                "radius_m": radius_m,
                "in_radius_group_count": len(groups) if radius_applied else None,
                "scope": "in_radius" if radius_applied else "all_groups_radius_not_applied",
            },
        }

    # ── 공개 지오코딩(다른 서비스 재사용·캐시 공유) ──
    async def geocode_addresses(self, queries: list[str]) -> dict[str, dict]:
        """주소 리스트 → {주소: {lat, lon}} (VWorld, 7일 캐시 공유). 분양정보 등에서 재사용."""
        return await self._geocode_many(queries)

    async def geocode_one(self, query: str) -> dict | None:
        return await self._geocode_one(query)

    # ── 지오코딩(카카오 로컬 + Redis 캐시) ──
    async def _redis(self):
        try:
            import redis.asyncio as aioredis
            return aioredis.from_url(self.settings.redis_url)
        except Exception:
            return None

    async def _geocode_many(self, queries: list[str]) -> dict[str, dict]:
        if not queries or not self._geo_key:
            return {}
        sem = asyncio.Semaphore(_GEOCODE_CONCURRENCY)
        async with httpx.AsyncClient(timeout=12.0) as client:
            async def run(q):
                async with sem:
                    return q, await self._geocode_one(q, client)
            pairs = await asyncio.gather(*[run(q) for q in queries])
        return {q: c for q, c in pairs if c}

    async def _geocode_one(self, query: str, client: httpx.AsyncClient | None = None) -> dict | None:
        if not query or not self._geo_key:
            # 키 미설정은 "주소를 못 찾은 것"과 전혀 다른 상태다 — 섞어 세면 진단이 망가진다.
            if query and not self._geo_key:
                self._geo_fail("key_missing")
            return None

        # ★리뷰 H-2 봉합 — 계측을 **질의 단위**로 모은다. 종전엔 PARCEL/ROAD 루프 안에서
        #   바로 적립해, ①실패 질의 1건이 2회 적립되고 ②PARCEL 실패 후 ROAD 성공한
        #   **성공 질의도 not_found 를 적립**했다. 그러면 `geocode_failure_breakdown` 은
        #   "좌표를 못 얻은 질의 수"가 아니게 되고 `coords_unresolved_count` 와 비교 불가다.
        #   ★더 나쁜 건 편향 방향이다 — not_found 만 구조적으로 부풀어 429/5xx 비중이 항상
        #   과소평가된다. 그런데 나는 재시도 착수 조건을 "이 계기가 429/5xx 가 유의미하다고
        #   말할 때"로 걸어놨다. 즉 **착수하지 않는 결론 쪽으로 기울어진 계기**였다.
        attempt_reasons: list[str] = []
        _final_reason = ""  # 캐시 저장에서 재사용(F-2)

        def _fail(reason: str) -> None:
            attempt_reasons.append(reason)
            # ★F-3 — 질의 단위 대표사유(위)와 **시도 단위 전량**은 서로 다른 질문에 답한다.
            #   질의 단위만 남기면 "429 가 총 몇 번 났나"가 소실돼, 429 스파이크 구간에서
            #   전체가 transient 로 쏠려 이번 PR 이 고친 근원(주소 오류=not_found)이 거꾸로
            #   가려진다. 두 관점을 **병기**해 서로를 오염시키지 않게 한다.
            self._geo_attempt_fail(reason)

        cache_key = f"geo:vworld:{query}"
        r = await self._redis()
        if r is not None:
            try:
                cached = await r.get(cache_key)
                if cached:
                    await r.aclose()
                    val = json.loads(cached)
                    # ★F-2 — 캐시된 실패에 **원래 사유**를 실어 보관한다. 종전엔 전부
                    #   `cached_miss` 한 바구니로 뭉쳐서, 워밍된 지역을 반복 조회하면 breakdown 이
                    #   그것에 지배돼 "429 대 not_found 비중"이라는 계측의 존재 이유가 다시
                    #   판정 불가가 됐다(공백은 메웠으나 정보량은 회복되지 않았다).
                    #   ★★판정을 `val` 의 truthiness 가 아니라 **`lat` 유무**로 바꾼다 —
                    #   사유를 담은 실패 엔트리 `{"_fail": ...}` 는 truthy 라, 그대로 두면
                    #   **실패가 성공으로 오분류**된다(리뷰어가 명시 경고한 함정).
                    if not val or val.get("lat") is None:
                        self._geo_fail((val or {}).get("_fail") or "cached_miss", query)
                        return None
                    return val
            except Exception:
                pass
        own = client is None
        if own:
            client = httpx.AsyncClient(timeout=12.0)
        coord = None
        try:
            base = {
                "key": self._geo_key, "service": "address",
                "request": "getcoord", "format": "json",
            }
            # 지번주소=PARCEL 우선, 도로명=ROAD 폴백
            for addr_type in ("PARCEL", "ROAD"):
                try:
                    resp = await client.get(
                        _VWORLD_GEOCODE_URL, params={**base, "address": query, "type": addr_type}
                    )
                    if resp.status_code != 200:
                        # ★W2 계측 — 종전엔 `continue` 뿐이라 **왜 실패했는지 아무도 몰랐다**.
                        #   그 상태에서는 "재시도를 넣으면 좋아진다" 같은 처방이 전부 신앙이 된다
                        #   (실제로 내가 그 오진을 했다 — 실패는 일시장애가 아니라 주소 오류였다).
                        _fail("http_429" if resp.status_code == 429 else
                              ("http_5xx" if resp.status_code >= 500 else "http_other"))
                        continue
                    j = resp.json()
                    if j.get("response", {}).get("status") == "OK":
                        pt = j["response"]["result"]["point"]
                        # ★W1-b 리뷰(H-3) — VWorld 가 **실제로 어떤 주소로 매칭했는지**(refined)를
                        #   버리지 않는다. 종전엔 point 만 취해서, 정밀도를 "질의 문자열의 모양"
                        #   으로 추정할 수밖에 없었다. 그 추정은 시군구가 빠지거나 틀린 질의가
                        #   **다른 시군구의 동명 지번**으로 해석돼도 `parcel` 로 분류한다 —
                        #   좌표는 완전히 틀린데 라벨이 "위치 확인"이라고 승인하는 형태다.
                        #   여기서 정답(매칭 주소)을 함께 실어 보내 소비처가 대조하게 한다.
                        _refined = (
                            ((j.get("response", {}).get("refined") or {}).get("text") or "").strip()
                        )
                        coord = {
                            "lat": float(pt["y"]),
                            "lon": float(pt["x"]),
                            "addr_type": addr_type,
                            **({"refined": _refined} if _refined else {}),
                        }
                        break
                    else:
                        # VWorld 는 매칭 실패도 **HTTP 200 + status=NOT_FOUND** 로 준다.
                        # 이건 일시장애가 아니라 **영구 실패**라 재시도로 못 고친다 — 그
                        # 구분이 없으면 처방의 방향 자체가 틀어진다.
                        _fail(str((j.get("response") or {}).get("status") or "not_ok").lower())
                except (httpx.TimeoutException, httpx.RequestError):
                    _fail("timeout_or_network")
                    continue
                except Exception:
                    _fail("exception")
                    continue
        finally:
            if own:
                await client.aclose()
        if coord is None and attempt_reasons:
            # ★리뷰 R-3 — 대표 사유를 "마지막 시도"로 잡으면 루프가 ("PARCEL","ROAD") 고정이라
            #   **항상 ROAD 의 사유**가 된다. 우리 질의는 대부분 지번 형태라 ROAD 는 구조적으로
            #   not_found 를 잘 내고, 그러면 PARCEL 에서 난 429/5xx 가 계속 가려진다 —
            #   커밋이 스스로 지적한 "착수하지 않는 결론 쪽으로 기울어진 계기"가 크기만 줄고
            #   방향은 그대로였다. **일시장애를 우선**해 그 편향을 없앤다.
            # 쿼리를 함께 남긴다 — 원인 코드만으로는 "어떤 주소가 왜 깨지는지" 못 본다
            # (이번 진단의 결정타가 실패 쿼리의 시군구를 눈으로 본 것이었다).
            _transient = ("http_429", "http_5xx", "timeout_or_network")
            _final_reason = next((r for r in attempt_reasons if r in _transient), attempt_reasons[-1])
            self._geo_fail(_final_reason, query)
        if r is not None:
            try:
                # ★성공은 7일, 실패/미해결은 5분만 캐시 — 일시 실패가 장기 고착되지 않게 한다.
                ttl = _GEOCODE_CACHE_TTL_OK if coord else _GEOCODE_CACHE_TTL_MISS
                # ★F-2 — 실패도 **사유와 함께** 캐시한다(구 엔트리 `{}` 는 5분 뒤 자연 소멸).
                _cached_val = coord if coord else {"_fail": _final_reason or "not_found"}
                await r.setex(cache_key, ttl, json.dumps(_cached_val))
                await r.aclose()
            except Exception:
                pass
        return coord
