# 159 프론트 잔여 오류 수정 (스윕 156 발굴)

루트=/home/kangjh3kang/My_Projects/Development_AI, 프론트=propai-platform/apps/web
무목업 / push·배포 없음 / git add 미수행(검토용) / 린터 import 트랩 git diff 확인 완료.
site-analysis page.tsx·DesignStudio.tsx 미접촉(병렬 executor 영역 회피).

## #G FeasibilityResultView.formatWon 무가드 가드 추가 (완료)
- `components/feasibility/FeasibilityResultView.tsx:21` formatWon 첫줄에 가드 추가:
  `if (value == null || !Number.isFinite(value)) return "—";`
- API가 npv_won 등 누락 시 `undefined.toLocaleString()` TypeError 잠재 크래시 방지. formatPriceKr 동일 패턴.

## #C /ko/parking 404 (빈 라우트) 정리 (완료)
- grep 결과: 사이드바/네비(SidebarNav.tsx 등)에 `/parking` href 링크 **없음**(grep exit 1).
  - `parking` 문자열은 모두 실 기능 내부 필드/식별자: safety/ParkingLogView(`/parking/dashboard` API), regulation 한도(주차), design 주차대수 산정, unit-mix 주차계수 등 — 라우트와 무관.
- 주차분석은 설계/BIM/인허가의 주차대수 산정에 포함 → 별도 page 불필요. 死라우트 판정.
- 조치: 빈 디렉터리 `app/[locale]/(dashboard)/parking/`(page.tsx 없음) 제거. git 미추적(empty dir)이라 git 조작 불필요.

## #E regulation/analyze 402 안내 (완료)
- `components/operations/RegulationsWorkspaceClient.tsx`: 기존엔 useLlm 체크박스 default true인데 402를
  generic catch가 "규제 분석에 실패" 일반메시지로 흡수(콘솔오염·오인안내).
- 수정: ProjectLegalWorkspaceClient(:472 기존 패턴)와 통일 — use_llm:true 호출 402(ApiClientError status===402) 시
  use_llm:false로 폴백 재호출 + `llmGated` 상태로 정직 안내:
  "AI 통합 해석은 잔액/구독 필요 — 계층·정량 한도·영향도는 표시됩니다." (amber).
- ApiClientError import 추가(`{ ApiClientError, apiClient }`), git diff 보존 확인.
- EnvironmentAnalysisPanel.tsx 조례병행 호출은 이미 `use_llm:false`(:255)라 402 불가 → 무수정(정상).

## #F digital-twin /latest 404 노이즈 (조치 불필요 — 이미 처리됨)
- `DigitalTwinControlTowerWorkspaceClient.tsx`의 status/risk/permit `/latest` 3개 호출은
  모두 `optionalGet`(:68) 경유 → ApiClientError status===404를 `null`로 변환(:72), 에러 안 던짐.
- 이미 "데이터없음=null" 정상처리. 추가 수정 불필요.

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- git diff: FeasibilityResultView(+1), RegulationsWorkspaceClient(+28/-6), ApiClientError import 보존.
- 무목업 준수, 디버그코드 없음.

## 미진/주의
- git add·commit·push 미수행(작업 지시대로 검토용 상태).
- parking 빈 디렉터리는 미추적이라 삭제만으로 정리 완료(추적파일 없었음).
