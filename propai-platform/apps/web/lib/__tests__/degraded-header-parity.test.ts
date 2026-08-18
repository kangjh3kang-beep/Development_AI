/**
 * 강등 헤더명이 **생산자와 소비자 사이에서 어긋나지 않게** 묶는다.
 *
 * 【왜 복제인가】생산자는 `lib/vworld-wms-proxy.ts`(서버 전용 — Buffer·process.env 사용),
 * 소비자는 `components/map/SatongMultiMap.tsx`(클라이언트 컴포넌트)다. 소비자가 생산자를
 * import 하면 서버 전용 모듈이 **클라이언트 번들로 끌려온다.** 그래서 리터럴을 복제했다.
 *
 * 【복제의 위험과 이 락】헤더명이 한쪽만 바뀌면 **강등이 조용히 관측 불가**가 된다 —
 * 타일은 투명하게 나오는데(지도는 정상처럼 보이고) 배너는 안 뜬다. 즉 **무음 강등**이며,
 * 이 저장소가 "무음 회색타일 금지" 로 막으려던 것의 정확한 반대편 재발이다.
 * 그래서 두 파일의 문자열이 **같은지**를 직접 단언한다.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { VWORLD_DEGRADED_HEADER } from "@/lib/vworld-wms-proxy";

const WEB_ROOT = join(__dirname, "..", "..");

describe("강등 헤더명 정합", () => {
  it("전제: 생산자 상수가 비어 있지 않다(공허한 초록 방지)", () => {
    expect(VWORLD_DEGRADED_HEADER.length, "헤더명이 비었다").toBeGreaterThan(3);
  });

  it("★소비자(SatongMultiMap)가 같은 헤더명을 읽는다", () => {
    const src = readFileSync(join(WEB_ROOT, "components", "map", "SatongMultiMap.tsx"), "utf8");
    // 실제로 **읽는** 코드만 인정한다(주석 언급이 아니라 `headers.get("…")`).
    const m = /headers\.get\(\s*"([^"]*Degraded[^"]*)"\s*\)/.exec(src);
    expect(m, "SatongMultiMap 이 강등 헤더를 읽는 코드가 없다 — 배너가 뜰 수 없다").not.toBeNull();
    expect(m?.[1], "생산자와 소비자의 헤더명이 어긋났다 — 강등이 무음이 된다").toBe(
      VWORLD_DEGRADED_HEADER,
    );
  });

  it("★강등 판정이 '200 + image/' 분기보다 **앞**에 있다", () => {
    // 순서가 뒤바뀌면 투명타일(200 image/png)이 '정상'으로 오진된다 — 거짓 초록.
    const src = readFileSync(join(WEB_ROOT, "components", "map", "SatongMultiMap.tsx"), "utf8");
    const degradedAt = src.indexOf('headers.get("X-VWorld-Degraded")');
    const okAt = src.indexOf('contentType.startsWith("image/")');
    expect(degradedAt, "강등 판정 코드를 못 찾았다").toBeGreaterThan(-1);
    expect(okAt, "정상 분기를 못 찾았다").toBeGreaterThan(-1);
    expect(degradedAt, "강등 판정이 정상 분기 뒤에 있다 — 투명타일이 '정상'으로 오진된다").toBeLessThan(okAt);
  });
});
