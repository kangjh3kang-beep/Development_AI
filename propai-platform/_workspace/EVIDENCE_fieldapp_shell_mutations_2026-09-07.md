# 변이 검증 증거 — 분양 현장앱 셸 리팩토링 (PR #1015)

적대 리뷰가 *「11/11 인지 8/8 인지 알 수 없고, `::VERDICT=` 산출물이 브랜치에 없어 **재현 불가**」*
라고 지적했다. 그래서 **판정 줄을 그대로** 남긴다. 손으로 고른 변이만이며(기계 변이는 별도),
각 실행은 도구가 **기준선 초록**과 **주입 성공**과 **원복 바이트 동일**을 강제한다.

```
mut1   ::VERDICT=CAUGHT   기준선 통과 15 건
mut2   ::VERDICT=CAUGHT   기준선 통과 15 건
mut3   ::VERDICT=CAUGHT   기준선 통과 15 건
mut4   ::VERDICT=CAUGHT   기준선 통과 27 건
mut5   ::VERDICT=CAUGHT   기준선 통과 27 건
mut6   ::VERDICT=CAUGHT   기준선 통과 27 건
mut7   ::VERDICT=CAUGHT   기준선 통과 27 건
mut8   ::VERDICT=CAUGHT   기준선 통과 27 건
mut9   ::VERDICT=CAUGHT   기준선 통과 33 건
mut10  ::VERDICT=CAUGHT   기준선 통과 33 건
mut11  ::VERDICT=CAUGHT   기준선 통과 33 건
r1     ::VERDICT=CAUGHT   기준선 통과 41 건
r2     ::VERDICT=CAUGHT   기준선 통과 41 건
r3     ::VERDICT=CAUGHT   기준선 통과 41 건
r4     ::VERDICT=CAUGHT   기준선 통과 41 건
r5     ::VERDICT=CAUGHT   기준선 통과 41 건
r6     ::VERDICT=SURVIVED 기준선 통과 41 건
r7     ::VERDICT=CAUGHT   기준선 통과 41 건
r8     ::VERDICT=CAUGHT   기준선 통과 41 건
```

## 판독

- **총 19회** · 최종 **전부 CAUGHT**.
- ★중간에 **SURVIVED 1건**(`r6`)이 났다 — M2 락이 `activeGroupTitle` 폴백이 아니라
  `groups[0]` 폴백으로도 만족됐다(활성 탭을 첫 그룹에 뒀기 때문). 락을 고쳐
  활성 탭을 첫 그룹 **밖**으로 옮긴 뒤 `r8` 에서 CAUGHT 를 확인했다.
  **그 SURVIVED 를 지우지 않고 남긴다** — 락을 추가한 것만으로는 그것이 무엇을 보는지 모른다는 증거다.
- `r1`·`r2`·`r3` 는 **적대 리뷰가 `::VERDICT=SURVIVED` 로 실증한 바로 그 변이**다.
  봉합 후 같은 변이가 CAUGHT 로 바뀌었다.

## 재현

```bash
cd propai-platform/apps/web
../../../scripts/mutate_manual.sh <파일> '<sed>' ./node_modules/.bin/vitest run components/sales-app/
```
