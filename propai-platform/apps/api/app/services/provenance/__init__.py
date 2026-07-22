"""provenance — 외부 수집 추적성 계약 패키지 (v4.0 Wave2 W2-1).

- source_snapshot: 외부 API 원본 응답 불변 스냅샷 + dead-letter.
- fact_status: Fact 신뢰상태 어휘(OBSERVED/DERIVED/ASSUMED/INFERRED/CONFLICT/UNKNOWN/STALE).

이번 1차는 계약(스냅샷 저장·상태 어휘)만 구현한다. 값 단위 계보(ReportClaim→...→SourceSnapshot)
로 실제 소비 배선을 잇는 것은 W2-2(필드수준 계보) 범위다.
"""
