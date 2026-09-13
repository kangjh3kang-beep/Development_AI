# 계획 — 추첨 엔트로피를 **다자화**한다 (Phase 1)

세션 `development-ai-a2` · `sid=79cfa3eb` · 2026-09-13
브랜치 `feat/draw-verifiable-rng`(이어서) · 선행: Phase 0 완료 · Phase 2(앵커링) 완료

## §0 옵시디언 조회 결과

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **없음** |
| 같은 클래스 선례 | **없음** — 「기여값·엔트로피·비콘」으로 조회한 4건은 전부 **무관**(결제·소스락·임계). 대조군 「추첨」 1건 생존 ⇒ **이 주제는 볼트에 전례가 0건** |
| 미결·부채 | Phase 0 이 남긴 것: **추첨 순번이 등록 순서**(xfail 로 표시 중) |
| 이전 판단의 근거 | Phase 0 이 정직하게 적은 한계: *"DB 를 직접 읽는 사람은 여전히 nonce 를 본다 — 이 모듈은 「운영자 무신뢰」가 아니다"* ⇒ **이 계획이 그 자리를 겨눈다** |

## §1 전제 표 — 전부 실측

| # | 전제 | 확인 방법 | **결과** |
|---|---|---|---|
| 1 | 지금 엔트로피가 서버 단독인가 | `seed_key` 호출부 전수 | ★**그렇다** — `seed_key(nonce, ann_id)` · `seed_key(nonce, group, candidate)`. 기여값이 **전부 서버가 아는 값**이다 |
| 2 | 공개 비콘이 이 환경에서 닿나 | 3곳 HTTP 실측 | `api.drand.sh` **200** · `drand.cloudflare.com` **200** · `beacon.nist.gov` **200** |
| 3 | 두 drand 엔드포인트가 **같은 값**을 주나 | 동시 조회 | ★**같다** — round `6461121` · signature 동일 ⇒ **교차검증 가능**(한 곳이 거짓말하면 갈린다) |
| 4 | 공약 저장소에 라운드를 담을 자리 | 스키마 확인 | **없다** — 컬럼 추가 필요 |
| 5 | 가스(앵커링) | 로컬 hardhat 실측 | `commitDraw` **93,573** · `revealDraw` **79,113** · `setOperator` **47,667** |
| 6 | ★cloudflare 가 왜 실패했나 | UA 별 HTTP 코드 | ★**기본 `Python-urllib` 를 403 으로 막는다** — UA 없음 **403** · UA 아무거나 **200** · `curl` **200**. ***「간헐 장애」로 적었던 것은 오진이었다*** |
| 7 | 두 운영자가 **같은 체인**인가 | `/info` 양쪽 | ★**같다** — `hash=8990e7a9…51b2ce` · `period=30` · `genesis=1595431050`(양쪽 동일) |
| 8 | 체인 해시를 URL 에 박으면 되나 | 양쪽 + 대조군 | `…/<해시>/public/latest` **200·200** · **없는 해시 → 500**(조용히 기본 체인으로 안 떨어진다) |
| 9 | 라운드 주기 30초가 맞나 | `/info` 의 `period` | ★**30** — 종전엔 코드 상수로만 적혀 있었고 **미측정**이었다 |

## §2 설계 — ★**비콘을 먼저, 테넌트 기여값은 그 다음**

내가 사용자에게 처음 제안한 순서는 「테넌트 기여값 → 비콘」이었다. **재 보니 순서가 틀렸다.**

### 왜 비콘이 먼저인가 — **2자 commit–reveal 은 「거부」로 깨진다**

테넌트 기여값을 쓰려면 ①테넌트가 먼저 공약 ②서버가 공약 ③테넌트가 공개 — 이 순서여야
둘 다 단독으로 못 정한다. 그런데 ***테넌트는 명부를 보고 마음에 안 들면 공개를 거부할 수 있다.***
- 거부하면 추첨이 **멈춘다**(가용성 인질)
- 타임아웃 후 서버 단독으로 진행하면 **그 순간 보장이 사라진다**
⇒ **2자 프로토콜에는 이 중단 공격이 내재**한다.

**공개 비콘은 그 문제가 없다.** 값이 **미래에 공개되고 누구도 보류할 수 없다**:
- 공약 시점에 **미래 라운드 번호**를 못 박는다(그 값은 아직 세상에 없다)
- 추첨 시점에 그 라운드를 가져온다 — **서버도 테넌트도 예측·조작 불가**
- 검증자가 **같은 라운드를 직접 조회**해 재현한다 ⇒ ***공개 검증 가능***

### Phase 1a — drand 비콘 (이번 작업)

1. `beacon.py` — 라운드 조회. **엔드포인트 복수**(한 곳이 죽어도 살고, **두 곳을 대조**해 갈리면 거부)
2. 공약 시 `beacon_round = 현재 + LEAD` 를 **저장**하고 **공개**한다
3. 추첨 시 그 라운드를 가져와 `seed_key(nonce, ref, beacon_randomness, …)` 에 섞는다
4. 라운드가 아직 안 나왔으면 **거부**하고 **언제 되는지** 말한다(조용히 진행 금지)
5. 비콘을 못 가져오면 **거부**(fail-closed). ★*「비콘을 쓴다」고 약속해 놓고 조용히 빼면
   그게 이 저장소가 반복해 데인 거짓 주장이다.*
6. 검증기가 **같은 라운드를 직접 조회**해 대조한다

### Phase 1b — 테넌트 기여값 (후속 · 선택)

비콘이 들어가면 **서버 단독 결정이 이미 불가능**하다. 테넌트 기여값은 그 위에
「테넌트도 참여했다」는 **절차적 정당성**을 더하는 것이고, **중단 공격 대가**가 붙는다.
⇒ 요구가 확인되면 그때. **이번 계획에 넣지 않는다.**

## §3 ★검증하지 못한 것

1. **라이브 추첨에서 비콘 지연이 얼마나 되는지 미측정** — drand 기본 체인은 라운드 주기가 있고,
   `LEAD` 를 크게 잡으면 **공약 후 그만큼 기다려야** 추첨할 수 있다. 운영 수용성은 사업 판단이다.
2. ~~drand 체인 해시 고정 미검증~~ → ★**해소했다**(전제 7·8). 해시를 실측해 URL 경로에 박았고
   (`beacon.CHAIN_HASH` · 검증기 `_CHAIN_HASH`), **없는 해시가 500 으로 거부**되는 것까지 대조군으로
   확인했다. **남은 미측정**: 그 체인이 앞으로도 유지되는지(체인이 은퇴하면 추첨이 **거부**된다 —
   fail-closed 의 대가이고, 그때 운영이 해시를 갱신해야 한다).
3. **서명 검증 미구현**(그대로) — drand 는 BLS 서명을 주지만 이번엔 **서로 다른 운영자 2곳 교차
   대조**로 갈음한다. ***암호학적 검증이 아니라 가용성 기반 대조다*** — 코드 독스트링에 적었다.
   **한 운영자가 두 엔드포인트를 모두 통제하면 뚫린다.**
4. **운영자가 「결과를 보고 미루는」 층은 못 막았다** — 라운드가 공개된 **뒤** 결과를 먼저 계산하고
   추첨을 미룰 수 있다. `committed_at`·`revealed_at` 으로 **보이게** 할 뿐 **막지는 못한다**.
5. **DB 통합 실행 미측정** — 새 컬럼(`beacon_round`)의 `ALTER TABLE` 은 CI 의 postgres 를 태우는
   테스트가 없다. 락은 전부 **순수 함수·AST·주입 fetcher** 축이다.
6. **라이브 운영 수용성 미측정** — 기본 `LEAD_ROUNDS=10` ≈ **5분** 대기. 사업 판단이 필요하다.
7. 네트워크가 막힌 배포 환경에서는 추첨이 **거부**된다(fail-closed 의 대가). 운영 판단 필요.

## §4 되돌리기

`beacon_round` 가 비어 있으면 **종전 경로 그대로**(비콘 없이) 동작하게 두지 **않는다** —
그러면 「쓴다고 해 놓고 안 쓰는」 조용한 경로가 생긴다. 되돌리려면 **공약 단계에서 라운드를
안 잡으면** 되고, 그때 검증기·화면이 **「비콘 미사용」이라고 말한다**(침묵 금지).

## §5 잠금 — ★**실재하는 이름과 개수**

`apps/api/tests/test_draw_beacon_contract.py` · **22건**(전부 주입 fetcher — 네트워크 0):

| 계획이 선언한 것 | 실제 락 이름 |
|---|---|
| 두 곳이 갈리면 거부 (+대조군) | `test_disagreeing_endpoints_are_refused` · `test_agreeing_endpoints_pass_control` |
| ★「2곳」이 아니라 **「운영자 2곳」** | `test_two_mirrors_of_one_operator_are_not_a_cross_check` · `test_operator_of_separates_the_two_operators` |
| 아직 안 나오면 거부 + **남은 초** | `test_future_round_is_refused_with_the_remaining_seconds` · `test_ready_round_passes_control` |
| 대기 ≠ 장애 (다른 예외·다른 상태코드) | `test_not_ready_is_a_distinct_exception_from_failure` · `test_draw_endpoints_split_not_ready_from_failure[×2]` |
| 비콘 실패 시 거부(조용히 진행 금지) | `test_unreachable_beacon_refuses_instead_of_dropping_the_contribution` |
| ★비콘이 **실제로 seed 를 바꾼다**(두 모집단) | `test_beacon_value_actually_changes_the_draw` · `test_no_beacon_and_beacon_give_different_seeds` |
| 공약 라운드는 **미래**여야 | `test_target_round_refuses_a_non_positive_lead` · `test_target_round_is_in_the_future_control` · `test_commit_refuses_a_past_round` |
| 검증기가 **같은 기여값**을 만든다 | `test_verifier_builds_the_same_beacon_contribution` |
| 체인 해시 핀(프로덕션 ↔ 검증기) | `test_chain_hash_is_pinned_and_matches_the_verifier` |
| ★UA 회귀 방지(403) | `test_http_request_carries_a_user_agent` |
| **두 추첨 경로가 같은 함수**를 탄다 | `test_both_draw_paths_go_through_seed_contributions[×2]` |
| 라운드 없는 공약 불가 · 공개 시각 기록 | `test_commit_cannot_be_made_without_a_round` · `test_reveal_records_the_reveal_time` |

★**개명이 곧 잠금이었다**: `reveal_nonce` → `reveal_commitment` 로 바꾸자 기존 락 **5건이 빨개졌다**.
  2-튜플 뒤에 필드를 덧붙였으면 옛 호출부가 **조용히** 옛 모양으로 언팩해 비콘을 안 쓰는 경로가
  초록으로 남았을 것이다. ★그 과정에서 **`raising=False` 스텁 1건만 안 빨개졌다**
  (`test_sales_contract_crm.py`) — ***`monkeypatch(..., raising=False)` 는 개명을 못 보는 눈이다.***
  기본값으로 되돌렸다.

## §6 변이 감사 · 라이브 대조

★**라이브 종단 실측**(2026-09-13): 라운드 `6461133` 을 두 운영자에서 가져와 프로덕션이 `u-02` 를
뽑았고, **독립 검증기가 같은 라운드를 직접 조회해 `u-02` 를 재현**했다. 대조군으로 `--beacon-round`
를 빼면 `u-01` 이 나온다 ⇒ ***비콘 값이 실제로 결과를 바꾼다는 것이 두 모집단으로 확인됐다.***


`mutate_changed.py` + **`base:` 줄** 인용 · 「생존 0」 검산. ★네트워크 의존 테스트는
**주입 가능한 fetcher** 로 만들어 오프라인에서도 태운다(그러지 않으면 CI 에서 조용히 skip 된다).
