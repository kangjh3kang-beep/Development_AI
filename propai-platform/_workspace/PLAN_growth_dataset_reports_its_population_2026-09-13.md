# 학습 데이터셋이 **자기 모집단을 말하지 않는다** — `LIMIT` 로 자른 반환수를 「활성 페어 수」로 낸다

- 날짜: 2026-09-13 · sid=ad208019 · 브랜치 `fix/growth-dataset-reports-its-population`
- 대상: `apps/api/app/services/growth/learning_loop.py::build_dataset_jsonl` + 소비처 2곳

## §0 옵시디언·보드 조회 결과

| 찾은 것 | 결과 |
|---|---|
| **이미 기각된 접근** | **없음** — 이 함수의 `limit` 을 다룬 기록이 볼트·보드에 없다 |
| **같은 클래스의 앞선 결함** | **있다(오늘, 같은 저장소, 두 세션)**: `GET /growth/insights?limit=500` 의 `items` 를 전수로 읽어 **분포·개수·「없다」를 모두 틀렸다**(전수는 `total=4133`). 통합자도 같은 엔드포인트에서 `500 ↔ 4133` 을 놓쳤다 |
| **미결·부채** | 보드 부채: `_workspace/vault_pending_2026-09-08_ad20/` (별건) |
| **이전 판단의 근거** | 「대조군을 붙이면 0건이 근거가 된다」가 **거짓**임을 오늘 합성으로 확정 — 대조군은 **조회기 사망만** 가르고, **상한(절단)은 못 잡는다** |

★**신선도 재확인**: 인용한 좌표를 전부 `origin/main`(6223c36d1) 기준으로 다시 읽었다.

## §1 전제 표 — **측정값**(예상값 아님)

| 전제 | 확인 방법 | 결과 |
|---|---|---|
| `build_dataset_jsonl` 이 `LIMIT :lim` 로 자른다 | 원문 | ✔ `ORDER BY created_at DESC LIMIT :lim` |
| 반환 `count` 가 **모집단이 아니라 반환수**다 | 원문 | ✔ `count = len(lines)` |
| 소비처가 그것을 **모집단으로 제시**한다 | 원문 | ✔ `learning_loop.py:549` `summary["dataset"] = {"active_pairs": ds.get("count", 0)}` |
| 형제 표면은 `total` 을 **이미 준다** | 라이브 | ✔ `/growth/learning/candidates` → `{"items":[], "total":0, "limit":1, "offset":0, …}` |
| 지금 발화하고 있나 | 라이브(읽기 전용) | ✘ **사건 미발생** — `/growth/learning/dataset` 2,907 B · **3줄**. 모집단 ≪ 5000 |
| 호출부 전수 | `git grep` | 프로덕션 **2곳**(`learning_loop.py:548` · `routers/growth.py:746`) · 테스트 3곳 |

★**라벨**: 이것은 **잠복**이다(「구멍 없음」이 아니라 **사건 미발생**). 그러나 **처방 비용이 낮고**, 같은 클래스가 **오늘 같은 저장소에서 두 세션을 넘어뜨렸다.**

## §2 변경과 「회귀가 아닌 근거」

1. `build_dataset_jsonl` 이 `total`(= `LIMIT` 없이 같은 `WHERE` 에 걸리는 행 수)과
   `truncated`(= `count < total`)를 **함께** 반환한다.
2. `learning_loop` 요약이 `active_pairs` 옆에 **`active_pairs_total` · `truncated`** 를 싣는다.
3. 라우터 감사기록 `detail` 에 `total`·`truncated` 를 싣는다(반출 추적이 **얼마나 있었는지**까지 남는다).

**회귀가 아닌 근거**: 기존 키(`count`·`jsonl`·`statuses`·`service`·`rights_enforced`·
`excluded_no_rights`)와 기존 값은 **그대로**다. **추가만** 한다. 기존 테스트 3곳은 `count` 만 읽는다.

## §3 ★검증하지 못한 것

- **절단이 실제로 일어나는 상태를 라이브에서 못 만든다**(쓰기 금지 · 활성 예시 ~4건).
  ⇒ 절단 경로는 **스텁으로만** 태운다. 라이브 확증은 **미측정**으로 남긴다.
- `COUNT(*)` 추가로 인한 **성능 영향 미측정**(같은 `WHERE`, 인덱스 동일 가정).
  ⇒ 이 경로는 **관리자 다운로드 + 학습 사이클 요약**이라 고빈도가 아니다 — 그것도 **가정**이다.
- 다른 `limit` 사용처(예: `/growth/insights` 라우터)는 **이 PR 범위 밖**이다. 별건.

## §4 되돌리기

단일 커밋. `git revert`. 추가 키만 늘렸으므로 소비처가 없어도 안전하다.

## §5 잠금 — **무엇이 이 변경을 지키는가**

| 락 | 축 |
|---|---|
| `test_dataset_reports_its_population` | 모집단 > limit 인 스텁에서 `count < total` · `truncated is True` |
| `test_dataset_not_truncated_when_it_fits` | 모집단 ≤ limit 에서 `count == total` · `truncated is False` (**두 모집단**) |
| `test_summary_carries_the_total_not_just_the_count` | `run_learning_cycle` 요약이 `active_pairs_total` 을 싣는가 — **소비처까지** |
| `test_count_never_exceeds_total` | ★**자기모순 검사**: 어떤 입력에서도 `count <= total` |

★**공허 방지**: 각 락은 스텁이 **실제로 두 값을 다르게** 내는지 먼저 단언한다(차가 0인 픽스처는 잠금이 아니다).

## §6 실행 중 드러난 것 — **계획서에 없던 두 가지**

### ★6-1 기존 회귀망이 **제 설계 결함**을 잡았다

계수 쿼리를 **행 조회와 같은 `try`** 에 뒀더니, 스텁이 `.scalar()` 를 못 받자 예외가 나고
**데이터셋 자체가 날아갔다**. 기존 테스트 **3건**(`test_wpj_growth_loop` 2 · `test_growth_learning_candidates` 1)이
즉시 빨개졌다. ⇒ ***보조 측정이 주 산출물을 죽이면 안 된다.*** 자기 `try` 로 분리하고 **본 산출물 뒤**로 옮겼다.
★이건 「gather 로 묶으면서 실패까지 묶었다」와 같은 클래스다 — **성공 경로를 묶으면 실패 경로도 묶인다.**

### ★★6-2 내 소비처 락이 **내가 쓴 주석**을 집고 있었다(변이 SURVIVED 실측)

    변이 C: summary 에서 `"active_pairs_total": ds.get("total"),` 줄 삭제  →  **SURVIVED**

원인: 락이 `"active_pairs_total" in inspect.getsource(...)` 였고, **바로 위에 내가 쓴 주석**에
같은 낱말이 있었다. 저장소 지침이 *「소스 검사는 주석·문자열에 뚫린다」* 를 **명문으로** 적어 뒀고
**내 락이 그것을 어겼다.**
⇒ `summary["dataset"]` 의 **딕셔너리 리터럴 키를 AST 로** 뽑아 비교하도록 바꿨다(대조군·역대조군 포함).
  재판정: **C SURVIVED → CAUGHT**.
★***주석에 예시를 적으면 그 예시가 다음 검사의 위양성/위음성이 된다*** — 이번엔 **위음성**이었다.

## §7 변이 결과(손 5 · 전부 커밋 후 · 원복 바이트 동일 확인)

| 변이 | 결과 |
|---|---|
| A `truncated` 를 상수 `False` 로 | **CAUGHT** |
| B `total` 을 `len(lines)` 로(= count 동일화) | **CAUGHT** |
| ★C 소비처에서 `active_pairs_total` 제거 | SURVIVED → **CAUGHT**(락 교체 후) |
| D `total = None` → `0`(모름→없음 뭉개기) | **CAUGHT** |
| E 소비처에서 `truncated` 제거 | **CAUGHT** |

★**이 5개는 내가 골랐다.** 기계 변이(`scripts/mutate_changed.py`)를 별도로 돌린다 — 결과는 PR 본문에 싣는다.
