import { describe, expect, it } from "vitest";

import { isValidPnu, jibunFromPnu, parcelDedupKey, parcelDisplayAddress } from "./pnu";

describe("jibunFromPnu", () => {
  it("일반 지번 본번-부번을 파싱한다", () => {
    // 4148025329 + 1(일반) + 0123(본번) + 0004(부번)
    expect(jibunFromPnu("4148025329101230004")).toBe("123-4");
  });

  it("부번이 0이면 본번만 낸다", () => {
    expect(jibunFromPnu("4148025329101230000")).toBe("123");
  });

  it("산 지번은 접두 '산'을 붙인다", () => {
    expect(jibunFromPnu("4148025329201230004")).toBe("산123-4");
  });

  it("★본번이 0이면 지번을 지어내지 않는다(무날조)", () => {
    expect(jibunFromPnu("4148025329100000000")).toBeNull();
  });

  it("형식이 아니면 null", () => {
    for (const bad of ["", null, undefined, "123", "41480253291012300041", "abcdefghijklmnopqrs"]) {
      expect(jibunFromPnu(bad as string)).toBeNull();
    }
    expect(isValidPnu("4148025329101230004")).toBe(true);
  });
});

describe("parcelDisplayAddress", () => {
  it("동 단위 주소에 지번을 붙여 **구분 가능**하게 만든다", () => {
    const a = parcelDisplayAddress("경기도 오산시 내삼미동", "4148025329101230004");
    const b = parcelDisplayAddress("경기도 오산시 내삼미동", "4148025329101230005");
    expect(a).toBe("경기도 오산시 내삼미동 123-4");
    expect(b).toBe("경기도 오산시 내삼미동 123-5");
    // ★두 라벨이 **달라야** 한다 — 같으면 사용자가 어느 필지를 고르는지 알 수 없다.
    expect(a).not.toBe(b);
  });

  it("주소에 이미 지번이 있으면 중복 표기하지 않는다", () => {
    expect(parcelDisplayAddress("경기도 오산시 내삼미동 123-4", "4148025329101230004"))
      .toBe("경기도 오산시 내삼미동 123-4");
  });

  it("PNU 가 없으면 주소를 그대로 쓴다", () => {
    expect(parcelDisplayAddress("경기도 오산시 내삼미동", null)).toBe("경기도 오산시 내삼미동");
  });
});

describe("parcelDedupKey — 프로덕션 버그의 회귀 잠금", () => {
  it("★같은 동의 서로 다른 필지는 **접히지 않는다**(77 → 1 버그)", () => {
    // 실제 신고: '현재 프로젝트 필지 불러오기 (77)' 인데 1건만 들어왔다.
    const parcels = Array.from({ length: 77 }, (_, i) => ({
      pnu: `41480253291${String(1000 + i).padStart(4, "0")}0000`,
      address: "경기도 오산시 내삼미동", // ← 77개가 전부 같은 동 단위 주소
    }));
    const keys = new Set(parcels.map((p) => parcelDedupKey(p)));
    expect(keys.size).toBe(77);
  });

  it("★대조군 — 주소로만 키를 잡으면 1건으로 접힌다(옛 동작)", () => {
    const parcels = Array.from({ length: 77 }, () => ({ address: "경기도 오산시 내삼미동" }));
    const keys = new Set(parcels.map((p) => parcelDedupKey(p)));
    // PNU 가 없으면 주소로 떨어지는 것이 맞다 — 이 케이스는 접히는 게 정상이다.
    expect(keys.size).toBe(1);
  });

  it("같은 PNU 는 주소 표기가 달라도 한 건으로 본다", () => {
    const a = parcelDedupKey({ pnu: "4148025329101230004", address: "오산시 내삼미동 123-4" });
    const b = parcelDedupKey({ pnu: "4148025329101230004", address: "경기도 오산시 내삼미동" });
    expect(a).toBe(b);
  });

  it("★키를 만들 수 없으면 null — 호출부가 '중복'으로 접지 않게 한다", () => {
    expect(parcelDedupKey({})).toBeNull();
    expect(parcelDedupKey({ pnu: "  ", address: "  " })).toBeNull();
  });

  it("주소 공백 차이는 같은 것으로 본다", () => {
    expect(parcelDedupKey({ address: "오산시  내삼미동 " })).toBe(parcelDedupKey({ address: "오산시 내삼미동" }));
  });
});
