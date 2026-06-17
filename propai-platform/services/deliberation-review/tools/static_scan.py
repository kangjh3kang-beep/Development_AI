"""Phase 0 — 법정/도메인 수치 하드코딩 정적 스캐너(INV-3).

AST 기반 — 할당(=)·증분대입(+=)·주석할당(: T =)·dict 리터럴에서 '법정키워드 이름/키 = 수치'를 탐지.
음수(UnaryOp)·dict 값·증분대입·지수표기까지 포착(regex 맹점 제거). 허용리스트/일반상수 제외.
AT-9류(각 페이즈) 테스트가 src에 대해 호출해 하드코딩 부재를 강제한다.
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
            num = _number(node.value)
            if num is not None:
                for t in node.targets:
                    check(_name(t), num)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and node.value is not None:
            num = _number(node.value)
            if num is not None:
                check(_name(node.target), num)
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    num = _number(v)
                    if num is not None:
                        check(k.value, num)
    return hits


# AT-6에서 쓰는 별칭.
static_scan = scan_for_numeric_legal_constants
