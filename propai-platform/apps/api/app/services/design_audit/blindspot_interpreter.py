"""설계심사 사각지대(Blindspot) AI 해석 (U6/DA-4).

DesignAuditOrchestrator(U5)가 산출한 결정론 점검 결과(findings)와 파생 신호
(derived_signals)를 근거(evidence)로, 룰 체크가 놓치기 쉬운 '심의 예상 쟁점
(사각지대)'을 LLM이 {claim, basis, confidence} 목록으로 제시한다.

설계 원칙:
- BaseInterpreter 상속(P2/P3/P4 공통 — LLM 생성·캐시·그라운딩·재생성 피드백 재사용).
- citation_gate(결정론): claim 안의 수치·법조문(법령명+제n조 정규식)을
  findings/derived_signals 및 legal_reference_registry 등록분과 대조해,
  미근거 인용은 '전문가 확인 필요'로 치환한다(할루시네이션 차단·가짜값 금지).
- 검증 재생성: VerifierService 검증 → fail 시 이슈 주입 1회 재생성 → 재검증
  (app/routers/pipeline._verify_and_maybe_retry 미러, 상한 1회·무한루프 금지).
- 무중단: 전 과정 실패(LLM 불가·파싱 실패·쟁점 0건) 시 None 반환 →
  호출처(design_audit 라우터)는 blindspot 섹션을 정직하게 생략한다.
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any

import structlog

from app.services.ai.base_interpreter import BaseInterpreter

logger = structlog.get_logger(__name__)

_MAX_ITEMS = 8
_CONFIDENCES = {"high", "medium", "low"}
_EXPERT_NOTE = "전문가 확인 필요"

SYSTEM_PROMPT = """\
당신은 한국 건축 인허가·건축위원회 심의 실무를 20년 이상 수행한 심의위원급 전문가이자 건축사(建築士)입니다. 다음 직능·경력을 겸비한 관점으로 판단합니다.

[전문가 자격·경력 페르소나 — 과장·날조 금지, 실제 국내 직능 부합]
- 건축사(대한건축사협회 등록) 및 지방건축위원회·경관위원회 심의위원 위촉 경력 20년.
- 광역·기초 지자체 건축위원회 심의안건 500건 이상 검토(경관·교통·교육환경·일조·주차·구조·피난 분야).
- 교통영향평가·경관심의·교육환경평가 협의 실무와 심의 감점·보완요구(재심의) 사유 축적.
- 도시계획(국토계획법)·건축법·주차장법·경관법·교육환경보호법의 위임구조(법→시행령→조례·별표)를 정확히 구분해 적용.
- 역할: 결정론 점검엔진(U5)의 findings·derived_signals를 근거로, 룰 체크가 놓치기 쉬운 '심의 예상 쟁점(사각지대)'을 심의위원 시각에서 선제적으로 도출합니다. 확정 판정이 아니라 '심의에서 제기될 수 있는 논점'을 제시하는 것이 목적입니다.

[심의 감점·쟁점 도메인 지식 — 확실한 산식·법조문만 규칙화(정확성 필수)]
아래 분야별로 심의에서 반복적으로 제기되는 논점과 정확한 근거법령을 우선 검토하되, 수치·판정은 반드시 제공 데이터(findings/derived_signals)에서만 인용한다. 조문은 아래 '확실한' 것만 인용하고, 그 외는 조문 없이 정성적으로 쓴다.
1) 일조·높이(정북일조): 전용주거·일반주거지역의 정북방향 인접대지 일조권 확보. 근거: 건축법 제61조(일조 등의 확보를 위한 건축물의 높이 제한), 위임: 건축법 시행령 제86조. 통상 높이 9m 이하 부분은 인접대지경계선에서 1.5m 이상, 9m 초과 부분은 해당 높이의 1/2 이상 이격이 원칙(구체값은 조례·데이터 확인). 데이터에 이격·높이·후퇴가 없으면 수치 없이 "정북일조 후퇴 검토 필요"로만 기술.
2) 주차: 부설주차장 설치기준 미달·장애인/전기차 의무비율·출입구 동선. 근거: 주차장법 제19조(부설주차장 설치), 위임: 주차장법 시행령 제6조(별표1) 및 해당 지자체 주차장 조례. 세대당·연면적당 대수 기준값은 조례·데이터에 근거해서만 인용.
3) 교육환경: 학교 인근 교육환경보호구역(절대보호구역 학교출입문 50m, 상대보호구역 학교경계 200m 내) 금지·제한행위 저촉 여부. 근거: 교육환경 보호에 관한 법률 제9조(교육환경보호구역에서의 금지행위). 학교·거리 데이터가 없으면 "교육환경보호구역 저촉 여부 확인 필요".
4) 경관: 경관지구·중점경관관리구역·경관심의 대상규모(높이·연면적) 저촉 및 가로·스카이라인·색채·저층부 대응. 근거: 경관법 제9조(경관계획), 국토계획법 제37조(경관지구 등 용도지구). 경관심의 대상 여부·규모 임계값은 데이터·조례 확인.
5) 교통: 교통영향평가 대상규모 도달·진출입 동선·교차로 영향. 근거: 도시교통정비 촉진법(교통영향평가). 대상규모·처리대수는 데이터에 근거해서만.
6) 대지·도로·공지: 접도요건(건축법 제44조, 대지와 도로의 관계), 건축선(제46·47조), 대지 안의 공지(제58조), 피난·용도제한(제49조)·구조안전(제48조) 관련 심의 보완가능성.
※ 위 조문 외 불확실한 조문·별표 번호·감점 배점표 수치는 지어내지 않는다(할루시네이션 금지). 배점·감점은 지자체 심의기준에 따라 상이하므로 "감점요인" 수준으로만 기술하고 임의 점수를 만들지 않는다.

[evidence 그라운딩·근거링크]
- 모든 쟁점은 제공된 findings/derived_signals/context의 실데이터(수치·판정·플래그)를 근거로 서술한다. basis에는 반드시 제공된 findings의 check_id만 인용한다(예: "ENG-3, CMP-1"). 제공되지 않은 check_id·근거 ID를 만들어내지 않는다.
- 법령·조례 근거를 claim에 쓸 때는 위 '확실한' 조문에 한해 '법령명 제n조' 형식으로 정확히 쓴다(예: "건축법 제61조", "주차장법 제19조", "교육환경 보호에 관한 법률 제9조", "경관법 제9조", "국토계획법 제37조"). 확실하지 않으면 조문을 생략하고 법령명만 또는 정성적으로 기술한다. (근거링크는 후처리에서 law.go.kr로 자동 부착되므로, 조문을 정확한 표기로만 남기면 된다.)
- 출처 없는 단정 금지: 데이터에 없는 거리·규모·기준값을 근거처럼 단정하지 않는다.

[출력 서술 정밀도 — 요구 JSON 키·값타입 절대변경 금지]
- 각 claim(1~2문장)은 가능한 한 '분석(무엇이 감지됐나) → 근거수치(제공 데이터) → 심의 시사점 → 리스크/보완가능성'의 흐름이 드러나게 압축해 작성한다. 단, 요구 출력 JSON 구조(blindspots 배열의 {claim, basis, confidence}와 summary)와 값 타입(문자열)은 절대 바꾸지 않는다. 키 추가·삭제·중첩 변경 금지.
- confidence는 high|medium|low 중 하나. 데이터 근거가 강하면 high, 정황·추정이면 medium, 데이터가 희박하면 low.
- summary는 전체 쟁점을 1~2문장으로 요약.

[정직강등 — 무날조·불확실·특이부지]
- 모든 수치는 위에 제공된 데이터에서만 인용한다. 데이터에 없으면 수치 없이 정성적으로 기술하거나 "데이터 없음/확인 필요"로 명시한다. 벤치마크·평균·업계관행 비율을 데이터 근거 없이 만들어내지 않는다.
- 단위환산은 정확히 한다(1평=3.3058㎡; 원/평=원/㎡×3.3058).
- 특이부지·비일상 토지특성(학교용지·개발제한구역·농지·산지·맹지·문화재·기반시설 등)이나 데이터 불확실 신호가 있으면, 쟁점을 단정하지 말고 전제·확인필요를 명시해 confidence를 낮춘다.
- 쟁점이 없거나 근거가 부족하면 억지로 만들지 말고 빈 배열을 반환한다. 근거(check_id) 없는 쟁점은 제외한다.

[형식 규칙(반드시 준수)]
1. 각 쟁점(claim)의 근거(basis)에는 반드시 제공된 findings의 check_id를 인용한다(제공된 것 외 생성 금지).
2. 모든 수치는 제공된 데이터에서만 인용한다. 없으면 수치 없이 정성적으로 기술한다.
3. 법조문은 확실한 경우에만 '법령명 제n조' 형식으로 쓰고, 불확실하면 쓰지 않는다.
4. confidence는 high|medium|low 중 하나.
5. 쟁점이 없으면 빈 배열을 반환한다(억지로 만들지 않는다).
6. 반드시 JSON 형식으로만 응답한다(마크다운·설명문 금지).
"""

USER_PROMPT_TEMPLATE = """\
아래 설계심사 점검 근거를 바탕으로 '심의 예상 쟁점(사각지대)'을 JSON으로 작성하세요.

## 점검 근거(findings + derived_signals)
{evidence_json}

## 요구 출력(JSON)
{{
  "blindspots": [
    {{"claim": "심의에서 제기될 수 있는 쟁점(1~2문장)",
      "basis": "근거가 된 findings의 check_id 인용(예: ENG-3)",
      "confidence": "high|medium|low"}}
  ],
  "summary": "쟁점 전체 요약 1~2문장"
}}
최대 {max_items}건. 근거(check_id) 없는 쟁점은 제외하세요.
"""


class BlindspotInterpreter(BaseInterpreter):
    """결정론 findings를 근거로 심의 예상 쟁점(사각지대)을 생성하는 인터프리터."""

    name = "design_blindspot"
    expected_keys = ["blindspots", "summary"]
    fallback_key = ""  # 구조화 실패 시 원문 폴백은 무의미 — 빈 dict(호출처 생략 경로)
    max_tokens = 3000
    system_prompt = SYSTEM_PROMPT

    async def generate_interpretation(self, data: dict) -> dict[str, str]:
        """evidence(findings/derived_signals/context) → {blindspots(JSON 문자열), summary}.

        Args:
            data: {"findings": [...], "derived_signals": {...}, "context": {...}}

        Returns:
            {"blindspots": "<JSON 배열 문자열>", "summary": str}. 실패 시 빈 dict.
        """
        compact = self._extract_compact_data(data)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            evidence_json=json.dumps(compact, ensure_ascii=False, indent=2, default=str)[:8000],
            max_items=_MAX_ITEMS,
        )
        return await self._invoke(user_prompt, cache_data=compact)

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """LLM에 필요한 핵심 근거만 추출(findings 상한으로 프롬프트 비대 방지)."""
        findings = data.get("findings") or []
        if isinstance(findings, list):
            findings = findings[:40]
        compact: dict[str, Any] = {
            "findings": findings,
            "derived_signals": data.get("derived_signals") or {},
        }
        if data.get("context"):
            compact["context"] = data["context"]
        return compact

    def _parse_response(self, raw: str) -> dict[str, str]:
        """기반 파서는 모든 값을 str()로 평탄화해 list(blindspots)가 깨진다 —
        blindspots는 JSON 문자열로 보존하도록 오버라이드.
        (코드블록 제거·중괄호 복원 규칙은 기반 클래스와 동일.)
        """
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            text = "\n".join(lines[1:end])
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start == -1 or brace_end == -1:
                logger.warning("blindspot 응답에서 JSON 미발견", raw_length=len(raw))
                return {}
            try:
                parsed = json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                logger.warning("blindspot 응답 JSON 파싱 최종 실패", raw_length=len(raw))
                return {}
        if not isinstance(parsed, dict):
            return {}
        result: dict[str, str] = {}
        items = parsed.get("blindspots")
        if isinstance(items, list):
            result["blindspots"] = json.dumps(items, ensure_ascii=False)
        summary = parsed.get("summary")
        if summary is not None:
            result["summary"] = str(summary)
        return result


def parse_blindspot_items(sections: dict[str, str] | None) -> list[dict[str, str]]:
    """인터프리터 섹션 → 정규화된 쟁점 목록 [{claim, basis, confidence}] (결정론)."""
    raw = (sections or {}).get("blindspots") or ""
    try:
        arr = json.loads(raw)
    except (TypeError, ValueError):
        return []
    items: list[dict[str, str]] = []
    for it in arr if isinstance(arr, list) else []:
        if not isinstance(it, dict):
            continue
        claim = str(it.get("claim") or "").strip()
        if not claim:
            continue
        conf = str(it.get("confidence") or "medium").strip().lower()
        items.append({
            "claim": claim[:400],
            "basis": str(it.get("basis") or "").strip()[:200],
            "confidence": conf if conf in _CONFIDENCES else "medium",
        })
    return items[:_MAX_ITEMS]


# ─────────────────────────────────────────────────────────────────────────────
# citation_gate — 결정론 인용 검문(수치·법조문). LLM 무관, 순수 함수.
# ─────────────────────────────────────────────────────────────────────────────

# 법조문: 법령명(…법/법률/시행령/시행규칙/조례/특별법) + 제n조(의m 가지번호 허용)
_LAW_CITATION_RE = re.compile(
    r"([가-힣A-Za-z0-9·\s]{1,40}?(?:법률|시행령|시행규칙|조례|특별법|법))\s*"
    r"(제\d{1,4}조(?:의\d{1,2})?)"
)
# 수치 토큰: 천단위 콤마 / 소수 / 정수
_NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+")


def _norm_law(name: str) -> str:
    """법령명 정규화 — 공백·가운뎃점 제거(legal_reference_registry와 동일 규칙)."""
    cleaned = name or ""
    for ch in (" ", "·", "・"):
        cleaned = cleaned.replace(ch, "")
    return cleaned


def _iter_findings(findings: Any):
    """findings가 list든 {그룹: [...]} dict든 개별 finding(dict)만 순회."""
    if isinstance(findings, dict):
        for v in findings.values():
            if isinstance(v, list):
                yield from (f for f in v if isinstance(f, dict))
    elif isinstance(findings, list):
        yield from (f for f in findings if isinstance(f, dict))


def _known_check_ids(findings: Any) -> set[str]:
    """findings에 실재하는 check_id 집합(대문자 정규화)."""
    ids: set[str] = set()
    for f in _iter_findings(findings):
        for key in ("check_id", "rule_id", "id", "code"):
            v = f.get(key)
            if v:
                ids.add(str(v).strip().upper())
    return ids


def _walk_numbers(obj: Any, out: set[float]) -> None:
    """evidence 트리의 모든 수치(숫자값 + 문자열 내 숫자)를 수집(소수 4자리 반올림)."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(round(float(obj), 4))
        return
    if isinstance(obj, str):
        for m in _NUMBER_RE.findall(obj):
            with contextlib.suppress(ValueError):
                out.add(round(float(m.replace(",", "")), 4))
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_numbers(v, out)


def _registry_pairs() -> set[tuple[str, str]]:
    """legal_reference_registry 등재 (정규화 법령명, 조문) 쌍 — 조문 있는 레코드만."""
    from app.services.legal.legal_reference_registry import LEGAL_REFERENCES

    pairs: set[tuple[str, str]] = set()
    for ref in LEGAL_REFERENCES.values():
        name = _norm_law(ref.get("law_name", ""))
        article = (ref.get("article") or "").strip()
        if name and article:
            pairs.add((name, article))
    return pairs


def _grounded_number(value: float, evidence_numbers: set[float]) -> bool:
    rounded = round(value, 4)
    if rounded in evidence_numbers:
        return True
    tol = max(1e-6, abs(value) * 1e-6)
    return any(abs(value - e) <= tol for e in evidence_numbers)


def citation_gate(
    items: list[dict[str, str]],
    findings: Any,
    derived_signals: Any = None,
    *,
    prior_evidence: Any = None,
) -> list[dict[str, Any]]:
    """결정론 인용 검문 — 미근거 수치·법조문을 '전문가 확인 필요'로 치환.

    대조 원천(이외 인정 안 함):
    - 수치: findings + derived_signals 트리의 모든 숫자(문자열 내 숫자 포함).
    - 법조문: legal_reference_registry 등재 (법령명, 제n조) 쌍 또는
      evidence 본문에 동일 인용(법령명+조문)이 실재하는 경우.
    - basis: findings에 실재하는 check_id 인용 여부(미확인 시 confidence 강등).

    치환 규칙(보수적):
    - 미등재 법조문 → 인용 전체를 "관련 법령(전문가 확인 필요)"로 치환.
    - 미근거 수치 → 해당 토큰을 "[전문가 확인 필요]"로 치환.
    - 치환·강등 발생 항목은 confidence="low" + citation_gate.reasons 기록.

    수치 검문 제외(과탐 방지 휴리스틱, 문서화된 한계):
    - 10 미만의 소수점/콤마 없는 정수(나열 숫자 "2개" 등),
    - '제n조' 조문 번호(법조문 검문에서 별도 처리), 'n년/월/일' 날짜 표기.

    입력 items는 변형하지 않고 사본을 반환한다(순수 함수).
    """
    evidence_numbers: set[float] = set()
    _walk_numbers(findings, evidence_numbers)
    _walk_numbers(derived_signals, evidence_numbers)
    evidence_norm = _norm_law(
        json.dumps([findings, derived_signals], ensure_ascii=False, default=str)
    )
    if prior_evidence is not None:  # Phase 1: 원장 prior 수치/법조문을 grounded corpus에 합류
        from app.services.ledger.prior_context import prior_numbers
        for _n in prior_numbers(prior_evidence):
            evidence_numbers.add(_n)
        evidence_norm = _norm_law(
            evidence_norm
            + json.dumps(prior_evidence.get("payload", prior_evidence), ensure_ascii=False, default=str)
        )
    known_ids = _known_check_ids(findings)
    registry_pairs = _registry_pairs()

    def _law_grounded(captured_norm: str, article: str) -> bool:
        # 레지스트리: 조사(은/는/이/가)가 앞에 붙어 캡처돼도 접미 일치로 인정.
        for name, art in registry_pairs:
            if art == article and captured_norm.endswith(name):
                return True
        # evidence 본문에 동일 인용 실재(접두 조사 제거하며 접미 부분 문자열 탐색).
        for i in range(len(captured_norm)):
            tail = captured_norm[i:]
            if len(tail) >= 2 and (tail + article) in evidence_norm:
                return True
        return False

    gated: list[dict[str, Any]] = []
    for item in items:
        claim = str(item.get("claim") or "")
        basis = str(item.get("basis") or "")
        confidence = str(item.get("confidence") or "medium")
        reasons: list[str] = []

        # 1) 법조문 검문(치환)
        def _law_sub(m: re.Match) -> str:
            captured_norm = _norm_law(m.group(1))
            article = m.group(2).strip()
            if _law_grounded(captured_norm, article):
                return m.group(0)
            reasons.append(f"미등록 법조문 인용: {m.group(0).strip()}")
            return f"관련 법령({_EXPERT_NOTE})"

        claim = _LAW_CITATION_RE.sub(_law_sub, claim)

        # 2) 수치 검문(치환) — 조문번호/날짜/나열 소수는 제외.
        def _num_sub(m: re.Match) -> str:
            token = m.group(0)
            start, end = m.start(), m.end()
            prev_ch = claim[start - 1] if start > 0 else ""
            next_ch = claim[end] if end < len(claim) else ""
            if prev_ch in ("제", "의") or next_ch in ("조", "년", "월", "일"):
                return token  # 조문 번호·날짜 표기 — 수치 검문 대상 아님
            try:
                value = float(token.replace(",", ""))
            except ValueError:
                return token
            if value < 10 and "." not in token and "," not in token:
                return token  # 나열 숫자("2개" 등) 과탐 방지
            if _grounded_number(value, evidence_numbers):
                return token
            reasons.append(f"미근거 수치 인용: {token}")
            return f"[{_EXPERT_NOTE}]"

        claim = _NUMBER_RE.sub(_num_sub, claim)

        # 3) basis check_id 검문(강등) — findings에 실재하는 ID 인용 여부.
        if not basis.strip():
            reasons.append(f"근거(check_id) 미제시 — {_EXPERT_NOTE}")
        elif known_ids:
            cited = {t.upper() for t in re.findall(r"[A-Za-z]{2,12}[-_]?\d{1,3}", basis)}
            if not (cited & known_ids) and not any(k in basis.upper() for k in known_ids):
                reasons.append(f"basis의 check_id가 findings에 없음 — {_EXPERT_NOTE}")

        gated.append({
            "claim": claim,
            "basis": basis,
            "confidence": "low" if reasons else confidence,
            "citation_gate": {"gated": bool(reasons), "reasons": reasons},
        })
    return gated


# ─────────────────────────────────────────────────────────────────────────────
# 검증 재생성(상한 1회) — app/routers/pipeline._verify_and_maybe_retry 미러.
# (라우터 모듈 임포트는 의존 비대 → 동일 정책을 자체 보유. 정책 변경 시 양쪽 동기화.)
# ─────────────────────────────────────────────────────────────────────────────


def _needs_retry(verdict: dict[str, Any]) -> bool:
    """fail 또는 high 심각도 이슈가 있으면 재생성 대상(파이프라인과 동일 규칙)."""
    if not isinstance(verdict, dict):
        return False
    if verdict.get("verdict") == "fail":
        return True
    return any(
        isinstance(i, dict) and i.get("severity") == "high"
        for i in (verdict.get("issues") or [])
    )


def _issues_text(verdict: dict[str, Any]) -> str:
    """검증 결과 → 재생성 프롬프트 주입용 이슈 요약(파이프라인과 동일 규칙)."""
    lines: list[str] = []
    for it in (verdict.get("issues") or [])[:8]:
        if not isinstance(it, dict):
            continue
        sev = it.get("severity", "?")
        typ = it.get("type", "이슈")
        claim = str(it.get("claim", ""))[:120]
        note = str(it.get("note", ""))[:160]
        lines.append(f"- [{sev}] {typ}: {claim} — {note}")
    summary = str(verdict.get("summary", ""))[:200]
    head = f"검증 요약: {summary}" if summary else ""
    return (head + "\n" + "\n".join(lines)).strip()


async def _verify_and_maybe_retry(
    evidence: dict[str, Any],
    interp: BlindspotInterpreter,
    sections: dict[str, str],
) -> tuple[dict[str, str], dict[str, Any] | None, bool, str | None]:
    """검증 → fail 시 이슈주입 1회 재생성 → 재검증. 상한 1회(무한루프 금지).

    반환: (채택 sections, verification, regenerated, verification_warning).
    모든 실패는 best-effort 무중단(원본 채택).
    """
    try:
        from app.services.verification.verifier_service import VerifierService

        verifier = VerifierService()
        v1 = await verifier.verify("design_blindspot", evidence, sections)
    except Exception:  # noqa: BLE001
        return sections, None, False, None

    if not _needs_retry(v1):
        return sections, v1, False, None

    try:
        interp.set_retry_feedback(_issues_text(v1))
        regen = await interp.generate_interpretation(evidence)
        interp.set_retry_feedback(None)
    except Exception:  # noqa: BLE001
        return sections, v1, False, "검증 실패 — 재생성 중 오류로 원본을 유지합니다."

    if not (isinstance(regen, dict) and regen):
        return sections, v1, False, "검증 실패 — 재생성 결과가 비어 원본을 유지합니다."

    try:
        v2 = await verifier.verify("design_blindspot", evidence, regen)
    except Exception:  # noqa: BLE001
        return regen, v1, True, "재생성본을 적용했으나 재검증은 일시적으로 수행되지 않았습니다."

    if _needs_retry(v2):
        return sections, v2, False, "검증에 실패했고 1회 재생성 후에도 통과하지 못해 원본을 유지합니다."

    return regen, v2, True, None


# ─────────────────────────────────────────────────────────────────────────────
# 통합 진입점 — 라우터(U6/DA-5)가 호출. 전체 실패 시 None(blindspot 섹션 생략).
# ─────────────────────────────────────────────────────────────────────────────


async def generate_blindspot(
    findings: Any,
    derived_signals: Any = None,
    *,
    context: dict[str, Any] | None = None,
    use_verification_retry: bool = True,
) -> dict[str, Any] | None:
    """사각지대(심의 예상 쟁점) 생성 — 검증 1회 재생성 + 결정론 citation_gate.

    Args:
        findings: U5 결정론 점검 결과(list 또는 {그룹: [...]} dict).
        derived_signals: U5 파생 신호 dict.
        context: 부지·설계 개요 등 보조 컨텍스트(근거로만 사용).
        use_verification_retry: VerifierService 검증·1회 재생성 사용 여부.

    Returns:
        {"generated": True, "label": "AI 추정", "items": [...], "summary": str|None,
         "regenerated": bool, ("verification"), ("verification_warning")}
        — 실패·쟁점 0건이면 None(호출처는 blindspot을 생략, 무중단).
    """
    try:
        evidence: dict[str, Any] = {
            "findings": findings or [],
            "derived_signals": derived_signals or {},
            "context": context or {},
        }
        interp = BlindspotInterpreter()
        sections = await interp.generate_interpretation(evidence)
        if not sections:
            return None

        verification: dict[str, Any] | None = None
        regenerated = False
        warning: str | None = None
        if use_verification_retry:
            sections, verification, regenerated, warning = await _verify_and_maybe_retry(
                evidence, interp, sections
            )

        items = parse_blindspot_items(sections)
        if not items:
            return None
        items = citation_gate(items, evidence["findings"], evidence["derived_signals"])

        out: dict[str, Any] = {
            "generated": True,
            "label": "AI 추정",  # 리포트 S6 '심의 예상 쟁점' 라벨 — 확정 아님 명시
            "items": items,
            "summary": (sections.get("summary") or "").strip() or None,
            "regenerated": regenerated,
        }
        if verification is not None:
            out["verification"] = verification
        if warning:
            out["verification_warning"] = warning
        return out
    except Exception as e:  # noqa: BLE001 — 전체 실패 시 생략(무중단)
        logger.warning("blindspot 생성 실패 — 섹션 생략(무중단)", error=str(e)[:120])
        return None
