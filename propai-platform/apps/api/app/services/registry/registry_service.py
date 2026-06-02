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

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _config() -> dict[str, str]:
    return {
        "url": (os.getenv("REGISTRY_API_URL") or "").strip(),
        "key": (os.getenv("REGISTRY_API_KEY") or "").strip(),
        "provider": (os.getenv("REGISTRY_PROVIDER") or "custom").strip(),
    }


def is_configured() -> bool:
    c = _config()
    return bool(c["url"] and c["key"])


class RegistryService:
    def status(self) -> dict[str, Any]:
        c = _config()
        return {
            "configured": is_configured(),
            "provider": c["provider"] if is_configured() else None,
            "message": (
                f"등기부 발급 API 연결됨({c['provider']})"
                if is_configured()
                else "등기부 발급 API 미설정 — REGISTRY_API_URL·REGISTRY_API_KEY 설정 시 활성화. "
                     "(대법원 IROS는 공개 API 없음 → CODEF 등 상용 등기부 API 키 필요, 발급 건당 과금)"
            ),
        }

    async def get_one(self, pnu: str | None = None, address: str | None = None) -> dict[str, Any]:
        """단건 등기부 조회/발급. 미설정 시 not_configured."""
        c = _config()
        item = {"pnu": pnu, "address": address}
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
        return {"configured": True, "provider": _config()["provider"],
                "count": len(results), "results": list(results)}
