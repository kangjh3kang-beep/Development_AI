/**
 * 필지 경사도 섹션(W2) — 표시 계약 + 정직 표기.
 *
 * 고정하는 계약:
 *   ① 조회 전(idle)엔 숫자를 만들지 않고 비용 사유를 밝힌다(1req/s → 명시적 요청)
 *   ② 완료 시 평균·최대·등급 + 서버 confidence 배지 + "참고값·실측 필요"
 *   ③ ★서버 note(SRTM 한계 문구)를 **그대로** 옮긴다 — 요약·의역하면 한계가 흐려진다
 *   ④ ok:false·네트워크 실패는 "경사도 0%"가 아니라 **조회 실패**로 표기한다(무날조)
 *   ⑤ 신뢰도 라벨은 서버 confidence를 구간화만 한다(프론트 재산정 없음)
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ParcelSlopeSection } from "@/components/precheck/ParcelSlopeSection";
import type { TerrainResult } from "@/components/terrain/types";

/** 호미곶 대보리 산1-1류(대규모 임야) — 서버 실응답 형태. */
const STEEP: TerrainResult = {
  ok: true,
  pnu: "4711025029000010001",
  slope: {
    mean_pct: 18.4,
    max_pct: 27.1,
    aspect_deg: 142,
    class: "경사",
    detail: "평균경사 18.4% / 최대 27.1% — 경사. 주 사면 향: 남동(142°). (필지 폴리곤 내부 61점 기준·이웃 지형 제외)",
  },
  confidence: 0.85,
  note: "참고용(EXPERIMENTAL): SRTM 30m 광역 표고 기반 — 정밀 측량/검증된 토목설계가 아님. 평균경사도는 필지 폴리곤 내부 격자점 61개만 집계(이웃 지형 제외).",
  resolution_m: 30,
};

/** 소형 필지 — DEM 1셀보다 작아 미세지형 분해 불가(신뢰도 낮음). */
const SMALL_PARCEL: TerrainResult = {
  ok: true,
  slope: { mean_pct: 4.2, max_pct: 6.0, aspect_deg: null, class: "평지", detail: "평균경사 4.2% / 최대 6.0% — 평지. 사면 향 불명확(평탄)." },
  confidence: 0.24,
  note: "참고용(EXPERIMENTAL): SRTM 30m 광역 표고 기반 — 정밀 측량/검증된 토목설계가 아님. 필지 320㎡가 DEM 1셀(≈900㎡)보다 작아 필지 내 미세지형을 분해할 수 없음 → 광역 지형 근사.",
};

describe("ParcelSlopeSection 표시 계약(W2)", () => {
  it("① 조회 전(idle) — 숫자를 만들지 않고 비용 사유를 밝히며 요청 버튼을 준다", () => {
    const onRequest = vi.fn();
    render(<ParcelSlopeSection status="idle" onRequest={onRequest} />);

    expect(screen.getByTestId("parcel-slope-section")).toBeInTheDocument();
    expect(screen.getByText(/미조회 — 표고\(SRTM 30m\) 조회에 약 1초/)).toBeInTheDocument();
    // 조회 전에 어떤 경사도 수치도 렌더하지 않는다.
    expect(screen.queryByTestId("parcel-slope-mean")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("parcel-slope-request"));
    expect(onRequest).toHaveBeenCalledTimes(1);
  });

  it("② 완료 — 평균·최대·등급 + 신뢰도 배지 + '참고값·실측 필요'", () => {
    render(<ParcelSlopeSection status="done" result={STEEP} onRequest={vi.fn()} />);

    expect(screen.getByTestId("parcel-slope-mean").textContent).toBe("18.4%");
    expect(screen.getByTestId("parcel-slope-max").textContent).toBe("27.1%");
    expect(screen.getByText("경사")).toBeInTheDocument();
    expect(screen.getByTestId("parcel-slope-confidence").textContent).toContain("비교적 높음");
    expect(screen.getByTestId("parcel-slope-confidence").textContent).toContain("0.85");
    expect(screen.getByText("참고값 · 실측 필요")).toBeInTheDocument();
    // 조회가 끝났으면 요청 버튼은 사라진다(중복 조회 유도 금지).
    expect(screen.queryByTestId("parcel-slope-request")).not.toBeInTheDocument();
  });

  it("★③ 서버 note(SRTM 한계)를 그대로 옮긴다 — 요약·의역 금지", () => {
    render(<ParcelSlopeSection status="done" result={SMALL_PARCEL} onRequest={vi.fn()} />);

    // 문구를 **원문 그대로** 비교한다. 프론트가 요약하면 "DEM 1셀보다 작아 분해 불가"라는
    //   핵심 한계가 사라지고 4.2%가 실측처럼 읽힌다.
    expect(screen.getByTestId("parcel-slope-note").textContent).toBe(SMALL_PARCEL.note);
    expect(screen.getByTestId("parcel-slope-note").textContent).toContain("DEM 1셀");
    expect(screen.getByTestId("parcel-slope-note").textContent).toContain("분해할 수 없음");
    // 신뢰도가 낮으면 라벨도 낮게(서버 값 구간화 — 프론트 재산정 없음).
    expect(screen.getByTestId("parcel-slope-confidence").textContent).toContain("낮음");
  });

  it("④ 실패 — '경사도 0%'가 아니라 조회 실패로 표기하고 재조회를 제공한다", () => {
    const onRequest = vi.fn();
    render(
      <ParcelSlopeSection
        status="error"
        errorMessage="주소/PNU로 좌표 또는 필지를 확인하지 못했습니다."
        onRequest={onRequest}
      />,
    );

    const err = screen.getByTestId("parcel-slope-error");
    expect(err.textContent).toContain("조회 실패");
    expect(err.textContent).toContain("좌표 또는 필지를 확인하지 못했습니다");
    // ★실패를 0%로 날조하지 않는다.
    expect(screen.queryByTestId("parcel-slope-mean")).not.toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "다시 조회" }));
    expect(onRequest).toHaveBeenCalledTimes(1);
  });

  it("④-b 로딩 중 — 진행 표시만, 수치·버튼 없음(연타 유도 차단)", () => {
    render(<ParcelSlopeSection status="loading" onRequest={vi.fn()} />);

    expect(screen.getByTestId("parcel-slope-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("parcel-slope-request")).not.toBeInTheDocument();
    expect(screen.queryByTestId("parcel-slope-mean")).not.toBeInTheDocument();
  });

  it("⑤ slope 없이 done — 임의 수치를 만들지 않고 산출 불가를 밝힌다", () => {
    render(
      <ParcelSlopeSection status="done" result={{ ok: true, confidence: 0.1 }} onRequest={vi.fn()} />,
    );

    expect(screen.getByText(/경사도 산출 불가/)).toBeInTheDocument();
    expect(screen.queryByTestId("parcel-slope-mean")).not.toBeInTheDocument();
  });

  it("⑤-b 신뢰도 구간 라벨이 서버 값을 따른다(경계 포함)", () => {
    const at = (confidence: number) => {
      const { unmount } = render(
        <ParcelSlopeSection
          status="done"
          result={{ ...STEEP, confidence }}
          onRequest={vi.fn()}
        />,
      );
      const text = screen.getByTestId("parcel-slope-confidence").textContent || "";
      unmount();
      return text;
    };
    expect(at(0.7)).toContain("비교적 높음");
    expect(at(0.69)).toContain("보통");
    expect(at(0.4)).toContain("보통");
    expect(at(0.39)).toContain("낮음");
  });
});
