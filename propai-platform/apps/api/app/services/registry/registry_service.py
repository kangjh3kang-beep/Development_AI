"""부동산 등기부(소유관계) 연동 — 공급자 무관 설정형 + 다필지 일괄 발급/조회.

대법원 인터넷등기소(IROS)는 공개 REST API가 없으므로, 상용 등기부 발급/조회 API
(예: CODEF·이지등기 등)를 환경변수로 연결한다. 키 미설정 시 'not_configured'를
반환하며(가짜 데이터 금지), 설정되면 단건·다필지 일괄 조회/다운로드를 수행한다.

환경변수:
- REGISTRY_API_URL   : 공급자 등기부 조회 엔드포인트(POST)
- REGISTRY_API_KEY   : 인증 키(Bearer)
- REGISTRY_PROVIDER  : 표기용 공급자명(선택, 기본 'custom')
요청 본문은 {pnu, address}를 전송하고, 응답에서 owner/summary/pdf_url 등을 표준화한다.
"""

import base64
import os
import time
import urllib.parse
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _config() -> dict[str, str]:
    return {
        "url": (os.getenv("REGISTRY_API_URL") or "").strip(),
        "key": (os.getenv("REGISTRY_API_KEY") or "").strip(),
        "provider": (os.getenv("REGISTRY_PROVIDER") or "custom").strip(),
    }


def _codef_cfg() -> dict[str, str]:
    return {
        "cid": (os.getenv("CODEF_CLIENT_ID") or "").strip(),
        "secret": (os.getenv("CODEF_CLIENT_SECRET") or "").strip(),
        "pubkey": (os.getenv("CODEF_PUBLIC_KEY") or "").strip(),
        "host": (os.getenv("CODEF_API_HOST") or "https://development.codef.io").strip(),
        "path": (os.getenv("CODEF_REGISTER_PATH") or "/v1/kr/public/ck/real-estate-register/status").strip(),
        # 부동산등기 열람/발급 필수 값
        "phone": (os.getenv("CODEF_PHONE_NO") or "").strip(),
        "password": (os.getenv("CODEF_PASSWORD") or "").strip(),  # 4자리 숫자(RSA 암호화됨)
        "eprepay_no": (os.getenv("CODEF_EPREPAY_NO") or "").strip(),  # 전자선납금 12자리
        "eprepay_pass": (os.getenv("CODEF_EPREPAY_PASS") or "").strip(),
        "issue_type": (os.getenv("CODEF_ISSUE_TYPE") or "1").strip(),  # 0발급 1열람
        "realty_type": (os.getenv("CODEF_REALTY_TYPE") or "").strip(),
    }


def _codef_register_ready() -> tuple[bool, list[str]]:
    """부동산등기 열람/발급에 필요한 설정 충족 여부 + 누락 목록."""
    c = _codef_cfg()
    missing = []
    if not c["pubkey"]:
        missing.append("CODEF_PUBLIC_KEY(비밀번호 RSA 암호화용)")
    if not c["password"]:
        missing.append("CODEF_PASSWORD(4자리 숫자)")
    if not c["phone"]:
        missing.append("CODEF_PHONE_NO(전화번호)")
    # issueType<2(발급/열람)는 전자선납금 필수
    if c["issue_type"] in ("0", "1"):
        if not c["eprepay_no"]:
            missing.append("CODEF_EPREPAY_NO(전자선납금 번호)")
        if not c["eprepay_pass"]:
            missing.append("CODEF_EPREPAY_PASS(전자선납금 비밀번호)")
    return (len(missing) == 0, missing)


def _is_codef() -> bool:
    c = _codef_cfg()
    return bool(c["cid"] and c["secret"])


def is_configured() -> bool:
    c = _config()
    return bool(c["url"] and c["key"]) or _is_codef()


# ── CODEF OAuth 토큰(모듈 캐시, 7일 유효) ──
_codef_token_cache: dict[str, Any] = {"token": None, "exp": 0.0}


async def _codef_token() -> str | None:
    import httpx

    c = _codef_cfg()
    if not (c["cid"] and c["secret"]):
        return None
    now = time.time()
    if _codef_token_cache["token"] and _codef_token_cache["exp"] > now + 120:
        return _codef_token_cache["token"]
    basic = base64.b64encode(f"{c['cid']}:{c['secret']}".encode()).decode()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            "https://oauth.codef.io/oauth/token",
            params={"grant_type": "client_credentials", "scope": "read"},
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        d = resp.json()
    tok = d.get("access_token")
    _codef_token_cache["token"] = tok
    _codef_token_cache["exp"] = now + int(d.get("expires_in", 600))
    return tok


def _codef_encrypt(plain: str) -> str | None:
    """CODEF 민감필드 RSA 암호화(공개키 PKCS1 v1.5 → base64). 필요 시 사용."""
    c = _codef_cfg()
    if not c["pubkey"] or not plain:
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.serialization import load_der_public_key

        key = load_der_public_key(base64.b64decode(c["pubkey"]))
        enc = key.encrypt(plain.encode("utf-8"), padding.PKCS1v15())  # type: ignore[arg-type]
        return base64.b64encode(enc).decode()
    except Exception as e:  # noqa: BLE001
        logger.warning("CODEF RSA 암호화 실패", err=str(e)[:80])
        return None


async def _codef_request(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """CODEF API 호출 — Bearer 토큰 + URL인코딩 응답 디코드."""
    import httpx

    tok = await _codef_token()
    if not tok:
        return {"result": {"code": "TOKEN_FAIL", "message": "OAuth 토큰 발급 실패"}}
    c = _codef_cfg()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{c['host']}{path}",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            content=__import__("json").dumps(body, ensure_ascii=False).encode("utf-8"),
        )
    text = resp.text or ""
    # CODEF 응답은 URL 인코딩된 JSON 문자열
    try:
        decoded = urllib.parse.unquote_plus(text)
        return __import__("json").loads(decoded)
    except Exception:  # noqa: BLE001
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {"result": {"code": "PARSE_FAIL", "message": text[:300]}}


class RegistryService:
    def status(self) -> dict[str, Any]:
        if (os.getenv("REGISTRY_PROVIDER") or "").strip().lower() == "apick":
            from app.services.registry.apick_client import apick_ready
            ok = apick_ready()
            return {"configured": ok, "provider": "apick", "register_ready": ok,
                    "message": ("apick 등기부 API 연결됨(주소 직접·고객 등기소 계정 불필요)" if ok
                                else "apick 미설정 — APICK_CL_AUTH_KEY 필요")}
        if _is_codef():
            cc = _codef_cfg()
            ready, missing = _codef_register_ready()
            return {"configured": True, "provider": "codef",
                    "host": cc["host"], "register_path": cc["path"],
                    "auth_ok": True, "register_ready": ready, "missing": missing,
                    "message": (f"CODEF 등기부 API 연결됨(host={cc['host']})"
                                if ready else
                                "CODEF 인증은 연결됨 — 부동산등기 발급에 추가 설정 필요: " + ", ".join(missing))}
        c = _config()
        return {
            "configured": is_configured(),
            "provider": c["provider"] if is_configured() else None,
            "message": (
                f"등기부 발급 API 연결됨({c['provider']})"
                if is_configured()
                else "등기부 발급 API 미설정 — REGISTRY_API_URL·REGISTRY_API_KEY 또는 CODEF_* 설정 시 활성화. "
                     "(대법원 IROS는 공개 API 없음 → CODEF 등 상용 등기부 API 키 필요, 발급 건당 과금)"
            ),
        }

    async def get_one(self, pnu: str | None = None, address: str | None = None,
                      realty_type: str | None = None, dong: str | None = None,
                      ho: str | None = None) -> dict[str, Any]:
        """단건 등기부 조회/발급. 미설정 시 not_configured. 집합건물은 realty_type=1+dong/ho."""
        item = {"pnu": pnu, "address": address}
        # apick 공급자(REGISTRY_PROVIDER=apick) — 주소 직접·고객 등기소 계정 불필요.
        if (os.getenv("REGISTRY_PROVIDER") or "").strip().lower() == "apick":
            from app.services.registry.apick_client import apick_ready, fetch_registry
            if apick_ready():
                return await fetch_registry(address=address, realty_type=realty_type)
            return {**item, "status": "not_configured", "message": "apick 인증키(APICK_CL_AUTH_KEY) 미설정"}
        if _is_codef():
            return await self._codef_one(pnu, address, realty_type, dong, ho)
        c = _config()
        if not is_configured():
            return {**item, "status": "not_configured",
                    "message": "등기부 발급 API 키 미설정"}
        import httpx

        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                resp = await client.post(
                    c["url"],
                    headers={"Authorization": f"Bearer {c['key']}", "Content-Type": "application/json"},
                    json={"pnu": pnu, "address": address},
                )
                resp.raise_for_status()
                data = resp.json()
            # 공급자 응답 표준화(키 명칭은 공급자별 상이 — 흔한 키를 폭넓게 수용)
            return {
                **item,
                "status": "ok",
                "owner": data.get("owner") or data.get("owner_name") or data.get("소유자"),
                "owner_count": data.get("owner_count") or data.get("소유자수"),
                "share": data.get("share") or data.get("지분"),
                "mortgage": data.get("mortgage") or data.get("근저당") or data.get("을구"),
                "summary": data.get("summary") or data.get("요약"),
                "pdf_url": data.get("pdf_url") or data.get("pdfUrl") or data.get("download_url"),
                "raw": data if len(str(data)) < 4000 else None,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("등기부 조회 실패", err=str(e)[:120])
            return {**item, "status": "error", "message": str(e)[:200]}

    async def _codef_one(self, pnu: str | None, address: str | None,
                         realty_type: str | None = None, dong: str | None = None,
                         ho: str | None = None) -> dict[str, Any]:
        """CODEF 부동산등기부등본 열람/발급 — 2-way(추가인증) 비동기 흐름.

        1차: 간편검색(주소) → CF-03002(continue2Way)+주소목록 →
        2차: is2Way+twoWayInfo+선택 uniqueNo → 최종(PDF BASE64+등기내용).
        ★전자선납금·열람/발급은 건당 과금. 필수 설정 미충족 시 호출하지 않음.
        """
        item = {"pnu": pnu, "address": address}
        ready, missing = _codef_register_ready()
        if not ready:
            return {**item, "status": "config_incomplete",
                    "message": "부동산등기 발급 설정 미완료 — 다음 값 필요: " + ", ".join(missing)}
        c = _codef_cfg()
        enc_pw = _codef_encrypt(c["password"])
        if not enc_pw:
            return {**item, "status": "config_incomplete", "message": "비밀번호 RSA 암호화 실패(CODEF_PUBLIC_KEY 확인)"}

        # 1차 요청(간편검색): 주소 문자열로 검색
        base: dict[str, Any] = {
            "organization": "0002",
            "phoneNo": c["phone"],
            "password": enc_pw,
            "inquiryType": "1",          # 간편검색
            "address": address or "",
            "issueType": c["issue_type"],  # 1:열람(기본)
            "ePrepayNo": c["eprepay_no"],
            "ePrepayPass": c["eprepay_pass"],
            "registerSummaryYN": "1",     # 등기사항 요약 출력
            "jointMortgageJeonseYN": "0",
            "tradingYN": "0",
        }
        # 부동산 구분: 요청값 > env 기본
        rt = realty_type or c["realty_type"]
        if rt:
            base["realtyType"] = rt
        # 집합건물(realtyType=1)은 동/호로 특정 호 등기 조회
        if rt == "1":
            if dong:
                base["dong"] = dong
            if ho:
                base["ho"] = ho

        try:
            data = await _codef_request(c["path"], base)
        except Exception as e:  # noqa: BLE001
            return {**item, "status": "error", "message": str(e)[:200]}

        result = data.get("result") or {}
        code = result.get("code")
        d = data.get("data") or {}

        # 추가인증(2-way) 필요 시: 주소목록에서 첫 부동산 고유번호 선택해 2차 요청
        if code == "CF-03002" or d.get("continue2Way"):
            addr_list = ((d.get("extraInfo") or {}).get("resAddrList")) or d.get("resAddrList") or []
            if not addr_list:
                return {**item, "status": "no_match",
                        "message": "해당 주소의 부동산을 찾지 못했습니다(주소 정밀화 필요)."}
            chosen = addr_list[0]
            unique_no = chosen.get("commUniqueNo")
            two = {
                "jobIndex": d.get("jobIndex"), "threadIndex": d.get("threadIndex"),
                "jti": d.get("jti"), "twoWayTimestamp": d.get("twoWayTimestamp"),
            }
            second = {**base, "is2Way": True, "twoWayInfo": two, "uniqueNo": unique_no}
            try:
                data = await _codef_request(c["path"], second)
            except Exception as e:  # noqa: BLE001
                return {**item, "status": "error", "message": f"2차 요청 실패: {str(e)[:160]}"}
            result = data.get("result") or {}
            code = result.get("code")
            d = data.get("data") or {}

        if code not in ("CF-00000", None):
            return {**item, "status": "provider_error", "code": code,
                    "message": result.get("message")}

        # 응답 표준화
        rows = d if isinstance(d, list) else [d]
        first = rows[0] if rows else {}
        owner = (first.get("resAddrList") or [{}])[0].get("resUserNm") if first.get("resAddrList") else None
        summary_office = None
        entries = first.get("resRegisterEntriesList") or []
        if entries:
            owner = owner or entries[0].get("resRealty")
            summary_office = entries[0].get("commCompetentRegistryOffice")
        return {
            **item, "status": "ok", "code": code,
            "issued": first.get("resIssueYN"),
            "owner": owner,
            "registry_office": summary_office,
            "doc_title": (entries[0].get("resDocTitle") if entries else None),
            "entries": entries,  # 등기사항 전체(갑구·을구·요약) — 권리분석용
            "addr_list": first.get("resAddrList") or [],
            "pdf_base64": first.get("resOriGinalData") or None,  # PDF BASE64
            "has_pdf": bool(first.get("resOriGinalData")),
            "summary": result.get("message"),
        }

    async def bulk(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """다필지 일괄 등기부 조회/발급."""
        import asyncio

        if not items:
            return {"configured": is_configured(), "count": 0, "results": []}
        if not is_configured():
            return {
                "configured": False,
                "count": len(items),
                "results": [{"pnu": it.get("pnu"), "address": it.get("address"),
                             "status": "not_configured"} for it in items],
                "message": self.status()["message"],
            }
        sem = asyncio.Semaphore(5)

        async def one(it: dict) -> dict:
            async with sem:
                return await self.get_one(pnu=it.get("pnu"), address=it.get("address"))

        results = await asyncio.gather(*[one(it) for it in items])
        provider = "codef" if _is_codef() else _config()["provider"]
        return {"configured": True, "provider": provider,
                "count": len(results), "results": list(results)}
