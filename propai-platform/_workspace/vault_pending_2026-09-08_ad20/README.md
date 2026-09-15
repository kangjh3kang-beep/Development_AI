# 볼트 대기열 — D: 접근 불가로 옵시디언에 못 쓴 기록 (2026-09-08 · sid=ad208019)

## 왜 여기 있나

옵시디언 Vault(`/mnt/d/옵시디언기록/…`)에 쓰려 했으나 **D: 전체가 접근 불가**다.
전역 규칙이 *"접근 불가 시 다른 위치 대체 저장 금지, 실패 경로만 보고"* 라
**볼트 문서를 임의 위치에 흩뿌리지 않고** 여기 한 곳에 모아 둔다.
D: 가 돌아오면 이 디렉토리 내용을 볼트로 옮기고 이 디렉토리를 지운다.

## 실측 (2026-09-08 18:2x · 관측)

| 조회 | 결과 |
|---|---|
| `ls "/mnt/d/옵시디언기록/나의-모든-기록-최적화본"` | `No such device` |
| `ls "/mnt/d/옵시디언기록/나의 모든 기록/AI_개발일지"` | `No such device` |
| `ls /mnt/d` (상위) | `No such device` |
| `stat -f /mnt/d` | `cannot read file system information` |
| **대조군** `ls /mnt/c` | **정상**(`$Recycle.Bin` 외 나열됨) |
| `mount \| grep /mnt/d` | **마운트 항목은 살아 있다** — `D: on /mnt/d type 9p (…trans=fd…)` |

★**마운트는 붙어 있는데 9p 전송만 죽었다.** `ls` 실패는 증상이지 원인이 아니다
(이 함정은 2026-09-06 에 한 번 기록됐다 — «살아 있는 마운트도 죽어 있을 수 있다»).
대조군 `/mnt/c` 가 통과하므로 **도구·경로·권한 문제가 아니다.**

## 처방 (사용자 판단 필요 — 내가 실행하지 않았다)

Windows 호스트에서 `wsl --shutdown` 후 재진입. **이 세션을 종료시키므로 실행하지 않았다.**
★D: 는 2026-09-05 이후 `Full Repair Needed` + 일부 파일 CRC 오류 이력이 있다.
`chkdsk /f D:` 는 길고 되돌리기 어려워 **사용자 결정 사항**으로 남겨 둔다.

## 대기 중인 문서

- `PR1021_review_R3_followup.md` — PR #1021 M1·M2·B2 봉합과 그 과정의 교훈
- `lesson_fixture_used_an_illegal_combination.md` — CI 실패 1건의 근본:
  픽스처가 **원래 불법인 조합**을 쓰고 있었다 · 「기본값 무해」 주석이 거짓이었다 ·
  로컬에서 못 재는 것을 「쟀다」고 말하지 않기 · **경고를 실패로 오독**한 판독 실수

## 재측정 이력 (라벨을 승계하지 않는다)

| 시각 | D: 상태 | 대조군 `/mnt/c` |
|---|---|---|
| 2026-09-08 18:2x | `No such device` | 정상 |
| 2026-09-08 18:5x | `No such device` (재측정) | 정상 |

## 이 기록의 다른 사본 (경로가 끊겨도 남는 곳)

- 세션 메모리: `feedback_scattered_validation_survives_being_switched_off.md`
- 공유 보드: `.git/coordination/BOARD.md` 의 2026-09-08 18:18 NOTE(sid=ad208019)
- PR #1021 본문
