"""전문가 패널 + 검증 서비스 (다관점 분석·토론·통합).

분석 결과/맥락을 입력받아, 분석 유형별 관련 전문가(설계사·디벨로퍼·인허가공무원·
도시개발·지구단위·부동산학교수·법률가·정비전문가 등) 관점에서 분석하고 쟁점을
토론한 뒤 통합 결론과 검증(반론·리스크·신뢰도)을 제시한다.

- mode="single": 1회 LLM 호출(빠름·저렴, 기본). 다관점+토론+검증을 구조화 출력.
- mode="deep": 전문가별 병렬 LLM + 통합·검증 호출(정밀·고비용).
LLM 실패 시 graceful 폴백.
"""

import asyncio
import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 분석 유형별 전문가 배치
ROSTERS: dict[str, list[dict[str, str]]] = {
    "permit": [
        {"role": "인허가 행정공무원", "lens": "인허가 절차·행정 처리 가능성·민원 관점"},
        {"role": "건축사", "lens": "건축법·설계 적합성·기술적 실현 가능성"},
        {"role": "정비사업 전문가", "lens": "정비·소규모정비 사업성·조합/주민 동의 관점"},
        {"role": "부동산 법률가", "lens": "법적 리스크·소송·권리관계 관점"},
        {"role": "디벨로퍼", "lens": "사업 수익성·일정·리스크 관점"},
    ],
    "regulation": [
        {"role": "도시계획 전문가", "lens": "상위계획 정합성·용도지역·도시관리계획 관점"},
        {"role": "지구단위계획 전문가", "lens": "지구단위·인센티브·공공기여 관점"},
        {"role": "인허가 행정공무원", "lens": "조례 적용·행정 재량·심의 관점"},
        {"role": "부동산 법률가", "lens": "규제 충돌·법적 제약·구제수단 관점"},
    ],
    "market": [
        {"role": "부동산학 교수", "lens": "시장 구조·수급·가격 형성 이론 관점"},
        {"role": "디벨로퍼", "lens": "실수요·분양성·타이밍 관점"},
        {"role": "감정평가사", "lens": "적정 시세·평가·담보가치 관점"},
        {"role": "분양마케팅 전문가", "lens": "수요층·분양전략·경쟁상품 관점"},
    ],
    "feasibility": [
        {"role": "디벨로퍼", "lens": "총사업비·수지·자금조달 관점"},
        {"role": "PF 금융 전문가", "lens": "대출가능성·금융구조·리스크 관점"},
        {"role": "시공/적산 전문가", "lens": "공사비·공기·시공 리스크 관점"},
        {"role": "부동산학 교수", "lens": "투자수익·민감도·시장 사이클 관점"},
    ],
    "site": [
        {"role": "도시개발 전문가", "lens": "입지·개발 잠재력·기반시설 관점"},
        {"role": "건축사", "lens": "용도지역 한도·배치·설계 가능성 관점"},
        {"role": "디벨로퍼", "lens": "최유효이용·사업화 관점"},
        {"role": "감정평가사", "lens": "토지가치·공시지가·시세 관점"},
    ],
    "cost": [
        {"role": "시공/적산 전문가", "lens": "공종별 물량·단가·적산 정확성 관점"},
        {"role": "건설사업관리(CM)", "lens": "공기·공정·간접비·현장 리스크 관점"},
        {"role": "구조기술사", "lens": "구조형식·물량 합리성(콘크리트·철근) 관점"},
        {"role": "디벨로퍼", "lens": "총공사비 적정성·예비비·물가변동 관점"},
    ],
    "tax": [
        {"role": "세무사", "lens": "취득·보유·양도세율 적용·중과·감면 정확성 관점"},
        {"role": "회계사", "lens": "과세표준·세후 현금흐름·법인/개인 구조 관점"},
        {"role": "부동산 법률가", "lens": "세법 개정·해석·불복 리스크 관점"},
        {"role": "디벨로퍼", "lens": "세부담이 사업수지에 미치는 영향 관점"},
    ],
    "esg": [
        {"role": "LCA/탄소 전문가", "lens": "전과정평가(EN15978)·내재/운영 탄소 산정 관점"},
        {"role": "녹색건축 인증 심사원", "lens": "G-SEED·에너지효율·인증 기준 관점"},
        {"role": "ESG 금융 전문가", "lens": "K-택소노미·녹색금융·공시 관점"},
        {"role": "건축 설비기술사", "lens": "에너지·설비 성능·저감수단 관점"},
    ],
    "design": [
        {"role": "건축사", "lens": "배치·평면·법규 적합성·설계 품질 관점"},
        {"role": "구조기술사", "lens": "구조 합리성·시공성 관점"},
        {"role": "디벨로퍼", "lens": "분양성·평형구성·수익 최적화 관점"},
        {"role": "도시계획 전문가", "lens": "용도지역 한도·일조·인동간격 관점"},
    ],
}
_DEFAULT_ROSTER = [
    {"role": "디벨로퍼", "lens": "사업성·실현가능성 관점"},
    {"role": "부동산학 교수", "lens": "시장·이론 관점"},
    {"role": "부동산 법률가", "lens": "법적 리스크 관점"},
    {"role": "도시계획 전문가", "lens": "도시계획·규제 관점"},
]

_SUBJECTS = {
    "permit": "이 부지의 인허가 가능성·개발방식 분석",
    "regulation": "이 부지에 적용되는 규제 환경 분석",
    "market": "이 지역의 부동산 시장 분석",
    "feasibility": "이 사업의 사업성(수지) 분석",
    "site": "이 부지의 부지분석",
    "cost": "이 사업의 공사비·적산 분석",
    "tax": "이 사업의 부동산 조세 분석",
    "esg": "이 건축물의 ESG·탄소(전과정평가) 분석",
    "design": "이 부지의 건축 설계(배치·평형·법규) 분석",
}

_PANEL_SYSTEM = """\
당신은 부동산개발 전문가 패널의 진행자입니다. 주어진 분석 자료를 바탕으로 각 전문가가
자신의 전문 관점에서 독립적으로 검토하고, 핵심 쟁점을 토론한 뒤, 다관점을 통합한 최종
의견과 검증(반론·리스크·신뢰도)을 제시합니다.
원칙: 제공 데이터에 근거하고 과장·허위 금지. 전문가마다 관점 차이를 분명히 드러낼 것.
실효 한도와 법정 한도가 다를 때 그 원인은 자료의 [실효 한도 근거] 블록(far_basis)으로만
설명하라 — 근거 없이 '조례 실효치'로 단정하는 것을 금지한다(근거 부재 시 '근거 미확인' 표기).
반드시 JSON만 출력."""


def _effective_limit_note(context: dict[str, Any] | str) -> str:
    """실효 한도 근거 해설 블록 — /regulation/analyze 류 응답의 SSOT 통과키를 사람이 읽는
    한 문단으로 승격해 프롬프트 선두에 놓는다(무날조 — 존재하는 필드만 사용).

    왜 필요한가(실측 결함): 전체 결과 JSON은 아래 [:N] 절단을 거치는데 effective_far
    통과키(far_basis·구조상한)는 응답 뒤쪽이라 전문가 LLM에 도달하지 못했고, 전문가들이
    "실효 80% ≠ 법정 100%"의 원인을 조례로 오귀속했다(자연녹지 구조상한 = 건폐율 20%×
    최고 4층 = 80%, 조례 인하가 아님). 선두 삽입으로 절단과 무관하게 항상 생존시킨다.
    """
    if not isinstance(context, dict):
        return ""
    eff = context.get("effective_far")
    if not isinstance(eff, dict):
        return ""

    def _num(v: Any) -> float | None:
        # 외부 클라이언트가 임의 context를 보낼 수 있으므로(라우터 미검증 dict) 수치형만 수용 —
        # 문자열 값에 :g 포맷을 적용하면 ValueError→500 이 되는 것을 차단(R1 P2).
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    eff_far = _num(eff.get("effective_far_pct"))
    if eff_far is None:
        return ""
    limits = context.get("limits") if isinstance(context.get("limits"), dict) else {}
    far_slot = limits.get("far") if isinstance(limits.get("far"), dict) else {}
    legal_far = _num(far_slot.get("legal"))
    far_basis = eff.get("far_basis")
    lines = ["[실효 한도 근거 — SSOT]"]
    head = f"- 실효 용적률 {eff_far:g}%"
    if legal_far is not None:
        head += f" (법정 상한 {legal_far:g}%)"
    lines.append(head)
    if far_basis and "구조상한" in str(far_basis):
        cap = _num(eff.get("structural_cap_pct"))
        floors = _num(eff.get("floor_cap"))
        bcr = _num(eff.get("effective_bcr_pct"))
        formula = ""
        if bcr is not None and floors is not None and cap is not None:
            formula = f" — 건폐율 {bcr:g}% × 최고 {int(floors)}층 = {cap:g}%"
        lines.append(
            f"- 근거: {far_basis}{formula}. 조례가 낮춘 것이 아니라 층수 제한 때문에"
            " 실무상 도달 가능한 물리적 상한이다(법정 용적률 자체는 유지)."
        )
        basis_src = eff.get("floor_cap_basis")
        if basis_src:
            lines.append(f"- 층수 제한 근거: {basis_src}")
    elif far_basis:
        lines.append(f"- 근거: {far_basis}")
    else:
        lines.append("- 근거 필드 미제공 — 원인(조례/구조상한 등)을 단정하지 말 것.")
    return "\n".join(lines) + "\n\n"

_PANEL_TMPL = """\
## 분석 주제
{subject} — {address}

## 분석 자료(요약)
{context}

## 참여 전문가
{roster}

## 출력 JSON 스키마 (간결하게 — 각 문자열은 핵심만, 장황한 서술 금지)
{{
  "experts": [
    {{"role": "전문가명", "opinion": "해당 관점 핵심 의견(2문장 이내)",
      "key_points": ["근거·포인트 최대 2개"], "concerns": ["우려·이견 최대 2개"]}}
  ],
  "debate": [
    {{"issue": "쟁점", "positions": "전문가간 이견 요약(1문장)", "resolution": "토론 결과·절충(1문장)"}}
  ],
  "consensus": "다관점 통합 최종 의견(3문장 이내, 가장 합리적인 결론)",
  "recommended_actions": ["실행 권고 최대 3개"],
  "verification": {{
    "confidence": 0-100 정수(분석 신뢰도),
    "risks": ["검증상 핵심 리스크 최대 3개"],
    "counterpoints": ["주의해야 할 반론·맹점 최대 2개"],
    "data_gaps": ["추가 확인 필요 데이터 최대 2개"]
  }}
}}
전문가는 위 명단 그대로 분석하세요.
"""

_EXPERT_SYSTEM = """\
당신은 한국 부동산개발 분야의 해당 전문가입니다. 제시된 분석 자료를 당신의 전문 관점에서만
검토해 의견을 제시합니다. 데이터 근거·과장 금지. JSON만 출력."""

_EXPERT_TMPL = """\
## 당신의 역할: {role} ({lens})
## 분석 주제: {subject} — {address}
## 분석 자료(요약)
{context}

## 출력 JSON
{{"role": "{role}", "opinion": "당신 관점의 핵심 의견(2~3문장)",
  "key_points": ["근거 1~3개"], "concerns": ["우려·이견 1~2개"]}}
"""

_SYNTH_SYSTEM = """\
당신은 전문가 패널 진행자입니다. 각 전문가 의견을 종합해 쟁점을 정리하고, 다관점을
통합한 최종 결론과 검증(반론·리스크·신뢰도)을 제시합니다. 과장 금지. JSON만 출력."""

_SYNTH_TMPL = """\
## 분석 주제: {subject} — {address}
## 전문가 의견
{opinions}

## 출력 JSON 스키마
{{
  "debate": [{{"issue":"쟁점","positions":"이견 요약","resolution":"토론 결과"}}],
  "consensus": "다관점 통합 최종 의견(3~5문장)",
  "recommended_actions": ["실행 권고 2~4개"],
  "verification": {{"confidence": 0-100 정수, "risks":["1~3개"],
    "counterpoints":["1~3개"], "data_gaps":["0~3개"]}}
}}
"""


def _strip_json(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        raw = raw[4:] if raw.lower().startswith("json") else raw
    return raw.strip()


class ExpertPanelService:
    async def analyze(
        self,
        analysis_type: str,
        context: dict[str, Any] | str,
        address: str = "",
        mode: str = "single",
        skip_memory: bool = False,
    ) -> dict[str, Any]:
        roster = ROSTERS.get(analysis_type, _DEFAULT_ROSTER)
        subject = _SUBJECTS.get(analysis_type, "부동산개발 분석")

        # 1. RAG Recall (if not skipped)
        rag_memories = []
        if not skip_memory:
            try:
                from app.services.memory_hub.memory_service import get_memory_hub
                query_str = f"Subject: {subject}, Context: {str(context)[:200]}"
                memories = await get_memory_hub().recall_experience(query=query_str, domain=analysis_type, top_k=2)
                rag_memories = [
                    {"id": str(m.id), "summary": m.summary, "score": m.score}
                    for m in memories
                ]
            except Exception as e:
                logger.warning("expert panel memory recall 스킵", err=str(e)[:160])

        # Prepare context string and append recalled memories if present
        # ★회상 포맷은 공용 헬퍼 단일경유(specialist_agent와 동일 계약) — score None/비수치 안전(:.2f 오류 방지).
        # ★실효 한도 근거 블록을 '선두'에 삽입 — 아래 절단([:N])을 항상 생존해 far_basis 오귀속
        #   (구조상한 80%를 '조례 실효치'로 설명)을 차단한다. 필드 부재 시 빈 문자열(무날조).
        ctx_str = context if isinstance(context, str) else json.dumps(context, ensure_ascii=False)
        ctx_str = _effective_limit_note(context) + ctx_str
        if rag_memories:
            from app.services.memory_hub.recall_format import format_recall_block
            ctx_str += format_recall_block(rag_memories, header="[이전 유사 분석 및 참고 노하우]")

        # 6000자: 종전 4000자는 규제 결과 JSON 후반부(근거 통과키·evidence)를 통째로 잘랐다.
        # 근거 블록 선두 삽입과 별개로, 절단 여유를 완만히 상향(비용 영향 제한적).
        ctx_str = ctx_str[:6000]

        if mode in ("deep", "graph"):
            # LangGraph 일원화: 전문가(다각도) → 검증(원데이터 대조·할루시네이션 게이트) → 통합.
            try:
                from app.services.expert_panel.expert_panel_graph import run_panel_graph
                result = await run_panel_graph(subject, address, ctx_str, roster)
                if not (result and result.get("consensus")):
                    raise ValueError("graph 결과 없음")
            except Exception as e:  # noqa: BLE001
                logger.warning("전문가 패널(graph) 실패, deep 폴백: %s", str(e)[:100])
                result = await self._deep(subject, address, ctx_str, roster)
        else:
            result = await self._single(subject, address, ctx_str, roster)
        result["analysis_type"] = analysis_type
        result["mode"] = mode
        result["roster"] = [r["role"] for r in roster]
        if rag_memories:
            result["rag_memories"] = rag_memories

        # 2. RAG Ingestion (if not skipped)
        # WP-R4: degraded 폴백(generated=False)은 "일시적으로 제공되지 않습니다" 류 메시지라
        #   노하우 메모리로 적재하면 향후 RAG 회상을 오염시킨다 → generated 결과만 적재(정직).
        if not skip_memory and result.get("generated") and result.get("consensus"):
            try:
                import uuid

                from app.tasks.memory_tasks import dispatch_memory_ingest

                memory_summary = f"Expert Panel ({analysis_type}) 다관점 합의 요약:\n"
                memory_summary += f"- 주제: {subject}\n"
                memory_summary += f"- 합의 결론: {result['consensus']}\n"
                if result.get("verification", {}).get("risks"):
                    memory_summary += f"- 핵심 리스크: {', '.join(result['verification']['risks'])}\n"

                ingest_payload = {
                    "project_id": None,
                    "session_id": f"auto_panel_{analysis_type}_{uuid.uuid4().hex[:8]}",
                    "domain": analysis_type,
                    "source_type": "expert_panel",
                    "summary": memory_summary.strip(),
                    "metadata": {
                        "address": address,
                        "expert_count": len(roster)
                    }
                }
                dispatch_memory_ingest(ingest_payload)
            except Exception as e:
                logger.warning("expert panel memory auto-ingestion 스킵", err=str(e)[:160])

        return result

    async def _single(self, subject, address, ctx, roster) -> dict[str, Any]:
        # WP-R4: 실패 사유(truncation/timeout/validation/provider)를 분류해 degraded로 전달한다.
        #   ★근본원인: max_tokens=3500이 4전문가 JSON을 절단 → json.loads 실패 → 침묵 폴백이었다.
        #   4전문가 풀 스키마(전문가+토론+합의+검증)의 실측 출력은 약 2.5~3.5k 토큰이라 3500은 경계선
        #   절단이 상시 발생 → 8000으로 상향(약 2.3배 헤드룸)해 절단을 구조적으로 제거한다.
        reason: str | None = None
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from app.services.ai.base_interpreter import GROUNDING_RULE
            from app.services.ai.llm_provider import get_llm

            roster_str = "\n".join(f"- {r['role']} ({r['lens']})" for r in roster)
            user = _PANEL_TMPL.format(subject=subject, address=address or "대상지",
                                      context=ctx, roster=roster_str)
            llm = get_llm(timeout=90, max_tokens=8000)
            resp = await llm.ainvoke(
                [SystemMessage(content=_PANEL_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)]
            )
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="expert_panel")
            raw = resp.content if hasattr(resp, "content") else str(resp)
            # 절단 감지: provider stop_reason이 length/max_tokens면 응답이 잘린 것(무목업·정직 사유).
            stop = ""
            meta = getattr(resp, "response_metadata", None)
            if isinstance(meta, dict):
                stop = str(meta.get("stop_reason") or meta.get("finish_reason") or "")
            try:
                data = json.loads(_strip_json(raw))
            except json.JSONDecodeError:
                reason = "truncation" if stop in ("max_tokens", "length") else "invalid_json"
                raise
            if not isinstance(data.get("experts"), list):
                reason = "validation"
                raise ValueError("experts 누락")
            data["generated"] = True
            return data
        except Exception as e:  # noqa: BLE001
            if reason is None:
                name = type(e).__name__.lower()
                reason = "timeout" if ("timeout" in name or "timeout" in str(e).lower()) else "provider"
            logger.warning(
                "전문가 패널(single) 실패 — degraded(침묵 폴백 아님)",
                reason=reason, err=str(e)[:160],
            )
            return self._fallback(roster, degraded_reason=reason)

    async def _deep(self, subject, address, ctx, roster) -> dict[str, Any]:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from app.services.ai.base_interpreter import GROUNDING_RULE
            from app.services.ai.llm_provider import get_llm

            async def one_expert(r: dict) -> dict[str, Any]:
                user = _EXPERT_TMPL.format(role=r["role"], lens=r["lens"],
                                           subject=subject, address=address or "대상지", context=ctx)
                llm = get_llm(timeout=60, max_tokens=900)
                resp = await llm.ainvoke(
                    [SystemMessage(content=_EXPERT_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)]
                )
                from app.services.ai.base_interpreter import record_llm_response_billing
                await record_llm_response_billing(llm, resp, service="expert_panel")
                try:
                    d = json.loads(_strip_json(resp.content if hasattr(resp, "content") else str(resp)))
                    d.setdefault("role", r["role"])
                    return d
                except Exception:  # noqa: BLE001
                    return {"role": r["role"], "opinion": "", "key_points": [], "concerns": []}

            experts = await asyncio.gather(*[one_expert(r) for r in roster])
            experts = [e for e in experts if e.get("opinion")]
            if not experts:
                raise ValueError("전문가 의견 없음")

            # 통합·검증
            opinions = "\n".join(
                f"[{e['role']}] {e.get('opinion','')} (포인트: {', '.join(e.get('key_points') or [])}; "
                f"우려: {', '.join(e.get('concerns') or [])})" for e in experts
            )
            synth_user = _SYNTH_TMPL.format(subject=subject, address=address or "대상지", opinions=opinions)
            llm = get_llm(timeout=70, max_tokens=2000)
            resp = await llm.ainvoke(
                [SystemMessage(content=_SYNTH_SYSTEM + GROUNDING_RULE), HumanMessage(content=synth_user)]
            )
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="expert_panel")
            synth = json.loads(_strip_json(resp.content if hasattr(resp, "content") else str(resp)))
            return {
                "generated": True,
                "experts": experts,
                "debate": synth.get("debate", []),
                "consensus": synth.get("consensus", ""),
                "recommended_actions": synth.get("recommended_actions", []),
                "verification": synth.get("verification", {}),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("전문가 패널(deep) 실패, single 폴백", err=str(e)[:100])
            return await self._single(subject, address, ctx, roster)

    # WP-R4: degraded 사유별 정직 메시지(무목업) — 프론트가 사유를 구분 표기(침묵 폴백 금지).
    _DEGRADED_MSG: dict[str, str] = {
        "truncation": "전문가 패널 응답이 토큰 한도로 잘려 검증을 완료하지 못했습니다. 다시 시도하면 정상화될 수 있습니다.",
        "invalid_json": "전문가 패널 응답을 해석하지 못했습니다(형식 오류). 잠시 후 다시 시도하세요.",
        "validation": "전문가 패널 응답 형식 검증에 실패했습니다(필수 항목 누락). 잠시 후 다시 시도하세요.",
        "timeout": "전문가 패널 LLM 응답이 시간 초과되었습니다. 잠시 후 다시 시도하세요.",
        "provider": "전문가 패널 LLM 연결에 실패했습니다. 잠시 후 다시 시도하세요.",
    }

    @staticmethod
    def _fallback(roster, degraded_reason: str | None = None) -> dict[str, Any]:
        consensus = ExpertPanelService._DEGRADED_MSG.get(
            degraded_reason or "",
            "전문가 패널 분석은 일시적으로 제공되지 않습니다. 잠시 후 다시 시도하세요.",
        )
        return {
            "generated": False,
            # 실패 사유(truncation/timeout/validation/invalid_json/provider) — 프론트 degraded 표기용.
            "degraded_reason": degraded_reason,
            "experts": [
                {"role": r["role"], "opinion": "AI 패널 연결 후 상세 의견이 제공됩니다.",
                 "key_points": [], "concerns": []}
                for r in roster
            ],
            "debate": [],
            "consensus": consensus,
            "recommended_actions": [],
            "verification": {"confidence": None, "risks": [], "counterpoints": [], "data_gaps": []},
        }
