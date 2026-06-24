# PropAI(사통팔땅) 플랫폼 전수 감사 · 개선·완성·디자인 통합 계획서
**작성: 2026-06-24 · 방법: 3개 전문 에이전트(페이지/데이터/디자인) 병렬 감사 + 메인 합성 · 근거: 코드 직접 정독(추측 배제)**

목표(플랫폼 합의): ①인간개입 최소화 ②전문가 더상세+시간절감 ③비전문가 전문가대행 ④광범위 누락없는 데이터수집→거름→통합분석 + 모든 산출물 근거·링크 제공.

---

## 0. 핵심 결론 (Executive Summary)

- **목업/깨진 페이지**: 이번 세션 3개 수정(multi-parcel·agent·supervision) 후 **영어 하드코딩·가짜데이터 목업은 소스에서 0건**. 깨진 페이지 0건. 플랫폼 표면 품질은 양호.
- **진짜 위험은 "보이지 않는 곳"에 있다**:
  1. **분석 2대 코어(심의·설계)가 '점 배선'**이다 — 종합분석 플래그십(`comprehensive_analysis_service`)이 심의/설계 코어를 **우회**하고, 심의엔진은 `DELIBERATION_ENGINE_URL` 기본 빈값 = **런타임 graceful no-op**. "모세혈관 배선" 합의의 토대가 사실상 비어 있을 수 있음.
  2. **데이터 수집 절단** — MOLIT 실거래·VWorld 규제·건축물대장 제목부가 **단일 페이지(numOfRows 고정, totalCount 미검증)** → "광범위 누락없는 수집" 원칙 정면 위반. 적정분양가·AVM 앵커가 부분표본 기반.
  3. **법령 진실원천 이중화** — `legal_reference_registry`(121) vs deliberation `_REFS`(73)가 다른 스키마로 공존 → 같은 조문이 다르게 인용. 원칙 "단일경유" 미충족.
  4. **근거·링크 표준계약이 ~25/108 라우터만 적용** — "모든 산출물에 근거" 원칙 전역 미달.
  5. **디자인 일관성 부채** — 영문 UI 혼입, 반응형 없는 `grid-cols-N` 다수(이번 세션 토지조서 오버플로우와 동류), `text-[9px]` 가독성, 근거표시 산발.
- **가장 잘된 것**: "무관자료 거름(②)"(특이부지·다필지 게이트·trust 이상치 제외) = 모범. 폴백 정직성(가짜값 미생성) = 양호.

---

## 1. 페이지 구성·기능 구현 (목표 부합도)

### 확인된 사실
- REAL 확정(전수 샘플): projects/[id]의 blockchain·contracts·finance·construction·esg·permit·legal·report·orchestrate·bim·design·cost·cad·boq·site-analysis + dashboard의 center·precheck·analysis·market-insights·permits·regulations·auction·g2b·land-schedule·registry-analysis·sales 전부 실연동.
- 목업 0 / 깨짐 0(이번 세션 수정 후).

### 갭 + 권고
| 항목 | 근거 | 권고 | 우선 |
|------|------|------|------|
| 심의분석 페이지가 **고정 SAMPLE_PAYLOAD**로만 시연 | `DeliberationResultPanel.tsx:82` PNU 고정·합성 FAR | 실부지 입력(SSOT/주소) 배선 → 비전문가가 자기 땅 심의(목표③). 배선 전 "데모 입력" 배지 | P0/P1 |
| `canvas`↔`multi-parcel` **지도 단일창 중복** | 둘 다 `ParcelBoundaryMap`+우측 분석 | 역할 명확화(단일=canvas, 다필지=multi-parcel) 또는 통합. `canvas`는 nav 미등록(준-고아) → 정식 등록 | P1 |
| ExtensionModulesGrid `demo:true` **stale** | agent/supervision은 이제 정직 플레이스홀더 | `demo`→`comingSoon` 의미로 재라벨 | P0 |
| 시공·실행 단계 자동화 공백 | agent(AI 실행 콘솔)·supervision(감리/공정) 미배선 | 전주기 체인 완성 위해 실배선(P2) | P2 |
| 운영 계층 비노출 | operations/tenant/maintenance/digital-twin 실배선됐으나 nav 숨김 | 성숙도 점검 후 운영권한 노출 검토 | P2 |

---

## 2. 데이터 조사·수집·분석 최적성 (원칙 ①③④)

### 충족도 (확인된 근거 기반)
| 원칙 | 충족도 | 핵심 근거 |
|------|--------|----------|
| ① 광범위 누락없는 수집 | **부분 60%** | MOLIT 실거래·VWorld 규제·대장 제목부 단일페이지 절단. (전유부 페이지네이션은 양호) |
| ② 무관자료 거름 | **양호 85%** | detect_special/multi_parcel 게이트·면적가중 dominant·trust 이상치 제외 = 모범 |
| ③ 통합분석 | **부분 55%** | /integrated-analysis 면적가중·GFA합 우수. 그러나 area SSOT 파편(feasibility/cost/esg 각자 수집) |
| ④ 근거·링크 표준제공 | **부분 50%** | evidence_contract 설계 우수, 소비처 ~25/108. 법령 SSOT 이중화 |

### P0 (데이터 정확도 직결 — 착수 전 결정 필요)
1. **MOLIT 실거래 `totalCount` 루프 페이지네이션** — 현재 `pageNo=1,numOfRows=100` 단일호출 무음 절단(`molit_service.py`·`molit_client.py`). 적정분양가·AVM 앵커 정확도 직결. (전유부 패턴을 실거래에 이식)
2. **법령 SSOT 이중화 해소** — `legal_reference_registry`(121) ↔ deliberation `_REFS`(73) 통합/어댑터 결정(메모리 LegalHub facade 계획 실행 여부).
3. **심의엔진 활성화 정책** — `config.py:52 DELIBERATION_ENGINE_URL=""` 기본 비활성이 의도인지, 프로덕션 설정 보장되는지 확정.
4. **종합분석 코어 연결 여부** — `comprehensive_analysis_service.analyze()`가 심의/설계 코어·SpecialistAgent 미호출(우회). "코어 중심 통합" 합의와 격차 — 연결할지 결정.

### P1
5. **공유 ProjectContext(통합면적·dominant zone·blended_far·special_parcels)** 도입 → 부지→수지→공사비→ESG 단일 입력 경유(area SSOT 일원화, 재수집·불일치 제거).
6. VWorld 규제/bbox `totalCount` 검증·페이지 루프.
7. KOSIS 폴백 상수(전국평균 4,200만원) 소비처 가드 강제.
8. evidence 표준블록을 미적용 분석 라우터(avm·market_ai·finance·construction 등)로 확대.

### P2
9. 수집기 provenance(source+timestamp) 전수 부착. 10. VWorld 필지 캐시 TTL. 11. SpecialistAgent 레지스트리 분석 라우터 경유.

---

## 3. 디자인·구성·워크플로우 가독성/직관력 (목표 ②③)

### P0 (회귀 없음·범위 소)
- **영문 UI → 한국어**: `projects/[id]/page.tsx:203 "Initializing Strategic Hub…"` 등(로딩·`cc-meta` eyebrow 36곳·`ModuleCommandStrip` label). 한국어 원칙.
- **반응형 없는 `grid-cols-N` 수정**: `ReferenceAssemblyCard`(4열)·`PersonaPanel`(4열) 등 → `grid-cols-2 sm:grid-cols-4`. (이번 세션 토지조서 오버플로우와 동류 — 전역 패턴)
- **테이블 `min-w-0` 누락**: lease-ops·auction·cost·pipeline 등 `overflow-x-auto` 부모 grid에 `min-w-0`(토지조서 기수정 패턴 전파).
- **외부 텍스처 URL → `cc-grid-bg` 토큰**: `transparenttextures.com` 6파일(CSP·오프라인 안전).

### P1 (여정·가독성)
- **공용 `<ProjectHeroHeader>` 병합**: projects/[id] 허브의 Hero+Metadata 중복(PNU·용도지역 2회 표시) 일원화.
- **`text-[9px]` → `text-[11px]` 전역 승급**(가독성 하한).
- **부지분석 결과 후속 CTA**(ComprehensiveAnalysisPanel → "이 부지로 프로젝트 생성") — 여정 단절 해소.
- **Canvas DrillCta 가시성**(11px 링크 → 전폭 버튼).
- **근거표시 표준화**: DataLineageTooltip/VerificationBadge/EvidencePanel 산발 → "신뢰수치 옆 항상 근거, 부재 시 'AI 추정' 배지" 정책.

### P2 (공용 컴포넌트화 — 한 곳 고쳐 전역 전파)
- `<ScrollTable>`(min-w-0+overflow-x-auto 강제, 25파일), `<DataKpiCard>`, `<SectionEmptyState>`, `lib/status-color.ts statusColorVar()`(상태색 토큰), OrchestratorPanel `simplified` 기본 전환.

---

## 4. 통합 우선순위 로드맵 (cross-cutting)

**P0 — 정직성·정확도·신뢰 직결 (즉시, 저위험)**
- D1 영문 UI 한국어화 · D2 반응형 grid/min-w-0 전역 스윕 · D3 ExtensionModulesGrid demo 재라벨 · D4 외부텍스처 토큰
- DATA1 MOLIT 실거래 페이지네이션 · 결정: 법령 SSOT/심의엔진/종합분석 코어연결(아래 §5)
- P1 심의 SAMPLE_PAYLOAD "데모입력" 배지

**P1 — 핵심 완성 (이번~다음 스프린트)**
- 공유 ProjectContext(area SSOT) · canvas/multi-parcel 정리 · 심의 실부지 배선 · evidence 표준 확대 · ProjectHeroHeader/CTA/근거표준화 · text-[9px] 승급

**P2 — 구조 강화 (다음 스프린트)**
- 분석코어 모세혈관 확대(종합분석·격리 라우터 코어경유) · 시공/운영 단계 실배선 · 공용 컴포넌트(ScrollTable/DataKpiCard/SectionEmptyState/status-color) · provenance 전수 · VWorld 캐시 TTL

---

## 5. 사용자 결정 필요 사항 (Open Questions)

1. **심의분석엔진**: `DELIBERATION_ENGINE_URL` 기본 비활성(graceful no-op)이 의도된 안전장치인가, 프로덕션 설정 누락인가? → "코어 중심 통합" 실효성이 여기서 갈림.
2. **법령 진실원천 이중화**: `legal_reference_registry`(121) vs deliberation `_REFS`(73)를 LegalHub facade로 통합할지, 도메인 분리(어댑터) 유지할지.
3. **분석코어 배선 범위**: 종합분석·cost·feasibility·esg 등 격리 라우터를 코어 경유로 전환할지, 현 점 배선이 의도인지.
4. **수집 페이지네이션 정책**: 전수 수집(원칙① 엄격) vs 상위 N건 표본(성능). trust 앵커 min_samples=20과 연동.
5. **evidence 표준 적용 목표**: 전 분석 라우터 100% vs 핵심만.

---

## 6. 이번 세션 선행 처리 완료(본 계획의 P0 일부 착수)
- 토지조서 grid 오버플로우 근본수정(§3 P0 패턴의 첫 사례) + 전역 동류 스윕은 P0 백로그.
- agent/supervision 영어목업 → 정직 한국어(§1).
- multi-parcel 뉴욕목업 → 실 한국어 토지이음급(§1).
- 분석흐름 HubErrorBoundary 자동복구(§3 안정성).
- 등기 apick 타임아웃·LLM 잘림·stale 캐시 근본수정(§2 수집 신뢰성).
