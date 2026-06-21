# 진행 기록 (실시간 공유) — 2026-06-21

> 전 과정·결과를 기록·저장하고 저장소(브랜치 `feature/deliberation-review` → origin `kangjh3kang-beep/Development_AI`)로 실시간 공유.
> 각 증분은 검증(테스트·INV-3·ruff) + **9.5 적대 게이트(HIGH 0)** 통과 후 커밋·푸시한다. 본 문서는 마일스톤마다 갱신.

## 1. 목표

설계사·도시계획 전문가의 실무 전과정을 "스킬"로 엔진(deliberation-review)에 심어 에이전트가 실무 결과물을 산출하게 함.
모든 결과물에 **분석근거+필요시 링크**를 기본 동반(설명가능성 기본화). 부동산개발·건축 관련 법규를 전수조사해 분석 시 확보.

## 2. 완료 증분 (커밋·푸시 완료)

### 시스템 1 — 인·허가/심의 스킬 (접근법 C: 선언적 프로세스 스펙 + 얇은 결정론 실행기)
| 증분 | 내용 | 게이트 | HEAD |
|---|---|---|---|
| PD1 | 프로세스 스펙 계약 + 로더(applicability·결정론 위상정렬) | HIGH 0 | `ae275e54` |
| PD2 | 실행기 + 심의 계측(비율 계측·등급밴드·음수가드) | 3회 수렴 | `8aacb9a7` |
| PD3 | 결과 영속 + alembic 0016 + 프로젝트DB·테넌트격리 | 3회 수렴 | `a596db2a` |
| PD4 | 엔진 라우트(process/run/project) | HIGH 0 | `bc9e6fc6` |
| PD6 | 자치법규(elis) 어댑터(LiveNetwork·graceful) | HIGH 0 | `4b7344db` |
| PD5 | 플랫폼 심의 SpecialistAgent(dispatch 자동 노출) | HIGH 0 | `1e5a9091` |

### 시스템 2 — 건축설계 라이프사이클 스킬 (시스템1 실행기 재사용)
| 증분 | 내용 | 게이트 | HEAD |
|---|---|---|---|
| DL1+DL2 | process-agnostic 일반화(ProcessSpec/run_process) + 6단계 설계 스펙·실행기·완결성 | HIGH 0 | `1a07f7ea` |
| DL3 | 설계 라우트 + process 공용테이블 spec_id 분리 | 2회 수렴 | `51a4f403` |

### 설명가능성 기본화 + 참조법규 확충
| 증분 | 내용 | 게이트 | HEAD |
|---|---|---|---|
| EX1 | 엔진 결과 기준에 근거(LegalRef)+링크(1차출처 URL) 기본 동반 | HIGH 0 | `a5975de6` |
| 전수조사 | 부동산개발·건축 법규 391개 유니버스(9 카테고리) + 갭/끊긴링크/고아 진단 | — | (docs/LEGAL_REFS_AUDIT_2026-06-21.md) |
| LAW1 | missing_high 25건 추가(집합건물법 등) + 끊긴링크(경관법) 복구, _REFS 26→51 | HIGH 0 | `717d093e` |
| LAW2 | missing_other 20건 추가(_REFS 51→71) + resolve_text 견고성 근본강화(substring→최장일치→접두 앵커) | 3회 수렴 | `7c8c4167` |

## 3. 진행 중

- (없음) — 다음 항목은 §7 잔여·다음 참고. 본 문서는 통합 실시간 진행 기록으로 마일스톤마다 갱신.

## 4. 핵심 성과 — 9.5 적대 게이트가 잡은 실버그(수렴 해소)

성장루프(구현→다렌즈 적대 게이트→수렴)가 다음 실결함을 사전 차단:
- PD2: 정량 단위 불일치(m²를 %와 비교해 정상건물 '미흡' 날조)·등급 truthiness·음수 면적 통과·정성 feature 도달성.
- PD3: 모델 metadata 미등록→테이블 DROP 위험·인덱스 드리프트→ix DROP 위험(데이터 소실).
- DL3: 비대칭 누출(permit 엔드포인트가 design run 노출)→store spec_id SSOT 양방향.
- LAW2: resolve_text 과대매칭(시행규칙→부모법, 합성 법령명→부모법 날조)→접두 앵커 근본수정.

## 5. 검증 상태

- 엔진 테스트: 548 passed(누적), INV-3(법정 수치 하드코딩 0)·static_scan·ruff clean, alembic 0016 가역.
- 플랫폼 심의 에이전트: 4 passed(엔진 venv 임포트).
- 참조법령 사전 _REFS: 71개(부동산개발·건축 핵심 법규 + 시행령/규칙 + 조례 + 기부채납·국유/공유재산).

## 6. 채택 표준

- 9.5 품질 게이트(모든 증분 HIGH 0 후 커밋). 수렴 루프로 미달 해소.
- 설명가능성 기본화: 모든 결과물에 근거(도출이유·법령·정량)+필요시 링크 기본 동반(미해소는 None 표면화·날조 금지).
- 결정 원칙: 모든 선택은 결과물 신뢰성·정확성·안전성+플랫폼 가치 방향.
- 데이터 동역학: 버전드 동적 SSOT(실시간 수집+시점 고정 스냅샷; 자치법규 Phase1·시장 예측-only Phase2).

## 7. 잔여·다음

- **EX2**: 플랫폼 BFF/`심의`·`설계` 에이전트 findings에 근거+링크 전파(롤아웃 범위=엔진+플랫폼).
- 참조법규: 정밀 조문화(law.go.kr 라이브 검증), orphan(국토계획법§77 건폐율·§84 안분) 배선, calc_engine INV-12 슬롯 정리.
- 시스템2 후속: 설계 SpecialistAgent(플랫폼), Phase2 생성형(매스/세대수 — design_gen 정합).
- 운영(사용자 승인·실값): DELIBERATION_ENGINE_URL 설정·LIVE_NETWORK 점등(자치법규 실소싱).

## 8. 공유 채널

- 코드/문서: 브랜치 `feature/deliberation-review` (origin `git@github.com:kangjh3kang-beep/Development_AI`). 각 증분 푸시 = 실시간 공유.
- 세션 상태/표준: 자동 메모리(MEMORY.md + 개별 메모리). 본 문서가 통합 진행 기록.
