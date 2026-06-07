# Flagship A — 90초 AI PreCheck 프론트엔드 구현 보고

작업 루트: `propai-platform/apps/web` (Next.js 16 App Router, React 19, Zustand, Tailwind v4, Framer Motion)
계약서: `.claude/skills/propai-orchestrator/_workspace/06_flagshipA_contract.md` (스키마 그대로 반영)

## 1. 신규/변경 파일 · 라우트 · 사이드바 진입점

신규:
- `app/[locale]/(dashboard)/precheck/page.tsx` — thin shell(locale 검증 → PreCheckWorkspace 위임), permits 페이지 패턴 동일.
- `components/precheck/PreCheckWorkspace.tsx` — client. 입력 바 + 탭(신호등/조닝) + A/B 패널 전체.
- `components/precheck/ZoningSignalMap.tsx` — client. Leaflet+OSM(무키) 조닝 시그널 지도. ParcelBoundaryMap의 leaflet 로더/토큰 패턴 재사용.
- `components/precheck/types.ts` — 계약 스키마 그대로의 응답/요청 타입.

변경:
- `app/[locale]/(dashboard)/layout.tsx` — `lifecycleNavigation`('프로젝트 분석' 그룹) 대시보드 바로 다음에 `{ href: /${locale}/precheck, label: "90초 AI PreCheck", icon: <IconPermit /> }` 1줄 추가.

라우트: `/{locale}/precheck` (예: `/ko/precheck`).
사이드바 진입점: 사이드바 첫 섹션 "프로젝트 분석" → 대시보드 다음, 프로젝트 관리 앞.

## 2. 응답 타입(계약 일치) · 재사용 컴포넌트

타입(`components/precheck/types.ts`)은 06 계약 그대로:
- A: `InstantPreCheckRequest`{address, pnu?, area_sqm?, use_llm?} / `InstantPreCheckResponse`{ok, address, pnu, zone_type, area_sqm, legal_limits{bcr_pct,far_pct,height_m,source}, methods[{code,name,signal,permitted,complexity,complexity_label,checks[{rule,status,detail}],reason}], summary{pass,warn,fail,best,llm_note}, elapsed_ms, sources, message?}.
- B: `ZoningSignalsRequest`{address?, pnu?, radius_m?} / `ZoningSignalsResponse`{ok, target{pnu,zone_type,address}, signals[{type,score,level,parcels[{pnu,zone_type,adjacent}],rationale}], geojson|null, sources, message?, note?}.

재사용:
- `lib/api-client.ts` → `apiClient.post`(useMock:false, timeoutMs:90_000), `ApiClientError`(payload.message/detail 추출).
- `components/common/NumberInput.tsx` → 면적 입력(쉼표, allowDecimal).
- `components/ui/AnimatedCounter.tsx` → 요약 바 pass/warn/fail 카운트 애니메이션.
- ParcelBoundaryMap의 `loadLeaflet()` 패턴(unpkg leaflet 1.9.4, CSS data-leaflet 가드) → ZoningSignalMap에 동형 적용.
- 디자인 토큰(`--surface-soft/strong`, `--line`, `--accent-strong/soft`, `--text-*`, `--shadow-glow`). 신호등은 의미색 emerald(pass)/amber(warn)/rose(fail) 일관 팔레트.

UI 구성:
- 입력 바: 주소(필수)+면적(선택)+90초 즉시 진단 버튼(Enter 지원)+AI 요약 체크박스. 클릭 시 A·B `Promise.allSettled` 병렬.
- 탭 A(신호등): 요약 바(카운트·용도지역·면적·추천방식·elapsed_ms) + 법정한도 칩(건폐/용적/높이) + LLM 요약 + 개발방식 카드 그리드(signal 색 테두리·dot·칩·복잡도·reason·checks).
- 탭 B(조닝): Leaflet 지도(geojson 있으면 구획 폴리곤·레벨 색강조, 없으면 위치 개요+안내) + 시그널 카드(type 배지·score/100·level·rationale·필지 인접 배지).
- 로딩/에러/빈 상태: A `ok:false`→amber 안내(용도지역 미확인), B `ok:false`/signals=0→note 안내, 지도 geojson 0→하단 안내 오버레이.

## 3. 로컬 검증 결과

- `npx tsc --noEmit -p tsconfig.json` → EXIT 0, **error TS 0** (전 프로젝트). precheck/layout 관련 0.
- `npx eslint components/precheck/ app/.../precheck/page.tsx` → **0 errors, 0 warnings**(신규 파일).
- layout.tsx eslint 경고 3건(headers/IconSiteAnalysis/IconDesign unused)은 **사전 존재**(내 1줄 추가와 무관).
- apiClient import 보존 확인(메모리 함정 회귀 없음): `import { apiClient, ApiClientError } from "@/lib/api-client"` 정상.
- Oracle 956MB 풀빌드 미실행(지시 준수, 타입/문법 수준 검증만).

## 4. 커밋

- 해시: `90b2450` (frontend는 backend dev와 워킹트리 공유로 동일 커밋 `f446bc6`에 함께 스테이징됨 → 메시지를 풀스택 범위로 amend).
- 메시지: `feat(precheck): 90초 AI PreCheck 신호등 그리드 + 조닝 시그널 지도 UI (+백엔드)`
- footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` 포함. git push 미실행.

## 5. 백엔드/QA 정합 사항(중요)

1. **엔드포인트 경로**: 프론트는 `apiClient.post("/precheck/instant")`, `"/precheck/zoning-signals")` 호출 → `/api/v1` prefix 자동 부여. 백엔드 라우터 prefix가 `/api/v1/precheck`인지 확인(계약 일치, 커밋 f446bc6 main.py include 확인됨).
2. **빈/오류 경로 계약 준수 필수**: 용도지역 미확인 시 **`ok:false`+`message`**(빈 200 금지). 프론트는 `ok:false`면 `message`를 amber 박스로 노출(없으면 기본 문구). address/pnu 모두 없음→422는 프론트가 ApiClientError payload.detail로 표시.
3. **신호 값 enum**: `signal`/`checks[].status`는 정확히 `"pass"|"warn"|"fail"`. 그 외 값은 fail 스타일로 폴백되지 않으니 계약 enum 엄수.
4. **level enum**: 시그널 `level`은 `"high"|"mid"|"low"`. 지도 폴리곤 색강조도 이 값 기준.
5. **zoning-signals 요청**: 프론트는 A 응답의 `pnu`가 있으면 B 요청에 `pnu`로 동봉(없으면 address만). 백엔드는 둘 중 하나로 동작해야 함.
6. **geojson(선택)**: B 응답에 parcel-boundaries 형식 FeatureCollection(`features[].properties.pnu/address/zone_type`)을 주면 지도가 구획을 그리고 시그널 필지 PNU와 매칭해 레벨 색강조. `null`이면 지도는 위치 개요만 표시하고 안내 노출(빈결과 아님). → properties에 `pnu` 키를 포함해야 색강조 매칭됨.
7. **elapsed_ms**: 숫자(ms). 요약 바에 그대로 표기.
8. **타임아웃**: 프론트 timeoutMs=90_000(90초 SLA). 백엔드는 이 내에 응답해야 408 방지.

## 6. 미적용(과설계 회피)
- useProjectContextStore 저장 훅은 생략(로컬 state만). 계약상 선택이며 부담 회피 — 추후 프로젝트 컨텍스트 승계 필요 시 instant 응답(zone_type/area_sqm/pnu)을 컨텍스트에 주입하는 1훅으로 확장 가능.
- i18n: 신규 dictionary 키 추가 없이 한국어 문구 직접 사용(기존 다수 화면과 동일 관행). 토큰색은 하드코딩 hex 미사용.
