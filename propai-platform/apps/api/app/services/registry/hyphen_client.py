"""하이픈(Hyphen Data Market) 부동산등기부등본 연동 API 클라이언트.

명세: https://api.hyphen.im (REST POST)
엔드포인트:
 - 주소검색: /in0004000168(간편주소), /in0004000167(도로명), /in0004000166(지번), /in0004000169(고유번호)
 - 등기부 열람: /in0004000948(민원캐시 차감 열람), /in0004000949(비회원 열람), /in0004001436(회원 발급)

인증:
 - Headers: HKey (HYPHEN_HKEY), User-Id (HYPHEN_USER_ID)
"""

from __future__ import annotations

import base64
import os
from typing import Any

import structlog

from app.services.common.exc_detail import exc_detail

logger = structlog.get_logger(__name__)


def _host() -> str:
    return (os.getenv("HYPHEN_API_HOST") or "https://api.hyphen.im").rstrip("/")


def hyphen_hkey() -> str:
    return (os.getenv("HYPHEN_HKEY") or os.getenv("HYPHEN_API_KEY") or "").strip()


def hyphen_user_id() -> str:
    return (os.getenv("HYPHEN_USER_ID") or "").strip()


def hyphen_ready() -> bool:
    return bool(hyphen_hkey() and hyphen_user_id())


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "HKey": hyphen_hkey(),
        "User-Id": hyphen_user_id(),
    }


# ── API 권한 실도달성 점검 ────────────────────────────────────────────────
# 키가 있다고 "연결됨"이라 말하면 안 된다 — 하이픈은 키가 유효해도 계약에 없는
# API는 errYn=Y "권한이 없는 API 입니다"로 거절한다(라이브에서 실제 발생).
# 틸코가 공개키를 실제로 받아와 검증(public_key_ok)하는 것과 대칭을 맞춘다.
_ACCESS_CACHE: dict[str, Any] = {}
_ACCESS_TTL_SEC = 300.0
# 권한 거절 및 인증 실패를 알리는 벤더 문구/코드
_FORBIDDEN_HINTS = (
    "권한이 없는 API",
    "권한이 없습니다",
    "권한 없음",
    "UserId 또는 HKey가 올바르지 않습니다",
    "HKey가 올바르지 않습니다",
    "회원 정보가 존재하지 않습니다",
    "올바르지 않습니다",
)


def _is_forbidden_message(msg: str) -> bool:
    m = (msg or "").strip()
    if not m:
        return False
    if any(h in m for h in _FORBIDDEN_HINTS):
        return True
    return ("권한" in m or "HKey" in m or "UserId" in m) and ("API" in m.upper() or "올바르지" in m or "없습니다" in m)


async def probe_api_access(force: bool = False) -> dict[str, Any]:
    """하이픈 계정이 등기 조회 API를 실제로 호출할 수 있는지 점검.

    반환: {"access": "ok"|"forbidden"|"unreachable"|"not_configured",
           "checked": bool, "message": str}

    - 과금되지 않는 검색 API(고유번호검색)로 확인한다(열람 API는 1,200원 차감이라 금지).
    - 데이터가 없어서 나는 오류(존재하지 않는 고유번호)는 '권한 있음'으로 본다 —
      요청이 계약 관문을 통과했다는 뜻이기 때문이다.
    - 결과는 짧게 캐시한다(상태 조회마다 벤더를 두드리지 않도록).
    """
    import time

    if not hyphen_ready():
        return {"access": "not_configured", "checked": False,
                "message": "HYPHEN_HKEY / HYPHEN_USER_ID 미설정"}

    now = time.monotonic()
    hit = _ACCESS_CACHE.get("v")
    if hit and not force and (now - hit[0]) < _ACCESS_TTL_SEC:
        return dict(hit[1])

    import httpx

    out: dict[str, Any]
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            # 고유번호검색(/in0004000169) — 조회 전용·무과금. 더미 번호로 관문만 통과 확인.
            resp = await client.post(f"{_host()}/in0004000169", headers=_headers(),
                                     json={"uniqNo": "00000000000000"})
            if resp.status_code != 200:
                out = {"access": "unreachable", "checked": True,
                       "message": f"하이픈 응답 오류(HTTP {resp.status_code})"}
            else:
                data = resp.json()
                common = data.get("common") or {}
                err_yn = common.get("errYn")
                err_cd = str(common.get("errCd") or "")
                err_msg = str(common.get("errMsg") or "")

                if err_yn == "Y":
                    if err_cd in ("HDM009", "HDM008") or _is_forbidden_message(err_msg):
                        out = {
                            "access": "forbidden",
                            "checked": True,
                            "message": f"하이픈 인증 실패 ({err_msg or 'UserId 또는 HKey가 올바르지 않습니다'}) — 설정에서 HKey 및 User-Id를 확인하세요.",
                        }
                    else:
                        # errYn=Y여도 '권한/인증' 사유가 아니면 관문은 통과한 것(데이터 없음 등)
                        out = {"access": "ok", "checked": True, "message": "하이픈 등기 API 호출 권한 확인됨"}
                else:
                    out = {"access": "ok", "checked": True, "message": "하이픈 등기 API 호출 권한 확인됨"}
    except Exception as e:  # noqa: BLE001
        # ★사유를 버리지 않는다(라이브 실측 2026-08-24).
        #   프로덕션 응답이 정확히 `"하이픈 연결 실패: "` 였다 — 사유가 **빈 문자열**이었다.
        #   `httpx.ConnectTimeout()`·`ReadTimeout()` 같은 타임아웃 계열은 `str(e)` 가 비어서,
        #   그대로 쓰면 **무엇이 막혔는지 알 수 없게 된다**.
        #   예외 **클래스명**이 기전을 가른다 — 이 한 조각이 진단을 통째로 좌우한다:
        #     ConnectTimeout / ConnectError → TCP 단계 차단(방화벽·보안목록·경로)
        #     ReadTimeout                   → 연결은 됐으나 응답 없음(상대 WAF 드롭 등)
        #     HTTPStatusError               → 벤더가 오류를 **응답**한 것(계약·인증·한도)
        detail = exc_detail(e)
        logger.warning("하이픈 권한 점검 예외", err=detail[:160])
        out = {"access": "unreachable", "checked": True,
               "message": f"하이픈 연결 실패: {detail[:120]}"}

    _ACCESS_CACHE["v"] = (now, dict(out))
    return out


def normalize_address_candidates(address: str) -> list[str]:
    """임야/산지 지번(산 1-1 ↔ 산1-1) 및 광역시/도 축약 주소 변형 후보를 자동 생성.

    1차 주소검색 실패 시 자동 폴백하여 벤더 주소검색 파서의 미세한 포맷 차이에 따른
    주소검색 누락(no_match)을 자동 보정한다.
    """
    import re

    addr = " ".join((address or "").split()).strip()
    if not addr:
        return []

    candidates: list[str] = []

    def _add(s: str) -> None:
        s = " ".join(s.split()).strip()
        if s and s not in candidates:
            candidates.append(s)

    _add(addr)

    # 1. "산 1-1" ↔ "산1-1" (산과 본번 사이 띄어쓰기 변형)
    v1 = re.sub(r"산\s+(\d+)", r"산\1", addr)
    _add(v1)
    v2 = re.sub(r"산(\d+)", r"산 \1", addr)
    _add(v2)

    # 2. 광역시/도 제거 및 시/군/구 이하 축약 주소 후보 생성
    parts = addr.split()
    if len(parts) >= 3:
        # 광역시/도 제거
        if any(parts[0].endswith(e) for e in ("도", "시", "특별시", "광역시", "특별자치도", "특별자치시")):
            without_do = " ".join(parts[1:])
            _add(without_do)
            _add(re.sub(r"산\s+(\d+)", r"산\1", without_do))
            _add(re.sub(r"산(\d+)", r"산 \1", without_do))

        # 읍/면/동/리 + 지번 축약
        for i in range(1, len(parts) - 1):
            sub = " ".join(parts[i:])
            if re.search(r"(?:산\s*)?\d+", sub):
                _add(sub)
                _add(re.sub(r"산\s+(\d+)", r"산\1", sub))
                _add(re.sub(r"산(\d+)", r"산 \1", sub))

    return candidates



# ★하이픈 주소검색은 **한글 문자열**을 받는다 — 숫자 코드가 아니다(2026-08-12 명세 확인).
#   내부 구분 코드(realty_kind: "1"집합건물 "2"토지 "3"건물 "0"/None 전체)를 그 표기로 옮긴다.
_KINDCLS_KO = {"0": "전체", "1": "집합건물", "2": "토지", "3": "건물", "": "전체"}
#   등기등록상태도 마찬가지다(현행/폐쇄/현행+폐쇄).
_CLSFLAG_KO = {"1": "현행", "2": "폐쇄", "3": "현행+폐쇄", "": "현행"}

# 시/도 표기(`admin_regn1`)는 **필수**인데 종전 요청에는 아예 없었다.
_SIDO = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
    "울산광역시", "세종특별자치시", "경기도", "강원특별자치도", "강원도",
    "충청북도", "충청남도", "전북특별자치도", "전라북도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
)
# 축약 표기도 흔히 들어온다("서울 강남구 …").
_SIDO_ALIAS = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}


def pick_field(d: dict[str, Any], name: str) -> Any:
    """응답에서 필드를 읽는다 — `get` 접두사 유무를 **양쪽 다** 본다.

    ★2026-08-12 라이브 실측: 실제 응답 키에는 `get` 접두사가 **없다**(`부동산고유번호`).
    그런데 벤더 명세 화면의 스키마는 `get부동산고유번호` 로 표시한다. 그 표기를 믿고 짠
    파서는 **검색이 성공해도** 값을 못 읽어 `unique_no` 가 빈 문자열이 됐다.

    ★모듈 레벨 공용 헬퍼인 이유: 같은 파일 안에 같은 파서가 **셋**(주소검색·고유번호검색·
    등기부 열람) 있는데 처음엔 한 곳만 고쳤다. 리뷰가 "형제 미스윕" 으로 잡았다 —
    한 곳을 고치면 전역이 따라오게 공용화한다(CLAUDE.md 전역 전파방지).

    ★빈 문자열은 값으로 인정하지 않는다 — 두 표기가 공존하고 한쪽이 비어 있을 때
    비어 있는 쪽을 채택하면 결함이 그대로 남는다.
    """
    v = d.get(name)
    if v is None or v == "":
        v2 = d.get(f"get{name}")
        return v if v2 is None or v2 == "" else v2
    return v


def extract_sido(address: str) -> str:
    """주소 문자열에서 시/도(`admin_regn1`)를 뽑는다. 못 뽑으면 빈 문자열.

    ★이 값이 **필수**다. 빠지면 하이픈은 `[C0000-002] 검색조건에 대한 결과가 없습니다`
    를 돌려준다 — "결과 없음" 처럼 보이지만 실제로는 **요청이 불완전**한 것이다.
    그 오해 때문에 "등기 열람이 안 된다" 가 오래 방치됐다.
    """
    a = (address or "").strip()
    for s in _SIDO:
        if a.startswith(s):
            return s
    head = a.split()[0] if a.split() else ""
    return _SIDO_ALIAS.get(head, "")


async def _search_single_address(
    address: str,
    kindcls: str = "0",
    cls_flag: str = "1",
    limit_page: str = "1",
    page_no: str = "1",
) -> dict[str, Any]:
    """단일 주소 원시 검색 (POST /in0004000168).

    ★2026-08-12 명세 대조로 두 결함을 고쳤다(라이브 실측으로 확증):
      1) 값 형식 — `kindcls`·`cls_flag` 는 **한글 문자열**인데 숫자 코드를 보내고 있었다.
      2) 필수 누락 — `admin_regn1`(시/도)를 아예 안 보냈다.
    둘 다 `[C0000-002] 결과가 없습니다` 로 나타나 **데이터가 없는 것처럼 보였다.**
    """
    import httpx

    url = f"{_host()}/in0004000168"
    sido = extract_sido(address)
    body = {
        "kindcls": _KINDCLS_KO.get(kindcls, kindcls or "전체"),
        # 시/도를 못 뽑으면 "전체" 로 둔다(문서상 기본값) — 빈 문자열은 VALID 오류다.
        "admin_regn1": sido or "전체",
        "cls_flag": _CLSFLAG_KO.get(cls_flag, cls_flag or "현행"),
        "simple_address": address,
        "detailYn": "Y",
        "limitPage": limit_page,
        "pageNo": page_no,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=_headers(), json=body)
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "status": "provider_error",
                    "items": [],
                    "message": f"하이픈 주소검색 오류 (HTTP {resp.status_code})",
                }
            data = resp.json()

        common = data.get("common") or {}
        err_yn = common.get("errYn")
        if err_yn and err_yn != "N":
            return {
                "ok": False,
                "status": "provider_error",
                "items": [],
                "message": common.get("errMsg") or "주소검색 실패",
                "raw": data,
            }

        res_data = data.get("data") or {}
        raw_list = res_data.get("list") or []
        items = []
        for item in raw_list:
            if isinstance(item, dict):
                items.append({
                    "unique_no": (pick_field(item, "부동산고유번호") or "").replace("-", "").strip(),
                    "gubun": pick_field(item, "구분"),
                    "owner": pick_field(item, "소유자"),
                    "jibun": pick_field(item, "부동산소재지번"),
                    "sangtae": pick_field(item, "상태"),
                })

        return {
            "ok": True,
            "status": "ok",
            "items": items,
            "total": res_data.get("totCnt") or len(items),
            "raw": data,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 간편주소검색 예외", err=exc_detail(e, limit=120))
        return {"ok": False, "status": "error", "items": [], "message": exc_detail(e, limit=200)}


async def search_by_simple_address(
    address: str,
    kindcls: str = "0",
    cls_flag: str = "1",
    limit_page: str = "1",
    page_no: str = "1",
) -> dict[str, Any]:
    """간편주소로 부동산 고유번호 검색 (POST /in0004000168).

    산지/임야 지번(산 1-1 ↔ 산1-1) 등 띄어쓰기 변형 후보를 자동 폴백 시도하여
    주소검색 누락을 자동 보정한다.
    """
    if not hyphen_ready():
        return {
            "ok": False,
            "status": "not_configured",
            "items": [],
            "message": "HYPHEN_HKEY / HYPHEN_USER_ID 미설정",
        }

    addr = (address or "").strip()
    if not addr:
        return {"ok": False, "status": "bad_request", "items": [], "message": "주소가 필요합니다."}

    candidates = normalize_address_candidates(addr)

    # 1차: 원본 주소 즉시 검색
    first_res = await _search_single_address(
        candidates[0], kindcls=kindcls, cls_flag=cls_flag, limit_page=limit_page, page_no=page_no
    )
    if first_res.get("ok") and first_res.get("items"):
        return first_res

    # 2차: 1차 실패 시 나머지 후보들을 병렬로 동시 검색(지연 및 타임아웃 방지)
    import asyncio

    if len(candidates) > 1:
        tasks = [
            _search_single_address(cand, kindcls=kindcls, cls_flag=cls_flag, limit_page=limit_page, page_no=page_no)
            for cand in candidates[1:]
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # ★`strict=True` — `tasks` 가 바로 위에서 `candidates[1:]` 로 생성되므로 길이가
        #   **항상 같다**. 어긋나는 일이 생기면 조용히 잘리는 대신 드러나는 편이 안전하다.
        #   (이 줄의 B905 로 main CI 가 막혀 **모든 PR** 이 함께 멈춰 있었다.)
        for cand, res in zip(candidates[1:], results, strict=True):
            if isinstance(res, dict) and res.get("ok") and res.get("items"):
                logger.info("하이픈 주소검색 병렬 자동보정 성공", original=addr, corrected=cand, count=len(res["items"]))
                return res

    return first_res or {"ok": False, "status": "no_match", "items": [], "message": "주소 검색 결과가 없습니다."}



async def search_by_unique_no(unique_no: str) -> dict[str, Any]:
    """고유번호로 주소 검색 (POST /in0004000169)."""
    if not hyphen_ready():
        return {"ok": False, "status": "not_configured", "items": [], "message": "HYPHEN 인증키 미설정"}

    uno = (unique_no or "").replace("-", "").strip()
    if not uno:
        return {"ok": False, "status": "bad_request", "items": [], "message": "고유번호가 필요합니다."}

    import httpx

    url = f"{_host()}/in0004000169"
    body = {"uniqNo": uno}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=_headers(), json=body)
            resp.raise_for_status()
            data = resp.json()

        res_data = data.get("data") or {}
        raw_list = res_data.get("list") or []
        items = [
            {
                "unique_no": (pick_field(it, "부동산고유번호") or "").replace("-", "").strip(),
                "gubun": pick_field(it, "구분"),
                "owner": pick_field(it, "소유자"),
                "jibun": pick_field(it, "부동산소재지번"),
                "sangtae": pick_field(it, "상태"),
            }
            for it in raw_list
            if isinstance(it, dict)
        ]
        return {"ok": True, "status": "ok", "items": items, "raw": data}
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 고유번호검색 예외", err=exc_detail(e, limit=120))
        return {"ok": False, "status": "error", "items": [], "message": exc_detail(e, limit=200)}


# ── 등기부 열람 응답 파서 ──────────────────────────────────────────────────
# ★2026-08-15 프로덕션 실측으로 드러난 **마지막 구간 결함**. 열람은 계속 성공하고
#   있었다(`errYn: N`, `열람일시` 기록). 벤더는 127KB PDF 와 26KB 구조화 등기 데이터를
#   매번 보냈다. 그런데 우리 파서가 **키 이름을 틀려** 둘 다 버렸다:
#     · PDF   : 우리가 읽은 `pdfHex` ↔ 실제 `pdfHexString`
#     · 소유자: 우리가 읽은 `소유자` ↔ 실제 `소유지분현황_갑구[].등기명의인`
#   결과는 `ok: True` + `has_pdf: False` + `owner: None` — **문서 없는 성공**이었고,
#   사용자에게는 "열람이 안 된다" 로 보였다. RC-1(주소검색 키)과 **같은 결함 클래스**다.
# ★그래서 이름 후보를 표로 두고 **하나라도 맞으면** 쓴다 — 벤더가 표기를 바꿔도 견딘다.
# ★근거 있는 둘만 둔다. 첫 판에는 `pdf_hex`·`pdfHexStr` 도 넣었는데 **어디에도 근거가
#   없는 추측**이었다(소비처 0). 추측을 표에 넣으면 다음 사람이 "실측된 표기" 로 읽는다.
_PDF_HEX_KEYS = ("pdfHexString", "pdfHex")
# ★**실측된 표 하나만** 본다(2026-08-15 역삼동 737 열람 응답).
#   첫 판에는 폴백으로 `소유권에_관한_사항_갑구` 와 `권리자_및_기타사항` 을 넣었는데,
#   리뷰가 그 조합의 파괴력을 실행으로 보였다:
#     · 갑구는 순위번호 **오름차순** — 첫 행은 소유권보존, 즉 **최초 소유자**다(현재가 아니라)
#     · 갑구에는 가압류·압류·경매개시결정도 산다 → **채권자가 소유자로** 나온다
#     · `권리자_및_기타사항` 은 이름·주민등록번호·주소가 **줄 단위로 구분된 블롭**이라,
#       줄바꿈을 접착하는 우리 `_clean` 과 만나면 번호까지 붙어 화면·DB·LLM 으로 흐른다
#   그 표가 실제로 오는지조차 **측정한 적이 없다**. 측정 전까지 넣지 않는다 —
#   "이름 후보를 여럿 두면 견고하다" 는 **동종 스칼라(PDF 키)에서만** 참이고,
#   **의미가 다른 칸**에 적용하면 견고한 게 아니라 오답을 만든다.
_OWNER_TABLES = ("소유지분현황_갑구",)
_OWNER_FIELDS = ("등기명의인", "소유자")
_SHARE_FIELDS = ("최종지분", "지분")


def extract_pdf_hex(res_data: dict[str, Any]) -> str:
    """열람 응답에서 PDF 16진 문자열을 찾는다 — 표기 후보를 **전부** 본다."""
    for k in _PDF_HEX_KEYS:
        v = res_data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _clean(v: Any) -> str:
    """벤더 값의 줄바꿈을 없앤다 — **공백으로 바꾸지 않고 이어 붙인다**.

    ★실측: 소유자가 `"강남금융센터주\r\n식회사 (소유자)"` 로 온다. 벤더가 등기부 지면
      너비에 맞춰 **단어 중간에서** 접은 것이다. 그래서 흔한 처리인 `" ".join(v.split())`
      을 쓰면 `"강남금융센터주 식회사"` 라는 **존재하지 않는 상호**가 만들어진다 —
      상호 검색·대조가 전부 빗나간다(첫 판에서 실제로 그렇게 짰다가 잡았다).
    ★줄바꿈만 제거하고, 남은 공백 연속은 하나로 줄인다. 벤더가 공백 뒤에서 접은 경우
      (`"홍길동 \r\n(소유자)"`)는 그 공백이 이미 있으므로 표기가 보존된다.
    """
    # ★스칼라만 문자열로 만든다. 벤더가 공유 소유자를 리스트로 주면 종전 코드는
    #   `"['김철수', '박영희']"` 라는 **파이썬 repr** 을 화면에 그대로 띄웠다.
    if isinstance(v, (list, tuple)):
        return ", ".join(_clean(x) for x in v if _clean(x))
    if v is None or isinstance(v, (dict, set)):
        return ""
    t = str(v).replace("\r\n", "").replace("\r", "").replace("\n", "")
    return " ".join(t.split())


def extract_owners(out_list: Any) -> list[dict[str, str]]:
    """등기 본문에서 소유자를 **전부** 뽑는다 — `[{"name":…, "share":…}, …]`.

    ★한 명으로 줄이지 않는 이유: 공유 필지는 `소유지분현황_갑구` 에 행이 여럿이고
      벤더가 **행마다 `최종지분`("2분의 1"/"단독소유")을 준다**. 첫 행만 쓰면 나머지
      소유자와 지분이 통째로 사라지는데, 그 값이 화면·DB 캐시·외부 LLM 프롬프트
      **세 표면**에 "이 필지의 소유자" 로 흐른다(이 저장소의 다필지 대표값 혼입 클래스).

    ★`outList` 는 dict 이고 갑구 표는 **리스트 또는 JSON 문자열**로 온다.
    """
    import json

    if isinstance(out_list, list):
        out_list = out_list[0] if out_list else {}
    if not isinstance(out_list, dict):
        return []

    # 종전 표기(평평한 `소유자` 필드)도 계속 지원한다 — 있으면 그대로 한 명으로 본다.
    flat = _clean(pick_field(out_list, "소유자"))
    if flat:
        return [{"name": flat, "share": ""}]

    owners: list[dict[str, str]] = []
    for table in _OWNER_TABLES:
        rows = out_list.get(table)
        if isinstance(rows, str):
            try:
                rows = json.loads(rows)
            except Exception:  # noqa: BLE001
                continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            # 초기값은 표(_OWNER_FIELDS)가 비었을 때만 쓰인다 — 지금은 도달 불가라
            # 변이가 생존한다(그 사실을 적어 둔다). 표를 비우는 변경에 대한 방어.
            name = ""
            for f in _OWNER_FIELDS:
                name = _clean(row.get(f))
                if name:
                    break
            if not name:
                continue
            share = ""   # 위와 같은 이유의 초기값(표가 비었을 때만 쓰임)
            for f in _SHARE_FIELDS:
                share = _clean(row.get(f))
                if share:
                    break
            owners.append({"name": name, "share": share})
    return owners


def format_owner(owners: list[dict[str, str]]) -> str | None:
    """표시용 한 줄. **축약했다는 사실이 보이게** 만든다.

    ★"김철수" 로만 내면 읽는 쪽은 단독 소유라고 믿는다. "김철수 외 1인" 이면
      더 있다는 것이 화면·프롬프트 어디서든 드러난다.
    """
    if not owners:
        return None
    head = owners[0]["name"]
    return head if len(owners) == 1 else f"{head} 외 {len(owners) - 1}인"


def extract_owner(out_list: Any) -> str | None:
    """표시용 소유자 한 줄(하위호환 진입점)."""
    return format_owner(extract_owners(out_list))


async def fetch_realty_registry(
    *,
    unique_no: str,
    user_id: str | None = None,
    user_pw: str | None = None,
    user_pw_enc: str | None = None,
    pay_no: str | None = None,
    pay_pw: str | None = None,
    pay_pw_enc: str | None = None,
    cmort_check: str = "N",
    trade_check: str = "N",
    display: str = "2",
) -> dict[str, Any]:
    """등기부등본 민원캐시 차감 열람 (POST /in0004000948)."""
    if not hyphen_ready():
        return {
            "ok": False,
            "status": "not_configured",
            "message": "HYPHEN_HKEY 및 HYPHEN_USER_ID 환경변수가 필요합니다.",
        }

    uno = (unique_no or "").replace("-", "").strip()
    if not uno:
        return {"ok": False, "status": "need_unique_no", "message": "부동산 고유번호(14자리)가 필요합니다."}

    uid = user_id or os.getenv("HYPHEN_IROS_USER_ID") or ""
    upw = user_pw or os.getenv("HYPHEN_IROS_USER_PW") or ""
    upw_enc = user_pw_enc or os.getenv("HYPHEN_IROS_USER_PW_ENC") or ""
    pno = pay_no or os.getenv("HYPHEN_PAY_NO") or ""
    ppw = pay_pw or os.getenv("HYPHEN_PAY_PW") or ""
    ppw_enc = pay_pw_enc or os.getenv("HYPHEN_PAY_PW_ENC") or ""

    import httpx

    url = f"{_host()}/in0004000948"
    body: dict[str, Any] = {
        "userId": uid,
        "searchDiv": "uniqNo",
        "uniqNo": uno,
        "cmortCheck": cmort_check,
        "tradeCheck": trade_check,
        "pdfHex": "Y",
        "xmlYn": "N",
        "display": display,
        "payDiv": "0",
        "payNo": pno,
        "dupChk": "Y",
    }
    if upw_enc:
        body["userPwEnc"] = upw_enc
    else:
        body["userPw"] = upw

    if ppw_enc:
        body["payPwEnc"] = ppw_enc
    else:
        body["payPw"] = ppw

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, headers=_headers(), json=body)
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "status": "provider_error",
                    "message": f"하이픈 열람 응답 오류 (HTTP {resp.status_code})",
                    "raw": resp.text[:300],
                }
            data = resp.json()

        common = data.get("common") or {}
        err_yn = common.get("errYn")
        if err_yn and err_yn != "N":
            return {
                "ok": False,
                "status": "provider_error",
                "error_code": common.get("errCd"),
                "message": common.get("errMsg") or "하이픈 등기부 열람 실패",
                "raw": data,
            }

        res_data = data.get("data") or {}
        pdf_hex = extract_pdf_hex(res_data)
        pdf_b64 = None
        if pdf_hex:
            try:
                pdf_bytes = bytes.fromhex(pdf_hex)
                pdf_b64 = base64.b64encode(pdf_bytes).decode()
            except Exception as pe:  # noqa: BLE001
                logger.warning("하이픈 등기부 PDF 변환 실패", err=str(pe)[:80])

        out_list = res_data.get("outList") or {}
        owners = extract_owners(out_list)
        # ★MED-2: `raw` 에 pdfHexString(254KB)이 그대로 있어 같은 문서를 두 번 실어 보냈다.
        #   base64 로 이미 싣고 있으므로 원본 hex 는 응답에서 뺀다(내용 손실 없음).
        raw_slim = dict(data)
        if isinstance(raw_slim.get("data"), dict):
            d2 = dict(raw_slim["data"])
            for k in _PDF_HEX_KEYS:
                d2.pop(k, None)
            raw_slim["data"] = d2

        return {
            "ok": True,
            "status": "ok",
            "origin": "hyphen",
            "unique_no": uno,
            "pdf_base64": pdf_b64,
            "has_pdf": bool(pdf_b64),
            "owner": format_owner(owners),
            "owners": owners,
            "owner_count": len(owners),
            "out_list": out_list,
            "raw": raw_slim,
            "message": "하이픈 부동산 등기부 열람 성공",
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("하이픈 등기부 열람 예외", err=exc_detail(e, limit=160))
        return {"ok": False, "status": "error", "message": exc_detail(e, limit=200)}


async def fetch_registry_by_address(
    address: str,
    realty_type: str | None = None,
    dong: str | None = None,
    ho: str | None = None,
) -> dict[str, Any]:
    """주소입력 → 1차 주소검색 → 2차 등기부 열람 2단계 통합 호출.

    한 주소에 여러 물건(토지·건물·집합건물 각 호)이 나오므로, 사용자가 고른
    부동산 구분·동·호에 맞는 물건을 공용 선택기로 고른다(무조건 첫 번째 금지).
    좁히지 못하면 조회는 계속하되 그 사실을 select_note로 정직하게 전달한다.
    """
    from app.services.registry.realty_kind import select_registry_item

    search_res = await search_by_simple_address(address)
    if not search_res.get("ok") or not search_res.get("items"):
        msg = search_res.get("message") or "주소 검색 결과가 없습니다."
        return {"address": address, "status": "no_match", "message": msg}

    picked, note = select_registry_item(search_res["items"], realty_type, dong, ho)
    uno = (picked or {}).get("unique_no")
    if not uno:
        return {"address": address, "status": "no_match", "message": "부동산 고유번호를 찾을 수 없습니다."}

    fetch_res = await fetch_realty_registry(unique_no=uno)
    fetch_res["address"] = address
    fetch_res["realty_gubun"] = (picked or {}).get("gubun")
    if note:
        fetch_res["select_note"] = note
    return fetch_res
