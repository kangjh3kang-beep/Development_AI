# PropAI 플랫폼 전체 완성도 감사 보고서 (2026-07-17)

> 감사 기준선: **origin/main `bd6cad60`** (전용 detached 워크트리에서 검증).
> ⚠️ 공유 메인 워크트리 로컬 main(`0123d90a`)은 origin 대비 **213커밋 stale** — 1차 감사에서 오진 다수 발생, 전건 origin/main 재검증으로 교정함.
> 방법: 6차원 병렬 감사(프론트 페이지 전수 / 백엔드 라우터 전수 / 산출물 파이프라인 7종 추적 / DESIGN.md 정합 / 경계면 QA 55항목 / 라이브 프로브) + 옵시디언 목표 트랙 대조.

## 종합 완성도: **약 91%**

| 차원 | 달성률 | 요점 |
|---|---|---|
| 프론트 페이지 (76개) | **96%** | 실질 미완 3건뿐(supervision·agent 준비중, esg S/G 미채점 — 전부 정직 처리) |
| 백엔드 API (~780 EP, include 121) | **96%** | 침묵 폴백 사실상 0, 무목업 규율 관철(정직 503/501/502). 고아 라우터는 origin/main에서 이미 정리됨(avm만 의도적 제외) |
| 산출물 파이프라인 (7대분류/16세분) | **94%** | BROKEN 0. 유일 PARTIAL = G2B 모달 미표시 3필드 |
| 경계면 정합 (55항목) | **~84%** | FAIL 11 중 2건은 origin/main에서 기수정/소멸 → 유효 9건(Major 3·Minor 6) |
| 디자인 정합 (DESIGN.md v3.0) | **78%** | 뼈대(토큰 SSOT·셀프호스팅 폰트·Lucide 단일) 100% PASS. 실점=Tailwind 상태색·그림자 정리부채 |
| 라이브 배포 | **95%** | 서비스 전면 UP. 프론트 1배포 랙(v426 라이브 vs v427 머지됨 — 배포요청 대기 중) |
| 옵시디언 목표달성도 | **90~92%** | 6대 캠페인 중 5 완결·1(사통맵) P0 완결 |

## 유효 결함 목록 (origin/main 기준 확인분)

### Major
1. **기성 청구기간 무음 소실** — `BillingDashboard.tsx:211`이 `period` 전송 ↔ `cost.py:587-588` 요청모델은 `period_from/period_to` → 값 증발(목록 기간 컬럼 빈값).
2. **다필지 배치 잡 FAILED 도달불가** — `parcel_batch.py:38-41` `except: pass`, `mark_failed` 부재 → 백그라운드 예외 시 `running` 고착, 프론트(`BulkParcelBatchPanel.tsx:79`) 1.5s 무한 폴링.
3. **G2B 계산≠표시 3필드** — `market_feed`(시장동향)·qto 세부·sensitivity가 직렬화(`schemas/g2b_bid.py:333~342`)되나 `G2BBidAnalysisModal.tsx`에 타입 선언만, JSX 렌더 0. 6엔진 중 표시 4/6.
4. **(잠복) C2R RunStateEnum ↔ 렌더 상태 어휘 분리** — `run_store.py` update_state 호출 0, 렌더 상태는 미영속 애드혹 문자열. 현재 소비자 없어 영향 0(P3 배선 전 정합 필요).

### Minor
5. `Balance.markup_pct` 유령 필드 4곳(백엔드 의도적 미반환) / guest 브랜치 필수 키 누락(`billing_service.py:414-419`).
6. `/market/report` 응답 `post<any>` 무타입 경계(`MarketInsightsWorkspaceClient.tsx:429`).
7. **`@propai/types` 패키지 사망** — apps/web import 0건, 미러 drift(ProjectResponse·TaxCalculationResponse). 동기화 or 폐기 결정 필요.
8. `JobState.EXPIRED` dead enum / 배치 완료 라벨 completeness 기준(FAILED 방출 시 오표기 잠복).
9. 死모듈 `land_conversion_charges.py`(호출 0) — 삭제 전 repo-wide 참조검사 필요.
10. `/zoning/parcel-boundaries` 법정한도 인라인 병렬 구현(`effective_*` 명명 — SSOT 미오염이나 지도 표시값 발산 소지).
11. `routers/bim.py:78` /threejs JSON 경로 소비처 불명 / `/reports/generate` 레거시 폴백 pdf만(pptx/docx 런타임 실패 시 500).
12. 네비 미등록 2건: `analytics/esg`(DashboardEsgScore 카드로만 진입), `settings/team`(BillingMeter로만 진입).
13. 디자인 정리부채: 상태색 Tailwind 팔레트(`ui/Badge.tsx:18-20`·`ui/Button.tsx:18` → 132파일 파급), 기본 그림자 클래스 153파일, 리터럴 상태색 hex(`BillingMeter.tsx:168,182` 등), 렌더 이모지 4~6파일, ㎡/평 병행 69%·평 소수자리 규격 편차(`formatters.ts:101-108`).

### 운영/인프라
14. **★로컬 공유 메인 213커밋 stale** — 이 트리 기준 감사·개발 시 완결 기능을 BROKEN 오판·기수정 코드 재구현 위험. (본 감사에서 실제 오진 유발: 디자인 28%→실측 78%, C2R BROKEN→COMPLETE, 고아 라우터 3→0 등)
15. **프론트 배포 랙** — 라이브 sw=v426, origin/main=v427(#351·#352·#353 미배포). 통합자 배포요청 게시 상태와 일치.
16. **platform_secrets → web 미배선**(옵시디언 07-17 기록) — 관리자 키 등록이 web 컨테이너에 무효. PLAN 편입 상태.

## stale 오진으로 기각된 항목 (기록 목적)
- 디자인 정합 28%(토큰 3중 분열·폰트 미로딩·Inter 사용·이모지 22파일) → 실측 78%, 뼈대 전부 PASS
- 백엔드 고아 `app/routers/auth.py`·`v2_tax.py` → 07-12 삭제 완료
- C2R 렌더 BROKEN / 개략수지 심볼 부재 / 단가 3계층 → 전부 origin/main에 완결
- BuildCostCard `cost_range` 키 불일치 → `cost?.range ?? cost`로 기수정
- LifecycleStageViews `/esg` dead link → 컴포넌트 자체 삭제로 소멸
- 영업 서브앱 nav 미등록 → `route-registry.ts:398-427` 등록 완료
- MOCK 배지 오해 → `runtime-mode.ts:12` 기본 live

## 옵시디언 목표 트랙 대조 (query 모드 — 볼트 무수정)
- 완결: 배선설계도 G1~G10 / 실효FAR SSOT(11PR) / 생성허브 계열(#338→#348→#352) / C2R CAD·BIM WP 13건(WP-K=BLOCKED_INPUT) / 수지·적산 P1~P4②
- 잔여: 사통맵 UX overhaul 후속 WS·admin키 web 배선·pubprice 분해단가 확정·비차단 백로그(#338 LOW 4·#352 후속 4)
- SSOT 신선도: `wiki/projects/PropAI.md` 본문이 07-11~15 기준(최근 3캠페인 미반영) — 갱신 권장

## 권고 우선순위
1. (P0-운영) 공유 메인 origin/main 동기화 + 프론트 v427 배포 완료 확인
2. (P1-실결함) Major 1~3 수정: period 필드 계약, mark_failed 전이, G2B 모달 3필드 렌더
3. (P2-구조) @propai/types 존폐 결정 · admin키 web 배선 · parcel-boundaries SSOT 수렴
4. (P3-부채) 상태색/그림자 토큰화 캠페인(코어 프리미티브 2파일 수정 → 132파일 자동 수렴), ㎡/평 formatArea 규격
