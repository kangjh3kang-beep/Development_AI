"""승인 상태머신(approval) 공용 계약 패키지 — v4.0 명세 P13(W1-A).

site_basis(artifact_status)·design_runs(DRAFT/APPROVED)·run_state(RunStateEnum) 세 원형이
각자 만들어 둔 "승인 상태머신"을 재작성하지 않고, 하나의 공용 어휘(ApprovalState)로 추출한다.
이 패키지는 3원형 코드를 참조만 하고 절대 변경하지 않는다(그린필드 금지 — 관통 전략).
"""
