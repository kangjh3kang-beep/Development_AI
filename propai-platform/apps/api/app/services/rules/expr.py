"""안전한 구조화 산식 노드 — 문자열 eval/exec 절대 금지(무목업 원칙).

산식은 Python 코드 문자열이 아니라 JSON 직렬화 가능한 구조화 노드 트리로 표현한다.
평가는 화이트리스트 연산자(_SAFE_OPS)만 수행하며, 임의 함수 호출·속성 접근·임포트가
불가능하다(AST 구문 자체가 이런 연산을 표현할 수 없음 — 구조적으로 안전).

노드 4종:
- ``VarRef`` : 입력 변수 참조(런타임 inputs dict에서 조회).
- ``ParamRef``: 규칙 파라미터 참조(RuleDef.params — 임계치 하드코딩 금지 주입처, INV-11 계승).
- ``Const``  : 리터럴 상수.
- ``BinOp``  : 이항연산(add/sub/mul/div/min/max — 전부 화이트리스트 고정).

평가 결과는 값이 결손이면(None) 조용히 0/기본값으로 대체하지 않고 None(UNKNOWN)을
그대로 전파한다(무날조 원칙 — 심의엔진 CalcEngine INV-12와 동일 시맨틱).
"""
from __future__ import annotations

import operator
from typing import Annotated, Literal

from pydantic import BaseModel, Field

_BinOpCode = Literal["add", "sub", "mul", "div", "min", "max"]


def _safe_div(a: float, b: float) -> float | None:
    if b == 0:
        return None  # 0으로 나눔 — 무음 fallback 금지, UNKNOWN 전파.
    return a / b


# 화이트리스트 연산자만 — 임의 함수 호출 경로 없음(구조적 안전, eval/exec 미사용).
_SAFE_OPS: dict[str, object] = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "div": _safe_div,
    "min": min,
    "max": max,
}


class VarRef(BaseModel):
    kind: Literal["var"] = "var"
    name: str


class ParamRef(BaseModel):
    kind: Literal["param"] = "param"
    name: str


class Const(BaseModel):
    kind: Literal["const"] = "const"
    value: float


class BinOp(BaseModel):
    kind: Literal["binop"] = "binop"
    op: _BinOpCode
    left: Expr
    right: Expr


Expr = Annotated[VarRef | ParamRef | Const | BinOp, Field(discriminator="kind")]
BinOp.model_rebuild()


class ExprTraceStep(BaseModel):
    """산식 평가 1단계(감사가능 trace) — 어느 노드·어느 값."""

    node: str  # 예: "var:building_area_sqm" / "binop:div" / "const"
    value: float | None


def eval_expr(
    node: Expr,
    inputs: dict[str, float | None],
    params: dict[str, float],
    trace: list[ExprTraceStep] | None = None,
) -> float | None:
    """구조화 산식 노드를 순수 함수로 평가한다(같은 입력→같은 결과).

    입력/파라미터 결손·0나눔은 None(UNKNOWN)으로 전파한다(날조 금지). trace가 주어지면
    방문한 모든 노드의 중간값을 순서대로 기록한다(감사가능성).
    """
    result: float | None
    if node.kind == "var":
        result = inputs.get(node.name)
        if trace is not None:
            trace.append(ExprTraceStep(node=f"var:{node.name}", value=result))
        return result
    if node.kind == "param":
        result = params.get(node.name)
        if trace is not None:
            trace.append(ExprTraceStep(node=f"param:{node.name}", value=result))
        return result
    if node.kind == "const":
        if trace is not None:
            trace.append(ExprTraceStep(node="const", value=node.value))
        return node.value
    if node.kind == "binop":
        left = eval_expr(node.left, inputs, params, trace)
        right = eval_expr(node.right, inputs, params, trace)
        if left is None or right is None:
            result = None  # 피연산자 결손 — UNKNOWN 전파(무날조).
        else:
            fn = _SAFE_OPS[node.op]
            result = fn(left, right)  # type: ignore[operator]
        if trace is not None:
            trace.append(ExprTraceStep(node=f"binop:{node.op}", value=result))
        return result
    raise ValueError(f"unsupported expr node kind: {node.kind}")  # pragma: no cover — 판별 유니온으로 도달 불가


__all__ = ["BinOp", "Const", "Expr", "ExprTraceStep", "ParamRef", "VarRef", "eval_expr"]
