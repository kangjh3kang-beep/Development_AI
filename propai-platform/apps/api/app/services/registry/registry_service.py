"""부동산 등기부(소유관계) 연동 — 하이픈(Hyphen) 1순위 + Tilko & PDF 업로드 3단계 파이프라인.

기존 apick 및 CODEF 모듈은 사용 불가하여 완전 제거되었으며,
하이픈(Hyphen Data Market) API를 기본 1순위 공급자로 사용합니다.

파이프라인:
 1순위: 하이픈 (Hyphen) API (HYPHEN_HKEY, HYPHEN_USER_ID)
 2순위: 틸코 (Tilko) API (TILKO_API_KEY, IROS_USER_ID)
 3순위: 비상 등기부 PDF 직접 업로드 (parse_registry_pdf)
"""

from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _config() -> dict[str, str]:
    return {
        "url": (os.getenv("REGISTRY_API_URL") or "").strip(),
        "key": (os.getenv("REGISTRY_API_KEY") or "").strip(),
        "provider": (os.getenv("REGISTRY_PROVIDER") or "hyphen").strip().lower(),
    }


def is_configured() -> bool:
    from app.services.registry.hyphen_client import hyphen_ready
    from app.services.registry.tilko_client import tilko_ready

    cfg = _config()
    if cfg["provider"] == "tilko":
        return tilko_ready()
    # 기본은 hyphen
    return hyphen_ready() or tilko_ready() or bool(cfg["url"] and cfg["key"])


class RegistryService:
    def status(self) -> dict[str, Any]:
        from app.services.registry.hyphen_client import hyphen_ready
        from app.services.registry.tilko_client import tilko_ready

        cfg = _config()
        p = cfg["provider"]

        if p == "tilko":
            ok = tilko_ready()
            return {
                "configured": ok,
                "provider": "tilko",
                "register_ready": ok,
                "message": (
                    "Tilko 등기부 API 연결됨" if ok else "Tilko 미설정 — TILKO_API_KEY / IROS 자격 필요"
                ),
            }

        # 기본 하이픈 (hyphen)
        h_ok = hyphen_ready()
        t_ok = tilko_ready()
        return {
            "configured": h_ok or t_ok,
            "provider": "hyphen" if h_ok else ("tilko" if t_ok else "pdf_upload"),
            "register_ready": h_ok or t_ok,
            "hyphen_ready": h_ok,
            "tilko_ready": t_ok,
            "message": (
                "하이픈(Hyphen) 부동산 등기부 API 1순위 연결됨"
                if h_ok
                else (
                    "Tilko 보조 등기부 API 연결됨 (하이픈 미설정)"
                    if t_ok
                    else "상용 등기 API 미설정 — HYPHEN_HKEY & HYPHEN_USER_ID 필요 (비상 PDF 업로드 기능 이용 가능)"
                )
            ),
        }

    async def get_one(
        self,
        pnu: str | None = None,
        address: str | None = None,
        unique_no: str | None = None,
        pdf_input: bytes | str | None = None,
    ) -> dict[str, Any]:
        """단건 등기부 조회/발급/파싱.

        - pdf_input 전달 시: 비상 PDF 업로드 파서(parse_registry_pdf) 즉시 실행
        - 1순위: 하이픈 (Hyphen)
        - 2순위: 틸코 (Tilko)
        - 3순위: PDF 파싱 안내
        """
        item = {"pnu": pnu, "address": address, "unique_no": unique_no}

        # 3순위 (우선): 직접 전달된 PDF 파싱 처리
        if pdf_input:
            from app.services.registry.registry_pdf_parser import parse_registry_pdf

            res = parse_registry_pdf(pdf_input)
            return {**item, **res}

        from app.services.registry.hyphen_client import fetch_realty_registry, fetch_registry_by_address, hyphen_ready
        from app.services.registry.tilko_client import fetch_realty_registry as fetch_tilko_registry
        from app.services.registry.tilko_client import tilko_ready

        cfg = _config()
        p = cfg["provider"]

        # 1순위: 하이픈 (Hyphen)
        if (p == "hyphen" or not p) and hyphen_ready():
            if unique_no:
                h_res = await fetch_realty_registry(unique_no=unique_no)
            elif address:
                h_res = await fetch_registry_by_address(address=address)
            else:
                return {**item, "status": "bad_request", "message": "주소 또는 고유번호가 필요합니다."}

            if h_res.get("status") == "ok":
                return {**item, **h_res}

            logger.warning("하이픈 등기 조회 실패, 2순위 Tilko 폴백 시도", err=h_res.get("message"))

        # 2순위: 틸코 (Tilko)
        if tilko_ready():
            if unique_no:
                t_res = await fetch_tilko_registry(unique_no=unique_no)
                if t_res.get("ok"):
                    return {
                        **item,
                        "status": "ok",
                        "origin": "tilko",
                        "pdf_base64": t_res.get("pdf_data"),
                        "has_pdf": bool(t_res.get("pdf_data")),
                        "message": "Tilko 등기부 조회 성공",
                    }
            elif address:
                from app.services.registry.tilko_client import search_unique_no

                s_res = await search_unique_no(address)
                if s_res.get("ok") and s_res.get("items"):
                    uno = s_res["items"][0]["unique_no"]
                    t_res = await fetch_tilko_registry(unique_no=uno)
                    if t_res.get("ok"):
                        return {
                            **item,
                            "status": "ok",
                            "origin": "tilko",
                            "unique_no": uno,
                            "pdf_base64": t_res.get("pdf_data"),
                            "has_pdf": bool(t_res.get("pdf_data")),
                            "message": "Tilko 등기부 조회 성공",
                        }

        # 커스텀 URL 방식 (설정 시)
        if cfg["url"] and cfg["key"]:
            import httpx

            try:
                async with httpx.AsyncClient(timeout=40.0) as client:
                    resp = await client.post(
                        cfg["url"],
                        headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
                        json={"pnu": pnu, "address": address},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                return {
                    **item,
                    "status": "ok",
                    "origin": "custom",
                    "owner": data.get("owner"),
                    "summary": data.get("summary"),
                    "pdf_url": data.get("pdf_url"),
                    "raw": data,
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("커스텀 등기부 API 조회 실패", err=str(e)[:120])

        return {
            **item,
            "status": "not_configured",
            "message": "등기부 API(Hyphen/Tilko) 미설정 또는 장애 발생 — '비상 등기부 PDF 직접 업로드' 기능을 이용하세요.",
        }

    async def bulk(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """다필지 일괄 등기부 조회."""
        import asyncio

        if not items:
            return {"configured": is_configured(), "count": 0, "results": []}

        sem = asyncio.Semaphore(5)

        async def one(it: dict) -> dict:
            async with sem:
                return await self.get_one(pnu=it.get("pnu"), address=it.get("address"), unique_no=it.get("unique_no"))

        results = await asyncio.gather(*[one(it) for it in items])
        return {"configured": is_configured(), "count": len(results), "results": list(results)}
