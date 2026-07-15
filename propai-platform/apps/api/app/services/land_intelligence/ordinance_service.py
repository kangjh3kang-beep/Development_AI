"""전국 지자체 도시계획조례 실시간 조회 서비스.

법제처 국가법령정보 공동활용 API를 활용하여
해당 시·군·구의 도시계획조례에서 건폐율/용적률 조례값을 자동 추출.

데이터 소스:
1. 법제처 자치법규 목록 조회 API (open.law.go.kr)
   - "{시군구명} 도시계획 조례" 검색 → 조례 일련번호 획득
2. 법제처 자치법규 본문 조회 API (data.go.kr/15058294)
   - 조례 본문에서 건폐율/용적률 조항 파싱
3. 정적 캐시 DB (API 실패 시 폴백)
   - 전국 주요 시·도 기본값 보유

참고 법률:
- 국토의 계획 및 이용에 관한 법률 시행령 제84조 (건폐율)
- 국토의 계획 및 이용에 관한 법률 시행령 제85조 (용적률)
- 각 지방자치단체 도시계획 조례
"""

import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# ★공용 퍼센트 파서 (전역 단일 진실원천) — 조례 본문의 건폐율/용적률 값을 뽑는다.
#   버그(라이브 재현): 기존 `(\d{1,4})퍼센트`는 천 단위 구분자를 못 읽어
#   '1,300퍼센트' → 300, '1 300퍼센트' → 300 으로 잘렸다(상업·준주거 고밀 용적률
#   1000%↑가 300~500%로 과소파싱 → 개발규모 심각 과소보고). 이 헬퍼로 모든
#   퍼센트 추출을 일원화해, 한 곳을 고치면 조례 파서 전역이 따라오게 한다.
#   (CLAUDE.md 버그수정 정책: 국소패치 금지, 공용화 추출.)
# ──────────────────────────────────────────────────────────────────────
#   패턴 설명(리뷰어 라이브검증):
#     · `\d{1,3}(?:[,\s]\d{3})+` = '1,300' / '1 300' / '1,234,567'(쉼표·공백 3자리 묶음)
#     · `\d{1,4}`               = '250' / '60' 같은 구분자 없는 평문 값(폴백)
#   추출 후 쉼표·공백을 제거해 정수로 변환한다.
_KR_PCT_RE = re.compile(
    r"(?:이하\s*)?(\d{1,3}(?:[,\s]\d{3})+|\d{1,4})\s*(?:퍼센트|%|프로)"
)


def _parse_kr_percent(text: str) -> int | None:
    """한국어 조례 퍼센트 표기(천 단위 구분자 허용)를 정수로 파싱한다.

    - '1,300퍼센트' → 1300, '1 300퍼센트' → 1300, '1,500 % 이하' → 1500
    - '250퍼센트' → 250, '60프로' → 60, '200%' → 200
    - 매칭 없으면 None(값 날조 금지 — 호출부가 정직 폴백).
    순수함수(외부 IO 없음)라 단위 테스트가 쉽다.
    """
    if not text:
        return None
    m = _KR_PCT_RE.search(text)
    if not m:
        return None
    # 천 단위 구분자(쉼표·공백)를 제거하고 정수화.
    return int(m.group(1).replace(",", "").replace(" ", ""))


def resolve_ordinance_region(address: str | None) -> str | None:
    """주소 → '도시계획조례 정본 레벨' 행정구역명(전 분석 공용 SSOT).

    ★법적 근거(국토의 계획 및 이용에 관한 법률 제77조 건폐율·제78조 용적률): 용도지역
    건폐율·용적률을 도시·군계획조례로 정하는 주체는 특별시장·광역시장·특별자치시장·
    특별자치도지사·시장·군수다. 자치구(서울 강남구·부산 해운대구 등)는 용적률/건폐율
    도시계획조례가 없다 → 자치구로 조회/딥링크하면 '연결 안됨'·값 미로드가 발생한다.
      · 특별시/광역시/특별자치시 → 그 시 본청(예: '서울특별시')이 정본.
      · 도 산하 → 시/군(예: '용인시'·'가평군')이 정본(도·행정구는 아님).
    조례 값 조회·딥링크·persist 키 모두 이 단일 출처를 경유해 레벨 불일치를 제거한다.
    """
    addr = address or ""
    if not addr:
        return None
    # 1) 특별시/광역시/특별자치시 = 조례 정본 레벨(자치구 아님).
    m = re.search(r"([가-힣]{2,4}(?:특별시|광역시|특별자치시))", addr)
    if m:
        return m.group(1)
    # 2) 도 산하 = 시/군이 정본(도·행정구 제외). 시/군이 행정구보다 앞서므로 첫 시/군 토큰 채택.
    for m in re.finditer(r"([가-힣]{1,4}[시군])(?:\s|$)", addr):
        return m.group(1)
    return None


# ── 조례 해석 영속(persist) — 한번 조사한 (시군구·용도지역) 값을 저장해 재사용한다.
#    자동 재조사 없음: 사용자가 '재분석'(force_refresh)을 실행할 때만 다시 조사·덮어쓴다.
#    (플랫폼 원칙: 분석 1회 → 저장 → 재사용, 입력변경/명시 요청 시에만 재실행)
_ORD_DDL = (
    "CREATE TABLE IF NOT EXISTS ordinance_resolutions ("
    "  sigungu varchar(40) NOT NULL,"
    "  zone_type varchar(40) NOT NULL,"
    "  payload jsonb NOT NULL,"
    "  source varchar(40),"
    "  fetched_at timestamptz NOT NULL DEFAULT now(),"
    "  PRIMARY KEY (sigungu, zone_type)"
    ")"
)
_ORD_READY = False


async def _ensure_ord_table(db) -> None:
    global _ORD_READY
    if _ORD_READY:
        return
    await db.execute(text(_ORD_DDL))
    await db.commit()
    _ORD_READY = True


async def _load_stored(sigungu: str | None, zone_type: str) -> dict | None:
    """저장된 조례 해석을 재사용(있으면). 자동만료 없음 — 사용자 재분석 전까지 유지."""
    if not sigungu:
        return None
    try:
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure_ord_table(db)
            row = (await db.execute(text(
                "SELECT payload, fetched_at FROM ordinance_resolutions WHERE sigungu=:s AND zone_type=:z"),
                {"s": sigungu, "z": zone_type})).first()
            if row:
                payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                # ★레거시 statutory(법정상한) 저장행 무시: 이 수정 이전 코드가 남긴 미확정값
                #   (source="법정상한")은 cross-tenant 오염원이므로 재사용하지 않는다. None 을
                #   반환해 조회 파이프라인(법제처API→정적캐시→법정상한)이 다시 실행되도록 한다.
                if payload.get("source") == "법정상한":
                    return None
                prov = payload.setdefault("provenance", {})
                prov["reused"] = True  # 저장본 재사용 표시
                prov["stored_fetched_at"] = str(row[1])
                return payload
    except Exception:  # noqa: BLE001 — 저장조회 실패는 실시간 경로로 진행(무손상)
        return None
    return None


async def _save_resolution(result: dict, sigungu: str | None, zone_type: str) -> None:
    if not sigungu:
        return
    try:
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure_ord_table(db)
            await db.execute(text(
                "INSERT INTO ordinance_resolutions (sigungu, zone_type, payload, source, fetched_at) "
                "VALUES (:s,:z,CAST(:p AS jsonb),:src, now()) "
                "ON CONFLICT (sigungu, zone_type) DO UPDATE SET payload=CAST(:p AS jsonb), source=:src, fetched_at=now()"),
                {"s": sigungu, "z": zone_type, "p": json.dumps(result, ensure_ascii=False, default=str),
                 "src": result.get("source")})
            await db.commit()
    except Exception:  # noqa: BLE001 — 저장 실패는 해석 결과를 손상하지 않는다.
        pass


def _attach_provenance(result: dict, confidence: float, recheck: bool, disclaimer: str) -> dict:
    """정직 출처표기 — 어떤 경로(실시간/캐시/법정)로 얻었는지·신뢰도·재확인 권장 여부를 명시."""
    result["provenance"] = {
        "source": result.get("source"),
        "confidence": confidence,
        "recheck_recommended": recheck,  # 캐시/법정폴백이면 True(조례 개정 가능)
        "disclaimer": disclaimer,
        "reused": False,
    }
    return result

# ── 법정 상한 (국토계획법 시행령) ──
# ★bcr·far만 보유(get_ordinance_limits 소비 계약과 1:1). 높이 제한(전용주거 10m/12m 등)은
#   app/services/legal/alris_service.py check_compliance(zone_rules.max_height)가 관장한다.
#   소비되지 않는 키(과거 'height')는 도달 불가 dead data라 여기 두지 않는다(정직게이트).
NATIONAL_LIMITS: dict[str, dict[str, float]] = {
    "제1종전용주거지역": {"bcr": 50, "far": 100},
    "제2종전용주거지역": {"bcr": 50, "far": 150},
    "제1종일반주거지역": {"bcr": 60, "far": 200},
    "제2종일반주거지역": {"bcr": 60, "far": 250},
    "제3종일반주거지역": {"bcr": 50, "far": 300},
    "준주거지역": {"bcr": 70, "far": 500},
    "중심상업지역": {"bcr": 90, "far": 1500},
    "일반상업지역": {"bcr": 80, "far": 1300},
    "근린상업지역": {"bcr": 70, "far": 900},
    "유통상업지역": {"bcr": 80, "far": 1100},
    "전용공업지역": {"bcr": 70, "far": 300},
    "일반공업지역": {"bcr": 70, "far": 350},
    "준공업지역": {"bcr": 70, "far": 400},
    "보전녹지지역": {"bcr": 20, "far": 80},
    "생산녹지지역": {"bcr": 20, "far": 100},
    "자연녹지지역": {"bcr": 20, "far": 100},
    "보전관리지역": {"bcr": 20, "far": 80},
    "생산관리지역": {"bcr": 20, "far": 80},
    "계획관리지역": {"bcr": 40, "far": 100},
    "농림지역": {"bcr": 20, "far": 80},
    "자연환경보전지역": {"bcr": 20, "far": 80},
}

# ── 전국 주요 시·군·구 조례 캐시 (API 실패 시 폴백) ──
# 출처: 각 지자체 도시계획조례 (2025~2026 기준)
ORDINANCE_CACHE: dict[str, dict[str, dict[str, float]]] = {
    # ── 서울특별시 ──
    "서울특별시": {
        "제1종전용주거지역": {"bcr": 50, "far": 100},
        "제2종전용주거지역": {"bcr": 40, "far": 120},
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 200},
        "제3종일반주거지역": {"bcr": 50, "far": 250},
        "준주거지역": {"bcr": 60, "far": 400},
        "중심상업지역": {"bcr": 60, "far": 1000},
        "일반상업지역": {"bcr": 60, "far": 800},
        "근린상업지역": {"bcr": 60, "far": 600},
        "유통상업지역": {"bcr": 60, "far": 600},
        "전용공업지역": {"bcr": 60, "far": 200},
        "일반공업지역": {"bcr": 60, "far": 200},
        "준공업지역": {"bcr": 60, "far": 400},
        "보전녹지지역": {"bcr": 20, "far": 50},
        "생산녹지지역": {"bcr": 20, "far": 50},
        "자연녹지지역": {"bcr": 20, "far": 50},
    },
    # ── 경기도 주요 시 ──
    # 출처: 각 시 도시계획 조례 (2025~2026 확인 기준)
    "성남시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 220},
        "제3종일반주거지역": {"bcr": 50, "far": 280},
        "준주거지역": {"bcr": 60, "far": 400},
    },
    "수원시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 250},
        "제3종일반주거지역": {"bcr": 50, "far": 300},
        "준주거지역": {"bcr": 70, "far": 500},
    },
    "용인시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 200},
        "제3종일반주거지역": {"bcr": 50, "far": 250},
    },
    "화성시": {
        "제2종일반주거지역": {"bcr": 60, "far": 250},
        "제3종일반주거지역": {"bcr": 50, "far": 300},
    },
    "고양시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 220},
        "제3종일반주거지역": {"bcr": 50, "far": 280},
    },
    # 의정부시 도시계획 조례 (2025 기준)
    # 의정부시의 경우 제2종일반주거지역 용적률이 법정상한(250%)과 동일하게 조례에 규정
    # 다만 7층 이하 제2종일반주거지역은 200%로 제한됨
    "의정부시": {
        "제1종전용주거지역": {"bcr": 50, "far": 100},
        "제2종전용주거지역": {"bcr": 50, "far": 150},
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 250},
        "제2종일반주거지역(7층이하)": {"bcr": 60, "far": 200},
        "제3종일반주거지역": {"bcr": 50, "far": 300},
        "준주거지역": {"bcr": 70, "far": 500},
        "일반상업지역": {"bcr": 80, "far": 900},
        "근린상업지역": {"bcr": 70, "far": 700},
        "준공업지역": {"bcr": 70, "far": 400},
    },
    "부천시": {"제2종일반주거지역": {"bcr": 60, "far": 200}, "준공업지역": {"bcr": 60, "far": 400}},
    "안양시": {"제2종일반주거지역": {"bcr": 60, "far": 220}},
    "안산시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "준공업지역": {"bcr": 70, "far": 400}},
    "파주시": {"제2종일반주거지역": {"bcr": 60, "far": 200}, "계획관리지역": {"bcr": 40, "far": 100}},
    "김포시": {"제2종일반주거지역": {"bcr": 60, "far": 250}},
    "광명시": {"제2종일반주거지역": {"bcr": 60, "far": 200}},
    "하남시": {"제2종일반주거지역": {"bcr": 60, "far": 200}},
    "시흥시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "준공업지역": {"bcr": 60, "far": 400}},
    "남양주시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 220},
        "제3종일반주거지역": {"bcr": 50, "far": 280},
        "준주거지역": {"bcr": 60, "far": 400},
    },
    "구리시": {
        "제2종일반주거지역": {"bcr": 60, "far": 220},
        "제3종일반주거지역": {"bcr": 50, "far": 280},
    },
    "양주시": {
        "제2종일반주거지역": {"bcr": 60, "far": 250},
        "제3종일반주거지역": {"bcr": 50, "far": 300},
    },
    # ── 인천광역시 ──
    "인천광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}, "준주거지역": {"bcr": 60, "far": 400}},
    # ── 부산광역시 ──
    "부산광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}, "일반상업지역": {"bcr": 80, "far": 1000}},
    # ── 대구광역시 ──
    "대구광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}},
    # ── 대전광역시 ──
    "대전광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}},
    # ── 광주광역시 ──
    "광주광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}},
    # ── 세종특별자치시 ──
    "세종특별자치시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}},
    # ── 울산광역시 ──
    "울산광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}},
    # ── 제주특별자치도 ──
    "제주특별자치도": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 250}},
}

# 법제처 API 엔드포인트 — 법제처 DRF는 https를 지원하므로 평문 http 대신 https 사용
# (평문 전송 시 API키·조회내용이 중간자에 노출될 수 있음). 만약 특정 환경에서 https 접속이
# 실패하면 인프라(프록시/CA)를 점검할 것 — 코드에서 http로 되돌리지 말 것.
MOLEG_ORDIN_LIST_URL = "https://www.law.go.kr/DRF/lawSearch.do"
MOLEG_ORDIN_TEXT_URL = "https://www.law.go.kr/DRF/lawService.do"


class OrdinanceService:
    """전국 지자체 도시계획조례 실시간 조회 서비스."""

    async def get_ordinance_limits(
        self, address: str, zone_type: str, force_refresh: bool = False
    ) -> dict[str, Any]:
        """주소와 용도지역으로 해당 지자체 조례 건폐율/용적률을 조회.

        해석 단일 파이프라인(SSOT) — zoning·regulation 공용:
        0. 저장된 분석 재사용 (force_refresh=False & 저장본 존재 시 즉시 반환, 재조사 없음)
        1. 법제처 API 실시간 조회 (도시계획조례 본문 파싱)
        2. 정적 캐시 DB (주요 시군구)
        3. 법정 상한 (국토계획법 시행령)
        → 1~3 결과는 저장(persist)하고 provenance(출처·신뢰도·재확인 권장)를 부착한다.
        force_refresh=True(사용자 '재분석' 실행) 일 때만 저장본을 무시하고 다시 조사·덮어쓴다.
        """
        # 주소에서 지자체 추출
        region_info = self._extract_region(address)
        sido = region_info["sido"]
        sigungu = region_info["sigungu"]
        # ★조례 관할명 정규화(공용 SSOT resolve_ordinance_region 재사용) — 특별시/광역시 자치구
        #   (동작구 등)는 조례 제정권이 없어 시 본청('서울특별시')으로 승격. 일반 시/군은 그대로.
        #   인용(legal_basis)·실시간 검색명을 이 관할로 일원화('동작구 도시계획 조례'[허위] 제거).
        jurisdiction = resolve_ordinance_region(address) or sigungu or (sido if sido != "미확인" else None)

        # 0차: 저장된 분석 재사용(자동 재조사 금지 — 사용자 재분석 시에만 갱신)
        # ★persist 키 = jurisdiction(조례 정본 관할, 저장 키와 동일 SSOT). 자치구(sigungu)
        #   키는 같은 시 본청 조례를 자치구별로 분산 저장/캐시미스(중복 재조회)시키므로 금지.
        if not force_refresh:
            stored = await _load_stored(jurisdiction, zone_type)
            if stored:
                return stored

        # 법정 상한
        national = NATIONAL_LIMITS.get(zone_type, {})
        national_bcr: float = float(national.get("bcr") or 60)
        national_far: float = float(national.get("far") or 250)

        result = {
            "sido": sido,
            "sigungu": sigungu,
            "zone_type": zone_type,
            "national_bcr": national_bcr,
            "national_far": national_far,
            "ordinance_bcr": None,
            "ordinance_far": None,
            "effective_bcr": national_bcr,
            "effective_far": national_far,
            "source": "법정상한",
            "legal_basis": "국토의 계획 및 이용에 관한 법률 시행령 제84조, 제85조",
            "ordinance_name": None,
            "last_updated": None,
        }

        # 1차: 법제처 API 실시간 조회(정규화 관할명으로 검색 — '동작구' 부재조례 회피).
        api_result = await self._fetch_from_moleg_api(sido or "", sigungu, zone_type, jurisdiction=jurisdiction)
        if api_result and api_result.get("bcr") is not None:
            ord_bcr = api_result["bcr"]
            ord_far = api_result["far"]
            result["ordinance_bcr"] = ord_bcr
            result["ordinance_far"] = ord_far
            result["effective_bcr"] = min(national_bcr, ord_bcr) if ord_bcr else national_bcr
            result["effective_far"] = min(national_far, ord_far) if ord_far else national_far
            result["source"] = "법제처API"
            result["ordinance_name"] = api_result.get("ordinance_name")
            result["last_updated"] = api_result.get("last_updated")
            result["legal_basis"] = f"{jurisdiction} 도시계획 조례"
            # ★파서의 정직 신호(parse_confidence/missing_sections/caveat)를 provenance에 반영한다.
            #   깔끔히 파싱되면 0.95 유지, 느슨한 매칭이면 파서 신뢰도로 하향해 '확정'으로
            #   호도하지 않는다(낮으면 recheck 권장). 소비자가 안 읽어도 무해한 additive 필드.
            parse_conf = api_result.get("parse_confidence")
            missing = api_result.get("missing_sections") or []
            caveat = api_result.get("caveat")
            loose_parse = (parse_conf is not None and parse_conf < 0.6)
            prov_conf = 0.95 if not loose_parse else min(0.95, 0.5 + (parse_conf or 0.0) * 0.5)
            disclaimer = "법제처 자치법규 실시간 조회값(도시계획조례 본문)."
            if caveat:
                disclaimer += f" {caveat}"
            elif loose_parse:
                disclaimer += " (파싱 신뢰도 낮음 — 조례 원문 재확인 권장)"
            _attach_provenance(result, confidence=prov_conf, recheck=loose_parse,
                               disclaimer=disclaimer)
            # provenance에 파서 세부 신호를 additive로 노출(정직 표기·디버깅용).
            result["provenance"]["parse_confidence"] = parse_conf
            result["provenance"]["missing_sections"] = missing
            result["provenance"]["evidence_span"] = api_result.get("evidence_span")
            await _save_resolution(result, jurisdiction, zone_type)
            return result

        # 2차: 정적 캐시 조회 (전국 주요 시군구 조례 데이터)
        cache_result = self._lookup_cache(sido or "", sigungu, zone_type)
        if cache_result:
            c_bcr = cache_result["bcr"]
            c_far = cache_result["far"]
            result["ordinance_bcr"] = c_bcr
            result["ordinance_far"] = c_far
            result["effective_bcr"] = min(national_bcr, c_bcr)
            result["effective_far"] = min(national_far, c_far)
            result["source"] = "지자체 조례(정적캐시)"
            result["legal_basis"] = f"{jurisdiction} 도시계획 조례"
            _attach_provenance(result, confidence=0.80, recheck=True,
                               disclaimer="정적 캐시(2025~2026 기준) — 조례 개정 가능, '재분석'으로 실시간 재확인 권장.")
            await _save_resolution(result, jurisdiction, zone_type)
            return result

        # 3차: 법정 상한 그대로 (해당 지자체 조례 데이터 미보유)
        logger.info(
            "조례 캐시 미보유 — 법정상한 적용: sido=%s, sigungu=%s, zone=%s, "
            "법정 건폐율=%.0f%%, 법정 용적률=%.0f%%",
            sido, sigungu, zone_type, national_bcr, national_far,
        )
        result["source"] = "법정상한"
        _attach_provenance(result, confidence=0.60, recheck=True,
                           disclaimer="해당 지자체 조례 미보유 — 법정상한 적용. 실제 조례 확인 필요.")
        # ★저장 금지(cross-tenant 오염 방지): statutory(법정상한)는 '조례 미확보'를 뜻하는
        #   미확정값이다. 이를 전역 캐시(sigungu, zone_type)에 저장하면 같은 시군구의 다른
        #   테넌트/프로젝트가 이 미확정값을 재사용(cross-tenant 오염)하게 되어, 실제 조례가
        #   법정상한보다 낮은 경우 과대허용값이 전파된다. 따라서 저장하지 않고 statutory 결과는
        #   현재 요청에만 transient 로 반환한다(Tier-1 법제처API·Tier-2 정적캐시=확정값이라 저장 유지).
        return result

    async def _fetch_from_moleg_api(
        self, sido: str, sigungu: str | None, zone_type: str, *, jurisdiction: str | None = None
    ) -> dict[str, Any] | None:
        """법제처 API로 도시계획조례 실시간 조회. jurisdiction=정규화 관할명(특별시/광역시는 시 본청)."""
        api_key = getattr(settings, "MOLEG_API_KEY", "") or ""
        if not api_key:
            return None

        # ★정규화 관할명으로 검색 — 특별시/광역시 자치구는 소속 시도 조례('동작구 도시계획 조례'[부재] 회피).
        search_name = f"{jurisdiction or sigungu or sido} 도시계획 조례"

        try:
            # Step 1: 자치법규 목록 검색 (User-Agent 필수)
            headers = {"User-Agent": "PropAI/1.0 (https://4t8t.net)"}
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                resp = await client.get(
                    MOLEG_ORDIN_LIST_URL,
                    params={
                        "OC": api_key,
                        "target": "ordin",
                        "type": "XML",
                        "query": search_name,
                        "display": "5",
                        "sort": "date",
                    },
                )
                resp.raise_for_status()
                ordin_list_xml = resp.text

            # 조례 일련번호 추출
            ordin_id = self._parse_ordin_id(ordin_list_xml, jurisdiction or sigungu or sido)
            if not ordin_id:
                return None

            # Step 2: 조례 본문 조회
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                resp = await client.get(
                    MOLEG_ORDIN_TEXT_URL,
                    params={
                        "OC": api_key,
                        "target": "ordin",
                        "type": "XML",
                        "ID": ordin_id,
                    },
                )
                resp.raise_for_status()
                ordin_text = resp.text

            # Step 3: 본문에서 건폐율/용적률 파싱
            return self._parse_bcr_far_from_text(ordin_text, zone_type, jurisdiction or sigungu or sido)

        except Exception as e:
            logger.warning("법제처 API 조례 조회 실패: %s %s (%s)", sido, sigungu, str(e))
            return None

    def _parse_ordin_id(self, xml_text: str, region_name: str) -> str | None:
        """자치법규 목록조회 응답에서 '본문조회(lawService.do)의 ID' 값을 추출한다.

        ★버그수정(라이브 그라운드 트루스): 법제처 자치법규(target=ordin) API의 목록 응답은
        본문조회 ID로 ``<자치법규ID>`` 를 요구한다(라이브 확인: 자치법규ID로 본문 64KB 수신,
        <자치법규일련번호>·<법령일련번호>로는 "일치하는 자치법규가 없습니다"). 종전 코드는
        법령(target=law) API용 필드 ``<법령일련번호>`` 만 찾아 자치법규 응답에서 항상 None →
        조례 본문을 한 번도 못 가져오던 결함(조례 경사도 전량 폴백·FAR/BCR 라이브조회 무력화의
        진원). 아래 순서로 시도하되 본문조회에 유효한 <자치법규ID>를 최우선한다.
        """
        # 본문조회 ID 후보(자치법규ID 우선)의 (위치, 값) 목록 — 하나의 필드종류로 통일해 수집.
        id_hits: list[tuple[int, str]] = []
        for pattern in (
            r"<자치법규ID>(\d+)</자치법규ID>",          # ★본문조회 ID(유효) — 최우선
            r"<자치법규일련번호>(\d+)</자치법규일련번호>",  # MST(일부 API 버전 호환)
            r"<법령일련번호>(\d+)</법령일련번호>",        # 법령 API 폴백(하위호환)
            r"<ordinSeq>(\d+)</ordinSeq>",                # 영문 키 폴백
        ):
            hits = [(m.start(), m.group(1)) for m in re.finditer(pattern, xml_text)]
            if hits:
                id_hits = hits
                break
        if not id_hits:
            return None
        # ★목록에 여러 자치법규(도시계획 조례·시행규칙·기타 조례)가 섞여 있으므로, 첫 ID를
        #   무조건 쓰지 않고 '도시계획 조례'(시행규칙 아님) 항목의 ID를 우선한다. 각 <자치법규명>
        #   뒤 '가장 가까운 ID'가 그 항목의 ID다(항목 순서: 명 → … → ID).
        names = [
            (m.start(), (m.group(1) or "").strip())
            for m in re.finditer(
                r"<자치법규명>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</자치법규명>",
                xml_text, re.DOTALL,
            )
        ]

        def _id_after(pos: int) -> str | None:
            # 항목 순서 가정: <자치법규명> … <자치법규ID>(명 뒤 가장 가까운 ID = 그 항목의 ID).
            after = [v for p, v in id_hits if p > pos]
            return after[0] if after else None

        def _is_city_plan_ordinance(name: str) -> bool:
            return "도시계획" in name and "조례" in name and "규칙" not in name

        region = (region_name or "").strip()
        # ① region_name까지 일치하는 '도시계획 조례'를 최우선(인접 동명이역 오조회 차단).
        if region:
            for npos, name in names:
                if region in name and _is_city_plan_ordinance(name):
                    oid = _id_after(npos)
                    if oid:
                        return oid
        # ② region 불명/미일치 시 '도시계획 조례'(시행규칙 아님)만으로 선택.
        for npos, name in names:
            if _is_city_plan_ordinance(name):
                oid = _id_after(npos)
                if oid:
                    return oid
        # ③ 폴백 — 특정 못하면 첫 ID(하위호환).
        return id_hits[0][1]

    def _parse_bcr_far_from_text(
        self, xml_text: str, zone_type: str, region_name: str
    ) -> dict[str, Any] | None:
        """조례 본문에서 요청된 용도지역의 건폐율/용적률 값을 추출.

        ★반환 계약(호출부 _fetch_from_moleg_api → get_ordinance_limits가 소비)은 그대로 유지한다:
            {"bcr": int|None, "far": int|None, "ordinance_name": str, "last_updated": str|None}
        여기에 '정직 신호' 키를 **추가로만**(additive) 얹는다 — 기존 소비자는 bcr/far/이름/시행일만
        읽으므로 아래 키가 늘어도 무해하다:
            "parse_confidence": 0~1(테이블·조문 깔끔히 매칭=높음, 느슨한 매칭/폴백=낮음)
            "missing_sections": 못 찾은 항목 목록(예: ["건폐율", "용적률", "요청 용도지역"])
            "caveat": 값이 단서/경과조치(다만 …) 맥락이면 그 주의문(없으면 None)
            "evidence_span": 값을 뽑아낸 원문 근거 스니펫(용도별 provenance용)

        내부적으로는 구조화 파서(_extract_zone_limits_structured)가 조례 본문 전체를
        {용도지역: {"bcr":pct, "far":pct, ...}} 형태로 파싱하고, 여기서 요청 zone_type만 골라낸다.
        """
        # CDATA 블록 추출하여 전체 텍스트 구성(구조화 파서에 원문 그대로 넘긴다).
        # ★CDATA 종결자는 ']]>'다. 기존 `CDATA\[(.*?)\]`는 첫 ']'에서 끊겨(비탐욕),
        #   '[별표 1]' 같이 본문에 ']'가 있으면 표가 잘려나갔다(별표 파싱 실패의 근본원인).
        #   여기서는 ']]>' 종결까지를 CDATA 본문으로 정확히 잡되, 종결자가 없는 변형 XML도
        #   폴백으로 흡수한다.
        chunks = re.findall(r"CDATA\[(.*?)\]\]>", xml_text, re.DOTALL)
        if not chunks:
            # 폴백(종결자 표기변형): 단일 ']'까지라도 잡아 최소한의 본문을 확보.
            chunks = re.findall(r"CDATA\[(.*?)\]", xml_text, re.DOTALL)
        full_text = " ".join(chunks)

        if not full_text.strip():
            return None

        # 1) 조례 본문 전체를 구조화 파싱(용도지역별 건폐율/용적률 표).
        structured = self._extract_zone_limits_structured(full_text)
        zones: dict[str, dict[str, Any]] = structured["zones"]

        # 2) 요청 용도지역에 해당하는 값을 관대 매칭으로 선택(표기변형·세분 허용).
        matched_key = self._match_requested_zone(zone_type, zones)
        entry = zones.get(matched_key) if matched_key else None

        bcr = entry.get("bcr") if entry else None
        far = entry.get("far") if entry else None

        # 3) '정직 신호' 집계 — 무엇을 못 찾았는지, 신뢰도는 얼마인지.
        missing_sections: list[str] = []
        if not structured["found_bcr_section"]:
            missing_sections.append("건폐율")
        if not structured["found_far_section"]:
            missing_sections.append("용적률")
        if entry is None or (bcr is None and far is None):
            # 조례에 값이 있어도 '요청 용도지역'이 표에 없으면 절대 만들어내지 않는다.
            missing_sections.append("요청 용도지역")

        if bcr is None and far is None:
            # 요청 용도지역 값을 전혀 못 찾음 → None 반환(호출부는 정적캐시→법정상한으로 폴백).
            # ★날조 금지: 여기서 값을 채우지 않는다(정직 폴백이 기존 올바른 동작).
            return None

        # 신뢰도: 조문 헤더를 정식으로 찾고(용도지역 안에서의 …) 표에서 명시 매칭했으면 높게,
        #         느슨한 폴백 매칭에 기댔으면 낮게. 단서/경과조치 맥락이면 더 감점.
        #         ★고밀 용도지역(상업·준주거)이 FAR<500이면 절단/오독 강한 신호 → 감점.
        parse_confidence = self._compute_parse_confidence(structured, entry, matched_key)
        caveat = entry.get("caveat") if entry else None
        # ★FIX2 방어: 고밀 존(상업·준주거) FAR<500이면 천 단위 절단 의심을 caveat로 명시
        #   (신뢰도는 이미 _compute_parse_confidence에서 강등됨 → recheck 자동 권장).
        if self._is_high_density_undershoot(matched_key, far):
            trunc_note = (
                "고밀 용도지역(상업·준주거)인데 용적률이 500% 미만으로 파싱됨 — "
                "천 단위(예: 1,300%) 절단 파싱 오류 의심(원문 재확인 권장)."
            )
            caveat = f"{caveat} {trunc_note}".strip() if caveat else trunc_note

        # 조례명/시행일 추출(기존과 동일).
        ordin_name_match = re.search(r"<자치법규명>.*?CDATA\[([^\]]+)\]", xml_text)
        date_match = re.search(r"<시행일자>(\d{8})</시행일자>", xml_text)

        return {
            "bcr": bcr,
            "far": far,
            "ordinance_name": ordin_name_match.group(1) if ordin_name_match else f"{region_name} 도시계획 조례",
            "last_updated": f"{date_match.group(1)[:4]}-{date_match.group(1)[4:6]}-{date_match.group(1)[6:]}" if date_match else None,
            # ── 추가(additive) 정직 신호 — 기존 소비자는 무시해도 무해 ──
            "parse_confidence": parse_confidence,
            "missing_sections": missing_sections,
            "caveat": caveat,
            "evidence_span": entry.get("evidence_span") if entry else None,
        }

    # ──────────────────────────────────────────────────────────────────────
    # 구조화 파서 헬퍼들 (P1-1 강화) — 정규식 남발을 줄이고, 조례 표기변형을
    # 관대하게 흡수한다. 각 헬퍼는 순수함수(외부 IO 없음)라 테스트가 쉽다.
    # ──────────────────────────────────────────────────────────────────────

    # 국토계획법상 21개 용도지역 표준명(세분 접미사 제거 후 최종 정규화용).
    _CANONICAL_ZONES: tuple[str, ...] = (
        "제1종전용주거지역", "제2종전용주거지역",
        "제1종일반주거지역", "제2종일반주거지역", "제3종일반주거지역",
        "준주거지역",
        "중심상업지역", "일반상업지역", "근린상업지역", "유통상업지역",
        "전용공업지역", "일반공업지역", "준공업지역",
        "보전녹지지역", "생산녹지지역", "자연녹지지역",
        "보전관리지역", "생산관리지역", "계획관리지역",
        "농림지역", "자연환경보전지역",
    )

    @staticmethod
    def _normalize_ws(text_in: str) -> str:
        """공백 정규화 — 연속 공백/개행/탭을 단일 공백으로 접는다.

        '용도지역  안에서의   건폐율' 같은 띄어쓰기 변형을 흡수하기 위한 전처리.
        """
        return re.sub(r"\s+", " ", text_in or "").strip()

    def _locate_section(self, full_text: str, kind: str) -> tuple[str | None, bool]:
        """'용도지역 안에서의 건폐율/용적률' 조문(또는 참조된 별표) 본문을 찾아 반환.

        - kind: "건폐율" 또는 "용적률".
        - 띄어쓰기 변형 허용: '용도지역안에서의' / '용도지역 안에서의' 모두 매칭.
        - "별표 N과 같다" 형태면 해당 별표 블록을 찾아 그 본문을 반환(표가 별표에 있는 조례 대응).
        Returns: (섹션본문|None, is_full_header)
          is_full_header=True → 정식 헤더('용도지역 안에서의 …')로 찾음(신뢰도 높음).
          False → 헤더 없이 단어(건폐율/용적률)만으로 폴백(신뢰도 낮게 취급).
        """
        norm = self._normalize_ws(full_text)
        # 반대 항목(건폐율↔용적률) — 이 헤더가 다시 나오면 현재 섹션의 끝이다(값 오염 방지).
        other = "용적률" if kind == "건폐율" else "건폐율"

        # 헤더 매칭: '용도지역' + (선택)공백 + '안에서의' + … + 건폐율/용적률.
        # (사이에 '의 최대한도' 같은 수식어가 끼어도 되도록 헤더~kind 사이를 관대하게 허용)
        header_re = r"용도지역\s*안에서의\s*(?:[^.]{0,20}?)?" + kind
        header = re.search(header_re, norm)
        is_full_header = header is not None
        if not header:
            # 헤더가 없더라도 '건폐율은/용적률은 … 별표'식 직접 언급을 폴백 탐색(느슨).
            header = re.search(kind, norm)
            if not header:
                return None, False

        start = header.start()
        tail = norm[header.end():]

        # ★별표 참조 우선 처리: "별표 N과 같다/따른다/의한다" → 표가 별표에 실려 있다.
        #   (경계 truncation보다 먼저 판정해야 참조 문구 자체를 잘라버리지 않는다.)
        ref_area = tail[:120]  # 헤더 직후 근접 영역에서만 참조를 인정(오검출 방지).
        ref = re.search(r"별표\s*(\d+)\s*(?:의\s*\d+)?", ref_area)
        if ref and ("같다" in ref_area or "따른" in ref_area or "의한" in ref_area):
            byeolpyo = self._locate_byeolpyo(norm, ref.group(1))
            if byeolpyo:
                # 별표에서 뽑되, 정식 조문에서 참조했으니 is_full_header는 그대로 반영.
                return byeolpyo, is_full_header

        # ★섹션 끝 경계: 헤더 이후에서 '반대 항목의 정식 헤더'가 다시 나오거나, 별표 '정의'
        #   블록([별표 N] — 대괄호로 시작)이 나오면 그 앞에서 끊는다(값이 뒤섞이는 것 방지).
        #   단순 '별표 N과 같다' 참조 문구(대괄호 없음)로는 끊지 않는다.
        other_hdr = re.search(r"용도지역\s*안에서의\s*(?:[^.]{0,20}?)?" + other, tail)
        byeolpyo_def = re.search(r"\[\s*별표\s*\d+", tail)
        # 폴백(헤더 없음)일 때는 값 오염을 줄이려 반대 단어도 경계로 인정.
        loose_other = re.search(other, tail) if not is_full_header else None
        bounds = [b.start() for b in (other_hdr, byeolpyo_def, loose_other) if b]
        window = min(bounds) if bounds else 2500
        section = norm[start:header.end() + window]
        return section, is_full_header

    def _locate_byeolpyo(self, norm_text: str, number: str) -> str | None:
        """'별표 N' 정의 블록을 본문에서 찾아 반환(표 값이 별표에 실린 조례 대응).

        ★핵심: '별표 N과 같다' 같은 참조 문구가 아니라 표가 실린 '정의' 블록을 잡아야 한다.
          - 우선 대괄호 정의('[별표 N]')를 찾는다.
          - 없으면 마지막 '별표 N' 등장을 정의로 본다(참조는 앞, 정의는 뒤에 오는 관행).
        """
        num = re.escape(number)
        # 1) 대괄호 정의 '[별표 N]' 우선.
        m = re.search(r"\[\s*별표\s*" + num + r"(?!\d)\s*\]?", norm_text)
        if not m:
            # 2) 폴백: '별표 N'의 '마지막' 등장(참조 뒤에 오는 정의로 간주).
            matches = list(re.finditer(r"별표\s*" + num + r"(?!\d)", norm_text))
            if not matches:
                return None
            m = matches[-1]
        start = m.start()
        # 별표 시작 이후 넉넉히(다음 별표 전까지, 최대 3000자).
        after = start + len(m.group(0))
        tail = norm_text[after:]
        nxt = re.search(r"\[?\s*별표\s*\d+", tail)
        end = (after + nxt.start()) if nxt else min(len(norm_text), start + 3000)
        return norm_text[start:end]

    def _extract_pct_near(self, fragment: str) -> tuple[int | None, bool]:
        """조각 텍스트에서 첫 퍼센트 값을 뽑는다.

        ★값 추출은 공용 헬퍼 `_parse_kr_percent`(천 단위 구분자 허용)로 일원화한다.
          (기존 `(\\d{1,4})퍼센트`는 '1,300퍼센트'를 300으로 잘라 상업·준주거 고밀
           용적률을 과소파싱했다 — 라이브 재현된 버그. 전역 단일 파서로 통일.)

        Returns: (값 또는 None, 단서맥락여부)
          단서맥락여부=True면 '다만/경과조치' 같은 예외문 안의 값일 수 있으니 신뢰도 감점.
        """
        m = _KR_PCT_RE.search(fragment)
        if not m:
            return None, False
        val = _parse_kr_percent(m.group(0))
        # 값 앞 40자에 단서/경과 키워드가 있으면 예외값일 수 있음.
        pre = fragment[max(0, m.start() - 40):m.start()]
        caveat_ctx = any(k in pre for k in ("다만", "경과조치", "종전", "적용하지"))
        return val, caveat_ctx

    def _extract_zone_limits_structured(self, full_text: str) -> dict[str, Any]:
        """조례 본문 전체를 {용도지역: {"bcr":pct,"far":pct,"caveat":..,"evidence_span":..}} 로 파싱.

        - 건폐율 조문/별표에서 용도지역별 값 → bcr
        - 용적률 조문/별표에서 용도지역별 값 → far
        - 표기변형·세분(제2종일반주거지역(7층 이하))을 관대하게 흡수.
        반환에 found_bcr_section/found_far_section(조문 발견 여부)도 담아 신뢰도 산출에 쓴다.
        """
        zones: dict[str, dict[str, Any]] = {}

        bcr_section, bcr_full = self._locate_section(full_text, "건폐율")
        far_section, far_full = self._locate_section(full_text, "용적률")

        for kind, section in (("bcr", bcr_section), ("far", far_section)):
            if not section:
                continue
            for zone_name, frag, caveat_hdr in self._iter_zone_fragments(section):
                val, caveat_ctx = self._extract_pct_near(frag)
                if val is None:
                    continue
                slot = zones.setdefault(zone_name, {})
                slot[kind] = val
                # 근거 스니펫(용도별) — 처음 잡힌 것을 대표로.
                slot.setdefault("evidence_span", self._normalize_ws(frag)[:120])
                if caveat_ctx or caveat_hdr:
                    slot["caveat"] = "단서·경과조치 맥락에서 추출된 값일 수 있음(원문 재확인 권장)."

        return {
            "zones": zones,
            "found_bcr_section": bcr_section is not None,
            "found_far_section": far_section is not None,
            # 정식 헤더('용도지역 안에서의 …')로 찾았는지 — 신뢰도 산출에 활용.
            "bcr_full_header": bcr_full,
            "far_full_header": far_full,
        }

    def _iter_zone_fragments(self, section: str):
        """조문/별표 구간을 용도지역 단위 조각으로 쪼개 (용도지역명, 값조각, 단서헤더) 산출.

        전략: 표준 용도지역명(세분 접미사 '(7층 이하)' 포함 가능)을 앵커로 스캔하고,
        각 앵커부터 다음 앵커 직전까지를 '그 용도지역의 값 조각'으로 본다.
        이렇게 하면 'OO지역 : 200퍼센트' 뿐 아니라 표/줄바꿈/공백 변형에서도 값을 잡는다.
        """
        # 앵커: 표준 용도지역명 + (선택) 세분 괄호. 긴 이름 우선(제2종일반주거지역 > 주거지역).
        alt = "|".join(re.escape(z) for z in sorted(self._CANONICAL_ZONES, key=len, reverse=True))
        anchor_re = re.compile(r"(" + alt + r")\s*(\([^)]*?층[^)]*?\))?")

        hits = list(anchor_re.finditer(section))
        for i, m in enumerate(hits):
            base = m.group(1)
            qualifier = m.group(2) or ""
            # 세분 접미사(예: '(7층 이하)')가 있으면 표준화해 붙인다.
            if qualifier:
                # 공백 제거해 '제2종일반주거지역(7층이하)' 형태로(캐시 키 표기와 정합).
                zone_name = base + re.sub(r"\s+", "", qualifier)
            else:
                zone_name = base
            start = m.end()
            end = hits[i + 1].start() if i + 1 < len(hits) else min(len(section), start + 120)
            frag = section[start:end]
            # 값 조각 앞 20자에 단서 키워드가 있으면 헤더 단서로 표시.
            head_ctx = section[max(0, m.start() - 20):m.start()]
            caveat_hdr = any(k in head_ctx for k in ("다만", "경과조치"))
            yield zone_name, frag, caveat_hdr

    def _match_requested_zone(
        self, zone_type: str, zones: dict[str, dict[str, Any]]
    ) -> str | None:
        """요청 용도지역명을 파싱된 표 키와 관대 매칭(표기변형·세분 허용).

        우선순위: 정확 일치 > 세분 무시 일치 > 부분 일치(짧은 조각 오매칭 방지 위해 길이 최소 4).
        """
        if not zone_type:
            return None
        req = re.sub(r"\s+", "", zone_type)

        # 1) 정확 일치
        if req in zones:
            return req
        # 2) 세분 접미사를 뗀 기본명 일치(요청이 기본명이고 표에 세분만 있으면 기본 우선).
        req_base = re.sub(r"\([^)]*\)", "", req)
        for k in zones:
            if re.sub(r"\([^)]*\)", "", k) == req_base and "(" not in req:
                return k
        # 3) 부분 일치(양방향) — 너무 짧은 조각은 배제해 '주거'류 광의 오매칭 차단.
        if len(req_base) >= 4:
            candidates = [
                k for k in zones
                if req_base in re.sub(r"\([^)]*\)", "", k) or re.sub(r"\([^)]*\)", "", k) in req_base
            ]
            if candidates:
                # 가장 구체적(긴) 키 우선.
                return sorted(candidates, key=len, reverse=True)[0]
        return None

    # ★고밀 용도지역명(상업 계열 + 준주거) — 이들이 FAR<500이면 절단/오독 강한 신호.
    #   상업·준주거는 조례 용적률이 통상 400~1500%로, sub-500 값은 '1,300→300'식
    #   천 단위 절단 파싱 오류의 대표 증상이다(방어 게이트에 사용).
    _HIGH_DENSITY_ZONES: tuple[str, ...] = (
        "중심상업지역", "일반상업지역", "근린상업지역", "유통상업지역", "준주거지역",
    )
    _HIGH_DENSITY_MIN_FAR: int = 500  # 이 미만이면 고밀 존에서 절단 의심.

    @classmethod
    def _is_high_density_undershoot(
        cls, matched_key: str | None, far: int | None
    ) -> bool:
        """고밀 용도지역(상업·준주거)이 FAR<500으로 파싱됐는지(절단 의심) 판정."""
        if matched_key is None or far is None:
            return False
        # 세분 접미사('(7층 이하)' 등)를 떼고 기본명으로 비교.
        base = re.sub(r"\([^)]*\)", "", matched_key)
        if not any(z in base for z in cls._HIGH_DENSITY_ZONES):
            return False
        return far < cls._HIGH_DENSITY_MIN_FAR

    @classmethod
    def _compute_parse_confidence(
        cls,
        structured: dict[str, Any],
        entry: dict[str, Any] | None,
        matched_key: str | None = None,
    ) -> float:
        """파싱 신뢰도 산출(0~1). 정식헤더·조문 발견·양쪽 값 확보·단서부재일수록 높다."""
        if entry is None:
            return 0.0
        conf = 0.5  # 기본(값은 찾았으나 정황 불충분)
        if structured.get("found_bcr_section"):
            conf += 0.15
        if structured.get("found_far_section"):
            conf += 0.15
        # 건폐율·용적률 둘 다 확보되면 표가 온전히 읽힌 신호.
        if entry.get("bcr") is not None and entry.get("far") is not None:
            conf += 0.15
        # ★정식 헤더('용도지역 안에서의 …') 없이 단어 폴백으로만 잡았으면 크게 감점
        #   (표 위치가 불확실 → 값 오독 위험). 값이 있는 쪽의 헤더 신뢰만 반영.
        bcr_loose = entry.get("bcr") is not None and not structured.get("bcr_full_header")
        far_loose = entry.get("far") is not None and not structured.get("far_full_header")
        if bcr_loose or far_loose:
            conf -= 0.35
        # 단서/경과조치 맥락이면 감점(예외값 오독 위험).
        if entry.get("caveat"):
            conf -= 0.25
        # ★방어 게이트(FIX2): 상업·준주거 고밀 존이 FAR<500이면 천 단위 절단 의심.
        #   설사 정식 헤더로 깔끔히 매칭됐어도(0.95) 이 값은 신뢰할 수 없으니 강등해
        #   recheck_recommended가 켜지도록 한다(거짓 확신 방지).
        if cls._is_high_density_undershoot(matched_key, entry.get("far")):
            conf = min(conf, 0.55) - 0.15
        return round(max(0.0, min(1.0, conf)), 2)

    # ──────────────────────────────────────────────────────────────────────
    # T2. 개발행위허가 경사도 기준 파서 (LEGAL_ENGINE_SLOPE_FOREST_PLAN 2026-07-02)
    #   시군구별 개발행위허가 경사도 기준(17.5도/20도/25도 상이)을 도시계획조례
    #   본문에서 추출한다. ★원칙(비협상): 정적 시드값 절대 금지(무날조 — 값 검증
    #   불가), 실패는 None(호출부가 "해당 지자체 조례 직접 확인 필요" 캐비앳 부착).
    #   기존 BCR/FAR 파이프라인(_fetch_from_moleg_api·_parse_bcr_far_from_text)은
    #   무수정 — 아래는 전부 additive 추가다.
    # ──────────────────────────────────────────────────────────────────────

    # persist 키(zone_type 슬롯) — 실제 용도지역명과 절대 충돌하지 않는 전용 키.
    #   기존 ordinance_resolutions(PK: sigungu, zone_type) 테이블을 그대로 재사용해
    #   '분석 1회 → 저장 → 재사용, 재분석 시에만 갱신' 플랫폼 원칙을 동일 적용한다.
    _SLOPE_PERSIST_KEY: str = "__개발행위허가_경사도__"

    # 개발행위 문맥 키워드 — 이 문맥 안의 '경사도 N도'만 채택(오탐 방어).
    #   주차장 진입로·도로 종단 경사도 등 무관 조항의 값을 잡지 않기 위한 게이트.
    _SLOPE_DEV_CONTEXT_KEYWORDS: tuple[str, ...] = (
        "개발행위", "형질변경", "토지의 형질",
    )
    # 문맥 탐색 창(경사도 매치 앞쪽 문자 수) — 조문 헤더 '제N조(개발행위허가의 기준)'
    #   에서 항 번호를 거쳐 값까지의 통상 거리를 흡수하되, 무관 조문까지 넘보지 않게 제한.
    _SLOPE_CONTEXT_WINDOW: int = 400

    # '경사도' 앵커 뒤에서 'N도' 값을 찾는다. 종전 정규식은 '경사도\s*조사\s*N도'로
    #   붙어있는 표현만 잡아, 실제 조례의 '평균경사도의 경우 처인구 지역은 20도 이하'처럼
    #   '경사도'와 'N도' 사이에 지역명 등 텍스트가 끼면 전량 놓쳤다(라이브: 용인시 조례에
    #   경사도 20/17.5도가 명백히 있는데 None). → 앵커('경사도') 뒤 POST_WINDOW 안의 'N도'
    #   값들을 모두 수집하도록 분리한다(구·지역별 다중값 흡수).
    _SLOPE_VALUE_RE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*도")
    # '경사도' 뒤 값 탐색창(문자 수) — '처인구 지역은 20도, 기흥구 지역은 17.5도'처럼
    #   구별 값 나열을 흡수하되 무관 조문까지 넘보지 않게 제한.
    _SLOPE_POST_WINDOW: int = 90
    # ★오탐 방어: 앵커('경사도')가 개발행위 '평균경사도'가 아니라 도로 종단경사·구조물 경사인
    #   경우(예: '종단경사도','도로의 경사도') 그 앵커는 건너뛴다(직전 6자 수식어 검사).
    _SLOPE_ANCHOR_BAD_PREFIX: tuple[str, ...] = ("종단", "도로", "진입", "옹벽", "구조물")
    # ★오탐 방어: 앵커 뒤 값 탐색 중 '다른 각도(度) 측정 주체'를 도입하는 명사가 나오면 그
    #   지점에서 탐색창을 절단한다 — 뒤따르는 'N도'는 경사도 기준이 아니라 도로종단경사·기준온도·
    #   방위 등 무관 각도값이므로 삼키지 않는다(라이브 회귀 재현: 진입도로 종단경사 12도를 25도
    #   기준으로 오채택하던 것 차단). ★'도(度)' 단위를 만드는 명사만 넣는다 — 표고·높이·폭은
    #   미터(m) 단위라 'N도'를 만들지 않으면서 구별 나열('…높이 제한구역인 기흥구 17.5도') 사이에
    #   끼면 정당한 값을 과잉절단하므로 제외한다. 구·지역 나열은 절단어가 아니라 다중값 보존.
    _SLOPE_SUBJECT_BREAK: tuple[str, ...] = ("도로", "종단", "진입", "온도", "방위")
    # 상식 범위 방어: 개발행위 기준 경사도는 통상 10~30도(별표4 국가기준 25도).
    #   45도 초과는 오독(각도 외 수치 혼입) 가능성이 높아 채택하지 않는다(None 폴백).
    _SLOPE_MAX_PLAUSIBLE_DEG: float = 45.0

    def _parse_slope_criteria_from_text(
        self, xml_text: str, region_name: str
    ) -> dict[str, Any] | None:
        """조례 본문에서 '개발행위 문맥의 경사도 N도' 기준을 추출한다(순수함수).

        반환: {"slope_deg": float, "ordinance_name": str, "evidence_span": str,
               "caveat": str|None} 또는 None(추출 실패 — 값 날조 금지).
        오탐 방어: 매치 앞 _SLOPE_CONTEXT_WINDOW 자 안에 개발행위 키워드가 있어야
        채택. 무관 조항(주차장·도로 경사도)은 문맥 미충족으로 배제된다.
        """
        # CDATA 추출은 기존 BCR/FAR 파서와 동일 규약(']]>' 정확 종결 + 변형 폴백).
        chunks = re.findall(r"CDATA\[(.*?)\]\]>", xml_text or "", re.DOTALL)
        if not chunks:
            chunks = re.findall(r"CDATA\[(.*?)\]", xml_text or "", re.DOTALL)
        full_text = self._normalize_ws(" ".join(chunks))
        if not full_text:
            return None

        # '경사도' 앵커마다: (a)앵커가 도로종단·구조물 경사면 배제 (b)개발행위 문맥이어야 채택
        #   (c)뒤 탐색창을 '다른 측정주체' 명사에서 절단한 뒤 그 안의 'N도'만 수집.
        #   구·지역별 상이(예: 처인구 20도/기흥구 17.5도)는 절단어가 아니므로 다중값 보존.
        found: list[tuple[float, int]] = []  # (경사도값, 앵커위치)
        for am in re.finditer("경사도", full_text):
            # (a) 앵커 배제 — '종단경사도'·'도로 경사도' 등은 개발행위 평균경사도가 아니다.
            prefix = full_text[max(0, am.start() - 6):am.start()]
            if any(k in prefix for k in self._SLOPE_ANCHOR_BAD_PREFIX):
                continue
            # (b) 개발행위 문맥(앞 400자) 아니면 배제(주차장·도로 조항 등).
            pre = full_text[max(0, am.start() - self._SLOPE_CONTEXT_WINDOW):am.start()]
            if not any(k in pre for k in self._SLOPE_DEV_CONTEXT_KEYWORDS):
                continue
            # (c) 탐색창을 '다른 측정주체' 명사에서 절단(앵커 자신 '경사도' 3자 이후부터 탐색).
            post = full_text[am.start():am.start() + self._SLOPE_POST_WINDOW]
            cut = len(post)
            for br in self._SLOPE_SUBJECT_BREAK:
                i = post.find(br, 3)
                if i != -1:
                    cut = min(cut, i)
            post = post[:cut]
            for vm in self._SLOPE_VALUE_RE.finditer(post):
                try:
                    v = float(vm.group(1))
                except ValueError:  # pragma: no cover — \d 매치라 사실상 불가
                    continue
                if 0.0 < v <= self._SLOPE_MAX_PLAUSIBLE_DEG:
                    found.append((v, am.start()))

        if not found:
            return None

        # 구·지역별 상이 가능 → 안전측(가장 엄격한 최소값)을 채택하고, 변동은 caveat로 정직 고지.
        #   sigungu 레벨 조회라 자치구를 특정할 수 없으므로 최소값이 안전(무날조: 값 지어내지 않음).
        distinct = sorted({v for v, _ in found})
        chosen = distinct[0]
        anchor = min(pos for v, pos in found if v == chosen)

        near = full_text[max(0, anchor - 40):anchor + 20]
        caveats: list[str] = []
        if len(distinct) > 1:
            caveats.append(
                "구·지역별로 경사도 기준이 상이("
                + "/".join(f"{v:g}도" for v in distinct)
                + f") — 안전측 최소값 {chosen:g}도 적용(해당 구 조례 재확인 권장)"
            )
        if any(k in near for k in ("다만", "경과조치", "종전", "적용하지")):
            caveats.append("단서·경과조치 맥락에서 추출된 값일 수 있음(원문 재확인 권장)")
        caveat = " / ".join(caveats) if caveats else None

        # 근거 스니펫(설명가능성 기본): 앵커 주변 원문을 동반한다.
        evidence = full_text[max(0, anchor - 40):min(len(full_text), anchor + self._SLOPE_POST_WINDOW)]
        ordin_name_match = re.search(r"<자치법규명>.*?CDATA\[([^\]]+)\]", xml_text)
        return {
            "slope_deg": chosen,
            "all_values_deg": distinct,
            "ordinance_name": (
                ordin_name_match.group(1)
                if ordin_name_match
                else f"{region_name} 도시계획 조례"
            ),
            "evidence_span": evidence.strip(),
            "caveat": caveat,
        }

    async def _fetch_ordinance_xml(self, region_name: str) -> str | None:
        """법제처 자치법규 API에서 '{region_name} 도시계획 조례' 본문 XML을 가져온다.

        기존 _fetch_from_moleg_api 와 동일한 2단 호출(목록 검색 → 본문 조회) 규약.
        API 키 미설정·조회 실패는 None(호출부가 정직 폴백).
        """
        api_key = getattr(settings, "MOLEG_API_KEY", "") or ""
        if not api_key:
            return None

        search_name = f"{region_name} 도시계획 조례"
        try:
            headers = {"User-Agent": "PropAI/1.0 (https://4t8t.net)"}
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                resp = await client.get(
                    MOLEG_ORDIN_LIST_URL,
                    params={
                        "OC": api_key,
                        "target": "ordin",
                        "type": "XML",
                        "query": search_name,
                        "display": "5",
                        "sort": "date",
                    },
                )
                resp.raise_for_status()
                ordin_id = self._parse_ordin_id(resp.text, region_name)
            if not ordin_id:
                return None
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                resp = await client.get(
                    MOLEG_ORDIN_TEXT_URL,
                    params={
                        "OC": api_key,
                        "target": "ordin",
                        "type": "XML",
                        "ID": ordin_id,
                    },
                )
                resp.raise_for_status()
                return resp.text
        except Exception as e:  # noqa: BLE001 — 외부 API 실패는 정직 폴백(None)
            logger.warning("법제처 API 조례 본문 조회 실패: %s (%s)", region_name, str(e))
            return None

    async def resolve_slope_criteria(
        self, sigungu: str | None, force_refresh: bool = False
    ) -> dict[str, Any] | None:
        """시군구 도시계획조례의 개발행위허가 경사도 기준을 조회한다(T2).

        파이프라인(기존 조례 해석과 동일 패턴):
        0. 저장본 재사용(force_refresh=False & 존재 시 — 자동 재조사 금지)
        1. 법제처 API 실시간 조회 → 개발행위 문맥 '경사도 N도' 추출
        → 성공 시 persist. ★실패는 None — 정적 시드 폴백 절대 금지(무날조).
          호출부(T1 예비판정)는 None 이면 국가기준(산지관리법 별표4, 25도)으로
          폴백하고 "해당 지자체 조례 직접 확인 필요" 캐비앳을 부착한다.

        성공 계약: {"slope_deg": float, "ordinance_name": str,
                    "verified": "api_parsed", ...(근거·캐비앳 additive)}
        sigungu 는 조례 정본 레벨 명칭(resolve_ordinance_region 산출)을 권장.
        """
        if not sigungu:
            return None

        # 0차: 저장본 재사용(사용자 재분석 시에만 갱신 — 기존 persist 규약 동일).
        if not force_refresh:
            stored = await _load_stored(sigungu, self._SLOPE_PERSIST_KEY)
            if stored and stored.get("slope_deg") is not None:
                return stored

        # 1차: 법제처 API 실시간 조회 → 파싱.
        xml_text = await self._fetch_ordinance_xml(sigungu)
        if not xml_text:
            return None
        parsed = self._parse_slope_criteria_from_text(xml_text, sigungu)
        if not parsed:
            # 본문은 확보했으나 개발행위 경사도 기준을 못 찾음 → 정직 None.
            logger.info(
                "조례 경사도 기준 미발견 — 폴백(None): sigungu=%s", sigungu
            )
            return None

        result: dict[str, Any] = {
            "slope_deg": parsed["slope_deg"],
            # 구·지역별 다중값(있으면) — 소비자(예비판정)가 안전측 최소 채택을 이해·표기하도록 전달.
            "all_values_deg": parsed.get("all_values_deg"),
            "unit": "도",
            "ordinance_name": parsed["ordinance_name"],
            "verified": "api_parsed",
            "sigungu": sigungu,
            "source": "법제처API",
            "legal_basis": (
                f"{parsed['ordinance_name']}(개발행위허가 기준) 및 "
                "국토의 계획 및 이용에 관한 법률 시행령 제56조 별표1의2"
            ),
            "evidence_span": parsed.get("evidence_span"),
            "caveat": parsed.get("caveat"),
        }
        # 성공값만 persist(실패·미확정은 저장하지 않음 — cross-tenant 오염 방지 규약 동일).
        await _save_resolution(result, sigungu, self._SLOPE_PERSIST_KEY)
        return result

    def _lookup_cache(
        self, sido: str, sigungu: str | None, zone_type: str
    ) -> dict[str, float] | None:
        """정적 캐시에서 조례값 조회."""
        # 시군구 매칭 시도
        if sigungu:
            data = ORDINANCE_CACHE.get(sigungu, {}).get(zone_type)
            if data:
                return data

        # 시도 매칭
        data = ORDINANCE_CACHE.get(sido, {}).get(zone_type)
        return data

    def _extract_region(self, address: str) -> dict[str, str | None]:
        """주소에서 시도/시군구를 추출."""
        # 광역시/특별시/도
        SIDO_LIST = [
            "서울특별시", "부산광역시", "대구광역시", "인천광역시",
            "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
            "경기도", "강원도", "충청북도", "충청남도",
            "전라북도", "전라남도", "경상북도", "경상남도", "제주특별자치도",
        ]
        SIDO_SHORT = {
            "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
            "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
            "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
            "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
            "전북": "전라북도", "전남": "전라남도", "경북": "경상북도",
            "경남": "경상남도", "제주": "제주특별자치도",
        }

        sido = None
        for s in SIDO_LIST:
            if s in address:
                sido = s
                break
        if not sido:
            for short, full in SIDO_SHORT.items():
                if short in address:
                    sido = full
                    break

        # 시군구 추출 (시/군/구 패턴)
        sigungu = None
        sigungu_match = re.search(r"(?:서울|부산|대구|인천|광주|대전|울산|경기|강원|충[북남]|전[북남]|경[북남]|제주)\S*\s+(\S+[시군구])", address)
        if sigungu_match:
            sigungu = sigungu_match.group(1)
        else:
            # 간단 패턴: "OO시", "OO군", "OO구"
            match = re.search(r"(\S{2,4}[시군구])\s", address)
            if match:
                candidate = match.group(1)
                # 광역시 자체를 시군구로 잡지 않도록
                if candidate not in SIDO_LIST and "특별" not in candidate and "광역" not in candidate:
                    sigungu = candidate

        return {"sido": sido or "미확인", "sigungu": sigungu}
