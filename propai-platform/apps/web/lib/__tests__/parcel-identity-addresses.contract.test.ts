/**
 * 필지 **정체성 주소** 계약 — 다필지가 한 문자열로 붕괴하지 않는다.
 *
 * 【사용자 신고 · 2026-08-28】
 * 77필지·86,755㎡ 부지가 「최적 개발방식 시뮬레이션」에서 **44㎡(13.3평)** 로 계산돼
 * 개발방식 **19건이 거짓 '불가'** 로 막혔다(«도시개발사업: 총면적 44m² < 1만m² 요건 미달»).
 * 근본 원인: 화면들이 `parcels.map((p) => p.address)` 를 손수 썼고, 스토어 주소에 지번이 없으면
 * 77개가 **같은 문자열**이 되어 백엔드 `_merge`(주소 중복제거)가 **1필지로 붕괴**시켰다.
 *
 * 【이 파일이 잠그는 것】
 *  1. 헬퍼가 PNU 로 주소를 **구분한다**(두 모집단)
 *  2. PNU 가 없으면 **구분을 지어내지 않는다**(무날조)
 *  3. ★**파생형 스윕** — 시뮬 카드에 `parcels` 를 넘기는 **모든** 프로덕션 소비처가
 *     공용 헬퍼를 경유한다. 손 목록이 아니라 소스에서 소비처를 **찾아내** 검사하므로,
 *     새 화면이 같은 결함을 들고 들어오면 여기서 빨개진다(4세대를 만들지 않기 위해).
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { parcelIdentityAddresses } from "@/lib/parcel-rows";
import { __stripCommentsForScan } from "@/lib/source-invariant";

const DONG = "경기도 오산시 내삼미동";

describe("parcelIdentityAddresses — 정체성", () => {
  it("A1 ★같은 동 주소라도 PNU 가 다르면 **구분된다**", () => {
    const out = parcelIdentityAddresses([
      { address: DONG, pnu: "4137011000104670001" },
      { address: DONG, pnu: "4137011000101140001" },
      { address: DONG, pnu: "4137011000104680001" },
    ]);
    expect(out.length).toBe(3);
    expect(new Set(out).size).toBe(3);
  });

  it("A2 ★PNU 가 없으면 구분을 **지어내지 않는다**(무날조)", () => {
    const out = parcelIdentityAddresses([
      { address: DONG, pnu: null },
      { address: DONG, pnu: null },
    ]);
    expect(new Set(out).size).toBe(1);
  });

  it("A3 ★면적으로 거르지 않는다 — 표시 모집단은 «고른 것» 전부다", () => {
    // `parcelAddressList` 와 의미가 다르다(그쪽은 면적>0 전송용).
    const out = parcelIdentityAddresses([
      { address: DONG, pnu: "4137011000104670001" },
      { address: DONG, pnu: "4137011000101140001" },
    ]);
    expect(out.length).toBe(2);
  });

  it("A4 대조군 — 빈 입력·빈 주소는 필지가 아니다", () => {
    expect(parcelIdentityAddresses(null)).toEqual([]);
    expect(parcelIdentityAddresses([{ address: "  ", pnu: "x" }])).toEqual([]);
  });
});

/** 프로덕션 소스(테스트·스토리 제외)를 훑는다. */
function productionSources(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next" || name === "__tests__") continue;
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) productionSources(full, acc);
    else if (/\.tsx?$/.test(name) && !/\.(test|spec)\.tsx?$/.test(name)) acc.push(full);
  }
  return acc;
}

describe("★파생형 스윕 — 시뮬 카드 소비처는 공용 헬퍼를 경유한다", () => {
  const ROOT = path.resolve(__dirname, "../..");
  const CARD = "DevelopmentScenarioCard";
  /** 정체성을 보장하는 통로 — 이 중 하나를 거쳐야 한다. */
  const SAFE = ["parcelIdentityAddresses", "parcelAddressList", "buildAnalysisParcelAddrs",
                "satongSelectionAddresses"];

  const consumers = productionSources(ROOT)
    .filter((f) => !f.includes(`${path.sep}lib${path.sep}`))
    .map((f) => ({ f, src: __stripCommentsForScan(readFileSync(f, "utf8"), f) }))
    .filter(({ src }) => src.includes(`<${CARD}`));

  it("S1 대조군 — 소비처를 실제로 찾았다(0건이면 아래 «위반 0» 이 공허하다)", () => {
    expect(consumers.length).toBeGreaterThanOrEqual(4);
  });

  it("S2 ★모든 소비처가 정체성 통로를 쓴다(손수 map 금지)", () => {
    const 위반 = consumers
      .filter(({ src }) => !SAFE.some((s) => src.includes(s)))
      .map(({ f }) => path.relative(ROOT, f));
    expect(위반, `시뮬 카드에 필지를 넘기면서 정체성 통로를 안 쓴다 — 같은 동의 필지가 한 문자열로 붕괴한다: ${위반.join(", ")}`).toEqual([]);
  });

  it("S3 ★음성 대조군 — 검사기가 실제로 위반을 잡는가", () => {
    const 가짜 = [{ f: "x.tsx", src: `<${CARD} parcels={ps.map((p) => p.address)} />` }];
    const 위반 = 가짜.filter(({ src }) => !SAFE.some((s) => src.includes(s)));
    expect(위반.length).toBe(1);
  });
});

/**
 * ★★모집단 축 교정 — 위 S1~S3 은 **「그 카드를 렌더하는 파일」** 을 모집단으로 삼는다.
 * 그런데 결함이 사는 층은 **「필지 정체성을 비교하는 파일」** 이다. 두 집합은 다르다:
 * `GlobalAddressSearch` 는 그 카드를 렌더하지 않으므로 **구조적으로 스윕 밖**이었고,
 * 실제로 그 안에서 **주소 문자열 중복제거 3곳**이 살아 있었다(2026-09-02 실측).
 *
 * → 축을 **행위**로 바꾼다: "필지끼리 주소 문자열로 정체성을 비교하는 줄" 을 찾는다.
 *   조회 대상은 손으로 고르지 않고 프로덕션 소스 전수에서 **파생**시킨다.
 *
 * ★검출기 자체를 두 방향으로 검증한다 — 양성(옛 결함 코드를 잡는가)과
 *   음성(주소를 **문자열과** 비교하는 정당한 조회를 안 잡는가). 후자가 없으면 위양성이
 *   정상 코드를 막는다(이 저장소가 반복해 데인 형태).
 */
describe("★파생형 스윕 — 필지 정체성을 주소 문자열로 비교하지 않는다", () => {
  const ROOT = path.resolve(__dirname, "../..");
  /** 두 **필지 객체**의 주소를 맞대는 형태(조회가 아니라 정체성 판정). */
  const PAIR = /\.(fullAddress|address)\s*===\s*[\w.]+\.(fullAddress|address)/;
  /** 주소만으로 만든 정체성 집합. */
  const ADDR_SET = /new Set\(\s*[\w.]+\.map\(\s*\(\s*\w+\s*\)\s*=>\s*\w+\.(fullAddress|address)\s*\)/;

  const offenders = productionSources(ROOT)
    .map((f) => ({ f, src: __stripCommentsForScan(readFileSync(f, "utf8"), f) }))
    .filter(({ src }) => src.split("\n").some((l) => PAIR.test(l) || ADDR_SET.test(l)))
    .map(({ f }) => path.relative(ROOT, f));

  it("T1 대조군 — 조회 모집단이 비어 있지 않다(0파일이면 아래가 공허하다)", () => {
    expect(productionSources(ROOT).length).toBeGreaterThan(100);
  });

  it("T2 ★양성 대조군 — 검출기가 옛 결함 코드를 잡는다", () => {
    const 옛코드 = [
      `if (addresses.some((a) => a.fullAddress === entry.fullAddress)) {`,
      `const existingAddresses = new Set(addresses.map((a) => a.fullAddress));`,
      `addresses.filter((a) => !uniq.some((e) => e.fullAddress === a.fullAddress))`,
      `(f) => (parcel.pnu && f.pnu === parcel.pnu) || f.address === parcel.address,`,
    ];
    for (const l of 옛코드) expect(PAIR.test(l) || ADDR_SET.test(l), `못 잡음: ${l}`).toBe(true);
  });

  it("T3 ★음성 대조군 — 주소를 **문자열과** 맞대는 정당한 조회는 안 잡는다", () => {
    // 이것은 «입력한 주소로 찾기» 이지 «두 필지가 같은가» 가 아니다. 잡으면 위양성이다.
    const 정당 = `a.fullAddress === address || a.jibunAddress === address`;
    expect(PAIR.test(정당) || ADDR_SET.test(정당)).toBe(false);
  });

  it("T4 ★위반 0 — 정체성 판정은 `parcel-entry-identity`/`pnu` 를 경유한다", () => {
    expect(
      offenders,
      `필지끼리 주소 문자열로 정체성을 판정한다 — 같은 동의 서로 다른 필지가 한 건으로 붕괴하거나, 같은 필지가 표기 차이로 두 건이 된다: ${offenders.join(", ")}`,
    ).toEqual([]);
  });
});
