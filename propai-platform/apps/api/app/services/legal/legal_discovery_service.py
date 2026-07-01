"""LLM 관련법령 탐색 + 정본(LegalHub) 교차검증 서비스.

정적 레지스트리(66법령)는 유한 — 부지/개발 맥락의 '관련·핵심 법령'을 LLM이 검색·식별하고,
그 결과를 LegalHub(정본)로 **교차검증**한다.

★정직성 게이트(무날조): build_law_url은 어떤 법령명이든 law.go.kr 한글주소를 '구성'하므로,
호스트만으로는 법령 실존을 검증하지 못한다. 따라서 신뢰 판정 기준은 **정본 레지스트리 등재 여부**다.
  - 정본 등재(registry_key 有)  → verified_ssot (검증된 링크·근거)
  - 정본 미등재(LLM 식별)        → llm_unverified (검증 권고 · 링크는 '구성된 추정')
  - 법령명 없음/해석 불가         → drop (가짜 인용 차단)

→ 커버리지 확장(LLM)과 정직(정본 게이트)을 동시에 달성. trust.cross_validate와 같은 결을 법령에 적용.
"""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.services.legal import legal_reference_registry as _reg
from app.services.legal.legal_hub import LegalHub

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "당신은 대한민국 부동산개발 인허가 법무 전문가입니다. 주어진 부지/개발 맥락에 '실제로 적용되는' "
    "대한민국 법령·조례·고시를 식별하세요. 존재하지 않는 법령·조문을 지어내지 마세요(불확실하면 제외). "
    "법령(국회 제정법·시행령·시행규칙), 조례(자치법규), 고시(국가/지자체가 법령 위임으로 발한 행정규칙 — "
    "예: 분양가상한제 산정 고시, 건축물 에너지효율등급 인증 고시, 지구단위계획 결정고시)를 모두 포함하세요. "
    "정확한 정식명칭과 조문(고시는 조문 생략 가능)을 쓰세요. 출력은 JSON 배열만:\n"
    '[{"law":"정확한 정식명칭","article":"제N조","category":"법령|조례|고시","reason":"적용 이유(한국어 1문장)",'
    '"importance":"core|related","confidence":0.0~1.0}]'
)
_TMPL = "## 부지/개발 맥락\n{context}\n\n위 맥락에 적용되는 핵심(core)·관련(related) 법령을 중요도순으로 최대 15개. JSON 배열만 출력."


class LegalDiscoveryService:
    """LLM 법령탐색 → 정본 교차검증."""

    async def discover(self, context: dict[str, Any]) -> dict[str, Any]:
        """맥락 → {core_laws, related_laws, cross_validation, disclosure, generated}."""
        raw = await self._llm_search(context)
        validated = [v for v in (self._crossvalidate(it) for it in raw) if v]
        core = [v for v in validated if v["importance"] == "core"]
        related = [v for v in validated if v["importance"] != "core"]
        registered = sum(1 for v in validated if v.get("registry_key"))
        gosi_n = sum(1 for v in validated if v.get("category") == "고시")
        # 지역 고시(도시관리계획 결정·지형도면·실시계획인가) 토지이음 deep-link 동반(시군구 스코프).
        sido = context.get("sido")
        sigungu = context.get("sigungu") or context.get("sigungu_name")
        regional = LegalHub.regional_gosi(sido, sigungu) if (sido or sigungu) else None
        return {
            "core_laws": core,
            "related_laws": related,
            "regional_gosi": regional,  # 부지 시군구 고시정보 열람 링크(토지이음)
            "cross_validation": {
                "total": len(validated),
                "verified_ssot": registered,
                "llm_unverified": len(validated) - registered,
                "gosi_identified": gosi_n,
            },
            "disclosure": (
                "LLM이 식별한 관련 법령을 법령 정본(LegalHub)으로 교차검증했습니다. "
                "verified_ssot=정본 등재(law.go.kr 검증 링크·근거), llm_unverified=정본 미등재 LLM 식별"
                "(링크는 구성된 추정 — 확인 권고). 해석 불가 인용은 제외했습니다(가짜 링크 금지)."
            ),
            "generated": bool(raw),
        }

    def _crossvalidate(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """LLM 1건 → 정본 대조(카테고리별 라우팅). 법령명 없으면 drop(가짜 인용 차단).

        법령 → LegalHub.by_article(정본 등재 시 verified_ssot). 조례/고시 → 카테고리별 검증 링크 구성
        (정본 개념키가 없으므로 llm_unverified=검증권고). 신뢰 게이트는 정본 등재 여부(호스트만으론 실존 미검증).
        """
        law = (item.get("law") or "").strip()
        if not law:
            return None
        article = item.get("article")
        category = (item.get("category") or "법령").strip()
        registry_key: str | None = None
        if category == "고시":
            url = _reg.build_admrule_url(law)
            art = ""
        elif category == "조례":
            url = _reg.build_ordinance_url(law)
            art = ""
        else:  # 법령(기본)
            # ★다중 조문 분리(LLM이 "제76조, 제77조, 제78조"처럼 묶어 반환) — 각각 정본 대조해 하나라도
            #   등재되면 verified_ssot로 인정(해당 매칭 조문·개념키 채택). 정본 매칭 정확도↑.
            arts = [a.strip() for a in re.split(r"[,/·;]|및|과|와", str(article or "")) if a.strip()]
            rec = LegalHub.by_article(law, article)  # 원본(단일/첫시도) 기본
            for a in arts:
                r = LegalHub.by_article(law, a)
                if r.get("key"):
                    rec = r
                    break
            registry_key = rec.get("key")
            url = rec.get("url")
            art = rec.get("article") or (arts[0] if arts else (article or ""))
        return {
            "law": law,
            "article": art,
            "category": category if category in ("법령", "조례", "고시") else "법령",
            "reason": item.get("reason", ""),
            "importance": "core" if item.get("importance") == "core" else "related",
            "confidence": item.get("confidence"),
            "url": url,
            "url_status": "verified" if _reg._is_trusted_legal_host(url) else "pending",
            # ★신뢰 판정은 '정본 등재' 여부 기준(법령만 개념키 보유). 조례/고시는 검증권고.
            "verification": "verified_ssot" if registry_key else "llm_unverified",
            "registry_key": registry_key,
        }

    async def _llm_search(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from app.services.ai.base_interpreter import GROUNDING_RULE, record_llm_response_billing
            from app.services.ai.llm_provider import get_llm

            ctx = json.dumps(context, ensure_ascii=False, indent=2)
            llm = get_llm(timeout=60, max_tokens=2000)
            resp = await llm.ainvoke([
                SystemMessage(content=_SYSTEM + GROUNDING_RULE),
                HumanMessage(content=_TMPL.format(context=ctx)),
            ])
            await record_llm_response_billing(llm, resp, service="legal_discovery")
            raw = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                raw = raw[4:] if raw.lower().startswith("json") else raw
            data = json.loads(raw.strip())
            return data if isinstance(data, list) else []
        except Exception as e:  # noqa: BLE001 — LLM 실패는 빈 결과(graceful·무목업).
            logger.warning("법령탐색 LLM 실패", err=f"{type(e).__name__}: {str(e)[:120]}")
            return []
