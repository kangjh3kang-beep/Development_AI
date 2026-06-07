# D3 — 설계변경 사전예측 (프론트엔드)

착공 전 설계변경 리스크(법규초과·필수요소 누락·정량 정합 모순)를 미리 보여주고
저비용 보완방안을 제시하는 패널. 백엔드 `POST /api/v1/design-risk/predict`(커밋 59c96c6) 연동.

## 1. 신규/변경 파일·배치

| 구분 | 경로 |
|------|------|
| 신규 타입 | `apps/web/components/design-risk/types.ts` |
| 신규 패널(client) | `apps/web/components/design-risk/DesignChangePredictPanel.tsx` |
| 마운트 | `apps/web/app/[locale]/(dashboard)/projects/[id]/permit/page.tsx` (LiveWorkspace 직전 섹션) |

배치 결정: 신규 라우트 대신 **인허가 포털(permit) 페이지**에 "설계변경 리스크 사전예측"
섹션으로 결합. 설계변경 리스크는 인허가 검토 흐름과 가장 가까워 결합 우선 원칙 충족.
부지분석 주소·자동설계(연면적/층수/건폐율/용적률)는 `useProjectContextStore`에서 자동 프리필.

## 2. 표시·정직성

- **입력**: 주소(필수, `ProjectAddressInput`) + 선택 설계 파라미터(접이식 `<details>`:
  층수·연면적·건폐율·용적률·높이·주차대수·세대수, `NumberInput`) + `use_llm` 토글.
  입력된 파라미터만 `design_params`로 전송(빈값 제외). PNU는 store에서 보조.
- **요약**: high/warn/info 카운트 배지(의미색) + `total_predicted_impact_note` + 용도지역.
- **리스크 리스트**: `category`별 그룹(법규초과=rose·누락=amber·간섭정합=violet),
  severity 배지(high=rose/warn=amber/info=sky), item·current·limit·detail.
  각 카드에 **보완방안(remedy)**(accent 좌측 보더 강조) + `est_impact`(정성).
- **AI 통합전략**(`ai_remedy` 있을 때): priority_actions·savings_opportunity·expert_review_note.
- **정직성 배지**: `badges.note`("사전예측·확정아님·전문가검토필요·3D clash 범위 외") 항상 노출,
  `badges.data_basis`, `data_gaps`(부족·추정 데이터 목록), `sources` 출처 표기.
- **필터(선택)**: 전체/카테고리/심각도 칩 토글 — 키는 응답 값과 1:1.
- **상태 처리**: 로딩("예측 중...")·에러(401/403→로그인 안내)·`ok:false`(error 카드)·
  리스크 0건(녹색 안내). 미로그인 시 버튼 비활성+안내.

## 3. 검증

- `npx tsc --noEmit` → EXIT 0.
- `npx eslint`(신규 2파일 + permit/page.tsx) → EXIT 0.
- `git diff --cached`로 permit/page.tsx의 `apiClient` import 보존 확인(린터 되돌림 없음). 추가 2곳만.
- 토큰 사용: `--accent-soft/--accent-strong`(@propai/ui 토큰, 다크 #14b8a626/#2dd4bf 정의 확인),
  `--surface-*`·`--line`·`--radius-*`·`--shadow-lg`·`--text-*` + 의미색(rose/amber/violet/sky/emerald)
  의 토큰 일관 다크 스타일. 기존 무파괴.

## 4. 커밋

`23bd43d` feat(design-risk): D3 설계변경 사전예측 패널 — 누락·간섭·법규초과 경고+보완방안
(footer: Co-Authored-By: Claude Opus 4.8 (1M context)). push 안 함.

## 5. 백엔드 정합

- 엔드포인트 `POST /api/v1/design-risk/predict`, apiClient.post v1(`/design-risk/predict`).
- Req: `{address?, pnu?, project_id?, design_params?{floors,gfa,bcr,far,height_m,parking,units}, use_llm}`.
- 응답 스키마 1:1: `ok`/`address`/`zone_type`/`summary{high,warn,info,total_predicted_impact_note}`/
  `risks[{category,item,severity,current,limit?,detail,remedy,est_impact?}]`/`ai_remedy?`/
  `badges{note,data_basis}`/`limits_used`/`data_gaps`/`sources`. `ok:false`→`{error,badges}`.
- 카테고리(법규초과/누락/간섭정합)·severity(high/warn/info) 값이 프론트 배지/필터/그룹 키와 1:1.
