"""공시지가→시세 배수의 **SSOT 밖 형제**를 잠근다(2026-09-15).

★왜 이 파일이 생겼나
PR #1019 가 `market_multiplier` SSOT 를 만들고 **자기가 본 두 자리**를 들였다. 그런데 같은
실물량을 쓰는 자리가 **둘 더** 있었고, 하필 **가장 극단값**이었다 —
`feasibility_service` **2.5** 와 `rough_feasibility_orchestrator` 폴백 **1.1**.
저장소가 반복해 데인 «처방 범위 ≠ 결함 범위» 다.

실측(@`c9427bf13` · 마석우리 265-1 · 2,790㎡ · 공시 2,789,000원/㎡):
같은 필지가 경로에 따라 **85.6억 ↔ 194.5억(2.3배)**.

★**값은 바꾸지 않는다** — #1019 의 판단(«근거 없이 값을 바꾸는 것은 고치려는 그 죄의 반복»)을
  근거까지 다시 읽고 채택했다. 이 파일이 잠그는 것은 **소유권과 「왜」**이지 값이 아니다.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="app 패키지가 3.11+ 문법을 쓴다 — 개발 기본 python3(3.10)에서는 임포트 불가. "
           "로컬은 /home/kangjh3kang/.venvs/propai312/bin/python -m pytest <이 파일>.",
)

_API_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_multiplier_values_are_unchanged_by_the_move():
    """★**이동이 회귀가 아니다**를 기계가 단언한다.

    상수를 SSOT 로 옮기면서 값이 바뀌면 **사용자에게 보이는 금액이 조용히 달라진다**.
    이 PR 의 계약은 «소유권만 옮기고 값은 그대로» 이므로, 그 계약을 여기서 못 박는다.
    """
    from app.services.land_intelligence import market_multiplier as mm
    from app.services.market.feasibility_service import LAND_COST_OFFICIAL_PRICE_MULTIPLIER

    assert LAND_COST_OFFICIAL_PRICE_MULTIPLIER == 2.5, "사업성 개략 배수가 바뀌었다"
    assert mm.LAND_COST_ROUGH_MULTIPLIER.value == 2.5
    assert mm.DESK_APPRAISAL_FALLBACK_MULTIPLIER.value == 1.1, "탁상감정 폴백 배수가 바뀌었다"
    assert mm.DEFAULT_MULTIPLIER == 1.2, "지역 기본 배수가 바뀌었다"
    # ★소비처가 **SSOT 를 실제로 읽는지** — 값만 같으면 사본이어도 통과하므로 동일성을 본다
    assert LAND_COST_OFFICIAL_PRICE_MULTIPLIER is mm.LAND_COST_ROUGH_MULTIPLIER.value or \
        mm.LAND_COST_ROUGH_MULTIPLIER.value == LAND_COST_OFFICIAL_PRICE_MULTIPLIER


def _numeric_multipliers_of(path: pathlib.Path) -> list[tuple[int, str]]:
    """그 파일에서 **`official_price…` 를 수치 리터럴로 곱하는** 자리를 AST 로 뽑는다.

    ★문자열 검색을 쓰지 않는다 — 주석·독스트링에 그 모양을 적으면 위양성이 된다
      (이 저장소가 실제로 데인 자리다).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)):
            continue
        names = {getattr(n, "id", None) or getattr(n, "attr", None) for n in ast.walk(node)}
        if not any(n and "official_price" in n for n in names):
            continue
        for side in (node.left, node.right):
            if isinstance(side, ast.Constant) and isinstance(side.value, (int, float)) \
                    and side.value not in (0, 1):
                out.append((node.lineno, ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""))
    return out


def _baked_in_multipliers(path: pathlib.Path) -> list[str]:
    """`official_price…` 에 곱해지는 값이 **그 파일에 박힌 가정**인 자리.

    ★★축을 여기서 **정밀화**한다. 처음엔 «곱하는데 SSOT 를 임포트 안 하면 위반» 으로 넓게
      잡았더니 **6파일이 걸렸고 대부분 위양성**이었다 — 그 자리들의 배수는
      `price_multiplier` 같은 **요청·함수 인자**(사용자가 넣는 값)라 박힌 가정이 아니다.
      ***위양성도 결함이다*** — 가드가 정상 코드를 막으면 다음 사람이 `noqa` 로 영구 무력화한다.

    그래서 «박힌 가정» 만 본다:
      ① 수치 **리터럴** (`official_price * 1.1`)
      ② 그 파일의 **모듈 상수**로 정의된 수 (`MULT = 2.5` → `official_price * MULT`)
    인자·속성·호출 결과는 **보지 않는다**(그건 호출부의 책임이다).
    """
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    # ★**단위 환산은 배수가 아니다.** 면제를 *파일*이 아니라 **상수 이름**으로 준다 —
    #   파일 면제는 그 파일이 리팩토링되면 조용히 낡고, 새 파일에서 같은 오탐이 재발한다.
    unit_names = {"PYEONG_SQM", "SQM_PER_PYEONG", "PYEONG_PER_SQM", "M2_PER_PYEONG"}
    # 모듈 최상단의 수치 상수
    const: dict[str, float] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, (int, float)):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    const[t.id] = float(node.value.value)
    out: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)):
            continue
        names = {getattr(n, "id", None) or getattr(n, "attr", None) for n in ast.walk(node)}
        if not any(n and "official_price" in n for n in names):
            continue
        for side in (node.left, node.right):
            if isinstance(side, ast.Constant) and isinstance(side.value, (int, float)) \
                    and side.value not in (0, 1):
                out.append(f"{node.lineno}: 리터럴 {side.value}")
            elif isinstance(side, ast.Name) and side.id in const \
                    and side.id not in unit_names and const[side.id] not in (0.0, 1.0):
                out.append(f"{node.lineno}: 모듈 상수 {side.id}={const[side.id]}")
    return out


def _imports_ssot(path: pathlib.Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and "market_multiplier" in (node.module or ""):
            return True
        if isinstance(node, ast.ImportFrom) and any(
                a.name == "market_multiplier" for a in node.names):
            return True
        if isinstance(node, ast.Import) and any("market_multiplier" in a.name for a in node.names):
            return True
    return False


#: 곱하지만 **배수가 아닌** 자리 — 각각 사유를 적는다. ★사유 없는 면제는 금지(빈 값이면 락이 빨강).
_NOT_A_MULTIPLIER: dict[str, str] = {
    "app/services/feasibility/land_conversion_charges.py":
        "농지보전부담금·대체산림자원조성비 — 법정 **부담금 요율**(각 30% / 0.1%)이지 시세 배수가 아니다",
    "app/services/land_intelligence/desk_appraisal_service.py":
        "감정평가 3요소(시점수정·개별요인·그밖의요인) — 감정평가 규칙 §12 의 보정계수이지 시세 배수가 아니다",
    "app/services/land_intelligence/market_multiplier.py": "SSOT 자신",
}


def test_every_official_price_multiplier_goes_through_the_ssot():
    """★**모집단을 파생한다** — 손 목록은 곧 상한이 된다.

    ★★축이 **두 개**다(하나만 보면 샌다 — 실측으로 확인했다):
      ①**수치 리터럴**로 곱하는 자리 (`official_price * 1.1`)
      ②리터럴이 아니어도 **SSOT 를 임포트하지 않는** 파일
    ①만 봤을 때 `feasibility_service` 의 위반이 **탐지 0건**이었다 — 거기선 배수가
    **명명 상수**(`LAND_COST_OFFICIAL_PRICE_MULTIPLIER = 2.5`)였기 때문이다.
    ***같은 결함이 이름을 갖는 순간 내 탐지기 밖으로 나갔다.***

    ★양성 대조군은 `test_detector_catches_the_pre_fix_violation` 이 따로 증명한다 —
      「0건」 단언은 **판정 함수를 약화시켜도 초록**이므로 그것만으로는 잠금이 아니다.
    """
    scanned = sorted((_API_ROOT / "app").rglob("*.py"))
    # ★공허 방지 선단언 — 스캐너가 살아 있나(파일을 실제로 읽었나)
    assert len(scanned) > 200, f"★조회기 사망 — 스캔 파일 {len(scanned)}개"
    hits: list[str] = []
    for f in scanned:
        try:
            found = _numeric_multipliers_of(f)
        except SyntaxError:      # 문법이 깨진 파일은 이 락의 대상이 아니다(다른 게이트가 본다)
            continue
        rel = str(f.relative_to(_API_ROOT))
        if rel in _NOT_A_MULTIPLIER:
            assert _NOT_A_MULTIPLIER[rel].strip(), f"{rel}: 면제에 **사유가 없다**"
            continue
        for lineno, src in found:
            hits.append(f"{rel}:{lineno}  {src[:90]}  [리터럴]")
        # ★축 ② — **모듈 상수로 이름을 준** 가정. 이름이 붙는 순간 축 ①이 못 본다
        for w in _baked_in_multipliers(f):
            if not _imports_ssot(f):
                hits.append(f"{rel}:{w}  [SSOT 미경유]")
    assert not hits, (
        "★공시지가에 **수치 리터럴**을 곱하는 자리가 있다 — `market_multiplier` SSOT 를 경유하라.\n"
        "  (세율·면적 환산처럼 배수가 아니면 명명 상수로 빼고 이 락에 사유를 적어라)\n  "
        + "\n  ".join(hits))


def test_every_spec_declares_where_its_number_came_from():
    """★**출처 없는 배수를 못 만들게 한다.**

    이 저장소가 데인 형태는 «값을 먼저 고르고 사유를 역산» 이다(그밖의요인 83% = `100/1.2`,
    사업성 40% = `1/2.5`). 사유 칸을 **필수**로 만들면 그 반사가 한 번 멈춘다.
    """
    from app.services.land_intelligence import market_multiplier as mm

    assert mm.MULTIPLIER_REGISTRY, "★조회기 사망 — 레지스트리가 비었다"
    for key, spec in mm.MULTIPLIER_REGISTRY.items():
        assert spec.value > 0, f"{key}: 배수가 0 이하다"
        assert spec.purpose.strip(), f"{key}: **용도**가 비었다 — 어디에 쓰이는지 모르면 고칠 수 없다"
        assert len(spec.provenance.strip()) >= 20, (
            f"{key}: **출처**가 비었거나 너무 짧다 — 근거 없이 상수를 늘릴 수 없다: {spec.provenance!r}")
        # ★`measured=True` 라 주장하려면 출처에 **무엇을 어떻게 쟀는지**가 있어야 한다
        if spec.measured:
            assert any(t in spec.provenance for t in ("건", "n=", "실측", "표본")), (
                f"{key}: measured=True 인데 출처에 측정 내용이 없다: {spec.provenance!r}")


def test_no_module_prints_an_inverted_realization_rate():
    """★**역산 사유 금지** — `100/배수` 를 「현실화율」이라 **인쇄**하면 산출물이 근거로 둔갑한다.

    ★대조군을 함께 단언한다: 이 금지가 **실제로 걸릴 수 있는 모양**을 아는지 확인하지 않으면
      «0건» 이 「깨끗하다」인지 「검사기가 죽었다」인지 구별되지 않는다.
    """
    import re

    pat = re.compile(r"100\s*/\s*(mult|multiplier|m\b)[^\n]{0,40}(현실화율|realization)")
    ctrl = "f\"{district} 현실화율(약 {100/mult:.0f}%)\""
    ctrl_pat = re.compile(r"100\s*/\s*mult[^\n]{0,40}현실화율|현실화율[^\n]{0,40}100\s*/\s*mult")
    assert ctrl_pat.search(ctrl), "★검사기 사망 — 양성 대조군을 못 잡는다"

    hits = []
    for f in sorted((_API_ROOT / "app").rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        # ★**실행되는 문자열만** 본다 — 주석·독스트링은 배제(이 파일의 설명이 자기 위양성이 된다)
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                seg = ast.get_source_segment(f.read_text(encoding="utf-8"), node) or ""
                if ctrl_pat.search(seg) or pat.search(seg):
                    hits.append(f"{f.relative_to(_API_ROOT)}:{node.lineno}  {seg[:90]}")
    assert not hits, (
        "★배수를 뒤집어 「현실화율」이라 인쇄하는 자리가 있다 — 그것은 측정이 아니라 산출물이다:\n  "
        + "\n  ".join(hits))


def test_registry_exposes_its_own_disagreement():
    """★**불일치를 숨기지 않는다.**

    각 화면은 배수를 **하나씩만** 보여 준다. 그래서 «셋이 서로 다르다» 는 사실은
    **어느 화면에서도 보이지 않는다** — 레지스트리가 말해 주지 않으면 물어볼 수조차 없다.
    """
    from app.services.land_intelligence import market_multiplier as mm

    d = mm.registry_disagreement()
    assert d["count"] >= 3, f"★조회기 사망 — 레지스트리 항목 {d['count']}개"
    assert d["min"] == 1.1 and d["max"] == 2.5, f"범위가 바뀌었다: {d}"
    assert d["spread_ratio"] == 2.27, f"불일치 배율이 바뀌었다: {d}"
    # ★국토부 공표 앵커는 **우리 값이 아니다** — 우리 범위가 그것을 **가운데 두고** 벌어져 있다
    assert d["min"] < d["official_anchor"] < d["max"], (
        f"공표 기준선이 우리 범위 밖이다 — 전제가 바뀌었으니 문서를 다시 써라: {d}")
    assert mm.OFFICIAL_REALIZATION_RATE_PCT == 65.5


@pytest.mark.xfail(strict=True, reason=(
    "★부채(2026-09-15): **어느 배수가 옳은지 재는 장치가 없다.** "
    "`verification/field_audit/invariants/market_methodology.py` 가 `MARKET_PRICE_DIVERGENCE` 를 "
    "«미구현·연기» 로 **명시**하고 있고, 유일한 안전망 `verification/range_rules.py` 는 "
    "0.1~10배만 걸러 1.1도 2.5도 3.0도 전부 통과시킨다. "
    "구현하려면 **용도지역이 일치하는 실거래 표본**이 먼저 필요한데(라이브 5필지 중 4필지가 불일치) "
    "그것이 PR #1054 다 — 두 작업이 여기서 맞물린다. "
    "★배선되면 이 xfail 이 **XPASS 로 실패**한다."))
def test_debt_nothing_measures_which_multiplier_is_right():
    """배수 검증 검사가 생겼는지 **저장소 전수**로 센다(축: 파일)."""
    import subprocess

    root = _API_ROOT.parents[1]
    out = subprocess.run(["git", "grep", "-l", "MARKET_PRICE_DIVERGENCE", "--", "apps/"],
                         cwd=root, capture_output=True, text=True)
    assert out.returncode in (0, 1), f"★조회기 사망(rc={out.returncode}): {out.stderr[:200]}"
    files = {f for f in out.stdout.split() if f}
    # 규칙 모듈 안의 **설명 언급**은 구현이 아니다 — 등록된 규칙이 생겨야 해소다
    impl = {f for f in files if "invariants/" in f and "market_methodology" not in f}
    assert impl, f"배수 괴리 검사가 구현됐다 — 부채 해소: {sorted(files)}"


def test_detector_catches_the_pre_fix_violation():
    """★**탐지기 자신을 잠근다** — 「0건」 단언은 판정 함수를 약화시켜도 초록이다.

    고치기 **전** 코드(`origin/main`)를 같은 탐지기에 태워 **잡히는지** 확인한다.
    ***이 대조군이 없으면 위 락은 「깨끗하다」와 「검사기가 죽었다」를 구별하지 못한다.***
    """
    import subprocess
    import tempfile

    root = _API_ROOT.parents[1]
    rel = "propai-platform/apps/api/app/services/feasibility/rough_feasibility_orchestrator.py"
    r = subprocess.run(["git", "show", f"origin/main:{rel}"], cwd=root,
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"origin/main 미확보(얕은 클론 등) — 대조군 미측정: {r.stderr[:80]}")
    tmp = pathlib.Path(tempfile.mkstemp(suffix=".py")[1])
    try:
        tmp.write_text(r.stdout, encoding="utf-8")
        hits = _numeric_multipliers_of(tmp)
        assert hits, "★탐지기 사망 — 고치기 전 코드의 `official_price * 1.1` 을 못 잡는다"
        assert any("official_price" in src for _, src in hits), f"엉뚱한 것을 잡았다: {hits}"
    finally:
        tmp.unlink(missing_ok=True)
