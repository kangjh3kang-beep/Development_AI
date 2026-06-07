"""대법원 법원경매정보(www.courtauction.go.kr) 실연동 클라이언트 — 무목업.

★2026-06-07 재구현(접근법 A: JSON API). 신 courtauction.go.kr(NELS, 2023 WebSquare SPA)는
물건검색을 ★JSON POST 엔드포인트로 제공한다. 라이브 조사로 다음을 확정했다:

  - 엔드포인트: POST /pgj/pgjsearch/searchControllerMain.on
  - 요청 본문(JSON): {"dma_pageInfo": {...}, "dma_srchGdsDtlSrchInfo": {...srchInfo...}}
  - 응답(JSON): data.dma_pageInfo.totalCnt(총건수) + data.dlt_srchResult[](물건 목록).
  - ★IP 보안정책: 세션쿠키(/pgj/index.on 선방문) + WebSquare 류 헤더
    (X-Requested-With/SubmissionID/Origin/Accept)가 모두 있어야 통과한다.
    누락 시 {"data":{"ipcheck":false}, "message":"...보안정책에 의하여 차단..."}.
  - 라이브 검증: 부동산 전국조회 totalCnt=29,032, 실물건(사건번호 2021타경105850,
    감정가 12,887,000,000원, 최저가 4,222,812,000원, 유찰5회 등) 반환 확인.

기존 BeautifulSoup HTML 추측 파서(미검증)를 제거하고, requests(미설치) 대신 ★httpx
(이미 의존성)로 재구현했다 → bs4/lxml 추가 불필요, 의존성 변경 0.

★예의·rate-limit(서버부하·IP차단 방지):
  - 요청 간 지연(delay_sec ± jitter), 순차(동시성 없음), 페이지 수 제한.
  - 적절한 User-Agent, graceful 중단. 과도 호출 시 서버가 일시 차단(잠시후 재시도) 가능.

★정직(무목업):
  - 못 가져오면 가짜데이터 없이 빈 결과 + data_source="unavailable" + reason.
  - 성공 시 data_source="court_scrape".
  - ipcheck=false(보안차단)·무자료·HTTP 오류는 모두 reason으로 정직 노출한다.

auction_service._fetch_court()가 asyncio.to_thread로 동기 호출하므로 fetch_items는
동기 httpx.Client 기반으로 유지한다(서비스 레이어 변경 최소화).
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 신 courtauction.go.kr(NELS) JSON 검색 엔드포인트(라이브 확정) ──
COURT_BASE_URL = "https://www.courtauction.go.kr"
COURT_INDEX_PATH = "/pgj/index.on"  # 세션쿠키(JSESSIONID/WMONID) 선취득용.
COURT_SEARCH_PATH = "/pgj/pgjsearch/searchControllerMain.on"  # 물건검색 컨트롤러.

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# 검색 구분코드(라이브 확정): 부동산=0004601, 동산=0004604.
SRCH_COND_REAL_ESTATE = "0004601"
# 부동산/동산 구분코드(라이브 확정): 부동산=00031R.
MVPRP_RLET_REAL_ESTATE = "00031R"

# 시/도 키워드 → 행정구역 2자리 코드(rprsAdongSdCd, 라이브 결과의 daepyoSidoCd와 일치).
SIDO_CODE_MAP: dict[str, str] = {
    "서울": "11", "부산": "26", "대구": "27", "인천": "28", "광주": "29",
    "대전": "30", "울산": "31", "세종": "36", "경기": "41", "강원": "42",
    "충북": "43", "충남": "44", "전북": "45", "전남": "46", "경북": "47",
    "경남": "48", "제주": "50",
}

# 법원경매 용도명(dspslUsgNm) → 내부 kind 코드.
KIND_MAP: dict[str, str] = {
    "아파트": "apt",
    "오피스텔": "officetel",
    "토지": "land",
    "대지": "land",
    "임야": "land",
    "전": "land",
    "답": "land",
    "다세대": "building",
    "다가구": "building",
    "주택": "building",
    "연립": "building",
    "근린": "building",
    "상가": "building",
    "건물": "building",
    "공장": "factory",
}

# 물건상태코드(mulStatcd) → 내부 status(진행중=01 위주).
_STATUS_MAP = {"01": "open", "02": "open", "03": "closed", "04": "closed"}


def normalize_kind(raw: Any) -> str:
    s = str(raw or "").strip()
    for key, code in KIND_MAP.items():
        if key in s:
            return code
    return "etc"


def sido_to_code(region: Any) -> Optional[str]:
    """시/도 키워드(서울/서울특별시/경기 등)를 rprsAdongSdCd 2자리 코드로 변환."""
    s = str(region or "").strip()
    if not s:
        return None
    if s.isdigit() and len(s) == 2:
        return s
    for key, code in SIDO_CODE_MAP.items():
        if s.startswith(key):
            return code
    return None


def _safe_int(raw: Any) -> Optional[int]:
    """금액/횟수 문자열을 정수로(원 단위). 0/빈값/'비공개'는 None(가짜 금지)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        v = int(raw)
        return v if v != 0 else None
    s = str(raw).strip()
    if not s or "비공개" in s or "미정" in s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None
    v = int(digits)
    return v if v != 0 else None


def _clean(s: Any) -> str:
    return " ".join(str(s or "").split())


def _normalize_court_date(raw: Any) -> Optional[str]:
    """yyyyMMdd(매각기일) → ISO8601 날짜. 빈값/형식불일치 시 None."""
    from datetime import datetime

    s = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(s) != 8:
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def parse_search_result(payload: dict[str, Any]) -> dict[str, Any]:
    """searchControllerMain.on JSON 응답을 내부 auction_items 스키마로 정규화한다.

    반환: {"items": [...], "total": int, "blocked": bool, "reason": str|None}.
    ipcheck=false(보안차단)·무자료는 가짜 없이 빈 items + reason 으로 정직 반환한다.
    네트워크와 분리되어 단위 테스트가 가능하다(픽스처 입력).
    """
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        msg = str((payload or {}).get("message") or "").strip()
        return {"items": [], "total": 0, "blocked": False,
                "reason": msg or "법원경매 응답 형식 오류"}

    # ★보안정책 차단(ipcheck=false): 정직하게 차단 사유 노출.
    if data.get("ipcheck") is False:
        return {"items": [], "total": 0, "blocked": True,
                "reason": str(payload.get("message") or "법원경매 보안정책 차단(ipcheck)")}

    page_info = data.get("dma_pageInfo") or {}
    total = _safe_int(page_info.get("totalCnt")) or 0
    rows = data.get("dlt_srchResult") or []
    if not isinstance(rows, list):
        return {"items": [], "total": total, "blocked": False, "reason": None}

    items: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        items.append(_normalize_row(r))
    return {"items": items, "total": total, "blocked": False, "reason": None}


def _normalize_row(r: dict[str, Any]) -> dict[str, Any]:
    """dlt_srchResult 한 행을 내부 auction_items 스키마로 정규화한다(라이브 필드)."""
    # 안정 item_no: docid(물건 고유) 우선, 없으면 사건번호+물건순번 조합.
    docid = _clean(r.get("docid"))
    case_no = _clean(r.get("srnSaNo"))  # 예: 2021타경105850.
    maemul_ser = _clean(r.get("maemulSer"))
    item_no = docid or (f"{case_no}-{maemul_ser}" if case_no else "")

    # 소재지: printSt(렌더용 정제 주소) 우선, 보조로 convAddr.
    address = _clean(r.get("printSt")) or _clean(r.get("convAddr"))
    usage = _clean(r.get("dspslUsgNm"))

    sido = _clean(r.get("hjguSido") or r.get("rd1Nm"))
    sigungu = _clean(r.get("hjguSigu") or r.get("rd2Nm"))

    status_code = _clean(r.get("mulStatcd"))
    status = _STATUS_MAP.get(status_code, "open")

    raw = dict(r)
    raw["_source"] = "court_scrape"
    return {
        "source": "court",
        "item_no": item_no,
        "kind": normalize_kind(usage),
        "kind_name": usage or None,
        "region_sido": sido,
        "region_sigungu": sigungu,
        "bjd_code": _clean(r.get("srchHjguDongCd")),
        "pnu": "",
        "address": address,
        "appraisal_price": _safe_int(r.get("gamevalAmt")),
        "min_bid_price": _safe_int(r.get("minmaePrice")),
        "fail_count": _safe_int(r.get("yuchalCnt")) or 0,
        "status": status,
        "bid_start": None,
        "bid_end": _normalize_court_date(r.get("maeGiil")),  # 매각기일.
        "court_name": _clean(r.get("jiwonNm")),
        "case_no": case_no or None,
        "raw": raw,
    }


# ──────────────────────────────────────────
# 네트워크 수집(지연·예의 — 실호출은 운영/cron에서만)
# ──────────────────────────────────────────


class CourtAuctionScraper:
    """법원경매 JSON 실연동(순차 + 지연). 실패/차단 시 graceful 빈 결과(무목업)."""

    def __init__(
        self,
        *,
        delay_sec: float = 1.5,
        delay_jitter: float = 0.8,
        timeout: float = 20.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_pages: int = 3,
    ):
        self.delay_sec = max(0.0, delay_sec)
        self.delay_jitter = max(0.0, delay_jitter)
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_pages = max(1, max_pages)

    def _sleep(self) -> None:
        """다음 요청 전 지연(서버부하·차단 방지). jitter로 패턴화 완화."""
        delay = self.delay_sec + random.uniform(0.0, self.delay_jitter)
        if delay > 0:
            time.sleep(delay)

    def _build_payload(
        self, *, region: Optional[str], page: int, page_size: int,
    ) -> dict[str, Any]:
        """searchControllerMain.on 요청 본문(부동산 전국/지역 조회)을 구성한다."""
        srch: dict[str, Any] = {
            "menuNm": "물건상세검색",
            "lafjOrderBy": "",
            "pgmId": "PGJ151F01",
            "mvprpRletDvsCd": MVPRP_RLET_REAL_ESTATE,
            "cortAuctnSrchCondCd": SRCH_COND_REAL_ESTATE,
            "statNum": 1,
        }
        sido_code = sido_to_code(region)
        if sido_code:
            srch["rprsAdongSdCd"] = sido_code
        return {
            "dma_pageInfo": {
                "pageNo": page,
                "pageSize": page_size,
                "totalYn": "Y",
            },
            "dma_srchGdsDtlSrchInfo": srch,
        }

    def _request(self, client, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        """검색 컨트롤러에 POST(JSON). 실패/비-JSON 시 None(가짜 생성 금지)."""
        try:
            resp = client.post(
                f"{COURT_BASE_URL}{COURT_SEARCH_PATH}",
                json=payload,
                headers={
                    # ★IP 보안정책 통과에 필요한 WebSquare 류 헤더(라이브 확정).
                    "Content-Type": "application/json;charset=UTF-8",
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "SubmissionID": "sbm_selectGdsDtlSrch",
                    "Origin": COURT_BASE_URL,
                    "Referer": f"{COURT_BASE_URL}{COURT_INDEX_PATH}",
                },
            )
            if resp.status_code != 200:
                logger.warning("법원경매 응답 %s — 중단", resp.status_code)
                return None
            return resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("법원경매 요청 실패(무목업, 빈 결과): %s", str(e)[:160])
            return None

    def fetch_items(
        self,
        *,
        region: Optional[str] = None,
        kind: Optional[str] = None,
        max_pages: Optional[int] = None,
        page_size: int = 40,
    ) -> dict[str, Any]:
        """법원경매 물건을 JSON API로 소량·지연 수집한다(순차).

        반환: {"items": [...], "data_source": "court_scrape"|"unavailable",
               "total": int, "note"|"reason": str}
        httpx 미설치/보안차단(ipcheck)/HTTP오류/무자료 시 가짜 없이 빈 결과 + reason.
        """
        try:
            import httpx
        except Exception:  # noqa: BLE001
            return self._unavailable("httpx 미설치 — 법원경매 수집 불가")

        pages = min(self.max_pages, max_pages or self.max_pages)
        items: list[dict[str, Any]] = []
        total = 0
        last_reason: Optional[str] = None
        blocked = False

        try:
            with httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            ) as client:
                # ★세션쿠키(JSESSIONID/WMONID) 선취득 — 보안정책 통과 전제.
                try:
                    client.get(f"{COURT_BASE_URL}{COURT_INDEX_PATH}")
                except Exception as e:  # noqa: BLE001
                    return self._unavailable(f"법원경매 세션 취득 실패: {str(e)[:120]}")
                self._sleep()

                for page in range(1, pages + 1):
                    payload = self._build_payload(
                        region=region, page=page, page_size=page_size,
                    )
                    body = self._request(client, payload)
                    if body is None:
                        last_reason = "법원경매 HTTP 오류 또는 비-JSON 응답"
                        break
                    parsed = parse_search_result(body)
                    if parsed["blocked"]:
                        blocked = True
                        last_reason = parsed["reason"]
                        break
                    total = parsed["total"] or total
                    page_items = parsed["items"]
                    if not page_items:
                        last_reason = parsed.get("reason") or "법원경매 무자료"
                        break
                    if kind:
                        page_items = [it for it in page_items if it.get("kind") == kind]
                    items.extend(page_items)
                    if len(items) >= total > 0:
                        break  # 더 가져올 게 없음.
                    self._sleep()  # ★다음 페이지 전 지연(예의).
        except Exception as e:  # noqa: BLE001
            logger.warning("법원경매 수집 실패(무목업): %s", str(e)[:160])
            return self._unavailable(f"법원경매 수집 실패: {str(e)[:120]}")

        if not items:
            if blocked:
                return self._unavailable(
                    "법원경매 보안정책 차단(ipcheck) — 잠시 후 재시도 필요"
                    + (f": {last_reason}" if last_reason else "")
                )
            return self._unavailable(
                last_reason or "법원경매 무자료(해당 조건의 물건 없음)"
            )
        return {
            "items": items,
            "data_source": "court_scrape",
            "total": len(items),
            "total_available": total,
            "note": (
                "대법원 법원경매정보 JSON API(searchControllerMain.on) 실연동"
                f" — 전국 {total}건 중 {len(items)}건 수집(지연·예의 적용)"
            ),
        }

    @staticmethod
    def _unavailable(reason: str) -> dict[str, Any]:
        return {"items": [], "data_source": "unavailable", "total": 0, "reason": reason}
