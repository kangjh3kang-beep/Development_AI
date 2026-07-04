"""F-Parcel 파운데이션 — 대량 다필지 배치 계층.

기존 단일 필지 해석 primitive(VWorldService, ParcelExcelService 규칙)를
그대로 재사용하면서, 그 위에 "여러 필지를 한 번에 처리하는 배치 계층"만
가산(additive)한다. 단일 동기 경로는 전혀 건드리지 않는다.
"""
