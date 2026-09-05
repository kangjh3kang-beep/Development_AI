"""조례의 **조건부 값**을 조문 제목으로 분류하고, 부지 조건과 매칭한다.

【무엇을 푸는가 — 이 캠페인의 원래 목표】
조례는 `용도지역 → 값 하나` 가 아니라 **`용도지역 × 조건 → 값들`** 이다. 오산시 조례에서
`자연녹지지역` 은 6개 조에 나오고 건폐율이 여러 개다(실측):

    제45조① 16호   20%  ← 기본(정답)
    제45조        30%  주유소·액화석유가스 충전소 / 30% 유원지 · 20% 공원 / 30% 학교
    제46조        30%  그 밖에 용도지구·구역 등
    제48조        80%  방화지구
    제49조        40%  기존 공장 증축
    제50조        30%  성장관리방안 수립지역

파서는 기본값을 골라내고 나머지를 `conditional` 로 보관하는 데까지 왔다. 그런데 그 값들이
**파서 함수 밖으로 나가지 못했다**(`_parse_bcr_far_from_text` 반환 계약에 키가 없었다) —
"소비처 0" 보다 한 단계 이른 상태다. 이 모듈이 그 값에 **조건 이름**을 붙여 밖으로 내보내고,
부지 조건과 맞춰 준다.

【★분류 앵커는 조제목이다 — 조각 텍스트가 아니다(실측)】
조건부 조각의 앞부분은 용도지역명 **뒤**에서 잘려 시작한다("에서는 건폐율을 30퍼센트…").
조건을 말하는 문구는 그 **앞**, 조제목에 있다: `제50조(성장관리방안 수립지역에서의 건폐율 완화)`.
그래서 가장 가까운 앞선 `제NN조(제목)` 을 앵커로 삼는다.

【★★함정 — 조건부가 곧 완화는 아니다】
오산시 `제47조(건폐율의 **강화**)` 가 실재한다. 조건부 값을 무조건 완화로 취급하면
**기본값보다 낮은 값을 상향 여지로 표시**하는 과대낙관이 된다. 방향(`direction`)을 함께 낸다.

【★적용하지 않는다 — #704 와 같은 계약】
조건 충족 여부를 우리가 확인할 수 있는 것은 **부지 designation 으로 판별되는 것뿐**이다.
건축물 용도(주유소·학교·유원지)·연혁(기존 공장) 조건은 **설계가 정해져야** 판정된다.
그래서 이 모듈은 `applied: False` 로 **후보만** 내고, 실효값은 건드리지 않는다.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.zoning.district_regime import (
    METRO_REGIME_NAMES,
    _norm,
    is_growth_management_plan,
)
from apps.api.app.utils.withheld import SOURCE_UNAVAILABLE

# 조제목 → 조건 종류. **부지 designation 으로 판별 가능한 것**과 그렇지 않은 것을 가른다.
#   site  = 부지가 그 구역/지구에 속하는가로 판정(우리가 측정 가능)
#   use   = 건축물 용도·연혁으로 판정(설계가 정해져야 안다 — 측정 불가)
#   base  = 기본 조문(조건 아님)
_ARTICLE_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # (조제목 키워드, condition_key, kind)
    (("성장관리방안", "성장관리계획"), "growth_management_plan", "site"),
    (("방화지구",), "fire_district", "site"),
    (("용도지구", "용도구역"), "designated_district", "site"),
    (("기존 공장", "기존공장"), "existing_factory", "use"),
    (("경관지구",), "landscape_district", "site"),
)

# 조제목이 **강화**를 말하면 그 값은 상향 여지가 아니다(오산시 제47조 실재).
_STRENGTHEN_TOKENS: tuple[str, ...] = ("강화", "축소", "제한")

_ARTICLE_RE = re.compile(r"제(\d+)조(?:의\s*\d+)?\s*\(([^)]{1,60})\)")


def find_article(section: str, pos: int) -> dict[str, Any] | None:
    """`pos` 직전의 가장 가까운 `제NN조(제목)` 를 찾는다. 없으면 None."""
    last = None
    for m in _ARTICLE_RE.finditer(section, 0, max(pos, 0)):
        last = m
    if not last:
        return None
    return {"article": f"제{last.group(1)}조", "article_title": last.group(2).strip()}


def extract_article_body(section: str, pos: int) -> str:
    """`pos` 가 속한 조문의 **본문 전체**(다음 조문 헤더 직전까지)를 돌려준다.

    ★왜 필요한가 — 조각(`context`)으로는 원리적으로 불가능하다(2026-08-21 실측).
      `context` 는 용도지역명 **뒤**에서 잘려 시작하는 **120자 고정 창**이라
      **앞뒤가 모두 잘린다**. 오산시 제46조 실측:

          context  → "…에 지정된 경우 30퍼센트 이하 3. 수산자원보호구역: 30퍼센트 이하 4. …따른"
          본문전체 → "1. 취락지구: 40 / 2. 개발진흥지구: (자연녹지) 30 / 3. 수산자원보호구역: 30
                      / 4. 자연공원: 60 / 5. 산업단지 등: 80"

      즉 **1·2번과 5번이 창 밖에 있다.** 이 창으로 매칭을 넓히면 보이지 않는 항목을
      말없이 빠뜨리고 *"이 부지는 해당 없음"* 이라는 **거짓 음성**을 낸다 —
      지금의 보수적 기각보다 나쁘다. 그래서 창이 아니라 **본문**을 본다.
    """
    # ※변이 생존(설명 가능): 이 줄을 지워도 아래 경로가 빈 문자열을 낸다(**이중 가드**) —
    #   `starts=[]` → `begin=0` → `end=0` → `body=""`. 조기반환은 의도를 적어 두는 쪽이다.
    if not section:
        return ""
    starts = [m.start() for m in _ARTICLE_RE.finditer(section)]
    begin = 0
    for st in starts:
        if st <= pos:
            begin = st
        else:
            break
    end = next((st for st in starts if st > begin), len(section))
    body = section[begin:end]
    # ★법제처 XML 원문이라 조문 끝에 CDATA/태그 꼬리가 붙는다(실측: `]]></조내용><조 …`).
    #   나열 파싱 전에 잘라 내지 않으면 태그 안의 숫자가 항목처럼 읽힌다.
    cut = body.find("]]>")
    if cut != -1:
        body = body[:cut]
    return body


# 나열 항목: `1. 취락지구: 40퍼센트 이하` · `4. 「자연공원법」에 따른 자연공원: 60퍼센트 이하`
#   ★항목명 상한은 넉넉해야 한다 — 오산 제46조 5호는 근거법 인용이 길어 **100자를 넘는다**
#     (`공업지역에 있는 「산업입지…」 제2조제8호가목부터 …준산업단지`). 80자로 자르면
#     **80% 항목이 통째로 사라진다**(실측으로 적발).
_ENUM_RE = re.compile(
    r"(?:^|\s)(\d{1,2})\.\s*([^:：\n]{2,160}?)\s*[:：]\s*([^0-9]{0,40}?)(\d{1,3})\s*퍼센트"
)
# ★개정 주기(`〈개정 2025. 2. 28〉`)를 먼저 걷어낸다 — 그 안의 `2. 28` 이 나열 번호로 읽혀
#   1호를 `'28〉 1. 취락지구'` 로 오염시켰다(실측으로 적발). 날짜는 항목이 아니다.
_AMEND_NOTE_RE = re.compile(r"[〈<]\s*(?:개정|신설|전문개정|본조신설)[^〉>]{0,40}[〉>]")
# 항목명에서 근거법 인용(「…」)과 수식어를 걷어내 **구역 이름**만 남긴다.
_LAW_CITE_RE = re.compile(r"「[^」]{1,60}」(?:\s*제[\d조항호가-힣]+)*(?:에\s*따른)?\s*")
# 항목 안에 붙는 용도지역 한정("자연녹지지역에 지정된 경우")
_ZONE_SCOPE_RE = re.compile(r"([가-힣]{2,10}지역)에\s*지정된\s*경우")


def parse_district_options(body: str) -> list[dict[str, Any]]:
    """조문 본문의 `N. 구역명: X퍼센트` 나열을 (구역명, 값, 용도지역한정) 로 뜯는다.

    ★값은 **항목마다 다르다**(오산 제46조: 취락 40 · 개발진흥 30 · 수산자원 30 ·
      자연공원 60 · 산업단지 80). 종전에는 조각 스캐너가 집은 **하나**(30)가
      조 전체를 대표했다 — 취락지구 부지에 30% 를 보여 주는 것은 **틀린 수치**다.
    """
    out: list[dict[str, Any]] = []
    body = _AMEND_NOTE_RE.sub(" ", body or "")
    for m in _ENUM_RE.finditer(body):
        raw = m.group(2).strip()
        prefix = m.group(3) or ""
        zone_scope = None
        zm = _ZONE_SCOPE_RE.search(prefix) or _ZONE_SCOPE_RE.search(raw)
        if zm:
            zone_scope = zm.group(1)
        name = _LAW_CITE_RE.sub("", raw).strip(" ·ㆍ,")
        name = _ZONE_SCOPE_RE.sub("", name).strip(" ·ㆍ,")
        # ※변이 생존(설명 가능): 실조례에서 2자 미만 항목명이 관측된 적이 없어 **도달 불가**다.
        #   정규식이 느슨해지거나 이상한 조례가 들어올 때를 위한 방어로 남긴다(락 추가 안 함).
        if len(name) < 2:
            continue
        out.append({
            "no": int(m.group(1)),
            "name": name,
            "value": int(m.group(4)),
            "zone_scope": zone_scope,
        })
    return out


def classify_article(article_title: str | None) -> tuple[str, str, str]:
    """조제목 → (condition_key, kind, direction).

    direction: 'relax'(완화 추정) | 'strengthen'(강화 — 상향 여지 아님)
    kind:      'site' | 'use' | 'unknown'
    """
    title = (article_title or "").strip()
    direction = "strengthen" if any(t in title for t in _STRENGTHEN_TOKENS) else "relax"
    for keywords, key, kind in _ARTICLE_RULES:
        if any(k in title for k in keywords):
            return key, kind, direction
    return "unclassified", "unknown", direction


def match_site_conditions(
    conditional_limits: Any, districts: Any
) -> dict[str, Any]:
    """조건부 값 × 부지 designation → 매칭 결과.

    Returns:
        `{"matched": [...], "unmatched_site": [...], "undecidable": [...], "applied": False}`

        · matched      — 부지 조건이 **실제로 충족**된 것(designation 으로 확인)
        · unmatched_site — 부지 조건이지만 이 필지는 해당 없음
        · undecidable  — **사유가 셋으로 갈린다**(한 갈래를 전체 라벨로 쓰지 않는다):
                         ①강화 조항이라 상향 여지가 아님 ②건축물 용도·연혁 조건이라
                         설계가 정해져야 판정 가능 ③**조문 나열을 읽지 못함**
                         (`decision_absent=SOURCE_UNAVAILABLE` — 사용자가 아니라
                         우리 자료의 결함이다).
                         ★2026-09-05 실측: 이 docstring 이 ②만 적고 있었고, 화면도
                           같은 문장을 하드코딩해 ①③까지 «설계를 정하세요»로 번역했다.
        ★`applied: False` — 후보일 뿐 적용값이 아니다(#704 `conditional_ceiling` 과 같은 계약).
    """
    rows = [d for d in (districts if isinstance(districts, (list, tuple)) else [])]
    names = [_norm(d) for d in rows]
    has_growth_plan = any(is_growth_management_plan(d) for d in rows)

    out: dict[str, list[dict[str, Any]]] = {
        "matched": [], "unmatched_site": [], "undecidable": [],
    }
    for item in conditional_limits or []:
        if not isinstance(item, dict):
            continue
        key, kind = item.get("condition_key"), item.get("condition_kind")
        if item.get("direction") == "strengthen":
            # 강화 조항은 상향 여지가 아니다 — 매칭 대상에서 제외하고 그대로 알린다.
            out["undecidable"].append({**item, "why": "강화 조항 — 상향 여지가 아님"})
            continue
        if kind != "site":
            out["undecidable"].append({
                **item,
                "why": "건축물 용도·연혁 조건 — 설계가 정해져야 판정 가능",
            })
            continue
        if key == "designated_district":
            # ★이 조는 **나열형**이라 항목마다 값이 다르다 — 조각이 집은 `item["value"]` 하나로
            #   판정하면 틀린 수치를 낸다. 나열을 실제로 읽었을 때만 판정한다.
            # ★★부지는 **여러 지구에 동시에 속한다**(실측: 필지당 designation 8~20건).
            #   첫 매칭에서 멈추면 나머지가 조용히 사라진다 — 맞는 것을 **전부** 낸다.
            resolved = _match_district_options(item, names)
            out[resolved["_bucket"]].extend(resolved["rows"])
            continue
        if _site_condition_holds(key, item, names, has_growth_plan):
            out["matched"].append(item)
        else:
            out["unmatched_site"].append(item)

    return {**out, "applied": False}


def _match_district_options(item: dict[str, Any], names: list[str]) -> dict[str, Any]:
    """`그 밖에 용도지구·구역 등` — 나열 항목 × 부지 designation. 맞는 것을 **전부** 낸다.

    세 갈래로만 답한다(**모르는 것을 아는 척하지 않는다**):

    · 나열을 못 읽었다      → `undecidable` (종전과 같은 보수적 기각, **사유를 명시**)
    · 읽었고 맞는 항목 있다  → `matched` — **맞는 항목 전부**를 각자의 값과 함께(조각 값 아님)
    · 읽었고 맞는 항목 없다  → `unmatched_site` — 이제 **전체 목록을 봤으므로** 신뢰할 수 있다

    ★★왜 전부인가 — 첫 매칭에서 멈추면 **임의로 하나를 고르는 것**이 된다.
      필지는 흔히 designation 을 8~20건 갖고(실측: 오산 내삼미동 20건), 하필 이 조문은
      **항목 순서가 값과 무관**하다(오산 제46조: 40·30·30·60·80). 실증한 결함:
      취락지구(40%)+자연공원(60%) 부지에서 **자연공원 60%가 사라졌다**(입력 순서와 무관 —
      순회가 부지 지정이 아니라 조문 번호 순이므로).
    ★겹칠 때 **어느 것이 적용되는지는 우리가 정하지 않는다** — 용도지구 경합의 우선순위는
      법·조례가 정하고 우리는 그 판단 근거를 갖고 있지 않다. 전부 후보로 내고 겹침을 알린다
      (`applied: False` 는 그대로 — 보이되 적용하지 않는다).
    """
    options = item.get("district_options") or []
    if not options:
        # ★`_bucket="undecidable"` 도 자체 어휘였다 — 닫힌 코드를 병기한다.
        #   조문을 못 읽은 것이므로 **원천 문제**(사용자가 할 수 있는 게 없다).
        return {"_bucket": "undecidable", "rows": [{
            **item,
            "why": "조문 나열 항목을 읽지 못함 — 어느 지구·구역인지 가릴 수 없어 판정 보류",
            "decision_absent": SOURCE_UNAVAILABLE,
        }]}

    zone = item.get("zone_type") or None
    hits: list[dict[str, Any]] = []
    for opt in options:
        name = (opt.get("name") or "").strip()
        # ※변이 생존(설명 가능): 실조례 항목명은 전부 3자 이상이라 **도달 불가**다.
        #   짧은 이름은 `name in n` 부분일치가 과하게 넓어지므로 방어로 둔다.
        if len(name) < 3:
            continue
        # ★부분일치 금지 규율(#703)의 올바른 방향: **조례가 적은 구역명 전체**가 부지 지정명
        #   안에 나타나야 한다(`취락지구` ⊂ `자연취락지구` = 하위유형이므로 참).
        #   반대 방향은 금지 — 서로 다른 제도가 접두를 공유할 때 엉뚱한 제도를 집는다.
        hit = next((n for n in names if name in n), None)
        if not hit:
            continue
        # ★수도권정비계획법 권역은 국계법 용도지구·구역이 아니다 — 공용 SSOT 로 배제한다.
        if any(m in hit for m in METRO_REGIME_NAMES):
            continue
        # 항목이 용도지역을 한정하면(`자연녹지지역에 지정된 경우`) 그 지역일 때만 성립.
        scope = opt.get("zone_scope")
        if scope and zone and scope != zone:
            continue
        hits.append((opt, hit))

    if not hits:
        return {"_bucket": "unmatched_site", "rows": [{
            **item,
            # ★조각이 집었던 값을 지운다 — 해당 없다고 판정한 마당에 그 값을 달고 다니면
            #   나중 소비처가 그것을 이 부지의 값으로 읽는다.
            "value": None,
            "why": (
                f"조문 나열 {len(options)}개 항목 중 이 부지의 지정과 맞는 것이 없음"
                f"({', '.join((o.get('name') or '')[:12] for o in options[:5])})"
            ),
        }]}

    overlap = len(hits)
    rows: list[dict[str, Any]] = []
    for opt, hit in hits:
        why = f"부지가 '{hit}' 로 지정됨 — 조문 {opt.get('no')}호"
        if overlap > 1:
            # ★겹침을 **숨기지 않는다**. 값이 서로 다르면 사용자가 그 사실을 알아야 한다.
            others = " · ".join(
                f"{o.get('name')} {o.get('value')}%" for o, _h in hits if o is not opt
            )
            why += (
                f" · ★이 부지는 {overlap}개 지구에 걸친다(함께: {others}) — "
                "경합 시 우선순위는 확인 필요"
            )
        rows.append({
            **item,
            # ★조각이 집은 값이 아니라 **이 항목의 값**으로 덮는다.
            "value": opt.get("value"),
            "matched_district": hit,
            "matched_option": opt.get("name"),
            "overlap_count": overlap,
            "why": why,
        })
    return {"_bucket": "matched", "rows": rows}


def _site_condition_holds(
    key: str | None, item: dict[str, Any], names: list[str], has_growth_plan: bool
) -> bool:
    """부지 designation 으로 이 조건이 충족되는가.

    ★`성장관리방안`(조례 구 명칭)은 국토계획법 **성장관리계획구역** 지정으로 판정한다 —
      수도권 `성장관리권역` 은 `is_growth_management_plan` 이 이미 배제한다(PR #703).
    """
    if key == "growth_management_plan":
        return has_growth_plan
    if key == "fire_district":
        return any("방화지구" in n for n in names)
    if key == "landscape_district":
        return any("경관지구" in n for n in names)
    # ★`designated_district` 는 여기 오지 않는다 — 나열형이라 `_match_district_options` 가
    #   **항목별 값**으로 판정한다(이 함수는 값이 하나인 조건만 다룬다).
    #   종전 주석이 *"나중에 나열 항목을 가를 수 있게 되면 고칠 자리가 여기"* 라고 적어 뒀는데,
    #   실제로 가를 수 있게 되니 **고칠 자리는 여기가 아니었다**(값이 조건마다 달라서).
    return False
