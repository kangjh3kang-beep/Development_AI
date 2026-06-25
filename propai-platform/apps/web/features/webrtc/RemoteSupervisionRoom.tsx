"use client";

/**
 * 원격 감리 화상회의 — 실 화상은 공용 LiveKitRoom(T6: 시뮬레이션 제거·정직).
 *
 * 기존 setTimeout 가짜 connected 시뮬레이션을 제거하고 LiveKitRoom(백엔드 토큰·실 연결)을 재사용한다.
 * 룸은 프로젝트 스코프 'supervision'. 실연결은 LiveKit Cloud 구성 후 동작(미구성 시 정직 degrade).
 *
 * ⚠️ STT 회의록 패널은 **백엔드 STT 파이프라인 미구현** — /webrtc/transcripts는 mock(데모) 전용이며
 * live 모드에선 빈 패널(404)로 표시된다. 따라서 패널을 '데모(STT 미구현)'로 정직 표기한다(가짜 자동변환
 * 표방 금지). 실 STT 구현 시 이 표기를 갱신한다.
 */

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import type { STTTranscript } from "@/components/cad/types";
import { LiveKitRoom } from "@/features/webrtc/LiveKitRoom";

export function RemoteSupervisionRoom({ projectId }: { projectId: string }) {
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // STT 회의록 데이터(폴링) — 화상연결과 독립.
  const { data: transcripts } = useQuery({
    queryKey: ["webrtc", "transcripts"],
    queryFn: () => apiClient.get<STTTranscript[]>("/webrtc/transcripts"),
    refetchInterval: 5_000,
  });

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcripts]);

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0" aria-label="원격 감리 화상회의">
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        {/* 실 화상회의 — 공용 LiveKitRoom(시뮬레이션 제거) */}
        <LiveKitRoom projectId={projectId} roomKey="supervision" />

        {/* STT 음성 인식 회의록(유지) */}
        <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
          <CardContent className="flex h-full flex-col p-5">
            <CardTitle className="mb-4 flex items-center gap-2 text-base text-slate-200">
              <svg className="h-4 w-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
              음성 인식 회의록
              <span className="ml-auto rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-400">데모 · STT 백엔드 미구현</span>
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
