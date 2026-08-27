"""고시(告示) 원문 검색 — 전수 다운로드 없이 '타깃 검색'.

사용자 과제: 고시 원문이 첨부파일(PDF/HWP)로 올라가 있어 전부 다운로드할 수 없고, 내용 서칭이 어렵다.

해법(다운로드 최소화):
 ① 국가 고시(행정규칙) — 법제처 DRF API(target=admrul)가 **본문 텍스트를 직접 반환**한다.
    파일 다운로드 없이 키워드로 검색·발췌(search_content). 가장 깔끔한 경로.
 ② 지역 고시(도시관리계획 결정·지형도면·실시계획인가 — 토지이음 첨부 PDF) — 부지가 실제 참조하는
    '그 고시 1건만' on-demand로 받아 fitz(PyMuPDF)로 텍스트 추출(extract_attachment_text).
    전수 인덱싱 금지, 부지 트리거 시 lazy 추출.
무날조: 실제 결과만, 키 미설정·미확보는 정직 표기(가짜 본문 금지).
"""
from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

from app.core.config import settings
from app.services.legal.moleg_drf_envelope import MolegDrfError, raise_unless_expected

logger = structlog.get_logger(__name__)

_DRF = "http://www.law.go.kr/DRF"
_HEADERS = {"User-Agent": "PropAI/1.0 (https://4t8t.net)"}


def _collect_admrule_text(svc: Any) -> str:
    """AdmRulService 응답의 조문 본문을 평탄 텍스트로(법제처 필드명 변형 방어)."""
    if not isinstance(svc, dict):
        return ""
    parts: list[str] = []
    for k in ("조문내용", "조문", "조", "조문정보", "본문"):
        v = svc.get(k)
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            for e in v:
                if isinstance(e, str):
                    parts.append(e)
                elif isinstance(e, dict):
                    parts.append(" ".join(str(x) for x in e.values() if isinstance(x, str)))
        elif isinstance(v, dict):
            parts.append(" ".join(str(x) for x in v.values() if isinstance(x, str)))
    return "\n".join(p for p in parts if p).strip()


def _excerpts(text: str, query: str, ctx: int = 200, limit: int = 3) -> list[str]:
    """본문에서 질의어 주변 발췌(키워드 매칭). 전수 다운로드 없이 '내용 서칭' 핵심."""
    if not text or not query:
        return []
    terms = [t for t in re.split(r"\s+", query.strip()) if len(t) >= 2]
    out: list[str] = []
    for t in terms:
        i = text.find(t)
        if i >= 0:
            s = max(0, i - ctx)
            e = min(len(text), i + len(t) + ctx)
            out.append(("…" if s > 0 else "") + text[s:e].strip() + ("…" if e < len(text) else ""))
        if len(out) >= limit:
            break
    return out


#: `search_admrule` 이 **실제로 파싱하는** 루트키 — 아래 파싱 루프·폴백과 1:1.
#: ★손 목록이 되지 않게 `tests/` 의 계약 테스트가 파싱 코드와 정합을 단언한다.
SEARCH_ROOT_KEYS: tuple[str, ...] = ("AdmRulSearch", "admRulSearch", "LawSearch", "admrulSearch", "admrul")
#: `fetch_admrule_text` 가 실제로 파싱하는 루트키.
TEXT_ROOT_KEYS: tuple[str, ...] = ("AdmRulService",)


class GosiSearchService:
    """고시 원문 타깃 검색(국가 행정규칙 본문 + 지역 첨부 on-demand)."""

    @staticmethod
    def _key() -> str:
        return getattr(settings, "MOLEG_API_KEY", "") or ""

    async def search_admrule(self, query: str, *, max_results: int = 5) -> dict[str, Any]:
        """국가 고시(행정규칙) 검색 — 법제처 DRF target=admrul. → {available, results:[{name,id,dept,date}]}."""
        key = self._key()
        if not key:
            return {"available": False, "reason": "MOLEG_API_KEY 미설정(법제처)", "results": []}
        try:
            async with httpx.AsyncClient(timeout=12.0, headers=_HEADERS) as c:
                r = await c.get(f"{_DRF}/lawSearch.do", params={
                    "OC": key, "target": "admrul", "type": "JSON",
                    "query": query, "display": str(max_results), "sort": "date"})
                r.raise_for_status()
                data = r.json()
            # ★법제처는 **오류도 HTTP 200** 으로 준다 — `raise_for_status()` 가 못 잡는다.
            #   종전에는 이 봉투가 루트키 매칭에 실패해 `results=[]` 로 흘러
            #   **`available=True`(=조회 성공·결과 0건)** 로 보고됐고,
            #   `basic_building_cost.detect_gosi_update` 가 그것을 받아
            #   **"확인했고 고시가 안 바뀌었다"** 고 단정했다(2026-08-27 라이브 실측).
            raise_unless_expected(data, expect=SEARCH_ROOT_KEYS)
        except MolegDrfError as e:
            logger.warning("법제처 DRF 오류 봉투(200)", err=str(e)[:160])
            return {"available": False, "reason": f"법제처 인증/권한 오류: {e}", "results": []}
        except Exception as e:  # noqa: BLE001
            logger.warning("법제처 고시 검색 실패", err=f"{type(e).__name__}: {str(e)[:120]}")
            return {"available": False, "reason": "법제처 API 호출 실패", "results": []}
        # 법제처 DRF 응답 루트키 방어(JSON 구조 변형: AdmRulSearch/admRulSearch/LawSearch …).
        root = {}
        for rk in ("AdmRulSearch", "admRulSearch", "LawSearch", "admrulSearch"):
            if isinstance(data.get(rk), dict):
                root = data[rk]
                break
        items = root.get("admrul") or root.get("law") or data.get("admrul") or []
        if isinstance(items, dict):
            items = [items]
        if not items:
            # 진단: 빈 결과 시 실제 최상위/루트 키를 노출(라이브 구조 파악·무목업 정직).
            logger.info("법제처 고시 검색 0건", query=query, top_keys=list(data.keys())[:6],
                        root_keys=list(root.keys())[:8] if root else [])
        results = []
        for it in items[:max_results]:
            name = it.get("행정규칙명") or it.get("법령명한글")
            if not name:
                continue
            results.append({
                "name": name,
                "id": it.get("행정규칙일련번호") or it.get("행정규칙ID") or it.get("ID"),
                "dept": it.get("소관부처명"),
                "date": it.get("발령일자") or it.get("시행일자"),
                "link": it.get("행정규칙상세링크"),
            })
        return {"available": True, "query": query, "results": results}

    async def fetch_admrule_text(self, admrul_id: str | None) -> dict[str, Any]:
        """행정규칙 본문 텍스트(파일 다운로드 없이). → {found, name, text}."""
        key = self._key()
        if not key or not admrul_id:
            return {"found": False, "text": ""}
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as c:
                r = await c.get(f"{_DRF}/lawService.do", params={
                    "OC": key, "target": "admrul", "type": "JSON", "ID": str(admrul_id)})
                r.raise_for_status()
                data = r.json()
            raise_unless_expected(data, expect=TEXT_ROOT_KEYS)
        except MolegDrfError as e:
            # ★종전에는 이 예외가 아래 `except Exception` 에 삼켜져 **종전과 바이트 동일한**
            #   `{"found": False, "text": ""}` 을 돌려줬다 — 배선을 해 놓고 **관측 계약이
            #   전혀 안 바뀌어서**, 소비처(`search_content`)가 *"본문을 읽었는데 키워드가 없다"* 와
            #   *"본문을 못 읽었다"* 를 **구별할 수 없었다**(독립 리뷰 ①).
            #   사유를 **반환값에** 싣는다 — 로그는 사용자에게 닿지 않는다.
            logger.warning("법제처 고시 본문 실패(200-봉투)", err=str(e)[:160])
            return {"found": False, "text": "", "reason": f"법제처 조회 실패: {e}"}
        except Exception as e:  # noqa: BLE001
            logger.warning("법제처 고시 본문 실패", err=f"{type(e).__name__}: {str(e)[:120]}")
            return {"found": False, "text": "", "reason": f"법제처 호출 실패: {type(e).__name__}"}
        svc = data.get("AdmRulService") or {}
        text = _collect_admrule_text(svc)
        name = svc.get("행정규칙명") if isinstance(svc, dict) else None
        return {"found": bool(text), "name": name, "text": text}

    async def search_content(self, query: str, *, max_results: int = 3) -> dict[str, Any]:
        """고시 검색 + 상위 N건 본문에서 질의어 발췌(전수 다운로드 X). 사용자 '내용 서칭' 직접 해법."""
        listing = await self.search_admrule(query, max_results=max_results)
        if not listing.get("available"):
            return {**listing, "matches": []}
        matches = []
        for item in listing["results"]:
            body = await self.fetch_admrule_text(item.get("id"))
            matches.append({**item, "excerpts": _excerpts(body.get("text", ""), query), "has_text": body.get("found")})
        return {
            "available": True, "query": query, "matches": matches,
            "note": "법제처 행정규칙(고시) 본문 검색(파일 다운로드 없이). 지역 도시관리계획 결정고시는 토지이음 고시정보 또는 extract_attachment_text로 부지 트리거 시 1건씩 추출.",
        }

    @staticmethod
    async def extract_attachment_text(url: str) -> dict[str, Any]:
        """지역 고시 첨부(PDF) 1건 on-demand 텍스트 추출(fitz). 부지 트리거 시만 — 전수 다운로드 금지."""
        if not url:
            return {"found": False, "text": ""}
        try:
            async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as c:
                r = await c.get(url)
                r.raise_for_status()
            import fitz  # PyMuPDF
            doc = fitz.open(stream=r.content, filetype="pdf")
            text = "\n".join(p.get_text() for p in doc)
            doc.close()
            return {"found": bool(text.strip()), "text": text}
        except Exception as e:  # noqa: BLE001
            logger.warning("고시 첨부 추출 실패", err=f"{type(e).__name__}: {str(e)[:120]}")
            return {"found": False, "text": ""}
