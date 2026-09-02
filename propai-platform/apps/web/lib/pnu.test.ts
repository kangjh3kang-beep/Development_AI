import { describe, expect, it } from "vitest";

import {
  addressHasJibun,
  bcodeFromPnu,
  isJibunToken,
  joinAddressJibun,
  isValidPnu,
  jibunFromPnu,
  normalizePnu,
  parcelDedupKey,
  parcelDisplayAddress,
  parcelJibunResolved,
  parcelShortLabel,
  projectParcelIdentityKey,
} from "./pnu";

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

describe("프로젝트 불러오기 — PNU 가 없는 필지의 잔여 접힘", () => {
  /**
   * ★★종전에는 이 자리에 패널 규칙의 **재구현**이 있었다
   *   (`p.pnu ? parcelDedupKey(p) : \`project-idx:...\``).
   *   그래서 «가짜 PNU 는 truthy 라 인덱스 탈출구를 건너뛴다» 는 결함이 **패널과 테스트에
   *   똑같이** 들어 있었고 테스트는 초록이었다 — 모델을 태우면 모델의 버그는 안 보인다.
   *   이제 **패널이 실제로 부르는 함수**를 태운다.
   */
  const projectKey = projectParcelIdentityKey;

  it("PNU 없는 같은 동 필지 3건이 접히지 않는다", () => {
    const parcels = [
      { address: "경기도 오산시 내삼미동" },
      { address: "경기도 오산시 내삼미동" },
      { address: "경기도 오산시 내삼미동" },
    ];
    expect(new Set(parcels.map(projectKey)).size).toBe(3);
  });

  it("PNU 가 있으면 인덱스와 무관하게 같은 필지는 한 건이다", () => {
    const a = projectKey({ pnu: "4148025329101230004", address: "x" }, 0);
    const b = projectKey({ pnu: "4148025329101230004", address: "y" }, 9);
    expect(a).toBe(b);
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 2026-08-20 — "77행이 전부 동 이름" 6번째 재발. 세 모집단을 **다른 결과**로 가른다.
//
//   (A) 진짜 PNU 보유            → 지번이 붙는다
//   (B) 주소에 지번 보유(PNU 없음) → 주소 그대로 쓴다(이미 특정 가능)
//   (C) 앵커 없음(동 단위 주소)    → 지어내지 않고 "미해석" 으로 남는다
//
// ★셋이 같은 결과를 내면 배선을 끊어도 통과한다 — 그래서 서로 **다름**을 못박는다.
// ────────────────────────────────────────────────────────────────────────────

describe("normalizePnu — PNU 칸에 PNU 가 아닌 것이 들어오면 '없음'", () => {
  it("19자리 숫자만 통과한다", () => {
    expect(normalizePnu("4137011000104670001")).toBe("4137011000104670001");
    expect(normalizePnu("  4137011000104670001  ")).toBe("4137011000104670001");
  });

  it("★실제 프로덕션 오염값(주소가 PNU 칸에 들어앉음)을 걷어낸다", () => {
    // selectionToSiteAnalysisPatch 의 `pnu: parcel.pnu || parcel.id` 가 만든 값.
    expect(normalizePnu("경기도 오산시 내삼미동")).toBeNull();
    expect(normalizePnu("store-0-경기도 오산시 내삼미동")).toBeNull();
    expect(normalizePnu("P-abc123")).toBeNull();
    expect(normalizePnu("")).toBeNull();
    expect(normalizePnu(null)).toBeNull();
    expect(normalizePnu(undefined)).toBeNull();
  });
});

describe("addressHasJibun — 동 단위 주소를 필지 식별자로 쓰지 않기 위한 판정", () => {
  it("번지가 붙어야 참", () => {
    expect(addressHasJibun("경기도 오산시 내삼미동 114-1")).toBe(true);
    expect(addressHasJibun("경기도 오산시 내삼미동 467")).toBe(true);
    expect(addressHasJibun("경기도 오산시 내삼미동 산12-3")).toBe(true);
  });

  it("★동·읍·면 단위만이면 거짓 — 이걸 참으로 보면 77필지가 임의의 한 필지로 수렴한다", () => {
    expect(addressHasJibun("경기도 오산시 내삼미동")).toBe(false);
    expect(addressHasJibun("")).toBe(false);
    expect(addressHasJibun(null)).toBe(false);
  });
});

describe("parcelShortLabel — 축약 SSOT(줄이기 **전에** PNU 로 지번을 파생한다)", () => {
  // 구 shortJibunLabel(lib/satong-click-menu) 케이스 이관 — 축약 자체의 계약은 유지된다.
  it("전체 주소 → 동+지번 2토큰", () => {
    expect(parcelShortLabel("경기도 용인시 수지구 신봉동 56-16")).toBe("신봉동 56-16");
  });

  it("2토큰 이하 주소는 그대로, 빈 값은 폴백", () => {
    expect(parcelShortLabel("신봉동 886")).toBe("신봉동 886");
    expect(parcelShortLabel("886")).toBe("886");
    expect(parcelShortLabel("")).toBe("필지");
    expect(parcelShortLabel(null)).toBe("필지");
    expect(parcelShortLabel(undefined, null, "선택지")).toBe("선택지");
  });

  it("★세 모집단이 **서로 다른** 라벨을 낸다(같으면 배선을 끊어도 통과한다)", () => {
    const a = parcelShortLabel("경기도 오산시 내삼미동", "4137011000104670001"); // (A)
    const b = parcelShortLabel("경기도 오산시 내삼미동 114-1", null);            // (B)
    const c = parcelShortLabel("경기도 오산시 내삼미동", null);                  // (C)
    expect(a).toBe("내삼미동 467-1");
    expect(b).toBe("내삼미동 114-1");
    // ★이 문자열이 사용자 스크린샷에 77번 찍힌 바로 그 글자다(지번이 없으니 구분 불가).
    expect(c).toBe("오산시 내삼미동");
    expect(new Set([a, b, c]).size).toBe(3);
  });

  it("★가짜 PNU(주소 문자열)는 지번을 만들지 못한다 — 조용히 (C)로 떨어진다", () => {
    expect(parcelShortLabel("경기도 오산시 내삼미동", "경기도 오산시 내삼미동"))
      .toBe(parcelShortLabel("경기도 오산시 내삼미동", null));
  });

  it("★같은 동 77필지가 서로 **다른** 라벨이 된다(실제 신고: 77행이 전부 같은 글자)", () => {
    const labels = new Set(
      Array.from({ length: 77 }, (_, i) =>
        parcelShortLabel(
          "경기도 오산시 내삼미동",
          `41370110001${String(1000 + i).padStart(4, "0")}0000`,
        ),
      ),
    );
    expect(labels.size).toBe(77);
  });
});

describe("parcelJibunResolved — '지번 미확인' 을 말해야 하는가", () => {
  it("(A) PNU 보유 → 해석됨", () => {
    expect(parcelJibunResolved({ address: "경기도 오산시 내삼미동", pnu: "4137011000104670001" })).toBe(true);
  });

  it("(B) 주소에 지번 보유 → 해석됨", () => {
    expect(parcelJibunResolved({ address: "경기도 오산시 내삼미동 114-1", pnu: null })).toBe(true);
  });

  it("★(C) 앵커 없음 → 미해석(화면이 그 사실을 말해야 한다)", () => {
    expect(parcelJibunResolved({ address: "경기도 오산시 내삼미동", pnu: null })).toBe(false);
    // 가짜 PNU 가 '해석됨' 으로 오인되면 안 된다 — 그게 6번 재발의 정체다.
    expect(parcelJibunResolved({ address: "경기도 오산시 내삼미동", pnu: "경기도 오산시 내삼미동" })).toBe(false);
  });
});

describe("parcelDisplayAddress — 주소가 이미 지번으로 끝나면 덧붙이지 않는다", () => {
  it("★'산1-1' 처럼 접두가 붙은 지번도 중복 표기하지 않는다(정규식이 못 보던 자리)", () => {
    // 종전: `(^|\s)1-1(\s|$)` 이 '산1-1' 의 '1-1' 을 못 봐 `… 산1-1 1-1` 을 만들었다.
    expect(parcelDisplayAddress("경상북도 포항시 남구 호미곶면 대보리 산1-1", "4711025029000010001"))
      .toBe("경상북도 포항시 남구 호미곶면 대보리 산1-1");
  });

  it("★PNU 가 다른 지번을 가리켜도 **모순되는 라벨**을 만들지 않는다", () => {
    // `… 114-1 467-1` 은 어느 쪽이 맞는지 화면이 말하지 못한다 — 주소를 그대로 둔다.
    expect(parcelDisplayAddress("경기도 오산시 내삼미동 114-1", "4137011000104670001"))
      .toBe("경기도 오산시 내삼미동 114-1");
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 적대리뷰 HIGH — `addressHasJibun` 이 저장소 기존 기준선(`(번지)?` 인정)보다 **좁았다**.
// 좁으면 지번이 **있는데도** 지오코딩·경계보강에서 제외돼 PNU 를 영영 못 얻는다(순수 회귀).
// ★비대칭: 좁게 잡은 쪽이 비싸다. 넓게 잡아 도로명(`테헤란로 152`)이 참이 돼도 라이브
//   geocode 가 `pnu: None` 을 줘 날조가 새지 않는다.
// ────────────────────────────────────────────────────────────────────────────
describe("addressHasJibun — 실무 표기 5종 위음성 회귀", () => {
  const NEGATIVES_THAT_MUST_PASS = [
    "경기도 오산시 내삼미동 114-1번지",
    "경기도 오산시 내삼미동 114번지",
    "서울특별시 강남구 역삼동 736-19 (역삼동)",
    "서울특별시 강남구 테헤란로 152 (역삼동, 강남파이낸스센터)",
    "경기도 오산시 내삼미동 114-1(대)",
  ];

  it("★다섯 표기 모두 '지번 있음' 이다(하나라도 거짓이면 그 필지는 PNU 를 못 얻는다)", () => {
    expect(NEGATIVES_THAT_MUST_PASS).toHaveLength(5); // 공허 진리 가드
    for (const addr of NEGATIVES_THAT_MUST_PASS) {
      expect(addressHasJibun(addr), addr).toBe(true);
    }
  });

  it("★대조군: 동 단위·건물 동호수는 여전히 거짓이어야 한다(가드가 전부 참이면 무의미)", () => {
    for (const addr of [
      "경기도 오산시 내삼미동",
      "경기도 오산시 내삼미동 (오산)",
      "서울특별시 강남구 역삼동 101동",
      "",
    ]) {
      expect(addressHasJibun(addr), addr).toBe(false);
    }
  });

  it("★기존 SSOT(useProjectContextStore.extractAddressTokens)와 **같은 규칙**을 쓴다", () => {
    // 두 곳이 각자 답하던 시절 어긋난 지점이 정확히 `(번지)` 였다.
    expect(isJibunToken("114-1번지")).toBe(true);
    expect(isJibunToken("산12-3")).toBe(true);
    expect(isJibunToken("101동")).toBe(false);
  });
});

describe("parcelDisplayAddress — 괄호 병기 주소에 지번을 중복 출력하지 않는다", () => {
  it("★`… 736-19 (역삼동)` 에 PNU 지번을 덧붙이지 않는다(후속 지적 회귀 고정)", () => {
    const addr = "서울특별시 강남구 역삼동 736-19 (역삼동)";
    expect(parcelDisplayAddress(addr, "1168010100107360019")).toBe(addr);
    // 축약 라벨에도 지번이 살아 있다(잘려서 동 이름만 남지 않는다).
    expect(parcelShortLabel(addr, "1168010100107360019")).toContain("736-19");
  });
});

// ────────────────────────────────────────────────────────────────────────────
// ★★이번 결함의 **진짜 상류**(2026-08-20 조사) — 엑셀 소재지/지번 분리 양식.
// 라이브 실측: `소재지=경기도 오산시 내삼미동` + `지번=467-1` →
//   백엔드는 `address="경기도 오산시 내삼미동"` · `jibun="467-1"` · `pnu=413…0001` 로
//   **정직하게 나눠** 준다. 프론트 유입부가 `address || jibun` 로 받아 지번을 통째로 버렸다.
// 같은 결합은 GlobalAddressSearch 가 2026-06-17 에 이미 갖고 있었는데, 13일 뒤 생긴
// 사통맵 유입부가 그 목록에 없어 결함을 재도입했다 — 그래서 구현을 여기 한 곳으로 모은다.
// ────────────────────────────────────────────────────────────────────────────
describe("joinAddressJibun — 소재지·지번 분리 양식 결합", () => {
  it("★분리형이면 결합한다(이 한 줄이 없어 77필지의 지번이 증발했다)", () => {
    expect(joinAddressJibun("경기도 오산시 내삼미동", "467-1"))
      .toBe("경기도 오산시 내삼미동 467-1");
  });

  it("결합형(이미 지번 포함)은 중복 붙이지 않는다", () => {
    expect(joinAddressJibun("경기도 오산시 내삼미동 467-1", "467-1"))
      .toBe("경기도 오산시 내삼미동 467-1");
  });

  it("★지번이 없으면 지어내지 않는다 — 주소를 그대로 둔다(무날조)", () => {
    expect(joinAddressJibun("경기도 오산시 내삼미동", null)).toBe("경기도 오산시 내삼미동");
    expect(joinAddressJibun("경기도 오산시 내삼미동", "")).toBe("경기도 오산시 내삼미동");
  });

  it("주소가 없으면 지번만, 둘 다 없으면 폴백", () => {
    expect(joinAddressJibun(null, "467-1")).toBe("467-1");
    expect(joinAddressJibun(null, null, "엑셀 등록 필지")).toBe("엑셀 등록 필지");
    expect(joinAddressJibun(null, null)).toBe("");
  });

  it("★결합 결과는 addressHasJibun 을 통과한다 — 상류·하류가 같은 판정을 공유한다", () => {
    const joined = joinAddressJibun("경기도 오산시 내삼미동", "467-1");
    expect(addressHasJibun(joined)).toBe(true);
    // 대조군: 결합하지 않았다면(구 동작) 미해석으로 남는다 — 두 결과가 갈린다.
    expect(addressHasJibun("경기도 오산시 내삼미동")).toBe(false);
  });
});

// 적대리뷰 최종 MEDIUM — `○가` 법정동 + 한자리 본번에서 **지번이 버려졌다**.
// `!addr.includes(jb)` 는 부분문자열이라 `을지로1가` 안의 `1` 을 "이미 있다" 로 오판했다.
describe("joinAddressJibun — 동 이름에 숫자가 있어도 지번을 버리지 않는다", () => {
  it("★`○가` 법정동 + 한자리 본번(실증 케이스)", () => {
    expect(joinAddressJibun("서울특별시 중구 을지로1가", "1")).toBe("서울특별시 중구 을지로1가 1");
    expect(joinAddressJibun("서울특별시 중구 충무로2가", "2")).toBe("서울특별시 중구 충무로2가 2");
    expect(joinAddressJibun("서울특별시 종로구 종로3가", "3")).toBe("서울특별시 종로구 종로3가 3");
  });

  it("★위양성 대조군 — 중복 방지는 그대로다(두 결과가 갈려야 의미가 있다)", () => {
    // 주소가 이미 지번으로 끝나면 붙이지 않는다.
    expect(joinAddressJibun("경기도 오산시 내삼미동 114-1", "114-1")).toBe("경기도 오산시 내삼미동 114-1");
    // PNU/지번이 어긋나도 모순 라벨을 만들지 않는다(주소 우선).
    expect(joinAddressJibun("경기도 오산시 내삼미동 114-1", "467-1")).toBe("경기도 오산시 내삼미동 114-1");
    // 산 지번도 동일.
    expect(joinAddressJibun("경상북도 포항시 남구 대보리 산1-1", "산1-1")).toBe("경상북도 포항시 남구 대보리 산1-1");
  });

  it("★결합 결과가 세 모집단에서 갈린다(전부 같으면 규칙을 바꿔도 통과한다)", () => {
    const a = joinAddressJibun("서울특별시 중구 을지로1가", "1");        // 결합됨
    const b = joinAddressJibun("경기도 오산시 내삼미동 114-1", "114-1"); // 결합 안 함(중복)
    const c = joinAddressJibun("경기도 오산시 내삼미동", null);          // 지번 없음
    expect(addressHasJibun(a)).toBe(true);
    expect(addressHasJibun(b)).toBe(true);
    expect(addressHasJibun(c)).toBe(false);
    expect(new Set([a, b, c]).size).toBe(3);
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 2026-09-02 — PNU **칸에 PNU 가 아닌 것**이 들어앉은 채로 정체성이 판정되고 있었다.
//
// 라이브 실측(`/api/v1/projects` 20건 292필지): PNU 칸의 비-PNU 값 **5건(1.7%)**
//   '◀ 전성결' · '◀ 전성결외 4인' · '◀ 김영효' · '◀ 더윙홀딩스'  ← 성명(토지조서 파싱 잔재)
//   'store-rep-용인시 수지구 신봉동 56-1'                        ← 합성 id
// 생산자는 `satong-map-selection.ts` 의 `store-rep-${address}` 라 **주소가 같으면 값도 같다.**
//
// ★세 모집단을 **다른 결과**로 가른다 — 같은 결과를 내면 배선을 끊어도 통과한다.
// ────────────────────────────────────────────────────────────────────────────

/** 라이브에서 실제로 관측된 오염값 + 형태가 다른 대표들. 하나라도 통과하면 정체성이 오염된다. */
const 가짜PNU = [
  "◀ 전성결",                                 // 실측 — 성명
  "◀ 더윙홀딩스",                              // 실측 — 법인명
  "store-rep-경기도 오산시 내삼미동",            // 실측 형태 — **주소 파생**이라 동이 같으면 값도 같다
  "경기도 오산시 내삼미동",                      // 볼트 2026-08-20 — parcel.id(주소 정규화 문자열)
  "413701100010467000",                       // 18자리(자릿수 미달)
  "41370110001046700012",                     // 20자리(자릿수 초과)
  "413701100010467000a",                      // 19자 이지만 숫자가 아니다
] as const;

describe("PNU 유효성이 정체성을 가른다 — 가짜 PNU 는 정체성이 아니다", () => {
  it("★대조군 — 위 값들은 전부 normalizePnu 에서 탈락한다(픽스처 생존 확인)", () => {
    for (const v of 가짜PNU) expect(normalizePnu(v)).toBeNull();
    // 음성 대조 — 진짜는 통과해야 한다(전부 null 을 주는 죽은 검사기와 구별)
    expect(normalizePnu("4137011000104670001")).toBe("4137011000104670001");
  });

  it("★모집단 A(진짜 PNU) — 같은 동 주소를 공유해도 서로 다른 필지로 갈린다", () => {
    // 라이브 77필지 프로젝트의 실제 형태: 주소는 전부 동 단위로 같고 PNU 만 다르다.
    const A = Array.from({ length: 77 }, (_, i) => ({
      pnu: `413701100010${String(4670001 + i).padStart(7, "0")}`.slice(0, 19),
      address: "경기도 오산시 내삼미동",
    }));
    expect(A.every((p) => normalizePnu(p.pnu) !== null)).toBe(true); // 픽스처가 진짜인지 먼저
    expect(new Set(A.map((p) => parcelDedupKey(p))).size).toBe(77);
    // ★★「77종」만 단언하면 **공허하다** — `project-idx:${i}` 폴백이 인덱스만으로 77종을 보장하므로
    //   `projectParcelIdentityKey` 가 PNU 를 **통째로 무시해도** 초록이었다(적대 리뷰 실측 SURVIVED).
    //   그래서 **키가 어디서 나왔는지**를 못 박는다: 진짜 PNU 면 `pnu:` 축이어야 한다.
    const keysA = A.map((p, i) => projectParcelIdentityKey(p, i));
    expect(new Set(keysA).size).toBe(77);
    expect(keysA.every((k) => k.startsWith("pnu:"))).toBe(true);
    expect(keysA.some((k) => k.startsWith("project-idx:"))).toBe(false);
    // 그리고 **인덱스와 무관**해야 한다 — 같은 필지를 다른 인덱스로 물어도 같은 키다.
    expect(projectParcelIdentityKey(A[0], 0)).toBe(projectParcelIdentityKey(A[0], 76));
  });

  it("★모집단 B(가짜 PNU) — 정체성으로 쓰이지 않는다. dedupKey 는 **주소로** 떨어진다", () => {
    const B = 가짜PNU.map((v) => ({ pnu: v, address: "경기도 오산시 내삼미동" }));
    const keys = B.map((p) => parcelDedupKey(p));
    // 가짜가 키가 되면 7종으로 갈린다 — 주소 폴백이 옳으므로 **1종**이어야 한다.
    expect(new Set(keys).size).toBe(1);
    expect(keys[0]).toBe("addr:경기도 오산시 내삼미동");
    // ★A 와 B 가 같은 결과를 내지 않는다(배선을 끊으면 이 대비가 무너진다)
    expect(new Set(keys).size).not.toBe(가짜PNU.length);
  });

  it("★★모집단 B — 프로젝트 경로에서는 **접히지 않는다**(77→1 재발 방지)", () => {
    // 종전 결함: `p.pnu ?` 가 참/거짓만 봐서 가짜가 truthy → 인덱스 탈출구를 건너뛰고
    //            `store-rep-<같은 동 주소>` 가 **전원 같은 키** → 77건이 1건으로 접혔다.
    const 오염된77 = Array.from({ length: 77 }, () => ({
      pnu: "store-rep-경기도 오산시 내삼미동", // 주소 파생이라 77건이 **모두 같은 값**
      address: "경기도 오산시 내삼미동",
    }));
    const keys = 오염된77.map((p, i) => projectParcelIdentityKey(p, i));
    expect(new Set(keys).size).toBe(77);
    // 그리고 그 키는 **가짜 PNU 를 담고 있지 않다**(키에 새어 나가면 상류로 다시 흐른다)
    expect(keys.every((k) => !k.includes("store-rep"))).toBe(true);
  });

  it("모집단 C(앵커 없음) — 지어내지 않는다. 기존 계약 유지", () => {
    expect(parcelDedupKey({ pnu: "  ", address: "  " })).toBeNull();
    expect(parcelDedupKey({})).toBeNull();
    expect(projectParcelIdentityKey({ address: "경기도 오산시 내삼미동" }, 3))
      .toBe("project-idx:3:경기도 오산시 내삼미동");
  });

  it("★진짜 PNU 는 공백이 섞여도 같은 정체성(정규화 전후 바이트 동일)", () => {
    expect(parcelDedupKey({ pnu: " 4137011000104670001 " })).toBe("pnu:4137011000104670001");
    expect(projectParcelIdentityKey({ pnu: "4137011000104670001" }, 0))
      .toBe(projectParcelIdentityKey({ pnu: "4137011000104670001" }, 9));
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 2026-09-02 — `bcode`(법정동 10자리) 파생이 **12벌** 흩어져 있었고, 전부 `length >= 10` 으로
// 판정했다. 길이 10 은 PNU 를 판정하지 못한다 — 오염값 `'store-rep-용인시 …'`(26자)이
// 통과해 `.slice(0,10)` 이 **`"store-rep-"` 를 법정동코드로** 만들었고, 백엔드는
// `bcode[:5]` = `"store"` 를 `lawd_cd` 로 쓴다(**없는 법정동으로 조회가 나간다**).
// ────────────────────────────────────────────────────────────────────────────
describe("bcodeFromPnu — 법정동코드는 **유효한 19자리**에서만 나온다", () => {
  it("모집단 A(진짜) — 앞 10자리를 준다", () => {
    expect(bcodeFromPnu("4137011000104670001")).toBe("4137011000");
    expect(bcodeFromPnu(" 1159010200100010001 ")).toBe("1159010200"); // 공백 허용(normalizePnu 경유)
  });

  it("★모집단 B(오염·길이만 충족) — **지어내지 않고 null**", () => {
    // 종전 가드 `length >= 10` 이 통과시키던 값들. 여기서 하나라도 문자열이 나오면
    // 그 값이 그대로 `lawd_cd` 가 된다.
    for (const bad of [
      "store-rep-용인시 수지구 신봉동 56-1", // 26자 — 실측 오염값
      "경기도 오산시 내삼미동",                // 11자 — 주소가 PNU 칸에
      "413701100010467000",                  // 18자 — 자릿수 미달
      "41370110001046700012",                // 20자 — 자릿수 초과
      "413701100010467000a",                 // 19자이지만 숫자가 아니다
    ]) {
      expect(bcodeFromPnu(bad)).toBeNull();
    }
  });

  it("모집단 C(없음) — null", () => {
    expect(bcodeFromPnu(null)).toBeNull();
    expect(bcodeFromPnu(undefined)).toBeNull();
    expect(bcodeFromPnu("")).toBeNull();
  });

  it("★대조군 — 길이가 10 이상이라는 이유만으로는 통과하지 못한다(옛 가드와의 차)", () => {
    const 옛가드통과 = (v: string) => v.length >= 10;
    const bad = "store-rep-용인시 수지구 신봉동 56-1";
    expect(옛가드통과(bad)).toBe(true);   // 옛 가드는 통과시켰다
    expect(bcodeFromPnu(bad)).toBeNull(); // 지금은 막는다 — 이 대비가 곧 이 수정이다
  });
});

// ────────────────────────────────────────────────────────────────────────────
// ★적대 리뷰 실측(2026-09-02) — **보내는 값이 「검증한 값」에 결속돼 있지 않았다.**
//   `{ pnu: normalizePnu(p.pnu) }` 를 `{ pnu: p.pnu }` 로 바꿔도 초록이었다.
//   원인: 픽스처에 **「유효하지만 정규화가 필요한」 모집단**이 없어서, 검증 결과와 원본이
//   항상 같은 문자열이었다 — 두 식이 갈리는 입력이 하나도 없으면 배선은 잠기지 않는다.
//   → 공백이 섞인 유효 PNU 를 표준 픽스처로 둔다. 소비처 테스트가 이것을 쓴다.
// ────────────────────────────────────────────────────────────────────────────
export const PNU_유효_공백포함 = " 4137011000104670001 ";
export const PNU_유효_정규화후 = "4137011000104670001";

describe("★정규화가 필요한 유효값 — 검증한 값과 원본이 갈린다", () => {
  it("정규화 전후가 **다른 문자열**이다(이 대비가 없으면 배선 락이 공허하다)", () => {
    expect(PNU_유효_공백포함).not.toBe(PNU_유효_정규화후);
    expect(normalizePnu(PNU_유효_공백포함)).toBe(PNU_유효_정규화후);
  });

  it("파생·정체성 모두 **정규화된 값**을 낸다(원본을 그대로 흘리지 않는다)", () => {
    expect(parcelDedupKey({ pnu: PNU_유효_공백포함 })).toBe(`pnu:${PNU_유효_정규화후}`);
    expect(projectParcelIdentityKey({ pnu: PNU_유효_공백포함 }, 3)).toBe(`pnu:${PNU_유효_정규화후}`);
    expect(bcodeFromPnu(PNU_유효_공백포함)).toBe(PNU_유효_정규화후.slice(0, 10));
  });
});
