# PLAN: 중앙분석센터 통합 리팩토링 — 구현계획 (git 검증본)

작성: 통합자 세션 / 2026-06-28. 대상: SiteCanvas(중앙분석센터) + 90초진단 + 종합부지분석 통합.
요청: 풀스크린 지도기반 통합분석을 "중앙분석센터"로 명명, 90초진단·종합부지분석을 통합해 이동동선 최소화.

---

## 0. ★결정적 사실 (git 검증 — 먼저 읽을 것)

ultracode 워크플로우 4축 매핑 + **git 직접검증**으로 확정한 현황. (워크플로우가 stale `feat-tmp` 워크트리를 봐 "canvas 미존재·미머지"로 오판했던 것을 origin/main 기준으로 정정.)

| 사실 | 검증 |
|------|------|
| **SiteCanvas(canvas)는 origin/main에 이미 존재·배포됨** | `git cat-file -e origin/main:.../canvas/page.tsx` OK. deploy/monitor-unified-workspace(sw v350 "통합 단일창")가 main 조상 |
| **통합단일창 P0~P3.5②가 main에 전부 머지됨** | eac7f580(P0 Go/NoGo)·f49a1468(P1 compact)·3a8ced01(P2 시니어자문)·d7660780(P3.5② 매스3D) 전부 `merge-base --is-ancestor origin/main` 참. feat/unified-workspace-p0는 main에 0커밋 앞섬(완전병합) |
| **그러나 canvas는 nav 미등록 = 발견성 0** | origin/main `nav-config.tsx`에 canvas 항목 없음. 직접 URL(`/projects/[id]/canvas`)로만 도달 |
| **명명 충돌**: nav "중앙분석센타"는 canvas가 아니라 **홈** | `nav-config.tsx:49 { id:"center", label:"중앙분석센타", href:\`/${locale}\` }` → 대시보드 홈(page.tsx). 사용자 정의 "중앙분석센터"(canvas)와 이름같고 대상다름 |
| **90초진단(PreCheck)·종합부지분석(site-analysis)은 흡수 미완** | PreCheck `writeToContext=false`(SSOT 미기록·독립). site-analysis 1145줄 단일스크롤 별도 라우트 |

**결론: 이 리팩토링은 "신규 구현"도 "브랜치 병합"도 아니다. SiteCanvas 본체는 이미 라이브이고, 남은 것은 ① 명명 정합 ② 발견성(nav 등록) ③ 90초진단·종합부지분석 흡수 ④ 3중 정본 정리.** 가장 ROI 높은 관점이자 가장 정직한 결론.

---

## 1. 현황 (3기능 역할·중복·동선·SSOT)

### 1-A. 명명 충돌 (★P0에서 먼저 해소)
- 사용자 "중앙분석센터" = 풀스크린 지도기반 통합분석 = **canvas/SiteCanvas**.
- 코드 "중앙분석센타"(nav id `center`) = **대시보드 홈**(`/${locale}`). 다른 화면.
- → 용어 1:1 매핑 확정 없이 진행하면 엉뚱한 화면 수정(리스크 톱2).

### 1-B. 세 기능 역할·중복·고유

| 기능 | 라우트 | 컨텍스트 | 역할 | 중복 | 고유 |
|------|--------|---------|------|------|------|
| **90초진단(PreCheck)** | `/precheck` | 미바인딩(`PreCheckWorkspace.tsx:263 writeToContext=false`) | 임의주소 즉시 룰체크+조닝신호(발굴도구) | 용도/건폐/용적·법정한도(부지분석과 30~40%) | M01~M15 신호등, 핸드오프(`handoff.ts`) |
| **SiteCanvas(중앙분석센터)** | `/projects/[id]/canvas` | 활성 바인딩 | 좌 9탭 요약 + 우 2분할 지도(구획도↔실거래) + 상단 Go/NoGo | 요약카드 다수 DrillCta로 전용창 이탈 | DecisionBriefPanel·SeniorConsultPanel·BuildableMassPreview |
| **종합부지분석** | `/projects/[id]/site-analysis` | 활성 바인딩 | 1145줄 단일스크롤 심층(L3 comprehensive·3D트윈·AVM) | LandProfile/SiteScore(canvas와 동일 컴포넌트) | L3 1콜·계층용적률·건축물대장·지형/환경/디지털트윈 |

### 1-C. 현재 이동동선 (hop)
- PreCheck→프로젝트: 3 hop(`/precheck`→`/projects/new`→`/projects/[id]`)
- 세 기능 횡단 최악: 4 hop
- canvas 요약탭이 다수 DrillCta로 전용창 이탈 → "단일창인데 점프 유발" 안티패턴(기존 PLAN 인정)

### 1-D. 상태 SSOT (견고·검증됨)
- `useProjectContextStore.ts`(1403줄): siteAnalysis/designData/feasibilityData/costData/snapshots/manualFields
- 헬퍼: `effectiveLandAreaSqm`(site-area.ts:18·다필지보호)·`resolveFarPct/Bcr/DominantZone`(zoning-ssot)·`isReadyForFirstCompute`(store:1229)·`purifyPollutedSnapshot`(store:667·주소오염정화)
- `ProjectContextBinder`(projects/[id]/layout.tsx)가 모든 서브라우트 단일 writer → canvas는 동일 projectId 내 컨텍스트 유지(재계산/소실 없음)

---

## 2. 통합 IA 설계 (2-Tier 단일 허브)

사용자 정의 "중앙분석센터" = **canvas 라우트로 확정**(홈 nav id `center`와 분리). 기존 2-Tier 구조를 정련.

### 화면 와이어 (ASCII)
```
┌─ 중앙분석센터 (= /projects/[id]/canvas, 풀스크린) ──────────────────────┐
│ [주소 1회 입력 · 다필지 통합배지 · ★Go/CONDITIONAL/HOLD · 진행률]        │ ← DecisionBriefPanel
├──────────────────────────┬─────────────────────────────────────────────┤
│ 좌: 맥락 탭 rail(~400px)  │ 우: 통합 지도(1fr)                           │
│  [부지 미확정 시]         │  [레이어 토글] 경계·실거래·경매·분양·3D       │
│   → GlobalAddressSearch   │                                              │
│   + 90초 신호등(인라인)   │   현재: boundary↔transactions 배타전환        │
│  ───────────────────────  │   목표 P3: 다레이어 동시토글                  │
│  토지│규제│입지│개발       │                                              │
│  일조│수지│시니어│통합     │                                              │
│  [컴팩트 요약 카드]        │                                              │
│   + "전문분석 열기 →"(T2) │                                              │
└──────────────────────────┴─────────────────────────────────────────────┘
                              │ (각 탭 "열기 →")
                              ▼  [Tier2 전용창: site-analysis·design·bim·cost·report — URL 유지]
```

- **진입/빠른진단 레인**: 부지 미확정 분기(canvas:106-120 GlobalAddressSearch)에 PreCheck instant(M01~M15 신호등) 인라인 → 라우트 hop 없이 빠른진단→심층.
- **심층 탭**: 종합부지분석 L3 요약을 canvas 탭에 컴팩트 임베드, 중량(3D트윈/AVM/지형)은 Tier2 전용창 CTA.
- **Tier 분리 원칙**: 경량 요약=인패널, 중량 도구(BIM WebGL·5D적산)=전용창(단일창에 박으면 성능저하 — b5f216e 진입멈춤 이력).

---

## 3. 타당성 검증 (정직)

| 항목 | 평가 | 근거 |
|------|------|------|
| 컴포넌트 재사용성 | ✅ 쉬움(이미 80% 됨) | canvas가 이미 9탭에 AutoZoningBadge·BuildableEnvelopeCard·SolarPlacementCard·SeniorConsultPanel·DecisionBriefPanel 자급식 임베드 완료. L3EnhancedCards 단독임베드 검증 |
| 상태 SSOT | ✅ 한화면 유지 | ProjectContextBinder 단일writer·로컬탭 useState(재마운트X)·isReadyForFirstCompute 무한재계산 차단 |
| **명명 충돌** | ⚠️ P0 선해소 | nav "중앙분석센타"=홈. 용어 1:1 매핑 먼저 |
| **발견성** | ⚠️ canvas nav 미등록 | 어느 진입점도 canvas 미연결 → 단일창이 동선에서 숨겨짐 |
| PreCheck SSOT 오염 | ⚠️ 핸드오프 유지로 방어 | 흡수 시 임의주소→SSOT 새 진입점. `consumePreCheckHandoff` 1회소비 패턴 유지(직접기록=주소고착 WP-D 재발) |
| 정본화(3중 surface) | ⚠️ 회귀주의 | `/analysis`·site-analysis·canvas 3중. canvas=정본, 나머지=딥링크 강등(북마크 보존 신중) |
| 성능(중량) | ⚠️ Tier2 유지 | BIM/적산 단일창 금지(전용창) |
| KAKAO 실키 | ⚠️ 코드 외 선결 | `NEXT_PUBLIC_KAKAO_MAP_KEY` 더미→로드뷰/지적편집도/다레이어 미작동 |
| 다필지·모바일 | ✅/⚠️ | effectiveLandAreaSqm 보호 / max-h-[60vh] 작은화면 잘림 반응형 |

**쉬움(이미 됨)**: 임베드·SSOT소비·Go/NoGo·컴팩트카드·시니어탭. **어려움**: 통합지도 다레이어 동시토글(KakaoMapControls 단일화·실키), 정본화 회귀, 모바일 반응형.

---

## 4. 증분 구현계획 (P0~P3)

> ★전제: SiteCanvas 본체는 이미 라이브. 신규구현 아님 — **발견성+흡수+명명+정본** 마감.

### P0 — 명명 정합 + 발견성(nav 등록) [노력 S · 위험 中]
- **대상**: `apps/web/components/layout/nav-config.tsx`, (선택) project layout/overview의 canvas 링크
- **작업**: ① 용어 확정 — "중앙분석센터"=canvas. nav `center`(홈) 라벨/대상 정리(홈 라벨 변경 or canvas 별도 항목 추가). ② canvas를 프로젝트 컨텍스트 nav/진입점에 등록(발견성 0→1). ③ 프로젝트 개요에서 "중앙분석센터 열기" CTA.
- **게이트**: 리뷰≥9.5·tsc/eslint/build. **무회귀**: 홈(page.tsx) 무손상·전용라우트 딥링크 보존.
- **라이브검증**: nav→canvas 진입, 주소입력→Go/NoGo 표시. sw bump.

### P1 — 90초진단 진입레인 흡수 [노력 M · 위험 中]
- **대상**: `canvas/page.tsx`(부지미확정 분기 106-120), `PreCheckWorkspace.tsx`, `handoff.ts`
- **작업**: 부지 미확정 상태에 PreCheck instant(신호등) 인라인. ★`writeToContext=false` 의도 보존 — "이 부지로 분석 시작" CTA에서만 핸드오프(consumePreCheckHandoff 1회소비)로 SSOT 기록(주소오염 방지).
- **게이트/검증**: 주소→신호등→탭 자동채움 라이브·purifyPollutedSnapshot 동작. **무회귀**: `/precheck` 독립라우트·발굴(경매/G2B) 핸드오프 보존.

### P2 — 종합부지분석 심층탭 흡수 [노력 L · 위험 中]
- **대상**: `canvas/page.tsx`(토지/규제/통합 탭), `L3EnhancedCards`, `site-analysis/page.tsx`
- **작업**: L3 요약을 canvas 탭 컴팩트 임베드. 중량(3D트윈/AVM/지형)=site-analysis 전용창 CTA. 정본=canvas, site-analysis=딥링크 강등.
- **게이트/검증**: 다필지 통합값 보존(guardMultiParcelRich)·L3 캐시 재사용. **무회귀**: site-analysis 직접진입·북마크 보존(리다이렉트 신중).

### P3 — 통합 지도 + 정본 정리 [노력 M · 위험 中]
- **대상**: canvas 지도셸(303-334), KakaoMapControls
- **작업**: boundary↔transactions 배타전환→다레이어 동시토글(경매·분양 추가)·우측 본맵 클릭선택. 3중 surface 정본 정리.
- **선결(코드 외)**: KAKAO 실 JS키. **무회귀**: 기존 지도모드·딥링크 보존.

---

## 5. 권고 · 리스크 톱3

### 권고
1. **P0(명명+발견성)부터** — 노력 S·즉시 가시성. "이미 만든 단일창을 사용자가 못 찾는" 가장 큰 손실 먼저 해소.
2. P1(90초진단 흡수) → P2(종합부지분석 흡수) → P3(지도/정본).
3. 각 증분 게이트(리뷰≥9.5·tsc/eslint/build)→PR→통합자 머지→배포(sw bump)→라이브검증.

### 리스크 톱3
1. **명명 혼선(★)**: "중앙분석센타"(홈)≠"중앙분석센터"(canvas). 용어 1:1 매핑 없이 진행 시 잘못된 화면 수정.
2. **PreCheck SSOT 오염**: 흡수 시 임의주소→SSOT 새 진입점. 핸드오프 1회소비 유지가 안전.
3. **정본화 회귀**: 3중 surface 통합 시 기존 딥링크/북마크 손상. 리다이렉트·강등 신중.

---

## 참고 좌표 (git 검증)
- origin/main: canvas 존재·P0~P3.5②(eac7f580/f49a1468/3a8ced01/d7660780) 머지됨·deploy/monitor-unified(sw v350) 배포됨
- `nav-config.tsx:49` — center→홈(명명충돌). canvas nav 미등록(발견성0)
- `canvas/page.tsx:51-103`(9탭)·106-120(부지미확정 진입)·163(DecisionBrief Go/NoGo)·305-333(지도 배타전환)
- `PreCheckWorkspace.tsx:263`(writeToContext=false)·`handoff.ts`(1회소비)
- `useProjectContextStore.ts:667,1229`(SSOT 방어)·`site-area.ts:18`(다필지)
- 기존 기획서: `_workspace/PLAN_unified_workspace_refactor_2026-06-26.md`(2-Tier 로드맵·feat-tmp 워크트리 untracked)
