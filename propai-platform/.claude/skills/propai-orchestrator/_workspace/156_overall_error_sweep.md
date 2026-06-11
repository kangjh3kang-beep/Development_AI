# PropAI 전반 오류 종합 스윕 (2026-06-07)

라이브 https://www.4t8t.net (test@4t8t.net) 로그인 후 전 라우트 크롤 + 백엔드 엔드포인트 curl 헬스 + 정적 무가드 패턴 grep.
**코드 수정 없음. 오류 목록·근본원인·수정위치만.**

## 검증 방법
- 라이브 크롤: agent-browser `--session sweep` 로그인 → 각 라우트 navigate → `window.error`/`unhandledrejection`/`fetch` 후킹으로 콘솔에러·4xx/5xx·Next 에러바운더리 캡처
- 백엔드: 실토큰(propai_access_token)으로 `api.4t8t.net` 직접 curl (403=권한정상, 402=과금게이트정상 → 제외, 500/예상외404만 채택)
- 정적: `toLocaleString/toFixed/.map/.length` 무가드 grep + 타입·백엔드 디폴트 대조

---

## 오류 목록 (우선순위순)

| # | 심각도 | 라우트/엔드포인트 | 증상 | 근본원인 (파일:라인) | 수정위치 |
|---|--------|------------------|------|---------------------|----------|
| A | **Critical** | `POST /api/v1/bim/generate-ifc` | **라이브 500 재현** `INTERNAL_SERVER_ERROR`. (이미 규명된 #2 minio) | `apps/api/services/bim_ifc_service.py:37,200` `from minio import Minio` — minio는 requirements.oracle.txt:91에 추가됐으나 **Oracle 컨테이너 재배포 미반영**(이미지에 패키지 없음) 또는 MinIO 서버 미가동. import는 try밖이라 폴백 안됨 | 백엔드 Oracle SSH 재배포(pip 반영) + bim_ifc_service의 `from minio import Minio`를 try/except로 감싸 graceful 폴백 |
| B | **High** | `GET /api/v1/projects` (목록) | 응답 `"total":0` 인데 items 1건 존재 → 프론트 "0건" 표기 가능 | `apps/api/routers/projects.py:129` `PaginatedResponse(items, page, page_size, has_next)` — **`total` 인자 누락**. 스키마 `packages/schemas/models.py:34` `total: int = 0` 디폴트라 항상 0 | projects.py:129 `total=` 채우기(별도 count 쿼리 또는 `len(items)`). 동일 누락 패턴이 다른 목록 라우터에도 있는지 `PaginatedResponse(` 전수 점검 권장 |
| C | **High** | `/ko/parking` | **라이브 404** ("This page could not be found", title="PropAI") | `apps/web/app/[locale]/(dashboard)/parking/` **디렉터리는 있으나 page.tsx 없음**(빈 디렉터리). 사이드바 링크는 없어 직접진입시만 노출 | parking/page.tsx 생성하거나 빈 디렉터리 삭제 |
| D | **Med** | 프로젝트 10단계 중 legal/bim/finance/permit/report | 콘솔 `FETCH_404 /api/v1/projects/{id}` 반복 | localStorage 생성 프로젝트 UUID가 백엔드 미존재(라이브 `8f07026a…`는 목록에 없고 `1167cdda…`만 존재). `apps/web/components/projects/ProjectContextBinder.tsx:56`가 호출, **try/catch로 잡혀 크래시 아님**(localStorage 폴백) — 콘솔노이즈+기기간 동기화X | 프로젝트 생성 시 백엔드 `POST /projects` 결과 UUID를 SSOT로 사용(현재 로컬 UUID와 불일치). MEMORY `project_project_persistence` 연장 |
| E | **Med** | `/legal` (regulation/analyze) | 콘솔 `FETCH_402` | `POST /api/v1/regulation/analyze` 과금게이트(402). 정상동작이나 **프론트가 402를 사용자 안내 없이 콘솔에러로만** 남김 | 프론트 regulation 호출부에서 402(쿼터/결제필요)를 캐치해 결제유도 UI 표기 |
| F | **Med** | `/ko/digital-twin` | 콘솔 `FETCH_404` 3건: `/permits/{id}/latest`, `/risk/unified/{id}/latest`, `/digital-twin/status/{id}/latest` | 라우트는 존재하나 스냅샷 없을 때 `raise HTTPException(404)` 설계(`apps/api/routers/digital_twin.py:71-74`, `risk.py:43`, `permits.py:200`). "데이터없음"을 404로 표현 → 프론트 콘솔오염 | 백엔드를 200+null/빈응답으로 바꾸거나, 프론트 fetch가 404를 "미실행 상태"로 정상처리(콘솔에러 억제) |
| G | **Low(잠재크래시)** | feasibility/finance 단계 | `result.npv_won` 등 undefined 시 크래시 가능 | `apps/web/components/feasibility/FeasibilityResultView.tsx:20-24` `formatWon(value:number)` — **null/undefined 무가드**. `Math.abs(undefined)=NaN`이 모든 `>=` 통과실패 → line24 `value.toLocaleString()`가 undefined에서 **TypeError**. 타입은 required number지만 런타임 API 누락 시 크래시(formatPriceKr 류 동일 패턴) | formatWon 시작에 `if (value==null||!Number.isFinite(value)) return "—";` 가드 추가 |
| H | **Low** | `/ko/market` | 직접진입 404(title="PropAI") | 실제 라우트는 `/ko/market-insights`. 사이드바는 `layout.tsx:100`에서 `/market-insights`로 **정상** 링크 → 사용자 영향 적음(직접 URL만) | 영향 미미. 필요시 `/market`→`/market-insights` redirect |

---

## 무거운/누락가능 의존성 대조 (배포 import 실패 위험)
`grep import minio|boto|cv2|torch|mlflow|ifcopenshell|pygltf` → 사용처 6파일:
- `safety_service.py:96 / parking_service.py:37` `import cv2` — try/except 가드됨(graceful)
- `avm_service.py:64 import mlflow` — try/except 가드됨
- `reference_image_service.py:88 import torch` — try/except 가드됨
- `bim_ifc_service.py:37,200 / floor_plan_image_service.py:81 from minio import Minio` — **bim_ifc_service는 try밖 → #A 원인**. floor_plan은 함수내부지만 try/except 확인필요
- requirements.oracle.txt 대조: minio==7.2.10, ifcopenshell==0.8.4, opencv-python-headless 등 **명세는 존재** → 문제는 **Oracle 재배포 미반영**(MEMORY `project_oracle_deploy`: 백엔드는 SSH 수동배포 필수, 푸시만으론 미반영)

## 백엔드 엔드포인트 헬스 (500/예상외만)
- 500: `/bim/generate-ifc` (#A) — **유일한 500**
- 200(정상): zoning/comprehensive, cost/estimate-overview, esg/lca/calculate, market/report(402), permits/ai-analysis(402), regulation/analyze(402), development-methods/scenarios, land-price/estimate, zoning/parcel-boundaries, g2b/bids, expert-panel/analyze(422=검증), v2/feasibility/calculate(402)
- 그 외 404는 전부 **테스트 경로/메서드 오기**(auction은 GET /search, feasibility는 /api/v2 + /auto-recommend, esg는 /lca/calculate)로 실버그 아님

## 정적 무가드 패턴 결론
- `toLocaleString/toFixed` 429건 중 대다수 `?.`·`?? 0`·`isNaN`·`Number.isFinite`·`==null` 가드 또는 부모 `result &&` 조건 렌더로 보호됨
- **유일 실위험: #G FeasibilityResultView.formatWon** (formatPriceKr류 미가드)
- `.map()` API배열은 대부분 부모 `&&` 가드 + 백엔드 디폴트 `[]`(예: special_districts comprehensive_analysis_service.py:726 `get("special_districts",[])`)로 보호됨

## 브랜딩 일관성(부가)
- 일부 라우트 title "PropAI"(g2b는 "공공입찰…PropAI…사통팔땅" 혼용), 다수는 "사통팔땅" — 404 페이지 기본 title이 "PropAI". 통일 권장(낮음)

---
**요약**: 라이브 실재현 신규 오류 = #A(500, 기존 minio·재배포건과 동일근본) / #B(total=0) / #C(parking 404 빈 라우트). 잠재크래시 신규 = #G(formatWon 무가드). 나머지(D~F)는 콘솔노이즈·과금게이트로 크래시 아님. 사용자 지목 3건 외 **신규 채택: #B, #C, #G** (그리고 D~F 노이즈 개선).
