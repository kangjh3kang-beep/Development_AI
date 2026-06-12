# PropAI 건축 지식베이스 심화안 (ARCH_KNOWLEDGE_DEEPENING)

작성일: 2026-06-12
대상 KB: `apps/api/app/services/cad/arch_grammar.py`
종합 출처: 6트랙 조사(트랙1 AI 평면생성 학술 / 트랙2 한국 주거 실무표준 / 트랙3 건축 구조공학 / 트랙4~6 단면·입면·설비·주차 — 조사 데이터 반영분)

## 0. 본 문서의 대원칙 (위반 시 KB 오염)

1. **출처 엄격 구분 — 가짜 법령화 금지.** 조사 결과는 `법령` / `표준(KDS·NKBA 등)` / `실무가이드` / `통상관행` / `논문` 5계로 분류한다. **논문 휴리스틱은 절대 `source='법령'`이 될 수 없으며 `source='논문'` 태그를 필수 부착**한다. 현 KB의 `_legal()`은 검증된 한국 법령에만 사용하고, 표준·논문·관행은 신규 출처 헬퍼(`_std()` / `_paper()` / `_practice()`)로 분리한다.
2. **결정론 우선.** Space Syntax 통합도·GED·BFS depth 등 모든 신규 지표는 입력이 같으면 출력이 같은 순수 함수로만 구현한다. KB(arch_grammar)에는 **계수·임계·가중치 데이터만** 둔다(계산 로직 0 원칙 유지). 함수는 엔진(unit_plan_generator / 신규 checker 모듈)에 둔다.
3. **arch_grammar는 additive.** 기존 상수(`ROOM_TYPES`·`BOUNDARY_RULES`·`WALL_TYPES`·`BOUNDARY_SCHEMA`·`OPENING_SCHEMA`·`ROOM_NAME_MAP`)의 키 개명·삭제·의미 변경 금지. 신규 필드·상수 추가만 허용(IFC 후속 계약 보호).

---

## ① 현 KB 대비 갭 — 무엇이 빠졌나

현 `arch_grammar.py`는 **단일 세대(unit) 평면의 실 타일링을 도면화**하는 데 최적화된 선언 KB다. 보유 자산은: `ROOM_TYPES`(11종 — 문/창/최소치수/wet), `ROOM_NAME_MAP`, `BOUNDARY_RULES`(open/wall_door 11쌍) + `DOOR_OWNER_BY_PAIR`, `WALL_TYPES`(4종 두께·내력), 채광·환기 비율, 그리드 모듈, `BOUNDARY_SCHEMA`/`OPENING_SCHEMA`(IFC 계약). 조사 6트랙 대비 갭은 다음과 같다.

### G1. 평면 품질의 **정량 지표 부재** (트랙1)
- 현 KB는 "경계가 open이냐 wall_door냐"만 규정하고, **생성된 평면이 좋은가**를 판정할 위상 지표가 전혀 없다.
- 빠진 것: Space Syntax 통합도(Integration)/평균깊이(Mean Depth)/RRA, JPG 깊이(현관 루트 BFS), 거실 우세(public_score), 그래프 일치도(GED), 인접 그래프 구축 규칙(거리 임계 0.03·rect 분해).
- 결과: 평면을 만들 수는 있으나 **리랭킹·리젝트·재생성 트리거** 기준이 없다.

### G2. **인접 선호(adjacency preference) 정량화 부재** (트랙1·2)
- 현 `BOUNDARY_RULES`는 "벽이 있냐 없냐"의 위상 규칙일 뿐, "거실-현관은 가까울수록 좋다 / 침실-주방은 멀수록 좋다"는 **선호 가중치**가 없다.
- 빠진 것: 인접 선호 행렬(+2~−2), LDK 강결합·안방존 클러스터(침실-욕실-드레스룸) 규칙, 거실 중심배치 생성순서.

### G3. **인체공학 클리어런스(치수 여유) 부재** (트랙2)
- `ROOM_TYPES`의 `min_area_sqm`/`min_width_m`는 실 전체 최소치만 가질 뿐, **가구·기구 주변 여유(clearance)** 데이터가 없다.
- 빠진 것: 주방 작업삼각형·통로폭·착지면(NKBA), 욕실 변기/세면 클리어런스(NKBA), 가구·통로 여유(Neufert), 세대 내 복도폭 상세.
- 결과: 실은 최소면적을 만족해도 **가구가 안 들어가는** 평면을 통과시킬 수 있다.

### G4. **단면(section)·층고 차원 부재** (트랙2·3)
- KB는 순수 2D 평면 전용. 반자높이·층높이·슬래브두께·보춤 등 **Z축(단면) 데이터가 0**이다.
- 빠진 것: 법정 반자 2.2m·층고 2.4m, 슬래브 최소두께비(KDS L/20~L/28), 보 최소춤비(KDS L/16~L/21), fy/경량 보정계수, 구조형식별 슬래브두께(벽식 vs 무량판 vs 라멘).

### G5. **구조 정합(structure consistency) 부재** (트랙3)
- 내력벽/기둥의 경간·정렬·전이 규칙이 없어, 평면이 **구조적으로 성립 불가능**해도 검출 못 함.
- 빠진 것: 라멘 기둥경간(6~9m)·벽식 벽간격(≤6m)·벽두께(200~250mm), 상하층 수직정렬·전이보·필로티/연약층, 내진설계 대상(2층/200㎡)·응답수정계수 R.

### G6. **입면(elevation)·실구성 매트릭스 부재** (트랙2)
- 베이(bay)·전용률·코어유형·평형별 실구성(59/74/84/114㎡) 등 **세대 외피·동(棟) 단위** 데이터가 없다.
- 빠진 것: bay_config(3·4베이 전면폭), 전용률 테이블(계단실/복도/타워), 코어 세대수, 평형→{침실·욕실·LDK}.

### G7. **설비·주차 정합 부재** (트랙2·6 — 조사 PARKING/설비 항목)
- 빠진 것: 주차 모듈(주차구획·차로폭), 설비 코어(PS/AD) 위치, 발코니·다용도실 서비스공간 배치 규칙(부분 보유 — note 텍스트뿐).

### G8. **3D / IFC 단면 계약 미비**
- `BOUNDARY_SCHEMA`/`OPENING_SCHEMA`는 평면 변·개구만 계약. **z(높이)·층·슬래브·기둥** 스키마가 없어 3D/IFC 격상 불가.

---

## ② 보강 항목 표 (우선순위화)

> **출처 분류 범례** · `법령`(한국 법령 — `_legal()` 즉시반영 후보) · `표준`(KDS/NKBA 등 공인 표준 — `_std()` 즉시반영 후보) · `실무가이드`/`통상관행`(`_practice()` — source 명시) · `논문`(`_paper()` — **source=논문 태그 필수, 법령화 금지**)
> **우선순위** · P0(평면 심화 즉시) · P1(단면/구조 정합) · P2(입면/설비/3D)

### 2-A. 즉시 반영 후보 — 법령·표준 (검증 출처)

| # | 항목 | 출처 | source_type | 코드화 형태 | 적용대상 | 우선 |
|---|------|------|-------------|-------------|----------|------|
| L1 | 반자높이 ≥2.2m / 층높이 ≥2.4m / 평면 50mm 모듈 | 주택건설기준 등에 관한 규정·주택법 시행규칙 제3조 | 법령 | `SECTION_RULES.ceiling_h_min_mm=2200`(typ 2300)·`floor_h_min_mm=2400`·`plan_module_mm=50`(기보유 GRID_MODULE 재확인) | 단면 | P1 |
| L2 | 내진설계 의무대상(2층↑ or 연면적200㎡↑ or 높이13m↑ 등) | 건축법 시행령 제32조 | 법령 | `SEISMIC.required = stories>=2 \|\| gfa>=200 \|\| height_m>=13 \|\| eave_m>=9 \|\| col_span_m>=10` | 구조 | P1 |
| S1 | 1방향 슬래브 최소두께비(단순L/20·일단L/24·양단L/28·캔틸L/10) | KDS 14 20 30 표4.2-1 | 표준 | `STRUCTURE_SPANS.slab_min_ratio={simple:1/20,one_end:1/24,both:1/28,cantilever:1/10}` | 단면/구조 | P1 |
| S2 | 보 최소춤비(단순L/16·일단L/18.5·양단L/21·캔틸L/8) | KDS 14 20 30 표4.2-1 | 표준 | `STRUCTURE_SPANS.beam_min_ratio={simple:1/16,one_end:1/18.5,both:1/21,cantilever:1/8}` | 단면/구조 | P1 |
| S3 | 최소두께 보정계수(fy≠400 → 0.43+fy/700; 경량 → max(1.65−0.00031·wc,1.09)) | KDS 14 20 30 표4.2-1 비고 | 표준 | `STRUCTURE_SPANS.factor_fy(fy)`·`factor_lw(wc)` 계수만 KB, 적용은 엔진 | 단면/구조 | P1 |
| S4 | 무량판 2방향 슬래브 최소두께 식 ln(0.8+fy/1400)/(36+9β) | KDS 14 20 30 | 표준 | `STRUCTURE_SPANS.flat_plate_typ_mm=[250,300]`·식 파라미터(β=장변/단변) | 단면/구조 | P1 |
| K1 | 주방 작업삼각형: 변 1.2~2.7m, 합 ≤6.7m, 동선 비관통 | NKBA Kitchen G5 | 표준 | `CLEARANCES.kitchen.work_triangle={leg_min:1200,leg_max:2700,sum_max:6700,no_traffic:true}` | 평면/설비 | P0 |
| K2 | 주방 통로폭: 1인≥1067·2인≥1219·보행≥914, 대향카운터 1067~1219 | NKBA Kitchen G6·7 | 표준 | `CLEARANCES.kitchen.aisle={cook1:1067,cook2:1219,walkway:914,opposed:[1067,1219]}` | 평면/동선 | P0 |
| K3 | 주방 착지면: 싱크 610+460·냉장고핸들 380·가열대 300, 빌트인냉장고 캐비닛 내폭≥918 | NKBA Kitchen | 표준 | `CLEARANCES.kitchen.landing={sink:[610,460],fridge_handle:380,cooktop:300,builtin_cab_w:918}` | 설비/평면 | P0 |
| B1 | 욕실: 변기중심↔벽≥380(권460)·전면≥530(권760)·세면2개중심≥760(권910) | NKBA Bathroom | 표준 | `CLEARANCES.bath={wc_to_wall:380(rec460),front:530(rec760),dual_lav:760(rec910)}` | 설비/평면 | P0 |

### 2-B. 즉시 반영 후보 — 실무가이드·통상관행 (source 명시, 법령화 금지)

| # | 항목 | 출처 | source_type | 코드화 형태 | 적용대상 | 우선 |
|---|------|------|-------------|-------------|----------|------|
| N1 | 가구 클리어런스: 식탁-벽 750(통행1000)·식탁둘레 900·침대진입 700·옷장앞 900 | Neufert | 실무가이드 | `CLEARANCES.furniture={dining_wall:[750,1000],dining_perimeter:900,bed_access:700,wardrobe:900}` | 평면/가구 | P0 |
| N2 | 통로/복도폭: 1인 600·표준 900·2인교행 1000~1500·세대내복도 900~1200 | Neufert·실무 | 실무가이드 | `CLEARANCES.passage={single:600,standard:900,two:[1000,1500],unit_corridor:[900,1200]}` | 동선/평면 | P0 |
| N3 | 침실 권장면적: 부부 12~16㎡·1인 7~10㎡, 안방존 전용의 12~15% | Neufert·실무 | 실무가이드 | `ROOM_TYPES[*].rec_area_sqm`(권장, min과 별도)·`MASTER_ZONE_RATIO=[0.12,0.15]` | 평면/면적 | P0 |
| A1 | 인접 선호행렬 5단계(+2 필수~−2 필수분리): 거실-현관+1~2, 주방-식당+2, 안방-전용욕+2, 거실-욕실−1, 침실-주방−1 | 건축 프로그래밍 관행(archisoup/BriefBuilder) | 통상관행 | `ADJACENCY_WEIGHTS[type_i][type_j] ∈ {+2,+1,0,−1,−2}` | 배치/인접 | P0 |
| P1 | 평형→실구성: 59=[침2-3,욕1,LDK1]·74=[침3,욕1-2,LDK1]·84=[침3,욕2,LDK1]·114=[침3-4,욕2,LDK1+α] | LH 주력평면매뉴얼(2018)·시장관행 | 실무가이드 | `UNIT_MIX_BY_AREA={59:{...},74:{...},84:{...},114:{...}}` | 평면/배치 | P1 |
| P2 | 베이: 3베이 전면폭 8.4~9.0m(전면실3)·4베이 10.5~11.0m(전면실4) | 부동산 평면분석 실무 | 통상관행 | `BAY_CONFIG={3:{front_rooms:3,front_w:[8.4,9.0]},4:{front_rooms:4,front_w:[10.5,11.0]}}` | 입면/배치 | P2 |
| P3 | 전용률: 계단실 0.75~0.83·복도 0.70~0.75·타워 0.70~0.78·주상복합 0.70~0.80·OT 0.50~0.60 | KB부동산·시장관행 | 통상관행 | `EFFICIENCY_RATIO={stair:[0.75,0.83],corridor:[0.70,0.75],tower:[0.70,0.78],...}` | 배치/코어 | P2 |
| P4 | 코어 세대수: 계단실 2·복도 다세대(편복도)·타워 3~4(중앙코어 방사) | 코어 유형론 실무 | 실무가이드 | `CORE_TYPE={stair:{units:2},corridor:{units:'multi'},tower:{units:[3,4]}}` | 코어/배치 | P2 |
| Z1 | 동선분리: 현관시선차단·안방존 클러스터·주방-다용도-세탁 인접 | 주거평면 실무·LDK이론 | 실무가이드 | `ZONING_RULES={entry_sightline_block:true,master_cluster:[master_bed,dress,bath_master],kitchen_service:[utility,laundry]}` | 평면/동선 | P0 |
| Z2 | 서비스공간: 발코니=확장흡수·다용도실=주방후면·드레스룸=통과형/부속형 | 발코니 확장 시장관행 | 통상관행 | `SERVICE_SPACE` 규칙(기존 note 텍스트 → 구조화) | 평면/배치 | P1 |
| C1 | RC라멘 기둥경간 6~9m(typ 6~7.5)·부담면적≈30㎡·한방향>6m&직교>6m → PT 권고 | KDS 41 10 05 + RC 실무관행 | 통상관행 | `STRUCTURE_SPANS.rc_frame={col_span:[6000,9000],tributary:30,warn_over:9000}` | 평면/구조 | P1 |
| C2 | 벽식: 벽간격≤6m·벽두께 200~250mm·무보·가변성 낮음 | 벽식 아파트 설계관행 | 통상관행 | `STRUCTURE_SPANS.bearing_wall={spacing_max:6000,thickness:[200,250],no_beam:true}` | 평면/구조 | P1 |

### 2-C. 논문 휴리스틱 — `source='논문'` 태그 필수 (법령·표준과 구분, 검증룰 후보)

| # | 항목 | 출처(논문) | source_type | 코드화 형태 | 적용대상 | 우선 |
|---|------|-----------|-------------|-------------|----------|------|
| R1 | Space Syntax 통합도: MD=TD/(k−1)·RA=2(MD−1)/(k−2)·RRA=RA/D_k·Integration=1/RRA | arXiv 2602.22507(2026) | 논문 | KB엔 `DIAMOND_VALUES`(D_k 표)만, 함수는 엔진 `space_syntax.py` | 평면/위상 | P0 |
| R2 | 거실 우세: public_score = max(Int[living]) − max(Int[non_living]) > 0 = PASS | arXiv 2602.22507 + RPLAN | 논문 | `PLAN_QUALITY_THRESHOLDS.public_score_min=0`(태그 논문) | 평면/검증 | P0 |
| R3 | JPG 깊이(현관 루트 BFS): depth(bedroom)>depth(living), depth(bath)≥depth(bedroom) | MDPI Sustainability 13/6/3394·Buildings 16/2/364 | 논문 | `PRIVACY_DEPTH_RULES`(루트=entry, 깊이 부등식) | 평면/프라이버시 | P0 |
| R4 | 인접 판정 임계 dist < 0.03×planLength; LDK 강결합·침실-욕실-드레스 클러스터 | ScienceDirect 2023·arXiv 2108.05947 | 논문 | `ADJACENCY_DETECT.dist_ratio=0.03`(태그 논문) | 평면/그래프 | P0 |
| R5 | GED(그래프 편집거리) 일치도, 합격 GED≤3(실수 5~8) | House-GAN++ CVPR2021 | 논문 | `PLAN_QUALITY_THRESHOLDS.ged_max=3` | 평면/일치도 | P1 |
| R6 | 엣지 타입 enum {ADJACENT, DOOR_CONNECTED, FRONT_DOOR, NO_RELATION} | House-GAN/++ | 논문 | `EDGE_TYPES` enum(인접 vs 기능 2채널) | 평면/제약표현 | P1 |
| R7 | 거실 중심 우선배치 generationOrder=[living(center),...] | Wu et al. TOG2019 | 논문 | `GENERATION_ORDER` 시드 규칙(태그 논문) | 평면/생성순서 | P1 |
| R8 | rect 분해(minArea=50px)·가시/접근 인접행렬 2종 분리 | arXiv 2602.22507 | 논문 | 엔진 전처리 파라미터(`min_rect_area_px=50`) | 평면/그래프 | P2 |
| R9 | 수직 비정형/연약층: 상하층 강성비<70% → soft_story, 전이보 시 내진취약 플래그 | 대한건축학회 구조계 + 필로티 가이드 | 논문/실무가이드 | `STRUCTURE_CHECKS.soft_story_ratio=0.70` (혼합: 논문+실무) | 구조/배치 | P1 |

> **주의**: R1~R9는 **생성 모델 학습/평가에서 도출된 휴리스틱**이다. KB 반영 시 모든 레코드에 `"source": "논문"`, `"paper_ref": "<arXiv/DOI>"`, `"is_legal": False`를 명시한다. 절대 `_legal()`로 감싸지 않는다.

---

## ③ KB 스키마 확장안 (additive only)

기존 `ROOM_TYPES` 등은 유지하고, 아래를 **추가**한다. 모든 신규 상수는 데이터 전용(계산 0).

### 3-1. 출처 헬퍼 분리 (법령화 방지의 핵심)
```python
# 기존 _legal()은 한국 '법령'에만 사용. 표준/관행/논문은 별도 헬퍼로 분리.
def _std(standard: str, clause: str) -> dict:        # KDS·NKBA 등 공인 표준
    return {"standard": standard, "clause": clause, "source_type": "표준", "is_legal": False}
def _practice(note: str) -> dict:                     # 실무가이드·통상관행
    return {"note": note, "source_type": "통상관행", "is_legal": False}
def _paper(ref: str) -> dict:                         # 논문 — 법령화 절대 금지
    return {"paper_ref": ref, "source_type": "논문", "is_legal": False}
```

### 3-2. `ROOM_TYPES` 추가 필드 (additive)
| 신규 필드 | 의미 | 출처 |
|-----------|------|------|
| `rec_area_sqm` | 권장면적(min과 별도 — 부부12~16/1인7~10㎡) | 실무가이드(N3) |
| `adjacency_role` | `'public'`(거실/주방/현관)·`'private'`(침실)·`'service'`(욕실/다용도) | 논문(R2/R3 위계용) |
| `furniture_clearance_ref` | `CLEARANCES` 내 해당 실 키 참조(예: bath→`CLEARANCES.bath`) | 표준(K·B·N) |
| `wet_drainage` | wet실의 배수 PS 인접 요구(bool) | 통상관행 |

### 3-3. 신규 상수 (전부 데이터 전용)
```python
ADJACENCY_WEIGHTS: dict[frozenset, int]   # +2~−2, source=통상관행(A1). frozenset 키로 대칭 보장
ADJACENCY_DETECT  = {"dist_ratio": 0.03, "source": "논문", "paper_ref": "..."}   # R4
CLEARANCES        = {"kitchen": {...}, "bath": {...}, "furniture": {...}, "passage": {...}}  # 표준+Neufert
STRUCTURE_SPANS   = {"slab_min_ratio": {...}, "beam_min_ratio": {...},
                     "factor_fy": "0.43+fy/700", "factor_lw": "max(1.65-0.00031*wc,1.09)",
                     "rc_frame": {...}, "bearing_wall": {...}, "flat_plate_typ_mm": [250,300]}  # KDS
SECTION_RULES     = {"ceiling_h_min_mm": 2200, "ceiling_h_typ_mm": 2300,
                     "floor_h_min_mm": 2400, "slab_typ_mm": {"rahmen":[120,150],"flat":[250,300]}}  # 법령+KDS
SEISMIC           = {"required_rule": "stories>=2 || gfa>=200 || ...", "R_factors": {...}}  # 법령+KDS
PLAN_QUALITY_THRESHOLDS = {"public_score_min": 0, "ged_max": 3,
                           "source": "논문", "paper_refs": [...]}   # R2/R5 — 논문 태그
PRIVACY_DEPTH_RULES     = {"root": "entry",
                           "depth_order": ["living<bedroom","bedroom<=bath"],
                           "source": "논문"}   # R3
DIAMOND_VALUES    = {k: D_k, ...}   # Space Syntax RRA 정규화 표 — 데이터만, 함수는 엔진
EDGE_TYPES        = ("ADJACENT","DOOR_CONNECTED","FRONT_DOOR","NO_RELATION")  # R6
GENERATION_ORDER  = {"seed": "living@center", "expand": "BFS-from-living", "source": "논문"}  # R7
ZONING_RULES      = {"entry_sightline_block": True, "master_cluster": [...], "kitchen_service": [...]}  # Z1
UNIT_MIX_BY_AREA  = {59:{...}, 74:{...}, 84:{...}, 114:{...}}   # P1
BAY_CONFIG        = {3:{...}, 4:{...}}        # P2
EFFICIENCY_RATIO  = {"stair":[0.75,0.83], ...}  # P3
CORE_TYPE         = {"stair":{"units":2}, "tower":{"units":[3,4]}, ...}  # P4
PARKING_MODULE    = {"stall": {"w_mm":2500,"l_mm":5000},   # 트랙6 — 조사 PARKING 항목 채움
                     "aisle_mm": {"right_angle":6000,"parallel":3500},
                     "source": "주차장법 시행규칙(검증 후 _legal)"}   # ※법령값은 출처 검증 후 반영
```

### 3-4. IFC 단면 계약 확장 (additive — 기존 SCHEMA 보호)
```python
SECTION_SCHEMA: dict[str,str] = {   # 신규 — 3D/IFC 격상 계약
    "level_id": "층 ID 'L##' — IfcBuildingStorey 근원",
    "z_base_m": "층 바닥 레벨(m)", "ceiling_h_m": "반자높이", "floor_h_m": "층고",
    "slab_thickness_mm": "슬래브 두께(STRUCTURE_SPANS 산정)",
    "structure_system": "'rahmen'|'bearing_wall'|'flat_plate'",
}
STRUCTURE_SCHEMA: dict[str,str] = {  # 신규 — 기둥/내력벽 수직 연속성
    "id":"'col##'|'bw##'", "x_m,y_m":"평면 좌표", "span_m":"경간",
    "aligns_below":"하층 부재와 정렬(bool)", "needs_transfer":"전이보 필요(bool)",
}
```
> **불변식**: 기존 `BOUNDARY_SCHEMA`/`OPENING_SCHEMA` 키는 손대지 않는다. 신규 `SECTION_SCHEMA`/`STRUCTURE_SCHEMA`만 추가.

---

## ④ 검증 룰로 승격 — 생성 후 체커 (신규 모듈 `arch_validators.py`, KB는 임계만)

> 원칙: **KB(arch_grammar)에는 임계·가중치 데이터만**, 판정 함수는 별도 결정론 체커 모듈에. 각 룰은 PASS/FAIL + 위반 상세 반환. 법령/표준 위반은 `hard`(리젝트), 논문 휴리스틱 위반은 `soft`(리랭킹 감점).

| 체커 | 근거 | 등급 | 입력→판정 | 액션 |
|------|------|------|-----------|------|
| `check_daylight_ratio` | 건축법 시행령 제51조(기보유 비율) | hard(법령) | 창면적/바닥 ≥1/10, 환기 ≥1/20 | FAIL→리젝트 |
| `check_ceiling_floor_height` | 주택건설기준 제3조(L1) | hard(법령) | 반자≥2.2·층고≥2.4 | FAIL→리젝트 |
| `check_slab_beam_depth` | KDS 14 20 30(S1·S2·S3) | hard(표준) | 경간×비율×보정 → 최소두께 충족 | FAIL→두께 재산정 |
| `check_kitchen_triangle` | NKBA G5(K1) | hard(표준) | 삼각형 변·합·동선관통 | FAIL→가구 재배치 |
| `check_kitchen_aisle` | NKBA G6·7(K2) | hard(표준) | 통로폭 ≥1067/1219 | FAIL→폭 확장 |
| `check_bath_clearance` | NKBA Bath(B1) | hard(표준) | 변기/세면 클리어런스 | FAIL→재배치 |
| `check_furniture_fit` | Neufert(N1·N2) | hard(실무) | 가구+여유 실 내 수용 | FAIL→경고 |
| `check_seismic_required` | 건축법 시행령 제32조(L2) | hard(법령) | 규모→내진대상 → 횡력시스템 입력 강제 | 미입력→블록 |
| `check_vertical_alignment` | 구조 수직연속성(R9) | hard(구조) | 상하 기둥/벽 정렬 | 미정렬→전이보 요구 |
| `check_soft_story` | 필로티/연약층(R9) | soft(논문+실무) | 층강성비<70% | 감점+플래그 |
| `score_integration_public` | Space Syntax(R1·R2) | **soft(논문)** | public_score>0 | <0→리랭킹 감점 |
| `score_jpg_depth` | JPG 깊이(R3) | **soft(논문)** | depth 부등식 위반수 | 위반↑→감점 |
| `score_ged_match` | House-GAN++(R5) | **soft(논문)** | GED(입력G, 생성G)≤3 | 초과→재생성 |
| `score_adjacency_pref` | 인접행렬(A1)+탐지(R4) | soft(관행+논문) | Σ ADJACENCY_WEIGHTS·isAdjacent | 점수 리랭킹 |

> **승격 구분 핵심**: 법령·표준 = `hard`(통과 못 하면 도면 리젝트). 논문 = `soft`(생성 품질 리랭킹/감점만, 절대 법적 리젝트 사유로 쓰지 않음).

---

## ⑤ 단계별 구현 로드맵

### Phase 0 — 출처 인프라 (선행, 0.5주)
- `_std()`/`_practice()`/`_paper()` 헬퍼 추가, 모든 신규 레코드에 `source_type`·`is_legal` 강제.
- 신규 모듈 골격: `arch_validators.py`(체커), `space_syntax.py`(위상 함수). KB는 데이터만.

### Phase 1 — 평면 심화 (P0, 최우선)
- KB: `ADJACENCY_WEIGHTS`·`ADJACENCY_DETECT`·`CLEARANCES`·`ZONING_RULES`·`PLAN_QUALITY_THRESHOLDS`·`PRIVACY_DEPTH_RULES`·`DIAMOND_VALUES`·`ROOM_TYPES` 추가필드(rec_area/adjacency_role/clearance_ref).
- 체커: `check_kitchen_*`·`check_bath_clearance`·`check_furniture_fit`(hard) + `score_integration_public`·`score_jpg_depth`·`score_adjacency_pref`(soft).
- 엔진: 거실 중심 시드(R7), 인접 그래프(거리0.03·rect분해), 통합도/깊이 산출, 리랭킹.
- **산출물**: "최소면적만 만족"하던 평면 → "가구 들어가고·동선 분리되고·거실이 공간코어인" 평면.

### Phase 2 — 단면/입면 (P1~P2)
- KB: `SECTION_RULES`·`SECTION_SCHEMA`·`UNIT_MIX_BY_AREA`·`BAY_CONFIG`·`EFFICIENCY_RATIO`·`CORE_TYPE`.
- 체커: `check_ceiling_floor_height`(hard). 평면+층고 → 단면 생성, 베이/전용률 입면 검증.

### Phase 3 — 구조/설비 정합 (P1)
- KB: `STRUCTURE_SPANS`·`STRUCTURE_SCHEMA`·`SEISMIC`·`PARKING_MODULE`(법령값 검증 후).
- 체커: `check_slab_beam_depth`·`check_seismic_required`·`check_vertical_alignment`(hard) + `check_soft_story`(soft).
- 내력벽=실경계 정렬, 기둥 경간 검증, 상하층 정렬·전이보 플래그, 주차모듈 정합.

### Phase 4 — 3D / IFC 격상
- `SECTION_SCHEMA`/`STRUCTURE_SCHEMA` 소비 → IfcBuildingStorey/IfcSlab/IfcColumn 변환.
- 평면(IfcRelSpaceBoundary)+단면(z)+구조(부재) 통합 BIM. 기존 IFC 계약 키 보존 확인.

---

## 부록 — 반영 시 체크리스트 (오염 방지)
- [ ] 신규 레코드마다 `source_type` ∈ {법령,표준,실무가이드,통상관행,논문} 명시했는가
- [ ] 논문 항목(R1~R9)에 `is_legal:False` + `paper_ref` 부착, `_legal()` 미사용 확인
- [ ] 법령·표준 임계 = `hard` 체커, 논문 휴리스틱 = `soft` 체커로 분리했는가
- [ ] 기존 `ROOM_TYPES`/`BOUNDARY_RULES`/`WALL_TYPES`/`*_SCHEMA` 키 개명·삭제 없이 additive인가
- [ ] KB(arch_grammar)에 계산 로직 0 유지(함수는 엔진/체커 모듈에만)인가
- [ ] `min_area_sqm`처럼 법정·관행 미정의 수치는 `None`으로 두고 가짜값 미기입했는가
- [ ] `PARKING_MODULE` 등 법령 수치는 1차 출처(주차장법 등) 검증 후 `_legal()` 반영했는가
