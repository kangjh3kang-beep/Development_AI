"""진단 사유가 **마지막 한 층에서 사라진다** — 같은 패턴 3건.

## 왜 이 셋이 한 파일인가

세 결함은 파일도 층도 다르지만 **뿌리가 하나**다:
**사유·상태가 만들어져 저장까지 되는데, 사람이 읽는 마지막 층에서 버려지거나 가려진다.**

| # | 어디서 | 무엇이 사라졌나 |
|---|---|---|
| 1 | `analyzer._rule_narrative` | `#861` 이 만든 보류 사유(`<field>_basis`)가 안 실리고 **`None%`** 가 나갔다 |
| 2 | `routers/growth.py` `ActiveFlagOut` | 문자열 워터마크(`growth_last_run.*`)를 **`None` 으로 위장** |
| 3 | `analyzer.note_coverage` | 파라미터 `withheld: int` 가 `withheld()` **헬퍼를 가려** 계약 호출이 물리적으로 불가 |

## 라이브 근거 (2026-08-27)

- 활성 플래그 6건 중 **4건**(`growth_last_run.*`)이 `value: null` 로 보였다 —
  운영자가 *"성장 축이 도는가"* 를 물을 때 **가장 먼저 보는 값**이
  「한 번도 안 돌았다」와 **구별 불가**였다.
- 그 질문은 가설이 아니다: 측정 시점 최신 인사이트가 **172분 전**이었고
  시간당 발화가 기대값이었다. 즉 **이 위장이 실제 진단을 막고 있었다.**
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.services.growth import analyzer as A

_API = Path(__file__).resolve().parents[1]


# ══════════════════════════════════════════════════════════════════════
# ① narrative 가 보류값을 숫자 자리에 흘리지 않는다 — **전 타입 × 두 모집단**
# ══════════════════════════════════════════════════════════════════════

def _quality_ins(**kw):
    sev, m = A._classify_quality(**kw)
    return {"insight_type": "quality_drop", "severity": sev,
            "metrics_json": dict(m, service="site_analysis")}


def test_withheld_metric_never_reaches_the_reader_as_none():
    """보류 → 숫자 자리에 `None` 이 아니라 **미측정**, 그리고 **사유가 실린다**."""
    ins = _quality_ins(fail=24, warn=5, verify_total=38, down=0, feedback_total=0)
    n = A._rule_narrative(ins)
    assert "None%" not in n and "None" not in n, n
    assert "미측정" in n
    # ★사유가 **실제로** 실렸는가 — 없으면 「말은 바꿨는데 이유는 여전히 버림」이다
    assert "표본" in n and "미달" in n, n


def test_judged_population_still_shows_the_real_number():
    """★음성 대조군 — 과잉 억제 방지. 표본이 충분하면 **숫자가 그대로** 나와야 한다.

    이게 없으면 "전부 미측정으로 찍기"라는 정반대 구현도 위 테스트를 통과한다.
    """
    n = A._rule_narrative(_quality_ins(fail=24, warn=5, verify_total=38,
                                       down=6, feedback_total=10))
    assert "60.0%" in n, n
    assert "미측정" not in n
    assert "※" not in n, "보류가 없는데 사유 꼬리가 붙었다(과잉)"


def test_every_narrative_branch_gets_the_reason_tail():
    """★**파생형** — 사유 부착이 타입 목록이 아니라 **단일 길목**에 걸렸는지.

    본문 반환 지점이 일곱이라 손으로 붙이면 하나를 빠뜨린다(#886 이 같은 이유로
    호출부 단일 길목을 골랐다). `_rule_narrative` 가 본문과 **분리**돼 있고
    모든 타입에서 꼬리가 붙는지를 **타입을 코드에서 파생시켜** 확인한다.
    """
    from app.services.growth.insight_types import INSIGHT_TYPES

    assert len(INSIGHT_TYPES) >= 6, "모집단이 비었다(공허한 참 방지)"
    withheld_m = {"down_pct": None, "down_pct_absent": "insufficient_coverage",
                  "down_pct_basis": "판정 보류 — 표본 부족"}
    for t in INSIGHT_TYPES:
        n = A._rule_narrative({"insight_type": t, "severity": "warn",
                               "metrics_json": dict(withheld_m)})
        assert "※" in n, f"{t} 에 사유 꼬리가 안 붙었다 — 단일 길목이 아니다"
        assert "판정 보류" in n, f"{t} 에 사유 본문이 안 실렸다"


def test_reason_tail_groups_identical_bases():
    """같은 사유의 두 필드가 **두 번 반복되지 않는다**(헤드라인 오염 방지)."""
    n = A._rule_narrative(_quality_ins(fail=0, warn=0, verify_total=0,
                                       down=0, feedback_total=0))
    assert n.count("※") == 1
    assert "fail_pct·warn_pct" in n, "같은 사유의 필드가 묶이지 않았다"


@pytest.mark.parametrize("payload,expect_tail", [
    # 진짜 보류: 값이 없고 사유가 붙었다 → 사유를 싣는다
    ({"down_pct": None, "down_pct_absent": "insufficient_coverage"}, True),
    # ★값이 **있는데** 사유 표식만 남은 계약 위반(낡은 마커) → 「미측정」이라 말하면 안 된다
    ({"down_pct": 5.0, "down_pct_absent": "insufficient_coverage"}, False),
    # 사유 표식이 비어 있으면 보류가 아니다
    ({"down_pct": None, "down_pct_absent": ""}, False),
    # 아무 표식도 없다
    ({"down_pct": 5.0}, False),
])
def test_reason_tail_only_for_genuinely_withheld_fields(payload, expect_tail):
    """★**과잉 부착 방향**을 잠근다 — 한쪽만 걸면 반대 방향이 원리적으로 탐지 불가다.

    `is_withheld` 게이트를 없애는 변이가 실제로 **생존**해서 추가한 락이다:
    값이 있는 필드에까지 「미측정」을 붙이면, 이 PR 이 고치려던 바로 그 거짓말
    (숫자 자리에 사실이 아닌 것을 넣는다)을 **반대 방향으로** 저지르게 된다.
    """
    note = A._withheld_note(payload)
    assert bool(note) is expect_tail, note


# ══════════════════════════════════════════════════════════════════════
# ② 라우터가 스칼라 플래그 값을 삼키지 않는다
# ══════════════════════════════════════════════════════════════════════

def test_active_flag_accepts_the_string_watermark():
    """`growth_last_run.*` 는 **문자열**이다 — dict 만 받으면 통째로 None 이 된다."""
    from app.routers.growth import ActiveFlagOut

    f = ActiveFlagOut(key="growth_last_run.analyze", scope="global",
                      value="2026-08-27T06:05:00+00:00", updated_by="growth-scheduler")
    assert f.value == "2026-08-27T06:05:00+00:00", "문자열 워터마크가 사라졌다"
    # 양성 대조군: dict 도 여전히 받는다(회귀 아님)
    assert ActiveFlagOut(key="k", scope="global", value={"a": 1}).value == {"a": 1}


def test_router_does_not_coerce_non_dict_to_none():
    """★배선 — 스키마만 넓히고 라우터가 계속 삼키면 아무것도 안 고쳐진다.

    ★**판정을 파서로 한다.** 첫 판에서 이 락을 문자열 검사로 썼다가
    **내가 이 파일과 라우터에 적은 설명 주석이 옛 코드를 그대로 인용**하는 바람에
    스스로 빨개졌다 — 「내가 쓴 안내문이 내 단언을 공허하게(혹은 거짓으로) 만든다」의
    교과서적 재발이다. AST 로 `ActiveFlagOut(value=…)` 인자가 **조건식이 아닌지**만 본다.
    """
    src = (_API / "app" / "routers" / "growth.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    checked = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "ActiveFlagOut"):
            continue
        for kw in node.keywords:
            if kw.arg != "value":
                continue
            checked += 1
            assert not isinstance(kw.value, ast.IfExp), \
                "value= 가 조건식이다 — 비-dict 를 삼키고 있다"
    assert checked == 1, f"ActiveFlagOut(value=…) 호출을 {checked}건 찾았다(1건이어야)"


def test_watermark_writer_really_writes_a_string():
    """★전제 확인 — 워터마크가 문자열이 **아니라면** 위 수정은 근거가 없다."""
    src = (_API / "app" / "services" / "growth" / "schedule.py").read_text(encoding="utf-8")
    assert "now.isoformat()" in src, "워터마크가 문자열이 아니다 — 전제 재확인 필요"
    assert "growth_last_run." in src


# ══════════════════════════════════════════════════════════════════════
# ③ 파라미터가 모듈 임포트를 가리지 않는다 — **AST 파생**(문자열 검사 아님)
# ══════════════════════════════════════════════════════════════════════

def test_note_coverage_no_longer_shadows_the_withheld_helper():
    sig = inspect.signature(A.note_coverage)
    assert "withheld" not in sig.parameters, "헬퍼 이름을 파라미터가 가린다"
    assert "withheld_count" in sig.parameters
    assert callable(A.withheld), "모듈 헬퍼가 사라졌다"


def test_emitted_coverage_key_is_still_the_contract_name():
    """★개명은 **파라미터만**이다 — 발행 키는 `metrics_json` 계약이라 그대로여야 한다."""
    cov: dict = {}
    A.note_coverage(cov, "ax", judged=0, withheld_count=5, floor=10)
    assert cov["ax"]["withheld"] == 5, "계약 키가 바뀌었다(화면·재고 행과 어긋난다)"
    assert "withheld_count" not in cov["ax"], "파라미터 이름이 payload 로 새어 나갔다"


def test_no_analyzer_parameter_shadows_a_module_level_import():
    """★**파생형 · AST** — 이 결함 클래스 전체를 잠근다(이 한 함수만이 아니라).

    문자열 검사로는 못 한다 — 이 파일의 설명 문장에 그대로 걸린다(§판정은 파서로).
    """
    src = (_API / "app" / "services" / "growth" / "analyzer.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported |= {(a.asname or a.name) for a in node.names}
        elif isinstance(node, ast.Import):
            imported |= {(a.asname or a.name.split(".")[0]) for a in node.names}
    assert imported, "임포트를 하나도 못 찾았다 — 파서가 죽었다(공허한 참 방지)"

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        args = node.args
        names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
        for bad in names & imported:
            offenders.append(f"{node.name}({bad})")
    assert not offenders, f"임포트를 가리는 파라미터: {offenders}"


@pytest.mark.parametrize("field,expect", [("down_pct", "미측정"), ("nope", "미상")])
def test_metric_text_partitions_withheld_from_merely_missing(field, expect):
    """★보류(사유 있음)와 **그냥 없음**은 다른 말이어야 한다 — 뭉치면 진단이 안 된다."""
    m = {"down_pct": None, "down_pct_absent": "insufficient_coverage"}
    assert A._metric_text(m, field) == expect
