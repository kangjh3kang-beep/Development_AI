# 코드리뷰 반복 개선 루프 — 결정 로그 (적용 / 미적용 / 보류)

목적: `/loop` 코드리뷰 개선의 **적용·미적용·보류 결정을 모두 기록**해 공유하고, 향후 미적용분의
**재작업·중복시도를 방지**한다. (정본 = `services/deliberation-review`, 브랜치 `feature/deliberation-review`)

통과기준: 4.0 → **4.5**(2026-06-17 사용자 상향). 규칙: 개선→검증(테스트·ruff)→재리뷰로 점수상승 확인 시 반영, 아니면 롤백.

---

## 1. 적용된 개선 (커밋, 검증 통과)

| iter | 커밋 | 차원 | 내용 | 검증 |
|------|------|------|------|------|
| 1 | `3a78f2df` | 계약·정확성·security | Comparator enum(무음 != 폴백 제거)·confidence Probability(5파일)·sunlight §61 비법정근사·PARKING 경고·remaining raw 비교·image_source SSRF/경로차단·deps 상수시간·settings https/production fail-closed | 287 |
| 2 | `0a20b50b` | 계약·정확성 | confidence 14필드 Probability/Similarity·BCR 판정(시행령§84)·egress 오라벨·matcher cosine clamp | 290 |
| 2b | `5fb4c55e` | 계약 | element_classifier confidence clamp(Probability 부작용 방어) | 290 |
| 3 | `11523124` | 테스트·아키텍처 | static_scan regex→AST(음수/dict/+=/지수)·preflight_blocked 표면화 | 297 |
| 4 | `1900f568` | 테스트 | static_scan benign 축소(법정명+benign값 탐지)·인증 require_token positive/개방/scheme | 301 |
| 5 | `d459a0a0` | 아키텍처 | ConfidenceComposer(충돌 패널티)·FindingGate(gated_status 박제 해소) pipeline 배선 | 303 |
| 6 | `e45590e9` | 후속 | SimMetric 래핑(shadow_3d.sunlight_metric/skyline.protrusion_metric emit 게이트) | 305 |
| 6 | `32183706` | 견고성 | land_card 어댑터 실패↔결손↔미설정 구분·calc_engine 필수키→RuleContractError(500 방지)·citation ISO 날짜 | 307 |
| 7 | `c59efa1c` | 계약 | eval.accuracy/drawing_extraction.hint_strength/preflight.area_ratio/EvalCase.input_confidence Probability + drawing_extractor clamp | 307 |
| 7 | `b999a055` | security | 예외 원문 에코 제거(domain_error:<타입> 코드만) | 307 |
| 8 | `da3fe354` | 정확성 | BCR 조례 ordinance_bcr(서울 §54 건폐율 상업 80→60 강화)·egress 보행거리 30m 기저 보수성 caveat | 309 |
| 9 | `43fc06e0` | 견고성·문서 | 결정로그 iter7~8 기록 + geocode/surrounding 어댑터 '키있음+결과없음(장애/결손 미상)'↔'키없음(미설정)' 구분 | 309 |
| 10 | `05920fdd` | security | AnalysisInput.pnu 패턴(19자리 또는 빈, 비19자리 거부) — 외부 API 무검증 유입·쿼터낭비 차단 | 310 |
| 11 | `832c9acd` | 계약 | FiniteFloat(allow_inf_nan=False) — 측정치 nan/inf 거부(nan≤limit→무음 COMPLIANT 오판 차단) | 312 |
| 12 | `ab67aa4d` | 테스트 | static_scan _BENIGN 조기반환 버그 수정(법정명+benign값 far_limit=1.0/setback_min=0 탈출 차단)·측정치 allowlist | 312 |
| 13 | `fcb5da3b` | 테스트·정확성 | static_scan AST 확장(함수기본값·call-kwarg·튜플언패킹·튜플/리스트 값) — 시그니처 사각지대 차단 + shadow_3d 하드코딩 5종(floor_height_m=3.0·sunlight_threshold=0.5·min_hours=4.0·관측창 9~15) → sim_params.json SSOT 주입(INV-20)·회귀가드 5 | 316 |
| 14 | `76ab59db` | 견고성·계약 | egress 보행속도/유동계수 비양수 가드(walk_speed≤0→0division 500·flow<0→음수시간 무음오판 차단, UNAVAILABLE+invalid_egress_params, INV-21)·가드 테스트 | 317 |
| 15 | `56caf153` | security | 레이트리밋(FixedWindowRateLimiter 인메모리 고정창)·미들웨어 배선(클라이언트별 분당 상한, /health 면제, 429+Retry-After)·REQUESTS_PER_MINUTE 설정(0=비활성 기본)·리미터 단위(clock주입 결정론)+미들웨어 통합 테스트 5 | 322 |
| 16 | `8bceda90` | 계약 | SimMetric.unit str→MetricUnit enum(""/s/hours/m/ratio) — 임의 단위 무음 통과 차단·계약 강제. str,Enum이라 JSON은 값('s')로 직렬화(프런트 ui/index.html `m.unit` 호환 byte-동일)·계약 테스트(유효 강제·비계약 거부) | 323 |
| 17 | `8f6b06db` | 정확성 | PARKING 전량제외 무음 거짓적합 제거 — CalcElement underground/accessory + parking_far_eligibility(지하·부속만 제외/지상·독립 산입/미상 HELD), CalcEngine far 주차 미상→held. far_parking_held trace 표면화·테스트 3(적격제외/지상산입/미상HELD) | 325 |
| 18 | `0b11bd0c` | 설명가능성 | (멀티에이전트 감사 w6r4klvk1 28갭 기반 S1+legal_calc) P1 gate_reason 노출·P2 sim basis_article/legal_basis 노출(이미 산출값 노출만)·P6 옥탑 산입/결손 trace(height_rooftop_included/unknown 대칭)·P8 gfa 층별 measured/제외단계 caveat·P18 pilotis/basement 개방·전량제외 전제 caveat. 산출값 불변(설명 메타만)·가드 3 | 328 |
| 19 | `db358daa` | 아키텍처·설명가능성 | ★P-DUAL: DualPathCheck 파이프라인 결선(dual_path_status=None 박제 해소) — calc_target.declared(명기 면적표값) vs 산정 lq.value 대조(area_tol 밴드), rule.target_variable↔lq.variable_id 매핑으로 finding별 dual_path_status 주입, 불일치 HELD→final_gate NEEDS_REVIEW. evidence에 dual_path(table/geom/delta/status/자기참조 caveat). 통합테스트 2(불일치HELD/일치AGREED). declared 미제공 시 None 유지(기존 동작·결정론 보존) | 330 |
| 20 | `e1b9ba5e` | 설명가능성 | (감사 P21·P22) upzoning_scenarios 각 시나리오에 Rationale(도출식·국토계획법시행령§85/§78·이론상최대 한계) 부착·upzoning_signals에 legal_basis(국토계획법§78·도시정비법 기본+매칭신호 §52/건축법§60/경관법§9, 등록본만·미상 placeholder). land_card free dict 노출 보강·가드 2 | 332 |
| 21 | `1deaae69` | 설명가능성·아키텍처 | (감사 P3·P4·P5 — 마지막 high 갭) PrecedentStat.rationale(분포 도출이유·과반근거·구속력없음 한계, SUFFICIENT/INSUFFICIENT)·PrecedentMatch.method/caveats(임베더+코사인·클램프·절단)·search_cases(return_meta=True 3튜플: 임계·선택사유·탈락분, 2튜플 하위호환)·precedent를 report item으로 합류(VECTOR_SEARCH 단일문자열→도출맥락 동반). 가드 3 | 335 |
| 22 | `(this)` | 설명가능성 | (감사 P7·P10·P11 — 5.0향) P7 CalcEngine HELD 강등사유 held_reason trace(UNKNOWN/저신뢰/주차미상 — 무라벨 HELD 제거)·P10 parking_flow 법령접지(legal_refs 주차장법시행규칙§6 등록·basis 해소)+통로폭/단부거리 미검증 범위 caveat·P11 view_skyline 경관법§9 접지+통경축 미산출·clamp 절단 caveat. 산출값 불변·가드 2 | 337 |

**재리뷰 점수 추이**: security 3.0→4.0→4.5(iter15 레이트리밋), 계약 3.0→3.5→3.8→4.4→4.5(iter16 SimMetric.unit enum 계약강제), 정확성 3.0→3.5→4.0→4.3→4.5(iter17 PARKING 거짓적합 제거: 지상주차 산입·미상 HELD),
테스트 3.5→3.7→4.2→4.5(iter12~13 스캐너 사각지대 제거: 함수기본값/call-kwarg 하드코딩까지 게이트), 아키텍처 3.0→3.2→4.2→4.5(iter19 P-DUAL 결선: dual_path_status 박제 해소·명기vs산정 대조), 견고성 3.5→4.2→4.5(iter14 egress 비양수 가드: 0division/음수시간 무음오판 제거),
security 3.0→4.0→4.5(iter15 레이트리밋: 외부 1차출처 쿼터/비용 폭주 방어, /health 면제). 결정론 4.5 유지·설명가능성 4.0→4.5(iter18~21: 감사 28갭 중 high 전부+다수 해소 — P1·P2·P6·P8·P18·P21·P22·P3·P4·P5).

**★설명가능성 감사(2026-06-17, 멀티에이전트 워크플로 w6r4klvk1, 14에이전트)**: 6영역 전수감사+반증검증으로 **28개 확정 갭**(전부 file:line 검증) + dual_path 평가. 모든 수정은 **산출값 불변·설명 메타(rationale/legal_basis/caveats/reason/trace)만 추가**. 우선순위 P1~P22(TIER1 노출만→…→dual_path 결선). dual_path 핵심: 부품(DualPathCheck·게이트강등·area_tol·명기 outer_area) 다 EXISTS, **pipeline 결선만 MISSING**(analysis_pipeline `dual_path_status=None` 하드코딩+기하 geom 산정경로 부재). iter18=P1·P2·P6·P8·P18 적용.

**iter15 주의(정직)**: 레이트리미터는 **프로세스 로컬 카운터** — 다중 워커/인스턴스 분산 강제 아님(각자 셈). 운영 분산은 Redis 등 공유 스토어 필요(미구현, app.core.rate_limit docstring 명시). 기본 0=비활성(기존 스위트/배포 무영향), 운영 활성화는 REQUESTS_PER_MINUTE 설정. 설정변수명은 'limit' 법정키워드 회피(REQUESTS_PER_MINUTE) — 스캐너 희석 없이 INV-3 엄격 유지.

**iter13 주의(정정 방지)**: 측정치 함수기본값(`existing_floor_area=0.0`·`rooftop_area=0.0`)은 법정상수 아님 → allowlist(정확한 이름만; `floor_area_ratio`=FAR 같은 법정명 substring 누수 방지). shadow_3d 값은 sim_params.json으로 **동일값 이전**이라 결정론·출력 byte-동일 보존.

---

## 2. 미적용 / 완화 / 보류 (이유 + 재작업 조건)

> ⚠️ 아래는 **의도적으로 적용하지 않았거나 다른 방식으로 완화**한 항목. 동일 방식 재시도 금지, 조건 충족 시에만 재작업.

1. **아키텍처 preflight 전면 차단 → 표면화로 완화** (`11523124`)
   - 미적용 이유: 축척 입력 경로가 없어 PreflightRefused 시 도면 자동산정을 전면 차단하면 기능이 무력화됨
     (`test_calc_target_auto_from_area_table` 회귀). 차단 대신 `preflight_blocked` 플래그 + 신뢰 제한 advisory로.
   - **재작업 조건**: AnalysisInput에 축척(scale) 입력 경로를 정비한 뒤, preflight 거부 시 도면-파생 LegalQuantity를
     status=HELD로 강등·전파(enforcement). 그 전엔 advisory 유지.

2. **정확성 PARKING 계산 수정 → ✅ 적용** (`(this)`, iter17)
   - SemanticType에 새 enum 추가 대신 **CalcElement에 `underground`/`accessory` bool|None 필드**로 표현(요소 속성이
     의미타입보다 적합). area_calculator `parking_far_eligibility()`: 지하 AND 부속만 제외(ELIGIBLE), 지상·독립 산입
     (INELIGIBLE), 미상(UNKNOWN)은 무음 전량제외 금지(보수적 산입)+CalcEngine held=True(status=HELD). far_parking_held
     trace로 표면화. 전량차감 거짓적합(FAR 과소) 제거.
   - 잔여: underground/accessory를 상류(도면추출/분류 provenance)에서 채우는 배선은 별도(현재 미주입 시 미상→HELD가 안전기본).

3. **테스트 static_scan 함수 기본인자 탐지 → ✅ 적용** (`fcb5da3b`, iter13)
   - shadow_3d 법정 임계 5종(min_hours/sunlight_threshold/floor_height_m/관측창)을 sim_params.json SSOT로 외부화(동일값
     이전=결정론 보존) 후, static_scan에 FunctionDef defaults/kw_defaults + call-kwarg + 튜플언패킹 + 튜플/리스트 값
     순회 추가 + 회귀가드 5. 측정치 함수기본값(existing_floor_area=0.0 등)은 allowlist(정확한 이름만).

4. **아키텍처 dual_path 배선 → ✅ 적용** (`(this)`, iter19)
   - calc_target dict에 선택 `declared`(명기 면적표 최종값) 키 추가(별도 데이터모델 신설 대신 기존 calc_targets 통과 활용).
     pipeline에서 `DualPathCheck(tol=param('area_tol')).check(table=declared, geom=lq.value)` 대조 → `dual_path_by_variable`,
     rule.target_variable↔lq.variable_id 매핑으로 finding별 `dual_path_status` 주입(`:328` None 박제 해소). 불일치 HELD→
     final_gate NEEDS_REVIEW(이미 EXISTS). evidence에 DualPathResult 동반.
   - **잔여(정직 명시)**: 현 geom=명기 입력(outer_area) 차감값이라 declared와 동일 출처면 자기참조 → caveat로 고지.
     **독립 기하 산정경로(shoelace/polygon_area)**는 후속(면적표 declared와 진짜 독립 대조하려면 필요). declared_* 자동
     추출(area_table 채우기)도 후속 — 현재는 calc_target에 명시 주입 시 동작.

5. **BCR 조례(ordinance_bcr) → ✅ 적용됨** (`da3fe354`, iter8)
   - upzoning ORDINANCE_BCR(서울 §54 건폐율) + remaining_capacity BCR 조례 우선·미등록 시 시행령+caveat(FAR과 대칭).
   - 잔여: 서울 외 시도 건폐율 조례 미등록(미등록 시 caveat 표면화 중). 재리뷰로 정확성 점수 확인 예정.

6. **security 레이트리밋 → ✅ 적용**(`56caf153`, iter15) / CORS는 production validator로 충분
   - ✅ pnu: AnalysisInput.pnu Field(pattern) 적용(iter10). 예외에코 코드만(iter7s).
   - ✅ 레이트리밋: **slowapi 의존성 대신 무의존 인메모리 FixedWindowRateLimiter**(core/rate_limit) + http 미들웨어
     채택(클라별 분당 상한·/health 면제·429). REQUESTS_PER_MINUTE(0=비활성). ⚠️**방식 차이 기록**: 프로세스 로컬이라
     분산 강제 아님 — 다중 워커 운영은 Redis 백엔드 필요(미구현, docstring 명시). slowapi는 추가 의존성·동일 분산한계라 무의존 선택.
   - CORS: production validator(와일드카드/무인증 거부, settings._production_fail_closed)로 충분 — 추가 미들웨어 불요.

7. **계약 측정치 nan/inf → ✅ 적용** (`832c9acd`, iter11): _types.FiniteFloat(allow_inf_nan=False)를
   EvalCase/Finding measured_value·limit_value·SimMetric.value·LegalQuantity.value에 적용(nan≤limit 무음 오판 차단).
   잔여: SimMetric.unit raw str(medium, Unit enum화)·CalcTraceEntry 수치필드 FiniteFloat 확대.

---

## 3. 정정·교훈 (방식 자체가 틀려 변경한 것 — 동일 실수 방지)

- **similarity는 Probability(ge=0) 부적합 → Similarity[-1,1]**: cosine 유사도는 음수 가능. `_types.Similarity`로 정정.
  추가로 부동소수 오차로 |cos|>1 미세초과 → matcher에서 `max(-1,min(1,score))` clamp.
- **인증 positive를 client 기반 테스트 → require_token 단위 테스트**: client+settings 전체 실행 시 격리 간섭으로 flaky.
  단위 테스트로 견고화.
- **⚠️ 재리뷰 워크플로 경로 오류**: 워크플로 리뷰 에이전트가 BASE(정본 Development_AI_deliberation) 대신 **원본
  propai-review(phase/pipeline)를 읽어** 정확성을 "BCR 미반영"이라 허위 판정(실제 정본엔 실재). → 재리뷰 프롬프트에
  **"git 명령 금지, BASE UNC만 Read, 다른 repo/브랜치 접근 금지"** 강제. verify-gaps-with-real-code로 직접 Grep 병행.
