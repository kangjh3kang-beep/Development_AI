/**
 * `LandShareModal` — **오염된 PNU 를 진짜인 것처럼 보내지 않는다.**
 *
 * 종전 가드는 `pnu && pnu.length >= 19` 였다. 라이브 실측(2026-09-02, 292필지) 오염값
 * `'store-rep-용인시 수지구 신봉동 56-1'` 은 **26자**라 그 가드를 통과했고,
 * `/zoning/land-share` 에 `{ pnu: "store-rep-…" }` 가 실려 나갔다.
 * 서버는 그런 PNU 를 해석하지 못하므로 **주소 경로로 갔어야 할 조회가 통째로 죽는다.**
 *
 * ★두 모집단을 같은 파일에서 가른다 — 진짜는 `{pnu}` 로, 오염은 `{address}` 로 나간다.
 *   한쪽만 보면 «항상 주소로 보내기» 같은 아무것도 안 하는 구현도 통과한다.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";

vi.mock("@/lib/api-client", () => ({ apiV1BaseUrl: () => "https://api.test/api/v1" }));

import { LandShareModal } from "@/components/operations/LandShareModal";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue({ json: async () => ({ ok: true, units: [] }) });
  vi.stubGlobal("fetch", fetchMock);
});

async function 요청본문(pnu: string | null) {
  render(
    <LandShareModal jibun="경기도 오산시 내삼미동 467-1" pnu={pnu} onClose={() => {}} onApplyArea={() => {}} />,
  );
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const [, init] = fetchMock.mock.calls[0] as [string, { body: string }];
  return JSON.parse(init.body) as { pnu?: string; address?: string };
}

describe("LandShareModal — /zoning/land-share 요청은 유효한 PNU 만 싣는다", () => {
  it("모집단 A(진짜 19자리) — pnu 로 나간다", async () => {
    const body = await 요청본문("4137011000104670001");
    expect(body.pnu).toBe("4137011000104670001");
    expect(body.address).toBeUndefined();
  });

  it("★모집단 B(오염 · 길이는 19 이상) — **주소로** 나간다(옛 가드는 pnu 로 보냈다)", async () => {
    const 오염 = "store-rep-용인시 수지구 신봉동 56-1"; // 26자 — `length >= 19` 를 통과한다
    expect(오염.length).toBeGreaterThanOrEqual(19); // ★픽스처가 옛 가드를 실제로 통과하는지 먼저
    const body = await 요청본문(오염);
    expect(body.pnu).toBeUndefined();
    expect(body.address).toBe("경기도 오산시 내삼미동 467-1");
  });

  it("모집단 C(없음) — 주소로 나간다(기존 계약 유지)", async () => {
    const body = await 요청본문(null);
    expect(body.pnu).toBeUndefined();
    expect(body.address).toBe("경기도 오산시 내삼미동 467-1");
  });
});
