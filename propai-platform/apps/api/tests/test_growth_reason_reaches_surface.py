"""진단 사유가 **마지막 한 층에서 사라진다** — 같은 패턴 3건.

## 왜 이 셋이 한 파일인가

**1·2 번은 뿌리가 하나**다:
**사유·상태가 만들어져 저장까지 되는데, 사람이 읽는 마지막 층에서 버려지거나 가려진다.**

★★**3번은 그 뿌리가 아니다**(독립 적대 렌즈 실측 2026-09-02 · AST 확인).
  `note_coverage` 는 가려진 이름 `withheld` 를 **본문에서 한 번도 값으로 쓰지 않는다**(전수 0건).
  실제 `withheld()` 호출 3건은 **파라미터가 없는 다른 함수**(`_classify_quality`)에 있다.
  즉 3번은 **만들어졌다가 버려진 것이 아니라 「아직 터지지 않은 잠복 위험」**이고,
  이것 때문에 **틀린 출력이 나간 적은 없다.**
  → *"같은 뿌리 3건"* 이라고 뭉치면 리뷰어가 **하나를 표본으로 보고 일반화**한다.
    1·2 를 고쳐도 3 은 아무것도 말해 주지 않는다. **묶지 않고 따로 적는다.**

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
    # ★★**칸을 본다 — 문자열 전체가 아니라**(독립 적대 렌즈 재검증 2026-09-02).
    #   `"미측정" in n` 은 **공허하다**: 프로덕션의 보류 사유 산문 자체가 그 낱말을 쓴다
    #   (`analyzer.py` "…미달합니다(**미측정**이며 0% 가 아닙니다)"). 그래서 지표 칸을
    #   `"미상"` 으로 바꾸는 변이를 넣어도 **이 단언은 통과**한다 — 사유 꼬리에서 낱말이
    #   공급되기 때문이다. **내가 쓴 안내문이 내 단언을 공허하게 만든** 그 형태다.
    assert A._metric_text(ins["metrics_json"], "down_pct") == "미측정", (
        "★보류된 지표의 **칸**이 「미측정」이 아니다 — 문자열 어딘가의 낱말로는 못 잠근다"
    )
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
    # ★**판정된 쪽도 칸으로 못 박는다**(음성 대조군의 강화).
    #   ★★**귀속 정정**(렌즈 재검증 2026-09-02): 종전 주석은 *"이 락 단독 실행에서
    #     SURVIVED"* 라고 적었는데 **거짓이었다** — 그 측정은 **위쪽
    #     `test_withheld_metric_never_reaches_the_reader_as_none`** 에 대한 것이고,
    #     이 테스트는 **판정된 경로**라 그 변이의 영향을 받지 않는다.
    #     내가 렌즈의 측정을 **엉뚱한 테스트에 갖다 붙였다.** 공허했던 단언은 위쪽에 있고,
    #     거기서 따로 고쳤다. 이 줄은 그 자체로는 유용하지만 **그 결함의 처방이 아니다.**
    assert A._metric_text(
        _quality_ins(fail=24, warn=5, verify_total=38, down=6, feedback_total=10)["metrics_json"],
        "down_pct",
    ) == "60.0%", "★판정된 지표의 칸이 숫자가 아니다"
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
            # ★**허용형**으로 판정한다(금지 목록형 금지).
            #   독립 리뷰(2026-08-27) 실증: `IfExp` 하나만 거부하면 **삼키는 다른 방법이
            #   전부 초록**이다 — `_coerce(fr[2])` · `fr[2] or None` · `_only_dict(fr[2])`.
            #   특히 `or None` 은 **한 글자로 원래 결함을 되살리는데** 금지형은 못 잡는다.
            #   → *"조건식이 아니다"* 가 아니라 *"**맨 첨자/이름**이다"* 로 뒤집으면
            #     세 우회가 전부 빨개진다(리뷰 제안 · 복제 실측으로 확인).
            assert isinstance(kw.value, ast.Subscript | ast.Name), (
                f"value= 가 맨 첨자/이름이 아니다({type(kw.value).__name__}) — "
                "형변환·조건식·함수 경유는 전부 삼킬 수 있다")
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


def test_no_analyzer_name_shadows_a_module_level_import():
    """★**파생형 · AST** — `analyzer.py` 의 **전 함수**를 잠근다(이 한 함수만이 아니라).

    문자열 검사로는 못 한다 — 이 파일의 설명 문장에 그대로 걸린다(§판정은 파서로).

    ★★**범위를 사실대로 좁혀 적는다**(독립 적대 렌즈 실측 2026-09-02).
      종전 문구는 *"이 결함 클래스 **전체**를 잠근다"* 였는데 **거짓이었다** — 이 락은
      `analyzer.py` **한 파일**만 읽는다. 같은 규칙을 `apps/api/app` 전체(809파일)에
      돌리면 **10건**이 나온다.
      ★그리고 그중 일부는 **결함이 아니다** — `unit_mix_optimizer._optimize_slsqp(np, minimize)`
        는 지연 임포트한 모듈을 호출부가 넘기는 **의도된 의존성 주입**이다.
        즉 이 규칙을 저장소 전역에 그대로 걸면 **위양성을 낸다**(위양성도 결함이다).
      → 넓히려면 **DI 허용 목록과 사유**가 함께 있어야 한다. 그 전까지는 **범위를 정직하게**
        적고, 넓히는 것은 별건으로 둔다.
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

    # ★★**파라미터만 보면 절반이다**(독립 적대 리뷰 실측 2026-09-02).
    #   종전 이 락은 `args` 만 읽어서 **지역 대입 그림자**를 못 봤다 — 실제로 같은 파일에
    #   `withheld = ...` 지역 대입이 **3함수 6줄** 살아 있었고, 그중 하나는 보류 지표를
    #   **생산하는** 함수(`_analyze_quality_drop`)라 그 헬퍼의 가장 유력한 미래 호출부였다.
    #   락 이름이 *"전 함수를 잠근다"* 였는데 실제로는 *"전 함수의 **파라미터**"* 였다.
    #   → **대입(Store)까지** 센다. 둘 다 같은 사고(헬퍼가 이름으로 가려짐)를 낸다.
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in imported:
            offenders.append(f"지역대입 {node.id} @{node.lineno}")
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


# ═══════════════════════════════════════════════════════════════════════════
# ★★L11 — **라우터를 실제로 태운다**(독립 적대 렌즈 실측 2026-09-02)
#
# 위 L7 은 호출 지점의 **AST 모양**(`value=` 인자가 `Subscript` 인가)만 본다.
# 렌즈가 **한 줄 위에서 강제 변환**하는 변이를 넣자 **40건 전부 초록**이었다:
#
#     for fr in [(r[0], r[1], r[2] if isinstance(r[2], dict) else None, ...) for r in flag_rows]
#
# 호출 지점은 여전히 `value=fr[2]` 라 모양 검사는 통과하는데, 모든
# `growth_last_run.*` 워터마크가 다시 `None` 이 된다 — **이 PR 이 고쳤다고 선언한 그 상태**다.
#
# ★그리고 실측: `heal_log` 를 **실행하는 테스트가 저장소에 0건**이었다(파서로 확인 ·
#   대조군으로 같은 스캐너가 다른 호출들을 찾음). 유일한 「히트」는 독스트링 산문이었다.
#   → *"부른다를 잠그면 아무것도 안 잠긴다 — **행위**를 태워라."*
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_heal_log_does_not_swallow_string_watermarks_END_TO_END(monkeypatch) -> None:
    """★엔드포인트를 **실행**해 문자열 워터마크가 살아 나오는지 본다.

    두 모집단을 **같은 실행에서** 태운다 — 문자열은 문자열로 살고, dict 는 dict 로 산다.
    한쪽만 보면 *"전부 통과시키는 구현"* 과 *"올바른 구현"* 이 구별되지 않는다.

    되살리는 변이: 라우터 어디서든 `isinstance(..., dict) else None` 강제 변환을 넣으면 죽는다
    (호출 지점이든 **그 위 한 줄이든** — 모양이 아니라 결과를 보므로).
    """
    from app.routers import growth as gr

    async def _ok_admin(request, db):        # 관리자 가드는 이 테스트의 대상이 아니다
        return "admin"

    monkeypatch.setattr(gr, "_require_admin", _ok_admin)

    # ★★**모집단을 손으로 고르지 않는다 — 쓰기 쪽 선언에서 파생한다.**
    #   (독립 적대 리뷰 실측 2026-09-02) 종전 이 테스트는 `str`·`dict` **둘만** 손으로 골랐다.
    #   그런데 쓰기 쪽 `SettingIn.value` 는 **여섯 타입**을 받는다. 손 목록이 **상한**이 되어
    #   `list` 가 **HTTP 500**(ValidationError)을, `int` 가 **float 로 변형**되는 것을
    #   둘 다 못 봤다 — 이 저장소가 반복해서 데인 *"손으로 나열한 목록이 곧 상한"* 이다.
    #   → **쓰기 타입에서 표본을 만든다.** 쓰기가 한 타입을 더 받게 되면 이 테스트가
    #     **자동으로** 그것을 태운다(새 타입이 감시망에 저절로 들어온다).
    import typing as _t

    from app.routers.growth import SettingIn

    _writer_types = {
        a for a in _t.get_args(SettingIn.model_fields["value"].annotation)
        if a is not type(None)
    }
    # ★대조군 — 파생이 죽으면 아래가 공허해진다(빈 집합도 "전부 통과"다)
    assert len(_writer_types) >= 5, f"★쓰기 타입 파생이 죽었다: {_writer_types}"

    _sample = {dict: {"timeout_multiplier": 1.5}, list: ["a", "b"], str: "s",
               int: 5, float: 1.5, bool: True}
    missing = _writer_types - set(_sample)
    assert not missing, f"★쓰기가 새 타입을 받는데 표본이 없다: {missing} — 표본을 추가하라"

    watermark = "2026-08-27T06:05:00+00:00"
    flag_rows = [
        # ★모집단 A — 평문 문자열 워터마크(`schedule.py` 가 isoformat() 로 쓴다)
        ("growth_last_run.analyze", "global", watermark, None, "growth-scheduler"),
        # ★모집단 B — dict 값(종전 구현이 유일하게 통과시키던 것)
        ("relax.molit", "global", {"timeout_multiplier": 1.5}, None, "healer"),
    ] + [
        # ★모집단 C — **쓰기가 받는 나머지 전부**(파생). 하나라도 읽기가 거부하면 500 이다.
        (f"writer.{t.__name__}", "global", _sample[t], None, "w")
        for t in sorted(_writer_types, key=lambda x: x.__name__)
    ]

    class _Res:
        def __init__(self, rows=None, scalar=0):
            self._rows, self._scalar = rows or [], scalar
        def fetchall(self): return self._rows
        def scalar(self): return self._scalar

    class _Db:
        def __init__(self): self.n = 0
        async def execute(self, *a, **k):
            self.n += 1
            if self.n == 1:
                return _Res(scalar=0)          # COUNT(*)
            if self.n == 2:
                return _Res(rows=[])           # heal_action 이력(이 테스트의 대상 아님)
            return _Res(rows=flag_rows)        # platform_settings 활성 플래그

    out = await gr.heal_log(request=object(), db=_Db())
    got = {f.key: f.value for f in out.active_flags}

    # ★대조군 먼저 — 모집단이 실제로 응답에 들어왔나(공허한 초록 방지)
    expected = {"growth_last_run.analyze", "relax.molit"} | {
        f"writer.{t.__name__}" for t in _writer_types
    }
    assert set(got) == expected, f"★플래그가 안 실렸다: {set(got) ^ expected}"

    # ★쓰기가 받는 **모든** 타입이 읽기에서 살아 나온다 — 하나라도 거부하면 엔드포인트가
    #   통째로 500 이라 actions·active_flags·total 이 **함께** 사라진다.
    for t in _writer_types:
        assert got[f"writer.{t.__name__}"] == _sample[t], (
            f"★쓰기가 받는 {t.__name__} 가 읽기에서 변형·거부됐다: "
            f"{got[f'writer.{t.__name__}']!r} != {_sample[t]!r}"
        )

    # ①문자열이 **문자열 그대로** 살아 나온다 — 여기가 종전 결함 자리
    assert got["growth_last_run.analyze"] == watermark, (
        "★문자열 워터마크가 삼켜졌다 — 운영자가 「축이 도는가」를 "
        "「한 번도 안 돌았다」와 구별할 수 없게 된다"
    )
    # ②dict 도 **dict 그대로** 산다(과잉 교정이 아님을 같은 실행에서 증명)
    assert got["relax.molit"] == {"timeout_multiplier": 1.5}, "★dict 가 망가졌다(과잉 교정)"


def test_absent_code_is_translated_not_leaked_as_raw_enum():
    """★영문 enum 이 **한국어 독자에게 그대로** 가지 않는다 — 세 모집단.

    `withheld()` 는 **쓰기 시점**에 사유 문장을 강제하지만 **읽기 시점엔 아무도 강제하지 않는다.**
    그래서 `_basis` 가 없는 **저장된 옛 행**이나 문장을 안 넣는 미래 생산자는
    코드값이 그대로 새어 나갔다 — 예: `※ down_pct insufficient_coverage`.

    되살리는 변이: `ABSENT_REASONS.get(...)` 을 지우면 이 테스트가 죽는다
    (종전에는 그 자리를 되돌려도 **17건 전부 초록**이었다 — 렌즈 실측).
    """
    from app.utils.withheld import ABSENT_REASONS

    # ★대조군 0 — 사전이 살아 있나(비면 아래 단언이 공허하다)
    assert ABSENT_REASONS, "★ABSENT_REASONS 가 비었다 — 조회기가 죽었다(위반 아님)"
    korean = ABSENT_REASONS["insufficient_coverage"]

    def _note(metrics):
        return A._withheld_note(metrics)

    # ①`_basis` 없음 + 알려진 코드 → **한국어 문장**으로 번역된다
    n1 = _note({"down_pct": None, "down_pct_absent": "insufficient_coverage", "service": "x"})
    assert "insufficient_coverage" not in n1, f"★영문 enum 이 그대로 새어 나갔다: {n1}"
    assert korean in n1, f"★한국어 사유가 안 실렸다: {n1}"

    # ②`_basis` 가 있으면 **그것이 이긴다**(과잉 교정이 아님 — 두 번째 모집단)
    mine = "verify 표본 3건으로 최소 5건에 미달합니다."
    n2 = _note({"down_pct": None, "down_pct_absent": "insufficient_coverage",
                "down_pct_basis": mine, "service": "x"})
    assert mine in n2 and korean not in n2, f"★명시 사유가 사전에 덮였다: {n2}"

    # ③**모르는 코드**는 원값 유지(사전에 없다고 삼키지 않는다 — 세 번째 모집단)
    n3 = _note({"down_pct": None, "down_pct_absent": "zzz_unknown_code", "service": "x"})
    assert "zzz_unknown_code" in n3, f"★모르는 코드를 삼켰다: {n3}"
