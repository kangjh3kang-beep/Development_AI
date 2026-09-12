/**
 * 레이어 조회 응답의 **사유**를 사용자 문구로 옮긴다 — 「없다」와 「못 봤다」를 가른다.
 *
 * ## 왜 (실측 2026-09-12)
 *
 * 사용자가 경매 레이어를 켜면 화면이 **「경매 무자료」** 라고 말한다
 * (`SatongMultiMap.tsx` 의 `auctionNote || (auctionCount ? … : "경매 무자료")`).
 * 그런데 라이브 서버는 이렇게 답하고 있었다:
 *
 *     GET /api/v1/auction/search?page_size=60
 *     → {"items":[],"total":0,"page":1,"page_size":60,"data_source":"unavailable"}
 *
 * **없는 것이 아니라 못 본 것**인데 화면은 없다고 말한다.
 *
 * ★★**「`data_source` 소비처 0건」은 거짓이었다**(2026-09-12 독립 렌즈 M-3 · 내가 재확인).
 *   `origin/main` 프론트에 **18파일**이 그 필드를 읽는다. 참인 것은 **좁힌 명제**뿐이다 —
 *   **`SatongMapShell.tsx` 안에서 0건**(재측정: 그 파일만 세면 0 · 전체는 18).
 *   ***범위를 안 적은 「0건」은 거짓이 된다*** — 그리고 그 거짓이 이 파일 주석에 실려 있었다.
 *
 * ★★그리고 **같은 토큰을 반대 뜻으로 읽는 표면이 이미 배포돼 있다**(M-2):
 *   `components/operations/market/DataSourceBadge.tsx:20` 이 `unavailable` 을
 *   **「데이터 없음」** 으로 렌더한다 — 여기서 「못 봤다」로 읽는 것과 **정반대**다.
 *   ★어휘 SSOT 통합은 **이 PR 범위 밖**으로 뒀다(그 배지는 다른 화면의 계약이고,
 *     묶으려면 양쪽 소비처를 다 태워야 한다). **부채로 남긴다** — 아래 `it.todo` 참조.
 *
 * ★빠진 것이 「정직 표기」 전부가 아니라 **한 조건뿐**이었다. 경매 경로는 이미
 * 레이어 꺼짐·앵커 대기·미로그인 **세 조건**에 정직한 노트를 낸다. 분양 `catch` 도
 * *"분양: 조회 실패 // 무자료와 실패를 구분(정직원칙)"* 이라 적어 뒀다.
 * ***옳은 패턴이 바로 옆에 있었고, 서버가 답한 경우만 빠져 있었다***(형제 훑기).
 *
 * ## ★계약 (2026-09-12 2차 정정 — 독립 렌즈가 **전제를 무너뜨렸다**)
 *
 * 초판은 `data_source: "unavailable"` 을 **「못 봤다」로 단정**했다. **틀렸다** —
 * `onbid_client.py` 는 그 토큰을 **네 갈래**에 쓴다:
 *   `:275` 인증키 미설정 · `:301` 응답 오류 ·
 *   **`:308` 「온비드 응답 무자료(해당 조건의 공고 없음)」** · `:317` 호출 실패
 * ★**308 은 조회에 성공하고 정말 없는 경우**다. 거기서 「데이터원 조회 불가」라고 말하면
 * ***「없다」를 「못 봤다」로 뒤집는 것*** — 내가 고치려던 결함의 거울상이다.
 *
 * ★가르는 정보는 **이미 있었다**: `_unavailable(reason)` 이 `reason` 을 실어 보내는데
 * `auction_service.search()` 가 **버리고 있었다**. 그래서 이 PR 은 백엔드에서 그 두 줄을
 * 되살리고, 여기서는 **서버의 사유를 그대로 쓴다**(형제 POI 가 이미 그렇게 한다 —
 * `SatongMultiMap.tsx:3193 setPoiNote(poiPayload.reason || "POI 조회 불가")`).
 *
 * 판정 순서:
 *   ①`reason`/`note` 가 있으면 **그대로** — 서버가 네 갈래를 자기 말로 구별해 준다
 *   ②`available === false` → 「조회 불가」
 *   ③`subscriber_only` → 「구독 필요」
 *   ④`CONFIRMED_QUERY_SOURCES` → `""`(화면은 종전대로 「무자료」)
 *   ⑤**그 밖(사유 없는 `unavailable` 포함)** → 「확인 불가」 — ★**원인을 단정하지 않는다**
 *
 * ★「없음」을 말하려면 **확인 어휘를 닫힌 집합으로** 가져야 한다. 실패 어휘만 닫으면
 * **모름이 성공으로 샌다** — 그래서 ④가 닫힌 집합이고 ⑤가 기본값이다.
 */

/** 사유를 갖는 조회 응답의 최소 계약(서버 스키마 전체를 끌어오지 않는다). */
export interface LayerSourceEnvelope {
  /** 분양(`/presale/nearby`)이 쓰는 형태. */
  available?: boolean | null;
  /** 경매(`/auction/search`)가 쓰는 형태. 어휘는 백엔드 파생(11종). */
  data_source?: string | null;
  /** ★서버가 **자기 말로** 적어 보낸 사유. 있으면 이것이 가장 정확하다(네 갈래를 구별한다). */
  reason?: string | null;
  /** 분양(`/presale/nearby`)이 쓰는 같은 뜻의 필드(`presale_service.py:293`). */
  note?: string | null;
}

/**
 * 「못 봤다」를 뜻하는 `data_source` 값 → 사용자 문구.
 *
 * ★**닫힌 집합이다.** 여기 없다고 «정상» 인 것이 아니다 — 아래 `CONFIRMED_QUERY_SOURCES` 를 보라.
 */
const UNSEEN_DATA_SOURCE_NOTES: Readonly<Record<string, string>> = Object.freeze({
  // ★★`unavailable` 을 **뺐다**(2026-09-12 2차 정정). 그 토큰은 네 갈래를 뭉치므로
  //   **원인을 단정할 수 없다** — 사유가 함께 오면 위 ①이 쓰고, 없으면 ⑤ 「확인 불가」다.
  //   초판은 여기 `unavailable: "데이터원 조회 불가"` 가 있었고, 그것이 **「없다」를
  //   「못 봤다」로 뒤집는** 자리였다.
  subscriber_only: "구독 필요",
});

/**
 * **실제로 그 출처를 조회했다**는 뜻의 값(닫힌 집합 · 백엔드 어휘에서 파생).
 *
 * ★이 집합에 있어야만 결과 0건을 **「무자료」로 단정**할 수 있다.
 * ★`mock`·`fallback` 은 **일부러 뺐다** — 「조회했다」가 아니라 「다른 것으로 답했다」라
 *   0건을 부재로 읽으면 안 된다(라이브 발화는 **미측정**이다).
 */
const CONFIRMED_QUERY_SOURCES: readonly string[] = Object.freeze([
  "live", "onbid_live", "molit_live", "sgis_live",
  "court_scrape", "onbid_rlst_detail", "comparable",
]);

/**
 * ★**세 번째 상태** — 조회했는지조차 모를 때.
 *
 * ★★2026-09-12 정정(독립 리뷰): 초판은 미상 `data_source` 에 **빈 문자열**을 냈고,
 *   그러면 화면이 종전대로 **「경매 무자료」** 를 말한다. 나는 그것을 «날조 금지» 로
 *   정당화했는데 **틀렸다**:
 *
 *   ***「무자료」는 중립 문구가 아니라 「주변에 없다」는 적극적 주장이다.***
 *   출처를 모르면 그 주장을 뒷받침할 측정이 없다 — 즉 그 분기는 날조를 피한 것이 아니라
 *   **다른 날조를 한 것**이다. 이 저장소가 이미 데인 형태다(미조회 부담금이 `0㎡ × 0원/㎡`
 *   로 그려져 **면제 확정 0원과 구별 불가**였던 자리 — *「모름」을 유효값으로 표현하면
 *   그 순간 관측이 된다*).
 *
 *   → 그래서 상태를 **셋**으로 만든다: 자료 있음 / **조회 실패(사유 명시)** / **확인 불가**.
 */
const UNKNOWN_SOURCE_NOTE = "확인 불가(조회 출처 미상)";

/**
 * @param label 레이어 이름(예: `"경매"`). 문구 앞에 붙는다.
 * @param res   조회 응답(부분). `null`/`undefined` 면 빈 문자열.
 * @returns 셋 중 하나 —
 *  ①`""`  : **조회했고 0건**(`available:true` 또는 확인된 출처) ⇒ 화면은 「무자료」
 *  ②`"경매: 데이터원 조회 불가"` 류 : **사유를 아는 실패**
 *  ③`"경매: 확인 불가(조회 출처 미상)"` : **조회했는지조차 모름** — 부재를 단정하지 않는다
 */
export function resolveLayerSourceNote(
  label: string,
  res: LayerSourceEnvelope | null | undefined,
): string {
  // ★★2026-09-12 — 여기도 `return ""` 이었다. 그러면 **응답 자체가 없을 때 화면이 다시
  //   「무자료」**, 즉 *"주변에 없다"* 라고 말한다 — ***바로 아래에서 방금 고친 그 결함을
  //   한 줄 위에서 그대로 하고 있었다.*** 응답이 없는 것은 「없음」의 근거가 아니라
  //   **「모름」의 가장 강한 형태**다.
  //   ★독립 리뷰가 «호출부 전수로 보니 `catch` 가 먼저 잡아 도달 불가» 라고 재 줬고, 그 관측은
  //     맞다(호출부 2곳 모두 `res` 를 받은 뒤에만 부른다). **그래도 고친다** — 도달 불가라는
  //     이유로 원칙에 어긋난 분기를 남기면, 그것이 되살아나는 날 아무도 다시 안 본다.
  //   ★**반증조건**(내 「도달 불가」 라벨에 붙인다): 204·빈 본문처럼 «성공했는데 `res` 가 없는»
  //     응답이 실재하면 이 줄이 즉시 발화한다. 그때는 이 반환이 옳은 값이다.
  if (!res) return `${label}: ${UNKNOWN_SOURCE_NOTE}`;

  // ★`available: false` 는 그 자체로 "못 봤다" 다(분양이 쓰는 형태).
  //   `undefined` 와 구별한다 — 필드가 없는 것은 "불가"가 아니다.

  // ★①**서버의 사유를 최우선**으로 쓴다 — 토큰 하나로는 못 가르는 갈래를 서버는 안다.
  //   형제 POI 가 이미 이렇게 한다(`SatongMultiMap.tsx:3193`). 내 매핑은 그 다음이다.
  //   ★초판은 이 분기가 **없어서** 서버가 「무자료(공고 없음)」라 말해도 내가
  //     「데이터원 조회 불가」로 **덮어썼다** — 정상 상태를 장애로 오독시켰다.
  const 서버사유 = res.reason ?? res.note;
  if (typeof 서버사유 === "string" && 서버사유.trim()) return `${label}: ${서버사유.trim()}`;

  // ★②분양처럼 `available` 만 주는 형태 — 참이면 **조회했고 0건**이다(무자료 단정 정당).
  // ★②`available === false` — **①에서 사유를 못 찾았을 때만** 여기 온다.
  //   ★초판은 이 검사가 ① **위에** 있어서, 분양이 `note` 로 보낸 서버 사유를
  //     「분양: 조회 불가」로 **덮어썼다** — 주석은 "사유가 없을 때만 온다"고 적혀 있었는데
  //     **코드가 그 주석과 모순**이었다. ***주석이 아니라 순서가 계약이다.***
  if (res.available === false) return `${label}: 조회 불가`;

  // ★③`available === true` — 조회했고 0건(무자료 단정 정당).
  if (res.available === true) return "";

  const src = res.data_source;
  // ★프로토타입 오염 차단 — `Object.freeze` 한 리터럴이라도 `constructor` 같은 키가
  //   truthy 로 새어 나오는 것을 막는다(이 저장소가 `MARKET_TYPE_LABELS` 에서 데인 자리).
  if (typeof src === "string" && Object.prototype.hasOwnProperty.call(UNSEEN_DATA_SOURCE_NOTES, src)) {
    return `${label}: ${UNSEEN_DATA_SOURCE_NOTES[src]}`;
  }
  // ★**조회했다고 확인된 출처일 때만** 0건을 「무자료」로 단정하게 둔다(빈 문자열).
  if (typeof src === "string" && CONFIRMED_QUERY_SOURCES.includes(src)) return "";
  // ★그 밖은 **세 번째 상태**다 — 사유를 지어내지 않으면서 **부재도 단정하지 않는다**.
  return `${label}: ${UNKNOWN_SOURCE_NOTE}`;
}
