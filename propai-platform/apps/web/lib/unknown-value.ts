/**
 * 미지값 경계 정규화 — 조회표가 「안심 기본값」으로 접히지 않게 한다.
 *
 * ## 이 파일이 있는 이유 (실측 근거)
 *
 * 화면 여러 곳이 `표[서버값] ?? 표.안심키` 형태로 미지값을 처리했다. 그 폴백이 **유효값**이라
 * 조용하다 — 「모른다」와 「안전하다고 관측됐다」가 **화면에서 구별되지 않는다.**
 *
 * 실측 2026-08-27:
 *   · `statusColors[c.status] || statusColors.safe` — 미지 status 가 **초록**으로 떨어졌다.
 *     같은 표에 `danger`(빨강)가 실재하는데 그게 가려진다. 생산자는 검증 0의 LLM JSON
 *     (`ai-analyze-client.ts` 가 `JSON.parse(...) as T` 로 캐스팅).
 *   · `VERDICT_META[result.verdict] || VERDICT_META.warn` — LLM 이 `"FAIL"` 을 뱉으면
 *     **"오류 발견"이 "주의"로 강등**됐다. 백엔드에 정규화가 없다(실측 0건 · 대조군 15행 생존).
 *
 * ## 처방의 형태
 *
 * > **「모름」을 그 타입의 유효값으로 표현하는 순간 결함이 생긴다.**
 *
 * 그래서 `resolveKnown` 은 값이 아니라 **판별 유니온**을 돌려준다. 호출부는 `known` 을
 * 보지 않고는 값을 꺼낼 수 없으므로, 「모름」 처리를 **빠뜨릴 수 없다**(tsc 가 강제한다).
 *
 * 대소문자·공백 흔들림은 **강등이 아니라 회복**이 맞다 — `"FAIL"` 은 모르는 값이 아니라
 * 표기가 흔들린 `fail` 이다. 단 비교 기준은 **표의 키에서 파생**한다(소문자 표라고
 * 하드코딩하면 대문자 키를 쓰는 표에서 조용히 틀린다).
 */

/**
 * 검증되지 않은 입력을 조회용 문자열로 — **여기서 절대 던지지 않는다.**
 * ★`String(raw)` 는 `toString` 이 던지는 객체에서 TypeError 를 낸다. 이 함수는 **미지값을
 *   안전하게 다루는 것이 임무**인데 그 입력에서 죽으면 화면이 통째로 사라진다
 *   (LegacyLedgerTable 이 같은 자리에 적어 둔 것: "백엔드가 네 번째 verdict 를 내면
 *   undefined.cls 로 패널 전체가 죽는다").
 */
function toProbeText(raw: unknown): string {
  if (typeof raw === "string") return raw.trim();
  if (raw == null) return "";
  try {
    return String(raw).trim();
  } catch {
    return "";
  }
}

/** 조회 결과. `known` 을 좁히지 않으면 `value` 를 쓸 수 없다(미지 처리 누락 방지). */
export type Resolved<T> =
  | { readonly known: true; readonly value: T; readonly key: string }
  | { readonly known: false; readonly value: null; readonly key: string | null };

/**
 * 표에서 키를 찾되, 못 찾으면 **표의 어떤 값도 돌려주지 않는다**.
 *
 * @param table 조회표(자기 소유 키만 본다 — 프로토타입 오염 차단)
 * @param raw   서버·LLM에서 온 검증되지 않은 값
 * @returns 정확일치 → known · 대소문자/공백만 다름 → known(회복) · 그 외 → **known:false**
 */
export function resolveKnown<K extends string, T>(
  table: Readonly<Record<K, T>>,
  raw: unknown,
): Resolved<T> {
  // ★비문자열도 원값을 버리지 않는다 — 이 파일이 「진단 불가는 그 자체로 장애다」라고
  //   써 놓고 raw=3 일 때 key 를 null 로 버리면 그 선언과 어긋난다.
  const text = toProbeText(raw);
  if (text === "") return { known: false, value: null, key: null };

  if (Object.prototype.hasOwnProperty.call(table, text)) {
    return { known: true, value: table[text as K] as T, key: text };
  }

  // 표기 흔들림 복원 — 기준을 표의 키에서 파생한다(소문자 가정 금지).
  const lowered = text.toLowerCase();
  for (const k of Object.keys(table)) {
    if (k.toLowerCase() === lowered) {
      return { known: true, value: table[k as K] as T, key: k };
    }
  }

  // ★여기서 표의 '안심' 항목을 돌려주면 이 파일이 막으려는 그 결함이 된다.
  return { known: false, value: null, key: text };
}

/**
 * 미지 원값을 화면에 실을 때의 길이 제한.
 * 사유를 표면까지 싣되(진단 불가는 그 자체로 장애다) 레이아웃을 깨지 않는다.
 */
export function shortenUnknownKey(key: string | null, max = 24): string | null {
  if (!key) return null;
  if (key.length <= max) return key;
  // 코드유닛으로 자르면 서로게이트 페어(이모지)가 깨진다 — 코드포인트로 자른다.
  return `${[...key].slice(0, max).join("")}…`;
}
