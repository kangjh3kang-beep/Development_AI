/**
 * ★필지 중복제거가 **주소 문자열**로 되어 있었다 — 두 방향으로 동시에 틀렸다.
 *
 * 【무엇이 있었나 · `GlobalAddressSearch` 4곳 + `SatongMapShell` 2곳】
 *
 *     ① 접힘  같은 동 단위 주소를 공유하는 **서로 다른 필지**가 한 건으로 사라진다
 *     ② 중복  **같은 필지**가 표기 차이로 두 건이 된다 — 그리고 보강이 표기를 수렴시킨 뒤에도
 *             **다시 접는 곳이 없었다**
 *
 * 【네 모집단 — 같은 실행에서 **다른 결과**가 나와야 한다】
 *   A 같은 동 주소 + 서로 다른 유효 PNU  → **안 접힌다**(2건)
 *   B 같은 필지 + 표기 두 가지(보강 수렴) → **접힌다**(1건)
 *   C 앵커 없음(PNU·주소 모두 없음)       → **보존**(무음 손실 금지)
 *   D 오염 PNU(`store-rep-<주소>`)         → 정체성이 **되지 않는다**(주소로 떨어진다)
 *
 * ★D 가 없으면 A 만으로 부족하다 — 가짜 PNU 끼리 값이 다르면 «가짜를 그냥 키로 써도» A 는
 *   통과한다(`#941` 이 같은 함정을 실측했다).
 */
import { describe, expect, it } from "vitest";
import {
  dedupeByIdentity, entryIdentityKey, isDuplicateOf, isSameParcel, mergeKeepingIncomingFirst,
} from "@/lib/parcel-entry-identity";

/** 같은 동, 서로 다른 필지 — 실제 신고 사례(오산 내삼미동 77필지)의 축소판. */
const DONG = "경기도 오산시 내삼미동";
const A1 = { pnu: "4137010200101140000", fullAddress: DONG };
const A2 = { pnu: "4137010200104670000", fullAddress: DONG };
/** 같은 필지, 표기 두 가지 — 백엔드가 짧은 주소를 자동 해소하기 전/후. */
const SHORT = { pnu: null, fullAddress: "상도동 211-204" };
const LONG = { pnu: null, fullAddress: "서울특별시 동작구 상도동 211-204" };
/** `#941` 라이브 실측 오염값 — 생산자가 주소로 합성하므로 **주소가 같으면 값도 같다**. */
const DIRTY1 = { pnu: `store-rep-${DONG}`, fullAddress: DONG };
const DIRTY2 = { pnu: `store-rep-${DONG}`, fullAddress: DONG };

describe("네 모집단이 서로 다른 결과를 낸다", () => {
  it("A 같은 동 주소 + 서로 다른 유효 PNU → **안 접힌다**", () => {
    const out = dedupeByIdentity([A1, A2]);
    expect(out).toHaveLength(2);
    // 공허 진리 가드 — 주소가 실제로 같은가(다르면 이 케이스가 아무것도 안 본다)
    expect(A1.fullAddress).toBe(A2.fullAddress);
  });

  it("B 같은 필지 · 표기 두 가지 → 보강이 수렴시킨 **뒤** 접힌다", () => {
    // 보강 전: 주소 문자열이 다르므로 두 건 — 이것이 정상이다(아직 같은 필지인지 모른다).
    expect(dedupeByIdentity([SHORT, LONG])).toHaveLength(2);
    // 보강 후: 백엔드가 짧은 주소를 전체 주소로 되돌려 준다 → 같은 필지로 드러난다.
    const enriched = [{ ...SHORT, fullAddress: LONG.fullAddress }, LONG];
    expect(dedupeByIdentity(enriched)).toHaveLength(1);
  });

  it("C 앵커 없음 → **보존**한다(하나로 접으면 데이터 손실이다)", () => {
    const blanks = [{ pnu: null, fullAddress: "" }, { pnu: null, fullAddress: "   " }];
    expect(entryIdentityKey(blanks[0])).toBeNull();
    expect(dedupeByIdentity(blanks)).toHaveLength(2);
  });

  it("D 오염 PNU 는 정체성이 되지 않는다 — 주소로 떨어진다", () => {
    // 오염값이 키가 되면 `pnu:store-rep-…` 두 개가 같아 접히는데, 그건 **우연히** 맞다.
    // 진짜 위험은 오염값이 **다른 필지에서 같아지는** 것이므로 키 형태를 직접 못 박는다.
    expect(entryIdentityKey(DIRTY1)).toBe(`addr:${DONG}`);
    expect(entryIdentityKey(DIRTY1)).not.toContain("store-rep");
    // 그리고 오염 PNU 를 가진 **서로 다른 필지**는 주소가 같으면 구별할 수단이 없다 —
    // 이것은 정직한 한계이고, 접히는 것이 맞다(앵커가 주소뿐이므로).
    expect(dedupeByIdentity([DIRTY1, DIRTY2])).toHaveLength(1);
  });
});

describe("병합 — 업로드분 우선 · 기존 중 같은 필지만 뺀다", () => {
  it("★같은 필지는 한 번만, 다른 필지는 둘 다 (두 모집단 동시)", () => {
    const merged = mergeKeepingIncomingFirst([A1, LONG], [A2, { ...LONG }]);
    // A2 는 A1 과 **다른 필지**라 남는다 · LONG 은 **같은 필지**라 안 남는다
    expect(merged).toHaveLength(3);
    expect(merged.filter((m) => m.fullAddress === LONG.fullAddress)).toHaveLength(1);
    expect(merged.filter((m) => m.fullAddress === DONG)).toHaveLength(2);
  });

  it("★앵커 없는 기존 행은 병합에서 살아남는다(무음 손실 금지)", () => {
    const merged = mergeKeepingIncomingFirst([A1], [{ pnu: null, fullAddress: "" }]);
    expect(merged).toHaveLength(2);
  });

  it("isDuplicateOf — 앵커가 없으면 «중복 아님»", () => {
    expect(isDuplicateOf(A1, [A2])).toBe(false);
    expect(isDuplicateOf(A1, [A1])).toBe(true);
    expect(isDuplicateOf({ pnu: null, fullAddress: "" }, [{ pnu: null, fullAddress: "" }])).toBe(false);
  });
});

describe("isSameParcel — 중복제거 키 동일성과 **다른** 판정이다", () => {
  it("★둘 다 유효 PNU 면 PNU 가 결정한다 — 주소가 같아도 다른 필지다", () => {
    expect(isSameParcel({ pnu: A1.pnu, address: DONG }, { pnu: A2.pnu, address: DONG })).toBe(false);
    expect(isSameParcel({ pnu: A1.pnu, address: DONG }, { pnu: A1.pnu, address: "다른 표기" })).toBe(true);
  });

  it("★한쪽이 PNU 를 안 가지면 주소로 판단한다(유령 패널 결함 R1 보존)", () => {
    // 지도 피처는 PNU 를 갖고 선택 목록의 시드 필지는 못 갖는 것이 **정상**이다.
    // 키 동일성으로 바꾸면 여기서 안 만나 삭제된 필지의 패널이 안 닫힌다.
    expect(isSameParcel({ pnu: A1.pnu, address: DONG }, { pnu: null, address: DONG })).toBe(true);
  });

  it("★빈 주소는 «판단 불가» 이지 «같음» 이 아니다", () => {
    expect(isSameParcel({ pnu: null, address: "" }, { pnu: null, address: "" })).toBe(false);
  });

  it("★오염 PNU 는 앵커로 안 쓰인다 — 주소 분기로 떨어진다", () => {
    // 오염값이 서로 **다르면** 옛 규칙은 주소로 떨어져 참이었다. 새 규칙도 참이다(무회귀).
    expect(isSameParcel({ pnu: "store-rep-a", address: DONG }, { pnu: "store-rep-b", address: DONG })).toBe(true);
    // 그러나 **유효 PNU 가 서로 다르면** 이제 거짓이다 — 이것이 고친 것이다.
    expect(isSameParcel({ pnu: A1.pnu, address: DONG }, { pnu: A2.pnu, address: DONG })).toBe(false);
  });
});
