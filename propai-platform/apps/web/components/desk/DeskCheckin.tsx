"use client";

import { useRef, useState } from "react";
import { salesApi } from "@/lib/salesApi";

const CONSENTS = [
  { type: "REQUIRED", label: "[필수] 방문/상담 관리 목적 개인정보 수집·이용" },
  { type: "MARKETING", label: "[선택] 분양 정보 마케팅 활용" },
  { type: "THIRD_PARTY", label: "[선택] 시행사/대행사 제3자 제공" },
];

export default function DeskCheckin({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [agree, setAgree] = useState<Record<string, boolean>>({ REQUIRED: false });
  const [matchInput, setMatchInput] = useState("");
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

  const submit = async () => {
    if (!agree.REQUIRED) { alert("필수 동의가 필요합니다."); return; }
    const esign = sig.current?.toDataURL("image/png");
    const consents = CONSENTS.map((c) => ({ type: c.type, agreed: !!agree[c.type], esign_uri: esign, agreed_at: new Date().toISOString() }));
    const r = await api.post<{ visitor_id: string }>("/mh/visitors/checkin", { name, phone_e164: phone, party_size: 1, consents });
    setResult({ visitor_id: r.visitor_id });
    alert("체크인 완료");
  };
  const match = async () => {
    if (!result?.visitor_id) return;
    const r = await api.post<{ matched?: { name: string; staff_id: string }; candidates?: { staff_id: string; name: string; score: number }[] }>(
      "/mh/match", { visitor_id: result.visitor_id, input_type: "PHONE", raw: matchInput });
    setResult({ ...result, match: r });
    if (r.matched) await api.post("/mh/notify", { visitor_id: result.visitor_id, staff_id: r.matched.staff_id });
  };

  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-xl font-black text-[var(--text-primary)]">모델하우스 방문 등록</h1>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="성함"
        className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-[var(--text-primary)]" />
      <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="연락처 (01012345678)"
        className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-[var(--text-primary)]" />
      <div className="space-y-2">
        {CONSENTS.map((c) => (
          <label key={c.type} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
            <input type="checkbox" checked={!!agree[c.type]} onChange={(e) => setAgree({ ...agree, [c.type]: e.target.checked })} className="mt-1" />
            <span>{c.label}</span>
          </label>
        ))}
      </div>
      <div>
        <p className="mb-1 text-sm text-[var(--text-tertiary)]">서명</p>
        <canvas ref={sig} width={380} height={120}
          className="w-full touch-none rounded-lg border border-[var(--line)] bg-white"
          onPointerDown={start} onPointerUp={end} onPointerMove={draw} onPointerLeave={end} />
      </div>
      <button onClick={submit} className="w-full rounded-lg bg-[var(--accent-strong)] py-2.5 font-black text-white">체크인</button>
      {result?.visitor_id && (
        <div className="space-y-2 border-t border-[var(--line)] pt-4">
          <p className="text-sm font-bold text-[var(--text-primary)]">지명 직원 매칭</p>
          <div className="flex gap-2">
            <input value={matchInput} onChange={(e) => setMatchInput(e.target.value)} placeholder="직원 연락처"
              className="flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-[var(--text-primary)]" />
            <button onClick={match} className="rounded-lg bg-emerald-600 px-4 font-bold text-white">매칭+호출</button>
          </div>
          {result.match?.matched && <p className="text-sm font-semibold text-emerald-400">매칭: {result.match.matched.name} (호출 발송)</p>}
          {result.match?.candidates && (
            <ul className="space-y-1 text-sm text-[var(--text-secondary)]">
              {result.match.candidates.map((c) => (
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
