# 세션 인수인계 — 2026-06-13

## 배포 현황
| 대상 | 커밋 | 비고 |
|------|------|------|
| origin/main | `1cd931f` | |
| 백엔드 Micro(api.4t8t.net) | `e78969a` | 1cd931f는 프론트 전용(tokenHint), 백엔드 동일 |
| 프론트 A1(4t8t.net) | `1cd931f` | **sw v151** |
| 등기 provider | apick(운영) | |

## 이번 세션 완료(배포·라이브검증)
1. **건축HUB 주택·건축인허가 통합** — `HUB_PERMIT_API_KEY` 설정, `/api/v1/permit-cases?pnu=&kind=hs|arch` 라이브. **나대지 해소**(data.go.kr 계정1키 승인 전파 → 건축물대장 실데이터).
2. **등기 provider** — 에이픽 운영 설정(실데이터+AI권리분석). CODEF=데모토큰. 틸코=코드 완결(ENC:제거·Pin=고유번호·주소검색 RISUConfirmSimpleC 배선·Auth·host env)이나 모든 POST generic 500 = **틸코 키 미활성**.
3. **빌링** — 관리자 코인게이트 면제(unlimited), 과금 구독자 월포함한도 지연할당.
4. **적산자동화(BOQ 5공종 + 의정부424 마스터 3997항목)** — `/api/v1/boq-auto/*` 라이브. KB심화·CAD업로드 상호연동.
5. nearby-map 결과캐시, 수지 산정근거 주석, 분석이력 중복제거, 로드뷰 미니맵, 대시보드 카드 클릭이동.
6. **tokenHint 래퍼 중복 버그 수정**(22 .tsx) — JSX 빌드 깨짐 복구.

## 대기(사용자/외부)
- **틸코**: 고객센터에 ①API KEY 사용여부 ②IROS RealtyRegistry+RISUConfirmSimpleC 구독·활성 ③generic 500 원인 문의. (GetPublicKey만 동작·모든 POST 500 → 키/계정 미활성. 코드는 공식샘플 정확 일치)
- **CODEF**: 운영 cid/secret 발급(데모토큰)
- **적산 프론트 UI** 배선 점검(백엔드 boq-auto 라이브)

## 배포 교훈
- **프론트 변경 포함 배포 시 빌드/tsc 사전검증 필수**(이번 tokenHint 버그가 미검증으로 노출).
- 부팅 크래시: `from __future__ import annotations` + `@limiter.limit`(slowapi) 동시 → 어노테이션 해석 깨짐. 머지 전 스캔.
- worktree cherry-pick: `$(git rev-parse HEAD)` 함정(worktree HEAD로 평가) → 명시 해시. remove 후 cwd 사라짐 → cd 복구.
- 키 주입: `/api/v1/admin/secrets`(Fernet DB+os.environ 즉시반영). 시크릿값은 `docker exec printenv`로 안 보임=정상.

## 협업
- 다른 클로드: `feature/trust-infra-2026-06-11` + main 작업. 모니터링 워처 `~/.feature_watch.sh`(세션종료시 미실행). 흐름: 감지→리뷰(머지충돌·부팅위험·tsc·구문)→main 머지/cherry-pick 격리→배포→sw 엣지 검증.
