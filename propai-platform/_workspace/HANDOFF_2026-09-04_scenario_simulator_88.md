# 인계서 — 개발방식 시뮬레이터 · 전제감사 · 보류값 계약

**작성** `development-ai-88 [8bcb81]` · 2026-09-04
**★인계 규약**: 값이 아니라 **재측정 명령**을 적는다. 값은 휘발성이고, 특히 **「무주인」·「미머지」는
누가 집으면 그 순간 거짓**이 된다. 아래 모든 상태 표기 옆에 **재는 법**을 붙였다.

---

## 0. 먼저 — 착수 전에 이것부터

```bash
scripts/coord.sh status | tail -40          # 공유 보드(누가 뭘 잡고 있나)
gh pr list --state open --limit 30          # 열린 PR
git rev-list --left-right --count HEAD...origin/main   # ★워크트리 지연(0 0 이어야 안전)
```
★**옵시디언을 먼저 조회한다**(계획 게이트 §0). 이 주제어가 유효하다:
`심의엔진`(15) · `permit_gate`(7) · `법제처`(23) · `보류`(59) · `mixed_review`(8).
★**「법규엔진」·「인허가엔진」은 그 이름으로 0건**이다 — 다른 이름으로 존재한다.

정본 문서 셋:
- `errors/2026-08-28_법은_수치를_주는데_코드는_단일상수_6m를_쓴다.md` — **진단 정본**(§7 「왜 아무 층도 못 잡았나」)
- `design/2026-08-25_보류값_계약_부재의_사유를_코드로.md` — **보류값 계약**
- `decisions/2026-08-07_봉합을_쌓지_말고_범위를_줄인다.md` — **언제 멈출지**(§2026-09-02 재확인에 4라운드 기록)

---

## 1. 무엇을 했나 (전부 **머지·배포·라이브 확증** 완료)

사용자 신고: *"2종일반이 포함된 토지인데 **지구단위계획이 불가**로 뜬다"*

| PR | 무엇 | 재측정 |
|---|---|---|
| **#940** | 인접성 게이트 축을 법정 요건으로 3분할 · 첫 필지 → 면적가중 · 제1종 아파트 불허 | `gh pr view 940 --json state,mergeCommit` |
| **#950** | `#940` **배포 후 라이브에서** 찾은 «한 문장 안의 모순»(`통합개발…불가` 단정) | 〃 950 |
| **#963** | 전제감사기를 시나리오 경로에 배선(**읽기 전용**) | 〃 963 |
| **#972** | 우세 용도지역 **보류를 계약대로**(센티널 → `None + _absent`) | 〃 972 |

**라이브 확증 프로브**(그대로 붙여넣어 쓸 것):
```bash
TOK=$(curl -s -X POST https://api.4t8t.net/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@4t8t.net","password":"admin1234"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -s -X POST 'https://api.4t8t.net/api/v1/development-methods/scenarios' \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"address":"서울특별시 동작구 상도동 211-376","parcels":["서울특별시 동작구 상도동 211-376","서울특별시 동작구 상도동 211-204"],"use_llm":false}' -o /tmp/lv.json
python3 -c "
import json,re; d=json.load(open('/tmp/lv.json')); S=d['scenarios']; m={x['scheme']:x for x in S}
pa=d.get('premise_audit')
print('premise_audit:', type(pa).__name__, pa and (pa.get('checked'), pa.get('registered')))
print('지구단위:', m['지구단위계획 연계']['applicable'], '| 불가:', sum(1 for x in S if x['applicable']=='불가'),'/',len(S))
print('도시개발(정당한 불가):', m['도시개발사업(도시개발법)']['applicable'])
print('모순단정:', sum(1 for x in S if x.get('notes') and re.search(r'통합개발[^.]{0,20}불가', x['notes'])))
print('primary_zone:', d['site']['primary_zone'])"
```
**기대**: `premise_audit=dict (6,6)` · 지구단위 **조건부** · 불가 **10/20** · 도시개발 **불가** ·
모순단정 **0** · `primary_zone` 은 **용도지역 이름**(센티널이면 안 됨)

★**`sw` 마커로 api 배포를 판정하지 마라** — `#950`·`#963` 은 **api 단독**이라 `sw` 로는 «미포함» 이 나온다.
**api 라이브 응답을 직접 태워라**(위 프로브의 `premise_audit` 키 존재가 증거).

---

## 2. ★다음 좌표 (우선순위 순 · 전부 **무주인**)

★**「무주인」은 재측정하라**: `grep -i "<키워드>" .git/coordination/BOARD.md | tail -3` + `gh pr list --search "<키워드>"`

### ① 프론트가 보류 사유를 읽게 (가장 값싸고 사용자 가시)

★**정정(2026-09-04 · `development-ai-09` 와의 왕복에서 드러난 인계서 결함)**
이 인계서 초판이 `#963` 부채 문구를 인용하며 *"센티널이 화면에 맨몸으로 나간다"* 를
**현재 상태처럼** 읽히게 적었다. **그건 「형제와 그냥 일치시켰을 때」의 가정 상태**이고
`#972` 는 그 길을 **가지 않았다.** `origin/main` 실측:

    main 판 dominant_zone_by_area
      상업+주거(1200:800) → ('일반상업지역',   'area_weighted')   ← **센티널 아님**
      동률(1000:1020)     → ('제3종일반주거지역','area_weighted')

즉 **`main` 은 센티널을 한 번도 내지 않는다**(임의 단일화를 할 뿐). 상태 전이는:

    전(main)      "일반상업지역"   ← **거짓 확신**
    후(#972 단독)  None → "용도미상" ← **정직한 보류**

→ **`#972` 단독 배포는 정보 회귀가 아니다**(§E21 「묶어서 배포」 불필요).
  다만 `"용도미상"` 은 **왜 보류인지 말하지 못한다** — 그건 **회귀가 아니라 정보 부족**이고
  **정확히 ①이 필요한 이유**다.
★그리고 `main` 에 **죽은 상수 2개**(`ZONE_BASIS_MIXED_REVIEW`·`MIXED_REVIEW_SENTINEL` —
  선언만·사용처 0)가 남아 *"이 경로가 센티널을 쓴다"* 는 오독을 낳았다. `#972` 에서 제거했다.

지금 `primary_zone=None` 이면 화면이 `{site.primary_zone || "용도미상"}` **폴백**만 탄다.
`primary_zone_absent="ambiguous"` · `primary_zone_basis` 를 **읽는 코드가 0건**이다.
```bash
grep -rn "primary_zone_absent\|primary_zone_basis" propai-platform/apps/web --include=*.tsx --include=*.ts | grep -v __tests__
# 0건이면 아직 그대로
```
★형제 모듈이 이미 있다: `apps/web/lib/zoning/dominant-zone.ts`.
**새로 만들지 말고 그것을 쓰라** — ★단 **그 모듈은 「센티널 계약」만 다룬다**
(`MIXED_REVIEW_SENTINEL` 비교 + 빈 값 fallback). **`_absent` 코드를 받는 인자가 없어서
「왜 보류인지」를 원리적으로 말할 수 없다**(09 실측). **확장이 필요하다.**
`#972` 가 `primary_zone_absent="ambiguous"` 를 응답에 싣는다 — 닫힌 어휘는
`app/utils/withheld.py` 의 `ABSENT_REASONS`(7종), `ambiguous` = *"판정이 갈려 단일화 거부"*.

### ② `premise_audit` 결과를 화면에 (소비처 0)
```bash
grep -rn "premise_audit\|premiseAudit" propai-platform/apps/web | grep -v __tests__   # ★0건
```
★**기존 라우터 경로(`auto_zoning`)도 프론트가 안 읽는다** — 라우터는 `warnings`/`disclosure` 로 우회한다.
그 비대칭을 맞추는 것도 선택지다.

### ③ ★형제가 보류값 계약을 **위반**한다
```bash
grep -n 'mixed_review_required' propai-platform/apps/api/app/utils/withheld.py        # SENTINEL_VALUES(금지어)
grep -n 'dominant_zone = "mixed_review_required"' propai-platform/apps/api/app/services/zoning/special_parcel.py
grep -rn "validate_withheld_pair" propai-platform/apps/api/app --include=*.py | grep -v withheld.py
```
★검증기는 있는데 **`special_parcel`·`scenario_simulator` 가 그 검사를 안 탄다.**
**소비처 6곳 파급**이라 별건으로 남겼다.

★★**정정(09 접지 실측 2026-09-05) — 「검증기를 배선하면 된다」는 범위가 다르다.**
진짜 뿌리는 **`select_primary_zone` 이 사유를 이미 내는데 소비처가 안 읽는 것**이다:

    select_primary_zone([])  →  zone=''  basis='none'      ← 용도지역 **조회 실패**
    _is_residential('') = False   _is_commercial('') = False
    → :1870 `not res and not com` = True
    ⇒ **「모름」이 「녹지·공업 등 비주거·비상업 용도지역」과 같은 답을 받는다**
    ⇒ 주거 시나리오 **7종이 사유 없이 조용히 빠진다**
    (판정 지점 9곳: 1628·1641·1661·1717·1739·1750·1772·1778·1789 · 정의 467·471)

★**`#972` 는 이 축을 못 덮는다**(그 브랜치에서 직접 태워 확인):

    혼재 보류(#972 대상)   21종 · 추진가능 16   ← 회복(`zones` 에 주거가 있으므로)
    ★조회 실패(zone='')    20종 · 추진가능 12   ← **여전히 깨짐**(pool 이 통째로 빔)

`#972` 가 세운 것은 **「보류 ≠ 불가」**, 이 축은 **「모름 ≠ 아님」** — **같은 규율의 다른 축**이다.
소유: `development-ai-09`(2026-09-05 claim).

### ④ 세 번째 `primary_zone` 구현
`app/services/development/integrated_recommender/orchestrator.py:453 _primary_zone`
★**초판은 경로를 `integrated_recommender/orchestrator.py` 로 적었는데 그건 없는 경로다**(09 정정).
**인계서의 틀린 경로는 다음 사람에게 「없다」로 읽힌다.**
— **순수 argmax**(혼재 처리 없음)이고
그 값이 `development_method_interpreter.py:59` 의 **LLM 프롬프트**로 들어간다.
★즉 «형제와 일치시켰다» 는 **3개 구현 중 2개**만 정렬한 것이다.

### ⑤ 측정 불가로 **고지만** 한 축들 (지어내지 말 것)
- **12m 도로 구역**(건축법 시행령 §111①) · **대지 수별 상한**(§111③ **500m**) — 결합건축 요건
- **도→미터 변환** — `DEG_TO_M_MIN=88,800` 은 **스칼라 하나로는 원리적으로 불가**
  (동서 과대 · 남북 약 20% 과소). 투영(EPSG:5186) 또는 축별 변환 + **위도 입력** 필요
- `TOL_DEG # 약 6m`(≈100,000 m/deg)와 `DEG_TO_M_MIN`(88,800)이 **같은 `d` 에 공존**
- **「입지규제최소구역」은 폐지 제도**(국토계획법 §40의2 **삭제 2024.2.6** → §40의3 **도시혁신구역**)인데
  `#940` 이 그것을 **「불가 → 조건부」로 승격**시켰다. **승격만 하고 라벨은 안 고친 조합**이다
- **모아주택/모아타운** 자치법규 조회 **0건** — 근거 미확보라 게이트에서 빼지 않았다

---

## 3. ★도구 함정 (이 저장소에서 실제로 데인 것 — 전부 오늘 실측)

```bash
# 변이 판정 — 이 형태로만 하라
scripts/mutate_manual.sh <파일> <sed> <python> -m pytest <경로> -q > /tmp/m.txt 2>&1; rc=$?
v=$(grep -oE '^(CAUGHT|SURVIVED)' /tmp/m.txt | tail -1)          # ★줄시작 앵커
why=$(grep -cE "SyntaxError|IndentationError|Transform failed" /tmp/m.txt)
echo "${v:-?} (rc=$rc)"   # ★${v:-?} — 빈 값을 «모름»으로 표시. rc: 0=SURVIVED 1=CAUGHT
                          #   10=미커밋 11=주입실패 12=셸래퍼(판정불가) 13=빨간 기준선
```
- ★**셸 래퍼(`bash -c`) 금지** — `rc=12`. 도구가 `execvp` 로 **직접 실행**한다. `cd` 는 **디렉토리를 바꿔서** 부르라
- ★**앵커 없이 긁으면 거짓 SURVIVED** — pytest 가 실패 테스트 **소스를 출력**하는데 주석에 그 낱말이 있으면 잡힌다
- ★**`sed` 가 구문을 깨면 rc≠0 → 거짓 CAUGHT** — `why != 0` 이면 그 CAUGHT 는 무효
- ★**판정 전 기준선 `rc=0` 확인**(도구가 `rc=13` 으로 거부하지만, 거부를 「완료」로 읽지 말 것)
- ★**`git grep --heads` 오용 시 전부 0건** — 대조군으로 조회기 생존부터 증명하라
- ★**라우터 디렉토리가 둘**: `apps/api/app/routers/` **와** `apps/api/routers/`. 한쪽만 보면 «소비처 0» 오판(내가 3번 밟음)
- 로컬 `python3` 은 **3.10** — 백엔드는 `<venv>/bin/python`(3.12=CI). venv 경로는 워크트리마다 확인

---

## 4. ★이 캠페인이 남긴 판정 규율 (재사용 가치가 가장 큼)

1. **머지·배포는 완료가 아니라 측정 시점이다.** `#950` 은 `#940` 배포본을 **라이브로 읽다가** 나왔다.
2. **대조군은 「다를 것 같은 축」이 아니라 「그 변수가 실제로 지배하는 축」이어야 한다.**
   `com` 축 락을 **세 번** 고쳤다(이름 집합 → 판정 → `est_far`·결합건축).
3. **느슨한 하한은 변이를 하한 안에서 살린다.** `>= 20` → **실측값 결속**(21·16 / 20·12).
4. **두 모집단은 「같은 경로」를 지나야 한다.** 하나는 `simulate` 경유·하나는 직접 호출이면
   직접 호출 쪽이 **배선 변이를 원리적으로 못 본다.**
5. **형태는 정상인데 값이 없거나 틀린 오류**가 가장 조용하다 —
   `${v:-?}` · `checked==registered` · 「미등록을 완료로 세지 않기」로 막는다.
6. **방어를 만들기 전에 「이미 막고 있는 것이 있나」를 재라.** 락파일 제안이 그렇게 기각됐다.
7. **적대 검증은 매번 「내 봉합이 만든 새 결함」을 찾았다**(`#940` 4회 · `#963` 1회).
   **자기승인하지 마라** — 4회 전부 REJECT/조건부였고, 1차에서 멈췄으면 12/21 이 미적용이었다.

---

## 5. 협업 (세션 이름은 **주소이지 신원이 아니다**)

★**보내기 직전에 `ListAgents` 로 이름을 다시 확인하라.** 이름은 재사용·개명된다.
★**이름이 목록에 없다 ≠ 세션이 죽었다**(개명이면 **이중 계상**돼 총원이 보존돼 조용하다).
소유자 판정은 **보드 마지막 활동 시각 + 계획서 서명**으로.

| 역할 | 세션(2026-09-04 기준 · **재확인 필수**) |
|---|---|
| 배포·큐 레인 | `development-ai-3a` — *"CI 초록만으로 밀지 않는다. 소유자 신호를 기다린다"* |
| 배포 실행 | `development-ai-62` |
| 변이 도구 | `development-ai-3c` |
| 프론트·사통맵 | `development-ai-23` |

★**배포 요청 시 「확증 조건」을 반드시 붙여라**(3a 가 요구한다):
①바뀌어야 하는 것 ②**바뀌면 안 되는 것(음성 대조군)** ③**판정하면 안 되는 것(미측정)**
*"조건 없는 요약이 더 멀리 퍼진다."*

---

## 6. ★내가 틀렸던 것 (같은 함정을 다시 밟지 않도록)

- **낡은 「무주인」 라벨을 재지 않고 승계해 보드에 재유포** — 다음 사람이 끝난 일을 다시 잡을 뻔했다
- **`app/routers/` 만 보고 「소비처 0」 오판** — 3회
- **`git grep --heads` 오용으로 「법령엔진에 판정 함수 0개」를 발견으로 읽을 뻔** — 대조군이 갈랐다
- **감시 루프가 「미등록」을 「완료」로 셈** — 거짓 완료
- **`monkeypatch` 가 조용히 아무것도 안 함**(`_enrich` 가 존재하지 않아 `raising=False` 통과)
- **내 락이 결함을 정답으로 못 박음**(`_zone_mix_from` `== []`) — 이어받는 사람이 고치려면 락을 먼저 깨야 했다
