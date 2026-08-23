"""고시 **결손 탐지** — 우리 데이터가 모르는 최근 지구단위계획 결정고시를 찾아낸다.

【무엇을 푸는가 — 실제 사고】
오산 내삼미동: 고시 제2025-274호(2025-12-23)로 **지구단위계획구역이 신규 결정**됐는데
그 고시가 VWorld `LT_C_UPISUQ161` 에 없다. 그래서 플랫폼은 자연녹지 법정 80%를
**지배 한도인 양** 답했다. 화면은 "지구단위계획 없음"을 *사실*처럼 보여 준다.

【★왜 '신선도 날짜'가 아니라 '결손 대조'인가 — 2026-08-21 반증 기록】
처음엔 레이어의 `ntfc_sn` 에서 최신 고시일을 뽑아 화면에 **유효시각(as-of)** 으로 박으려 했다.
알려진 이 사고에 대입하니 **안심시키는 방향으로 실패**했다:

    그 필지 BOX 의 max(고시일) = 2026-06-24  ← "약 2개월 전 · 최신" 으로 표시됐을 값
    오산 자체 max = 2025-07-30 · 2025-12-23 이후 피처 = 0건

`max(고시일)` 이 보증하는 건 *"최소한 그 날 이후 한 번은 적재됨"* = **하한**인데,
"낡았는가"는 *"이후 누락이 없는가"* = **상한** 질문이다 — **재려는 것의 반대쪽을 잰다.**
그래서 날짜를 **합성해 단정하지 않고**, 권위 있는 원본(토지이음)의 고시를 우리 데이터에서
**찾아보는 방식**으로 바꿨다. 못 찾으면 그 **고시를 지목**한다(행동 가능).
상세: 볼트 `decisions/2026-08-21_P3신선도_ntfc_sn_지표_반증과_canary설계`.

【★무엇을 주장하고 무엇을 주장하지 않는가】
- 주장한다: *"이 고시가 우리 데이터에서 **확인되지 않는다**"* — 원문 링크와 함께.
- 주장하지 않는다: *"데이터가 틀렸다"* · *"이 필지가 지구단위계획구역이다"*.
  대조는 **고시일 기준 휴리스틱**이라 100%가 아니다(아래 실측 참조). 그래서 결과는
  **확인 요청**이지 판정이 아니다.

【실측 정밀도(오산 2015~2026 · 토지이음 고유 846건 전건 페이징)】
필터를 좁힐수록 VWorld 반영률이 단조 상승한다 — 이 계층이 필터 선택의 근거다:

    전체                       543일 중 25 적중  ( 4.6%)
    '지구단위계획'                69일 중 15      (21.7%)
    '지구단위계획구역'              33일 중 13      (39.4%)
    [신규]+구역                  15일 중  8      (53.3%)
    ★[신규]+구역+경미제외          14일 중  8      (57.1%)  ← 채택

채택 부류에서 **2018-11 ~ 2024-02 신규 구역 지정 8건이 연속 적중**하고,
가장 최근인 **2025-12-23 만 빠진다**. 그리고 2019-03-14 `지구단위계획구역 실효고시`가
빠져 있는 것은 **구역이 사라진 것이라 없는 게 맞다**(규칙이 잡음이 아니라는 방증).
"""
from __future__ import annotations

import html
import re
from datetime import date as _date
from datetime import timedelta as _timedelta
from typing import Any
from urllib.parse import quote as _quote

import httpx
import structlog

logger = structlog.get_logger(__name__)

EUM_LIST_URL = "https://www.eum.go.kr/web/gs/gv/gvGosiList.jsp"
# ※변이 생존(설명 가능): UA 는 **라이브에서만** 의미가 있다(정부 사이트가 기본 UA 를 거를 수
#   있다). MockTransport 로는 잠글 수 없고, 잠근다면 그건 목을 검사하는 것이지 동작이 아니다.
_UA = {"User-Agent": "Mozilla/5.0 (compatible; PropAI/1.0; +https://4t8t.net)"}

# 한 페이지 50건.
# ★상한을 6으로 뒀더니 **화성시가 통째로 침묵**했다(2.5년 창 300건 = 상한 도달 → 전건확보 실패
#   → 설계대로 아무것도 단정하지 않음). 안전측으로 실패하지만 **탐지가 0이 된다**.
#   바쁜 시군구도 최근 창을 전건 확보하도록 12로 올린다(실측: 화성 ≈120건/년).
#   그래도 도달하면 **침묵**한다 — 절단된 목록으로 "결손 없음"을 말하지 않는다.
_PAGE_SIZE = 50
_MAX_PAGES = 12

# 기본 조회 창 — "최근"의 범위. 너무 좁히면 결손을 놓치고, 너무 넓히면 상한에 걸려 침묵한다.
DEFAULT_WINDOW_MONTHS = 24

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TD_RE = re.compile(
    r"<td[^>]*?(?:\stitle=\"(?P<title>[^\"]*)\")?[^>]*>(?P<body>.*?)</td>", re.S
)
_DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")
# `ntfc_sn` 안의 YYYYMMDD. ★이 값을 '고시일'이라 부르지 않는다 — VWorld 공식 속성표에
#   날짜 필드는 없고(결정고시**관리코드**), 8자리를 날짜로 읽는 것은 우리 역공학이다.
#   여기서는 **대조 키**로만 쓴다(같은 날짜가 있으면 '확인됨'으로 본다).
NTFC_DATE_RE = re.compile(r"(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])")


# 토지이음이 **빈 결과에 내는 명시적 신호**(라이브 실측 2026-08-23):
#   <tr><td colspan="4">조회된 데이터가 없습니다.</td></tr>
# ★이 신호가 파서 파손과 진짜 0건을 가른다. 종전엔 `파싱 0건 → complete=True` 라
#   **HTML 구조가 바뀌어도 "전건 확보"** 로 판정돼, 결손 탐지가 조용히 0이 됐다.
_EMPTY_STATE_RE = re.compile(r"조회된\s*데이터가\s*없습니다")

#: 파서 건강 관측의 **구별된** event_type.
#  ★F4a: severity·recommended_action 을 담지 않는다(자동 변이 루프가 조치신호로 읽는다).
GOSI_PARSER_OBSERVATION_EVENT = "gosi_parser_observation"


def looks_like_empty_result(page_html: str) -> bool:
    """항목 0건이 **진짜 0건**인지(파서 파손이 아닌지) 판별한다.

    ★위양성 방향이 안전하다: 문구가 바뀌면 `complete=False`(침묵)가 되지
      "결손 없음"(거짓 안심)이 되지 않는다 — 이 서비스의 설계 철학과 같은 방향이다.
    """
    return bool(_EMPTY_STATE_RE.search(page_html or ""))


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(fragment))).strip()


def parse_gosi_rows(page_html: str) -> list[dict[str, str]]:
    """토지이음 고시목록 표를 (고시일·고시번호·제목·담당기관) 으로 뜯는다.

    ★고시번호·제목은 `<td title="...">`/`<a title="...">` 속성에 **전체 문자열**이 들어 있고
      본문 텍스트는 `[신규]` 접두·주석이 섞인다. 속성을 우선 쓰되 없으면 본문으로 폴백한다.
    """
    out: list[dict[str, str]] = []
    for tr in _ROW_RE.findall(page_html or ""):
        cells = [(m.group("title"), _text(m.group("body"))) for m in _TD_RE.finditer(tr)]
        if len(cells) < 4:
            continue
        date = cells[0][1]
        if not _DATE_RE.fullmatch(date):
            continue
        seq_m = re.search(r"gvGosiDet\.jsp\?seq=(\d+)", tr)
        out.append({
            # ★상세(첨부 PDF)로 가려면 seq 가 필요하다 — 목록에서만 얻을 수 있다.
            "seq": seq_m.group(1) if seq_m else "",
            "date": date,
            "gosino": (cells[1][0] or cells[1][1] or "").strip(),
            # 제목 본문은 `[신규]`/`[변경]` 구분 접두를 갖고 있어 **본문을 우선**한다
            # (title 속성엔 그 접두가 없다 — 아래 신규 판정에 필요하다).
            "title": (cells[2][1] or cells[2][0] or "").strip(),
            "org": (cells[3][0] or cells[3][1] or "").strip(),
        })
    return out


def is_new_district_designation(title: str) -> bool:
    """이 고시가 **지구단위계획구역을 새로 지정**하는가 = 피처가 반드시 생겨야 하는 부류.

    ★`실효`(구역 해제)는 제외한다 — 실효되면 피처가 **없는 것이 맞다**.
      실측(오산 2019-03-14 `지구단위계획구역 실효고시`)에서 정확히 빠져 있었고,
      이를 결손으로 신고했다면 **위양성**이었다.
    ★`경미한 변경`도 제외한다 — 결정고시관리코드를 갱신하지 않을 수 있다.
    """
    t = title or ""
    if not t.startswith("[신규]"):
        return False
    if "지구단위계획구역" not in t:
        return False
    return "경미" not in t and "실효" not in t


async def fetch_recent_gosi(
    sigungu_code: str, start_yyyymmdd: str, end_yyyymmdd: str,
    *, client: httpx.AsyncClient | None = None,
) -> tuple[list[dict[str, str]], bool]:
    """토지이음 고시목록 — 기간 내 **전건**(페이징). 반환: (행, 전건확보여부).

    ★전건 확보 여부를 함께 낸다. 절단된 목록으로 "결손 없음"을 말하면 **거짓 안심**이 된다
      (같은 함정을 두 번 밟았다: VWorld `size` 상한, 그리고 이 목록의 `listSize`).
    """
    rows: list[dict[str, str]] = []
    owns = client is None
    c = client or httpx.AsyncClient(timeout=20.0, headers=_UA, follow_redirects=True)
    complete = False
    try:
        for page in range(1, _MAX_PAGES + 1):
            resp = await c.get(EUM_LIST_URL, params={
                "selSggCd": sigungu_code, "startdt": start_yyyymmdd,
                "enddt": end_yyyymmdd, "listSize": str(_PAGE_SIZE), "pageNo": str(page),
            })
            resp.raise_for_status()
            page_html = resp.content.decode("euc-kr", "replace")
            got = parse_gosi_rows(page_html)
            if not got:
                # ★0건이 '진짜 없음'인지 '파서 파손'인지 가른다.
                #   ①이미 읽은 행이 있으면 **파서는 작동한 증거**다 — 페이징 끝일 뿐이다.
                #     (기존 회귀망이 이 위양성을 잡아 줬다: 1p 50건 → 2p 빈 페이지 시나리오)
                #   ②첫 페이지부터 0건인데 빈 상태 신호도 없으면 **HTML 구조가 바뀐 것**으로 본다.
                #     그대로 complete=True 로 두면 결손 탐지가 조용히 0이 된다(거짓 안심).
                if not rows and not looks_like_empty_result(page_html):
                    logger.warning(
                        "토지이음 목록 파싱 0건인데 빈 상태 신호가 없다 — 파서 파손 의심: "
                        "sgg=%s page=%s len=%s", sigungu_code, page, len(page_html),
                    )
                    _record_parser_observation(sigungu_code, broken=True, page_len=len(page_html))
                    return rows, False
                complete = True
                break
            rows.extend(got)
            if len(got) < _PAGE_SIZE:
                complete = True
                break
    except Exception as e:  # noqa: BLE001 — 외부 사이트. 실패는 **침묵하지 않고** 표기한다.
        logger.warning("토지이음 고시목록 조회 실패: sgg=%s (%s)", sigungu_code, e)
        return rows, False
    finally:
        # ※변이 생존(설명 가능): 호출부가 준 클라이언트를 닫으면 안 된다는 소유권 규약이다.
        #   자원 위생이라 관측 가능한 동작 차이가 없다(닫아도 테스트는 통과한다).
        if owns:
            await c.aclose()
    _record_parser_observation(sigungu_code, broken=False, row_count=len(rows))
    return rows, complete


def _record_parser_observation(
    sigungu_code: str, *, broken: bool, row_count: int = 0, page_len: int = 0,
) -> None:
    """파서 건강을 **영속** 관측한다(platform_events).

    ★structlog 만으로는 빈도를 잴 수 없다 — docker logs 는 배포마다 사라진다
      (2026-08-23 실측: 계측을 넣은 다음 날 읽으니 25분치 1건이었다).
    ★성공 경로도 남긴다 — 그래야 **분모**를 알고 "언제부터 깨졌나"를 잴 수 있다.
    """
    try:
        from app.services.growth import capture_service

        capture_service.record_event(GOSI_PARSER_OBSERVATION_EVENT, {
            "surface": "api",
            "service": "gosi_coverage",
            "payload": {
                "broken": broken,
                "sigungu_code": sigungu_code,
                "row_count": row_count,
                "page_len": page_len,
            },
        })
    except Exception:  # noqa: BLE001 — 관측이 탐지를 깨뜨리면 안 된다.
        pass


async def fetch_recent_gosi_adaptive(
    sigungu_code: str, end_yyyymmdd: str, *, months: int = DEFAULT_WINDOW_MONTHS,
    client: httpx.AsyncClient | None = None,
) -> tuple[list[dict[str, str]], bool, str]:
    """전건이 확보될 때까지 **창을 좁혀** 재조회한다. 반환: (행, 전건확보, 실제 시작일).

    ★왜 필요한가 — 실측: 화성시는 2.5년 창에 600건이라 페이지 상한에 걸려 **통째로 침묵**했다.
      침묵은 안전하지만 탐지가 0이다. 창을 좁히면 **탐지 범위만 줄고 거짓 주장은 생기지 않는다**
      (우리는 결손을 *찾았을 때만* 말하지, "결손 없음"을 말하지 않는다).
    ★그래서 실제로 확인한 창의 시작일을 함께 낸다 — 고지에 범위를 박기 위해서다.
      "최근 N개월 기준" 없이 말하면 확인하지 않은 기간까지 확인한 것처럼 읽힌다.
    """
    end = _date.fromisoformat(f"{end_yyyymmdd[:4]}-{end_yyyymmdd[4:6]}-{end_yyyymmdd[6:]}")
    for m in (months, months // 2, months // 4, 6, 3):
        # ※변이 생존(설명 가능): `months//4` 가 0이 되는 아주 짧은 창에서만 도달한다.
        #   기본값(24)에서는 도달 불가 — 방어로 남긴다.
        if m < 1:
            continue
        start = end - _timedelta(days=int(m * 30.44))
        s8 = start.strftime("%Y%m%d")
        rows, complete = await fetch_recent_gosi(sigungu_code, s8, end_yyyymmdd, client=client)
        if complete:
            return rows, True, s8
    return [], False, ""


def find_uncovered(
    gosi_rows: list[dict[str, str]], known_dates: set[str], *, limit: int = 3,
) -> list[dict[str, str]]:
    """신규 구역 지정 고시 중 **우리 데이터에서 확인되지 않는** 것(최신 우선)."""
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for r in sorted(gosi_rows, key=lambda x: x["date"], reverse=True):
        if not is_new_district_designation(r.get("title", "")):
            continue
        key = (r["date"], r.get("gosino", ""))
        if key in seen:
            continue
        seen.add(key)
        if r["date"].replace("-", "") in known_dates:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def build_coverage_notice(
    uncovered: list[dict[str, str]], *, complete: bool, checked: int,
    sigungu_name: str | None = None, list_url: str | None = None,
    window_start: str | None = None,
) -> dict[str, Any] | None:
    """화면 계약. 결손이 없거나 조회가 불완전하면 **아무것도 단정하지 않는다**(None).

    ★`complete=False`(목록 절단·조회 실패)면 결손 유무를 말할 수 없다 — None 을 낸다.
      여기서 "결손 없음"을 내면 절단된 목록으로 안심시키는 것이 된다.
    """
    if not complete or not uncovered:
        return None
    head = uncovered[0]
    where = f"{sigungu_name} " if sigungu_name else ""
    return {
        # ★'없다/틀렸다'가 아니라 '확인되지 않는다' — 대조는 휴리스틱이다.
        "reason": (
            f"{where}최근 지구단위계획구역 결정고시 중 **우리 데이터에서 확인되지 않는 것**이 "
            f"있습니다: {head['date']} {head['gosino']}. 이 고시가 이 부지에 미치는지 "
            f"원문으로 확인하십시오 — 지구단위계획은 용적률·건폐율·용도를 직접 정합니다."
        ),
        "items": uncovered,
        # ★고시 원문에서 읽은 수치가 있으면 함께 낸다 — **적용값이 아니라 후보**다.
        #   한 구역 안에 획지별로 값이 다르므로(실측: 양산2구역 200%·180%) 어느 것이 이 부지에
        #   걸리는지는 우리가 정하지 않는다. 그래서 개수와 함께 '확인 필요'를 말한다.
        "limits_note": _limits_note(uncovered[0].get("limits")) if uncovered else None,
        "checked_count": checked,
        # ★확인한 범위를 명시한다 — 없으면 확인하지 않은 기간까지 확인한 것처럼 읽힌다.
        "window_start": window_start,
        "list_url": list_url,
        "applied": False,   # 형제 계약과 동일 — 값을 바꾸지 않는다
    }


# ── 소비처용 진입점 — 조회·대조·캐시를 한 곳에서 ────────────────────────────────
#   ★조회가 무겁다(실측: 오산 2.0s · 성남 5.1s · 화성 16.2s — 화성은 창을 6개월로 좁힌 뒤).
#     시군구 단위로 캐시한다. 신선도는 하루 단위로 바뀌지 않으므로 TTL 은 넉넉히 잡는다.
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SEC = 6 * 3600


async def _vworld_known_dates(sigungu_code: str, bbox: str) -> set[str]:
    """VWorld 지구단위 레이어에서 **해당 시군구** 피처의 관리코드 날짜 집합.

    ★BOX 는 시군구 경계를 넘는다(실측: 오산 BOX 68건이 3개 시군구 혼재). 반드시
      `signgu_se` 로 걸러야 한다 — 안 그러면 옆 시군구 고시를 우리 것으로 세어
      **결손을 놓친다**(이 프로젝트가 이미 한 번 데인 형태).
    """
    from app.core.config import settings

    key = getattr(settings, "VWORLD_API_KEY", "") or getattr(settings, "VWORLD_KEY", "") or ""
    if not key:
        return set()
    params = {
        "service": "data", "request": "GetFeature", "data": "LT_C_UPISUQ161",
        "key": key, "domain": "https://4t8t.net", "format": "json",
        "size": "1000", "geomFilter": bbox,
        # ★지오메트리를 빼면 1306KB → 46KB(실측). 우리는 관리코드만 필요하다.
        "geometry": "false",
    }
    async with httpx.AsyncClient(timeout=30.0, headers=_UA) as c:
        resp = await c.get("https://api.vworld.kr/req/data", params=params)
        resp.raise_for_status()
        payload = resp.json()
    body = payload.get("response") or {}
    fc = ((body.get("result") or {}).get("featureCollection")) or {}
    out: set[str] = set()
    for feat in fc.get("features") or []:
        props = feat.get("properties") or {}
        if props.get("signgu_se") != sigungu_code:
            continue
        m = NTFC_DATE_RE.search(str(props.get("ntfc_sn") or ""))
        if m:
            out.add(m.group(0))
    return out


async def gosi_coverage_for_region(
    sigungu_code: str, bbox: str, *, today_yyyymmdd: str | None = None,
    sigungu_name: str | None = None,
) -> dict[str, Any]:
    """시군구 단위 결손 탐지 결과(캐시). 실패·불완전이면 `notice=None`."""
    import time as _time

    ck = f"{sigungu_code}|{bbox}"
    hit = _CACHE.get(ck)
    if hit and (_time.time() - hit[0]) < _CACHE_TTL_SEC:
        return hit[1]

    end = today_yyyymmdd or _date.today().strftime("%Y%m%d")
    rows, complete, window_start = await fetch_recent_gosi_adaptive(sigungu_code, end)
    try:
        known = await _vworld_known_dates(sigungu_code, bbox)
    except Exception as e:  # noqa: BLE001 — 대조 상대를 못 얻으면 결손을 말할 수 없다.
        logger.warning("VWorld 대조 실패: sgg=%s (%s)", sigungu_code, e)
        known, complete = set(), False
    # ★대조 상대가 비면 **모든 고시가 결손처럼 보인다** — 그 상태로 신고하면 전건 위양성이다.
    #   (실측으로 겪었다: 페이징 절단 때 16/16 결손이 나왔고 전부 오탐이었다.)
    if not known:
        complete = False
    uncovered = find_uncovered(rows, known)
    # ★가장 최근 결손 1건에 한해 고시 원문 수치를 읽어 본다(P5).
    #   전건에 하면 PDF 를 여러 개 받아 느려진다(첨부 3~4MB) — 사용자가 먼저 볼 것 하나만.
    #   ★실패해도 조용히 넘어간다: 수치는 **있으면 더 나은 것**이지 없다고 틀린 값이 나가지 않는다.
    if uncovered and uncovered[0].get("seq"):
        limits = await fetch_gosi_limits(uncovered[0]["seq"])
        if limits.get("available"):
            uncovered[0]["limits"] = limits
    result = {
        "sigungu_code": sigungu_code,
        "checked_count": len(rows),
        "window_start": window_start,
        "complete": complete,
        "known_date_count": len(known),
        "notice": build_coverage_notice(
            uncovered, complete=complete, checked=len(rows),
            sigungu_name=sigungu_name, window_start=window_start,
            list_url=f"{EUM_LIST_URL}?selSggCd={sigungu_code}",
        ),
    }
    _CACHE[ck] = (_time.time(), result)
    return result


def bbox_from_geometry(geometry: Any, *, pad_deg: float = 0.06) -> str | None:
    """필지 지오메트리 → 주변을 덮는 `BOX(minx,miny,maxx,maxy)`.

    ★왜 필지 하나가 아니라 주변인가 — 우리가 찾는 것은 **이 시군구의 최근 고시**이지
      이 필지에 걸친 구역이 아니다. 필지 폴리곤만 쓰면 교차하는 구역만 보게 되어
      "이 시군구가 최근 고시를 반영했는가"를 물을 수 없다.
    ★BOX 는 시군구 경계를 넘는다 — 그래서 소비처가 반드시 `signgu_se` 로 다시 거른다
      (실측: 오산 BOX 68건이 3개 시군구 혼재).
    """
    xs: list[float] = []
    ys: list[float] = []

    def walk(node: Any) -> None:
        if isinstance(node, (list, tuple)):
            if len(node) == 2 and all(isinstance(v, (int, float)) for v in node):
                xs.append(float(node[0]))
                ys.append(float(node[1]))
                return
            for child in node:
                walk(child)

    walk((geometry or {}).get("coordinates") if isinstance(geometry, dict) else None)
    if not xs or not ys:
        return None
    return (
        f"BOX({min(xs) - pad_deg:.6f},{min(ys) - pad_deg:.6f},"
        f"{max(xs) + pad_deg:.6f},{max(ys) + pad_deg:.6f})"
    )


async def gosi_coverage_for_pnu(pnu: str, *, sigungu_name: str | None = None) -> dict[str, Any]:
    """PNU 하나로 결손 탐지 — 시군구코드·BOX 를 **백엔드가 스스로 구한다**.

    ★화면이 좌표를 갖고 있지 않다(`SiteAnalysisData` 는 `zoneCode·address·pnu` 뿐이다).
      좌표를 요구하는 계약을 만들면 훅이 **한 번도 실행되지 않는다** — 이 저장소가 반복해서
      데인 "정의만 하고 소비처 0"이 된다. 그래서 PNU 만 받는다.
    """
    from app.services.external_api.vworld_service import VWorldService

    sgg = (pnu or "")[:5]
    if len(sgg) != 5:
        return {"sigungu_code": sgg, "complete": False, "notice": None,
                "error": "pnu_invalid"}
    feature = await VWorldService().get_parcel_by_pnu(pnu)
    bbox = bbox_from_geometry((feature or {}).get("geometry"))
    if not bbox:
        # 필지 지오메트리를 못 얻으면 대조 상대를 만들 수 없다 — 아무것도 단정하지 않는다.
        return {"sigungu_code": sgg, "complete": False, "notice": None,
                "error": "parcel_geometry_unavailable"}
    return await gosi_coverage_for_region(sgg, bbox, sigungu_name=sigungu_name)


# ── 고시 원문에서 **수치 후보**를 읽는다(P5) ──────────────────────────────────────
#   【인계서 전제를 반증했다】여러 세션 인계서가 P5 를 *"조서 숫자(사용자 입력 전제라
#   제품 결정 사안)"* 로 못 박아 두었다. 실측하니 **기계로 읽힌다**:
#   오산 지구단위계획 고시 6건 중 **5건에서 텍스트 추출 성공**(1건만 이미지 스캔)이고,
#   내삼미1구역 `용적률 80%` · 원동7구역 `용적률 200%` · 양산2구역 `200%·180%` 가 나왔다.
#   ★사고 당시 사용자가 신고한 "실제 계획 200%"와 원동7구역 값이 일치한다.
#
#   【다운로드 열쇠 — 이것 때문에 막혀 있었다】토지이음 첨부는 `/web/FileDownload.do` 에
#   **POST** 하는데, 사이트가 EUC-KR 이라 **폼 바디를 EUC-KR 로 인코딩**해야 한다.
#   UTF-8 로 보내면 세션·헤더가 다 맞아도 `alert('첨부파일이 없습니다.')` 만 돌아온다.
#
#   【★무엇을 주장하지 않는가】읽은 수치를 **적용하지 않는다**. 지구단위계획은 한 구역 안에서
#   **획지·가구마다 값이 다르다**(양산2구역에서 200%와 180%가 함께 나왔다). 어느 값이 이
#   필지에 걸리는지는 조서·도면을 봐야 알 수 있고 우리는 그 매칭을 하지 않는다.
#   그래서 **후보로만** 내고 "이 부지에 적용되는지 확인 필요"를 함께 낸다.

_PDF_MAGIC = b"%PDF"
_DOWNLOAD_URL = "https://www.eum.go.kr/web/FileDownload.do"
_DETAIL_URL = "https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp"
_DOWNLOAD_ARG_RE = re.compile(r"javascript:download\('([^']+)'\s*,\s*'([^']+)'\)")
# `용적률 ∘ 200%` · `용적률 ⦁80%` — 원문에 불릿/공백이 섞인다(실측).
_FAR_RE = re.compile(r"용적률[^0-9]{0,60}?(\d{2,4})\s*(?:퍼센트|%)")
_BCR_RE = re.compile(r"건폐율[^0-9]{0,60}?(\d{1,3})\s*(?:퍼센트|%)")
# 텍스트 PDF 판정 하한 — 스캔본은 실측 7~13자였다(여백·머리글 정도만 잡힌다).
_MIN_TEXT_CHARS = 500


def parse_far_bcr_candidates(text: str) -> dict[str, list[int]]:
    """고시 본문 텍스트 → 용적률·건폐율 **후보 전부**(중복 제거, 등장 순서 유지).

    ★하나만 고르지 않는다 — 한 구역 안에 값이 여럿이다(실측: 양산2구역 200%·180%).
      P4 에서 배운 것과 같다: 순서가 의미를 뜻하지 않으므로 임의 선택은 오답이 된다.
    """
    def _uniq(pat: re.Pattern[str], lo: int, hi: int) -> list[int]:
        out: list[int] = []
        for m in pat.finditer(text or ""):
            v = int(m.group(1))
            if lo <= v <= hi and v not in out:
                out.append(v)
        return out

    return {
        # 법정 최대(중심상업 1500%)를 넘는 값은 오독이다 — 범위로 거른다.
        "far_pct": _uniq(_FAR_RE, 20, 1500),
        "bcr_pct": _uniq(_BCR_RE, 5, 90),
    }


def _pdf_text(content: bytes, *, seq: str = "") -> str | None:
    """PDF 바이트 → 텍스트. 실패하면 None(**침묵하지 않고 경고를 남긴다**).

    ★모듈 수준으로 뺀 이유: 테스트가 **외부 경계만** 대역할 수 있게 하기 위해서다.
      함수 안에 `import fitz` 가 박혀 있으면 오케스트레이션 층(다운로드·선택·판정)이
      통째로 무잠금이 된다 — 이 세션에서 같은 실수를 이미 두 번 했다.
    ★`PyMuPDF` 는 `requirements.oracle.txt` 에 **명시적으로** 선언돼 있어야 한다
      (실측: 프로덕션에 있으나 `Required-by` 가 비어 재빌드 시 사라질 수 있었다).
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:  # noqa: BLE001 — PDF 파손·라이브러리 부재
        logger.warning("고시 PDF 텍스트 추출 실패: seq=%s (%s)", seq, e)
        return None


async def fetch_gosi_limits(seq: str, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """고시 상세(`seq`) → 첨부 PDF → 용적률·건폐율 **후보**. 실패·스캔이면 정직하게 빈 결과.

    반환: `{"available", "far_pct", "bcr_pct", "source_file", "text_chars", "reason"}`
      · `available=False` 면 **아무 수치도 주장하지 않는다**(스캔본·다운로드 실패·첨부 없음).
    """
    owns = client is None
    c = client or httpx.AsyncClient(timeout=90.0, headers=_UA, follow_redirects=True)
    try:
        det = await c.get(_DETAIL_URL, params={"seq": seq})
        det.raise_for_status()
        page = det.content.decode("euc-kr", "replace")
        pdfs = [f for _u, f in _DOWNLOAD_ARG_RE.findall(page) if f.lower().endswith(".pdf")]
        if not pdfs:
            return {"available": False, "reason": "pdf_attachment_absent",
                    "far_pct": [], "bcr_pct": []}

        best: tuple[int, str, str] | None = None   # (텍스트 길이, 텍스트, 파일명)
        for path in pdfs[:3]:
            # ★EUC-KR 폼 인코딩이 필수다(위 주석 참조) — UTF-8 이면 '첨부파일이 없습니다'.
            body = f"file={_quote(path, encoding='euc-kr')}&gosi=Y&seq={seq}".encode()
            resp = await c.post(
                _DOWNLOAD_URL, content=body,
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "Referer": str(det.url)},
            )
            # ※변이 생존(설명 가능): 이 검사를 지워도 아래 `_pdf_text` 가 HTML 을 열지 못해
            #   None 을 내고 같은 `continue` 로 닫힌다(**이중 가드**). 실패 사유를 여기서
            #   조기에 가르는 편이 읽기 쉬워 남긴다.
            if resp.content[:4] != _PDF_MAGIC:
                continue
            text = _pdf_text(resp.content, seq=seq)
            # ※변이 생존(설명 가능): 위 PDF 매직 검사와 **이중 가드**다(둘 다 같은 continue).
            if text is None:
                continue
            if best is None or len(text) > best[0]:
                best = (len(text), text, path.rsplit("/", 1)[-1])

        if best is None:
            return {"available": False, "reason": "download_failed", "far_pct": [], "bcr_pct": []}
        chars, text, fname = best
        if chars < _MIN_TEXT_CHARS:
            # ★스캔본 — 이미지라 읽을 것이 없다(실측 7~13자). OCR 은 하지 않는다.
            #   여기서 빈 후보를 "수치 없음"으로 내면 **없는 것과 못 읽은 것이 뭉개진다**.
            return {"available": False, "reason": "scanned_image", "source_file": fname,
                    "text_chars": chars, "far_pct": [], "bcr_pct": []}
        cands = parse_far_bcr_candidates(text)
        return {
            "available": bool(cands["far_pct"] or cands["bcr_pct"]),
            "reason": None if (cands["far_pct"] or cands["bcr_pct"]) else "no_numbers_in_text",
            "source_file": fname, "text_chars": chars, **cands,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("고시 수치 추출 실패: seq=%s (%s)", seq, e)
        return {"available": False, "reason": "error", "far_pct": [], "bcr_pct": []}
    finally:
        if owns:
            await c.aclose()


def _limits_note(limits: Any) -> str | None:
    """읽은 수치를 **후보로만** 말하는 한 문장. 없으면 None(단정 금지)."""
    if not isinstance(limits, dict) or not limits.get("available"):
        return None
    far = limits.get("far_pct") or []
    bcr = limits.get("bcr_pct") or []
    parts: list[str] = []
    if far:
        parts.append("용적률 " + " · ".join(f"{v}%" for v in far))
    if bcr:
        parts.append("건폐율 " + " · ".join(f"{v}%" for v in bcr))
    if not parts:
        return None
    multi = len(far) > 1 or len(bcr) > 1
    tail = (
        " — 한 구역 안에서도 획지마다 값이 다릅니다. 이 부지에 어느 값이 걸리는지는 "
        "조서·도면으로 확인하십시오."
        if multi else
        " — 이 값이 이 부지에 적용되는지는 조서·도면으로 확인하십시오."
    )
    return f"고시 원문에서 읽은 값(후보): {' / '.join(parts)}{tail}"
