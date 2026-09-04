"""rfi — RFI(Request for Information) 루프 계약 패키지 (v4.0 Wave3 W3-6).

- rfi_register: RFIItem(구조화 정보요청 1건) + RFIRegister(수집·상태전이 — 불법 전이 거부) +
  emit_rfi(기존 정직 마커에서 1줄 방출 가능한 저마찰 헬퍼).

이번 1차는 계약(방출·상태머신·조회)만 구현한다. 답변 UI/알림(프론트 서피스)은 이월 백로그
"3표식 프론트 서피스"에서 합류하고, DB 영속도 이월 명시(이번 1차는 인메모리 + 안정 직렬화
계약(``to_dict()``)만 제공 — 필요 시 호출부가 기존 원장 구조에 실어 나른다).

RDM(``app.services.provenance.required_data``, W2-4)과의 관계: RDM은 "이 단계에 이 데이터가
얼마나 필요한가"(요구등급 4단계)를 선언하고, RFI는 "그 결측을 실제로 발견한 시점에 구조화
방출 + 해소 추적"을 담당한다 — 서로 다른 축이라 중복이 아니라 RDM 위에 얹는다(RFI severity는
RDM RequirementLevel에서 파생 — 새 어휘 발명 금지).
"""
