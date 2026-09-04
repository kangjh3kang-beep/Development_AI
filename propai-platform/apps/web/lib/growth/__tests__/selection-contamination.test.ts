/**
 * ★순수 층 — 판정 → 전송 속성 변환. **상수·`service`·`surface` 를 함께 잠근다.**
 *
 * 이 저장소가 3회 반복한 실수: 계측을 붙이면서 이벤트 **이름만** 잠그고 `service`·`surface`
 * 는 안 잠근다. 그러면 그 필드를 지워도 테스트가 초록이고, 대시보드에서 이벤트가 어디서
 * 왔는지 알 수 없게 된다(집계 축이 사라진다).
 *
 * ★픽스처는 **세 모집단을 가른다** — 정상/지역혼합/깨짐. 셋이 같은 값을 내면 배선을 끊어도
 *   결과가 같아 잠금이 아니다(규율 §2).
 */
import { describe, expect, it, vi } from "vitest";

import type { SelectionIntegrity } from "@/lib/selection-integrity";

const trackEventMock = vi.hoisted(() => vi.fn());
vi.mock("../event-collector", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../event-collector")>()),
  trackEvent: trackEventMock,
}));

import {
  SELECTION_CONTAMINATION_EVENT,
  SELECTION_CONTAMINATION_SERVICE,
  buildSelectionContaminationProps,
  selectionContaminationKey,
  trackSelectionContamination,
} from "../selection-contamination";

const CLEAN: SelectionIntegrity = {
  verdict: "single_site",
  regionGroups: ["충청북도 제천시 금성면 성내리 산 7-1"],
  malformedRows: [],
  spreadKm: 0.12,
};

/** `4f8a6db5` 실측 — 같은 제천시인데 15.94km, 2개 지역군. */
const MULTI_REGION: SelectionIntegrity = {
  verdict: "multi_region",
  regionGroups: ["충청북도 제천시 금성면 성내리 산 7-1", "충청북도 제천시 모산동 123-1"],
  malformedRows: [],
  spreadKm: 15.94,
};

/** `ad66982a` 실측 — 소유자명 4행, **좌표 전무**(spreadKm 은 미상이지 0이 아니다). */
const MALFORMED: SelectionIntegrity = {
  verdict: "malformed",
  regionGroups: ["경기도 용인시 수지구 고기동 689"],
  malformedRows: ["◀ 전성결", "◀ 김영효", "◀ 더윙홀딩스", "◀ 이순덕"],
  spreadKm: null,
};

describe("선택 오염 관측 — 속성 변환", () => {
  it("★정상 선택은 보내지 않는다(전수 전송은 신호를 잡음에 묻는다)", () => {
    expect(buildSelectionContaminationProps(CLEAN, "/ko/precheck")).toBeNull();
  });

  it("지역 혼합은 판정·거리·군수를 담아 보낸다", () => {
    const props = buildSelectionContaminationProps(MULTI_REGION, "/ko/precheck");
    expect(props).not.toBeNull();
    expect(props!.service).toBe(SELECTION_CONTAMINATION_SERVICE); // ★집계 축
    expect(props!.route).toBe("/ko/precheck");
    expect(props!.severity).toBe("warn"); // 정당할 수 있다 — 오류가 아니다
    expect(props!.payload).toEqual({
      verdict: "multi_region",
      spread_km: 15.94,
      region_groups: 2,
      malformed_rows: 0,
    });
  });

  it("깨진 데이터는 severity 가 다르고 행수를 담는다(두 모집단이 다른 값을 낸다)", () => {
    const props = buildSelectionContaminationProps(MALFORMED, "/ko/precheck");
    expect(props!.severity).toBe("error"); // multi_region 의 "warn" 과 **다르다**
    expect(props!.payload).toEqual({
      verdict: "malformed",
      // ★좌표가 없으면 **미상**이다 — 0 으로 뭉개면 "붙어 있다"는 거짓이 된다.
      spread_km: null,
      region_groups: 1,
      malformed_rows: 4,
    });
  });

  it("★주소 원문을 보내지 않는다 — 사람 이름·지번이 그대로 실려 나가면 안 된다", () => {
    const serialized = JSON.stringify(
      buildSelectionContaminationProps(MALFORMED, "/ko/precheck")!.payload,
    );
    expect(serialized).not.toContain("전성결");
    expect(serialized).not.toContain("고기동");
    // ★음성 단언만으로는 아무것도 잠기지 않는다(payload 를 통째로 지워도 참이다).
    //   그래서 **개수는 실려 있다**는 양성 단언을 함께 둔다.
    expect(serialized).toContain("\"malformed_rows\":4");
  });

  it("중복 제거 키는 판정이 달라지면 달라진다", () => {
    const a = selectionContaminationKey(MULTI_REGION);
    expect(selectionContaminationKey(MULTI_REGION)).toBe(a); // 같은 사실 = 같은 키
    expect(selectionContaminationKey(MALFORMED)).not.toBe(a);
    expect(selectionContaminationKey(CLEAN)).not.toBe(a);
  });
});

describe("★배선 — 오염일 때만 collector 를 태운다", () => {
  it("오염이면 상수 이름·service 로 trackEvent 를 호출한다", () => {
    trackEventMock.mockClear();
    expect(trackSelectionContamination(MULTI_REGION, "/ko/precheck")).toBe(true);
    expect(trackEventMock).toHaveBeenCalledTimes(1);
    // ★문자열 리터럴이 아니라 **상수**로 단언한다 — 상수를 바꾸면 호출부도 따라와야 한다.
    expect(trackEventMock.mock.calls[0][0]).toBe(SELECTION_CONTAMINATION_EVENT);
    expect(trackEventMock.mock.calls[0][0]).toBe("selection_contamination_observation");
    expect(trackEventMock.mock.calls[0][1].service).toBe(SELECTION_CONTAMINATION_SERVICE);
  });

  it("정상이면 아예 호출하지 않는다(대조군 — 두 모집단이 갈린다)", () => {
    trackEventMock.mockClear();
    expect(trackSelectionContamination(CLEAN, "/ko/precheck")).toBe(false);
    expect(trackEventMock).not.toHaveBeenCalled();
  });
});
