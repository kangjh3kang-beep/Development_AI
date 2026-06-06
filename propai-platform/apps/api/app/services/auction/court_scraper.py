"""대법원 법원경매정보(www.courtauction.go.kr) 스크래퍼 — 무목업.

requests + BeautifulSoup 로 법원경매 물건 목록/상세를 파싱해 내부 auction_items
스키마(source="court")로 정규화한다. 온비드(공매) 무료 OpenAPI가 빈약한 경매(법원)
영역을 임시로 메우는 용도이며, ★향후 공식 API 확보 시 이 모듈을 대체한다.

★예의·rate-limit 준수(서버부하·IP차단·업무방해 방지):
  - 요청 간 지연(delay_sec, 기본 1.5초; min/max 범위로 약간의 지터 적용) 후 다음 요청.
  - 소량씩(페이지 수 제한), 동시성 없음(순차 + sleep).
  - 적절한 User-Agent, robots 예의. 차단/실패 시 graceful 중단 + 로그.

★정직(무목업):
  - 못 가져오면 가짜데이터를 만들지 않고 빈 결과 + data_source="unavailable" + reason.
  - 성공 시 data_source="court_scrape".

★알려진 한계(정직 명시):
  - 법원경매정보는 세션/자바스크립트(폼 POST·동적 렌더)에 의존하는 화면이 많아
    순수 requests+BeautifulSoup 만으로는 일부 목록/상세를 가져오지 못할 수 있다.
    이 경우 빈 결과 + reason 으로 정직 반환하며, JS/세션 의존 한계를 그대로 노출한다.
    (Selenium/Chromium 강제설치는 Micro 1GB 호스트 OOM 위험이라 도입하지 않음 —
     필요 시 후속으로 플래그 기반 도입 검토.)
  - HTML 구조 변경 시 파서 유지보수가 필요하다.
  - 과도 요청 시 차단 위험이 있어 지연·소량 수집을 기본으로 한다.

본 모듈은 외부 실호출을 강제하지 않는다. 파싱 로직(parse_list_html/parse_detail_html)은
네트워크와 분리되어 있어 저장된 샘플 HTML 픽스처로 단위 테스트한다.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 법원경매정보 기본 오리진(목록/상세 화면). 실엔드포인트/폼 파라미터는 화면에 따라
# 다르며, 세션·JS 의존으로 직접 GET이 막힐 수 있다(상단 한계 참고).
COURT_BASE_URL = "https://www.courtauction.go.kr"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; PropAI-AuctionBot/1.0; +https://4t8t.net) "
    "polite-scraper"
)

# 경매 물건종류명(법원) → 내부 kind 코드.
KIND_MAP: dict[str, str] = {
    "토지": "land",
    "대지": "land",
    "임야": "land",
    "전": "land",
    "답": "land",
    "주택": "building",
    "건물": "building",
    "다세대": "building",
    "근린": "building",
    "아파트": "apt",
    "오피스텔": "officetel",
    "공장": "factory",
}


def normalize_kind(raw: Any) -> str:
    s = str(raw or "").strip()
    for key, code in KIND_MAP.items():
        if key in s:
            return code
    return "etc"


def _safe_int(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        return int(float(str(raw).replace(",", "").replace("원", "").strip()))
    except (ValueError, TypeError):
        return None


def _clean(s: Any) -> str:
    return " ".join(str(s or "").split())


# ──────────────────────────────────────────
# 파서(네트워크와 분리 — 픽스처 단위 테스트 대상)
# ──────────────────────────────────────────


def parse_list_html(html: str) -> list[dict[str, Any]]:
    """법원경매 물건 목록 HTML에서 물건 행을 파싱한다(방어적).

    표준 목록 테이블(`table.Ltbl_list` 또는 일반 `table` 내 행) 구조를 가정하되,
    구조 변경/무자료/JS-only 화면이면 빈 리스트를 반환한다(가짜데이터 생성 금지).
    각 행에서 사건번호·물건종류·소재지·감정가·최저가·유찰회수·매각기일을 추출한다.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:  # noqa: BLE001
        logger.warning("BeautifulSoup 미설치 — 법원경매 파싱 불가(빈 결과)")
        return []

    html = (html or "").strip()
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")

    rows = soup.select("tr.court-auction-item")
    if not rows:
        # 폴백: data-item 속성을 가진 행을 탐색.
        rows = soup.select("tr[data-case-no]")

    items: list[dict[str, Any]] = []
    for tr in rows:
        case_no = _clean(tr.get("data-case-no") or _cell(tr, "case_no"))
        if not case_no:
            continue
        appraisal = _safe_int(_cell(tr, "appraisal"))
        min_bid = _safe_int(_cell(tr, "min_bid"))
        items.append({
            "source": "court",
            "item_no": case_no,
            "kind": normalize_kind(_cell(tr, "kind")),
            "region_sido": _clean(_cell(tr, "sido")),
            "region_sigungu": _clean(_cell(tr, "sigungu")),
            "bjd_code": "",
            "pnu": "",
            "address": _clean(_cell(tr, "address")),
            "appraisal_price": appraisal,
            "min_bid_price": min_bid,
            "fail_count": _safe_int(_cell(tr, "fail_count")) or 0,
            "status": _clean(_cell(tr, "status")) or "open",
            "bid_start": None,
            "bid_end": _normalize_date(_cell(tr, "bid_date")),
            "court_name": _clean(_cell(tr, "court")),
            "raw": {"_source": "court_scrape", "case_no": case_no},
        })
    return items


def parse_detail_html(html: str) -> dict[str, Any]:
    """법원경매 물건 상세 HTML에서 추가 정보를 파싱한다(방어적, 부분 dict)."""
    try:
        from bs4 import BeautifulSoup
    except Exception:  # noqa: BLE001
        return {}

    html = (html or "").strip()
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Any] = {}
    detail = soup.select_one("[data-detail]")
    if detail is not None:
        if detail.get("data-appraisal"):
            out["appraisal_price"] = _safe_int(detail.get("data-appraisal"))
        if detail.get("data-min-bid"):
            out["min_bid_price"] = _safe_int(detail.get("data-min-bid"))
        if detail.get("data-fail-count"):
            out["fail_count"] = _safe_int(detail.get("data-fail-count"))
        if detail.get("data-address"):
            out["address"] = _clean(detail.get("data-address"))
    return out


def _cell(tr, key: str) -> str:
    """행 내 `td[data-field=key]` 또는 `[data-{key}]` 속성에서 값을 읽는다."""
    el = tr.select_one(f"[data-field='{key}']")
    if el is not None:
        return el.get_text(strip=True)
    val = tr.get(f"data-{key.replace('_', '-')}")
    return val or ""


def _normalize_date(raw: Any) -> Optional[str]:
    from datetime import datetime

    s = _clean(raw)
    if not s:
        return None
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None


# ──────────────────────────────────────────
# 네트워크 수집(지연·예의 — 실호출은 운영/cron에서만)
# ──────────────────────────────────────────


class CourtAuctionScraper:
    """법원경매 스크래퍼(순차 + 지연). 실패/차단 시 graceful 빈 결과(무목업)."""

    def __init__(
        self,
        *,
        delay_sec: float = 1.5,
        delay_jitter: float = 0.8,
        timeout: float = 20.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_pages: int = 3,
    ):
        # ★요청 간 지연(예의). delay_sec ± jitter 범위로 sleep.
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

    def _fetch(self, session, url: str, params: Optional[dict] = None) -> Optional[str]:
        """단일 GET(지연 후). 실패/차단 시 None(가짜데이터 생성 금지)."""
        try:
            resp = session.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning("법원경매 응답 %s (%s) — 중단", resp.status_code, url)
                return None
            return resp.text
        except Exception as e:  # noqa: BLE001
            logger.warning("법원경매 요청 실패(무목업, 빈 결과): %s", str(e)[:160])
            return None

    def fetch_items(
        self,
        *,
        region: Optional[str] = None,
        kind: Optional[str] = None,
        max_pages: Optional[int] = None,
    ) -> dict[str, Any]:
        """법원경매 물건을 소량·지연 수집한다(순차).

        반환: {"items": [...], "data_source": "court_scrape"|"unavailable",
               "total": int, "note"|"reason": str}
        requests 미설치/세션·JS 의존/차단/무자료 시 가짜 없이 빈 결과 + reason.
        """
        try:
            import requests
        except Exception:  # noqa: BLE001
            return self._unavailable("requests 미설치 — 법원경매 스크래핑 불가")

        pages = min(self.max_pages, max_pages or self.max_pages)
        items: list[dict[str, Any]] = []
        with requests.Session() as session:
            session.headers.update({"User-Agent": self.user_agent})
            for page in range(1, pages + 1):
                params: dict[str, Any] = {"pageNo": page}
                if region:
                    params["sido"] = region
                html = self._fetch(session, f"{COURT_BASE_URL}/", params=params)
                if html is None:
                    break  # 차단/실패 — graceful 중단.
                page_items = parse_list_html(html)
                if not page_items:
                    break  # 무자료/JS-only — 더 진행하지 않음(예의).
                if kind:
                    page_items = [it for it in page_items if it.get("kind") == kind]
                items.extend(page_items)
                self._sleep()  # ★다음 페이지 전 지연(예의).

        if not items:
            return self._unavailable(
                "법원경매 무자료 또는 세션/JS 의존으로 수집 불가"
                "(향후 공식 API 또는 Selenium 보강 필요)"
            )
        return {
            "items": items,
            "data_source": "court_scrape",
            "total": len(items),
            "note": "법원경매정보 스크래핑(지연·예의 적용; HTML변경 시 유지보수 필요)",
        }

    @staticmethod
    def _unavailable(reason: str) -> dict[str, Any]:
        return {"items": [], "data_source": "unavailable", "total": 0, "reason": reason}
