"use client";

import { useEffect, useRef, useState } from "react";
import { Contact } from "lucide-react";
import { salesApi } from "@/lib/salesApi";
import { apiClient } from "@/lib/api-client";
import ConsentModal, { type ConsentResult, type ConsentTemplate } from "@/components/desk/ConsentModal";
import { getStoredRefCode } from "@/lib/referralRef";

type MatchType = "PHONE" | "NAME" | "CARD";

export default function DeskCheckin({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [consentTpl, setConsentTpl] = useState<ConsentTemplate | null>(null);
  const [showConsent, setShowConsent] = useState(false);
  const [matchInput, setMatchInput] = useState("");
  const [matchType, setMatchType] = useState<MatchType>("PHONE");
  const [matchBusy, setMatchBusy] = useState(false);
  const cardRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<{ visitor_id: string; match?: { matched?: { name: string; staff_id: string }; candidates?: { staff_id: string; name: string; score: number }[] } } | null>(null);
  const sig = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);

  const draw = (e: React.PointerEvent) => {
    if (!drawing.current || !sig.current) return;
    const r = sig.current.getBoundingClientRect();
    const c = sig.current.getContext("2d")!;
    c.lineWidth = 2; c.lineCap = "round"; c.strokeStyle = "#111";
    c.lineTo(e.clientX - r.left, e.clientY - r.top); c.stroke();
    c.beginPath(); c.moveTo(e.clientX - r.left, e.clientY - r.top);
  };
  const start = (e: React.PointerEvent) => { drawing.current = true; draw(e); };
  const end = () => { drawing.current = false; sig.current?.getContext("2d")?.beginPath(); };

  // 동의 고지문(수집항목·이용목적·보유기간) 사전 로드. 실패 시 모달이 폴백 고지문 사용.
  useEffect(() => {
    let alive = true;
    api.get<ConsentTemplate>("/mh/consent-template")
      .then((t) => { if (alive) setConsentTpl(t); })
      .catch(() => { /* 폴백 고지문 사용 */ });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);

  // 체크인 버튼 → 입력 검증 후 동의팝업 오픈(필수 미동의 시 모달에서 등록 비활성).
  const openConsent = () => {
    if (!name.trim() || !phone.trim()) { alert("성함과 연락처를 입력해 주세요."); return; }
    setShowConsent(true);
  };

  // 동의팝업 확인 → 서명 결합 후 실제 등록 호출(직원매칭·알림은 기존 흐름 유지).
  const submitWithConsent = async (consents: ConsentResult[]) => {
    setShowConsent(false);
    const esign = sig.current?.toDataURL("image/png");
    const payload = consents.map((c) => ({ ...c, esign_uri: esign }));
    try {
      // Phase C — 공유링크(?ref=)로 진입한 방문자면 추천코드를 동봉(백엔드가 자동 visit 퍼널 기록·무파괴).
      const refCode = getStoredRefCode();
      const r = await api.post<{ visitor_id: string }>("/mh/visitors/checkin",
        { name, phone_e164: phone, party_size: 1, consents: payload, ...(refCode ? { ref: refCode } : {}) });
      setResult({ visitor_id: r.visitor_id });
      alert("체크인 완료");
    } catch {
      alert("체크인에 실패했습니다. 필수 동의 여부를 확인해 주세요.");
    }
  };
  const runMatch = async (input_type: MatchType, raw: string) => {
    if (!result?.visitor_id || !raw) return;
    setMatchBusy(true);
    try {
      const r = await api.post<{ matched?: { name: string; staff_id: string }; candidates?: { staff_id: string; name: string; score: number }[] }>(
        "/mh/match", { visitor_id: result.visitor_id, input_type, raw });
      setResult((prev) => (prev ? { ...prev, match: r } : prev));
      if (r.matched) await api.post("/mh/notify", { visitor_id: result.visitor_id, staff_id: r.matched.staff_id });
    } finally { setMatchBusy(false); }
  };
  const match = () => void runMatch(matchType, matchInput.trim());
  // 명함 이미지 업로드 → URL → CARD(OCR) 매칭
  const matchByCard = async (file: File) => {
    if (!result?.visitor_id) return;
    setMatchBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const up = await apiClient.post<{ url: string }>("/uploads/image", { body: fd, useMock: false });
      await runMatch("CARD", up.url);
    } catch { alert("명함 업로드/인식에 실패했습니다."); }
    finally { setMatchBusy(false); if (cardRef.current) cardRef.current.value = ""; }
  };

  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-xl font-black text-[var(--text-primary)]">모델하우스 방문 등록</h1>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="성함"
        className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-[var(--text-primary)]" />
      <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="연락처 (01012345678)"
        className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-[var(--text-primary)]" />
      <div>
        <p className="mb-1 text-sm text-[var(--text-tertiary)]">서명</p>
        <canvas ref={sig} width={380} height={120}
          // @ink-contract-ignore — 서명 캔버스의 종이 배경. 텍스트 자식 없음.
          className="w-full touch-none rounded-lg border border-[var(--line)] bg-white"
          onPointerDown={start} onPointerUp={end} onPointerMove={draw} onPointerLeave={end} />
      </div>
      <button onClick={openConsent} className="w-full rounded-lg bg-[var(--accent-strong)] py-2.5 font-black text-white">체크인 (개인정보 동의)</button>
      {showConsent && (
        <ConsentModal
          template={consentTpl}
          onConfirm={(c) => void submitWithConsent(c)}
          onCancel={() => setShowConsent(false)}
        />
      )}
      {result?.visitor_id && (
        <div className="space-y-2 border-t border-[var(--line)] pt-4">
          <p className="text-sm font-bold text-[var(--text-primary)]">지명 직원 매칭</p>
          <div className="flex overflow-hidden rounded-lg border border-[var(--line)]">
            {([["PHONE", "전화"], ["NAME", "이름"], ["CARD", "명함(OCR)"]] as const).map(([v, lbl]) => (
              <button key={v} onClick={() => setMatchType(v)}
                className={`flex-1 px-2 py-1.5 text-xs font-bold ${matchType === v ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-strong)] text-[var(--text-secondary)]"}`}>{lbl}</button>
            ))}
          </div>
          {matchType === "CARD" ? (
            <>
              <input ref={cardRef} type="file" accept="image/*" capture="environment" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void matchByCard(f); }} />
              <button onClick={() => cardRef.current?.click()} disabled={matchBusy}
                className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-[var(--line-strong)] py-2.5 text-sm font-bold text-[var(--accent-strong)] disabled:opacity-50">
                {matchBusy ? "인식 중…" : (<><Contact className="size-4" aria-hidden />명함 촬영/업로드 → 직원 매칭</>)}
              </button>
            </>
          ) : (
            <div className="flex gap-2">
              <input value={matchInput} onChange={(e) => setMatchInput(e.target.value)}
                placeholder={matchType === "PHONE" ? "직원 연락처(01012345678)" : "직원 이름"}
                className="flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-[var(--text-primary)]" />
              <button onClick={match} disabled={matchBusy} className="rounded-lg bg-emerald-600 px-4 font-bold text-white disabled:opacity-50">{matchBusy ? "…" : "매칭+호출"}</button>
            </div>
          )}
          {result.match?.matched && <p className="text-sm font-semibold text-emerald-400">매칭: {result.match.matched.name} (호출 발송)</p>}
          {result.match?.candidates && (
            <ul className="space-y-1 text-sm text-[var(--text-secondary)]">
              {(result.match.candidates ?? []).map((c) => (
                <li key={c.staff_id} className="flex justify-between">
                  <span>{c.name}</span>
                  <button className="text-[var(--accent-strong)]" onClick={async () => {
                    await api.post("/mh/notify", { visitor_id: result.visitor_id, staff_id: c.staff_id }); alert("호출 발송");
                  }}>호출</button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
