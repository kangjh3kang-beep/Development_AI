import { describe, it, expect } from "vitest";
import { roomName, tileColumns, connectionLabel } from "./livekit";

describe("roomName", () => {
  it("프로젝트 스코프·결정론·백엔드 정합", () => {
    expect(roomName("p1", "main")).toBe("proj-p1-main");
    expect(roomName("p1")).toBe("proj-p1-main");
    expect(roomName("p1", "a/b c!")).toBe("proj-p1-abc"); // 비안전 문자 제거
    expect(roomName("p1", "헬로")).toBe("proj-p1-main"); // 비ASCII→폴백
  });
});

describe("tileColumns", () => {
  it("참가자 수→열(결정론)", () => {
    expect(tileColumns(0)).toBe(1);
    expect(tileColumns(1)).toBe(1);
    expect(tileColumns(2)).toBe(2);
    expect(tileColumns(4)).toBe(2);
    expect(tileColumns(6)).toBe(3);
    expect(tileColumns(9)).toBe(3);
    expect(tileColumns(12)).toBe(4);
  });
});

describe("connectionLabel", () => {
  it("상태→라벨, 미지는 원문", () => {
    expect(connectionLabel("connected")).toBe("연결됨");
    expect(connectionLabel("connecting")).toBe("연결 중…");
    expect(connectionLabel("reconnecting")).toBe("재연결 중…");
    expect(connectionLabel("weird")).toBe("weird");
  });
});
