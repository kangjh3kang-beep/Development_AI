"""규범 상수 표는 **근거 없이 새로 생길 수 없다** (2026-08-23 · `#760`→`#774` 일반화).

## 왜 래칫인가

`#760` 이 `MAX_FLOORS` 하나를 고쳤고, `#774` 가 **같은 파일의 형제 두 표**를 고쳤다.
그런데 형제를 손으로 찾는 방식은 **다음 표를 놓친다** — 이 저장소가 반복해 데인 형태다
(*"목록형이 아니라 전수/파생형으로 쓴다. 사람이 센 목록이 곧 상한이 된다."*).

그래서 **모집단을 코드에서 파생**시킨다: 규범 판정 소관 패키지 안에서
**값이 원시 숫자인 dict 상수**를 AST 로 전수 수집한다. 이미 근거를 지닌 타입
(`LegalLimit`/`PracticeLimit`)으로 감싼 표는 **구조적으로 수집되지 않는다** —
즉 상환하면 모집단에서 자동으로 빠진다.

## 이 파일이 잠그는 것

1. 새 원시 규범 표가 **조용히** 생기지 않는다(등재 없이는 실패)
2. 등재된 부채는 **사유를 지닌다**(뭉뚱그리지 않는다)
3. 상환된 표가 등재부에 **죽은 채 남지 않는다**
4. ★수집기가 **타입 적용 여부를 실제로 가른다**(양성·음성 대조군)

## ★이 래칫의 **경계** — 안 보는 것을 먼저 적는다

모집단은 위 `NORMATIVE_ROOTS` **패키지 안**으로 한정했다. 그래서 다음은 **안 본다**:

· 규범값이 규범 패키지 **밖**에 살면(예: `feasibility/` 안의 법정 한도) 수집되지 않는다
· dict 가 아닌 형태(모듈 상수 스칼라·리스트·클래스 속성)는 수집되지 않는다
· 값이 함수 호출·컴프리헨션으로 만들어지면(근거 타입이 아니어도) 수집되지 않는다

★"전수"라고 부르지 않는 이유다. 커버리지를 **표 수**로 세면 통과하고 **표현 형태**로 세면
구멍이 보인다 — 그 구멍을 여기 적어 두어야 다음 사람이 *"이미 전수 감사됐다"* 로 오독하지 않는다.

## ★근거가 '어디에 사는가'를 함께 적는다

수집된 표 상당수는 근거가 **주석·이웃 상수**에 있다(`_LEGAL_BASIS_BCR`·`FLOOR_CAP_BASIS`).
사람에겐 보이지만 **주석은 지워져도 아무 테스트도 울지 않는다**(규율 C10).
값과 함께 다니는 근거(타입)와 옆에 적힌 근거(주석)는 **강도가 다르다** — 등재부에 구분해 적는다.
"""

from __future__ import annotations

import ast
import pathlib
import re

# 규범 판정 소관 — 이 아래의 숫자는 계획을 깎거나 부적합을 만든다.
NORMATIVE_ROOTS = (
    "app/services/zoning/",
    "app/services/permit/",
    "app/services/legal/",
    "app/services/land_intelligence/ordinance_service.py",
)

#: 근거를 값과 함께 지니는 타입 — 이걸로 감싸면 모집단에서 빠진다.
SOURCED_TYPES = {"LegalLimit", "PracticeLimit"}

API_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _is_raw_numeric(node: ast.expr) -> bool:
    """값이 **원시 숫자**인가(근거를 지닌 호출이 아니라)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_raw_numeric(node.operand)
    if isinstance(node, ast.Dict):
        return bool(node.values) and all(_is_raw_numeric(v) for v in node.values)
    if isinstance(node, ast.Tuple):
        return bool(node.elts) and all(_is_raw_numeric(e) for e in node.elts)
    return False


def collect_raw_normative_tables() -> dict[str, int]:
    """`{"경로::이름": 항목수}` — 규범 패키지 안의 **원시 숫자 dict 상수** 전수."""
    found: dict[str, int] = {}
    for path in sorted((API_ROOT / "app").rglob("*.py")):
        rel = path.relative_to(API_ROOT).as_posix()
        if not any(rel.startswith(r) or rel == r for r in NORMATIVE_ROOTS):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - 파싱 불가 파일은 대상이 아니다
            continue
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if not isinstance(target, ast.Name):
                continue
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", target.id):
                continue
            value = node.value
            if not isinstance(value, ast.Dict) or not value.keys:
                continue
            numeric = sum(1 for v in value.values if _is_raw_numeric(v))
            # 값의 과반이 원시 숫자면 '수치 표'로 본다(혼합 표도 잡는다).
            if numeric == 0 or numeric < len(value.values) * 0.6:
                continue
            found[f"{rel}::{target.id}"] = len(value.values)
    return found


# ── 등재부 — **부채는 사유를 지닌다** ────────────────────────────────────────
#
# 형식: "경로::이름": "근거가 어디에 사는가 + 왜 아직 타입이 아닌가"
#
# ★상환 방법: 값을 `LegalLimit`(법정) 또는 `PracticeLimit`(실무)로 감싸고 여기서 지운다.
#   그러면 수집기가 더는 잡지 않는다(구조적으로 모집단에서 빠진다).
NORMATIVE_DEBT: dict[str, str] = {
    # ★2026-08-24 상환 3건 — 근거가 **주석·이웃 상수**에 살던 표를 타입으로 옮겼다.
    #   `ZONE_FAR_MIN`(시행령 §85) · `GROWTH_MGMT_BCR_CEILING`·`GROWTH_MGMT_FAR_CEILING`
    #   (법 §75의3제2·3항). 감싸는 순간 수집기가 더는 잡지 않아 **여기서 자동으로 빠진다**.
    #   ★상환 순서는 "조문이 이미 확인된 것" 우선이다 — 확인 안 된 값에 조문을 붙이는 것은
    #     이 축이 막으려던 날조 그 자체다(그런 항목은 사유를 그대로 두고 남겼다).
    "app/services/zoning/far_incentive_calculator.py::NATIONAL_FAR_LIMITS": (
        "용도지역별 법정 용적률 상한. 조문 근거 미확인 — **확인 전에는 감싸지 않는다**"
        "(없는 근거를 지어내는 것이 이 축이 막으려던 잘못이다)"
    ),
    "app/services/zoning/far_incentive_calculator.py::ALPHA_COEFFICIENTS": (
        "인센티브 계수 — 법정인지 실무인지 먼저 판별해야 한다(등급을 모르면 감쌀 수 없다)"
    ),
    "app/services/zoning/far_optimization_simulator.py::GSEED_BONUS_PCT": (
        "녹색건축인증 용적률 완화폭. 고시 근거 미확인 — 시뮬레이터 전용이라 부적합을 내지 않는다"
    ),
    "app/services/zoning/far_optimization_simulator.py::ENERGY_GRADE_BONUS_PCT": (
        "에너지효율등급 용적률 완화폭. 고시 근거 미확인 — 시뮬레이터 전용이라 부적합을 내지 않는다"
    ),
    "app/services/zoning/far_optimization_simulator.py::USE_BASED_FAR": (
        "용도별 용적률 가정치 — 시뮬레이터 입력 가정이지 법정 상한이 아니다"
    ),
    "app/services/permit/building_code_rules.py::ZONE_DEFAULTS": (
        "`#763` 이 `LEGAL_KEYS`/`ORDINANCE_KEYS` 로 **출처를 갈랐으나** 값 자체는 여전히 원시 숫자다. "
        "그 분류를 타입으로 승격하는 것이 다음 단계"
    ),
    "app/services/land_intelligence/ordinance_service.py::NATIONAL_LIMITS": (
        "전국 기본 법정 한도. 조례가 덮어쓰는 **기본값**이라 등급이 '법정'인지 '기본가정'인지 판별 필요"
    ),
    "app/services/land_intelligence/ordinance_service.py::ORDINANCE_CACHE": (
        "조례 조회 실패 시의 캐시 시드 — 규범값이 아니라 **데이터 캐시**다. "
        "규범 패키지에 살아서 수집되지만 성격이 다르다(분류만 하고 감싸지 않는다)"
    ),
    "app/services/legal/precedence_resolver.py::AUTHORITY_ORDER": (
        "법령 위계 **순서**(숫자가 크기가 아니라 순위)다. 제약값이 아니므로 감싸지 않는다"
    ),
}


def test_새_원시_규범표가_조용히_생기지_않는다() -> None:
    """★핵심 래칫 — 등재 없이 새 표가 들어오면 여기서 걸린다."""
    found = collect_raw_normative_tables()
    # ★공허 진리 방지 — 수집기가 죽으면 '위반 0'이 자동으로 참이 된다.
    assert len(found) >= 8, (
        f"규범 표를 {len(found)}개밖에 못 모았다 — 수집기가 죽었거나 경로가 바뀌었다: {sorted(found)}"
    )
    unregistered = sorted(set(found) - set(NORMATIVE_DEBT))
    assert unregistered == [], (
        "근거도 등재도 없는 원시 규범 표가 있다. "
        "`LegalLimit`/`PracticeLimit` 로 감싸거나 NORMATIVE_DEBT 에 사유와 함께 등재하라: "
        f"{unregistered}"
    )


def test_죽은_부채를_남기지_않는다() -> None:
    """상환했으면 등재부에서도 지운다 — 남으면 래칫이 거짓말한다."""
    found = collect_raw_normative_tables()
    stale = sorted(set(NORMATIVE_DEBT) - set(found))
    assert stale == [], f"등재부에만 있고 코드엔 없다 — 상환됐거나 이름이 바뀌었다: {stale}"


def test_부채_사유가_비어있지_않다() -> None:
    for key, reason in NORMATIVE_DEBT.items():
        assert len(reason) > 25, f"{key} 의 사유가 너무 짧다 — 부채를 뭉뚱그리지 마라"


def test_수집기가_타입_적용을_실제로_가른다_대조군() -> None:
    """★양성·음성 대조군 — 위 세 락은 *아무것도 수집하지 않는* 구현에서도 초록이다.

    이미 상환된 표(`MAX_FLOORS`·`MIN_LOT_AREA`·`ROAD_REQUIREMENT`)가 **수집되지 않고**,
    아직 원시인 표(`NATIONAL_FAR_LIMITS`)는 **수집되는지** 함께 본다.
    두 모집단이 다른 값을 내야 이 수집기가 잠금 노릇을 한다.
    """
    found = collect_raw_normative_tables()
    validator = "app/services/zoning/development_feasibility_validator.py"
    repaid = [f"{validator}::{n}" for n in ("MAX_FLOORS", "MIN_LOT_AREA", "ROAD_REQUIREMENT")]
    repaid += [
        "app/services/zoning/legal_zone_limits.py::ZONE_FAR_MIN",
        "app/services/zoning/conditional_legal_ceiling.py::GROWTH_MGMT_BCR_CEILING",
        "app/services/zoning/conditional_legal_ceiling.py::GROWTH_MGMT_FAR_CEILING",
    ]
    for name in repaid:
        assert name not in found, (
            f"{name} 은 근거를 지닌 타입으로 감쌌는데도 수집됐다 — 수집기가 타입을 못 가른다"
        )
    # ★대조군은 **아직 원시인 표**여야 한다. `ZONE_FAR_MIN` 을 상환하며 이 자리가 죽었고
    #   (상환하면 수집되지 않으므로) 다른 원시 표로 갈아 끼웠다 — 대조군이 상환과 함께
    #   조용히 무력해지는 것을 여기서 잡았다.
    assert "app/services/zoning/far_incentive_calculator.py::NATIONAL_FAR_LIMITS" in found, (
        "아직 원시인 표가 수집되지 않았다 — 수집기가 아무것도 안 잡고 있다(공허한 초록)"
    )


def test_상환하면_모집단에서_빠진다_경로확인() -> None:
    """★상환 경로가 **실제로 동작하는지** 합성 코드로 태운다(문서만 그럴듯한 것 방지)."""
    raw = ast.parse('X: dict[str, int] = {"a": 1, "b": 2}\n').body[0]
    wrapped = ast.parse(
        'X: dict[str, LegalLimit] = {"a": LegalLimit(1, law="건축법 §44①")}\n'
    ).body[0]
    assert isinstance(raw, ast.AnnAssign) and isinstance(raw.value, ast.Dict)
    assert isinstance(wrapped, ast.AnnAssign) and isinstance(wrapped.value, ast.Dict)
    assert all(_is_raw_numeric(v) for v in raw.value.values), "원시 표를 원시로 못 본다"
    assert not any(_is_raw_numeric(v) for v in wrapped.value.values), (
        "감싼 표를 여전히 원시로 본다 — 상환해도 모집단에서 안 빠진다"
    )
    # 감싸는 타입 이름이 실제로 존재하는지(문서-코드 괴리 방지)
    from app.services.legal import legal_limit as m

    for t in SOURCED_TYPES:
        assert hasattr(m, t), f"{t} 가 없다 — 이 파일이 말하는 상환 경로가 실재하지 않는다"
