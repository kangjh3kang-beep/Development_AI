/**
 * 주소 입력 표면(`GlobalAddressSearch`)의 **필지 정체성 · 중복제거** — 한 곳.
 *
 * ## 왜 생겼나 (2026-09-02)
 *
 * 엑셀 토지조서 업로드·검색 추가·지도 다중선택이 **전부 `fullAddress` 문자열 비교**로
 * 중복을 판정했다. 그래서 두 방향으로 동시에 틀렸다:
 *
 *     ① 접힘  같은 동 단위 주소를 공유하는 **서로 다른 필지**가 한 건으로 사라진다
 *             (`경기도 오산시 내삼미동` ×77 → 1건. `lib/pnu.ts` 가 생긴 바로 그 버그)
 *     ② 중복  **같은 필지**가 표기 차이로 두 건이 된다
 *             (`상도동 211-204` vs `서울특별시 동작구 상도동 211-204`)
 *
 * ★②가 더 조용하다 — 백엔드가 짧은 주소를 자동 해소해 **전체 시군구 주소로 되돌려 주기**
 *   때문에(`enrichParcels`), 병합 시점에는 다른 문자열이던 두 행이 보강 후 **바이트 동일**로
 *   수렴한다. 그런데 **수렴 후 다시 중복제거하는 곳이 없었다.** 즉 «중복제거를 했다» 는
 *   사실이 «중복이 없다» 를 보장하지 못했다.
 *
 * ## 규칙
 *
 * 정체성은 `parcelDedupKey`(=`lib/pnu.ts`) **하나만** 쓴다 — 유효 PNU 우선, 없으면 주소,
 * 둘 다 없으면 `null`. ★`null` 은 **"중복 아님"** 이다: 앵커 없는 행을 하나로 접으면
 * 데이터 손실이다(무음 손실 금지).
 *
 * ★이 규칙을 호출부에 인라인으로 두지 않는 이유: 규칙이 두 벌이면 한쪽만 고쳐진다.
 *   `#941` 이 정확히 그것으로 값을 치렀다(패널은 인라인, 테스트는 재구현 → 같은 결함이
 *   양쪽에 있고 초록).
 */
import { normalizePnu, parcelDedupKey } from "@/lib/pnu";

/** 이 모듈이 다루는 최소 형상 — 컴포넌트의 `AddressEntry` 를 구조적으로 받는다. */
export type ParcelIdentityInput = {
  pnu?: string | null;
  fullAddress?: string | null;
};

/**
 * 입력 행의 정체성 키. 앵커(유효 PNU·주소)가 없으면 `null`.
 * ★`fullAddress` → `address` 로만 옮기고 **판정은 `parcelDedupKey` 가 한다**(구현 두 벌 금지).
 */
export function entryIdentityKey(e: ParcelIdentityInput): string | null {
  return parcelDedupKey({ pnu: e.pnu, address: e.fullAddress });
}

/**
 * 같은 배열 안의 중복을 제거한다(앞의 것을 남긴다).
 * ★키가 `null` 인 행은 **전부 보존**한다 — 앵커가 없는 것은 "같다" 고 말할 수 없다.
 */
export function dedupeByIdentity<T extends ParcelIdentityInput>(entries: readonly T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const e of entries) {
    const k = entryIdentityKey(e);
    if (k === null) { out.push(e); continue; }
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(e);
  }
  return out;
}

/** `candidate` 가 `existing` 안에 **이미 있는 필지**인가. 앵커 없으면 `false`(중복 아님). */
export function isDuplicateOf(candidate: ParcelIdentityInput, existing: readonly ParcelIdentityInput[]): boolean {
  const k = entryIdentityKey(candidate);
  if (k === null) return false;
  return existing.some((e) => entryIdentityKey(e) === k);
}

/**
 * `incoming`(새로 올린 것)을 앞에 두고, `existing` 중 **incoming 에 없는 것만** 뒤에 붙인다.
 * incoming 내부 중복도 함께 정리한다.
 */
export function mergeKeepingIncomingFirst<T extends ParcelIdentityInput>(
  incoming: readonly T[],
  existing: readonly T[],
): T[] {
  const head = dedupeByIdentity(incoming);
  const keys = new Set(head.map(entryIdentityKey).filter((k): k is string => k !== null));
  const tail = existing.filter((a) => {
    const k = entryIdentityKey(a);
    return k === null || !keys.has(k);   // 앵커 없는 기존 행은 남긴다(무음 손실 금지)
  });
  return [...head, ...tail];
}

/**
 * 두 필지가 **같은 필지인가** — 중복제거 키 동일성과는 **다른 판정**이다.
 *
 * ## 왜 `entryIdentityKey(a) === entryIdentityKey(b)` 로 하지 않나
 *
 * 한쪽만 PNU 를 갖고 있으면 키가 `pnu:…` 와 `addr:…` 로 갈려 **절대 안 만난다.**
 * 그런데 이 판정이 필요한 자리(지도 상세 패널 닫기·카드↔지도 포커스)는 **한쪽은 지도
 * 피처(PNU 보유), 다른 쪽은 선택 목록(시드 필지는 PNU 미확보)** 인 경우가 정상이다.
 * 키 동일성으로 바꾸면 **삭제한 필지의 상세 패널이 안 닫히는** 유령 패널 결함(R1 HIGH)이
 * 되살아난다.
 *
 * ## 규칙
 *
 *     둘 다 유효 PNU  → PNU 가 결정한다 (다르면 **다른 필지**)
 *     한쪽이라도 없음  → 주소로 판단 (빈 주소는 판단 불가 → false)
 *
 * ★종전 인라인 규칙 `(a.pnu && b.pnu === a.pnu) || b.address === a.address` 는
 *   **`||` 때문에 PNU 가 서로 달라도 주소만 같으면 참**이었다. 즉 같은 동 단위 주소를
 *   공유하는 **서로 다른 필지**를 같다고 판정했다 — 필지 A 를 지우면 필지 B 의 패널이 닫히고,
 *   카드 A 를 누르면 지도가 B 로 간다. 그리고 `a.pnu` 는 **유효성을 안 봐서**, `#941` 이 실측한
 *   오염 PNU(`store-rep-<주소>`)면 truthy 인 채 비교가 어긋나 곧장 주소 분기로 떨어졌다.
 */
export function isSameParcel(
  a: { pnu?: string | null; address?: string | null },
  b: { pnu?: string | null; address?: string | null },
): boolean {
  const pa = normalizePnu(a.pnu == null ? "" : String(a.pnu));
  const pb = normalizePnu(b.pnu == null ? "" : String(b.pnu));
  if (pa && pb) return pa === pb;
  const aa = (a.address || "").trim().replace(/\s+/g, " ");
  const ab = (b.address || "").trim().replace(/\s+/g, " ");
  return aa !== "" && aa === ab;
}
