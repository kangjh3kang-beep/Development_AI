# Phase0-A 백엔드: baseline 수지 422 해소 (zone 폴백 + 약식주소 정규화)

대상: `propai-platform/apps/api/app/routers/v2_feasibility.py` (백엔드 단독)
원칙: 무목업·라이브검증. push/배포 금지. git add 명시경로만.

## 근본원인 (라이브 확정)
1. **zone_code 폐기**: baseline이 프론트가 보낸 `zone_code`(용도지역명)를 무시하고
   `zone_type`만 읽음. → 프론트가 zone_code로 보내면 `get_permitted_types("")` = `[]` →
   항상 "용도지역 미상" 폴백(M06, confidence penalty) + FAR/BCR 법정상한 미반영.
2. **약식주소 지오코딩 실패**: "서울 강남구 역삼동 1" 같은 약식 시도명은 VWorld 지오코딩
   실패 → 면적 자동감지 불가 → `land_area_sqm=0` → 422. 완전주소("서울특별시…736")는 200.

## 구현 (3건)

### 1) zone 폴백 통합
`zone = (req.zone_type or req.zone_code)` 단일 변수로 통합. baseline 내 모든 사용처
(허용유형 판정 `get_permitted_types(zone)`, dev_type 자동선택 assumption, FAR 역산)를
`zone`으로 교체. zone_code/zone_type 둘 다 수용.
- 추가: 자동감지로 `zone_limits`를 못 얻은 경우(자동감지 미수행/실패), 사용자가 보낸
  용도지역명을 `AutoZoningService._normalize_zone_name` + 정적 `ZONE_LIMITS` 테이블로
  매핑해 **법정 FAR/BCR 상한**을 보강 → zone_code만 줘도 FAR 역산에 실제 반영.
  (SSOT 재사용, 신규 테이블 미작성)

### 2) 약식주소 정규화 헬퍼 `_normalize_address()`
17개 광역시도 약식→정식 매핑(`_SIDO_SHORT_TO_FULL`).
"서울"→"서울특별시", "경기"→"경기도", "부산"→"부산광역시", "강원"→"강원특별자치도",
"전북"→"전북특별자치도", "세종"→"세종특별자치시" 등. 시도명 접두만 보강(구·동·번지
누락은 보강 불가 — 추정 생성 금지=무목업). 이미 정식명이면 그대로. baseline에서
지오코딩 호출 전 정규화 적용 → 자동감지 성공률↑.

### 3) 422 메시지 개선
면적·주소 둘 다 불가 시:
"부지면적을 자동감지하지 못했습니다. 정확한 주소(시·구·동·번지) 또는
부지면적(land_area_sqm)을 입력하세요." (프론트 게이트 표시용 명확화)

## 라이브 검증 (in-process, 실서비스 호출)
venv가 로컬 미기동이라 실엔드포인트를 in-process로 직접 호출(실 service/schema 사용).
Oracle은 배포 금지·미반영이라 미사용.

### 주소 정규화 (전후)
```
'서울 강남구 역삼동 1'      -> '서울특별시 강남구 역삼동 1'
'서울특별시 강남구 역삼동 736' -> (유지)
'경기 성남시 분당구'        -> '경기도 성남시 분당구'
'서울강남구'(붙임)          -> '서울특별시 강남구'
'경남 창원시'/'전북 전주시'/'강원 춘천시'/'세종 어진동' -> 정식명 보강 OK
```

### zone_code FAR 역산 반영 (면적 제공, 자동감지 불필요 경로)
```
제2종일반주거지역(법정250) -> applied_far=250.0  far_src='용도지역 법정 상한'
일반상업지역(법정1300)     -> applied_far=250.0  (min(zone,유형표준250)=기존 설계)
자연녹지지역(법정100)      -> applied_far=100.0  GFA=500㎡ (zone법정<유형표준 → 하향 반영)
제3종일반주거지역(법정300) -> applied_far=250.0
```
→ 핵심: 자연녹지처럼 법정 상한이 유형표준보다 낮은 zone에서 GFA가 정확히 하향됨
  (이전엔 zone_code 폐기로 항상 유형표준250·far_src="개발유형 표준(추정)"·confidence penalty).
  dev_type assumption도 "제2종일반주거지역 인허가 가능유형 중 대표(일반분양) 자동선택"으로
  zone_code가 실제 반영됨 확인.

### 422 (약식주소 + 면적0, 자동감지 네트워크 차단 시)
```
'서울 강남구 역삼동 1' + land_area_sqm=0
-> 422: "부지면적을 자동감지하지 못했습니다. 정확한 주소(시·구·동·번지) 또는
        부지면적(land_area_sqm)을 입력하세요."
```

## 검증 명령
- `python -m py_compile app/routers/v2_feasibility.py` → OK
- import 보존(`git diff` grep): 기존 import 전부 유지, 추가 import는 함수 내 지연 import
  (AutoZoningService, ZONE_LIMITS — 기존 패턴과 동일).
- 디버그 잔재(print/TODO/debugger) 스캔: 없음.

## 미진 / 후속
- 약식주소에 구·동·번지가 모두 누락된 경우는 정규화로 지오코딩 보강 불가(무목업 원칙상
  추정 면적 생성 금지). 사용자에게 면적 직접입력 또는 완전주소 안내(422 메시지로 처리).
- min(zone_far, type_typical_far) 정책상 고용적 zone(상업)에서 유형표준(M06=250)이
  상한이 됨 — 분양형 건물 밀도 가정의 기존 설계. 상업 고밀 개발유형(M01 등) 선택 시
  자동 상향되나 baseline 자동선택은 M06 우선 유지(보수적). 정책 변경은 별도 범위.
- 라이브 서버(로컬/Oracle) curl 검증은 배포 금지로 미수행. in-process 실서비스 호출로 대체.
