"""P5 측량·좌표 계약(Survey / CoordinateContract) 패키지.

DXF(설계·측량 도면)의 지적 좌표와 지도(GIS) 좌표를 오가며 정합을 검증한다.
좌표 변환은 공용 헬퍼(build_crs_transformer)를 재사용하고, 이 패키지는
계약 모델(coordinate_contract)과 대조 리포트(coordinate_service)만 새로 얹는다.
DB 스키마·마이그레이션은 만들지 않는다(모델·리포트 수준).
"""
