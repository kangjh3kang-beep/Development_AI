# 102 — 환경분석 계절 버그 수정 + 조례 병행검토

## 변경 파일
- `apps/web/components/environment/EnvironmentAnalysisPanel.tsx` (+134)
- `apps/web/components/environment/types.ts` (+11)
- `apps/api/app/services/environment/environment_service.py` (+25)
- `apps/api/routers/environment.py` — 변경 없음(season 이미 위임 통과, 수정 불필요)
- `apps/web/components/environment/EnvironmentSummaryCard.tsx` — 변경 없음(항상 `season:"winter"` 요청 → "동지" 라벨 정확, `sunlight_hours_winter` 폴백 키 유지로 정상 동작. 최소 diff 원칙)

## 수정 1: 계절 변경 자동 refetch (주원인)
- `useEffect([season, res, busy, run])` 추가. `res` 존재 + `!busy` + `lastSeasonRef.current !== season`일 때만 `run()` 자동 호출.
  - 첫 분석 전(res=null) 자동실행 금지.
  - `lastSeasonRef`(useRef)에 `run()` 진입 시 현재 season 기록 → 동일 계절 중복/무한루프 차단.
  - `run`은 useCallback(deps에 season 포함)이라 최신 season 반영.
- 계절 버튼 onClick은 기존대로 `setSeason`만(useEffect가 트리거 담당).
- import: `useEffect, useRef` 추가(린터 import 트랩 git diff 확인 — 의도한 1줄만 변경).

## 수정 2: 계절 라벨·키 일반화 (라벨버그, 하위호환)
### 백엔드 (`environment_service.py`)
- `SEASON_LABELS` 맵 추가(winter→동지, summer→하지, equinox→춘추분).
- `_compute_solar`: `season_key`(미상→winter 폴백)·`season_label` 도출. summary "동지" 하드코딩 → `season_label`.
- 출력 키 추가(계절중립): `season`(에코), `season_label`, `sunlight_hours`, `max_altitude_deg`.
- **하위호환**: 기존 `sunlight_hours_winter` 키 유지(동일 값) → 구버전 프론트(SummaryCard 등) 회귀 0.
- `_solar_grade`/GRADE_META: 등급 임계(4h/2h)는 동지=최악조건 기준 유지, 주석만 일반화(표기는 선택 계절). span은 9~15시 공통.
### 프론트
- `types.ts`: `EnvironmentSolar`에 `season?/season_label?/sunlight_hours?/max_altitude_deg?` 추가, `sunlight_hours_winter` optional+@deprecated.
- `EnvironmentAnalysisPanel.tsx`: `solarSeasonLabel = solar.season_label ?? SEASON_LABEL[solar.season ?? season]`, `solarSunlightHours = solar.sunlight_hours ?? solar.sunlight_hours_winter`. 라벨 "동지 일조시간" → `{solarSeasonLabel} 일조시간`.
- 결과: 하지 선택→자동 재요청 시 "하지 일조시간 N h", summary "하지(6/21) … 태양 최대고도 X°"로 동지와 다르게 표기.

## 수정 3: 조례 병행검토
- 호출: `POST /regulation/analyze`, body `{ address, pnu, use_llm: false }`.
  - `use_llm` 파라미터명 확인(RegulationAnalyzeRequest 스키마, 과제1에서 추가됨). use_llm=false → 비용/402게이트 없이 사실 계층만(`ai:null`).
  - 환경분석 성공(res.ok) 시 동반 1회만 호출(과도 자동호출 방지). address 없으면 미호출.
- 표시 항목(응답 `limits.bcr/far` = `{legal, ordinance, effective, unit}`):
  - 건폐율(법정/조례)·용적률(법정/조례) 2카드.
  - "조례 확인 필요" 배지: 조례 한도가 법정과 다를 때(ordinance != legal) 표시.
  - `hierarchy` 중 `level==="지자체 조례"` items(도시계획 조례·건축 조례) 리스트.
  - 병행 확인 안내 문구.
- 실패/무자료(limits 없음): 기존 약식 안내 유지("지자체 조례·완화규정 별도 확인") — 무목업.
- 신규 컴포넌트 `OrdinanceSection`(파일 내 로컬, 단일용도). state `ordinance` + `setOrdinance`.

## 검증
- 백엔드: `python3 -m py_compile app/services/environment/environment_service.py routers/environment.py` → PY_COMPILE_OK
- 프론트: `npx tsc --noEmit` → EXIT 0
- git diff import 보존(panel: React 훅 1줄만 변경, 그 외 import 무변동). 신규 의존성 0.

## 미진사항
- 라이브 검증(실제 하지/동지 수치 차이) 미수행 — push/배포 금지 제약. 정적 타입/컴파일만 확인.
- `_solar_grade` 임계는 동지 기준 절대값 유지(하지 선택 시 일조시간↑로 등급이 후하게 나올 수 있음 — 설계상 "선택 계절 기준 표기"). 등급을 계절별 기준으로 분리할지는 기획 판단 필요.
- 다른 executor 담당 4개 파일(site-analysis/page.tsx·LandIntelligencePanel·ModulePlaceholder·DigitalTwinScene) 미접촉.
