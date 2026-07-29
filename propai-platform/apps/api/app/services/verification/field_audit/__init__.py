"""field_audit — 도메인 correctness 자가검증 하네스(신경-기호 자가검증 Phase0).

현행 `verification/`(range_rules·calc_ledger·verifier_service)는 grounding·정직성·
결정론 산식 재계산이라는 '하한선'을 잡는다. field_audit은 그 위에 도메인 correctness
'상한선'(규제→리스크 하한 매핑·POI dedup·매트릭스 커버리지·시세 방법론·토지속성 조합)을
불변식(pure fn)으로 얹어, `analyze()` 주경로가 라이브·IDE에서 잡히는 오류를 스스로
잡도록 하는 게이트다.

★비대칭 계약(neuro proposes / symbolic disposes): 이 패키지는 symbolic(dispose) 쪽.
  이미 계산된 result(결정론 파생값)를 '규칙에 맞는가'로만 판정하며 값을 생산하지 않는다.

W0(Phase0) 범위 = 계약·골격·골든 기준선·주경로 배선만. **규칙은 0건(no-op)** — 실제
불변식은 W1부터 등록된다. behavior 불변·additive가 절대 원칙(analyze() 출력에 'field_audit'
키 하나만 추가).

공개 계약:
  - contracts.AuditFinding / AuditReport
  - rules_registry.register_audit_rule / iter_rules
  - runner.run(result, ctx) -> AuditReport  (result["field_audit"] 부착)
"""

from app.services.verification.field_audit.contracts import (
    AuditFinding,
    AuditReport,
)

__all__ = ["AuditFinding", "AuditReport"]
