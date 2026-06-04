"""분석 검증 에이전트 — 오류·할루시네이션 가드.

분석 출력이 제공된 원본 데이터에 근거하는지 검증한다. 근거없는 주장(할루시네이션),
수치 불일치, 내부 모순, 과장을 탐지해 ✅통과/⚠️주의/❌오류 판정과 플래그를 제시한다.
모든 분석에 자동 배치(전수)되며, 결과당 1회만 호출(프론트 캐싱)하여 비용을 통제한다.

규칙 사전검사(수치 모순 등) + LLM 근거검증을 결합. LLM 실패 시 규칙기반 폴백.
"""

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_SYSTEM = """\
당신은 부동산개발 분석의 '검증관'입니다. 아래 [분석 출력]이 [원본 데이터]에 실제로
근거하는지 엄격히 검증합니다. 다음을 탐지하세요:
1) 할루시네이션: 원본 데이터에 없는 수치·사실·법조문을 지어낸 주장
2) 수치 불일치: 원본과 다른 값, 단위 오류, 계산 모순
3) 내부 모순: 분석 내 앞뒤가 안 맞는 서술
4) 과장/단정: 데이터로 뒷받침되지 않는 확정적 단정
검증관은 관대하지 않게, 그러나 근거가 충분하면 통과시킵니다. JSON만 출력."""

_TMPL = """\
## 분석 유형: {analysis_type}

## 원본 데이터(근거 자료)
{source}

## 분석 출력(검증 대상)
{output}

## 출력 JSON 스키마
{{
  "verdict": "pass|warn|fail",
  "grounded_score": 0-100 정수(원본 근거 충실도),
  "issues": [
    {{"type": "할루시네이션|수치불일치|내부모순|과장",
      "claim": "문제된 주장(짧게 인용)",
      "severity": "high|medium|low",
      "note": "왜 문제인지 + 원본과의 차이"}}
  ],
  "summary": "검증 요약 1~2문장"
}}
원칙: high 이슈가 있으면 verdict=fail, medium만 있으면 warn, 없으면 pass.
이슈가 없으면 issues=[]. 추측으로 이슈를 만들지 말 것.
"""


def _prescan(context: dict[str, Any] | str) -> list[dict[str, str]]:
    """규칙기반 사전검사: 명백한 수치 이상(음수 면적/용적률 비정상 등)."""
    issues: list[dict[str, str]] = []
    if not isinstance(context, dict):
        return issues
    far = context.get("max_far") or context.get("effective_far")
    try:
        if far is not None and (float(far) < 0 or float(far) > 2000):
            issues.append({"type": "수치불일치", "claim": f"용적률 {far}%",
                           "severity": "medium", "note": "용적률 범위(0~2000%) 이탈 — 확인 필요"})
    except (TypeError, ValueError):
        pass
    area = context.get("land_area_sqm")
    try:
        if area is not None and float(area) < 0:
            issues.append({"type": "수치불일치", "claim": f"면적 {area}㎡",
                           "severity": "high", "note": "면적이 음수"})
    except (TypeError, ValueError):
        pass
    return issues


def _strip_json(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        raw = raw[4:] if raw.lower().startswith("json") else raw
    return raw.strip()


class VerifierService:
    async def verify(
        self,
        analysis_type: str,
        source: dict[str, Any] | str,
        output: dict[str, Any] | str,
    ) -> dict[str, Any]:
        pre = _prescan(source if isinstance(source, dict) else {})

        # ── 결정론 수치-원장(Calc Ledger): LLM과 무관하게 산식 재계산으로 계산환각 적발 ──
        from app.services.verification.calc_ledger import run_calc_checks
        from app.services.verification.range_rules import run_range_checks
        calc = run_calc_checks(source, output)
        # 모듈별 범위 sanity 규칙(산식은 맞아도 값이 비현실/법정범위 이탈)
        range_issues = run_range_checks(analysis_type, source, output)
        pre = pre + calc["issues"] + range_issues  # 계산오류·범위위반(high)은 두 경로 모두 반영

        src = source if isinstance(source, str) else json.dumps(source, ensure_ascii=False)
        out = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)

        try:
            from app.services.ai.llm_provider import get_llm
            from langchain_core.messages import HumanMessage, SystemMessage

            user = _TMPL.format(analysis_type=analysis_type, source=src[:4000], output=out[:4000])
            llm = get_llm(timeout=50, max_tokens=1500)
            resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), HumanMessage(content=user)])
            data = json.loads(_strip_json(resp.content if hasattr(resp, "content") else str(resp)))
            issues = list(data.get("issues") or []) + pre
            # 판정 보정(사전검사 high 반영)
            verdict = data.get("verdict") or "pass"
            sev = {i.get("severity") for i in issues}
            if "high" in sev:
                verdict = "fail"
            elif "medium" in sev and verdict == "pass":
                verdict = "warn"
            return {
                "generated": True,
                "verdict": verdict,
                "grounded_score": data.get("grounded_score"),
                "issues": issues,
                "summary": data.get("summary") or "검증 완료.",
                "calc_checks": calc["checks"],
                "calc_pass_rate": calc["pass_rate"],
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("검증 LLM 실패, 규칙기반 폴백", err=str(e)[:100])
            return {
                "generated": False,
                "verdict": "fail" if any(i["severity"] == "high" for i in pre) else ("warn" if pre else "pass"),
                "grounded_score": None,
                "issues": pre,
                "summary": (
                    "AI 검증은 일시적으로 제공되지 않습니다. 규칙기반 사전검사 + 결정론 재계산만 적용되었습니다."
                    if calc["total"] else
                    "AI 검증은 일시적으로 제공되지 않습니다. 규칙기반 사전검사만 적용되었습니다."
                ),
                "calc_checks": calc["checks"],
                "calc_pass_rate": calc["pass_rate"],
            }
