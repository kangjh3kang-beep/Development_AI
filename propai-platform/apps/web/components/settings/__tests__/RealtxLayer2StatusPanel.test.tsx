/**
 * 실거래 2층 관측 패널 락 — **「모름」이 수치를 입지 않는가**.
 *
 * ## 이 파일이 존재하는 이유
 *
 * 이 패널 자체가 *"만들어 놓고 아무도 안 읽는 것은 전달된 것이 아니다"* 라는 주장의
 * 산물이다. 그렇다면 **그 주장을 이 패널이 스스로 지키는지**도 잠가야 한다
 * (CLAUDE.md §D-16 — PR 이 선언한 원칙을 그 PR 의 신규 코드에 적용했는가).
 *
 * ★잠그는 것은 *"API 를 부른다"* 가 아니라 **그려진 결과**다.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn() },
  ApiClientError: class extends Error {},
}));

import { apiClient } from "@/lib/api-client";
import {
  RealtxLayer2StatusPanel,
  displayAge,
  displayCount,
  toneFor,
} from "../RealtxLayer2StatusPanel";

const BASE = {
  stored_rows: 4898,
  reobserved_rows: 0,
  scopes: { total: 36, baseline_done: 36, sigungu_ever_scanned: 6, trade_scopes: 36 },
  corrections: { total: 0, by_kind: {} },
  quota: {
    targets: 6, daily_scopes: 36, weekly_avg_per_day: 39.4,
    baseline_targets: 6, vs_baseline: 1.0, limit: "미측정", state: "기준선범위",
  },
  detection: { state: "미시험", meaning: "정정 탐지가 아직 한 번도 돌지 않았다(재관측 행 0)." },
  collection: {
    recent: { months: ["202608"], last_scanned_at: "2026-08-26T19:10:00Z", age_hours: 8, state: "정상", stale: false },
    tail: { probe_month: "202602", last_scanned_at: null, age_hours: null, state: "미수집", stale: null },
  },
  as_of: "2026-08-27T03:00:00+00:00",
};

// ══════════════════════════════════════════════════════════════
// 1. ★「모름」을 수치로 위장하지 않는다 (순수 함수)
// ══════════════════════════════════════════════════════════════

describe("표시 규율", () => {
  it("null 을 0 으로 접지 않는다 — 접으면 「모름」이 관측으로 읽힌다", () => {
    expect(displayCount(null)).toBe("미상");
    expect(displayCount(undefined)).toBe("미상");
    // ★두 모집단이 갈린다 — 0 은 **관측**이므로 그대로 0 이어야 한다
    expect(displayCount(0)).toBe("0");
    expect(displayCount(4898)).toBe("4,898");
  });

  it("나이를 말할 수 없으면 **상태 이름**을 보여 준다(수치 위장 금지)", () => {
    expect(displayAge({ age_hours: null, state: "미수집" })).toBe("미수집");
    expect(displayAge({ age_hours: null, state: "시각이상" })).toBe("시각이상");
    // ★대조군 — 잴 수 있으면 수치가 나온다(이 단언이 공허하지 않다)
    expect(displayAge({ age_hours: 8, state: "정상" })).toBe("8.0시간 전");
    expect(displayAge({ age_hours: 48, state: "낡음" })).toBe("2.0일 전");
  });

  it("★판정 불가를 **정상색으로 칠하지 않는다**", () => {
    // 모른다 — 초록이 아니다
    for (const s of ["미배포", "미수집", "미시험", "상태소실"]) {
      expect(toneFor(s)).toBe("unknown");
    }
    // 관측됐다
    for (const s of ["관측됨_정정없음", "관측됨_정정있음", "정상"]) {
      expect(toneFor(s)).toBe("ok");
    }
    // 문제다
    for (const s of ["모순", "낡음", "시각이상"]) {
      expect(toneFor(s)).toBe("warn");
    }
    // ★파티션 — 세 색이 실제로 갈린다(하나로 접으면 여기서 죽는다)
    expect(new Set(["미시험", "정상", "모순"].map(toneFor)).size).toBe(3);
  });
});

// ══════════════════════════════════════════════════════════════
// 2. ★배선 — **그려진 결과**를 본다("부른다" 가 아니라)
// ══════════════════════════════════════════════════════════════

describe("배선", () => {
  it("판정과 사유가 **화면에 뜬다**", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(BASE as never);
    render(<RealtxLayer2StatusPanel />);
    await waitFor(() => expect(screen.getByText("미시험")).toBeTruthy());
    // ★사유도 떠야 한다 — 상태 코드만 뜨면 사람이 판단할 수 없다
    expect(screen.getByText(/아직 한 번도 돌지 않았다/)).toBeTruthy();
    expect(screen.getByText(/4,898/)).toBeTruthy();
    // ★한도를 지어내지 않았는지 — 화면에도 「미측정」이 떠야 한다
    expect(screen.getByText(/미측정/)).toBeTruthy();
  });

  it("★두 모집단 — 서버가 다른 판정을 주면 **화면도 달라진다**(상수 렌더 방지)", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      ...BASE,
      reobserved_rows: 4898,
      corrections: { total: 7, by_kind: { cancelled: 5, registry_added: 2 } },
      detection: { state: "관측됨_정정있음", meaning: "4898행 재관측 중 정정 7건." },
    } as never);
    render(<RealtxLayer2StatusPanel />);
    await waitFor(() => expect(screen.getByText("관측됨_정정있음")).toBeTruthy());
    expect(screen.queryByText("미시험")).toBeNull();
    expect(screen.getByText(/cancelled: 5건/)).toBeTruthy();
  });

  it("★꼬리 미수집을 `0시간 전` 으로 그리지 않는다", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(BASE as never);
    render(<RealtxLayer2StatusPanel />);
    await waitFor(() => expect(screen.getByText("미시험")).toBeTruthy());
    expect(screen.queryByText(/0\.0시간 전/)).toBeNull();
    expect(screen.getAllByText(/미수집/).length).toBeGreaterThan(0);
  });

  it("★조회 실패의 **사유를 삼키지 않는다** — 진단 불가는 그 자체로 장애다", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error("403 관리자 권한이 필요합니다."));
    render(<RealtxLayer2StatusPanel />);
    await waitFor(() => expect(screen.getByText(/조회 실패/)).toBeTruthy());
    expect(screen.getByText(/관리자 권한/)).toBeTruthy();
  });

  it("★엔드포인트 경로가 계약과 일치한다", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(BASE as never);
    render(<RealtxLayer2StatusPanel />);
    await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
    expect(vi.mocked(apiClient.get).mock.calls[0][0]).toBe("/market/realtx-layer2/status");
  });
});
