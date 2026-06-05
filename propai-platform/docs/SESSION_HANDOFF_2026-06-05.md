# 세션 핸드오프 — 2026-06-05

다음 세션(클로드)에서 이어가기 위한 기준점. (인프라/스케일 작업은 제미나이가 별도 진행)

## 1. OMC(oh-my-claudecode) 글로벌 설치 완료
- **설치**: `npm i -g oh-my-claude-sisyphus@latest`(전역 prefix `~/.npm-global`, PATH 등록됨) + `omc setup --no-plugin`.
- **연동(~/.claude)**: 에이전트 19 + 스킬 37 동기화(전체 63=OMC+기존 PropAI), 훅·HUD 상태줄·전역 `~/.claude/CLAUDE.md`(OMC) 추가 → 모든 Claude Code 세션에 OMC 적용.
- **보존**: 메모리·PropAI 프로젝트 스킬·프로젝트 CLAUDE.md 유지.
- **이용법**:
  - 스킬: `autopilot`, `ultrawork`, `team`, `deep-dive`, `ultraqa`, `ralph`, `ui-ux-pro-max`, `canvas-design` 등 (새 세션부터).
  - CLI: `omc launch` / `omc info` / `omc doctor`(진단) / `omc update`(갱신).
  - 인터랙티브 설정: `/oh-my-claudecode:omc-setup`.
  - 플러그인 방식(대안): Claude Code에서 `/plugin marketplace add https://github.com/Yeachan-Heo/oh-my-claudecode` → `/plugin install oh-my-claudecode`.
  - ★적용 완전 반영을 위해 Claude Code 재시작 권장.
- **주의**: settings.json 훅·statusLine·전역 CLAUDE.md가 변경됨(전 세션 영향). 이상 시 `omc doctor`.

## 2. 이번 세션 완료한 플랫폼 고도화(모두 배포·검증)
1. 분석 원장(블록체인-inspired 해시체인) + 용량 쿼터 + 관리자 감사로그. 프론트 write-through·원장기반 복원·무결성 배지.
2. AI 해석 온디맨드 + 캐시(interpretation_cache) + 입력매핑 정교화(`_normalize_for_interpreter`) + 프리페치 + 타임아웃/재시도.
3. 보고서 실 PDF 일원화(`/api/v2/pipeline/report/pdf`, `/api/v1/reports/generate`) + **AI 해석 PDF 포함**.
4. 검증/할루시네이션 배지 전 모듈(통합보고서·예상시세[avm]·ESG·투자ROI·마켓·인허가).
5. CAD/BIM 별도 메뉴 분리(설계 스튜디오) + BIM-적산 5D 부위별 물량(QtoBreakdown) + 설계 직관화.
6. 인허가 페이지 정리(중복/로그인오류 제거·일조 결합), 1102 완화(무거운 패널 ssr:false).
7. 금액 쉼표 전수(NumberInput), 탭 SVG 아이콘·줄바꿈·compact 중복제거, 관리자 메뉴 복구.
8. R-ONE 부동산통계(지가변동률 실시간·cap rate·전월세전환율), 틸코 등기(RSA/AES), 토지조서 UX, 인터넷등기소 점검 분류.

## 3. 다음 세션 고도화 계획(우선순위)
1. **예상시세 보고서 PDF에 AI 해석 포함**(desk_appraisal_pdf + avm) — 통합보고서와 동일 패턴. ← 바로 다음.
2. **통합보고서를 원장 단일출처로 직접 렌더**(현재 컨텍스트 경유 간접).
3. esg/tax 인터프리터 입력 매핑 추가 정교화.
4. 남은 화면 이모지 → SVG 전수.
5. (인프라/제미나이) Oracle Ampere A1 업그레이드 → 멀티워커 + arq 큐(장시간 작업 비동기) + Redis 캐시 + 프런트 런타임 이전(Vercel 또는 Oracle Node).

## 4. 운영 원칙(필수)
- 백엔드 변경 → Oracle SSH 무중단 배포(`~/deploy.sh`, blue-green) 필수. 프런트 → Cloudflare 자동(main 푸시).
- 한 번에 하나 모듈 완벽 구현. 커밋 footer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- 상세 메모리: `project_session_handoff`, `project_analysis_ledger`, `project_design_bim_studio`, `project_scaling_infra`, `project_oracle_deploy`.
