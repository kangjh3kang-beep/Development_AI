# Flagship B — 이미지융합 AVM (PoC) 프론트엔드 구현 보고

커밋: `644beaf` feat(avm-vision): 이미지융합 AVM 패널(항공특징+실험적 보정 전/후+EXPERIMENTAL 배지)

## 1. 신규/변경 파일 · 배치 위치

작업 루트: `propai-platform/apps/web`

| 파일 | 내용 |
|------|------|
| `components/avm-vision/types.ts` (신규, 61줄) | 계약 스키마 그대로 TS 타입. `AvmVisionRequest`, `AvmVisionImage`(center/zoom/bbox/thumbnail_url 포함), `AvmVisionFeatures`, `AvmVisionResult`. experimental:boolean, source "image"\|"proxy", thumbnail_url 항상 null 반영 |
| `components/avm-vision/AvmVisionPanel.tsx` (신규, 340줄, client) | 본체 패널. 입력(주소 필수 + 선택 기준시세) → `apiClient.post("/avm-vision/analyze")` → 항공썸네일/특징카드/보정 전후/confidence/note/sources |
| `components/operations/DeskAppraisalReportClient.tsx` (수정 +11줄) | **예상시세(desk appraisal) 화면에 결합**. 추정 결과(`res.ok`) 생기면 보고서 카드 아래 `<AvmVisionPanel>` 렌더, 기준값 시드(appraised_total_won / appraised_price_per_sqm / pnu / ranAddr) |
| `app/api/vworld/data/route.ts` (수정 +25줄) | 기존 VWorld 프록시에 `service=image` 분기 추가 — `/req/image` getmap PNG 바이너리 패스스루(Referer 헤더 부여, Cache 1d) |

**배치 결정**: 신규 라우트 대신 기존 `desk-appraisal` 화면(`app/[locale]/(dashboard)/desk-appraisal/page.tsx` → DeskAppraisalReportClient)에 자연 결합. 추정 보고서가 산출된 직후 동일 주소·기준값을 시드받아 패널이 나타나므로 사용자가 "예상시세 → 이미지융합 실험보정"을 연속 흐름으로 본다. (과한 신규 진입점 회피 — 지침대로 기존 화면 결합 우선)

## 2. VWorld 키 클라이언트 노출 처리 (★ 핵심 판단)

- **기존 코드 확인 결과**: `lib/vworld-client.ts:10`에서 이미 `NEXT_PUBLIC_VWORLD_API_KEY`를 클라이언트 사용 중. 주석에 "공개 API 키이며 도메인 제한으로 보호된다"고 명시 → **이미 의도적으로 노출된 도메인제한 공개키**. 따라서 썸네일 직접 렌더 채택(키 노출 회피 생략 분기로 갈 필요 없음, 기존 정책과 일관).
- **단, getmap 직접 호출은 회피**: VWorld `/req/image` getmap은 **Referer 헤더 필수**(백엔드 보고 함정: `Referer: https://www.4t8t.net`). 브라우저 `<img src>`는 Referer를 설정 못 해 403/빈응답 위험. → **기존 Next.js 프록시(`/api/vworld/data`)에 `service=image` 분기를 추가**해 서버측에서 Referer 부여 후 PNG 패스스루. 키는 쿼리로 전달하되 프록시 경유라 외부 노출 표면은 기존 data/address 프록시와 동일.
- **썸네일 URL 구성**(`thumbUrl`): `image.available && image.center && image.zoom`일 때만. `center=[lon,lat]`, zoom 7~18 클램프, basemap=PHOTO, crs=EPSG:4326, size=512,512, version=2.0 — 백엔드 보고의 라이브 확정 파라미터 그대로.
- **graceful 폴백**: 키 없음/`image.available=false`/`<img onError>` 시 "영상 분석 완료(서버측)" 또는 "항공영상 미취득" 안내 + 특징만 표시(직접 렌더 생략). 안전 우선 분기 내장.

## 3. 응답 타입 계약 일치 · 재사용 컴포넌트

- `components/avm-vision/types.ts`가 계약(11)·백엔드 확정(12) 1:1 매핑: image 블록에 `center:[lon,lat]`·`zoom` 추가 필드 반영, `thumbnail_url` 항상 null, `features.source`="image"\|"proxy", `experimental` 항상 true, `adjustment_pct` ±8 상한, `confidence` 0~1.
- 재사용: `apiClient.post`(자동 `/api/v1` prefix, body 객체 자동 JSON), `@propai/ui`의 `Card`/`CardContent`. 패널 자체 경량 위젯(`FeatureBar`)은 단일용도라 별도 추상화 없이 내장.
- 의미색 일관 팔레트: 상향=#10b981(green), 하향=#ef4444(red), 실험=violet(#a78bfa 계열), 도로접면 good/normal/poor=green/amber/red. 하드코딩 hex는 의미색(상향/하향/실험)에만 한정, 레이아웃/표면은 디자인 토큰(`var(--surface-*)`, `var(--line)`, `var(--text-*)`, `var(--accent-strong/soft)`) 사용.
- EXPERIMENTAL 배지(헤더 violet pill, 눈에 띄게) + note(프록시/미취득 사유, ⚗ 마커) + rationale(보정 근거 서술) + sources + 면책 문구("법적·평가적 효력 없음, 참고 지표") 전부 노출 — 과신 방지·할루시네이션 방지 철학 유지.

## 4. 로컬 검증 · 커밋

- `npx tsc --noEmit` → **EXIT 0** (전체 web 패키지).
- `npx eslint` (신규 2파일 + 변경 2파일) → **0 errors**. 1 warning은 `DeskAppraisalReportClient.tsx:394 yMax` 미사용 — **내 diff 아님(기존 코드)**, git diff로 확인.
- `apiClient` import 보존 확인(회귀 함정): `AvmVisionPanel.tsx:13 import { apiClient }` 존재.
- 커밋: 명시 경로만 `git add`(4파일, `git add -A` 미사용 — 동시세션 race 회피). 커밋 전 `git diff --staged` 점검 완료. footer Co-Authored-By 포함.
- **커밋 해시: `644beaf`**. git push는 하지 않음(지침).

## 5. 운영 메모

- 배포에 cv2 미설치면 `features.source="proxy"`로 떨어져 배지가 "공간컨텍스트 추론"(amber) 표시, cv2 설치 시 "영상분석"(violet)으로 승격 — 프론트는 `features.source`만으로 자동 구분.
- 항공썸네일은 `/api/vworld/data?service=image` 경유. Cloudflare Workers 서울 엣지라 한국 공공API 접근 원활(기존 프록시 주석 근거). 키는 `NEXT_PUBLIC_VWORLD_API_KEY`(빌드 환경변수)에 의존 — 미설정 환경은 자동 폴백(특징만 표시).
- 기준시세 미입력 시 패널은 상위 desk 추정값(`appraised_total_won`)을 시드로 전달하므로 백엔드 재산출 없이 즉시 융합. 사용자가 입력칸에 다른 기준값을 넣으면 override.
