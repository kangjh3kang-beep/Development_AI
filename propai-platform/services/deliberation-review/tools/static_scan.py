"""Phase 0 — 법정/도메인 수치 하드코딩 정적 스캐너(INV-3).

AST 기반 — 할당(=)·증분대입(+=)·주석할당(: T =)·dict 리터럴·**함수기본값·call 키워드인자·튜플언패킹·
튜플/리스트 값**에서 '법정키워드 이름/키 = 수치'를 탐지. 음수(UnaryOp)·지수표기까지 포착(regex 맹점 제거).
함수 시그니처 기본값(예: floor_height_m=3.0)·주입처럼 보이는 call kwarg(build(far_limit=250))도 차단.
허용리스트/일반상수 제외. AT-9류(각 페이즈) 테스트가 src에 대해 호출해 하드코딩 부재를 강제한다.
"""
from __future__ import annotations

import ast

# 법정/도메인 수치를 시사하는 식별자 키워드(부분일치).
_LEGAL_KEYWORDS = (
    "far", "bcr", "height", "area", "limit", "ratio", "floor", "setback", "coverage",
    "threshold", "margin", "distance", "width", "depth", "span", "speed", "hours",
    "exclusion", "relax", "incentive", "tol", "pct", "percent",
)

# (benign 값 면제 제거 — 법정키워드 매칭 식별자는 0/1/1.0 등 benign값도 INV-3 누수이므로 무조건 탐지.
#  측정치/지역변수 false positive는 호출측 allowlist로 제외.)


def _number(node: ast.AST) -> float | int | None:
    """수치 리터럴(음수 UnaryOp 포함) → 값, 아니면 None. bool 제외."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _number(node.operand)
        return -inner if inner is not None else None
    return None


def _numbers(node: ast.AST | None) -> list[float | int]:
    """수치 리터럴 또는 수치만으로 된 튜플/리스트(예: hours=(9,10,11)) → 값 리스트. 아니면 []."""
    if node is None:
        return []
    n = _number(node)
    if n is not None:
        return [n]
    if isinstance(node, (ast.Tuple, ast.List)):
        vals = [_number(e) for e in node.elts]
        if vals and all(v is not None for v in vals):
            return [v for v in vals if v is not None]
    return []


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _fmt(value: float | int) -> str:
    return repr(value) if isinstance(value, float) else str(value)


def scan_for_numeric_legal_constants(source: str, allowlist: tuple[str, ...] = ()) -> list[str]:
    """source에서 하드코딩 의심 수치 할당 목록("name=value") 반환. 없으면 []. 파싱 실패 시 []."""
    hits: list[str] = []
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return hits

    def check(name: str | None, value: float | int) -> None:
        if name is None or name in allowlist:
            return
        # 비법정 식별자는 무관(benign 무의미). 법정키워드 매칭 식별자는 benign값(0/1/1.0 등)도 INV-3 누수 → 면제 없음.
        if any(k in name.lower() for k in _LEGAL_KEYWORDS):
            hits.append(f"{name}={_fmt(value)}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            # 튜플 언패킹: far, bcr = 250, 60 → 이름·값 짝지어 검사.
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Tuple)
                    and isinstance(node.value, ast.Tuple)
                    and len(node.targets[0].elts) == len(node.value.elts)):
                for t, v in zip(node.targets[0].elts, node.value.elts):
                    num = _number(v)
                    if num is not None:
                        check(_name(t), num)
            else:  # 단일 수치 또는 수치 튜플/리스트(hours=(9,10,...)) → 타깃명 기준.
                for t in node.targets:
                    for num in _numbers(node.value):
                        check(_name(t), num)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and node.value is not None:
            for num in _numbers(node.value):
                check(_name(node.target), num)
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    for num in _numbers(v):
                        check(k.value, num)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 함수기본값에 숨은 법정 리터럴(예: floor_height_m=3.0) — 시그니처 사각지대 차단.
            a = node.args
            pos = a.posonlyargs + a.args
            for arg, default in zip(pos[len(pos) - len(a.defaults):], a.defaults):
                for num in _numbers(default):
                    check(arg.arg, num)
            for arg, default in zip(a.kwonlyargs, a.kw_defaults):
                for num in _numbers(default):
                    check(arg.arg, num)
        elif isinstance(node, ast.Call):
            # 호출 키워드 인자(예: build(far_limit=250)) — 주입처럼 보이는 하드코딩 차단.
            for kw in node.keywords:
                if kw.arg is not None:
                    for num in _numbers(kw.value):
                        check(kw.arg, num)
    return hits


# AT-6에서 쓰는 별칭.
static_scan = scan_for_numeric_legal_constants
