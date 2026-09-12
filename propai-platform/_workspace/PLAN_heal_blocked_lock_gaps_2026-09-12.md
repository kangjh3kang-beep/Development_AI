# 독립 리뷰 REVISE 반영 — 내 「35/35 CAUGHT」 밖에서 6건이 생존했다

작성: development-ai-a4 · sid=7af9eaa2 · 2026-09-12 · 후속 PR(원 PR #1025 머지 069bc340e2f1)

## 0. 옵시디언 조회

볼트 접근 OK(대조군 C: OK). **이 주제의 직접 기록 있음** — 오늘 내가 쓴
`errors/2026-09-12_권한을_받은_것과_지금_눌러도_되는_것은_다른_축이다.md` 와
`errors/2026-09-10_결론은_맞고_인과는_절반이었다.md`.
★그리고 **그 교훈이 이번에 나에게 그대로 돌아왔다** — «N/N CAUGHT 는 내가 고른 N개».

## 1. 전제 표 (측정 방법 · 실제 값)

| # | 전제 | 방법 | 결과 |
|---|---|---|---|
| 1 | 리뷰어 변이 6건이 정말 생존하는가 | 그쪽 명령 그대로 재현 | **M1 SURVIVED**(리뷰어 실측) → 반영 후 **M1~M6 전부 CAUGHT** |
| 2 | 스텁이 `params` 를 버리는가 | 원문 | `execute(self, stmt, params=None)` 가 받고 **한 번도 안 봄** ✔ |
| 3 | 행이 SELECT 목록과 무관한가 | 원문 | 늘 같은 튜플 반환 ✔ |
| 4 | `created_at` 단언이 공허한가 | ORDER BY 절 확인 | **ORDER BY 에도 있음** ⇒ SELECT 에서 지워도 참 ✔ |
| 5 | 저장소가 두 사유를 의도적으로 가르는가 | `healing_rules.py:73-88` 원문 | `CAP_BLOCK_REASONS`(기록) ↔ `ESCALATION_COUNT_REASONS`(판정 · trigger_cap 하나) **명시** ✔ |
| 6 | 새 부채 파일이 vitest 에 수집되는가 | `vitest.config.ts:37` | `include: ["**/*.test.ts", ...]` **파생형** ⇒ 수집됨(형제 14개) |

## 2. 변경 내용

- 스텁이 **`params` 를 기록**하고 테스트가 `at`·`limit`·`offset`·`since` **bind 값**을 단언
- SELECT **순서까지** 단언(`payload` 가 `created_at` 보다 앞) — 뒤집히면 실 DB 에서 **500**
- `ORDER BY … DESC` 단언 · `limit`/`offset` 이 **서로 다른 값**으로 도달하는지
- `blocked_by_reason` 추가 — **합산이 두 상태를 뭉개지 않게**(MAJOR-2)
- 소비처 부채를 **`it.todo` 로 초록 안에** 노출(MAJOR-3)

## 3. ★검증하지 못한 것

- **vitest 를 직접 돌리지 못했다** — 새 워크트리에 `node_modules` 가 없다.
  수집은 `include` **패턴에서 파생**해 확인했을 뿐이고, **실행으로 확인한 것이 아니다.**
- 실 Postgres 의 `blocked_by_reason` 질의(`payload->>'reason'` + `GROUP BY`)는 **스텁으로만** 태웠다.
  ★리뷰어가 라이브에서 `payload->>` 자체는 동작함을 확인했으나(`action_type` 필터 200·total 47),
  **`GROUP BY` 질의는 그 확인에 포함되지 않았다.**
- 리뷰어가 «형제 후보» 로 든 4종(`field_audit_observation` 등)은 **이번 범위 밖**이다(미측정).

## 4. 되돌리기

라우터 1파일 + 테스트 1파일 + 부채 1파일. `git revert` 1회. 추가 필드뿐이라 소비처 파손 없음.

## 5. 잠금

`tests/test_heal_blocked_observable.py` **9 → 13건**.
★원 PR 계획서가 «락 6건» 이라 적었는데 실제는 **9건**이었다(리뷰어 MINOR-3 — 선언과 산출물 불일치).
이 계획서는 **실제 수를 적는다**: 13건.
★리뷰어 변이 **M1~M6 전부 CAUGHT**(그쪽 명령 그대로 재현).
