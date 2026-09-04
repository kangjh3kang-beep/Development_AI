# 관리자 연결결산 — **"확인 못 함"이 "정합"으로** 읽힌다

- 작성: 2026-08-26 · 브랜치 `fix/reconcile-withheld-visibility`
- ★**`#832`(보류값 계약)에 의존**한다 — `withheld()`·`INSUFFICIENT_COVERAGE` 사용
- 계보: `#832` 커버리지 원장이 **미배선 부채로 선언한** `sales/admin/console.py`

## 0. 계획 게이트 §0 — 옵시디언 조회
`판정 보류|대사|reconcil|연결결산` 조회(대조군 517파일). **이 결함의 선행 기록 없음.**

## 1. 관측 — 라이브 admin 실측(2026-08-25T23:0xZ)

`GET /api/v1/sales/projection/accounting-rollup` · 현장 **13곳**

| | |
|---|---|
| `reconciliation.balanced` | **True 2 · None 11** |
| 롤업이 노출 | `reconcile_failed_count` **0** |
| 보류를 노출하는 키 | **없음**(`withheld\|unknown\|absent` 0건) |

**85%가 대사조차 못 한 상태**인데 관리자 화면은 **"정합 실패 0"** 으로 깨끗해 보였다.

★사유도 없다 — 각 현장 `reconciliation.note` 는 `balanced=True` 인 곳과 `None` 인 곳이
**동일한 정적 방법론 설명**이었다(대조군으로 확인).

## 2. ★소비처는 옳았다 — 결함은 그 위층

`views.py` 는 `if rec.get("balanced") is False:` 로 **명시 비교**하고 주석도
*"balanced=None(판정보류)은 실패가 아니므로 세지 않는다"* 라고 정확히 적어 뒀다.
**실패와 보류를 가른 것까지는 맞는데 보류를 버렸다.** *세지 않은 것*이 결함이다.

## 3. 처방 — 값은 바꾸지 않는다, **세지 않던 것을 센다**

1. 생산자: `balanced=None` 에 `balanced_absent = insufficient_coverage` + 사유 문구
2. 집계: `tally_reconciliation()` **순수 함수**로 세 갈래(failed/withheld/ok)
3. 롤업: `reconcile_withheld_count` 를 `reconcile_failed_count` **와 나란히** 노출
4. `note` 에 구분 명시 — *"'불일치 0'과 '확인 못 함 N'은 다른 사실"*

★기존 키·값·판정 로직 **불변**. 추가만 한다.

## 4. ★락을 두 번 만들었다 — 첫 판이 변이에 뚫렸다

첫 롤업 락은 `"reconcile_withheld_count" in src` 라는 **소스 문자열 검사**였다.
증가문을 `pass` 로 바꾸는 변이가 **생존**했다 — 변수 선언과 응답 키에 문자열이 남으니
**세는 일이 멈춰도 참**이었다.

→ 판정을 **순수 함수로 꺼내 행동으로** 잠갔다. 재변이 2종 CAUGHT
(축 혼입 `elif b is None` 무력화 · 롤업이 함수를 안 씀).

## 5. 검증

- 락 **7건** — 행동 3(세 갈래 계수·축 비혼입·**라이브 형상 13곳=보류11+정합2**) ·
  배선 1 · 특이도 3
- 회귀: 전체 스위트 **기준선 69 / 현재 69, 집합 동일 → 0**
  (비교기에 `len>50` 생존 단언 — 파서가 죽으면 0/0 이 "회귀 0"으로 읽힌다)

## 6. 검증 못한 것 (정직)

- **화면 배너가 이 수를 실제로 그리는지는 미확인.** 이 PR 은 **API 까지**다.
  프론트가 `reconcile_withheld_count` 를 소비하지 않으면 숫자는 응답에만 있다
  (`reconcile_failed_count` 도 한때 *"프론트 소비 0인 dead output"* 이었던 전례가 있다).
- 라이브 표본은 **admin 테넌트 13곳** 하나다. 다른 테넌트의 보류 비율은 미측정.
- `balanced=False` 갈래는 **라이브에서 한 건도 못 봤다**(13곳 중 0) — 단위테스트로만 확인.
