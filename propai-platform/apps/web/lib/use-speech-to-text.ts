"use client";

/**
 * 음성 → 텍스트(STT) 훅 — 브라우저 Web Speech API(무비용, 한국어 기본).
 * 설계 의도·검색 등 자연어 입력을 음성으로 받기 위한 공용 훅.
 * 미지원 브라우저는 supported=false → 호출부가 마이크 버튼을 숨기면 됨.
 */

import { useCallback, useEffect, useRef, useState } from "react";

type SpeechToText = {
  supported: boolean;
  listening: boolean;
  error: string | null;
  start: () => void;
  stop: () => void;
};

/* eslint-disable @typescript-eslint/no-explicit-any */
export function useSpeechToText(onResult: (text: string) => void, lang = "ko-KR"): SpeechToText {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<any>(null);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    setSupported(!!SR);
  }, []);

  const start = useCallback(() => {
    if (typeof window === "undefined") return;
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      setError("이 브라우저는 음성 인식을 지원하지 않습니다.");
      return;
    }
    try {
      const rec = new SR();
      rec.lang = lang;
      rec.interimResults = true;
      rec.continuous = false;
      rec.onresult = (e: any) => {
        let transcript = "";
        for (let i = 0; i < e.results.length; i++) transcript += e.results[i][0].transcript;
        if (transcript) onResultRef.current(transcript);
      };
      rec.onerror = (e: any) => {
        setError(e?.error === "not-allowed" ? "마이크 권한이 필요합니다." : "음성 인식 오류");
        setListening(false);
      };
      rec.onend = () => setListening(false);
      recRef.current = rec;
      setError(null);
      setListening(true);
      rec.start();
    } catch (err: any) {
      setError(err?.message || "음성 인식 시작 실패");
      setListening(false);
    }
  }, [lang]);

  const stop = useCallback(() => {
    try {
      recRef.current?.stop();
    } catch {
      /* noop */
    }
    setListening(false);
  }, []);

  return { supported, listening, error, start, stop };
}
