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
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.core.db_utils import PostGISHelper
from app.services.data_validation.deal_date import parse_deal_date
from app.services.data_validation.price_stats import robust_price_stats
from app.services.land_intelligence.sample_attenuation import (
    build_sample_attenuation,
)
from app.services.market.comparable_sample import is_masked_jibun as _is_masked_jibun
from app.services.market.land_dong_stats import dong_land_stats
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

# ── 적응형 반경(opt-in) ──────────────────────────────────────────────────────
# 왜 필요한가(쉬운 설명): 반경 1km 는 **도시 밀집지 기준**이다. 지방·농촌 필지에서는 그 안에
# 거래가 거의 없어 지도가 텅 빈다. 라이브 실측(2026-08-21 제천 모산동 123-1):
#   반경 1km → 렌더 가능 마커 **2**개 · 3km → 40 · 10km → **118**
#   (좌표미확보 56 은 국토부 지번 마스킹이라 **모든 반경에서 동일** — 반경과 무관한 원천한계)
# 즉 사용자가 본 "실거래가 안 나온다"의 지배 원인은 원천 데이터가 아니라 **우리 기본값**이었다.
#
# ★확대 비용은 0 이다 — 이 서비스는 `지오코딩 → 반경필터 → 캡` 순서라, 반경 밖 그룹도
#   **이미 좌표를 다 구해 놓고** 버린다. 사다리를 걷는 것은 손에 쥔 데이터에 대한 재판정뿐이다.
# ★opt-in 이다 — 지도만 켠다. 탁상감정·AVM·시세 경로의 표본 반경을 조용히 바꾸면
#   "반경 N 안에서 위치가 확인된" 이라는 기존 문구가 거짓이 된다.
_RADIUS_LADDER_M = (1000, 3000, 5000, 10000)
_AUTO_EXPAND_MIN_MARKERS = 10  # 이 수를 넘기는 **가장 좁은** 반경을 고른다(과확대 방지)

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

# 그룹 간 이상치 트림 시 `robust_price_stats`(정수 입력 전제)에 넘길 스케일.
# 평당가는 실수라 그대로 넣으면 `int(p)` 절단으로 계통 편차가 생긴다 — 100배로 넣고 되돌린다.
_PP_SCALE = 100


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


def select_precut_survivors(
    groups: "list[dict[str, Any]]", budget: int, target_dong: str, target_eupmyeon: str = ""
) -> "list[dict[str, Any]]":
    """지오코딩 예산 안에서 **어느 그룹을 남길지** 고른다(순수함수 — 외부호출 0).

    정렬키 = `(지역순위, -거래건수)`. 지역순위는 `_locality_rank` 참조.
    예산 이하이면 **정렬조차 하지 않는다**(종전 동작 보존 — 순서가 바뀌면 하위 소비처가
    «첫 값 대표» 로 다른 값을 볼 수 있다).

    ★`build()` 안에 인라인으로 두면 «무엇을 고르는가» 를 네트워크 없이 태울 수 없어
      락이 «호출됐다» 만 보게 된다. 이 저장소가 반복해서 데인 형태라 분리한다.
    """
    if len(groups) <= budget:
        return groups
    return sorted(
        groups, key=lambda x: (_locality_rank(x, target_dong, target_eupmyeon), -x["count"])
    )[:budget]


def _locality_rank(group: "dict[str, Any]", target_dong: str, target_eupmyeon: str) -> int:
    """사전컷 지역 프라이어 순위 — **작을수록 먼저 남는다.**

        0 = 대상 법정동(리) 일치      1 = 같은 읍·면      2 = 그 외

    ★`target_eupmyeon` 이 빈 문자열이면 1단이 **발화하지 않아** 종전(0/2 이진)과
      **순서가 동일**하다. 그래서 옵트인하지 않은 소비처(탁상감정 등)는 동작이 불변이다.
    """
    dong = group.get("dong")
    if target_dong and _dong_tail(dong) == target_dong:
        return 0
    if target_eupmyeon and _eupmyeon_head(dong) == target_eupmyeon:
        return 1
    return 2


def _eupmyeon_from_address(address: str | None) -> str:
    """주소에서 **읍·면 토큰**을 뽑는다(사전컷 2단 프라이어용).

      "경기도 남양주시 화도읍 마석우리 265-1" → "화도읍"
      "서울특별시 강남구 역삼동 736"          → ""   (동 지역은 읍·면이 없다)

    못 찾으면 빈 문자열 — 그때는 2단 프라이어가 **꺼진다**(추측해서 엉뚱한 읍을 우대하지 않는다).
    """
    for tok in (address or "").split():
        if len(tok) >= 2 and tok[-1] in ("읍", "면"):
            return tok
    return ""


def _eupmyeon_head(value: str | None) -> str:
    """법정동 표기의 **읍·면 토큰**(있으면). 없으면 빈 문자열.

    MOLIT `umdNm` 은 읍·면 지역에서 `"화도읍 창현리"` 처럼 **두 토큰**으로 온다
    (`_dong_tail` 이 그 꼬리를 취한다). 여기서는 **머리**를 취해 «같은 읍·면» 을 판정한다.
    동(洞) 지역은 한 토큰이라 읍·면이 없다 → 빈 문자열(추측해서 만들지 않는다).

    ★왜 필요한가(2026-09-05 실측): `lawd_cd` 가 **시군구**라 MOLIT 은 시군구 전체 거래를 준다.
      남양주시 마석 기준 조회에서 사전컷 대상의 고유 법정동이 **33개**였고
      다산동·별내동·진접읍 등 **10~20km 밖 신도시**가 섞여 있었다. 사전컷 2순위가
      `-거래건수` 라 그 대단지들이 예산을 쓸어가고, 정작 1km 안 단지가 잘렸다.
      실측: 1km 내 실재 아파트 **25곳** 중 화면에 **4곳**(= 대상 리 일치분) — 손실의
      **84% 가 「리 사이」** 였고 그 25곳의 리가 **전부 같은 읍(화도읍)** 이었다.
      ⇒ 읍·면 한 계층만 넣으면 **추가 외부호출 0회**로 그 손실을 회복한다.
    """
    v = (value or "").strip()
    parts = v.split()
    return parts[0] if len(parts) >= 2 else ""


# ★R1 리뷰(m-5) — 마스킹 판정을 **공용 헬퍼 한 곳**으로 모은다.
#   종전엔 이 파일의 `_is_masked_jibun` 과 `comparable_sample` 의 `"*" in str(...)` 리터럴이
#   **독립 정의** 둘이었다. 리뷰어가 판정을 전각 `＊` 까지 넓히자 이 파일만 따라오고 소비처는
#   갈렸다. CLAUDE.md 전역 전파방지("공용 함수로 추출해 한 곳을 고치면 전역이 따라오게")
#   위반이라, 정의를 소비처 모듈(`comparable_sample`)로 올리고 여기서는 임포트해 쓴다.
#   (의존 방향: `nearby_map_service` → `comparable_sample`. 역방향 임포트가 없어 순환 없음.)


def _target_dong_source(address: str, target_dong: str) -> str:
    """동 프라이어가 **왜** 켜졌는지/꺼졌는지를 한 값으로 말한다.

    꺼진 이유를 구분하지 않으면 판독자가 정상 동작과 결함을 섞어 집계한다:
      - `address`            : 주소에서 법정동을 뽑았다(프라이어 켜짐).
      - `unresolved_road_name`: 도로명 주소라 법정동이 없다 — **설계상 정상**이다
                                (추측해서 엉뚱한 동을 우대하지 않는다는 문서화된 선택).
      - `unresolved`          : 지번 주소인데도 못 뽑았다 — **조사 대상**이다.
    이 구분이 없으면 "프라이어 미발화 30%"가 정상인지 버그인지 판정할 수 없다.
    """
    if target_dong:
        return "address"
    for tok in (address or "").split():
        if tok.endswith(("로", "길")):
            return "unresolved_road_name"
    return "unresolved"


def _count_dong_matches(groups: "list[dict[str, Any]]", target_dong: str) -> int | None:
    """`groups` 중 대상 법정동과 일치하는 그룹 수. 셀 수 없으면 **None**.

    ★사전컷 정렬키(`_dong_tail(x["dong"]) == target_dong`)와 **정확히 같은 판정**을 써야
    한다. 다른 규약으로 세면 계측이 관측 대상을 대변하지 못한다(자가검증 골든이 실함수를
    호출하지 않아 거짓 안전을 준 W2-c 와 같은 계열).

    ★실패 시 0 이 아니라 None 인 이유(무날조) — 0 은 "일치 그룹이 없었다"는 **관측된 사실**을
    뜻한다. 세는 데 실패한 것을 0 으로 적으면 관측된 적 없는 사실을 만들어 낸다(N-4 와 동일
    판단). 소비처는 None 을 "미측정"으로 읽어야 하며, 산술에 쓰기 전에 확인해야 한다.

    ★`target_dong` 이 비면(도로명 주소 등) 프라이어 자체가 무동작이므로 0 을 돌려준다 —
    이건 실패가 아니라 **판정된 사실**이다(`dong_prior_active=False` 와 짝으로 읽는다).
    """
    try:
        if not target_dong:
            return 0
        return sum(1 for g in groups if _dong_tail(g.get("dong")) == target_dong)
    except Exception:  # noqa: BLE001 — 계측이 본로직을 깨지 않는다
        return None


def _display_cap_impact(
    categories: "dict[str, dict[str, Any]]",
    avm: "dict[str, Any] | None",
    avm_legacy: "dict[str, Any] | None",
    avm_trimmed: "dict[str, Any] | None",
    *,
    radius_applied: bool,
) -> "dict[str, Any] | None":
    """**진단 전용** — 표시 상한이 표본을 얼마나 자르고 시세를 얼마나 움직이는가.

    ★이 필드는 **표시·계산에 쓰지 말 것.** `avm` 이 정본이다. 여기 실리는
    `price_per_sqm_display_cap_lifted` 는 **아직 채택된 값이 아니다**.
    이름과 `diagnostic_only=True` 가 유일한 방벽이라 이름을 정확히 쓴다 —
    관측용 값이 표시로 새는 것이 이 저장소가 반복해서 겪은 사고다.

    존재 이유(D-2): `_MAX_GROUPS_PER_CAT` 은 선언부가 스스로 "마커 상한·페이로드 축소"라고
    밝히는 **표시용 상수**인데 추정기 표본을 결정한다. 그 절단은 `-count` 정렬이라
    **거래 많은 단지 쪽으로 편향**된다. 고칠지 말지는 **델타를 재고 나서** 정한다 — 큰 숫자를
    보고 처방부터 세웠다가 한계수율이 0 이었던 M-4 를 반복하지 않기 위해서다.

    ★리뷰 A-1 정정 — **"uncapped" 는 과대 주장이었다.** `cat["groups"]` 는 지오코딩 **전에**
    `_MAX_GEOCODE_GROUPS_PER_CAT`(80)으로 사전컷되므로, 여기서 푸는 것은 **표시 상한 28 하나
    뿐**이고 사전컷 80 은 그대로 걸려 있다. 역삼동에서 사전컷은 거의 확실히 결속 중이다
    (실측 `apt_trade` `groups_cut=158`). 그래서 이름을 `_display_cap_lifted` 로 바꾸고,
    사전컷 현황(`geocode_precut_*`)을 **같이 실어** 판독자가 "캡을 풀면 전체 표본"으로
    오독하지 않게 한다.

    ★리뷰 A-2 정정 — 이 **가격 델타는 `apt_trade`(AVM) 한정**이다. 탁상감정은 이 페이로드에서
    `land_trade` 만 읽고 `avm` 은 쓰지 않는다(`desk_appraisal_service`). 그런데 캡은 전 카테고리에
    걸리므로 **돈에 더 가까운 쪽(land_trade → 채택단가 → 토지비 SSOT → NPV/IRR)이 미계측**이었다.
    가격 델타를 land 로 확장하는 것은 산식이 달라 별건이므로, 우선 **절단량만 전 카테고리로**
    관측한다(`truncation_by_category`). 절단량이 0 인 카테고리는 "고칠 필요 없음"을 말해 주고,
    0 이 아니면 그 카테고리의 가격 영향은 **아직 모른다**는 뜻이다.

    필요한 값이 하나라도 없으면 **None**(무날조 — 비교 불가를 0 으로 적지 않는다).
    """
    try:
        # ★거짓 음성 차단 — `radius_applied=False` 가지의 `_compute_avm_summary` 는
        #   `sample_field` 를 쓰지 않고 `cat["groups"]`(= 이미 캡된 `capped + unresolved`)를
        #   다시 거른다. 그래서 그 경로에서는 **절단이 실재해도** 두 값이 같아져 `delta_pct=0`
        #   이 나온다 — "영향 없음"으로 읽히는 **false-healthy** 다. 측정 못 한 것을 0 으로
        #   적지 않는다. 왜 None 인지는 응답 최상위 `radius_applied` 가 이미 말해 준다.
        if not radius_applied:
            return None
        apt_cat = categories.get("apt_trade") or {}

        # ★★리뷰 B-1 봉합 — **단위는 맞췄는데 모집단이 어긋나 있었다.**
        #   종전엔 `capped_group_count` 를 실었는데 그건 **정밀·동 대표점을 가리지 않은**
        #   전체 절단 그룹 수다. 반면 `sample_group_count(_lifted)` 는 **정밀 좌표분만**이다.
        #   정렬이 정밀분을 앞세우므로, 반경 안에 동 대표점 그룹이 하나라도 있으면 두 수는
        #   **반드시 갈라진다**. 리뷰어 실측: 정밀 10·동 40 일 때
        #   `dropped=22` 인데 `delta_pct=0.0` — "22그룹을 잘랐는데 시세 영향 0%" 라는,
        #   판독자를 **정확히 반대 결론으로** 끌고 가는 문장이 생성됐다(잘린 22개는 AVM 이
        #   애초에 안 쓰는 동 대표점이므로).
        #   ★내가 바로 위에 "단위가 섞이면 판독자가 두 수를 빼서 엉뚱한 결론을 낸다"고 주석까지
        #     달아 놓고, **단위(그룹/건수) 축만 맞추고 모집단(정밀/전체) 축을 놓쳤다.**
        #     방지하려던 결함 클래스가 축 하나만 옮겨 그대로 재발한 것이다.
        #   → AVM 표본이 실제로 잃은 양은 두 표본 길이의 차다. 전체 절단 수도 유용하므로
        #     **이름을 분리해** 병기한다(같은 dict 안에서 두 수가 다른 것은 정상이며, 이름이
        #     그 차이를 설명해야 한다).
        # ★D-2 전환으로 **이름의 의미가 바뀌었다** — `_in_radius_groups` 는 이제 **계산 표본**
        #   (캡 이전 전량)이고, `_in_radius_groups_display_capped` 가 **표시 표본**이다.
        #   두 수의 차 = 표시 상한이 화면에서 잘라낸 정밀 그룹 수(계산에는 이제 포함된다).
        n_compute = len(apt_cat.get("_in_radius_groups") or [])
        n_display = len(apt_cat.get("_in_radius_groups_display_capped") or [])
        precut = apt_cat.get("precut") or {}

        truncation: dict[str, Any] = {}
        for _key, _cat in categories.items():
            _all = len(_cat.get("_in_radius_groups") or [])
            _disp = len(_cat.get("_in_radius_groups_display_capped") or [])
            truncation[_key] = {
                "sample_group_count_display": _disp,
                "sample_group_count_compute": _all,
                "dropped_precise_group_count": _all - _disp,
                # 정밀·동 대표점을 **가리지 않은** 전체 절단 수. 위 값과 다른 것이 정상이다.
                "dropped_all_precisions_group_count": _cat.get("capped_group_count"),
                # ★리뷰 R5 — 상위 제약(사전컷)도 **카테고리별**로 병기한다. 최상위
                #   `geocode_precut_*` 는 apt 전용이라, land 를 판독할 때 그걸 보면 틀린다.
                "geocode_precut_groups_cut": (_cat.get("precut") or {}).get("groups_cut"),
            }

        # ★★리뷰 R1 봉합 — 종전엔 `avm` 이 없으면 **절단량까지 통째로** None 을 냈다.
        #   그런데 apt 비교표본이 없는 모집단(농어촌·토지 — 호미곶급)이 정확히 A-2 가 겨냥한
        #   곳이다. 즉 **가장 알고 싶은 데서 계측이 암전**했다(리뷰어 실행 증거: apt 0건 ·
        #   land 표시캡 12그룹 절단인데 `display_cap_impact: None`).
        #   → 가격 델타는 apt AVM 이 있을 때만, **절단량은 `radius_applied` 만으로 항상** 싣는다.
        #     가격 3종은 계산 불가면 **키를 빼지 않고 None** 으로 둔다 — 키 자체가 사라지면
        #     소비처가 "이 응답엔 그 개념이 없다"로 읽지만, 실제로는 "못 쟀다"이기 때문이다.
        _priced = bool(avm and avm_legacy)
        cur = (avm or {}).get("price_per_sqm") if _priced else None
        leg = (avm_legacy or {}).get("price_per_sqm") if _priced else None

        def _pct(a, b):
            """b 대비 a 의 변화율(%). 분모가 없으면 **None**(0 으로 날조하지 않는다)."""
            return round((a - b) / b * 100.0, 2) if (a and b) else None

        # ★리뷰 C-2 — 트림은 **정본이 아니다**. 캐노니컬(`cur`)은 캡 해제 + 무절사이고,
        #   트림은 아직 채택되지 않은 **진단 값**(`trm`)이다. 델타도 그렇게 나눈다.
        trm = (avm_trimmed or {}).get("price_per_sqm") if avm_trimmed else None
        _delta_total = _pct(cur, leg)          # 이 PR 이 실제로 바꾼 양(= 캡 해제분)
        _delta_cap = _pct(cur, leg)            # 총 변화 = 캡 해제 기여(트림 미채택이므로 동일)
        _delta_trim_candidate = _pct(trm, cur)  # ★미채택 — 트림을 채택하면 추가로 이만큼 움직인다

        return {
            # ★소비처 오용 방지 — 이 플래그를 보고도 렌더하면 그건 의도적 오용이다.
            "diagnostic_only": True,
            # ★★리뷰 MAJOR-2 봉합 — **최상위 카운트·가격은 전부 `apt_trade` 전용**인데 이름에
            #   그 사실이 없었다. R1 이 "최상위는 0 인데 카테고리별은 12" 인 상태를 **새로
            #   도달 가능하게** 만들었으므로(apt 표본 0 · land 12절단), 최상위만 훑는 판독자는
            #   "절단 0" 으로 읽는다. 값이 거짓은 아니지만(apt 에 대해 참) 이름이 범위를
            #   말하지 않으면 그건 판독자 책임이 아니다. 전 카테고리 수치는
            #   `truncation_by_category` 에 있다.
            "price_delta_category": "apt_trade",
            # ── 가격 델타(`apt_trade`/AVM 한정 — 표본이 없으면 None) ──
            "sample_group_count_display": n_display,   # 화면에 실린 정밀 그룹 수
            "sample_group_count_compute": n_compute,   # AVM 이 실제로 쓴 정밀 그룹 수
            "sample_deal_count": (avm or {}).get("comparable_count") if _priced else None,
            "sample_deal_count_display_capped": (
                (avm_legacy or {}).get("comparable_count") if _priced else None
            ),
            "dropped_precise_group_count": n_compute - n_display,
            "dropped_all_precisions_group_count": apt_cat.get("capped_group_count"),
            # ── 전환 변화량의 **원인별 귀속** ──
            "price_per_sqm": cur,                       # 전환 후(= 현재 사용자가 보는 값)
            "price_per_sqm_before_transition": leg,     # 전환 전(표시캡 표본 + 무절사)
            "delta_pct": _delta_total,                  # 이 PR 이 실제로 바꾼 양
            "delta_pct_from_cap_lift": _delta_cap,      # 그 전부가 캡 해제 기여다
            # ── ★미채택 진단 — 이상치 트림을 **채택하면** 추가로 얼마나 움직이는가 ──
            #   `avm` 은 트림을 쓰지 않는다. 이 값들은 프로덕션에서 델타를 재고 부호·크기
            #   일관성을 확인한 뒤 별도 PR 로 전환 여부를 판정하기 위한 것이다.
            "price_per_sqm_outlier_trimmed_candidate": trm,
            "delta_pct_from_outlier_trim_candidate": _delta_trim_candidate,
            "outlier_groups_excluded_candidate": (
                (avm_trimmed or {}).get("outlier_groups_excluded") if avm_trimmed else None
            ),
            "confidence_score": (avm or {}).get("confidence_score") if _priced else None,
            "confidence_score_before_transition": (
                (avm_legacy or {}).get("confidence_score") if _priced else None
            ),
            # ── 상위 제약(A-1) — 이걸 안 실으면 "캡을 풀면 전체 표본"으로 오독한다 ──
            "geocode_precut_budget": precut.get("budget"),
            "geocode_precut_groups_cut": precut.get("groups_cut"),
            # ── 절단량은 전 카테고리(A-2) — 가격 델타는 apt_trade 한정임을 이름이 말한다 ──
            "truncation_by_category": truncation,
        }
    except Exception:  # noqa: BLE001 — 진단이 본로직을 깨지 않는다
        # ★리뷰 R2 — 이 try 는 **이 함수 안**만 보호한다. 호출부의 `avm_lifted` 계산
        #   (`_compute_avm_summary(..., sample_field=...)`)은 이 밖이라 여기서 못 막는다.
        #   위험은 낮다(lifted 표본은 canonical 의 상위집합이고 원소 형상이 같다)지만,
        #   "진단이 본로직을 깨지 않는다"는 주장은 **이 함수 범위 한정**임을 명시해 둔다.
        # ★무성 실패 금지 — 로그가 없으면 진단기가 스스로 깨져도 "avm 없음/반경 미적용"과
        #   구분 불가하게 None 으로 수렴한다("관측전용은 스모크 없으면 무성회귀").
        logger.warning("표시상한 영향 계측 실패 — 진단 필드를 None 으로 낸다", exc_info=True)
        return None


def _precut_accounting_mismatch(
    categories: "dict[str, dict[str, Any]]", geocode_precut: int
) -> bool:
    """카테고리별 `groups_cut` 합이 기존 스칼라와 **갈라졌는가**.

    ★리뷰 F-1 봉합 — 종전엔 이 식이 응답 dict 안에 인라인으로 있었고 골든은 정상 상태의
    `is False` 만 단언했다. 그러면 **표현식을 리터럴 `False` 로 치환하는 변이가 생존한다**
    — 즉 "항상 False 를 내는 고장난 탐지기"도 그 단언을 통과한다. 탐지기가 잡아야 할 회귀를
    스스로 false-healthy 로 가리는 형태로, #497 에서 배포가드가 정확히 이렇게 적발됐다.
    순수 함수로 빼서 **발산 입력으로 True 분기를 직접 태울 수 있게** 한다.
    """
    total = sum((c.get("precut") or {}).get("groups_cut") or 0 for c in categories.values())
    return total != geocode_precut


def _pick_representative_pair(
    pairs: Iterable[tuple[str, str, str]],
) -> tuple[str, str, str]:
    """후보 `(시군구, 동, 지번)` 중 **대표 하나**를 결정론적으로 고른다.

    ★R5 리뷰(F-2) — 이 선택이 왜 순수 함수로 분리돼 있는가:

    호출부는 `set` 을 넘긴다. 그런데 파이썬 `set` 순회는 **한 프로세스 안에서는 일정**해서,
    `sorted` 를 빼도 같은 프로세스에서 도는 테스트는 전부 통과한다(실측: 변이 생존).
    실제 위험은 그때 드러나지 않는다 — `PYTHONHASHSEED` 는 **프로세스마다 다르므로**,
    정렬을 빼면 "배포할 때마다 다른 지번이 대표가 되는" 더 은밀한 비결정성이 된다.

    → 선택 로직만 떼어내 **후보 순서를 직접 흔들 수 있게** 한다. 테스트가 같은 원소의
    여러 순열을 리스트로 넣으면, 정렬이 빠진 순간 답이 갈려 변이가 죽는다.

    규칙: 지번을 쓸 수 있는 후보(마스킹 아님)를 우선하고, 그 안에서 `sorted` 첫 번째.
    어느 쪽이 "옳은" 지번인지는 알 수 없다. 알 수 없을 때 필요한 것은 정답이 아니라
    **재현성**이다 — 같은 데이터가 같은 화면을 내야 한다.
    """
    usable = sorted(p for p in pairs if p[2] and not _is_masked_jibun(p[2]))
    if usable:
        return usable[0]
    return sorted(pairs)[0]


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
        # ★N-5 — 세 계측 중 둘만 초기화하면, 다음 사람이 lazy init 을 "중복"으로 보고 지울 때
        #   바로 깨진다(W2 에서 그 경로로 테스트 11건이 죽었다). 대칭을 맞춘다.
        self._geo_attempt_failures: dict[str, int] = {}
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
        target_land_use: str = "",
        target_jimok: str = "",
        auto_expand_radius: bool = False,
        locality_prior: bool = False,
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
        # ★`locality_prior` 를 키에 **반드시** 넣는다. 안 넣으면 지도(켜짐)와 계산층(꺼짐)이
        #   같은 캐시 항목을 공유해, 먼저 부른 쪽의 **정렬이 다른 쪽에 새어** 나간다.
        #   그러면 «계산층 불변» 보장이 캐시 한 줄로 무너진다(옵트인 설계의 급소).
        cache_key = ((address or "").strip(), f"{lawd_cd}", months, radius_m, auto_expand_radius,
                     locality_prior)
        # ★auto_expand_radius 를 키에 넣는다 — 같은 주소·반경이라도 확대 여부에 따라
        #   결과가 다르다. 빼면 지도가 다른 소비처의 좁은 결과를 그대로 받는다.
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

        # ── 2-b) 토지 층화 통계 — **좌표 없이 말할 수 있는 것** ────────────────────
        # ★토지 실거래는 지번이 100% 마스킹돼 좌표를 만들 수 없다(실측 3지역 30개월
        #   3,113건 전수). 그래서 반경으로는 아무 말도 못 한다. 그런데 원천은 법정동·
        #   용도지역을 100% 채워 주므로, **행정구역+용도 축**으로는 말할 수 있다.
        # ★여기서 계산하는 이유: `trade_raw["land"]` 는 **이미 받아 둔 원본 행**이다.
        #   추가 API 호출이 0이고, 그룹 평균이 아니라 **개별 거래**로 통계를 낸다
        #   (그룹 평균으로 다시 평균을 내면 이중 평균이 된다).
        # ★`try` 밖에서 초기화 — 예외가 나도 아래 payload 조립이 `NameError` 로 깨지지 않는다.
        #   (참고 통계가 본 응답을 무너뜨리지 않는다는 이 블록의 전제를 지키는 줄이다.)
        # ★정직 표기 — 이 줄과 아래 `logger.debug` 는 **변이로 잠기지 않는다**
        #   (`scripts/mutate_changed.py` 실측). 둘 다 `dong_land_stats` 가 던졌을 때만
        #   관측되는데, 그 함수는 순수 계산이라 정상 입력에서 던지지 않는다.
        #   방어·관측용으로 남기되 "잠갔다"고 세지 않는다.
        land_dong_stats_out = None
        try:
            land_dong_stats_out = dong_land_stats(
                trade_raw.get("land", []),
                # ★`target_dong` 은 아래(사전컷)에서 정의되므로 여기서 직접 도출한다 —
                #   같은 헬퍼를 쓰므로 두 곳의 판정이 갈리지 않는다.
                target_dong=self._dong_from_address(address),
                target_land_use=target_land_use,
                # ★지목은 가격을 **자릿수로** 가른다(대 vs 도로) — 용도지역보다 앞선 축이다.
                target_jimok=target_jimok,
                # ★시점수정은 **하지 않는다** — 하는 척하지 않기 위해 `now_ym` 도 넘기지 않는다.
                #   보정하려면 R-ONE 월별 변동률 시계열(`rate_series`)이 필요한데, 그건 외부
                #   호출이라 이 경로에서 매번 부를 수 없다. `now_ym` 만 넘기면 `_time_factor` 가
                #   시계열이 없어 어차피 None 을 돌려주므로 **아무 일도 일어나지 않는다**.
                #   그 상태로 두면 "시점수정 인자를 넘겼다"는 외형만 남는다.
                #   → 넘기지 않고, 산출물의 `time_adjusted=False` 와 고지 문구가 그 사실을 말한다.
                #   ★창이 6개월이라 보정 없이도 왜곡이 작다(30개월 창을 쓸 때 다시 판단할 것).
            )
        except Exception as e:  # noqa: BLE001 — 참고 통계가 본 응답을 깨뜨리지 않는다
            # ★정직 표기 — 이 로그 문구도 잠그지 않는다(위 초기화 줄과 같은 이유).
            #   운영자용 관측이지 사용자 계약이 아니다.
            logger.debug("토지 층화 통계 산출 실패", err=str(e)[:80])

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
        # ★2단 프라이어(읍·면)는 **옵트인**이다. 기본 꺼짐 = 종전과 순서 동일.
        #   지도(표시)만 켠다 — 탁상감정 등 **계산층은 표본이 바뀌면 감정단가가 바뀌므로**
        #   같은 커밋에서 건드리지 않는다(그 값은 토지비 SSOT→NPV·IRR 로 흐른다).
        target_eupmyeon = _eupmyeon_from_address(address) if locality_prior else ""
        # ★M-4 계측 — 사전컷의 **순효과를 판정할 재료**를 카테고리별로 남긴다.
        #   종전엔 `geocode_precut_count` 라는 **10개 카테고리 합산 스칼라 하나**뿐이라,
        #   응답만 보고는 (a)어느 카테고리에서 컷이 발동했는지 (b)대상 법정동 일치 그룹이
        #   예산(80)을 넘었는지를 **원리적으로 역산할 수 없었다**(미지수 10개에 방정식 1개).
        #   그 두 가지가 곧 M-4 티켓("동 프라이어가 타 동 반경내 물건을 굶기는가")의
        #   발동 조건이다 — 즉 티켓을 판정할 계측이 없는 채로 처방부터 논의되고 있었다.
        #   ★분모(`groups_before`)를 **발동하지 않은 카테고리에도** 싣는다. 안 그러면
        #     `groups_cut == 0` 이 "80 이하라 안 잘림"인지 "그 카테고리 거래가 0건"인지
        #     구분되지 않는다(0 과 미확보를 같은 기호로 쓰지 않는다).
        #   ★추가 외부 호출 0 — 이미 메모리에 있는 리스트를 세는 것뿐이다.
        for cat in categories.values():
            _before = len(cat["groups"])
            _matched_before = _count_dong_matches(cat["groups"], target_dong)
            if _before > _MAX_GEOCODE_GROUPS_PER_CAT:
                geocode_precut += _before - _MAX_GEOCODE_GROUPS_PER_CAT
                cat["groups"] = select_precut_survivors(
                    cat["groups"], _MAX_GEOCODE_GROUPS_PER_CAT, target_dong, target_eupmyeon
                )
            _matched_kept = _count_dong_matches(cat["groups"], target_dong)
            cat["precut"] = {
                "budget": _MAX_GEOCODE_GROUPS_PER_CAT,
                # 단위는 전부 **그룹 수**다 — 이름에 박는다. 이웃한 `sample_basis` 는
                # 거래 건수 전용 계약이라 이 블록을 그쪽에 넣지 않는다(H-4 단위 혼입 재발 방지).
                "groups_before": _before,
                "groups_cut": max(0, _before - len(cat["groups"])),
                # 프라이어가 **켜지긴 했는지**. `target_dong` 이 비면(도로명 주소 등)
                # 정렬 1순위 항이 상수로 붕괴해 순수 건수 정렬로 돌아간다 — 응답만 보고는
                # 그 사실을 알 수 없었다.
                "dong_prior_active": bool(target_dong),
                # ★2단(읍·면) 프라이어가 **켜지긴 했는지**. 응답만 보고 알 수 있어야
                #   «효과 없음» 과 «발화 안 함» 을 가를 수 있다(0 과 미확보를 안 뭉친다).
                "eupmyeon_prior_active": bool(target_eupmyeon),
                # ★티켓의 핵심 질문: 대상 동 일치 그룹이 예산을 넘었는가(before > budget)?
                #   그리고 그중 몇이 살아남았는가(kept)? 둘의 차가 프라이어 포화도다.
                # ★★`active is True` 인데 `before == 0` 인 조합의 해석 — **경보가 아니라
                #   "확인 필요"다**(2026-08-05 프로덕션 첫 실사용에서 정정).
                #   종전 주석은 이 조합을 **표기 규약 불일치 경보**라고 단정했는데(H-4 가 그
                #   형태였다 — `umdNm` 이 두 토큰인데 완전일치 비교였다), 실제로 호미곶에서
                #   이 조합이 떴을 때 원인은 규약 불일치가 **아니었다**: 대상 법정동(대보리)에
                #   3개월 실거래가 **진짜 0건**이었다(관측된 동이 오천읍 용덕리·구정리, 대송면
                #   송동리·제내리, 송도동, 효자동, 일월동 뿐). 즉 이 조합은 **다섯 원인**을 포함한다:
                #     (1) 표기 규약 불일치 — 우리 **정규화**가 `umdNm` 형태를 못 따라간다.
                #                            수정 지점은 `_dong_tail`.               → **조사 대상**
                #     (2) 대상 동 무자료   — 그 동에 해당 카테고리 거래가 없다.        → **정상**
                #     (3) 대상 동 오추출   — `target_dong_hint` **자체가** `umdNm` 과 영영 안 맞는
                #                            표기다. 주소가 **행정동**이면 `_dong_from_address` 가
                #                            그대로 뽑아 온다. 두 서브클래스가 있다:
                #                              (3a) 접두 유사 — `"길음1동"` vs `"길음동"`, `"우1동"` vs `"우동"`
                #                              (3b) **병합 행정동** — `"청운효자동"` 관할 법정동은
                #                                   통인동·누하동·누상동·옥인동…, `"종로1·2·3·4가동"`
                #                                   관할은 관철동·견지동·공평동. **이름이 전혀 안 겹친다.**
                #                            수정 지점은 `_dong_from_address`(D-1 계열). → **조사 대상**
                #     (4) 시군구 오지정    — `lawd_cd`/`sigungu_hint` 가 틀려 **딴 시군구 행**이
                #                            들어왔다. `build()` 는 세 인자를 독립으로 받고 정합성
                #                            불변식이 없다. 이 서브시스템에서 **실제로 났다**(#535 —
                #                            시군구를 중개사무소 소재지에서 가져오던 한 줄). → **조사 대상**
                #     (5) 그룹 키 병합     — `key = name or jibun or dong` 이고 그룹 대표 `dong` 은
                #                            **첫 행의 것**이라, 대상 동 거래가 **다른 동 이름으로
                #                            대표되는 그룹에 흡수**되면 matched=0 인데 거래는 **실재**한다.
                #                            건물명이 없는 카테고리(토지·단독다가구)는 키가 지번으로
                #                            강등되고 `"1-1"`·`"산1-1"` 같은 지번은 한 시군구의 거의
                #                            모든 법정동에 있으므로 병합은 **예외가 아니라 상시**다.
                #                            수정 지점은 `_group_trade`/`_group_rent` 키·대표동. → **조사 대상**
                #   ★리뷰 차단 2회 봉합 — 초판은 (3)을 통째로 빠뜨렸고, 2판은 (3)을 넣고도
                #     "무관한 동만 보이면 (2)"라는 분기가 **(3b) 병합 행정동을 정상으로 닫았다**.
                #     행정동은 **정의상 병합명**이라 (3b)가 예외가 아니라 **구조적 다수**다 —
                #     즉 2판 규칙은 그 서브클래스에서 origin/main 의 "전부 경보"보다 탐지력이 낮았다.
                #     거짓양성보다 거짓음성이 나쁘다는 서열(W2-b·#497·W2-c)을 스스로 어긴 것이다.
                #   가르는 법(순서대로 — ★★**어느 단계도 "정상"으로 종결하지 않는다**):
                #     ① **수집이 성공했는데** `groups_before == 0` 이면 카테고리 전체 무자료다
                #        (즉답 — 동 문제 아님). ★`_collect` 가 예외를 삼키므로 **조회가 전면
                #        실패해도** `groups_before == 0` 이 된다 — 최상위 `fetch_failed`/
                #        `partial_failed`/`data_source` 를 **먼저** 볼 것. 이 코드블록이 스스로
                #        "0 과 미확보를 같은 기호로 쓰지 않는다"고 못 박아 놓고 ①이 그걸 어겼다.
                #     ② `lawd_cd` 가 대상지 시군구 코드와 맞는가? `sigungu_source == "row_fallback"` 인가?
                #        둘 중 하나라도 어긋나면 **(4)**.
                #        ★대상지 코드는 **법정동코드 앞 5자리**다 — ③과 **같은 표**(juso.go.kr)를 쓴다.
                #          ③에만 조회 경로를 적고 ②엔 안 적었던 비대칭을 해소한다.
                #        ★`row_fallback` 절은 **보조 신호**다 — 이 서명(`matched_before == 0`)을
                #          실제로 생산하는 것은 `lawd_cd` 오지정 쪽뿐이다. `sigungu_hint` 는
                #          `_query` 에만 들어가고 그룹의 `dong`(=`umdNm`)에는 영향이 없어
                #          매칭 카운트를 바꿀 수 없다(위양성만 만들고 위음성은 안 만든다).
                #        ★`sigungu_hint` **단독 대조는 (4)의 증거가 될 수 없다** — 힌트는 호출부가
                #          안 주면 주소에서 도출되므로(`sigungu_hint or sigungu_hint_from_address`),
                #          `lawd_cd` 만 틀린 경우 **힌트는 정확**하고 행의 진짜 시군구는 응답에서
                #          사라진다(그룹 시군구가 힌트로 덮인다). 2판 규칙은 이 절반을 놓쳤다.
                #     ③ `target_dong_hint` 가 **법정동인가**? 행정동이면 **(3)**.
                #        ★이건 **문자열 판정이 아니다** — 법정동코드 목록(juso.go.kr)으로 **조회**해야
                #          한다. "숫자 접미"는 휴리스틱일 뿐이고 반례가 이 저장소에 이미 있다:
                #          `"을지로2가"`·`"충무로1가"` 는 숫자를 포함한 **법정동**이다
                #          (`test_dong_from_address_stops_at_jibun` 이 그 형태를 잠근다).
                #     ④ 관측 `dong` 분포와 대조 — 같은 동의 **다른 표기**가 보이면 **(1)**.
                #     ④-b ★(5) 병합의 **값싼 1차 단서** — `jibun` 이 있는데
                #        `coord_precision == "dong"`(= `location_status == "approximate"`)인 그룹이
                #        있는가? `_finalize` 가 법정동이 둘 이상이면 `"dong"` 으로 강등하므로
                #        그 조합 자체가 **다동 병합 서명**이고 **응답에 이미 실려 있다**.
                #        ⑤의 "MOLIT 원자료 확인"보다 훨씬 싸다.
                #        ★확증은 아니다 — `_refined_mismatch` 도 같은 강등을 하므로 **강한 단서**일 뿐.
                #     ★★⑤ **여기서 "정상"으로 닫지 말 것.** 관측 분포로는 (2)와 (5)를 **구별할 수
                #        없다** — 대상 동 거래가 다른 동 이름의 그룹에 흡수되면 서명이 (2)와 같다.
                #        (2)로 닫으려면 **대상 동의 원천 거래 유무를 직접 확인**해야 한다(MOLIT 원자료).
                #        그 확인 전에는 **"미확인"** 이지 "정상"이 아니다.
                #        ★이 규칙을 **비종결**로 만든 이유 — 3차 리뷰까지 오는 동안 원인이
                #          (1)(2) → (3) → (4) → (5) 로 계속 늘었다. 열거를 늘리는 방식은
                #          다음 라운드에 (6)이 나오면 또 뚫린다. **열거 완결성에 의존하지 않는
                #          fail-safe** 로 바꾸는 것이 이 루프를 끝내는 수정이다
                #          (거짓양성 < 거짓음성 서열과도 일치).
                #     ※ (2) 의 "정상"은 **요청 `months` 창 기준**이다 — 창을 넓히면 나올 수 있다.
                #   ★가중 신호(증명 아님) — (1)·(3)·(4)는 **힌트 축** 결함이라 `matched_before == 0`
                #     이 **전 카테고리에서 동시에** 나타난다. (2)는 대개 일부 카테고리만 0 이다.
                #     `precut` 이 카테고리별로 실리므로 추가 계산 0 으로 얻을 수 있다.
                #     단 "대상 동에 전 카테고리 거래가 진짜 0" 인 경우가 있으므로 **증명이 아니다**.
                #   ★부분일치 카운터를 하나 더 실어 자동 분리하는 안은 **기각**했다 —
                #     `"중동"` 이 `"중동리"` 에 부분일치하는 식의 위양성을 새로 만들고(실측 확인),
                #     그러면 이 주석이 고치려는 오독을 **다른 형태로 재생산**한다(관측 장치가 결함
                #     클래스를 만든 F-2/N-1 계열). 판별은 사람이 동 분포와 대조한다.
                #     ※ 관측된 `dong` 집합 자체를 실어 ②를 눈으로 하게 만드는 안(원시 관측이라
                #        위양성 결함 클래스를 원리적으로 못 만든다)은 **후속 티켓**으로 남긴다.
                "dong_matched_group_count_before": _matched_before,
                "dong_matched_group_count_kept": _matched_kept,
            }
        queries: set[str] = set()
        # ★R2 리뷰(L-3) — 질의를 **만들지 못한** 그룹 수를 센다.
        #   이 그룹들이 `geocode_attempted_count` 분모에서 빠지므로, 이 수가 없으면
        #   W2 계측 기준선(사전컷 73.8% · 지오코딩 실패 2.6%)과 **직접 비교가 불가**해진다.
        #   "실패율이 좋아졌다"가 실제 개선인지 분모가 줄어든 것인지 구분할 수 있어야 한다.
        unqueryable_groups = 0
        for cat in categories.values():
            for grp in cat["groups"]:
                # ★빈 질의(마스킹 지번 등 **질의를 만들 수 없는** 그룹)는 지오코딩하지 않는다.
                #   빈 문자열을 그대로 보내면 예산을 버리고 실패 계측을 오염시킨다.
                if grp["_query"]:
                    queries.add(grp["_query"])
                else:
                    unqueryable_groups += 1
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

        # 4-b) ★적응형 반경 — **이미 확보된 좌표만으로** 사다리를 걸어 유효 반경을 정한다.
        #      추가 지오코딩·추가 외부호출 0(아래 루프가 쓸 `coords` 를 그대로 읽는다).
        #      고르는 규칙: 임계(_AUTO_EXPAND_MIN_MARKERS)를 넘기는 **가장 좁은** 반경.
        #      어느 반경도 임계를 못 넘기면 **가장 넓은 후보**를 쓴다(빈 지도보다 낫다) —
        #      다만 확대 사실·유효 반경을 응답에 실어 화면이 **반드시 고지**하게 한다.
        radius_requested_m = radius_m
        radius_expanded = False
        if auto_expand_radius and radius_applied:
            _dists_m: list[float] = []
            for _cat in categories.values():
                for _grp in _cat["groups"]:
                    _c = coords.get(_grp.get("_query"))
                    if not _c:
                        continue  # 좌표미확보 = 원천한계. 반경을 넓혀도 살아나지 않는다.
                    _dists_m.append(
                        PostGISHelper.st_distance(center_lat, center_lon, _c["lat"], _c["lon"]) * 1000.0
                    )
            _candidates = [radius_m] + [r for r in _RADIUS_LADDER_M if r > radius_m]
            _chosen = None
            for _cand in _candidates:
                if sum(1 for d in _dists_m if d <= _cand) >= _AUTO_EXPAND_MIN_MARKERS:
                    _chosen = _cand
                    break
            if _chosen is None and _dists_m:
                _chosen = _candidates[-1]
            if _chosen is not None and _chosen != radius_m:
                radius_m = _chosen
                radius_expanded = True

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
                    # ★거리를 **버리지 않는다** — 이미 계산해 놓고 판정에만 쓰고 폐기했다.
                    #   분양(presale) 그룹은 이미 `distance_m` 을 싣고 화면이 "1.2km" 로 쓴다
                    #   (같은 응답 안의 선례). 실거래만 안 싣고 있었다.
                    grp["distance_m"] = round(dist_km * 1000.0)
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
            # ★★2026-08-22 — 정렬 2순위를 **거리**로 바꾼다(종전: 거래건수만).
            #
            # 왜: 캡(_MAX_GROUPS_PER_CAT)이 물 때 **무엇이 남는가**를 이 키가 정한다.
            # 종전 `-count` 는 이 파일이 스스로 적어 둔 대로 *"거래 많은 단지 쪽으로 편향"* 된다 —
            # 실측(강남 1km): 6개 카테고리가 전부 28개로 잘린다. 그때 남는 28은 **대형 단지**이고,
            # 개발자가 보려는 **인근 소규모 필지·토지 거래가 밀려난다.**
            # 지도의 목적은 "이 부지 **주변**"이므로 남길 기준은 **가까움**이어야 한다.
            #
            # ★계산 표본에는 영향이 없다 — `D-2 전환` 으로 `_in_radius_groups`(AVM·탁상감정)는
            #   **캡 이전 전량**이고, 정렬은 집합이 아니라 **순서**만 바꾼다. 금액 불변이다.
            # ★거리 미상(반경 미적용 등)은 뒤로 보낸다 — 없는 값을 0 으로 취급하면
            #   좌표 없는 그룹이 "가장 가깝다"가 되어 정반대로 오염된다(무날조).
            resolved.sort(
                key=lambda x: (
                    _precise_first.get(x.get("coord_precision"), 1),
                    x.get("distance_m") if x.get("distance_m") is not None else float("inf"),
                    -x["count"],
                )
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
            # ★★D-2 전환 — **계산 표본과 표시 표본을 분리한다.**
            #   `_MAX_GROUPS_PER_CAT` 은 선언부가 스스로 "마커 상한·페이로드 축소"라고 밝히는
            #   **표시용 상수**인데 종전엔 그것이 AVM 표본까지 결정했다. 프로덕션 계측 결과
            #   (5표본 전부 음수 · −3.2 ~ −6.75%) **부호 일관성**이 확인돼 전환한다.
            #   - 계산 표본(`_in_radius_groups`) = **캡 이전** 반경통과 정밀분 전량
            #   - 표시 표본(`_in_radius_groups_display_capped`) = 종전과 동일(캡 적용분)
            #   `count_in_radius` 등 **표시 계약은 캡 기준 그대로** 둔다 — 실제로 응답에 실리는
            #   `groups` 배열이 캡 적용분이므로, 그 배열을 설명하는 카운트는 캡 기준이어야 한다.
            #   두 수가 다른 것이 정상이며, 그 차이는 `capped_group_count` 와
            #   `avm.basis.display_capped_group_count` 가 설명한다.
            cat["_in_radius_groups"] = [
                g for g in resolved if g.get("coord_precision") != "dong"
            ]
            cat["_in_radius_groups_display_capped"] = precise
            # ★D-2 그림자 계측 — **표시용 상한이 추정기 표본을 결정하고 있다.**
            #   `_MAX_GROUPS_PER_CAT` 은 선언부가 스스로 "카테고리별 **마커** 상한 —
            #   지오코딩 부하·**페이로드 축소**"라고 밝히는 표시/전송용 상수인데, `precise` 가
            #   `capped` 에서 나오므로 그 상수가 AVM·탁상감정 표본까지 자른다.
            #   라이브 실측(2026-08-05 역삼동): 반경 1,500m·6개월에서 `apt_trade` 의 반경 통과
            #   **정밀** 그룹 52개 중 **24개(46%)가 표시 상한 때문에 폐기**됐다.
            #   ★리뷰 A-2 정정 — 초판은 이 파라미터를 "탁상감정 자신의 것"이라 썼는데,
            #     탁상감정은 이 페이로드에서 **`land_trade` 만** 읽고 `avm` 은 쓰지 않는다
            #     (`desk_appraisal_service`). 파라미터가 같다는 것과 **같은 카테고리를 본다는 것은
            #     다른 말**이다. 아래 그림자 계측의 **가격 델타는 `apt_trade` 한정**이고,
            #     `land_trade` 는 **절단량만**(`truncation_by_category`) 관측한다.
            #   그리고 그 절단은 `-count` 정렬이라 **거래 많은 단지 쪽으로 편향**된다.
            #   ★그런데 이 값은 사용자에게 보이는 **시세·감정 단가**다. 계측 없이 바꾸면
            #     "얼마나 달라지는지 모르는 채" 금액을 흔드는 것이다 — M-4 에서 큰 숫자(73.8%)를
            #     보고 처방부터 세웠다가 한계수율이 사실상 0 이었던 실수를 그대로 반복하게 된다.
            #   → **이 PR 은 아무 금액도 바꾸지 않는다.** 캡 없는 표본으로 같은 산식을 돌린 값을
            #     진단 전용으로 병기해 프로덕션에서 **델타를 먼저 재고**, 그 근거로 전환을 판정한다.
            #   페이로드 비용 0 — 이 필드는 응답 직전 제거된다(`_in_radius_groups` 와 동일).
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
                # ★★"왜 표본이 0인가"를 소비처가 **말할 수 있게** 한다.
                #   마스킹 지번 그룹은 질의를 만들 수 없어(`_query_for`) 좌표가 없고,
                #   따라서 `located_count` 에 들어오지 못한다. 그 사실이 응답에 없으면
                #   소비처는 "거래가 없다"와 "거래는 있는데 원천이 지번을 가려서 위치를 못
                #   잡는다"를 **구분할 수 없고**, 탁상감정은 사유 없이 공시지가로 폴백한다.
                #   실측: `land_trade`·`house_trade` 는 이 값이 그룹 전량과 같다.
                #
                #   ★★R1 리뷰(M-1) — 단위를 **`capped_*` 선례와 동일하게** 둘로 가른다.
                #   `sample_basis` 의 카운트는 전부 **거래 건수** 계약인데(같은 파일 :515 가
                #   H-4 재발 방지로 명문화) 초판은 여기에 **그룹 수**를 넣고 소비처가
                #   "거래 N건"이라고 렌더했다 — H-4("표시 상한 초과 7건이라 써놓고 실제 15건")와
                #   **같은 형태의 단위 혼입**이다. 라벨이 쓰는 값은 건수로 주고, 그룹 수는
                #   이름을 분리해 보존한다.
                "masked_jibun_count": sum(
                    int(g.get("count") or 0)
                    for g in cat["groups"]
                    if _is_masked_jibun(g.get("jibun"))
                ),
                "masked_jibun_group_count": sum(
                    1 for g in cat["groups"] if _is_masked_jibun(g.get("jibun"))
                ),
                # ★★2026-08-06 실측 — 표본에 **지분거래가 몇 건 섞였는지**. 원천이 주는
                #   구분인데 종전엔 파서에서 버려 아무도 알 수 없었다.
                #   ★왜 제외가 아니라 계측인가: 같은 (동·지번·금액·면적·날짜)가 최다 29회
                #   반복되는데, 이것이 **중복 신고**인지 **한 필지를 여럿이 나눠 산 실제
                #   지분거래**인지 우리는 **구분할 수 없다**. 구분할 수 없는 것을 지우면
                #   실거래를 없애게 된다(무날조). 지금 할 수 있는 정직은 "무엇이 섞여
                #   있는지 말하는 것"이고, 제외·가중은 그 다음 판단이다.
                "share_deal_count": sum(
                    int(g.get("share_deal_count") or 0) for g in cat["groups"]
                ),
                # ★해제 건수(카테고리 합) — 소비처가 **알고 판단**할 수 있게 노출한다.
                #   형제(지분)와 같은 원칙: **세되 버리지 않는다**.
                "cancelled_count": sum(
                    int(g.get("cancelled_count") or 0) for g in cat["groups"]
                ),
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
        # ★D-2 그림자 계측 — 표시 상한이 **없었다면** 같은 산식이 얼마를 냈을지 병기한다.
        #   `avm` 자체는 **한 글자도 바뀌지 않는다**(전환은 이 델타를 프로덕션에서 읽은 뒤).
        # ★D-2 전환의 변화량을 관측 가능하게 한다. 금액을 바꾸는 변경이므로 "얼마나
        #   달라졌나"를 응답이 스스로 말해야 한다.
        #     legacy    = 표시캡 표본 + 무절사 (= 전환 **이전** 사용자가 보던 값)
        #     canonical = 캡 해제 표본 + 무절사 (= 전환 **이후** 값, `avm_summary`)
        #     trimmed   = 캡 해제 표본 + 트림   (= **미채택** 후보 — 진단 전용)
        avm_legacy = self._compute_avm_summary(
            categories.get("apt_trade"), radius_applied=radius_applied, radius_m=radius_m,
            sample_field="_in_radius_groups_display_capped", robust=False,
        )
        # ★★리뷰 C-2 봉합 — **트림은 정본에서 뗀다.** 캡 해제는 프로덕션 6표본 계측 후
        #   전환했는데 트림은 **계측 0 으로 즉시 정본화**했다 — 이 커밋이 삭제한 주석에
        #   내가 직접 적어둔 규율("계측 없이 바꾸면 얼마나 달라지는지 모르는 채 금액을
        #   흔드는 것")을 트림에만 적용하지 않은 것이다. 두 변경이 같은 기준을 받아야 한다.
        #   → 트림은 **진단 전용**으로만 계산해 델타를 프로덕션에서 먼저 재고,
        #     부호·크기 일관성을 확인한 뒤 별도 PR 로 전환한다.
        avm_trimmed = self._compute_avm_summary(
            categories.get("apt_trade"), radius_applied=radius_applied, radius_m=radius_m,
            robust=True,
        )
        display_cap_impact = _display_cap_impact(
            categories, avm_summary, avm_legacy, avm_trimmed,
            radius_applied=radius_applied,
        )
        for _cat in categories.values():
            _cat.pop("_in_radius_groups", None)
            _cat.pop("_in_radius_groups_display_capped", None)

        result: dict[str, Any] = {
            "center": center or {"lat": None, "lon": None, "address": address},
            # ★확대가 일어났으면 여기 값은 **실제로 필터에 쓴** 반경이다(요청값 에코 아님).
            #   화면의 원·라벨이 실제 필터와 어긋나지 않게 하려면 이 값이어야 한다.
            "radius_m": radius_m,
            "radius_requested_m": radius_requested_m,
            "radius_expanded": radius_expanded,
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
            # ★질의를 만들지 못해 **시도 자체를 안 한** 그룹 수(분모에서 빠진 몫).
            #   이 수가 없으면 실패율 개선이 진짜인지 분모 축소인지 판별할 수 없다.
            "geocode_unqueryable_group_count": unqueryable_groups,
            # ★토지 층화 통계 — 좌표가 없어 반경으로는 못 말하는 것을 **행정구역+용도** 축으로
            #   말한다. 값이 아니라 **값과 그 값이 무엇인지**를 함께 싣는다(층·표본수·시점수정
            #   여부·지분 제외 건수). 표본이 모자라면 `None` — 없는 것을 만들지 않는다.
            #   ★이 값은 **참고 통계**다. 채택 단가를 바꾸지 않는다(소비처가 그렇게 표시해야 한다).
            "land_dong_stats": land_dong_stats_out,
            # ★리뷰 M-1 — 이번 PR 이 새로 넣은 변수(힌트)도 관측 대상이다. 힌트가 비면
            #   전 행이 조용히 중개사 시군구로 회귀하는데, 응답만 봐서는 구분이 안 됐다.
            "sigungu_hint": sigungu_hint,
            "sigungu_source": "hint" if sigungu_hint else "row_fallback",
            "geocode_precut_count": geocode_precut,
            # ★M-4 계측 — `sigungu_hint`/`sigungu_source` 와 **대칭**으로 동 프라이어도
            #   관측한다. 종전엔 힌트 축만 노출돼, `sigungu_source == "hint"`(정상)인데
            #   동 프라이어만 꺼져 있는 조합이 "전부 정상"으로 보였다. 두 힌트는 서로
            #   **독립적으로 실패**하고 실패 모드가 다르다(시군구=질의 정확도, 동=정렬 우선순위).
            # ★이름에 `_hint` 를 박는 이유: 이 값은 PNU/bcode 에서 온 **권위값이 아니라**
            #   입력 문자열 휴리스틱이다. 소비처가 "대상 법정동"으로 렌더하면 주소 오타가
            #   사실로 승격된다(`sigungu_hint` 와 같은 판단).
            "target_dong_hint": target_dong,
            "target_dong_source": _target_dong_source(address, target_dong),
            # ★신구 카운터의 **무성 발산**을 스스로 고발한다. 카테고리별 `groups_cut` 합과
            #   위 스칼라가 갈라지면 둘 중 하나가 틀린 것인데, 런타임 assert 는 계측이
            #   본로직을 죽이는 것이라 쓰지 않는다(관측 장치 제1원칙). 대신 응답에 실어
            #   판독자가 즉시 알게 한다 — 정상 상태에서는 항상 False 여야 한다.
            "precut_accounting_mismatch": _precut_accounting_mismatch(categories, geocode_precut),
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
            # ★D-2 **진단 전용**(표시 금지) — 표시용 상한 `_MAX_GROUPS_PER_CAT` 이 표본을
            #   얼마나 자르고 시세를 얼마나 움직이는지. `avm` 이 정본이며 이 PR 은 그것을
            #   바꾸지 않는다. 이 델타를 프로덕션에서 읽은 뒤에 전환 여부를 판정한다.
            #   ★가격 델타는 `apt_trade`(AVM) 한정이고, **절단량은 전 카테고리**로 싣는다
            #     (`truncation_by_category`) — 탁상감정은 `land_trade` 를 쓰므로 apt 만 보면
            #     돈에 더 가까운 쪽이 미계측으로 남는다(리뷰 A-2).
            "display_cap_impact": display_cap_impact,
        }

        # ★D9 — 감쇠 사슬을 **한 줄로**. 위 키들에 사유가 다 들어 있었지만 여섯 군데에
        #   흩어져 있어 사용자가 조립할 수 없었다(라이브: 원본 2,350곳 → 표시 209곳인데
        #   화면은 209 만 말했다). 재계산은 하지 않는다 — 이미 조립된 값을 엮기만 한다.
        #   판단을 **순수 함수로 꺼내** 두었으므로 이 줄은 배선이고, 락은 따로 있다.
        result["sample_attenuation"] = build_sample_attenuation(result)

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
        # ★마스킹 지번은 **없는 것으로 취급**한다 — `"논현동 5*"` 는 어떤 지오코더로도
        #   필지에 매칭될 수 없다. 그대로 질의하면 (1)예산을 매칭 불가 질의에 쓰고
        #   (2)`not_found` 계측을 오염시키며 (3)정밀도가 `parcel` 로 시작했다가
        #   `_refined_mismatch` 로 강등되는 **두 단계 거짓**이 된다.
        #
        # ★★R1 리뷰(C-1·C-2) 봉합 — 초판은 여기서 **건물명·동 대표점 폴백으로 넘어갔다**.
        #   그것이 더 큰 결함 둘을 만들었다:
        #   (C-1) 동 대표점을 붙이면 그룹이 `unresolved` 가 아니라 `resolved` 가 되어
        #         **반경 판정 대상**이 된다. 대표점이 반경 밖이면 실거래가 응답에서
        #         **삭제**되고, 어떤 카운트에도 남지 않아 사유가 "수집된 거래가 없습니다"로
        #         나온다 — 이 봉합이 없애려던 **바로 그 거짓 문장**이다. 같은 파일이
        #         "좌표 미확보는 제외하지 않고 보존한다(**반경 밖 단정 금지**)"라고
        #         계약을 명문화하고 있고, 아래 `_query_grain` 독스트링은 그 좌표를 두고
        #         "반경 안팎 판정에 쓸 수 없다"고 말한다. 쓸 수 없다고 선언한 좌표로
        #         삭제 판정을 내린 것이다.
        #   (C-2) 건물명 폴백은 `building` 정밀도를 얻어 **AVM 표본에 새로 편입**된다 —
        #         계측도 고지도 없이 사용자가 보는 금액이 움직인다(리뷰어 실측 +100%).
        #
        #   ★그래서 **질의 자체를 만들지 않는다**(`""`). 좌표 미확보로 남아 종전처럼
        #   보존되고(반경 밖 단정 없음·AVM 편입 없음), 매칭 불가 질의에 예산도 쓰지 않는다.
        #   위치를 모르는 것이 **사실**이므로, 아는 척하는 대신 그 사실을 말한다
        #   (`sample_basis.masked_jibun_*` → `no_sample_reason`).
        if jibun and _is_masked_jibun(jibun):
            return ""
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

        ★D-1 봉합 — 종전엔 **주소 전체**를 훑으며 마지막 매치를 채택해, 지번 **뒤에** 오는
        동/호 표기가 법정동을 덮어썼다:
          "서울특별시 강남구 역삼동 736 101동 502호" → "101동"  (기대: "역삼동")
        `101동` 은 `umdNm` 과 **영영 매칭되지 않으므로**, 사전컷 프라이어의 1순위 항이 전
        그룹에서 상수 1로 붕괴해 순수 건수 정렬(= W2 이전 동작)로 **무음 회귀**한다.
        오좌표를 만들지는 않지만(매칭이 안 될 뿐) 기출하 최적화가 조용히 꺼진다.
        법정동은 **지번보다 앞**에 오므로, 지번 토큰(숫자 시작 또는 "산"+숫자)을 만나면
        거기서 멈춘다. 도로명 주소가 빈 문자열이 되는 기존 동작은 그대로 유지된다.
        """
        best = ""
        for tok in (address or "").split():
            # 지번 도달 — 이 뒤의 동/호·건물 표기는 법정동이 아니다.
            if tok[:1].isdigit() or (tok[:1] == "산" and tok[1:2].isdigit()):
                break
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
        # ★마스킹 지번(`"5*"`)으로는 불일치를 **판정할 수 없다** — 우리가 그 지번으로 질의하지도
        #   않았고, 매칭 주소에 `*` 가 들어 있을 리도 없다. 판정 불가를 "불일치"로 쓰면
        #   모르는 것을 근거로 강등하는 것이라 무날조 원칙에 어긋난다(`refined` 부재와 동일 취급).
        #   ★R2 리뷰(L-2) 정직 표기 — 현재 이 가드는 **도달 불가**다. 마스킹 그룹은 질의가
        #   빈 문자열이라 지오코딩 대상이 아니고, 따라서 이 함수가 마스킹 그룹으로 호출되는
        #   경로가 없다. 방어로 남기되 **도달 불가라는 사실을 밝힌다** — 여기 붙은 단위
        #   테스트를 "배선을 잠갔다"로 세면 변이 점수를 부풀리게 된다.
        if jibun and not _is_masked_jibun(jibun) and jibun not in refined:
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
        # ★마스킹 지번은 **질의 자체를 만들지 않는다**(`_query_for` 참조) — 어떤 입도도
        #   가리키지 않으므로 전용 값으로 말한다. `"dong"` 으로 뭉뚱그리면 "동 대표점은
        #   받았다"로 읽혀, 좌표가 아예 없다는 사실이 관측에서 사라진다.
        if jibun and _is_masked_jibun(jibun):
            return "masked"
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
                # ★R5(H-2) — 질의 확정에 쓸 **실재 쌍**과 원본 건물명.
                "_pairs": set(), "_name_raw": name, "_share_deals": 0, "_cancelled": 0,
                "deals": [], "_prices": [], "_areas": [],
            })
            # ★W1-b 리뷰(H-3) — 빈 dong 도 **센티널로 기록**한다. 종전엔 빈 값을 그냥 건너뛰어,
            #   "법정동을 모르는 행"이 섞여도 `_dongs` 크기가 1로 남아 정밀 좌표로 분류됐다.
            #   동을 모르는 행이 섞인 것과 여러 동이 섞인 것은 **같은 위험**이다(그룹 대표
            #   좌표가 일부 행만 대표한다).
            g["_dongs"].add(dong)
            # ★★R5 리뷰(H-2) — **실재하는 (시군구·동·지번) 쌍만** 후보로 모은다.
            #   자세한 이유는 `_resolve_group_queries` 독스트링 참조.
            g["_pairs"].add((sigungu, dong, jibun))
            # ★2026-08-06 — 지분거래 건수를 센다. 원천(`shareDealingType`)이 주는 구분인데
            #   종전엔 파서에서 버려 **지분과 일반이 한 통에** 섞였다. 단가 차이가 지역마다
            #   방향까지 다르므로(강남 0.27배 · 포항북 2.14배) 섞인 채로는 대표값을 말할 수 없다.
            if str(r.get("share_dealing_type") or "").strip() == "지분":
                g["_share_deals"] += 1
            # ★2026-08-26 — **해제된 계약 건수**를 센다(형제 지분거래와 같은 원칙: 세되 버리지
            #   않는다). 원천 `cdealType` 이 주는데 종전엔 파서에서 버려, **해제된 거래가
            #   정상 거래로** 지도에 찍히고 시세 표본에 섞였다.
            #   ★라이브 실측: 해제 1.95%(68/3,482) · 해제 평균이 정상 대비 **+11.5%**(고가 편향).
            #     전체 평균 왜곡은 0.22% 로 작지만 **개별 마커가 거짓**이고 소표본에서 증폭된다.
            if r.get("is_cancelled"):
                g["_cancelled"] += 1
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
        self._resolve_group_queries(groups)
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
                # ★R5 리뷰(F-1) — 전월세도 **같은 헬퍼**를 탄다. 바로 윗줄 주석이
                #   "한쪽만 고치면 비대칭이 남는다"고 스스로 경고해 뒀는데 R4 에서
                #   매매만 고쳤다(전역 전파방지 미이행). 이번엔 공용화로 봉합한다.
                "_pairs": set(), "_name_raw": name, "_share_deals": 0, "_cancelled": 0,
                "deals": [], "_deposits": [], "_monthlies": [], "_areas": [],
            })
            # ★W1-b 리뷰(H-3) — 빈 dong 도 **센티널로 기록**한다. 종전엔 빈 값을 그냥 건너뛰어,
            #   "법정동을 모르는 행"이 섞여도 `_dongs` 크기가 1로 남아 정밀 좌표로 분류됐다.
            #   동을 모르는 행이 섞인 것과 여러 동이 섞인 것은 **같은 위험**이다(그룹 대표
            #   좌표가 일부 행만 대표한다).
            g["_dongs"].add(dong)
            g["_pairs"].add((sigungu, dong, jibun))
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
        self._resolve_group_queries(groups)
        return self._finalize(type_key, label, "rent", groups)

    def _resolve_group_queries(self, groups: dict[str, dict[str, Any]]) -> None:
        """그룹의 지오코딩 질의를 **실재하는 행에서, 결정론적으로** 확정한다.

        ## 왜 이 함수가 있는가 — 두 결함을 한 번에 없앤다

        그룹 키가 `name or jibun or dong` 이라 **같은 건물명이 여러 법정동·여러 지번에
        걸치면 한 그룹으로 병합**된다(래미안·자이·e편한세상 …). 종전에는 질의를
        `setdefault` 시점, 즉 **첫 행**으로 정했다.

        ★R4(H-2) 첫 결함 — 첫 행이 마스킹이면 단지 전체가 좌표를 잃었다. MOLIT 응답
        순서는 우리가 통제하지 않으므로 **AVM 표본이 들어왔다 나갔다** 했다(시세 비결정성).

        ★★R5(H-2) 두 번째 결함 — 그 봉합이 더 나쁜 것을 만들었다. "비마스킹 지번을 만나면
        승격"하면서 **첫 행의 동 + 승격 행의 지번**을 짝지어, **어느 거래에도 존재하지 않는
        주소**를 합성해 지오코더로 보냈다. 리뷰어 실측: `(래미안,5*,논현동)` + `(래미안,736,
        역삼동)` → `"경상북도 남구 논현동 736"`. 실재하지만 **무관한 필지**에 핀이 찍히고,
        라벨은 "위치 개략(동 단위)"이라며 오차를 축소해 말한다. 좌표가 없어 정직했던 상태가
        **아는 척하는 상태**로 바뀐 것이라, 이 PR 의 존재 이유를 새 경로에서 위반했다.

        ★R5(F-2) 세 번째 — 승격은 비마스킹 지번이 **1개일 때만** 순서 무관이었다.
        2개 이상이면 여전히 "첫 행 승"이라 6순열이 2가지 결과를 냈고, 동이 같으면
        `parcel`→located→**AVM 편입**이라 금액 경로에 비결정성이 살아 있었다.

        ## 그래서 이렇게 한다

        행을 돌며 **실재하는 `(시군구, 동, 지번)` 3튜플만** 모아 두고, 순회가 끝난 뒤
        그 집합에서 하나를 고른다.

        - 후보는 **한 행에서 통째로** 온다 → 합성이 원천적으로 불가능하다.
        - 지번을 쓸 수 있는 쌍(마스킹 아님)을 우선한다 → 정보가 많은 쪽이 이긴다.
        - `sorted(...)[0]` 으로 고른다 → **행 순서와 무관**하게 항상 같은 답이다.
          (어느 쌍이 "옳은지"는 알 수 없다. 알 수 없을 때 필요한 것은 정답이 아니라
          **재현성**이다 — 같은 데이터가 같은 화면을 내야 한다.)
        """
        for g in groups.values():
            pairs = g.pop("_pairs", set())
            name = g.pop("_name_raw", "")
            if not pairs:
                # ★R6 리뷰(F-E) 정직 표기 — 이 가지는 **도달 불가**다. 모든 `setdefault`
                #   직후에 `_pairs.add(...)` 가 무조건 실행되므로 빈 그룹이 생기지 않는다
                #   (리뷰어 계측: 빈 rows·전필드 공백·None 등 5형태에서 빈 그룹 0개).
                #   방어로 남기되, 이걸 "순서의존 폴백"으로 읽지 않도록 밝힌다.
                continue
            sigungu, dong, jibun = _pick_representative_pair(pairs)
            g["dong"], g["jibun"] = dong, jibun
            # ★R6 리뷰(F-A) — 건물명이 **없어 파생된** 이름은 대표 쌍을 따라가야 한다.
            #   `name` 은 `setdefault`(첫 행) 때 `f"{dong} {jibun}"` 으로 만들어지는데
            #   대표만 바꾸면 **한 팝업에 서로 다른 두 주소**가 뜬다(리뷰어 실측:
            #   제목 "역삼동 736" 아래 부제 "논현동 736 · 2건" — SatongMultiMap:766-767 이
            #   `name` 과 `dong/jibun` 을 나란히 그린다).
            #   ★원본 건물명이 있으면 건드리지 않는다 — 그건 행에서 온 진짜 이름이다.
            if not name:
                g["name"] = f"{dong} {jibun}".strip() or "물건"
            g["_query"] = self._query_for(sigungu, dong, jibun, name)
            g["_query_grain"] = self._query_grain(jibun, name)

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
            # ★지분거래 건수 — 그룹 대표값이 무엇으로 이뤄졌는지 소비처가 알 수 있게 한다.
            g["share_deal_count"] = g.pop("_share_deals", 0)
            # ★해제 건수도 같은 자리에서 내부키(`_cancelled`) → 공개키로 승격한다.
            g["cancelled_count"] = g.pop("_cancelled", 0)
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
            if _grain == "masked":
                # ★R2 리뷰(M-1) — `"masked"` 를 `else` 로 흘려보내면 `"dong"` 이 박힌다.
                #   그러면 `_query_grain` 독스트링이 막겠다고 선언한 상태("동 대표점은
                #   받았다"로 읽히는 것)가 **그대로 출하된다** — 좌표가 아예 없다는 사실이
                #   관측에서 사라진다. 선언한 구분을 실제 응답까지 전달한다.
                # ★★R3 리뷰(F-1) — 이 검사가 `len(_dongs) > 1` **아래**에 있어 봉합이
                #   절반만 도달했다. 그룹 키가 `name or jibun or dong` 이라 같은 마스킹
                #   리터럴(`"5*"`)이 서로 다른 법정동에서 오면 **한 그룹으로 병합**되고
                #   `_dongs` 가 2가 돼 `"dong"` 이 박혔다. 마스킹 지번은 짧아서 동 간
                #   충돌이 흔하므로 오히려 지배적 갈래일 수 있다.
                #   ★질의를 만들지 않았으므로 **병합 여부와 무관하게 좌표가 없다** —
                #   병합 검사보다 위에 두는 것이 옳다.
                g["coord_precision"] = "masked"
            elif len(_dongs) > 1:
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
        sample_field: str = "_in_radius_groups",
        robust: bool = False,
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
            # ★D-2 그림자 계측 — 기본값은 종전과 **완전히 동일**(`_in_radius_groups`).
            #   `sample_field` 는 "표시 상한이 없었다면 얼마였을까"를 같은 산식으로 재계산하기
            #   위한 주입점일 뿐이며, 이 인자를 주지 않는 호출부의 동작은 한 글자도 바뀌지 않는다.
            groups = cat.get(sample_field) or []
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
        pp_unweighted: list[float] = []      # 트림 **밴드** 산출용 — 그룹당 1개(비가중)
        pp_pairs: list[tuple[float, int]] = []  # (평당가, 건수) — 가중평균 산출용
        for g in groups:
            avg_price_10k = g.get("avg_price_10k")
            avg_area_m2 = g.get("avg_area_m2") or 0
            if avg_price_10k and avg_area_m2 > 0:
                per_pyeong = avg_price_10k / (avg_area_m2 / PYEONG_SQM)
                cnt = g.get("count") or 1
                pp_sum += per_pyeong * cnt
                pp_n += cnt
                # ★D-2 동반 — **그룹 간** 이상치 트림용 표본. `robust_price_stats` 는
                #   `_finalize` 에서 그룹 **내부** 거래에만 걸려 있었고, 그룹 사이는 무보정이었다.
                #   표시 캡을 풀어 표본을 늘리면 소량·이질 그룹이 대거 들어오므로 그 구멍이
                #   그대로 노출된다("표본만 늘리면 더 정확"이 자명하지 않은 이유).
                #   건수 가중을 유지하려고 그룹당 `cnt` 개로 확장해 넣는다(새 산식이 아니라
                #   기존 공용 헬퍼 재사용 — 로그 IQR·표본 8건 미만 트림 생략 규약 그대로).
                #   ★★리뷰 C-1 봉합 — 밴드는 **비가중 그룹 표본**에서 산출한다.
                #     종전엔 건수만큼 확장한 표본으로 사분위를 계산했는데, 그러면 **거래가 많은
                #     그룹이 사분위 구간을 점유**해 밴드가 그쪽으로 붕괴하고 **정상 이웃 단지가
                #     이상치로 제거**된다. 리뷰어 실측: 가격 집합은 그대로 두고 **건수 분포만**
                #     바꿨더니 제외 판정이 완전히 달라졌다(−10.16% / 0% / +5.62%).
                #     즉 그건 이상치 판정이 아니라 **거래량 편중 판정**이었다.
                #   ★`robust_price_stats` 는 `int(p)` 절단(만원 정수 입력 전제)이므로 실수인
                #     평당가는 **100배 스케일**로 넣고 되돌려 절단 편차를 제거한다.
                pp_unweighted.append(per_pyeong * _PP_SCALE)   # 밴드 산출용(그룹당 1개)
                pp_pairs.append((per_pyeong, int(cnt)))        # 가중평균용
        if pp_n <= 0:
            return None

        outliers_excluded = 0
        if robust and pp_unweighted:
            _pp = robust_price_stats(pp_unweighted)
            # ★트림이 **아무것도 제거하지 않았으면 추정치도 바뀌지 않아야 한다.**
            #   `robust_price_stats` 를 경유하면 스케일 왕복·정수 반올림으로 값이 미세하게
            #   움직이는데(실측 0.0002%), 그러면 "트림 미발동인데 값이 변했다"는 설명 불가능한
            #   상태가 된다. 제외 0 건이면 **원래 가중평균을 그대로** 쓴다 — 이 판정의 부작용을
            #   0 으로 만들고, `delta_pct_from_outlier_trim == 0.0` 이 **정확히** 참이 된다.
            if _pp["avg"] > 0 and _pp["excluded"] > 0:
                # ★밴드는 비가중으로 정하되, **평균은 건수 가중**으로 낸다 — 살아남은 그룹만
                #   원래 가중치로 다시 평균한다(트림이 가중 구조를 바꾸지 않는다).
                # ★★리뷰 CRITICAL 봉합 — 경계 비교를 **정수로** 맞춘다.
                #   `robust_price_stats` 는 `int(p)` 로 절단한 값에서 min/max 를 돌려주므로
                #   `_hi` 는 정수인데 비교 대상 `v * _PP_SCALE` 은 실수다. 그래서 **최고 생존
                #   그룹이 자기 자신을 밴드 밖으로 판정**해 매번 추가 탈락했다 —
                #   그것도 **최고가 정상 단지**를, 보고 없이(제외 수는 밴드 판정분만 셌다).
                #   리뷰어 몬테카를로: 발동 건의 **100%** 가 정확한 트림과 불일치, 후보 델타
                #   **부호가 22.3% 뒤집힘**, 평균 편향 −1.90%(최악 −21.21%).
                #   ★이건 직전 REJECT 의 C-1 과 **같은 피해 클래스**(정상 고가 단지 삭제)이고
                #     원인만 "거래량 편중"에서 "정수 절단"으로 바뀐 것이다.
                _lo, _hi = int(_pp["min"]), int(_pp["max"])
                _kept = [(v, c) for v, c in pp_pairs if _lo <= int(v * _PP_SCALE) <= _hi]
                _kn = sum(c for _v, c in _kept)
                # ★자기정합 불변식 — **밴드가 남긴 그룹 수 == 평균에 실제로 들어간 그룹 수.**
                #   이 확인이 없어서 밴드 판정과 평균 산출이 **다른 집합**을 써도 통과했다.
                #   이번 결함의 단일 근원이다. 어긋나면 보고값을 실제 탈락 수로 정직 교정한다
                #   (조용히 숨기지 않는다 — 관측 장치는 자기 오차를 말해야 한다).
                _actually_dropped = len(pp_pairs) - len(_kept)
                # ★등가변이 정직 고지 — 아래 (2)는 **무조건** 등가이고, (1)은 **조건부**로만
                #   등가다. 헤더에서 둘을 뭉뚱그리면 스캔하는 독자가 (1)까지 무조건이라고
                #   오독한다(#554 리뷰 LOW-1: 초판 헤더가 "어떤 입력으로도 잡히지 않는다"는
                #   **철회된 절대 주장**을 그대로 이고 있었다 — 6줄 아래에서 철회되는데도).
                #     (1) **조건부 등가** — `_actually_dropped` vs `_pp["excluded"]` 는
                #         `int(per_pyeong*100) > 0` **인 한** 같다(`core ⊆ vals`, 밴드가
                #         `min(core)`~`max(core)`). 그 조건이 깨지면 **갈린다**(아래 반증).
                #         ★리뷰 반증 — 내 초판 증명은 `robust_price_stats` 의 **사전 필터**
                #           (`price_stats.py`: `int(p) > 0` 인 값만 `vals` 에 넣는다)를 빠뜨렸다.
                #           `int(per_pyeong*100) == 0` 인 초미세 그룹은 `excluded` **분모에 안
                #           들어가는데** `pp_pairs` 에는 남아 `_kept` 에서 탈락한다 → 두 값이
                #           1 만큼 갈린다(리뷰어 반례 실측). **그때 정직한 값은 `_actually_dropped`
                #           쪽이고 이 코드가 채택한 것이 그것이다.**
                #         ★즉 "어떤 입력으로도 잡히지 않는다"는 **거짓**이었다 — 무작위 3,000회
                #           반례 0 은 사실이지만 그 표본이 해당 클래스를 포함하지 않았을 뿐이다.
                #           ★"반례를 못 찾았다"를 "반례가 없다"로 승격한 것이 오류의 형태다.
                #           (도달 조건: `avg_area_m2 > PYEONG_SQM × 100 × avg_price_10k`
                #            ≈ `330.5785 × avg_price_10k`. #554 리뷰 LOW-2 — 초판은 `330` 이라
                #            썼는데 330~330.58 구간은 조건을 만족해도 발산하지 않는다.
                #            발산 집합은 `int(per_pyeong*100) == 0` 이 아니라 **`<= 0`** 이다
                #            — 음수 가격까지 덮는다(LOW-3). MOLIT 아파트 매매에서는 사실상
                #            불가하나 **없다고 단정할 근거가 아니다**.)
                #     (2) **무조건 등가** — `_kn > 0` 가드 — `min(core)` 를 낸 그룹은 **반드시** 밴드 안이므로
                #         `_kept` 는 공집합이 될 수 없다(도달 불가·방어적).
                #   그래도 (1)은 **정직한 쪽**(실제 탈락 수)을 싣고 (2)는 남겨 둔다 —
                #   경계가 다시 어긋나면 (1)이 즉시 진실을 말하고 (2)가 죽음을 막는다.
                #   ★"변이가 안 잡힌다"를 "잠겼다"로 보고하지 않기 위해 근거를 여기 남긴다.
                if _kn > 0:
                    per_pyeong = sum(v * c for v, c in _kept) / _kn
                    outliers_excluded = _actually_dropped
                else:
                    per_pyeong = pp_sum / pp_n
            else:
                per_pyeong = pp_sum / pp_n
        else:
            per_pyeong = pp_sum / pp_n      # 만원/평(무절사 — 전환 전 동작 재현용)
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
            # ★그룹 간 이상치로 제외된 수(0 이면 트림이 발동하지 않았다는 **관측된 사실**).
            # ★단위를 이름에 박는다 — 밴드가 **비가중 그룹 표본**에서 나오므로 이건 **그룹 수**다
            #   (건수가 아니다). 종전 건수 가중 시절의 이름을 그대로 두면 판독자가 거래 수로 읽는다.
            "outlier_groups_excluded": outliers_excluded,
            "robust_applied": bool(robust),
            # ★근거 표기 — 이 시세가 **무엇으로부터** 나왔는지 소비처가 알 수 있어야 한다.
            "basis": {
                "radius_applied": radius_applied,
                "radius_m": radius_m,
                "in_radius_group_count": len(groups) if radius_applied else None,
                "scope": "in_radius" if radius_applied else "all_groups_radius_not_applied",
                # ★★D-2 — **계산 표본 ≠ 표시 표본**임을 계약으로 박는다.
                #   `sample_basis.located_count`(표시)와 위 `comparable_count`(계산)가 다른 것이
                #   정상이며, 그 차이가 곧 표시 상한이 잘라낸 양이다. 이걸 안 실으면
                #   두 수를 비교한 판독자가 "둘 중 하나가 틀렸다"고 읽는다.
                "sample_scope": "in_radius_precise_all",
                # ★★리뷰 M-1 봉합 — 종전엔 `capped_group_count` 를 실었는데 그건
                #   **정밀·동 대표점을 가리지 않은 전체 절단 수**이고, 이 주석이 설명하려는
                #   차이(계산 표본 − 표시 표본)는 **정밀분 기준**이다. 실측 불일치:
                #   정밀 10·동 40 → 필드 22 인데 AVM 이 캡으로 잃은 정밀 그룹은 **0**.
                #   ★`_display_cap_impact` 에서 고친 바로 그 결함(B-1)을 여기에 재도입했다.
                #   → 정밀 기준 차이를 싣고 이름도 그렇게 바꾼다.
                # ★리뷰 MINOR-1 — 표시 표본 키가 **없는** 직접 호출 경로에서는 이 차가
                #   "표본 전량이 절단됐다"는 정반대 문장이 된다. 미확보는 **None**(무날조).
                "dropped_precise_group_count": (
                    len((apt_trade_category or {}).get("_in_radius_groups") or [])
                    - len((apt_trade_category or {})["_in_radius_groups_display_capped"] or [])
                    if apt_trade_category and "_in_radius_groups_display_capped" in apt_trade_category
                    else None
                ),
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
                        # ★N-1 — 사유는 보존하되 **캐시 출처는 지우지 않는다**. F-2 가 사유를
                        #   되살리면서 "이건 캐시다"라는 신호를 없앴는데, 그러면
                        #   `geocode_failure_breakdown` 은 라이브 실패와 캐시된 실패를 **같은 키로
                        #   합산**하고 `geocode_attempt_breakdown` 은 라이브 시도만 센다(캐시 히트는
                        #   _fail 을 안 거친다). 워밍된 부정 캐시 구간에서 두 숫자를 대조하면
                        #   "질의 30건이 429 인데 시도는 0건"이 되고, 그 429 는 **최대 5분 전
                        #   단일 사건이 30개 질의로 증폭된 것**일 수 있다 — R-3 의 transient-first
                        #   편향과 같은 방향으로 중첩된다. 이 PR 의 유일한 목적(재시도 착수를
                        #   데이터로 판정)에 대해 첫 판정이 틀릴 수 있는 구조였다.
                        self._geo_fail("cached:" + ((val or {}).get("_fail") or "unknown"), query)
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
                # ★N-4 — 관측된 적 없는 사유를 채우지 않는다(무날조). 현재는 도달 불가한
                #   방어값이지만, 도달하면 "not_found" 라는 **거짓 관측**을 만든다.
                _cached_val = coord if coord else {"_fail": _final_reason or "unknown"}
                await r.setex(cache_key, ttl, json.dumps(_cached_val))
                await r.aclose()
            except Exception:
                pass
        return coord
