"""부동산 등기정보 분석 — 법무사·변호사 에이전트 권리분석.

등기부등본(CODEF 조회 또는 직접 입력 텍스트)을 법무사/변호사 관점에서 분석해
소유정보·소유기간·매입금액·보유지분·가등기·압류/가압류·근저당·매도청구 가능여부 등
권리관계를 구조화해 제공한다. LLM 실패 시 graceful 폴백.
"""

import time
from typing import Any

import structlog

from app.services.ai.llm_failure import classify_failure as _classify_failure
from app.services.ai.llm_failure import failure_reason as _failure_reason
from app.services.common.exc_detail import exc_detail
from app.utils.pnu import is_valid_pnu

logger = structlog.get_logger(__name__)

# 등기 분석 결과 캐시(모듈) — CODEF 발급은 느리고(약 40~50s) 유료라 동일 필지 재분석을
# 즉시 응답하고 비용을 절약한다. 키=(pnu|address, realty_type, dong, ho). TTL 6시간.
_ANALYZE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_ANALYZE_TTL = 6 * 3600.0          # 인메모리(프로세스) 캐시
_ANALYZE_DB_TTL = 7 * 24 * 3600    # DB 영속 공유 캐시(7일) — 재분석은 선납금 소모라 길게 보관
_ANALYZE_DDL = (
    "CREATE TABLE IF NOT EXISTS registry_analysis_cache ("
    "key text PRIMARY KEY, result jsonb NOT NULL, created_at timestamptz DEFAULT now())"
)


def _cache_success(result: dict[str, Any] | None) -> bool:
    """캐시 적중을 '성공 분석'만 인정 — LLM 폴백('분석 불가', ai.generated=False)은 캐시 미스로
    취급해 재분석한다(provider/LLM 회복 후 stale 실패가 영구 서빙되는 것 방지·self-heal)."""
    if not isinstance(result, dict):
        return False
    ai = result.get("ai")
    return bool(isinstance(ai, dict) and ai.get("generated"))


def _norm_addr(s: str | None) -> str:
    return " ".join((s or "").split()).strip()


def _cache_key(address: str | None, pnu: str | None, realty_type: str | None,
               dong: str | None, ho: str | None) -> str:
    """페이지·호출부와 무관하게 동일 필지는 동일 키. 주소(정규화) 우선, realty 기본 토지(2)."""
    base = _norm_addr(address) or (pnu or "")
    # ★★스키마 버전을 키에 넣는다. 없으면 **프롬프트 스키마를 늘려도 옛 캐시가 그대로 반환**되어
    #   새 필드가 영영 비고, 소비처는 그것을 "자료 없음"으로 읽는다(이 저장소가 이미 겪은
    #   '폴백 캐시 박제' 결함 클래스). 스키마를 바꿀 때마다 이 값을 올린다.
    #   v2: ownership.ownership_history 추가(주택법 §22 상속 보유기간 합산 근거)
    # ★변이 도구가 이 접두 삭제를 **생존**으로 보고한다(설명 가능한 생존):
    #   캐시 키는 **DB/Redis 왕복**이 있어야 효과가 관측되는데 단위 테스트는 그 층을 안 태운다.
    #   여기에 문자열을 복창하는 락(`assert key.startswith("v2|")`)을 만들면 **동어반복**이라
    #   스키마를 바꾸고 버전을 안 올리는 진짜 실수를 못 잡는다.
    #   대신 규율을 코드에 남긴다: **스키마를 바꾸면 이 값을 올린다.** 안 올리면 옛 캐시가
    #   새 필드 없이 반환되고 소비처가 그것을 "자료 없음"으로 읽는다(폴백 캐시 박제).
    return f"v2|{base}|{realty_type or '2'}|{dong or ''}|{ho or ''}"


async def _db_cache_get(key: str) -> dict[str, Any] | None:
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await db.execute(text(_ANALYZE_DDL)); await db.commit()
            row = (await db.execute(
                text("SELECT result, extract(epoch from created_at) AS ts "
                     "FROM registry_analysis_cache WHERE key = :k"), {"k": key})).first()
            if row and row[0] and (time.time() - float(row[1] or 0)) < _ANALYZE_DB_TTL:
                return row[0]
    except Exception as e:  # noqa: BLE001
        logger.warning("등기분석 DB캐시 조회 실패", err=exc_detail(e, limit=80))
    return None


async def _db_cache_put(key: str, result: dict[str, Any]) -> None:
    try:
        import json as _json

        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await db.execute(text(_ANALYZE_DDL))
            await db.execute(text(
                "INSERT INTO registry_analysis_cache(key, result, created_at) "
                "VALUES (:k, CAST(:v AS jsonb), now()) "
                "ON CONFLICT (key) DO UPDATE SET result = EXCLUDED.result, created_at = now()"),
                {"k": key, "v": _json.dumps(result, ensure_ascii=False, default=str)})
            # ★만료행을 **물리적으로** 지운다. 종전엔 TTL 을 읽기에서만 걸어, 읽히지 않는
            #   등기부 사본(소유자명·발급 PDF 서명 URL)이 이 표에 **무기한** 쌓였다.
            #   `app/core/charge_idempotency.py` 가 경고한 "30일 TTL 삭제를 우회하는 사본"과
            #   같은 형태다 — 캐시를 늘리면서 그 결함을 함께 남기지 않는다.
            await db.execute(
                text("DELETE FROM registry_analysis_cache "
                     "WHERE created_at < now() - make_interval(secs => :ttl)"),
                {"ttl": _ANALYZE_DB_TTL})
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("등기분석 DB캐시 저장 실패", err=exc_detail(e, limit=80))


# ── 발급 원본 캐시 — **돈이 들어간 산출물**을 분석 성공/실패와 분리해 보관 ──────────────
#
# ★왜 필요한가(2026-08-24 실측). 분석 캐시는 `_cache_success` 로 **성공만** 저장한다. LLM 이
#   실패하면 캐시 미스가 되고, 다음 시도는 `RegistryService.get_one()` 을 **다시** 부른다.
#   그 층에는 캐시가 없다(실측: `registry_service.py` 에 cache 참조 0건). 즉 등기부가
#   **다시 발급되고 민원캐시가 다시 차감된다** — 사용자에게는 1,200원을 안 받는데
#   (`analysis_charged` 가 막는다) **선불 잔액은 탄다.**
#
#   `app/core/charge_idempotency.py` 는 자기 근거로 *"읽기는 기존 캐시가 흡수하므로 외부
#   발급이 다시 나가지도 않는다"* 고 적어 두었다. **실패 경로에서 그 전제가 깨진다.**
#   여기서 그 전제를 참으로 만든다.
#
# ★무엇을 보관하나: 발급이 **성공한 경우**(reg.status=="ok") 그 산출물 — 본문 텍스트·출처·
#   `fetched` 메타(PDF 서명 URL 포함). 발급이 실패한 경우는 보관하지 않는다(받은 것이 없으므로
#   재시도가 다시 발급하는 것이 옳다).
#
# ★★영속하지 않는다 — **인메모리 전용(6시간)**. 이유는 둘이고, 둘 다 캐시 적중률보다 무겁다:
#   ① **개인정보**: 여기 담기는 것은 등기부 **본문 전문**(소유자·근저당권자 등)이다.
#      `charge_idempotency.py` 가 이미 경고했다 — *"저장 대상이 등기부 전문이고 만료도
#      프루닝도 없어 30일 TTL 삭제를 우회하는 사본이 무기한 쌓인다"*. 그 결함을 캐시를
#      늘리면서 새로 만들지 않는다. 기존 표가 보관하는 것은 **파생물**(`land`·`ai`)이지
#      본문이 아니다 — 그 선을 넘지 않는다.
#   ② **신선도**: 등기부는 시점 문서다. 6시간은 7일보다 안전하다.
#   ★정직한 한계: 워커가 여러 개면 재사용은 **프로세스 단위**다. 다른 워커로 간 요청은
#     다시 발급한다 — 반복 조회의 낭비는 거의 사라지지만 0은 아니다.
#
# ★신선도 비교(참고): 성공 분석은 인메모리 6시간 / DB 7일로 이미 캐시된다. 등기부는 변하지만, 이
#   플랫폼은 이미 성공한 분석을 7일간 캐시로 돌려주고 있다 — 실패 건만 매번 새로 발급하던
#   것이 오히려 비대칭이었다. 새 신선도 위험을 만드는 게 아니라 **기존 정책에 맞추는** 것이다.
#   그래도 재사용 사실과 발급 시각은 응답에 실어 화면이 말할 수 있게 한다.
#
# ★굳어붙지 않게: 발급본이 쓸모없었던 경우(이미지 PDF 등)도 재사용되므로, 호출측이
#   `force_reissue=True` 로 **명시적으로** 새 발급을 요청할 수 있다(돈이 드는 행위라 기본 아님).
_SOURCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _source_key(cache_key: str) -> str:
    return f"src|{cache_key}"


async def _source_cache_get(key: str) -> dict[str, Any] | None:
    hit = _SOURCE_CACHE.get(key)
    if hit and (time.time() - hit[0]) < _ANALYZE_TTL:
        return hit[1]
    return None


async def _source_cache_put(key: str, payload: dict[str, Any]) -> None:
    _SOURCE_CACHE[key] = (time.time(), payload)


# ── 결정론적 실패 기억 — **같은 실패를 다시 사지 않는다** ──────────────────────
#
# ★왜(2026-08-25). 실패한 분석은 캐시하지 않는다(자가치유). 그런데 **결정론적** 실패는
#   회복되지 않으므로, 그 설계가 "볼 때마다 LLM 을 다시 사는" 결과를 낳는다 —
#   등기 재발급 누수와 **같은 얼굴**이고 축만 다르다(벤더 발급 → LLM 토큰).
#   실측 사례: 긴 등기부의 응답 절단(`parse`)은 같은 본문이면 매번 같은 자리에서 실패한다.
#
# ★일시 실패는 **절대 기억하지 않는다**(타임아웃·과부하·잔액). 그걸 기억하면 회복을 막는다.
#   `llm_failure.is_retry_worthwhile` 이 그 판정의 단일 출처다.
#
# ★TTL 을 짧게(30분) 둔다 — 근본을 고쳐 배포해도 사용자가 오래 갇히지 않게. 그래도 갇히면
#   `force_reissue=True` 가 모든 기억을 건너뛴다.
_FAILURE_TTL = 30 * 60.0
_FAILURE_MEMO: dict[str, tuple[float, dict[str, Any]]] = {}


def _failure_memo_get(key: str) -> dict[str, Any] | None:
    hit = _FAILURE_MEMO.get(key)
    if not hit:
        return None
    if (time.time() - hit[0]) >= _FAILURE_TTL:
        _FAILURE_MEMO.pop(key, None)
        return None
    return hit[1]


def _failure_memo_put(key: str, ai: dict[str, Any]) -> None:
    _FAILURE_MEMO[key] = (time.time(), ai)


async def peek_analyze_cache(
    address: str | None = None, pnu: str | None = None, realty_type: str | None = None,
    dong: str | None = None, ho: str | None = None, registry_text: str | None = None,
) -> dict[str, Any] | None:
    """동일 필지의 성공 분석이 인메모리 또는 DB(영속·공유)에 있으면 반환(작업 제출 전 즉시반환)."""
    if registry_text and registry_text.strip():
        return None
    key = _cache_key(address, pnu, realty_type, dong, ho)
    hit = _ANALYZE_CACHE.get(key)
    if hit and (time.time() - hit[0]) < _ANALYZE_TTL and _cache_success(hit[1]):
        return {**hit[1], "cached": True}
    db_hit = await _db_cache_get(key)
    if db_hit and _cache_success(db_hit):
        _ANALYZE_CACHE[key] = (time.time(), db_hit)  # 인메모리 승격
        return {**db_hit, "cached": True}
    return None

_SYSTEM = """\
당신은 부동산 등기·권리분석 전문가 패널(법무사 20년 + 부동산 전문 변호사)입니다.
제시된 부동산등기부등본 내용만 근거로 권리관계를 법무사 실무 기준으로 정확히 분석합니다.
- 갑구(소유권): 소유자·지분·소유권 변동·거래가액·가등기·가처분·압류·가압류·경매개시
- 을구(소유권 이외): 근저당권(채권최고액·근저당권자)·전세권·지상권·임차권 등
[법무사 판단 규칙]
1) 말소기준권리: (근)저당권·압류·가압류·담보가등기·경매개시결정 중 '최선순위' 등기를 기준으로 본다.
2) 인수/소멸: 말소기준권리보다 후순위 권리는 정리(매각) 시 원칙적 소멸, 선순위 권리·선순위 가처분·
   순위보전 가등기·대항력 있는 임차권/전세권은 인수 대상이 될 수 있음을 명시한다.
3) 대항력: 대항요건(점유·전입 등)이 말소기준권리보다 앞서면 인수 위험으로 본다(등기상 단서가 있으면).
4) 개발 관점: 매도청구·지분정리·근저당 말소조건·선순위 위험을 개발 실행 리스크로 연결한다.
원칙: 등기 내용에 있는 사실만 사용, 없으면 '기재 없음'. 추측·과장 금지. 법률자문이 아닌
참고용 분석임을 전제. 반드시 JSON만 출력."""

_TMPL = """\
아래 부동산등기부등본 내용을 법무사·변호사 관점에서 분석해 JSON으로만 답하세요.
{addr_line}
## 등기부 내용
{registry}

## 출력 JSON 스키마
{{
  "ownership": {{
    "current_owner": "현재 소유자(공동소유면 전원)",
    "share": "보유 지분(예: 단독, 1/2 등)",
    "ownership_form": "단독소유|공동소유 (소유자 수 기준)",
    "owners": [{{"name": "소유자명", "share": "지분(예: 1/2, 1388분의 1387.08, 99.934%)", "acquisition_date": "취득일", "acquisition_cause": "취득원인", "acquisition_price": "거래가액(있으면)"}}],
    "acquisition_date": "소유권 취득일(등기원인일/접수일)",
    "acquisition_cause": "취득 원인(매매·상속·증여 등)",
    "acquisition_price": "거래가액(매매시, 기재 있으면)",
    "ownership_period": "현 소유자 보유기간(취득일~현재 추정)",
    "ownership_history": [{{"date": "접수일/등기원인일", "cause": "이전 원인(매매·상속·증여 등)", "owner": "취득자", "predecessor": "전 소유자(기재 있으면)", "share": "지분"}}]
  }},
  "provisional_registration": {{"exists": true/false, "detail": "가등기 내용(있으면)"}},
  "seizure": [{{"type": "압류|가압류|경매개시|가처분", "holder": "권리자", "detail": "내용", "date": "일자"}}],
  "mortgage": [{{"max_claim": "채권최고액", "mortgagee": "근저당권자", "date": "설정일"}}],
  "other_rights": ["전세권·지상권·임차권 등 기타 권리(있으면)"],
  "baseline_right": "말소기준권리(최선순위 (근)저당·압류·가압류·담보가등기·경매개시 등) — 없으면 '해당 없음'",
  "acquired_extinguished": "인수/소멸 권리 요약(말소기준권리 기준 후순위 소멸·선순위/대항력 인수, 1~3문장) — 판단불가면 '기재 없음'",
  "right_to_demand_sale": {{"possible": "가능|조건부|불가|판단보류", "reason": "근거(소유구조·권리관계 관점)"}},
  "rights_analysis": "권리관계 종합 분석(말소기준권리·인수/소멸·대항력 포함, 3~5문장)",
  "risks": ["거래·개발상 권리 리스크 1~4개"],
  "safety_grade": "안전|주의|위험",
  "summary": "한줄 요약"
}}

★`ownership.ownership_history` 는 **갑구의 소유권 이전 등기를 오래된 것부터 순서대로** 담는다.
  상속으로 취득한 경우 「주택법」 제22조가 **피상속인의 소유기간을 합산**하도록 정하므로,
  전 소유자(`predecessor`)와 그 취득일을 알 수 있으면 반드시 함께 적는다.
  ★등기 내용에 없는 것은 만들지 말고 해당 항목을 생략한다(추정 금지).
"""


# ═══ A-2b: 절단(truncation) 시에만 발화하는 **분할 프롬프트** ═══════════════════
# ★왜 분할이 절단을 없애나: `max_tokens` 가 캡하는 것은 **출력**이다. 위 `_TMPL` 은
#   사실(소유·이력·압류·근저당·기타권리)과 **산문**(rights_analysis 3~5문장·risks·
#   acquired_extinguished)을 **한 응답에** 요구해서, 등기부가 길면 출력이 캡에 닿아 잘린다
#   (라이브 실측 — 코드펜스가 닫히지 않은 채 끝났다). 스키마를 둘로 나누면 **각 응답의
#   출력이 짧아진다.**
#
# ★★2단의 입력에 **원문 등기부를 그대로 넣는다.** 잘리는 것은 출력이지 입력이 아니므로,
#   사실 JSON 만 넘겨 근거를 얇게 만들 이유가 없다 — 말소기준권리 순위·대항력 판단은
#   등기 원문의 접수번호·순위번호를 봐야 정확하다. (설계 초안은 "사실만 넘긴다"였고,
#   그것은 **불필요한 품질 손실**이었다. 캡의 대상을 잘못 짚은 데서 나온 설계다.)
_TMPL_FACTS = """\
아래 부동산등기부등본에서 **사실관계만** 추출해 JSON으로만 답하세요.
★해석·판단·산문은 쓰지 마세요(다음 단계에서 따로 합니다). 출력을 짧게 유지합니다.
{addr_line}
## 등기부 내용
{registry}

## 출력 JSON 스키마
{{
  "ownership": {{
    "current_owner": "현재 소유자(공동소유면 전원)",
    "share": "보유 지분(예: 단독, 1/2 등)",
    "ownership_form": "단독소유|공동소유 (소유자 수 기준)",
    "owners": [{{"name": "소유자명", "share": "지분(예: 1/2, 1388분의 1387.08, 99.934%)", "acquisition_date": "취득일", "acquisition_cause": "취득원인", "acquisition_price": "거래가액(있으면)"}}],
    "acquisition_date": "소유권 취득일(등기원인일/접수일)",
    "acquisition_cause": "취득 원인(매매·상속·증여 등)",
    "acquisition_price": "거래가액(매매시, 기재 있으면)",
    "ownership_period": "현 소유자 보유기간(취득일~현재 추정)",
    "ownership_history": [{{"date": "접수일/등기원인일", "cause": "이전 원인(매매·상속·증여 등)", "owner": "취득자", "predecessor": "전 소유자(기재 있으면)", "share": "지분"}}]
  }},
  "provisional_registration": {{"exists": true/false, "detail": "가등기 내용(있으면)"}},
  "seizure": [{{"type": "압류|가압류|경매개시|가처분", "holder": "권리자", "detail": "내용", "date": "일자"}}],
  "mortgage": [{{"max_claim": "채권최고액", "mortgagee": "근저당권자", "date": "설정일"}}],
  "other_rights": ["전세권·지상권·임차권 등 기타 권리(있으면)"]
}}

★`ownership.ownership_history` 는 **갑구의 소유권 이전 등기를 오래된 것부터 순서대로** 담는다.
  상속으로 취득한 경우 「주택법」 제22조가 **피상속인의 소유기간을 합산**하도록 정하므로,
  전 소유자(`predecessor`)와 그 취득일을 알 수 있으면 반드시 함께 적는다.
  ★등기 내용에 없는 것은 만들지 말고 해당 항목을 생략한다(추정 금지).
"""

_TMPL_JUDGE = """\
아래 부동산등기부등본과 그것에서 추출한 사실관계 JSON을 근거로 **권리 판단만** JSON으로 답하세요.
★사실 재나열은 하지 마세요(이미 확보했습니다). 출력을 짧게 유지합니다.
{addr_line}
## 등기부 내용
{registry}

## 추출된 사실관계(JSON)
{facts}

## 출력 JSON 스키마
{{
  "baseline_right": "말소기준권리(최선순위 (근)저당·압류·가압류·담보가등기·경매개시 등) — 없으면 '해당 없음'",
  "acquired_extinguished": "인수/소멸 권리 요약(말소기준권리 기준 후순위 소멸·선순위/대항력 인수, 1~3문장) — 판단불가면 '기재 없음'",
  "right_to_demand_sale": {{"possible": "가능|조건부|불가|판단보류", "reason": "근거(소유구조·권리관계 관점)"}},
  "rights_analysis": "권리관계 종합 분석(말소기준권리·인수/소멸·대항력 포함, 3~5문장)",
  "risks": ["거래·개발상 권리 리스크 1~4개"],
  "safety_grade": "안전|주의|위험",
  "summary": "한줄 요약"
}}
"""

# ★두 단계가 **덮는 키**를 파생형으로 못 박는다 — 손으로 나열하면 스키마에 키를 더할 때
#   조용히 빠지고, 그 키는 분할 경로에서만 영영 비어 있게 된다(정상 경로는 초록이라 안 보인다).
_SPLIT_FACT_KEYS = ("ownership", "provisional_registration", "seizure", "mortgage", "other_rights")
_SPLIT_JUDGE_KEYS = ("baseline_right", "acquired_extinguished", "right_to_demand_sale",
                     "rights_analysis", "risks", "safety_grade", "summary")


def _derive_ownership(ai: dict[str, Any] | None) -> dict[str, Any]:
    """등기 분석(ai.ownership)에서 소유형태(단독/공동)·소유자수·소유자목록을 도출.
    AI가 구조화 owners를 주면 그대로, 없으면 current_owner/share 문자열을 파싱."""
    own = (ai or {}).get("ownership") or {}
    owners = own.get("owners") if isinstance(own.get("owners"), list) else None
    if not owners:
        # 폴백: "이차희(1388분의 0.92), 주식회사더플라우(...)" / share "A 0.066%, B 99.934%"
        import re
        names = [s.strip() for s in re.split(r"\s*,\s*", str(own.get("current_owner") or "")) if s.strip()]
        shares = [s.strip() for s in re.split(r"\s*,\s*", str(own.get("share") or "")) if s.strip()]
        owners = []
        for i, n in enumerate(names):
            nm = re.sub(r"\(.*?\)", "", n).strip()
            owners.append({"name": nm or n, "share": shares[i] if i < len(shares) else None})
    owners = [o for o in (owners or []) if (o.get("name") or "").strip() and o.get("name") != "데이터 없음"]
    if not owners:
        return {}
    form = own.get("ownership_form") or ("공동소유" if len(owners) >= 2 else "단독소유")
    return {"ownership_form": form, "owner_count": len(owners), "owners": owners}


def _has_registry_entries(text: str) -> bool:
    """등기사항(갑구·을구 등) 본문이 실제로 담겼는지 — 머리말만 있는 텍스트와 구별.

    왜 필요한가: 구조화 텍스트가 "소유자(요약): 홍길동" 한 줄이어도 '비어있지 않다'는
    이유로 PDF 전문 그라운딩이 스킵되면, 근저당·압류가 통째로 빠진 껍데기 권리분석이
    나온다(하이픈 이관 후 실제로 그렇게 동작했다). 등기사항 줄("[갑구] …")의 존재로 판정한다.
    """
    # 실제 등기부 전문은 전각 괄호(【갑구】)를 쓰고, 우리가 구성한 요약은 반각([갑구])을 쓴다.
    # 둘 다 '등기사항 있음'으로 본다 — 프로바이더 제공 전문을 빈 것으로 오판하면 안 된다.
    return any(ln.startswith(("[", "【")) for ln in (text or "").splitlines())


def _registry_text_from_codef(reg: dict[str, Any]) -> str:
    """CODEF 등기부 응답(구조화)에서 분석용 텍스트 구성.

    하이픈 응답에는 resRegisterEntriesList가 없어 머리말(소유자·관할등기소)만 남는다 —
    그 경우 _has_registry_entries가 False가 되어 호출부가 PDF 전문으로 그라운딩한다.
    """
    parts: list[str] = []
    if reg.get("doc_title"):
        parts.append(f"문서: {reg['doc_title']}")
    if reg.get("owner"):
        parts.append(f"소유자(요약): {reg['owner']}")
    if reg.get("registry_office"):
        parts.append(f"관할등기소: {reg['registry_office']}")
    # 주소목록 소유자(있으면)
    for a in (reg.get("addr_list") or []):
        if a.get("resUserNm"):
            parts.append(f"[소유자(주소목록)] {a.get('resUserNm')} / 고유번호 {a.get('commUniqueNo','')}")
    raw = reg.get("raw") or reg
    entries = reg.get("entries") or (raw.get("resRegisterEntriesList") if isinstance(raw, dict) else None) or []
    # 등기사항 요약/내용 직렬화(있는 만큼)
    for entry in entries:
        for sm in (entry.get("resRegistrationSumList") or []):
            t = sm.get("resType", "")
            for cl in (sm.get("resContentsList") or []):
                for dl in (cl.get("resDetailList") or []):
                    if dl.get("resContents"):
                        parts.append(f"[{t}] {dl['resContents']}")
        for his in (entry.get("resRegistrationHisList") or []):
            t = f"{his.get('resType','')}/{his.get('resType1','')}"
            for cl in (his.get("resContentsList") or []):
                for dl in (cl.get("resDetailList") or []):
                    if dl.get("resContents"):
                        parts.append(f"[{t}] {dl['resContents']}")
    return "\n".join(parts)[:8000]


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """등기부등본 PDF에서 분석용 텍스트 추출(법무사 권리분석 입력 보강).
    apick xlsx 추출이 비어 PDF만 확보된 경우의 폴백. 텍스트형 PDF만 추출되며
    스캔(이미지) PDF는 빈 문자열을 반환한다(graceful — OCR 미적용, 무리한 추측 금지).
    PyMuPDF(이미 의존성·해촉증명서 래스터에 사용) 재사용 — 신규 의존성 없음."""
    if not pdf_bytes:
        return ""
    try:
        try:
            import pymupdf as _fitz  # PyMuPDF ≥1.24
        except ImportError:
            import fitz as _fitz  # 구버전 별칭
        doc = _fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()[:8000]
    except Exception:  # noqa: BLE001 — 의존성/추출 실패 시 빈 문자열(폴백 경로 유지)
        return ""


class RegistryAnalysisService:
    async def _land_info(self, address: str | None, pnu: str | None) -> dict[str, Any] | None:
        """토지 소유구분·지목·면적·공시지가·용도지역(VWorld/공공데이터). 등기부 미연동 시에도 제공."""
        if not address and not pnu:
            return None
        try:
            from app.services.external_api.vworld_service import VWorldService
            from app.services.zoning.auto_zoning_service import AutoZoningService

            vworld = VWorldService()
            owner_type = None
            land_area = land_category = official_price = zone_type = None
            # ★유효한 PNU 만 외부 조회에 쓴다. 종전엔 검증이 없어 PNU 칸의 오염값
            #   (라이브 실측: 성명 `'◀ 전성결'` · `'store-rep-…'`)이 그대로
            #   `vworld.get_land_info()` 로 나갔다 — 실패가 예정된 외부 호출이고,
            #   주소가 있으면 아래 `AutoZoningService` 가 **진짜 PNU 를 준다**.
            effective_pnu = pnu if is_valid_pnu(pnu) else None
            if address:
                az = await AutoZoningService().analyze_by_address(address)
                effective_pnu = effective_pnu or az.get("pnu")
                zone_type = az.get("zone_type")
                land_area = az.get("land_area_sqm")
                land_category = az.get("land_category")
                official_price = az.get("official_price_per_sqm")
            if effective_pnu:
                li = await vworld.get_land_info(effective_pnu)
                if li:
                    props = li.get("properties") or {}
                    owner_type = props.get("owner_type")
                    land_area = land_area or props.get("area")
                    land_category = land_category or props.get("jimok")
                lc = await vworld.get_land_characteristics(effective_pnu)
                if lc:
                    land_area = land_area or lc.get("area_sqm")
                    land_category = land_category or lc.get("land_category")
                    official_price = official_price or lc.get("official_price_per_sqm")
                    zone_type = zone_type or lc.get("zone_type")
            return {
                "pnu": effective_pnu,
                "owner_type": owner_type,  # 소유구분(개인/국·공유 등) — 등기부 외 공부상
                "land_category": land_category,
                "land_area_sqm": land_area,
                "official_price_per_sqm": official_price,
                "zone_type": zone_type,
                "note": "공부상 소유구분·토지특성(소유자 성명·지분은 등기부 분석 결과 참조)",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("토지정보 조회 실패", err=exc_detail(e, limit=80))
            return None

    async def analyze(
        self,
        address: str | None = None,
        pnu: str | None = None,
        registry_text: str | None = None,
        realty_type: str | None = None,
        dong: str | None = None,
        ho: str | None = None,
        land_hint: dict[str, Any] | None = None,
        force_reissue: bool = False,
    ) -> dict[str, Any]:
        """등기부를 조회·해석한다.

        Args:
            force_reissue: True 면 **모든 캐시를 건너뛰고 새로 발급**한다. 돈이 드는 행위라
                기본값은 False — 호출측이 명시적으로 요청할 때만 켠다. 발급본이 쓸모없었던
                경우(이미지 PDF 등)에 갇히지 않기 위한 탈출구다.
        """
        import asyncio

        # 캐시 조회(직접 입력 텍스트는 매번 다를 수 있어 캐시 제외) — 정규화 키 + DB 영속 공유
        cache_key = None
        if not (registry_text and registry_text.strip()):
            cache_key = _cache_key(address, pnu, realty_type, dong, ho)
        if cache_key and not force_reissue:
            hit = _ANALYZE_CACHE.get(cache_key)
            if hit and (time.time() - hit[0]) < _ANALYZE_TTL and _cache_success(hit[1]):
                return {**hit[1], "cached": True}
            db_hit = await _db_cache_get(cache_key)
            if db_hit and _cache_success(db_hit):
                _ANALYZE_CACHE[cache_key] = (time.time(), db_hit)
                return {**db_hit, "cached": True}

        origin = None
        source = None
        fetched_meta = None
        # 우리가 '머리말 요약'만 합성해 둔 상태인가(= 등기사항 없음). 문자열에서 되짚지 않고
        # 만든 시점에 표시한다 — 수동 입력·프로바이더 제공 전문을 빈 것으로 오판하지 않기 위해.
        thin_summary = False

        async def _resolve_land() -> dict[str, Any] | None:
            # 공부(지목/용도지역/공시지가/소유구분/면적)는 항상 조회하고,
            # 부지분석 hint는 '빈칸 보강용'으로만 사용(이전엔 hint 있으면 공부조회를
            # 통째로 건너뛰어 지목/공시지가/소유구분이 비던 버그). CODEF와 병렬이라 지연 영향 적음.
            base = await self._land_info(address, pnu) or {}
            if land_hint:
                for k in ("pnu", "owner_type", "land_category", "land_area_sqm",
                          "official_price_per_sqm", "zone_type"):
                    if not base.get(k) and land_hint.get(k) is not None:
                        base[k] = land_hint.get(k)
            return base or None

        if registry_text and registry_text.strip():
            land = await _resolve_land()
            source = registry_text.strip()[:8000]
            origin = "manual"
        else:
            # ★★이미 발급받은 등기부가 있으면 **다시 발급하지 않는다.**
            #   발급은 민원캐시(선불 잔액)를 차감하는데, 분석 캐시는 성공만 저장하므로
            #   LLM 이 실패한 필지는 볼 때마다 재발급돼 돈이 샜다(2026-08-24 실측).
            #   여기서 재사용하면 재시도는 **해석만** 다시 한다(자가치유는 그대로 유지).
            src_key = _source_key(cache_key) if cache_key else None
            reused = await _source_cache_get(src_key) if (src_key and not force_reissue) else None
            if reused:
                land = await _resolve_land()
                source = reused.get("source") or ""
                origin = reused.get("origin")
                thin_summary = bool(reused.get("thin_summary"))
                fetched_meta = dict(reused.get("fetched") or {})
                # 재사용 사실과 발급 시각을 **응답에 싣는다** — 화면이 "언제 발급분인지"를
                #   말할 수 있어야 한다. 조용히 옛 등기부를 보여 주면 그게 곧 거짓이 된다.
                fetched_meta["reused_issue"] = True
                fetched_meta["issued_at"] = reused.get("issued_at")
                reg = None
            else:
                # CODEF 등 연동 조회 시도 — 토지정보 조회와 병렬 실행(독립적, 지연 단축)
                from app.services.registry.registry_service import RegistryService

                land, reg = await asyncio.gather(
                    _resolve_land(),
                    RegistryService().get_one(
                        pnu=pnu, address=address, realty_type=realty_type, dong=dong, ho=ho,
                        # ★아래 층에도 전달한다 — 위 캐시만 건너뛰면 발급 캐시가 그대로
                        #   옛 등기부를 돌려줘 "새로 발급"이 조용히 무시된다.
                        force_reissue=force_reissue,
                    ),
                )
            st = reg.get("status") if reg is not None else "ok"
            if st == "ok" and reg is not None:
                # apick 등은 추출 텍스트(registry_text)를 직접 제공 → 그대로 LLM 분석.
                # CODEF는 구조화 JSON → _registry_text_from_codef로 텍스트 구성.
                if reg.get("registry_text"):
                    source = reg["registry_text"]
                    origin = reg.get("origin") or "apick"
                else:
                    source = _registry_text_from_codef(reg)
                    # 출처는 실제 프로바이더를 그대로 — 하이픈 결과를 codef로 오표기하지 않는다.
                    origin = reg.get("origin") or "codef"
                    # 등기사항 없이 머리말만 나온 경우 표시(아래 PDF 그라운딩이 성공하면 해제)
                    thin_summary = not _has_registry_entries(source)
                # 발급 PDF는 서버(비공개 버킷)에 저장하고 만료 URL로 전달(TTL 자동삭제)
                # + ★PDF 그라운딩: 구조화 텍스트(xlsx)가 비어 PDF만 확보된 경우, PDF 본문에서 직접
                #   텍스트를 추출해 분석 소스로 사용(권리분석이 'PDF 미분석'으로 통째 누락되던 갭 해소).
                #   추출 실패(이미지 PDF 등) 시 source에는 머리말 요약만 남는데, 그 상태는
                #   thin_summary로 표시해 아래에서 'empty'로 정직 처리한다(껍데기 분석 금지).
                pdf_url = None
                b64 = reg.get("pdf_base64")
                if b64:
                    try:
                        import base64 as _b64

                        pdf_bytes = _b64.b64decode(b64)
                        # ★'비어있지 않음'이 아니라 '등기사항이 실제로 담겼는가'로 판정한다.
                        #   머리말 한 줄(소유자 요약)만 있는 경우도 PDF 전문으로 그라운딩해야
                        #   갑구·을구(근저당·압류)가 분석에 들어간다.
                        if not _has_registry_entries(source):
                            pdf_text = _pdf_to_text(pdf_bytes)
                            if pdf_text:
                                source = pdf_text
                                origin = f"{reg.get('origin') or 'apick'}+pdf"
                                thin_summary = False  # 전문 확보 — 껍데기 아님

                        from apps.api.services.storage_service import upload_registry_pdf

                        up = await upload_registry_pdf(pdf_bytes, ttl_days=30)
                        pdf_url = up.get("url")
                    except Exception as e:  # noqa: BLE001
                        logger.warning("등기부 PDF 처리 실패", err=exc_detail(e, limit=80))
                fetched_meta = {
                    "owner": reg.get("owner"), "registry_office": reg.get("registry_office"),
                    "doc_title": reg.get("doc_title"), "has_pdf": reg.get("has_pdf"),
                    "pdf_url": pdf_url,
                    # 어느 구분의 물건을 열람했는지 + 요청한 구분/동·호로 좁히지 못한 경우의 고지.
                    # 최종 표면까지 전달해야 "다른 물건을 조회했는데 조용히 성공"이 되지 않는다.
                    "realty_gubun": reg.get("realty_gubun"),
                    "select_note": reg.get("select_note"),
                }
                # ★★발급이 성공했다 = **돈이 나갔다**. 해석이 뒤에서 실패하더라도 이 산출물은
                #   보관한다 — 그래야 재시도가 재발급하지 않는다(민원캐시 재차감 차단).
                #   발급이 실패한 경우는 여기 오지 않으므로 보관되지 않는다(받은 게 없으니
                #   재시도가 새로 발급하는 것이 옳다).
                if src_key:
                    import datetime as _dt

                    await _source_cache_put(src_key, {
                        "source": source,
                        "origin": origin,
                        "thin_summary": thin_summary,
                        "fetched": fetched_meta,
                        "issued_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
                    })
            elif reg is not None:
                # 등기부 데이터 미확보 — 토지정보는 제공 + 직접 입력 유도
                return {
                    "status": st or "not_available",
                    "origin": "none",
                    "land": land,
                    "message": (reg.get("message")
                                or "등기부 데이터를 가져오지 못했습니다. 등기부등본 내용을 직접 입력하거나 "
                                   "등기부 API(CODEF) 설정을 완료하세요."),
                    "ai": None,
                }

        if not source or thin_summary:
            # ★머리말(소유자 요약)만 확보된 상태로 권리분석을 돌리면 근저당·압류가 '기재 없음'이
            #   되어 거짓 '안전' 등급이 나오고 캐시에 박힌다. 분석하지 않고 정직하게 반환한다.
            # ★원인을 **데이터가 말하는 대로** 고른다(라이브 실측 2026-08-24).
            #   종전엔 `thin_summary` 면 무조건 *"발급 PDF가 이미지 형식이면 텍스트 추출이
            #   되지 않습니다"* 라고 안내했다. 그런데 같은 응답이 `has_pdf=False` 인 경우가 있다 —
            #   **PDF 가 아예 없는데** 사용자에게 *"당신 PDF 형식 탓"* 이라 말하고 직접 입력을
            #   시킨 것이다. 발급 자체가 안 된 것과, 발급은 됐는데 텍스트가 안 뽑히는 것은
            #   **원인도 처방도 다르다**(전자는 기다리거나 관리자 확인, 후자는 직접 입력).
            _has_pdf = bool((fetched_meta or {}).get("has_pdf"))
            if not thin_summary:
                _msg = "분석할 등기부 내용이 없습니다."
            elif _has_pdf:
                _msg = ("등기부 본문(갑구·을구)을 확보하지 못했습니다. "
                        "발급 PDF가 이미지 형식이면 텍스트 추출이 되지 않습니다 — "
                        "등기부등본 내용을 직접 입력하시면 분석해 드립니다.")
            else:
                _msg = ("등기부가 **발급되지 않았습니다**(PDF 없음) — 소유자 요약만 확보돼 "
                        "권리분석(근저당·압류 등)을 할 수 없습니다. 등기 발급 연동 상태를 "
                        "관리자에게 확인하시거나, 등기부등본 내용을 직접 입력하시면 분석해 드립니다.")
            return {"status": "empty", "origin": origin, "land": land,
                    "fetched": fetched_meta,
                    "message": _msg,
                    "ai": None}

        # ★같은 문서가 같은 이유로 계속 실패한다면 **다시 사지 않는다**(LLM 토큰).
        #   기억은 결정론적 실패에만 남으므로, 일시 실패는 여기 걸리지 않고 그대로 재시도된다.
        memo = _failure_memo_get(cache_key) if (cache_key and not force_reissue) else None
        if memo is not None:
            # ★시도하지 않았음을 **밝힌다.** 안 하고 한 척하면 그 자체가 거짓이다.
            ai = {**memo, "remembered_failure": True}
        else:
            ai = await self._llm(address, source)
            if cache_key and not ai.get("generated"):
                from app.services.ai.llm_failure import is_retry_worthwhile

                # 분류는 폴백이 실어 보낸 것을 **그대로** 쓴다(문자열에서 다시 캐지 않는다).
                cls = str(ai.get("failure_class") or "other")
                if not is_retry_worthwhile(cls):
                    _failure_memo_put(cache_key, ai)
        # 등기 기반 소유형태(공동/단독)·소유자목록을 공부 카드(land)에 보강
        deriv = _derive_ownership(ai)
        if deriv:
            land = land or {}
            land.update(deriv)
            land["registry_owner"] = ((ai or {}).get("ownership") or {}).get("current_owner")
            if not land.get("owner_type"):
                # 공부 소유구분이 비면 등기 소유형태로 대체 표기
                land["owner_type"] = deriv["ownership_form"]
        out = {"status": "ok", "origin": origin, "land": land, "fetched": fetched_meta, "ai": ai}
        # ★성공(generated=True)만 캐시 — 실패한 권리분석(LLM 폴백 '분석 불가')을 캐시하면 provider/LLM
        #   회복 후에도 stale 실패가 영구 서빙되어 사용자가 복구 불가(자동채움이 계속 빈값). 실패는 재시도 시
        #   fresh로 다시 분석되게 한다(단, 성공 캐시는 유지해 apick 재발급 과금을 방지).
        ai_ok = bool(isinstance(ai, dict) and ai.get("generated"))
        if cache_key and ai_ok:
            _ANALYZE_CACHE[cache_key] = (time.time(), out)
            await _db_cache_put(cache_key, out)  # 영속·공유(페이지·배포 무관 재사용)
        return out

    async def _invoke(self, user: str, *, max_tokens: int = 4096) -> tuple[Any, str]:
        """LLM 1회 호출 + **과금 기록** + 텍스트 정규화의 **단일 통로**.

        ★분할 재시도(A-2b)도 반드시 이 래퍼를 경유한다. 유료 외부호출에 두 번째 경로를
          만들면 **그 경로만 과금 기록이 빠진다** — 이 저장소는 반환 지점이 여럿인 함수에
          손으로 캐시·계측을 붙였다가 하나를 빠뜨려 재과금 경로를 만든 전례가 있다
          (§유료 산출물 규율 1). 그래서 «호출 + 기록» 을 쪼갤 수 없게 묶어 둔다.

        반환: (원본 응답 객체, 정규화된 본문 문자열)
              ★응답 객체를 그대로 돌려주는 이유는 `is_truncated(resp)` 가 **메타데이터**
                (finish_reason·usage)를 보기 때문이다 — 본문 문자열만으로는 판정 불가.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.services.ai.base_interpreter import GROUNDING_RULE, record_llm_response_billing
        from app.services.ai.llm_json import coerce_llm_text
        from app.services.ai.llm_provider import get_llm

        llm = get_llm(timeout=70, max_tokens=max_tokens)
        resp = await llm.ainvoke(
            [SystemMessage(content=_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)]
        )
        # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
        await record_llm_response_billing(llm, resp, service="registry")
        raw = coerce_llm_text(resp.content if hasattr(resp, "content") else str(resp)).strip()
        return resp, raw

    async def _llm_split(self, address: str | None, registry: str) -> dict[str, Any] | None:
        """★절단이 감지됐을 때만 발화하는 **2단 분할**. 실패하면 None(호출처가 정직 폴백).

        1단 = 사실(소유·이력·압류·근저당·기타권리) · 2단 = 판단·산문.
        각 단의 **출력**이 짧아져 `max_tokens` 캡에 닿지 않는다.

        ★2단이 실패해도 **1단의 사실은 버리지 않는다.** 소유자·근저당·압류는 유료로 발급한
          등기부에서 뽑은 산출물이고, 산문이 없다고 그것까지 버리면 «전량 실패» 와 같아진다
          (§유료 산출물 규율 2). 대신 `partial=True` 와 사유를 실어 **모름을 유효값으로
          위장하지 않는다**.
        """
        import json

        from app.services.ai.llm_json import parse_llm_json

        addr_line = f"## 대상 부동산\n- 주소: {address}\n" if address else ""

        def _stage_reason(exc: Exception, resp: Any, stage: str) -> str:
            """★각 단의 절단을 **그 단에서** 가른다(`#968` 의 정직성을 새 경로에도 적용).

            이것이 없으면 1단이 잘렸을 때 사유가 *「분할 재시도도 실패 — 파서 오류: char 0」* 이
            되어 **`#968` 이 없애려던 그 표기로 되돌아간다**(§D-20 처방 범위 ≠ 결함 범위).
            """
            from app.services.ai.llm_json import is_truncated as _is_trunc
            base = _failure_reason(exc)
            if _is_trunc(resp):
                return f"분할 {stage}의 응답도 최대 길이에서 잘렸습니다 — 파서 오류: {base}"
            # ★절단이 아니어도 **어느 단에서 죽었는지**는 말한다. 안 말하면 조사자가
            #   1단(사실 추출)과 2단(판단 생성) 중 어디를 보라는 단서를 못 받는다
            #   — 음성 대조군을 쓰다가 발견한 진짜 격차다.
            return f"분할 {stage} 실패 — {base}"

        resp_f = None
        try:
            resp_f, raw_f = await self._invoke(_TMPL_FACTS.format(addr_line=addr_line, registry=registry))
            facts = parse_llm_json(raw_f)
        except Exception as e:  # noqa: BLE001
            # 1단이 실패하면 분할로 얻을 것이 없다 — 호출처의 정직 폴백으로 되돌린다.
            reason = _stage_reason(e, resp_f, "1단(사실)")
            logger.warning("등기 권리분석 분할 1단(사실) 실패",
                           err=f"{type(e).__name__}: {exc_detail(e, limit=100)}", reason=reason)
            self._split_stage_reason = reason  # 호출처가 사유를 그대로 싣는다
            return None

        out: dict[str, Any] = {k: facts[k] for k in _SPLIT_FACT_KEYS if k in facts}
        out["split_call"] = True  # ★분할이 발화했음을 산출물에 남긴다(진단·계측·과금 대조)
        resp_j = None
        try:
            resp_j, raw_j = await self._invoke(_TMPL_JUDGE.format(
                addr_line=addr_line, registry=registry,
                facts=json.dumps(facts, ensure_ascii=False)))
            judge = parse_llm_json(raw_j)
            out.update({k: judge[k] for k in _SPLIT_JUDGE_KEYS if k in judge})
            out["generated"] = True
            return out
        except Exception as e:  # noqa: BLE001
            reason = _stage_reason(e, resp_j, "2단(판단)")
            logger.warning("등기 권리분석 분할 2단(판단) 실패 — 사실만 반환",
                           err=f"{type(e).__name__}: {exc_detail(e, limit=100)}", reason=reason)

        # ══ 2단 실패 = **부분 결과**. 사실은 살리되 «성공» 이라고 말하지 않는다 ══
        #
        # ★★`generated` 는 **성공 계약**이다 — 프론트 `isAnalyzed`(`lib/registry-analyze.ts`)와
        #   서버 `_cache_success` 가 **둘 다 이 한 필드**를 본다. 판단이 없는 건에 `True` 를
        #   실으면 세 가지가 한꺼번에 무너진다(적대 리뷰 실측):
        #     ① `RegistryBatchRow` 가 **「안전성 주의」 배지를 칠한다** — 그 가드의 주석이
        #        *"LLM 폴백도 safety_grade:'주의' 를 담아 오므로 존재 여부로 칠하면 아무것도
        #        판정하지 않은 건이 «안전성 주의»로 보인다"* 고 **라이브 사고 좌표까지 적어
        #        뒀는데**(2026-08-24 오산 내삼미동 448-2·347-8), 이 경로가 그것을 우회했다
        #     ② `failureAction` 이 `unknown` 이 되어 **「해석 다시 시도」 버튼이 사라진다**
        #     ③ `_cache_success` 가 참이라 **DB 에 7일** 재서빙 — 사용자가 복구할 길이 없다
        #   ★그래서 `generated` 를 켜지 않는다. 사실은 payload 에 그대로 남아 상세가 읽을 수
        #     있고, 캐시되지 않으므로 **재시도가 판단을 다시 만든다**(자가치유).
        #
        # ★`safety_grade`·`summary` 를 **기본값으로 채우지 않는다.** 채우면 «모름» 이
        #   «판단 결과» 로 위장되고, 그것은 거부보다 나쁘다.
        out["generated"] = False
        out["partial"] = True
        out["failure_reason"] = (
            "등기부가 길어 분할 분석했으나 권리 판단 생성에 실패했습니다 — "
            f"소유·담보·압류 사실은 유효합니다. 사유: {reason}")
        out["failure_class"] = "parse"
        out["rights_analysis"] = "권리 판단을 생성하지 못했습니다(소유·담보·압류 사실은 유효)."
        return out

    async def _llm(self, address: str | None, registry: str) -> dict[str, Any]:
        raw = ""  # 파싱 실패 시 진단용(except에서 raw_head 로깅) — 잘린 JSON 등 근본추적.
        resp = None  # ★절단 판정(is_truncated)에 필요 — except 에서 참조한다.
        try:
            from app.services.ai.llm_json import parse_llm_json

            addr_line = f"## 대상 부동산\n- 주소: {address}\n" if address else ""
            user = _TMPL.format(addr_line=addr_line, registry=registry)
            # ★max_tokens 4096: 권리분석 JSON(소유권·근저당·압류·기타권리·rights_analysis 산문 등)이
            #   2500토큰을 넘으면 응답이 잘려 json.loads가 실패→'분석 불가' 폴백이 떴다(근본). 헤드룸 확보.
            #   ★그 헤드룸으로도 부족한 등기부가 실재한다(라이브 실측) — 그때는 아래 except 에서
            #     **분할 재시도**한다. 정상 경로는 여기서 끝나므로 **호출 수·과금은 불변**이다.
            resp, raw = await self._invoke(user)
            data = parse_llm_json(raw)  # 공용 관대 파서(프리앰블·후행 설명 허용) — 파서 SSOT
            data["generated"] = True
            return data
        except Exception as e:  # noqa: BLE001
            def _record_fallback(exc: Exception) -> None:
                """★성장루프 **분자**: 이 실패가 집계되지 않아, 등기 권리분석이 통째로 죽어도
                `fallback_rate` 인사이트가 한 번도 뜨지 않았다(2026-08-24 실장애 — 사용자가
                화면을 보고 알려 줄 때까지 아무도 몰랐다). 성공(분모)은 과금 헬퍼가 남긴다.

                ★**분할 시도 뒤에** 부른다. 앞에 두면 분할로 회복된 건까지 분자에 들어간다.
                """
                from app.services.ai.base_interpreter import record_llm_failure
                record_llm_failure("registry", exc)

            # ★진단성: 타입명 + 응답 head를 남겨 '잘린 JSON/비-JSON/LLM오류'를 구분 가능하게.
            logger.warning("등기 권리분석 LLM 실패, 폴백",
                           err=f"{type(e).__name__}: {exc_detail(e, limit=100)}", raw_head=(raw or "")[:180])
            # ★절단은 **파싱 실패가 아니라 응답이 잘린 것**이다 — 사유를 정직하게 바꾼다.
            #   `is_truncated` 의 독스트링이 *"호출처는 이 판정으로 절단을 'parse'가 아닌
            #   별도 사유로 정직하게 분류해야 한다"* 고 **명시**하는데 이 호출처가 안 썼다(참조 0건).
            #   그래서 사용자·조사자에게 `Expecting value: line 1 column 1 (char 0)` 이 보였고,
            #   그것은 **「빈 응답」처럼 읽혀** 엉뚱한 곳을 보게 했다(라이브 실측: 실제는 절단).
            #   ★`failure_class` 는 바꾸지 않는다 — 절단도 **결정론적**이라 `parse` 분류가 옳다
            #     (재시도 판정을 건드리면 이 변경의 범위를 넘는다).
            from app.services.ai.llm_json import is_truncated as _is_truncated
            _reason = _failure_reason(e)
            if _is_truncated(resp):
                # ★A-2b: 절단은 **결정론적**이라 같은 프롬프트로 재시도해도 같은 자리에서
                #   또 잘린다(코드 주석 :161 이 이미 그렇게 적어 뒀다). 그래서 재시도가 아니라
                #   **분할**한다 — 스키마를 둘로 나눠 각 응답의 출력을 캡 아래로 내린다.
                #   실패하면 None 이 와서 아래 정직 폴백으로 그대로 떨어진다.
                self._split_stage_reason = ""
                _split = await self._llm_split(address, registry)
                if _split is not None and _split.get("generated"):
                    # ★분할이 **완전히** 성공했다 — 사용자는 폴백을 보지 않는다.
                    #   그러므로 `record_llm_failure` 를 **발화시키지 않는다**(아래 참조).
                    logger.info("등기 권리분석 절단 → 분할 호출로 회복")
                    return _split
                _stage = getattr(self, "_split_stage_reason", "") or ""
                _reason = (
                    "AI 응답이 최대 길이에서 잘렸습니다(등기부가 깁니다) — 분할 재시도도 "
                    f"실패했습니다. {_stage or ('파서 오류: ' + _reason)}"
                )
                if _split is not None:
                    # 부분 결과(사실만) — 사유를 이 자리의 절단 맥락으로 덮어쓴다.
                    _split["failure_reason"] = _split.get("failure_reason") or _reason
                    _record_fallback(e)
                    return _split
            # ★성장루프 **분자**는 «사용자가 폴백을 봤다» 를 뜻해야 한다. 그래서 분할 시도
            #   **뒤에** 기록한다 — 앞에 두면 분할로 회복된 건까지 분자에 들어가 `fallback_rate`
            #   가 조용히 다른 뜻이 된다(적대 리뷰 지적 M-4).
            _record_fallback(e)
            return {
                "generated": False,
                "ownership": {}, "provisional_registration": {"exists": None},
                "seizure": [], "mortgage": [], "other_rights": [],
                "right_to_demand_sale": {"possible": "판단보류", "reason": "등기 내용 확인 필요"},
                # ★"일시적"이라고 단정하지 않는다 — 그 표기가 결정론적 영구 실패를
                #   일시 장애로 위장해 오래 숨긴 전례가 있다(2026-08-21 LLM 계층 사망).
                "rights_analysis": "AI 권리분석을 생성하지 못했습니다. 등기부 내용을 직접 확인하세요.",
                "failure_reason": _reason,
                # ★분류는 **실제 예외가 있는 이 자리**에서 한다. 나중에 문자열만 보고 다시
                #   분류하면 타입이 지워져(`Exception("JSONDecodeError: …")`) 메시지에
                #   타입명이 우연히 들어 있어야만 맞는다 — 운에 기대는 판정이 된다.
                "failure_class": _classify_failure(e),
                "risks": [], "safety_grade": "주의", "summary": "분석 불가",
            }
