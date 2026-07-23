"""Rule DSL 공용 패키지 (v4 계약층 W3-7).

심의엔진(services/deliberation-review) CalcRule 파일럿(app/contracts/calc_rule.py·
canonical_vars.py·enums.py)의 설계를 승격한다. 심의엔진은 독립 마이크로서비스라 직접
import 불가(W3-6 재확증) — 동형 재구현이 아니라 apps/api 전용 공용 패키지로 승격.

공개 API:
- ``contracts``: Unit·Comparator enum, CanonicalVariable, VariableRegistry, RuleContractError.
- ``expr``: 안전한 구조화 산식/조건 노드(VarRef·ParamRef·Const·BinOp) — 문자열 eval 금지.
- ``rule_def``: RuleDef(선언 — 근거조문·입력변수·산식/한도·단위·유효기간).
- ``result``: RuleResult(값+감사가능 trace) — status는 기존 FactStatus(W2-1) 재사용.
- ``evaluate``: evaluate()/evaluate_many() 순수 함수(같은 입력→같은 결과+trace).
"""
from __future__ import annotations
