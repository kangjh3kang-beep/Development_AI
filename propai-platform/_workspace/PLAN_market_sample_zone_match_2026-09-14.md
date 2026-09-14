# 잴 수 있는 것을 **조건문**으로 말한다 — 참고 실거래 표본의 용도지역 일치를 기계 필드로

- 2026-09-14 · sid=ad208019 · 브랜치 `fix/market-sample-zone-match`
- 계기: 사용자 신고 — *"감정평가액이 기부채납 제외하고도 더 높은데 우리 시세분석이 시세를 못 잡는 것 아닌가"*
  (경기도 남양주시 화도읍 마석우리 265-1 외 8필지 · 감정 **15,390,680,000원/844평**)

## §0 조회 결과

★**볼트는 `ENODEV` 로 접근 불가** — 볼트를 참조했다고 말하지 않는다. 메모리(ext4)와 저장소 기록으로 대신했다.

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | ①**창 24개월 확대** — 만들고 라이브로 재고 **기각·삭제**(6개월 786,502 → 24개월 631,272, **−20%**) ②**「수도권 3배」 일괄** 기각 ③**`MARKET_MULTIPLIER_MAP` 값 변경** 기각(34개 지역 전 경로가 움직인다) ④**월별 중앙값을 시점계수로** 기각 — 전부 `PLAN_desk_appraisal_market_reality_2026-09-07.md` |
| **같은 클래스 선행 결함** | `land_dong_stats.py:285-291` 주석이 **직접** 적어 뒀다: *"혼입도 왜곡도 아니고 **모집단이 다른** 것이었는데 `scope_label` 이 '논현동' 뿐이라 사용자는 구분할 수 없다"*(논현동 1-1 공시지가 **0.54배** 사고) |
| **미결·부채** | 형제 계획서 §7 「미완」 셋: **B 방법2 승격** · **E 그밖의요인 1.2** · **F R-ONE 미구성 표면화** |
| **이전 판단의 근거** | PR #1019 — 그밖의요인 1.2 의 **값은 의도적으로 안 바꿨다**(형제 실측 1.448이나 **n=3**). 근거 없이 값을 바꾸는 것은 고치려는 그 죄의 반복 |

★**신선도 재확인**: 인용 좌표를 전부 `origin/main`(be9995a74)에서 다시 읽었다.
★그리고 **선행 기록 두 건이 이미 고쳐져 있었다** — 사용자 PDF 가 수정 전 판이다(아래 §1 참조).

## §1 전제 표 — 전부 **라이브 실측**(읽기 전용 · AI 해석 미요청)

| 전제 | 확인 방법 | 결과 |
|---|---|---|
| 두 문서가 같은 필지 묶음인가 | 면적 대조 | 감정 **921평 = 3,044.6㎡** ↔ PropAI 합산 **3,043.0㎡**(차 +1.6㎡) ⇒ **같다** |
| 같은 순면적에서 격차 | 844평(2,790.1㎡) 환산 | PropAI **9,538,820,884원** ↔ 감정 **15,390,680,000원** = **62.0%**(38% 낮음) |
| 역산 그밖의요인 | 감정단가 ÷ (공시×시점×형상) | **2.11**(우리 1.2 → **1.76배** 차이) |
| 라이브 `methods` 수 | `POST /land-price/desk-appraisal` | **4개**(PDF 는 1행) ⇒ **PDF 는 수정 전 판** |
| 라이브 시점수정 | 같은 응답 | **1.047**(PDF 1.0414) · `time_adjust_basis` = *"**전국 범위** … 요청 지역 경기의 시계열이 없어 전국 값을 적용"* |
| PDF 어댑터가 그 강등을 읽나 | `appraisal_adapter.py:190` | **읽는다** ⇒ 「R-ONE 실데이터」 오표기는 **이미 고쳐졌다**(라이브 결함 아님) |
| PDF 어댑터가 참고단가를 싣나 | `_method_basis` | **싣는다**(`[참고 …원/㎡ — …]`) ⇒ 이것도 **이미 고쳐졌다** |
| 참고 실거래 값 | `land_market_stats` | **3,855,297원/㎡** · n=6 · layer `dong_jimok` |
| ★그 표본의 용도지역 | `land_use_mix` | **제1종일반주거 83.3% · 계획관리 16.7%** |
| ★대상 용도지역 | `subject.zone_type` | **일반상업지역** |
| ★★**일치율** | 위 둘의 대조 | **0.0%** — ***완전히 다른 시장*** |
| ★그 0% 가 기계 필드로 있나 | 응답 전수(리프 168) | **0건** — 산문에만, 그것도 **조건문**: *"…**섞여 있으면** 단가가 크게 다를 수 있습니다"* |
| 왜 조건문인가 | `stats_note` 시그니처 | `(stats, window_months)` — **대상 용도지역 인자가 없다.** 원리적으로 실측을 말할 수 없다 |

## §2 결함 — **잴 수 있는 것을 조건문으로 말한다**

시스템은 `subject.zone_type`(일반상업지역)과 `land_use_mix`(1종주거 83.3%…)를 **둘 다 구조화**로 갖고 있다.
그런데 둘을 **대조하지 않는다.** 그래서:

- 사용자는 «참고 3,855,297원/㎡» 를 **같은 시장의 대조값**으로 읽는다.
- 실제로는 **대상 용도지역이 표본에 0%** 다.
- 산문은 *"섞여 있으면"* 이라 **가정법**으로 말해, 「확인 못 했다」와 「확인했고 0% 다」를 **같은 문장으로 덮는다.**

★이 모듈의 주석이 **자기 언어로 이미 경고**하고 있다: *"모집단이 다른 것인데 사용자는 구분할 수 없다."*
설계 의도는 *"막지 않고 **밝힌다**"* 인데, **밝힘이 조건문이면 밝힌 것이 아니다.**

## §3 변경

1. `land_dong_stats.zone_match(stats, target_land_use)` **신설**(순수 함수) —
   `{"target_land_use", "share_pct", "verdict"}`. 대상이 없거나 `land_use_mix` 가 없으면 **`None`(못 쟀다)**.
   ★**3상태**: `None`=못 쟀다 / `share_pct=0.0`=**쟀고 0%** / `>0`=일부·전부.
2. `stats_note(..., *, target_land_use=None)` — 주면 **조건문 대신 실측 문장**. 안 주면 **현행 그대로**(무회귀).
3. `desk_appraisal_service`:
   - `land_market_stats` 에 `target_land_use` · `target_land_use_share_pct` 실기
   - `_methods(...)` 의 `reference_note` 에 실측 문장
   - ★인자는 **뒤에** 추가(저장소 §33 — 앞에 넣으면 위치인자 호출부가 조용히 밀린다)

**회귀가 아닌 근거**: 기존 키·값 **불변**, 추가만. `target_land_use` 미전달 시 문구까지 **바이트 동일**.

## §4 ★검증하지 못한 것 — **이 PR 이 격차를 닫지 않는다**

- ***이 변경은 채택가를 올리지 않는다.*** 62% → 62% 다. 고치는 것은 **「시스템이 아는 것을 말하지 않는 것」**이다.
- 격차의 나머지는 **재지 않았다**:
  · 그밖의요인 **1.2 vs 역산 2.11** — 형제가 **n=3** 으로 값 변경을 기각했고 나도 **바꾸지 않는다**
  · **일단지 평가 부재** — 8필지 단가가 **539,473 ~ 4,368,493(8.1배)** 인데 단순 합산한다. 감정 실무는 일단지
  · **인허가 프리미엄 축 없음** — 대상은 «공동주택 **인허가** 부지» 인데 우리 모델에 그 축이 없다
  · **형상 0.9** — 통합 부지인데 개별 필지 형상으로 감액
- 용도지역 층(`dong_zone`)이 **표본 하한에 막혀** 안 서는 문제는 **이 PR 범위 밖**(창 확대는 이미 기각됨).
- 화면 렌더 **미측정**.

## §5 잠금

★★**2026-09-14 정정(독립 리뷰 M3)**: 이 표는 한때 **락 이름 5개를 선언하고 그중 4개가
실재하지 않았다**(`test_zone_match_three_states` · `test_note_states_the_measured_share_not_a_conditional`
· `test_note_unchanged_when_target_absent` · `test_reference_note_carries_the_mismatch`).
계획을 쓸 때의 이름이 구현하면서 바뀌었고 **아무도 대조하지 않았다** — 그리고 그 사이
§6 에서 추가한 락 4개는 이 표에 **한 줄도 없었다**. 저장소 기록 그대로다:
***순증이 순삭제를 덮는다*** · ***계획서가 선언한 락이 실재하는지는 PR 에서 확인한다(§C).***
⇒ 아래 표는 **AST 로 파생**해 다시 적었고, 이제 **기계가 검사한다**:
`test_plan_section5_lock_names_exist` — 이 표의 백틱 `test_*` 이름이 실제 테스트 모듈에 없으면 **빨강**.

파일: `apps/api/tests/test_market_sample_zone_match.py` (락 15 + 부채 xfail 1)

| 락 | 축 |
|---|---|
| `test_zone_match_separates_three_states` | `None`(못 쟀다) / `0.0`(쟀고 0%) / `>0` — **세 상태가 다른 값** |
| `test_zone_match_uses_the_same_normalisation_as_the_producer` | 생산자 `_mix_of` 와 **같은 `_norm`** 으로 비교한다 |
| `test_note_says_the_measured_share_instead_of_a_conditional` | 대상 주면 **「섞여 있으면」이 사라지고** 실측 수치가 나온다 |
| `test_note_is_unchanged_when_target_is_unknown` | 대상 없으면 **바이트 동일**(무회귀) |
| `test_two_populations_produce_different_notes` | 일치 0% ↔ 일치 100% 가 **다른 문구** |
| `test_reference_note_and_machine_field_carry_the_mismatch` | `methods[1]` 이 참고값과 함께 실측을 싣는다(**소비처까지**) |
| `test_zone_match_clause_covers_all_three_branches` | 세 갈래 전수 · **거짓 금지를 양방향**으로 |
| `test_call_sites_actually_pass_the_target_zone` | 호출부를 **AST 로 파생** · 키워드가 아니라 **값 표현식**(리터럴 정확 일치) |
| `test_partial_branch_of_the_note_carries_the_measured_share` | 가운데 갈래도 **수치+건수 인접** |
| `test_response_keys_are_a_contract` | 출력 키 이름이 계약 — 바뀌면 소비처가 **조용히 `None`** |
| `test_machine_field_describes_the_very_stats_it_is_shown_beside` | ★H2 — 일치율이 **`land_market_stats` 바로 그 통계**를 잰다(동일성) |
| `test_unmeasurable_never_collapses_into_measured_zero` | ★H3 — 공백만 대상 · 센티넬 대상 · 전부 미표기 · 섞인 미표기 |
| `test_absence_is_counted_not_inferred_from_a_rounded_percentage` | ★M2 — `none` 은 **센 결과가 0**일 때만(반올림 바닥 1/20001) |
| `test_match_requires_every_known_parcel_not_a_rounded_percentage` | ★L2/L1 — `match` 는 **건수 동일성** · `share_pct` 타입을 **세 모집단**에서 |
| `test_producer_and_consumer_share_one_sentinel` | ★생산자를 태운다 — `rows` → `_mix_of` → `zone_match` 두 층 |
| `test_debt_machine_zone_match_field_has_no_consumer_yet` | **`xfail(strict=True)` 부채** — 기계 필드 소비처 0. 배선하면 XPASS 로 실패 |
| `test_plan_section5_lock_names_exist` | ★**이 표 자신** — 선언한 이름이 실재하지 않으면 빨강 |

★**공허 방지**: 각 락은 **대조군을 먼저** 단언한다(조회기 생존 · 픽스처가 실제로 두 값을 다르게 낸다).

## §6 실행 결과 — **계획서에 없던 것 셋**

### ★6-1 배선이 안 잠겨 있었다(기계 변이가 짚음)

내 락이 `_assemble_methods` 를 **직접 호출**해서 **호출부를 한 번도 안 태웠다.**
`:814`·`:837` 의 `target_land_use=...` **줄삭제가 SURVIVED**.
⇒ AST 로 **호출부**를 파생해 잠갔다. 저장소 기록 그대로: ***「존재를 잠그면 행위는 안 잠긴다」***.

### ★★6-2 그리고 **「넘기는가」 는 「무엇을 넘기는가」가 아니었다**

호출부 락을 넣었더니 **줄삭제는 CAUGHT** 인데 **문자열변경은 여전히 SURVIVED**:

    target_land_use=str((subject or {}).get("zone_type") or "")
                                            ^^^^^^^^^^^ 이것만 바꾸면 값이 **항상 비고**
                                                        기능이 통째로 꺼지는데 키워드는 그대로다

⇒ `ast.get_source_segment` 로 **값 표현식**을 뽑아 `zone_type`·`subject` 를 단언 → CAUGHT.

### ★★★6-3 내 단언이 **다른 이유로** 만족되고 있었다(같은 파일에서 **세 번**)

    처음: assert "83.3%" in note          ← 같은 노트의 **구성 나열**(`:398`)이 이미 싣는다
    거울상: assert "같은 용도지역 표본입니다" in note  ← 수치를 지워도 통과

⇒ **수치와 판정어의 인접**을 지문으로 삼았다: `0.0%**(0건)` · `83.3%** 뿐입니다` ·
  `100%** 입니다 — 같은 용도지역 표본`. 세 갈래 전부 CAUGHT.
★자문: ***「이 단언이 참인 이유가, 내가 의도한 그 이유인가?」***

### ★6-4 「문구」가 아니라 「거짓」을 잠갔다

`if zm["verdict"] == "match":` 한 줄을 지우면 그 `return` 이 **0% 블록 안의 죽은 코드**가 되고
100% 일치가 *"…100% **뿐입니다 — 나머지는 다른 용도지역입니다**"* 로 떨어진다.
***100% 인데 「나머지는」은 거짓이다.*** 수치만 단언하면 통과한다 ⇒ **참·거짓**을 양방향으로 단언.

## §7 변이 결과

| 판 | 결과 |
|---|---|
| 손 변이(내가 고른 6종) | **6/6 CAUGHT** |
| 기계 1차 | `generated=58 judged=48 caught=40 **survived=16**` |
| 기계 2차(배선·분기 닫은 뒤) | `caught=? **survived=8**` |
| **기계 3차(최종)** | `generated=58 judged=48 **caught=43 survived=5** undecided=10` |

★**남은 생존 5건은 전부 「순수 산문」**이다(수치도 판정어도 아닌 설명 부분).
  저장소 규율대로 **잠그지 않고 사유를 코드에 적었다** — *"산문까지 단언하면 다듬을 때마다 깨진다."*
★판정 불가 10건은 전부 **변이가 구문을 깬 것**(여러 줄 f-string·dict 리터럴). **분모가 그만큼 작다.**

## §8 회귀

신규 락 **10 passed** · `test_land_dong_stats` 포함 **19 passed** · `ruff` All checks passed ·
기존 회귀 **이름 집합 동일**(기준선 4 failed/35 passed ↔ 브랜치 동일 · 그 4건은 로컬
`prometheus_client` 미설치로 **선재** — `origin/main` 워크트리에서 대조군으로 확인).
