"use client";

/**
 * LiveKit 공용 화상회의 룸 — 회의방(collaboration) + 원격감리(RemoteSupervision) 재사용.
 *
 * 백엔드 /api/v2/livekit/.../token으로 토큰 발급 → livekit-client로 connect → 구독 트랙을 타일로 attach.
 * 권한(can_publish)은 백엔드 VideoGrant(역할 규칙). 미구성/권한 부족 시 503·정직 메시지(크래시 금지).
 * ⚠️ 실연결은 LiveKit Cloud 구성 후 스테이징 검증 대상(키 없이는 입장 시 정직 degrade).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track } from "livekit-client";
import { apiClient } from "@/lib/api-client";

type TokenResp = {
  url: string;
  token: string;
  room: string;
  can_publish: boolean;
  can_record: boolean;
};
type Phase = "idle" | "connecting" | "connected" | "error";

const PHASE_LABEL: Record<Phase, string> = {
  idle: "대기",
  connecting: "연결 중…",
  connected: "연결됨",
  error: "오류",
};

export function LiveKitRoom({
  projectId,
  roomKey = "main",
}: {
  projectId: string;
  roomKey?: string;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [canPublish, setCanPublish] = useState(false);
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const roomRef = useRef<Room | null>(null);
  const tilesRef = useRef<HTMLDivElement | null>(null);

  const attachTrack = useCallback((track: Track) => {
    const el = track.attach();
    if (track.kind === Track.Kind.Audio) {
      el.style.display = "none";
      tilesRef.current?.appendChild(el);
      return;
    }
    (el as HTMLVideoElement).className =
      "w-full rounded-lg bg-black aspect-video object-cover";
    const wrap = document.createElement("div");
    wrap.dataset.trackSid = track.sid ?? "";
    wrap.appendChild(el);
    tilesRef.current?.appendChild(wrap);
  }, []);

  const join = useCallback(async () => {
    setPhase("connecting");
    setError(null);
    try {
      const resp = await apiClient.postV2<TokenResp>(
        `/livekit/projects/${projectId}/rooms/${roomKey}/token`,
      );
      if (!resp?.token || !resp.url) throw new Error("no token");
      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;
      room
        .on(RoomEvent.TrackSubscribed, (track) => attachTrack(track))
        .on(RoomEvent.LocalTrackPublished, (pub) => {
          if (pub.track) attachTrack(pub.track);
        })
        .on(RoomEvent.Disconnected, () => setPhase("idle"));
      await room.connect(resp.url, resp.token);
      setCanPublish(resp.can_publish);
      if (resp.can_publish) {
        await room.localParticipant.enableCameraAndMicrophone();
      }
      setPhase("connected");
    } catch {
      setError("화상회의 연결 실패 — 구성(키)·접근권한·브라우저 카메라 권한을 확인하세요.");
      setPhase("error");
    }
  }, [projectId, roomKey, attachTrack]);

  const leave = useCallback(async () => {
    await roomRef.current?.disconnect();
    roomRef.current = null;
    if (tilesRef.current) tilesRef.current.innerHTML = "";
    setPhase("idle");
  }, []);

  useEffect(() => {
    return () => {
      void roomRef.current?.disconnect();
    };
  }, []);

  const toggleMic = useCallback(async () => {
    const r = roomRef.current;
    if (!r) return;
    const next = !micOn;
    await r.localParticipant.setMicrophoneEnabled(next);
    setMicOn(next);
  }, [micOn]);

  const toggleCam = useCallback(async () => {
    const r = roomRef.current;
    if (!r) return;
    const next = !camOn;
    await r.localParticipant.setCameraEnabled(next);
    setCamOn(next);
  }, [camOn]);

  return (
    <div
      data-testid="livekit-room"
      className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-black text-[var(--text-primary)]">
          화상회의{" "}
          <span className="ml-1 rounded-full bg-[var(--surface)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-hint)]">
            {PHASE_LABEL[phase]}
          </span>
        </h3>
        {phase === "connected" ? (
          <button
            type="button"
            data-testid="livekit-leave"
            onClick={() => void leave()}
            className="rounded-lg bg-[var(--status-error)] px-4 py-1.5 text-[11px] font-black text-white"
          >
            나가기
          </button>
        ) : (
          <button
            type="button"
            data-testid="livekit-join"
            onClick={() => void join()}
            disabled={phase === "connecting"}
            className="rounded-lg bg-[var(--accent-strong)] px-4 py-1.5 text-[11px] font-black uppercase tracking-widest text-white disabled:opacity-40"
          >
            {phase === "connecting" ? "연결 중…" : "입장"}
          </button>
        )}
      </div>

      {error && (
        <p data-testid="livekit-error" className="mb-2 text-xs text-[var(--status-error)]">
          {error}
        </p>
      )}

      <div
        ref={tilesRef}
        data-testid="livekit-tiles"
        className="grid grid-cols-1 gap-2 sm:grid-cols-2"
      />

      {phase === "connected" && canPublish && (
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void toggleMic()}
            className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)]"
          >
            {micOn ? "마이크 끄기" : "마이크 켜기"}
          </button>
          <button
            type="button"
            onClick={() => void toggleCam()}
            className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)]"
          >
            {camOn ? "카메라 끄기" : "카메라 켜기"}
          </button>
        </div>
      )}

      <p className="mt-3 text-[10px] text-[var(--text-hint)]">
        ※ 실연결은 LiveKit Cloud 구성 후 사용 가능(미구성 시 입장은 정직하게 실패 표기).
      </p>
    </div>
  );
}
