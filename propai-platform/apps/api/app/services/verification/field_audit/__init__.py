"""field_audit — 도메인 correctness 자가검증 하네스(신경-기호 자가검증 Phase0).

현행 `verification/`(range_rules·calc_ledger·verifier_service)는 grounding·정직성·
결정론 산식 재계산이라는 '하한선'을 잡는다. field_audit은 그 위에 도메인 correctness
'상한선'(규제→리스크 하한 매핑·POI dedup·매트릭스 커버리지·시세 방법론·토지속성 조합)을
불변식(pure fn)으로 얹어, `analyze()` 주경로가 라이브·IDE에서 잡히는 오류를 스스로
잡도록 하는 게이트다.

★비대칭 계약(neuro proposes / symbolic disposes): 이 패키지는 symbolic(dispose) 쪽.
  이미 계산된 result(결정론 파생값)를 '규칙에 맞는가'로만 판정하며 값을 생산하지 않는다.

W1(Phase0)부터 계층 A 하드 불변식이 등록된다 — W1-1: cross_field.G1(protection_zone_severity
보호구역→리스크 하한). 패키지 임포트가 invariants를 임포트해 규칙을 자동 등록한다(runner는
analyze() 주경로에서 이 패키지를 임포트하므로 프로덕션에서 규칙이 활성화된다). behavior 불변·
additive는 유지 원칙(analyze() 출력에 'field_audit' 키 하나만 추가·규칙은 판정만·값 미생산).

공개 계약:
  - contracts.AuditFinding / AuditReport
  - rules_registry.register_audit_rule / iter_rules
  - runner.run(result, ctx) -> AuditReport  (result["field_audit"] 부착)
"""

from app.services.verification.field_audit import invariants  # noqa: F401  임포트 부작용=W1 규칙 등록
from app.services.verification.field_audit.contracts import (
    AuditFinding,
    AuditReport,
)

__all__ = ["AuditFinding", "AuditReport", "invariants"]
