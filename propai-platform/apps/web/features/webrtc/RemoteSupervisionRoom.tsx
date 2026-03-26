"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import type { STTTranscript } from "@/components/cad/types";

type ConnectionStatus = "disconnected" | "connecting" | "connected";

const STATUS_STYLES: Record<ConnectionStatus, { bg: string; text: string; label: string }> = {
  disconnected: { bg: "bg-slate-500/20", text: "text-slate-400", label: "미연결" },
  connecting: { bg: "bg-amber-500/20", text: "text-amber-400", label: "연결 중..." },
  connected: { bg: "bg-emerald-500/20", text: "text-emerald-400", label: "통화 중" },
};

export function RemoteSupervisionRoom() {
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const remoteVideoRef = useRef<HTMLVideoElement>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoOff, setIsVideoOff] = useState(false);

  // STT 회의록 데이터
  const { data: transcripts } = useQuery({
    queryKey: ["webrtc", "transcripts"],
    queryFn: () => apiClient.get<STTTranscript[]>("/webrtc/transcripts"),
    refetchInterval: 5_000,
  });

  // 회의록 자동 스크롤
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcripts]);

  const handleConnect = () => {
    setStatus("connecting");
    // WebRTC 연결 시뮬레이션
    setTimeout(() => setStatus("connected"), 1500);
  };

  const handleDisconnect = () => {
    setStatus("disconnected");
  };

  const statusStyle = STATUS_STYLES[status];

  return (
    <section className="grid gap-6" aria-label="원격 감리 화상회의">
      {/* 상단: 연결 상태 + 컨트롤 */}
      <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
          <div className="flex items-center gap-3">
            <motion.div
              className={`h-3 w-3 rounded-full ${status === "connected" ? "bg-emerald-400" : status === "connecting" ? "bg-amber-400" : "bg-slate-500"}`}
              animate={status === "connecting" ? { opacity: [1, 0.3, 1] } : {}}
              transition={{ duration: 0.8, repeat: Infinity }}
            />
            <span className={`rounded-full ${statusStyle.bg} px-3 py-1 text-xs font-medium ${statusStyle.text}`}>
              {statusStyle.label}
            </span>
            <span className="text-xs text-slate-500 font-mono">
              WebRTC 1.0 · coturn relay
            </span>
          </div>
          <div className="flex gap-2">
            {status === "disconnected" ? (
              <button
                onClick={handleConnect}
                className="rounded-xl bg-emerald-500/20 px-4 py-2 text-sm font-medium text-emerald-400 transition hover:bg-emerald-500/30"
              >
                감리 시작
              </button>
            ) : (
              <>
                <button
                  onClick={() => setIsMuted(!isMuted)}
                  className={`rounded-xl px-3 py-2 text-sm transition ${
                    isMuted ? "bg-red-500/20 text-red-400" : "bg-white/5 text-slate-300 hover:bg-white/10"
                  }`}
                >
                  {isMuted ? "음소거 해제" : "음소거"}
                </button>
                <button
                  onClick={() => setIsVideoOff(!isVideoOff)}
                  className={`rounded-xl px-3 py-2 text-sm transition ${
                    isVideoOff ? "bg-red-500/20 text-red-400" : "bg-white/5 text-slate-300 hover:bg-white/10"
                  }`}
                >
                  {isVideoOff ? "카메라 켜기" : "카메라 끄기"}
                </button>
                <button
                  onClick={handleDisconnect}
                  className="rounded-xl bg-red-500/20 px-4 py-2 text-sm font-medium text-red-400 transition hover:bg-red-500/30"
                >
                  통화 종료
                </button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 영상 + 회의록 */}
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        {/* 영상 영역 */}
        <Card className="overflow-hidden border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
          <CardContent className="p-0">
            <div className="relative aspect-video w-full bg-black/80">
              {/* 리모트 비디오 (메인) */}
              <video
                ref={remoteVideoRef}
                className="h-full w-full object-cover"
                autoPlay
                playsInline
                muted
              />
              {/* 연결 대기 오버레이 */}
              <AnimatePresence>
                {status !== "connected" && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-black/60 backdrop-blur-sm"
                  >
                    <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-white/10 bg-white/5">
                      <svg className="h-8 w-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <p className="text-sm text-slate-400">
                      {status === "connecting" ? "상대방 연결 대기 중..." : "감리 시작 버튼을 눌러 화상 연결을 시작하세요"}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* 로컬 비디오 (PIP) */}
              <div className="absolute bottom-4 right-4 h-28 w-40 overflow-hidden rounded-xl border border-white/10 bg-black/40 shadow-2xl">
                <video
                  ref={localVideoRef}
                  className="h-full w-full object-cover"
                  autoPlay
                  playsInline
                  muted
                />
                {(status !== "connected" || isVideoOff) && (
                  <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80">
                    <span className="text-xs text-slate-500">
                      {isVideoOff ? "카메라 OFF" : "대기"}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* STT 음성 인식 회의록 */}
        <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
          <CardContent className="flex h-full flex-col p-5">
            <CardTitle className="mb-4 flex items-center gap-2 text-base text-slate-200">
              <svg className="h-4 w-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
              음성 인식 회의록
              <span className="ml-auto text-[10px] font-normal text-slate-500">STT 자동 변환</span>
            </CardTitle>
            <div
              className="flex-1 space-y-3 overflow-y-auto pr-1"
              style={{ maxHeight: "420px" }}
              aria-label="회의록 스크롤 영역"
            >
              <AnimatePresence initial={false}>
                {transcripts?.map((t) => (
                  <motion.div
                    key={t.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                    className="rounded-xl border border-white/5 bg-white/[0.02] p-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-cyan-400">{t.speaker}</span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {new Date(t.timestamp).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                      </span>
                    </div>
                    <p className="mt-1.5 text-sm leading-relaxed text-slate-300">{t.text}</p>
                  </motion.div>
                ))}
              </AnimatePresence>
              <div ref={transcriptEndRef} />
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
