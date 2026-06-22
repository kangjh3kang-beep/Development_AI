"""심의/설계도면 자동분석 엔진 BFF 서비스 패키지.

엔진(services/deliberation-review)은 패키지명 `app` 충돌로 직접 import 불가 →
BFF가 HTTP로 호출한다. 이 패키지는 계약 미러링(_engine_contract)과
run_id↔테넌트 결속·멱등(binding_service)을 담당한다.
"""
