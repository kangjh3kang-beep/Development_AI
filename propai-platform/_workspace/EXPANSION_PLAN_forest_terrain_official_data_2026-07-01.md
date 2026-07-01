# 확장경로 계획 — 산지·임목·경사 공식데이터 게이트 (기존자산 확장)

- 작성일: 2026-07-01
- 상위: `REDTEAM_PASS4_GROUNDTRUTH_VERIFIED_PLAN` §7 확장경로 5번, 코덱스 `LAW_REVIEW_ENGINE` §6.2/9, 감사 P1-2(임목본수도·경사도는 인허가급 아님)
- ★원칙: **재구현 금지 — 기존 `special_parcel`·`terrain_service` 위에 얹는다.** 신규는 산림청 커넥터 1개뿐.

## 1. 그라운드-트루스: 이미 있는 것 vs 없는 것

**이미 있는 자산(확장 대상):**
- `app/services/zoning/special_parcel.py` — 임야(산지) 게이트 실존: `developability="CONDITIONAL"`, `legal_basis=["산지관리법 제14조(산지전용허가)"]`, `legal_ref_keys=["forest_conversion"]`, `permit_prerequisites=["산지전용허가","경사도/표고/입목축적 검토"]`, `resolution_paths` 포함. **단, 텍스트 경고 수준 — 정량 데이터 없음.**
- `app/services/terrain/terrain_service.py` — OpenTopoData SRTM 30m 경사/표고/토공. **"정밀 측량/검증된 토목설계 아님" 정직표기 이미 있음**, 필지<DEM셀이면 confidence 하향. 즉 "참고 vs 공식" 분리의 절반은 존재.
- `legal_reference_registry` — `forest_conversion` 등 법령 키 레지스트리.

**없는 것(진짜 갭):**
- 산림청 공식 데이터 커넥터(산지구분도·임상도·산림기본통계) — 부재. ★유일한 신규 자산.
- `NEEDS_OFFICIAL_SURVEY` 차단 게이트 — 참고 데이터를 인허가 확정값으로 오인 방지하는 명시적 차단 상태.
- 정량 지표: 보전산지 여부, 입목축적(대상지 vs 관할평균), 평균경사도 수치, 표고비율.

## 2. 목표: "참고 예비판정"과 "인허가 제출용 확정조사"의 명시적 분리

감사·법령엔진계획의 핵심 요구 = **공공데이터로 예비 스크리닝은 하되, 산지전용 허가 확정은 공식 현장조사서 없이는 차단.** (산림청 임상도조차 "허가신청용 현장조사서 대체 불가"임을 계획이 인정.)

**데이터 등급(기존 evidence 계약 `legal_effect` 필드 재사용):**
| 등급 | 예시 | 산출 영향 |
|---|---|---|
| `binding_record` | 산지구분도 고시, 보전산지 지정 | 확정 판정 근거 |
| `spatial_reference` | 임상도 GIS 속성, SRTM 경사 | 예비 스크리닝만, 확정 차단 |
| `derived_estimate` | SRTM 30m 표고 보간 | 리스크 표시만 |
| `requires_official_survey` | 평균경사도·입목축적 현장조사서 | ★확정 설계 차단 게이트 |

## 3. 구현 단계 (기존자산 확장 순)

### E1. `special_parcel` 임야 게이트에 정량 필드 + 차단상태 추가 (신규 아님)
- 기존 임야 게이트 dict에 `forest_facts`(보전산지/준보전산지, 산지구분, 평균경사도, 표고비율, 입목축적, 관할평균 대비) 필드 추가.
- `developability`에 `NEEDS_OFFICIAL_SURVEY` 상태 추가(현재 POSSIBLE/CAUTION/CONDITIONAL/PRECONDITION/BLOCKED에 1개).
- 공식데이터 미확보 시 설계 확정 차단 플래그(`blocking_unknown=True`), 참고안만 허용.

### E2. `terrain_service` 공식 DEM 경로 분기 (기존 SRTM은 참고 유지)
- SRTM 30m 결과에 `legal_effect="derived_estimate"` 명시(이미 정직표기 있음 → 계약 필드화).
- 공식 수치지형도/지자체 제출기준 평균경사도 계산 모듈 자리 확보(`official_slope` None→추후 배선). 미확보면 `requires_official_survey`.
- 산지전용 기준(25도/30도/지자체) 대비 경사 면적분포 예비 산정.

### E3. 산림청 커넥터 신설 — `app/services/forest/forest_data_service.py` (★유일 신규)
- 산지구분도(보전/준보전), 임상도(임종·임상·수종·수관밀도·영급·경급), 산림기본통계(관할 ha당 평균 입목축적).
- `ConnectorReadiness` 라벨: forest.go.kr 임상도=파일데이터(비실시간)→`limited/file_download`, 산지정보시스템=열람중심→`manual_only`. 자동수집 불가는 정직표기 + 열람링크.
- **special_parcel 임야 게이트가 이 서비스를 호출**(독립 판정경로 신설 금지 — 게이트 경유).

### E4. 입목축적 예비 산정 + 산지전용 게이트
- 임상도 영급·경급·수관밀도 → 입목축적 예비값(보조지표, 확정 아님).
- 대상지 vs 관할 시군구 평균 입목축적 비교(산지전용 심사 기준).
- 660㎡ 미만 예외, 분할회피 의심, 2만㎡ 이상 집단화 보전산지 기준 룰.
- 결과는 `참고예비` 배지 + "산림조사서·평균경사도조사서 제출 필요(작성자격: 산림기술사 등)" 안내 → E1 차단상태 연결.

### E5. UI: 산지/임야 전용 패널 (기존 특이필지 카드 확장)
- 입목·경사·표고·산지구분 패널 별도 표시. 각 값에 `legal_effect` 배지(확정/참고/공식조사필요).
- BLOCKED/NEEDS_OFFICIAL_SURVEY 시 전문가(산림기술사/감정평가사) 연결 CTA(4차 레드팀 4G-7 반영).

## 4. 100% 게이트(이 확장 한정)
1. 임야/산지 필지는 `NEEDS_OFFICIAL_SURVEY` 미해소 시 **확정 설계·도면 생성 차단**, 참고안만.
2. SRTM 등 참고 DEM 값이 인허가 확정값으로 표시되면 실패(`legal_effect` 배지 필수).
3. 산림청 커넥터 각 원천은 `ready/limited/manual_only/unavailable` 분류.
4. 입목축적/평균경사도는 "예비값"과 "제출용 확정조사 필요"가 분리 표시.
5. 회귀 fixture: 보전산지·준보전산지·경사25도초과·660㎡미만·2만㎡이상 케이스.

## 5. 우선순위·의존
- E1(special_parcel 정량필드+차단상태)이 최우선(신규 커넥터 없이도 "참고 vs 확정" 분리·차단 게이트 확보 → 즉시 무결성 상승).
- E3(산림청 커넥터)는 원천 readiness 조사 선행(forest.go.kr API 실호출 검증 — 미제공이면 manual_only 링크아웃).
- E2/E4/E5는 E1·E3 이후.
- ★모두 성장루프(executor→리뷰≥9.5→통합자머지→배포→라이브검증), 한 번에 하나 모듈.

## 6. 열린 질문
- forest.go.kr 임상도/산지구분도가 실시간 REST API를 제공하는가, 파일데이터/열람뿐인가(실호출 검증 필요). 후자면 커넥터는 "열람링크+수동확인 큐"로 정직 강등.
- 공식 수치지형도(국토지리정보원) 경사 데이터 획득 경로·좌표계·라이선스.
