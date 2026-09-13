# 계획 — 동·호 추첨에 **검증 가능한 난수(VRNG)** 적용 + 블록체인 앵커링

세션 `development-ai-a2` · `sid=79cfa3eb` · 2026-09-13
요청: *"RNG난수생성시스템을 분양앱의 동·호추첨시스템에 적용"* + *"블록체인과 연동해 스마트컨트랙트"*

## §0 옵시디언 조회 결과

| 찾을 것 | 결과 |
|---|---|
| 이미 기각된 접근 | **없음**(이 주제로 기각 기록 0건) |
| 추첨 **설계** 기록 | `2026-07-22_PropAI_분양앱_사이트맵_스토리보드.md` **1건뿐**이고 그 안에서 「추첨」은 **1회 언급**(계약자 여정의 한 단계). **설계 결정 기록 없음** |
| `commit-reveal`·「사전 공약」·「검증 가능한 난수」 | **0건** — 이 주제는 볼트에 **전례가 없다** |
| 미결·부채 | 없음 |

## §1 전제 표 — **전부 실측** (★가장 중요한 것: 둘 다 「없는 것을 새로 만드는 일」이 아니다)

| # | 전제 | 확인 방법 | **결과** |
|---|---|---|---|
| 1 | 추첨 엔진이 있나 | 전수 grep | ★**있다** — `app/services/sales/draw/draw_engine.py` (340줄) |
| 2 | **추첨 경로가 몇 개인가** | 엔드포인트 전수 | ★**둘이고 난수 정책이 서로 다르다**(아래 §1-A) |
| 3 | 스마트컨트랙트 인프라 | `contracts/` 실측 | ★**있다** — Solidity 4종(`PropAIEscrow`·`PropAIToken`·`PropAIGovernance`·`SubcontractPayment`) + Hardhat + typechain + 테스트 4종 |
| 4 | 체인에 **실제로 배포**됐나 | ①`contracts/deployments/amoy/` ②★**체인에 직접 질의**(`eth_getCode`) | ①**배포 기록 파일이 있다** — `PropAIEscrow` `0x961cba4A…` · chainId **80002** · 2026-03-18. ②★**판정 불가** — 이 환경에서 `https://rpc-amoy.polygon.technology` 가 **HTTP 000**(대조군: `api.4t8t.net` 200 · `api.github.com` 200 → 망은 살아 있고 **그 호스트만 막혔다**). ***「파일에 주소가 있다」는 「체인에 코드가 있다」가 아니다*** — 나는 처음에 이것을 「실배포」라고 말했고 그건 **파일을 본 것**이었다. 정정한다. |
| 5 | API 가 체인을 부르나 | 소비처 전수 | **부른다** — `apps/api/services/blockchain_service.py`(Web3.py) ← `apps/api/routers/blockchain.py` (★단 이 트리는 `app/` 트리와 **다른 계층**이다 — §3-5) |
| 6 | 추첨을 잠그는 테스트 | 전수 grep(`draw_for_candidate`/`draw_engine`/`sales_draw`) | ★**전용 테스트 0건**(`test_sales_contract_crm.py` 가 계약 경로로 스치기만) · 대조군 `sales_unit_inventory` 1건 → 조회기 생존 |
| 7 | 추첨 순번(`seq`) 결정 | `_next_seq` | **등록 순서**(`MAX(seq)+1`) — **무작위화 없음** |

### §1-A ★두 경로의 난수 정책 (실측 · 이 계획의 출발점)

| | ① 청약 당첨자 추첨 | ② 동·호 즉석추첨 |
|---|---|---|
| 엔드포인트 | `POST /subscription/{ann_id}/draw` | `POST /draw/groups/{g}/candidates/{c}/draw` |
| 난수 원천 | `seed = body.seed or ann.announce_no or ann_id`<br>`_tiebreak = sha256(f"{seed}:{app_id}")` | `seed = secrets.token_hex(8)`<br>`random.Random(seed).choice(sorted(pool))` |
| 난수의 역할 | **동점자 순서**(rank·가점 다음 3순위 키) | **세대 선택** |
| ★치명 결함 | **①-a 호출자가 `seed` 를 보낼 수 있다** → 오프라인에서 원하는 당첨자 나올 때까지 굴린 뒤 제출 = **결과 선택**<br>**①-b 미지정 시 seed = 공고번호** → **공개·예측 가능** ⇒ ***당첨자를 사전에 계산할 수 있다*** | **②-a 사전 공약이 없다** → 서버가 뽑아 보고 롤백 후 재시도(**grinding**) 가능. 원장엔 **성공한 seed 하나만** 남는다<br>**②-b 재현이 CPython 구현 종속**(`random.Random(str)` 의 시딩·`choice` 내부) → **외부 감사자가 다른 언어·다른 파이썬으로 재현 불가**<br>**②-c pool 원본 미저장** · 해시도 **sha256 앞 16자(64비트) 절단** |

★**그리고 독스트링이 약속한다**: *「누구나 재현·검증(부정 재추첨 방지)」*.
①은 그 약속을 **못 지키고**, ②는 **절반만** 지킨다 — 「그 seed 로 그 결과가 나온다」는 증명하지만
***「그 seed 가 공정하게 뽑혔다」는 증명하지 못한다.***

## §2 설계 — 4단계. **1단계만으로도 치명 결함이 사라진다**

### Phase 0 — 체인 없이(2~3일) · ★여기가 본체

0-1. **난수 추출기를 교체**: `app/services/sales/draw/vrng.py`
     - `HMAC-SHA256(key=seed_material, msg=f"{domain}:{counter}")` → 정수 → **rejection sampling** → 인덱스
     - ★`random.Random` **금지**. HMAC-SHA256 은 **언어·버전 독립**이라 감사자가 파이썬 없이도 재현한다
0-2. **commit–reveal**
     - 추첨 개시: `server_nonce = secrets.token_bytes(32)` → **`commit = sha256(nonce)` 를 원장에 먼저 기록**(`DRAW_COMMIT`)
     - 추첨 실행: `nonce` 를 **공개**하고 `sha256(nonce) == commit` 검증. ⇒ **서버가 seed 를 갈아치우면 해시가 안 맞는다** = grinding 차단
0-3. **`run_draw` 의 seed 입력 제거** — 호출자 seed 금지. 공고번호 폴백 **삭제**
0-4. **pool 전문 저장** — 정렬된 unit id 목록을 원장에 싣고, 해시는 **절단 금지**(sha256 64자)
0-5. **순번(`seq`)도 같은 VRNG 로** 배정(등록 순서 배제)
0-6. **검증기**: `scripts/verify_draw.py` + 공개 엔드포인트 — `(commit, nonce, pool, 결과)` 만으로 **제3자가 재현**

### Phase 1 — 서버 단독 결정 배제(1~2일)
`seed_material = HMAC(server_nonce, participants_hash ‖ beacon)`
- `participants_hash` = 대상자 명부 확정 해시(공약에 포함)
- `beacon` = 추첨 시각 이후 공개되는 **외부 공개 난수**(drand 등) ⇒ 서버도 참가자도 **단독으로 못 정한다**

### Phase 2 — ★**블록체인 앵커링**(이미 있는 자산 재사용 · 3~5일)
새 컨트랙트 `contracts/src/DrawRegistry.sol`:
```solidity
function commit(bytes32 drawId, bytes32 commitHash, bytes32 participantsHash) external onlyOperator;
function reveal(bytes32 drawId, bytes32 nonce, bytes32 poolHash, bytes32 resultRoot) external onlyOperator;
event DrawCommitted(bytes32 indexed drawId, bytes32 commitHash, uint256 at);
event DrawRevealed(bytes32 indexed drawId, bytes32 nonce, bytes32 resultRoot, uint256 at);
```
- ★★**개인정보는 절대 온체인에 올리지 않는다** — 이름·연락처·동호는 **오프체인**, 체인에는 **해시만**
  (개인정보보호법 · 체인은 **삭제 불가**라 파기 요구를 구조적으로 못 지킨다)
- 결과는 **머클루트** 하나만 올리고, 개인은 자기 항목의 **머클 증명**으로 검증
- 기존 자산 그대로: Hardhat · Polygon **Amoy(80002)** → 검증 후 **Polygon 메인넷(137)**
- 배선은 `blockchain_service.py` 의 Web3.py 패턴을 따른다(신규 표면 최소화)

### Phase 3 — 온체인 난수(Chainlink VRF) · **선택**
- 필요조건: **서버를 전혀 신뢰하지 않는 모델**을 요구할 때만
- ★Phase 0~2 로 «사전 계산 불가 + 사후 변조 불가 + 제3자 재현 가능» 은 **이미 달성**된다.
  VRF 는 그 위에 «운영자도 못 본다」를 더하는 것이고 **가스·지연·구독 운영** 비용이 붙는다
- ⇒ **기본 계획에 넣지 않는다.** 요구가 확인되면 그때 별도 계획

## §2-B ★사용자 확답 2건과 **그 귀결**(2026-09-13)

| 질문 | 답 | 설계에 미치는 영향 |
|---|---|---|
| 공급 유형 | **임의공급** | 청약홈 연동·법정 공개추첨 절차를 전제하지 않는다. ⇒ **주 사용처는 ②(동·호 즉석추첨)**. 다만 ①(`run_draw`)도 **코드에 살아 있으므로 결함은 막는다** — 임의공급에서도 순위·가점형 추첨을 쓸 수 있다 |
| 적용 시점 | **신규 공고부터** | ★**소급 금지** ⇒ **v1/v2 공존**이 강제된다(아래) |

### ★「신규 공고부터」가 강제하는 것 — 버전 공존

옛 추첨(v1)으로 이미 배정된 건은 **그 알고리즘으로 재현**돼야 하므로 v1 경로를 지울 수 없다.
그런데 **지우지 않으면 신규 공고가 실수로 v1 을 탈 수 있다.** 둘 다 만족시키려면:

1. 모든 추첨 이벤트에 **`algo_version`** 을 기록한다(v1 기록은 **부재 = v1** 로 읽는다)
2. 추첨그룹·공고에 **`draw_algo` 를 생성 시점에 못 박는다**(나중에 못 바꾼다)
3. ★**신규 생성물은 v2 만 허용**하는 게이트를 둔다 — 「v1 로도 만들 수 있다」를 남기면
   그것이 곧 **나중의 서식지**가 된다(이 저장소가 반복해 데인 형태)
4. 락이 **두 모집단**을 단언한다: *기존 그룹은 v1 로 재현되고, 신규 그룹은 v1 을 거부한다*

★**소급 변경이 아님을 증명하는 것도 락이다** — v1 로 배정된 과거 건의 재현 결과가
이 변경 전후로 **같아야** 한다(회귀가 아닌 근거, §2 의 그것).

## §3 ★검증하지 못한 것 (비우지 않는다)

1. **임의공급의 구체적 법·계약 요건은 여전히 미측정이다.** 「주택공급에 관한 규칙」 청약 절차가
   아니라는 것까지가 확인된 것이고, ★**「공정 추첨」을 광고·고지하면 그 주장 자체가 사실이어야
   한다**(표시·광고 측면). 공증·입회·녹화 등 **운영 요건은 사업자 판단**이며 이 계획은 그것을
   가정하지 않는다 — 다만 **Phase 0 의 산출물이 그 증빙으로 그대로 쓰인다.**
2. **①의 실제 운용 여부** — `run_draw` 가 라이브에서 실제로 쓰이는지(호출 이력)는 **미측정**.
   코드 경로만 봤다.
3. **Amoy 배포분의 현재 생존 — ★조회를 시도했고 「판정 불가」다.**
   `eth_getCode` 로 물었으나 이 환경에서 **RPC 호스트가 차단**돼 있다(HTTP 000 · 대조군 2건 200).
   ⇒ **「배포돼 있다」도 「없다」도 말할 수 없다.** Phase 2 착수 전에 **망이 열린 곳에서**
   `eth_getCode` 가 `0x` 보다 긴 값을 돌려주는지 확인해야 한다(대조군: 아무 EOA 주소는 `0x`).
   ★그리고 Phase 2 는 **새 컨트랙트 배포**가 필요하므로 어차피 **RPC 송출 경로 확보가 선행 조건**이다.
4. **가스비·운영비 미측정** — Polygon 메인넷 앵커링 1건당 비용, 월 추첨 건수 가정 없음.
5. ★**`apps/api/services/` 와 `apps/api/app/services/` 가 다른 트리다.** `blockchain_service.py` 는
   **전자**에 있고 추첨 엔진은 **후자**에 있다. 이 저장소에는 트리가 셋이라는 실측 기록이 있다 —
   **어느 트리에 붙일지는 착수 전에 다시 재야 한다.**
6. **현재 추첨이 이미 운영 중이라면** — 진행 중 공고의 규칙을 바꾸는 것은 **소급 변경**이다.
   적용 시점(신규 공고부터)을 사용자와 정해야 한다.

## §4 되돌리기 경로

- Phase 0 은 `vrng.py` **신규 파일** + 두 엔진의 **호출 지점 교체**다. 옛 경로를 지우지 않고
  `DRAW_ALGO_VERSION` 을 원장에 남기면, 되돌릴 때 **과거 추첨의 검증은 그대로 재현**된다.
- Phase 2 는 **관측·기록 전용**(체인 기록이 실패해도 추첨은 성립). 앵커링을 끄면 원상.
  ★단 «체인에 올렸다»를 사용자에게 약속한 뒤 끄면 **그 약속이 거짓**이 되므로, 문구는 켠 뒤에 쓴다.

## §5 잠금 (같은 커밋에)

| 락 | 무엇을 잠그나 |
|---|---|
| `test_vrng_is_language_independent` | 알려진 `(key, msg)` → **고정 기대값**(외부 도구로 계산한 값). 파이썬 버전이 바뀌어도 같아야 한다 |
| `test_vrng_uniform_and_no_modulo_bias` | rejection sampling 이 실제로 편향을 없애는가(χ² · 대조군으로 modulo 구현을 넣어 **기울어짐을 검출**) |
| `test_commit_precedes_reveal` | ★**공약 없는 추첨은 거부**된다(공약 이벤트가 없으면 `draw` 가 실패) |
| `test_tampered_nonce_is_rejected` | `sha256(nonce) != commit` 이면 **거부** |
| `test_caller_cannot_supply_seed` | `run_draw(seed=...)` 가 **더는 존재하지 않거나 무시**됨 + 공고번호 폴백 부재 |
| `test_pool_is_stored_untruncated` | pool 원본 저장 + 해시 **64자**(절단 변이 CAUGHT) |
| `test_seq_is_drawn_not_insertion_order` | 등록 순서와 추첨 순번이 **다른 모집단**을 만든다 |
| `test_no_pii_onchain` (Phase 2) | 온체인 페이로드에 **이름·연락처·동호 문자열이 없다**(대조군: 해시는 있다) |
| `DrawRegistry.test.ts` (Phase 2) | 이중 commit 거부 · reveal 불일치 거부 · 권한 |

## §6 변이 감사

`scripts/mutate_changed.py` 실행 · **`base:` 줄과 함께** 인용 · **「생존 0」 검산**.
★`.sol`·`.sh` 는 그 도구의 축 밖(`.py/.ts/.tsx` 만) ⇒ **`mutate_manual.sh` 로 따로 태운다.**
★이 변경은 **추가가 본체**라 기계 변이가 잘 붙지만, **삭제 부분**(공고번호 폴백 제거 등)은
분모에 안 들어온다 — **「남기기로 한 것」에 손 변이**를 넣는다.
