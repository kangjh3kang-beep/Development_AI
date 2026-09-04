"""절단(truncation) 시에만 **분할 호출**하는 것을 잠근다 — 정상 경로의 과금은 불변이어야 한다.

## 무엇을 고쳤나

`#968`(A-1)은 절단을 **정직하게 보고**하게 했다. 이 변경은 절단 **자체를 없앤다**.

`max_tokens=4096` 이 캡하는 것은 **출력**이다. `_TMPL` 은 사실(소유·이력·압류·근저당)과
**산문**(rights_analysis 3~5문장·risks·acquired_extinguished)을 **한 응답에** 요구해서,
등기부가 길면 출력이 캡에 닿아 잘린다. 그래서 절단이 감지되면 스키마를 **둘로 나눠**
재시도한다 — 각 응답의 출력이 짧아진다.

## ★이 파일이 잠그는 네 축 (하나만 빠져도 다른 결함이 산다)

| 축 | 왜 필요한가 |
|---|---|
| **발화 조건** | «항상 분할» 이면 정상 경로의 과금이 **3배**가 된다. 절단일 때만 발화해야 한다 |
| **호출 수** | 위를 «분할이 안 났다» 로만 재면 부족하다 — **실제 유료 호출 횟수**를 센다 |
| **부분 보존** | 2단이 실패해도 1단의 **유료 산출물(사실)** 을 버리면 «전량 실패» 와 같다 |
| **배선(유료 경로 단일화)** | 분할이 `_invoke` 를 우회해 직접 `ainvoke` 하면 **그 경로만 과금 기록이 빠진다** |

★특히 **발화 조건**이 없으면 «절단이 아닌 실패에도 분할» 하는 구현이 나머지 락을 전부
통과한다(그리고 조용히 과금이 는다). 그래서 **특이도 케이스를 따로 둔다.**
"""
from __future__ import annotations

import ast
import json
import re
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from app.services.registry import registry_analysis_service as ras

_SVC = Path(ras.__file__)

# ★라이브에서 실제로 관측된 절단 형태(미종단 펜스) — `#968` 과 같은 픽스처를 쓴다.
_TRUNCATED_RAW = (
    '```json\n{\n  "ownership": {\n    "current_owner": "조영섭(지분 1/2), 김순복(지분 1/2)",\n'
    '    "owners": [\n      {\n        "name": "조영섭'
)

_FACTS_RAW = json.dumps({
    "ownership": {"current_owner": "조영섭, 김순복", "share": "각 1/2",
                  "owners": [{"name": "조영섭", "share": "1/2"}, {"name": "김순복", "share": "1/2"}]},
    "provisional_registration": {"exists": False},
    "seizure": [{"type": "가압류", "holder": "○○은행", "date": "2024-03-11"}],
    "mortgage": [{"max_claim": "3억6천만원", "mortgagee": "○○은행", "date": "2019-05-02"}],
    "other_rights": [],
}, ensure_ascii=False)

_JUDGE_RAW = json.dumps({
    "baseline_right": "2019-05-02 근저당권(○○은행)",
    "acquired_extinguished": "후순위 가압류는 매각 시 소멸.",
    "right_to_demand_sale": {"possible": "조건부", "reason": "공동소유 지분 정리 필요"},
    "rights_analysis": "말소기준권리는 2019년 근저당이다. 이후 가압류는 소멸한다. 대항력 단서는 없다.",
    "risks": ["공동소유 지분 협의"], "safety_grade": "주의", "summary": "근저당·가압류 존재",
}, ensure_ascii=False)


class _Resp:
    """`is_truncated` 가 보는 것은 본문이 아니라 **메타데이터**다 — 그 층을 그대로 태운다."""

    def __init__(self, *, truncated: bool) -> None:
        self.response_metadata = {"stop_reason": "max_tokens" if truncated else "end_turn"}


def _svc() -> Any:
    return ras.RegistryAnalysisService()


def _wire(monkeypatch, script: list[Any]) -> list[str]:
    """`_invoke` 를 대본으로 바꾸고 **호출된 프롬프트**를 기록해 돌려준다.

    ★기록 대상이 «횟수» 가 아니라 **프롬프트 본문**인 이유: 횟수만 세면 «두 번째 호출도
      같은 전체 스키마» 인 구현(= 분할이 아니라 단순 재시도)이 통과한다. 절단은 결정론적이라
      그 구현은 라이브에서 **또 잘린다.**
    """
    seen: list[str] = []

    async def fake(user: str, **kw: Any):
        seen.append(user)
        step = script[len(seen) - 1]
        if isinstance(step, Exception):
            raise step
        return step

    monkeypatch.setattr(ras.RegistryAnalysisService, "_invoke", staticmethod(fake), raising=True)
    return seen


# ══════════════════════════════════════════════════════════════════════════════
# 축 1·2 — 두 모집단: 정상은 1회 그대로 · 절단은 분할해서 회복
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_normal_response_stays_a_single_paid_call() -> None:
    """모집단 A(정상) — **호출 1회**. 이 단언이 없으면 과금 3배가 조용히 통과한다."""
    good = json.dumps({"ownership": {"current_owner": "홍길동"}, "summary": "정상"}, ensure_ascii=False)
    with pytest.MonkeyPatch.context() as mp:
        seen = _wire(mp, [(_Resp(truncated=False), good)])
        out = await _svc()._llm("서울시 ...", "등기부 원문")

    assert len(seen) == 1, f"정상 응답인데 유료 호출이 {len(seen)}회 — 과금이 늘었다"
    assert out["generated"] is True
    assert out.get("split_call") is not True, "정상 경로에서 분할이 발화했다"
    assert out["summary"] == "정상"


@pytest.mark.asyncio
async def test_truncated_response_recovers_via_split() -> None:
    """모집단 B(절단) — 분할해서 **사실과 판단이 모두** 살아난다."""
    with pytest.MonkeyPatch.context() as mp:
        seen = _wire(mp, [
            (_Resp(truncated=True), _TRUNCATED_RAW),      # 1차: 잘림
            (_Resp(truncated=False), _FACTS_RAW),          # 분할 1단
            (_Resp(truncated=False), _JUDGE_RAW),          # 분할 2단
        ])
        out = await _svc()._llm("남양주시 화도읍 마석우리 265-1", "긴 등기부 원문")

    assert len(seen) == 3, f"분할이 발화하지 않았다(호출 {len(seen)}회)"
    assert out["generated"] is True and out["split_call"] is True
    assert out.get("partial") is not True, "두 단계가 다 성공했는데 partial 로 표기됐다"

    # ★사실과 판단이 **둘 다** 실렸는가 — 한쪽만 보면 반쪽 구현이 통과한다.
    assert out["ownership"]["owners"][0]["name"] == "조영섭"
    assert out["mortgage"][0]["mortgagee"] == "○○은행"
    assert "말소기준권리" in out["rights_analysis"]
    assert out["baseline_right"].startswith("2019")
    assert out["safety_grade"] == "주의"
    # ★★일부 키만 보면 «병합에서 한 키를 빠뜨리는» 변이가 통과한다(적대 리뷰 실측:
    #   `risks` 를 빼도 초록이었다). **선언한 두 목록 전부**가 실렸는지 파생형으로 본다.
    missing = [k for k in ras._SPLIT_FACT_KEYS + ras._SPLIT_JUDGE_KEYS if k not in out]
    assert not missing, f"분할이 선언한 키가 결과에 없다: {missing}"

    # ★분할이 **진짜 분할**인가 — 2·3번째 호출이 1차와 같은 전체 스키마면 또 잘린다.
    assert "rights_analysis" not in seen[1], "분할 1단이 산문까지 요구한다 — 출력이 안 줄어든다"
    assert "ownership_history" not in seen[2], "분할 2단이 사실을 재요구한다 — 출력이 안 줄어든다"
    # ★2단은 원문 등기부를 **본다**(사실 요약만 주면 순위·대항력 근거가 얇아진다).
    # ★**두 단 다** 본다. 2단만 단언하면 1단이 원문 없이도 초록이다(적대 리뷰 실측).
    assert "긴 등기부 원문" in seen[1], "분할 1단이 등기 원문을 못 본다"
    assert "긴 등기부 원문" in seen[2], "분할 2단이 등기 원문을 못 본다"


# ══════════════════════════════════════════════════════════════════════════════
# 축 1 — 특이도: **절단이 아닌** 실패는 분할하지 않는다 (없으면 «항상 분할» 이 만점)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_non_truncated_parse_failure_does_not_split() -> None:
    with pytest.MonkeyPatch.context() as mp:
        seen = _wire(mp, [(_Resp(truncated=False), "죄송합니다. 분석할 수 없습니다.")])
        out = await _svc()._llm(None, "등기부")

    assert len(seen) == 1, f"절단이 아닌데 분할이 발화했다(호출 {len(seen)}회) — 과금이 는다"
    assert out["generated"] is False
    assert out.get("split_call") is not True


@pytest.mark.asyncio
async def test_llm_transport_error_does_not_split() -> None:
    """전송 오류(=응답 객체 자체가 없다)도 분할 대상이 아니다."""
    with pytest.MonkeyPatch.context() as mp:
        seen = _wire(mp, [TimeoutError("provider timeout")])
        out = await _svc()._llm(None, "등기부")

    assert len(seen) == 1 and out["generated"] is False


# ══════════════════════════════════════════════════════════════════════════════
# 축 3 — 부분 보존: 2단이 실패해도 **유료로 얻은 사실**은 버리지 않는다
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_judge_stage_failure_keeps_the_facts_and_says_why() -> None:
    with pytest.MonkeyPatch.context() as mp:
        seen = _wire(mp, [
            (_Resp(truncated=True), _TRUNCATED_RAW),
            (_Resp(truncated=False), _FACTS_RAW),
            RuntimeError("judge stage down"),
        ])
        out = await _svc()._llm(None, "긴 등기부")

    assert len(seen) == 3
    assert out["partial"] is True
    # 유료 산출물(사실)이 살아 있다
    assert out["ownership"]["owners"][1]["name"] == "김순복"
    assert out["seizure"][0]["type"] == "가압류"
    # ★사유를 표면까지 싣는다 — 진단 불가는 그 자체로 장애다
    assert "judge stage down" in out["failure_reason"] or "RuntimeError" in out["failure_reason"]

    # ★★★부분 결과를 **성공이라고 말하지 않는다.** `generated` 는 프론트 `isAnalyzed` 와
    #   서버 `_cache_success` 가 **둘 다 보는 단일 성공 계약**이다. 판단이 없는데 켜면
    #   ①「안전성 주의」 배지가 칠해지고 ②「해석 다시 시도」 버튼이 사라지고 ③DB 에 7일
    #   캐시돼 복구 불가가 된다(적대 리뷰가 실측으로 잡았다 — 초판이 정확히 그랬다).
    assert out["generated"] is False, "판단이 없는 부분 결과가 «성공» 으로 표기됐다"

    # ★«모름» 이 «판단 결과» 로 위장되지 않는가 — 판단 키는 **아예 없어야** 한다.
    #   그래야 `RegistryBatchRow` 의 기존 가드가 배지를 안 칠한다.
    for k in ("safety_grade", "summary", "baseline_right", "acquired_extinguished",
              "right_to_demand_sale", "risks"):
        assert k not in out, f"판단을 못 했는데 `{k}` 에 값이 실렸다: {out.get(k)!r}"
    assert "생성하지 못" in out["rights_analysis"]
    # 재시도 버튼이 뜨는 조건(`failureAction` → reinterpret)
    assert out["failure_class"] == "parse"


@pytest.mark.asyncio
async def test_facts_stage_failure_falls_back_honestly() -> None:
    """1단도 실패하면 분할로 얻을 것이 없다 — 정직 폴백으로 되돌아가고 **사유가 갱신**된다."""
    with pytest.MonkeyPatch.context() as mp:
        seen = _wire(mp, [
            (_Resp(truncated=True), _TRUNCATED_RAW),
            RuntimeError("facts stage down"),
        ])
        out = await _svc()._llm(None, "긴 등기부")

    assert len(seen) == 2
    assert out["generated"] is False
    assert "잘렸습니다" in out["failure_reason"], "절단 사유가 사라졌다(A-1 회귀)"
    assert "분할 재시도도" in out["failure_reason"], "분할이 시도됐다는 사실이 사유에 없다"


# ══════════════════════════════════════════════════════════════════════════════
# 축 4 — 배선: 유료 호출은 `_invoke` **한 통로**만 지난다
# ══════════════════════════════════════════════════════════════════════════════

def _ainvoke_sites(tree: ast.AST) -> list[int]:
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "ainvoke"]


def test_paid_llm_call_has_exactly_one_call_site() -> None:
    """분할이 `_invoke` 를 우회해 직접 호출하면 **그 경로만 과금 기록이 빠진다.**

    ★판정은 문자열이 아니라 **파서**로 한다 — 이 파일의 주석·독스트링에 `ainvoke` 라는
      낱말이 여러 번 나오므로 `grep` 은 그것을 호출부로 센다(이 저장소가 여러 번 데인 형태).
    """
    tree = ast.parse(_SVC.read_text(encoding="utf-8"))
    sites = _ainvoke_sites(tree)
    assert len(sites) == 1, f"유료 LLM 호출부가 {len(sites)}곳({sites}) — `_invoke` 단일 통로가 깨졌다"

    # ★그 유일한 호출부가 **`_invoke` 안**인가. 개수만 세면 «_invoke 를 지우고 _llm 에서
    #   직접 호출» 하는 변경이 통과한다(개수는 여전히 1이다).
    owner = next((fn.name for fn in ast.walk(tree)
                  if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and any(l in _ainvoke_sites(fn) for l in sites)), None)
    assert owner == "_invoke", f"유료 호출이 `{owner}` 안에 있다 — 과금 기록과 분리됐다"

    # 음성 대조군: 조회기가 살아 있는가(호출이 하나도 없으면 위 단언이 공허해진다)
    assert _ainvoke_sites(ast.parse("async def f():\n    await x.ainvoke(1)\n")), "조회기 사망"


# ══════════════════════════════════════════════════════════════════════════════
# 파생형 — 두 단계의 키가 **원래 스키마 전부**를 덮는가
# ══════════════════════════════════════════════════════════════════════════════

def _all_schema_keys(tmpl: str) -> set[str]:
    """스키마의 **모든 깊이**의 키. 축을 「최상위」로 두면 중첩 키가 조용히 사라진다."""
    body = tmpl.split("## 출력 JSON 스키마", 1)[1].replace("{{", "{").replace("}}", "}")
    return set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', body))


def _toplevel_schema_keys(tmpl: str) -> set[str]:
    """`_TMPL` 의 출력 스키마에서 **최상위 키만** 뽑는다(중첩 키는 제외)."""
    # ★`_TMPL` 은 `.format()` 용이라 스키마의 리터럴 중괄호가 **이중화**(`{{`)돼 있다.
    #   정규화하지 않으면 깊이가 0→2 로 건너뛰어 **최상위 키가 한 개도 안 잡힌다**
    #   (첫 실행에서 실제로 그렇게 나왔고, 위 공허진리 하한이 그것을 잡았다).
    body = tmpl.split("## 출력 JSON 스키마", 1)[1].replace("{{", "{").replace("}}", "}")
    keys, depth = set(), 0
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("★") or not stripped:
            continue
        if depth == 1 and stripped.startswith('"'):
            keys.add(stripped.split('"')[1])
        depth += line.count("{") - line.count("}")
        if depth < 0:
            break
    return keys


def test_split_prompts_actually_request_every_key_they_declare() -> None:
    """★상수 목록이 아니라 **분할 프롬프트 본문**과 대조한다.

    초판은 `_TMPL` ↔ **손으로 쓴 상수**만 봤다. 그래서 `_TMPL_FACTS` 에서 `mortgage` 를
    통째로 지워도, 중첩 키 `owners[].acquisition_price` 나 `ownership_history`(주택법 §22
    상속 보유기간 합산의 근거)를 지워도 **전부 초록**이었다(적대 리뷰가 변이로 실증).

    ★**선언은 자기를 검증하지 않는다.** 무엇이 실제로 요구되는지는 프롬프트에만 있다.
    """
    facts_keys = _toplevel_schema_keys(ras._TMPL_FACTS)
    judge_keys = _toplevel_schema_keys(ras._TMPL_JUDGE)
    assert len(facts_keys) >= 4 and len(judge_keys) >= 6, (
        f"프롬프트 파서가 죽었다 — facts={sorted(facts_keys)} judge={sorted(judge_keys)}")

    # 선언(상수) ↔ 프롬프트(실제 요구)를 **양방향**으로 못 박는다.
    assert facts_keys == set(ras._SPLIT_FACT_KEYS), (
        f"1단 프롬프트와 `_SPLIT_FACT_KEYS` 가 어긋난다: "
        f"프롬프트만={sorted(facts_keys - set(ras._SPLIT_FACT_KEYS))} "
        f"상수만={sorted(set(ras._SPLIT_FACT_KEYS) - facts_keys)}")
    assert judge_keys == set(ras._SPLIT_JUDGE_KEYS), (
        f"2단 프롬프트와 `_SPLIT_JUDGE_KEYS` 가 어긋난다: "
        f"프롬프트만={sorted(judge_keys - set(ras._SPLIT_JUDGE_KEYS))} "
        f"상수만={sorted(set(ras._SPLIT_JUDGE_KEYS) - judge_keys)}")


def test_split_prompts_cover_every_key_of_the_original_schema_including_nested() -> None:
    """원래 스키마의 키가 **중첩까지** 어느 한 단에는 요구되는가.

    ★축이 「최상위 키」면 중첩 키가 조용히 사라진다 — 적대 리뷰가 `acquisition_price` 와
      `ownership_history` 를 지워 실증했다. 그래서 **모든 깊이의 키**를 센다.
    """
    schema = _all_schema_keys(ras._TMPL)
    assert len(schema) >= 25, f"스키마 키 추출 {len(schema)}개 — 파서가 죽었다"
    assert {"ownership", "rights_analysis", "acquisition_price", "ownership_history"} <= schema

    covered = _all_schema_keys(ras._TMPL_FACTS) | _all_schema_keys(ras._TMPL_JUDGE)
    missing = schema - covered
    assert not missing, f"분할 프롬프트가 요구하지 않는 원래 스키마 키: {sorted(missing)}"

    # 두 단이 **겹치지 않는가**(겹치면 출력이 안 줄어 절단이 재발한다)
    overlap = set(ras._SPLIT_FACT_KEYS) & set(ras._SPLIT_JUDGE_KEYS)
    assert not overlap, f"두 단이 같은 최상위 키를 요구한다: {sorted(overlap)}"


def test_split_stages_do_not_raise_the_output_cap() -> None:
    """분할은 캡을 **올려서** 해결하는 것이 아니다 — 캡이 조용히 바뀌면 근거가 사라진다."""
    src = _SVC.read_text(encoding="utf-8")
    assert "max_tokens: int = 4096" in src, "`_invoke` 의 기본 출력 캡이 바뀌었다"
    # 분할 호출이 캡을 손대지 않는지(둘 다 기본값을 쓴다)
    assert "self._invoke(_TMPL_FACTS.format" in src and "max_tokens" not in \
        src.split("self._invoke(_TMPL_FACTS.format")[1].split(")")[0]


# ══════════════════════════════════════════════════════════════════════════════
# 축 4-b — 과금 기록: `_invoke` **아래 층**을 직접 태운다
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_every_paid_call_records_billing(monkeypatch) -> None:
    """★`_invoke` 를 monkeypatch 하는 다른 테스트들은 이 층을 **통째로 우회**한다.

    그래서 `record_llm_response_billing` 호출을 지워도 나머지 락이 전부 초록이었다
    (적대 리뷰 실측). AST 락은 `ainvoke` 의 **개수와 소유자**만 보므로 이것을 못 잡는다.
    → 여기서는 `get_llm` 만 스텁하고 **`_invoke` 본문을 그대로 태운다.**
    """
    billed: list[str] = []

    class _FakeLLM:
        async def ainvoke(self, _msgs):
            return _Resp(truncated=False)

    async def fake_billing(_llm, _resp, service: str = "") -> None:
        billed.append(service)

    # ★`langchain_core` 가 없는 환경에서도 **이 층을 태운다.** `importorskip` 을 쓰면
    #   로컬에서 조용히 건너뛰어 «무잠금인데 초록» 이 된다(이 저장소가 데인 형태).
    #   스텁하는 것은 **메시지 데이터 클래스뿐**이고, 검증 대상(과금 기록)은 그대로 실행된다.
    if "langchain_core" not in sys.modules:
        mod = types.ModuleType("langchain_core")
        msgs = types.ModuleType("langchain_core.messages")
        for name in ("HumanMessage", "SystemMessage"):
            setattr(msgs, name, type(name, (), {"__init__": lambda self, content="": None}))
        mod.messages = msgs
        monkeypatch.setitem(sys.modules, "langchain_core", mod)
        monkeypatch.setitem(sys.modules, "langchain_core.messages", msgs)

    import app.services.ai.base_interpreter as bi
    import app.services.ai.llm_provider as lp
    monkeypatch.setattr(lp, "get_llm", lambda **kw: _FakeLLM(), raising=True)
    monkeypatch.setattr(bi, "record_llm_response_billing", fake_billing, raising=True)

    svc = _svc()
    await svc._invoke("프롬프트")
    assert billed == ["registry"], f"유료 호출이 과금에 기록되지 않았다: {billed}"

    # ★두 모집단: 분할 경로의 **세 호출 전부**가 기록되는가.
    #   개수만 세면 «1회만 기록하고 나머지는 빠뜨리는» 구현이 통과한다.
    billed.clear()
    await svc._invoke("a"); await svc._invoke("b"); await svc._invoke("c")
    assert billed == ["registry"] * 3, f"기록 누락: {billed}"
