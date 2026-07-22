"""provenance — 외부 수집 추적성 계약 패키지 (v4.0 Wave2 W2-1~W2-4).

- source_snapshot: 외부 API 원본 응답 불변 스냅샷 + dead-letter.
- fact_status: Fact 신뢰상태 어휘(OBSERVED/DERIVED/ASSUMED/INFERRED/CONFLICT/UNKNOWN/STALE).
- lineage_ref: 필드수준 계보 참조 계약(W2-2).
- handoff_bundle: 단계 인계(Stage Handoff) 번들 계약(W2-3).
- required_data: 원본자료 충족도 Required Data Matrix 계약 — 요구등급 4단계(required/
  conditionally_required/recommended/reference_only) × 상태 6종을 판정해 종합 decision을
  산출한다(W2-4).

이번 1차는 계약(스냅샷 저장·상태 어휘·매트릭스 판정)만 구현한다. 값 단위 계보(ReportClaim→
...→SourceSnapshot)로 실제 소비 배선을 잇는 것은 W2-2 이후 점진 채택 범위다.
"""
