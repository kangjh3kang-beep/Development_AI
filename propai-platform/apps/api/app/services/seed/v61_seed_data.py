"""v61 시드 데이터 — 2026 법정요율, 표준단가, 인허가 도서, 공종 분류."""

from __future__ import annotations

from datetime import date
from typing import Any


def seed_legal_rates_2026() -> list[dict[str, Any]]:
    """2026년 법정요율 12개 시드 데이터.
    출처: 국토교통부공고2024-1782호 + 고용노동부고시2025."""
    return [
        {"rate_category": "산재보험_건설업", "rate_value": 0.035000, "effective_from": date(2026, 1, 1), "gov_notice_no": "고용노동부고시2025-001"},
        {"rate_category": "고용보험_실업급여", "rate_value": 0.009000, "effective_from": date(2026, 1, 1), "gov_notice_no": "고용노동부고시2025-001"},
        {"rate_category": "건강보험_사업주", "rate_value": 0.035950, "effective_from": date(2026, 1, 1), "gov_notice_no": "건강보험공단2026"},
        {"rate_category": "국민연금_사업주", "rate_value": 0.047500, "effective_from": date(2026, 1, 1), "gov_notice_no": "국민연금법개정2025"},
        {"rate_category": "장기요양보험료", "rate_value": 0.004724, "effective_from": date(2026, 1, 1), "gov_notice_no": "건강보험공단2026"},
        {"rate_category": "퇴직공제부금비", "rate_value": 0.021000, "effective_from": date(2026, 1, 1), "gov_notice_no": "건설근로자공제회"},
        {"rate_category": "간접노무비율", "rate_value": 0.144000, "effective_from": date(2026, 1, 1), "gov_notice_no": "국토교통부공고2024-1782"},
        {"rate_category": "일반관리비율", "rate_value": 0.055000, "effective_from": date(2026, 1, 1), "gov_notice_no": "국토교통부공고2024-1782"},
        {"rate_category": "이윤상한", "rate_value": 0.150000, "effective_from": date(2026, 1, 1), "gov_notice_no": "국토교통부공고2024-1782"},
        {"rate_category": "안전보건관리비", "rate_value": 0.020700, "effective_from": date(2026, 1, 1), "gov_notice_no": "고용노동부고시2025"},
        {"rate_category": "환경보전비", "rate_value": 0.001600, "effective_from": date(2026, 1, 1), "gov_notice_no": "환경부고시2025"},
        {"rate_category": "부가가치세", "rate_value": 0.100000, "effective_from": date(2026, 1, 1), "gov_notice_no": "부가가치세법"},
    ]


def seed_standard_prices_2026() -> list[dict[str, Any]]:
    """2026 표준단가 42개 시드 (표준품셈2025 + 시장단가)."""
    return [
        # 철근콘크리트
        {"material_code": "RC-001", "material_name": "레미콘 25-240-15", "spec": "25MPa, 슬럼프 150", "unit": "m³", "material_price": 82000, "labor_price": 35000, "expense_price": 8000},
        {"material_code": "RC-002", "material_name": "레미콘 30-240-15", "spec": "30MPa, 슬럼프 150", "unit": "m³", "material_price": 87000, "labor_price": 35000, "expense_price": 8000},
        {"material_code": "RC-003", "material_name": "레미콘 35-240-15", "spec": "35MPa, 슬럼프 150", "unit": "m³", "material_price": 93000, "labor_price": 36000, "expense_price": 8500},
        {"material_code": "RC-004", "material_name": "이형철근 SD400 D10", "spec": "SD400, D10", "unit": "ton", "material_price": 920000, "labor_price": 280000, "expense_price": 45000},
        {"material_code": "RC-005", "material_name": "이형철근 SD400 D13", "spec": "SD400, D13", "unit": "ton", "material_price": 900000, "labor_price": 260000, "expense_price": 42000},
        {"material_code": "RC-006", "material_name": "이형철근 SD400 D16", "spec": "SD400, D16", "unit": "ton", "material_price": 880000, "labor_price": 250000, "expense_price": 40000},
        {"material_code": "RC-007", "material_name": "이형철근 SD500 D25", "spec": "SD500, D25", "unit": "ton", "material_price": 950000, "labor_price": 240000, "expense_price": 38000},
        {"material_code": "RC-008", "material_name": "거푸집 합판", "spec": "유로폼 600×1200", "unit": "m²", "material_price": 18000, "labor_price": 32000, "expense_price": 5000},
        {"material_code": "RC-009", "material_name": "시스템 거푸집", "spec": "알루미늄 시스템", "unit": "m²", "material_price": 8000, "labor_price": 25000, "expense_price": 4000},
        # 방수
        {"material_code": "WP-001", "material_name": "아스팔트 방수", "spec": "개량 아스팔트 시트", "unit": "m²", "material_price": 12000, "labor_price": 15000, "expense_price": 3000},
        {"material_code": "WP-002", "material_name": "우레탄 방수", "spec": "2액형 우레탄", "unit": "m²", "material_price": 15000, "labor_price": 12000, "expense_price": 2500},
        {"material_code": "WP-003", "material_name": "시트 방수", "spec": "PVC 시트 1.5t", "unit": "m²", "material_price": 18000, "labor_price": 14000, "expense_price": 3000},
        # 창호
        {"material_code": "WW-001", "material_name": "AL 이중창", "spec": "T-Bar 24mm 복층", "unit": "m²", "material_price": 120000, "labor_price": 35000, "expense_price": 8000},
        {"material_code": "WW-002", "material_name": "시스템 창호", "spec": "3중 유리 시스템", "unit": "m²", "material_price": 180000, "labor_price": 45000, "expense_price": 10000},
        {"material_code": "WW-003", "material_name": "커튼월", "spec": "SSG 커튼월", "unit": "m²", "material_price": 350000, "labor_price": 80000, "expense_price": 25000},
        # 타일/석재
        {"material_code": "TL-001", "material_name": "바닥 타일", "spec": "600×600 포세린", "unit": "m²", "material_price": 25000, "labor_price": 22000, "expense_price": 4000},
        {"material_code": "TL-002", "material_name": "외벽 석재", "spec": "화강석 30T", "unit": "m²", "material_price": 85000, "labor_price": 45000, "expense_price": 12000},
        # 도장
        {"material_code": "PT-001", "material_name": "수성페인트", "spec": "KS M 6010 2급", "unit": "m²", "material_price": 3500, "labor_price": 8000, "expense_price": 1500},
        # 기계설비
        {"material_code": "ME-001", "material_name": "에어컨 실외기", "spec": "시스템 에어컨 5HP", "unit": "대", "material_price": 3500000, "labor_price": 350000, "expense_price": 80000},
        {"material_code": "ME-002", "material_name": "배관 (동관)", "spec": "φ15A 동관", "unit": "m", "material_price": 12000, "labor_price": 18000, "expense_price": 3000},
        # 전기
        {"material_code": "EL-001", "material_name": "전선 HIV 2.5sq", "spec": "HIV 600V 2.5mm²", "unit": "m", "material_price": 1200, "labor_price": 3500, "expense_price": 500},
        {"material_code": "EL-002", "material_name": "분전반", "spec": "MCC 20회로", "unit": "면", "material_price": 450000, "labor_price": 120000, "expense_price": 25000},
        # 조경
        {"material_code": "LS-001", "material_name": "소나무", "spec": "H4.0×R15", "unit": "주", "material_price": 350000, "labor_price": 80000, "expense_price": 30000},
        {"material_code": "LS-002", "material_name": "잔디", "spec": "한국잔디 떼붙이기", "unit": "m²", "material_price": 5000, "labor_price": 8000, "expense_price": 2000},
        {"material_code": "LS-003", "material_name": "투수블록", "spec": "200×100×60", "unit": "m²", "material_price": 18000, "labor_price": 15000, "expense_price": 3000},
        # 토목
        {"material_code": "CV-001", "material_name": "PHC 파일", "spec": "φ400 A종", "unit": "m", "material_price": 45000, "labor_price": 35000, "expense_price": 15000},
        {"material_code": "CV-002", "material_name": "흙막이 H형강", "spec": "H-300×300×10×15", "unit": "m", "material_price": 120000, "labor_price": 55000, "expense_price": 20000},
        # 가설
        {"material_code": "TMP-001", "material_name": "비계 (강관)", "spec": "강관비계 외부", "unit": "m²", "material_price": 3000, "labor_price": 12000, "expense_price": 2000},
        {"material_code": "TMP-002", "material_name": "가설울타리", "spec": "C형강 + 샌드위치패널", "unit": "m", "material_price": 35000, "labor_price": 25000, "expense_price": 5000},
        {"material_code": "TMP-003", "material_name": "타워크레인", "spec": "T/C 10ton급", "unit": "월", "material_price": 0, "labor_price": 0, "expense_price": 8500000},
    ]


def seed_permit_documents() -> list[dict[str, Any]]:
    """인허가 도서 37개 메타데이터."""
    return [
        # A: 건축계획서
        {"doc_code": "A-01", "doc_category": "A", "doc_name": "건축계획서 (개요)"},
        {"doc_code": "A-02", "doc_category": "A", "doc_name": "건축계획서 (구조계획)"},
        {"doc_code": "A-03", "doc_category": "A", "doc_name": "건축계획서 (설비계획)"},
        {"doc_code": "A-04", "doc_category": "A", "doc_name": "건축계획서 (소방계획)"},
        {"doc_code": "A-05", "doc_category": "A", "doc_name": "건축계획서 (조경계획)"},
        # B: 설계도면
        {"doc_code": "B-01", "doc_category": "B", "doc_name": "배치도"},
        {"doc_code": "B-02-B3", "doc_category": "B", "doc_name": "지하3층 평면도"},
        {"doc_code": "B-02-B2", "doc_category": "B", "doc_name": "지하2층 평면도"},
        {"doc_code": "B-02-B1", "doc_category": "B", "doc_name": "지하1층 평면도"},
        {"doc_code": "B-02-01", "doc_category": "B", "doc_name": "1층 평면도"},
        {"doc_code": "B-02-STD", "doc_category": "B", "doc_name": "기준층 평면도"},
        {"doc_code": "B-02-TOP", "doc_category": "B", "doc_name": "최상층 평면도"},
        {"doc_code": "B-02-RF", "doc_category": "B", "doc_name": "옥상층 평면도"},
        {"doc_code": "B-03-E", "doc_category": "B", "doc_name": "동측 입면도"},
        {"doc_code": "B-03-W", "doc_category": "B", "doc_name": "서측 입면도"},
        {"doc_code": "B-03-S", "doc_category": "B", "doc_name": "남측 입면도"},
        {"doc_code": "B-03-N", "doc_category": "B", "doc_name": "북측 입면도"},
        {"doc_code": "B-04-L", "doc_category": "B", "doc_name": "종단면도"},
        {"doc_code": "B-04-T", "doc_category": "B", "doc_name": "횡단면도"},
        {"doc_code": "B-05", "doc_category": "B", "doc_name": "구조평면도"},
        {"doc_code": "B-06-01", "doc_category": "B", "doc_name": "기계설비도 (급배수)"},
        {"doc_code": "B-06-02", "doc_category": "B", "doc_name": "기계설비도 (공조)"},
        {"doc_code": "B-07-01", "doc_category": "B", "doc_name": "전기설비도 (간선)"},
        {"doc_code": "B-07-02", "doc_category": "B", "doc_name": "전기설비도 (조명)"},
        {"doc_code": "B-07-03", "doc_category": "B", "doc_name": "전기설비도 (소방)"},
        # C: 3D/일영
        {"doc_code": "C-01-SE", "doc_category": "C", "doc_name": "투시도 (남동방향)"},
        {"doc_code": "C-01-NE", "doc_category": "C", "doc_name": "투시도 (북동방향)"},
        {"doc_code": "C-02-F", "doc_category": "C", "doc_name": "조감도 (정면)"},
        {"doc_code": "C-04-S", "doc_category": "C", "doc_name": "일조분석 (하지)"},
        {"doc_code": "C-04-W", "doc_category": "C", "doc_name": "일조분석 (동지)"},
        # D: 토목/구조
        {"doc_code": "D-01", "doc_category": "D", "doc_name": "토목공사도"},
        # E: 에너지
        {"doc_code": "E-01", "doc_category": "E", "doc_name": "에너지절약계획서"},
        {"doc_code": "E-02", "doc_category": "E", "doc_name": "건축물에너지효율등급"},
        {"doc_code": "E-03", "doc_category": "E", "doc_name": "제로에너지건축물 인증"},
        # F: 소방
        {"doc_code": "F-01", "doc_category": "F", "doc_name": "소방시설 설계설명서"},
        {"doc_code": "F-02", "doc_category": "F", "doc_name": "소방시설 배치도"},
        # G: 접근성
        {"doc_code": "G-01", "doc_category": "G", "doc_name": "장애물없는생활환경 인증"},
    ]


def seed_work_types() -> list[dict[str, Any]]:
    """5대 공종 + 하위 공종 계층."""
    return [
        # 대분류
        {"work_code": "A", "work_name": "건축공사", "parent_code": None, "work_level": 0, "work_category": "건축", "sort_order": 1},
        {"work_code": "B", "work_name": "기계설비공사", "parent_code": None, "work_level": 0, "work_category": "기계", "sort_order": 2},
        {"work_code": "C", "work_name": "전기설비공사", "parent_code": None, "work_level": 0, "work_category": "전기", "sort_order": 3},
        {"work_code": "D", "work_name": "조경공사", "parent_code": None, "work_level": 0, "work_category": "조경", "sort_order": 4},
        {"work_code": "E", "work_name": "토목공사", "parent_code": None, "work_level": 0, "work_category": "토목", "sort_order": 5},
        # 건축 하위
        {"work_code": "A01", "work_name": "철근콘크리트공사", "parent_code": "A", "work_level": 1, "work_category": "건축", "sort_order": 10},
        {"work_code": "A02", "work_name": "철골공사", "parent_code": "A", "work_level": 1, "work_category": "건축", "sort_order": 11},
        {"work_code": "A03", "work_name": "조적공사", "parent_code": "A", "work_level": 1, "work_category": "건축", "sort_order": 12},
        {"work_code": "A04", "work_name": "방수공사", "parent_code": "A", "work_level": 1, "work_category": "건축", "sort_order": 13},
        {"work_code": "A05", "work_name": "미장/타일공사", "parent_code": "A", "work_level": 1, "work_category": "건축", "sort_order": 14},
        {"work_code": "A06", "work_name": "창호/유리공사", "parent_code": "A", "work_level": 1, "work_category": "건축", "sort_order": 15},
        {"work_code": "A07", "work_name": "도장공사", "parent_code": "A", "work_level": 1, "work_category": "건축", "sort_order": 16},
        {"work_code": "A08", "work_name": "목공사", "parent_code": "A", "work_level": 1, "work_category": "건축", "sort_order": 17},
        {"work_code": "A09", "work_name": "지붕/금속공사", "parent_code": "A", "work_level": 1, "work_category": "건축", "sort_order": 18},
        # 기계 하위
        {"work_code": "B01", "work_name": "급배수·위생공사", "parent_code": "B", "work_level": 1, "work_category": "기계", "sort_order": 20},
        {"work_code": "B02", "work_name": "공조·환기공사", "parent_code": "B", "work_level": 1, "work_category": "기계", "sort_order": 21},
        {"work_code": "B03", "work_name": "소방기계공사", "parent_code": "B", "work_level": 1, "work_category": "기계", "sort_order": 22},
        # 전기 하위
        {"work_code": "C01", "work_name": "전력간선공사", "parent_code": "C", "work_level": 1, "work_category": "전기", "sort_order": 30},
        {"work_code": "C02", "work_name": "조명·콘센트공사", "parent_code": "C", "work_level": 1, "work_category": "전기", "sort_order": 31},
        {"work_code": "C03", "work_name": "소방전기공사", "parent_code": "C", "work_level": 1, "work_category": "전기", "sort_order": 32},
        # 조경 하위
        {"work_code": "D01", "work_name": "식재공사", "parent_code": "D", "work_level": 1, "work_category": "조경", "sort_order": 40},
        {"work_code": "D02", "work_name": "포장/시설물공사", "parent_code": "D", "work_level": 1, "work_category": "조경", "sort_order": 41},
        # 토목 하위
        {"work_code": "E01", "work_name": "토공사/기초공사", "parent_code": "E", "work_level": 1, "work_category": "토목", "sort_order": 50},
        {"work_code": "E02", "work_name": "흙막이/지반공사", "parent_code": "E", "work_level": 1, "work_category": "토목", "sort_order": 51},
    ]
