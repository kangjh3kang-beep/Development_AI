# [배포요청 → 통합자] 통합 보고서 생성엔진

**브랜치:** `feat/unified-report-engine` (커밋 `573d9979`, origin 푸시됨)
**분기점:** origin/main `31212cc9` · **현 origin/main:** `3d2f1800`(#171 terrain) — **충돌 없음(클린 머지)**
**작성:** 2026-07-03 · 요청자 세션: feat-tmp(45b9613a)

## 한 줄 요약
프로젝트 통합 보고서를 **PDF·PPTX·DOCX** 한 엔드포인트에서 생성하는 통합엔진 신설 + `rates` 404 실버그 수정 + 시니어 프롬프트 evidence 계약(전역).

## 1) 머지
- PR: `https://github.com/kangjh3kang-beep/Development_AI/pull/new/feat/unified-report-engine`
- **squash·일반 머지 무관**(내 파일과 origin/main 신규분 교집합 0 — `terrain_service.py`만 겹치지 않음).
- 변경: 백엔드 신규 `apps/api/app/services/report/render/`(8모듈)+`adapters` / 수정 `routers/reports.py`·`main.py`(rates 1줄)·`pyproject.toml`(python-pptx)·`base_interpreter.py`(GROUNDING_RULE v3) / 프론트 신규 `ReportDownloadMenu.tsx`+`report/page.tsx` / 테스트 2 / 근거 `_workspace/report_engine/`.

## 2) 배포
### 백엔드 (168.110.125.89 · 블루그린)
```
ssh -i ~/.oci.key <user>@168.110.125.89 '~/deploy.sh origin/main'
```
- ★**python-pptx 설치 필수**: `pyproject.toml`·`requirements.txt` 모두 `python-pptx==1.0.2`(oracle 포함) 선언됨. 배포 빌드가 의존성 재설치를 하는지 확인 — 미설치 시 PPTX 요청이 500(PDF 폴백은 pdf 포맷에만 적용). dev venv엔 원래 미설치였음(RISK#2, 이번에 pyproject 선언으로 해소).
- reportlab·python-docx·openpyxl은 기존 설치됨.

### 프론트 (158.179.174.207 A1 · safe-deploy web · 수동)
- `ReportDownloadMenu.tsx`+`report/page.tsx` 변경 → A1 재빌드 필요. sw 버전으로 반영 확인.

## 3) 배포 후 라이브검증 (★남은 유일 게이트)
로그인(admin@4t8t.net) 상태로 `agent-browser --session propai` 또는 UI:
1. 프로젝트 → REPORT 페이지 → **보고서 다운로드** 카드에 PDF/PPT/Word 세그먼트 노출 확인.
2. 각 포맷 클릭 → 실파일 다운로드(3개). **python `json.load`/파일 시그니처 파싱이 권위**(grep 금지 — ㎡/한글 오탐).
   - PDF `%PDF` · PPTX/DOCX `PK\x03\x04`. 내용: feasibility 통합면적·정직표기(빈값 "—")·XML 안전.
3. **rates 404 수정 확인**: BIM 원가 대시보드 진입 → `/api/v1/rates/current` **200**(과거 404).
- 무인증 curl은 `/reports/generate` 403(인증필요) — regulation/building-compliance로 대체 확인 가능하나 3포맷은 로그인 UI가 권위.

## 4) 게이트(이미 통과 — 참고)
pytest 26 passed(회귀0: base_interpreter·market PDF·cost) · ruff clean(내 파일) · eslint clean · 3포맷 스모크+어댑터 e2e(pipeline_result→11섹션→PDF/PPTX/DOCX) 라이브검증.

## 5) 배포 후 통지 부탁
머지·배포 완료를 보드 note로 남겨주시면(또는 origin/main에 render 패키지 등장 시 워처 자동감지), 요청 세션이 라이브검증 후 로드맵(persona 4종 통합→bank 서버PDF→…)을 이어갑니다.
