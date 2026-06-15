/**
 * LiveKit 화상회의 프론트 순수코어 — 룸명(백엔드 정합)·타일 그리드·연결상태 라벨.
 *
 * 실제 연결은 LiveKitRoom 컴포넌트(livekit-client)가, 토큰은 백엔드가 담당. 본 모듈은 DOM/네트워크
 * 무관 순수함수만(vitest 결정론 검증). roomName은 백엔드 livekit_rules.room_name과 동일 규칙.
 */

/** 프로젝트 스코프 룸명 — 백엔드 livekit_rules.room_name과 정합(영숫자·-_만·40자·폴백 main). */
export function roomName(projectId: string, roomKey = "main"): string {
  const safe = [...(roomKey || "")]
    .filter((ch) => /[A-Za-z0-9]/.test(ch) || ch === "-" || ch === "_")
    .join("")
    .slice(0, 40);
  return `proj-${projectId}-${safe || "main"}`;
}

/** 참가자 수 → 타일 그리드 열 수(결정론). 1→1, 2~4→2, 5~9→3, 그 이상→4. */
export function tileColumns(count: number): number {
  if (count <= 1) return 1;
  if (count <= 4) return 2;
  if (count <= 9) return 3;
  return 4;
}

export type ConnState = "disconnected" | "connecting" | "connected" | "reconnecting";

const CONN_LABELS: Record<ConnState, string> = {
  disconnected: "연결 끊김",
  connecting: "연결 중…",
  connected: "연결됨",
  reconnecting: "재연결 중…",
};

/** 연결 상태 → 한글 라벨(미지 상태는 원문 폴백 — 가짜 표기 금지). */
export function connectionLabel(state: string): string {
  return CONN_LABELS[state as ConnState] ?? state;
}
