"""LLM 관측의 **분모와 분자는 한 쌍이어야 한다**.

## 무엇이 있었나 (2026-08-24 실장애)

성장루프의 `fallback_rate` 는 `llm_call` 이벤트 수를 **분모**로, `fallback` 이벤트와
`llm_call(ok=false)` 를 **분자**로 쓴다(`growth/analyzer.py`). 그런데 `llm_call` 은
`BaseInterpreter` **안에서만** 기록돼 왔다. 등기 권리분석처럼 `llm.ainvoke` 를 직접 부르는
서비스는 분모가 0이라 `FALLBACK_MIN_CALLS=10` 에 걸려 **인사이트가 영원히 뜨지 않았다.**

결과: 등기 권리분석이 통째로 죽어(모든 필지가 "분석 불가") **사용자가 화면을 보고 알려 줄
때까지 아무도 몰랐다.** 같은 시각 `site_analysis` 는 폴백률 80.77% critical 로 잡히고 있었다 —
**측정되는 서비스만 보이는 계기판**이었다.

## 이 락이 강제하는 것

분모(`record_llm_response_billing`)를 배선한 모듈은 분자(`record_llm_failure` 또는
`record_fallback`)도 배선해야 한다. **분모만 있으면 그 서비스는 폴백률 0% 로 보인다** —
전부 실패하는 서비스가 초록으로 읽히는, 침묵보다 나쁜 상태다.

★목록형이 아니라 **파생형**이다: 소스에서 호출자를 긁어 온다. 새 서비스가 분모를 배선하면
자동으로 이 검사에 들어온다(사람이 센 목록이 상한이 되지 않게).

★면제는 **사유와 함께** 남긴다. 사유 없는 면제는 "고쳤는데 안 잠긴" 상태를 초록으로 만든다.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

_DENOM = {"record_llm_response_billing", "record_llm_response_billing_sync"}
_NUMER = {"record_llm_failure", "record_fallback"}


def _identifiers(src: str) -> set[str]:
    """모듈이 **실제로 쓰는** 식별자 집합(AST).

    ★문자열 검색을 쓰면 **주석과 독스트링에 뚫린다.** 실제로 초판이 그랬다:
      `tasks/_async_batch.py` 는 도달성을 설명하는 **독스트링에서 이름을 언급**할 뿐인데
      위반으로 신고됐다(위양성). `code_lines()` 는 `#` 주석만 걷어내므로 부족하다 —
      판정을 파서에게 넘긴다.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out.add(a.asname or a.name.split(".")[-1])
    return out

# ── 면제 — **부채 목록이며, 줄어야 한다** ──────────────────────────────────────
# 형식: 모듈 상대경로 → 사유. 사유 없이 추가하지 마라.
# ★2026-08-24 현재 전부 같은 사유다: 분모 계측은 공용 헬퍼를 타서 자동으로 생겼지만,
#   각 서비스의 **실패 경로**는 그 서비스의 폴백 규약을 아는 사람이 배선해야 한다.
#   배선하는 PR 에서 **이 목록에서 지운다**(면제를 남기면 락이 skip 이라 무잠금이다).
_EXEMPT: dict[str, str] = {
    "services/verification/verifier_service.py": "★부채 — 실패 경로 미배선",
    "services/design_ingest/vision_parser.py": "★부채 — 실패 경로 미배선",
    "services/legal/alris_service.py": "★부채 — 실패 경로 미배선",
    "services/legal/legal_discovery_service.py": "★부채 — 실패 경로 미배선",
    "services/land_intelligence/parcel_excel_service.py": "★부채 — 실패 경로 미배선",
    "services/permit/permit_analysis_service.py": "★부채 — 실패 경로 미배선",
    "services/market/conversational_market_ai.py": "★부채 — 실패 경로 미배선",
    "services/ai_services/bid_interpreter.py": "★부채 — 실패 경로 미배선",
    "services/ai/assistant_agent.py": "★부채 — 실패 경로 미배선",
    "services/market/market_report_service.py": "★부채 — 실패 경로 미배선",
    "services/growth/improvement_agent.py": "★부채 — 실패 경로 미배선",
    "services/regulation/regulation_analysis_service.py": "★부채 — 실패 경로 미배선",
    "services/growth/analyzer.py": "★부채 — 실패 경로 미배선",
    "services/development/scenario_simulator.py": "★부채 — 실패 경로 미배선",
    "services/expert_panel/expert_panel_graph.py": "★부채 — 실패 경로 미배선",
    "services/expert_panel/expert_panel_service.py": "★부채 — 실패 경로 미배선",
    "services/precheck/precheck_service.py": "★부채 — 실패 경로 미배선",
}


def _modules_recording_denominator() -> dict[str, set[str]]:
    """분모를 배선한 모듈 → 그 모듈이 쓰는 식별자 집합(파생형 수집)."""
    out: dict[str, set[str]] = {}
    for f in APP.rglob("*.py"):
        if f.name == "base_interpreter.py":  # 정의처(분모의 집)
            continue
        try:
            names = _identifiers(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if names & _DENOM:
            out[str(f.relative_to(APP))] = names
    return out


def test_전제_분모_호출자를_실제로_찾는다():
    """공허한 초록 방지 — 수집기가 죽으면 '위반 0'이 저절로 참이 된다."""
    mods = _modules_recording_denominator()
    assert len(mods) >= 10, f"분모 호출자를 못 찾았다(수집이 깨졌다): {sorted(mods)}"
    assert "services/registry/registry_analysis_service.py" in mods


def test_전제_면제는_실재하는_파일만_담는다():
    """죽은 면제도 실패시킨다 — 사라진 파일의 면제가 남으면 목록이 거짓말을 한다."""
    dead = [m for m in _EXEMPT if not (APP / m).exists()]
    assert not dead, f"존재하지 않는 파일의 면제: {dead}"


def test_전제_면제에는_사유가_있다():
    empty = [m for m, why in _EXEMPT.items() if not (why or "").strip()]
    assert not empty, f"사유 없는 면제: {empty}"


def test_핵심_분모를_배선했으면_분자도_배선한다():
    """분모만 있는 모듈은 폴백률 **0%** 로 읽힌다 — 침묵보다 나쁜 거짓 초록이다."""
    violations = [
        m for m, names in _modules_recording_denominator().items()
        if m not in _EXEMPT and not (names & _NUMER)
    ]
    assert not violations, (
        "LLM 실패를 성장루프에 남기지 않는 모듈(폴백률이 거짓 0%가 된다): " + ", ".join(sorted(violations))
    )


def test_핵심_등기는_면제가_아니다():
    """이번 실장애의 당사자다 — 면제로 되돌아가면 같은 사각이 다시 생긴다."""
    assert "services/registry/registry_analysis_service.py" not in _EXEMPT
    names = _identifiers((APP / "services/registry/registry_analysis_service.py").read_text(encoding="utf-8"))
    assert names & _NUMER, "등기 권리분석의 LLM 실패가 다시 집계되지 않는다"
    assert names & _DENOM, "분모(과금 헬퍼)가 빠지면 분자만 남아 폴백률이 100%로 읽힌다"


def test_전제_모든_면제가_실제로_필요하다():
    """★죽은 면제도 결함이다.

    면제를 빼도 위반이 아니라면 그 항목은 **부채 목록을 부풀리는 거짓 기록**이다.
    (초판이 손으로 만든 목록이었고, AST 판정으로 바꾸자 실제 모집단이 달라졌다.)
    """
    denom = _modules_recording_denominator()
    unnecessary = [
        m for m in _EXEMPT
        if m not in denom or (denom[m] & _NUMER)
    ]
    assert not unnecessary, (
        "면제가 필요 없는 모듈(분모를 안 쓰거나 이미 분자를 배선함) — 목록에서 지워라: "
        + ", ".join(sorted(unnecessary))
    )


# ── 실행 락 — 소스 검사는 "쓰여 있나"만 본다. 여기서는 **실제로 적재되는지** 태운다 ──────
import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_핵심_등기_LLM_실패가_실제로_이벤트로_적재된다(monkeypatch):
    """★배선 락은 실행까지 가야 한다.

    소스에 `record_llm_failure` 가 보이는 것과, 실패했을 때 그것이 **불리는 것**은 다르다.
    (임포트만 남기고 호출을 주석 처리하면 소스 검사는 초록이다.)
    """
    from app.services.growth import capture_service as gcap
    from app.services.registry.registry_analysis_service import RegistryAnalysisService

    gcap._QUEUE.clear()

    # LLM 을 확실히 실패시킨다 — `_llm` 의 except 분기를 태우기 위함.
    def _boom(*a, **k):
        raise RuntimeError("의도적 실패(테스트)")

    monkeypatch.setattr("app.services.ai.llm_provider.get_llm", _boom, raising=True)

    out = await RegistryAnalysisService()._llm("경기도 오산시 내삼미동 448-2", "【갑구】…")

    # ① 폴백은 정직하게 실패를 말한다
    assert out["generated"] is False
    assert out["failure_reason"]

    # ② 그 실패가 성장루프 큐에 남는다(분자)
    rows = [r for r in gcap._QUEUE if r.get("event_type") == "llm_call"]
    assert rows, "LLM 실패가 성장루프에 한 줄도 남지 않았다 — 폴백률이 영원히 0%가 된다"
    row = rows[-1]
    assert row.get("service") == "registry"
    assert (row.get("payload") or {}).get("ok") is False
    assert "RuntimeError" in ((row.get("payload") or {}).get("error") or "")

    gcap._QUEUE.clear()


@pytest.mark.asyncio
async def test_대조군_성공은_ok_true_로_적재된다():
    """분모가 실제로 흐르는지 — 이것이 없으면 분자만 쌓여 폴백률이 100%로 읽힌다."""
    from app.services.ai.base_interpreter import record_llm_response_billing
    from app.services.growth import capture_service as gcap

    gcap._QUEUE.clear()

    class _Resp:
        usage_metadata = {"input_tokens": 10, "output_tokens": 20}

    class _LLM:
        model = "claude-x"

    await record_llm_response_billing(_LLM(), _Resp(), service="registry")

    rows = [r for r in gcap._QUEUE if r.get("event_type") == "llm_call"]
    assert rows, "성공 호출이 분모로 적재되지 않는다"
    pl = rows[-1].get("payload") or {}
    assert pl.get("ok") is True
    assert rows[-1].get("service") == "registry"
    # ★성공/실패 페이로드가 **실제로 다른 모양**이어야 한다. 같으면 분기를 없애도 초록이라
    #   "성공만 토큰을 싣는다"는 계약이 무잠금으로 남는다(변이 생존으로 실측했다).
    assert pl.get("input_tokens") == 10
    assert pl.get("output_tokens") == 20
    assert "error" not in pl, "성공 이벤트에 error 가 실렸다 — 실패와 구별되지 않는다"

    gcap._QUEUE.clear()


@pytest.mark.asyncio
async def test_성공과_실패_이벤트는_모양이_다르다(monkeypatch):
    """대조군의 대조군 — 두 경로가 같은 페이로드를 만들면 분기 자체가 장식이다."""
    from app.services.ai.base_interpreter import record_llm_failure, record_llm_response_billing
    from app.services.growth import capture_service as gcap

    gcap._QUEUE.clear()

    class _Resp:
        usage_metadata = {"input_tokens": 3, "output_tokens": 4}

    class _LLM:
        model = "claude-x"

    await record_llm_response_billing(_LLM(), _Resp(), service="svc")
    record_llm_failure("svc", RuntimeError("깨짐"))

    # `_QUEUE` 는 deque 라 슬라이스가 안 된다(실측 TypeError) — list 로 받는다.
    ok_pl, fail_pl = (r.get("payload") or {} for r in list(gcap._QUEUE)[-2:])
    assert ok_pl != fail_pl
    assert ok_pl.get("ok") is True and fail_pl.get("ok") is False
    assert "input_tokens" in ok_pl and "input_tokens" not in fail_pl
    assert "error" in fail_pl and "error" not in ok_pl

    gcap._QUEUE.clear()
