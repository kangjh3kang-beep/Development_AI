"use client";

import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";

export default function LegalPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-teal-500 border-t-transparent" />
      </div>
    );
  }

  if (!isValidLocale(locale)) {
    return null;
  }

  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  const t = dictionary.modulePlaceholders["legal"];

  return (
    <div className="flex flex-col gap-12 pb-20">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <ModulePlaceholder
          eyebrow={t.eyebrow}
          title={t.title}
          description={t.description}
          statusLabel={runtimeMode}
          localeLabel={locale}
          items={t.items}
        />
      </motion.div>

      <div className="grid gap-10 md:grid-cols-[1fr_1.2fr]">
        {/* Compliance Trackers */}
        <motion.div 
          initial={{ opacity: 0, x: -30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-[3rem] border border-white/5 bg-[#0a0f14]/80 p-10 shadow-2xl backdrop-blur-3xl"
        >
          <div className="flex items-center gap-4 mb-10">
            <div className="h-10 w-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-400">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            </div>
            <h3 className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">건축 제한 분석</h3>
          </div>

          <div className="grid gap-8">
            {[
              { label: "건폐율", limit: "60%", current: "58.2%", progress: 97 },
              { label: "용적률", limit: "300%", current: "298.5%", progress: 99 },
              { label: "높이제한", limit: "80m", current: "75.2m", progress: 94 },
              { label: "일조권", limit: "적용", current: "충족", progress: 100 },
              { label: "조경면적", limit: "15%", current: "15.4%", progress: 100 },
            ].map((item, i) => (
              <div key={item.label} className="group/item">
                <div className="flex items-center justify-between mb-4 px-2">
                  <span className="text-[11px] font-black uppercase tracking-widest text-white/60 group-hover/item:text-teal-400 transition-colors">{item.label}</span>
                  <div className="flex gap-4 items-center">
                    <span className="text-[9px] font-black text-white/20 uppercase tracking-widest">Limit: {item.limit}</span>
                    <span className="text-sm font-black text-white tracking-tight italic">{item.current}</span>
                  </div>
                </div>
                <div className="relative h-2 w-full rounded-full bg-white/5 overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${item.progress}%` }}
                    transition={{ delay: 0.5 + i * 0.1, duration: 1 }}
                    className={`h-full bg-gradient-to-r ${item.progress >= 99 ? "from-red-500 to-orange-500 shadow-[0_0_15px_#ef4444]" : "from-teal-500 to-indigo-500 shadow-[0_0_15px_#14b8a6]"}`}
                  />
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Regulatory Checklist */}
        <motion.div 
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-[3rem] border border-white/5 bg-[#0a0f14]/80 p-10 shadow-2xl backdrop-blur-3xl"
        >
           <div className="flex items-center gap-4 mb-10">
            <div className="h-10 w-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-400">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
            </div>
            <h3 className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">규제 체크리스트</h3>
          </div>

          <div className="grid gap-4">
            {[
              { label: "용도지역 조례 적합성 검토", checked: true, status: "Verified" },
              { label: "건축법 제 21조 준수 여부", checked: true, status: "Verified" },
              { label: "소방법 화재 안전 등급", checked: false, status: "Pending" },
              { label: "환경영향평가 대상 여부", checked: true, status: "N/A" },
              { label: "지능형 건축물 인증 요건", checked: false, status: "In Progress" },
              { label: "주차장법 시행령 적합", checked: true, status: "Verified" },
              { label: "과밀부담금 산정 완료", checked: false, status: "Pending" },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between gap-6 rounded-3xl bg-white/5 px-8 py-6 border border-white/5 transition-all hover:bg-white/10 group/row">
                <div className="flex items-center gap-6">
                  <div className={`flex h-8 w-8 items-center justify-center rounded-xl border-2 transition-all ${
                    item.checked 
                    ? "border-teal-500 bg-teal-500 text-white shadow-[0_0_10px_rgba(20,184,166,0.3)]" 
                    : "border-white/10 text-transparent"
                  }`}>
                    {item.checked && <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>}
                  </div>
                  <span className={`text-sm font-bold tracking-tight ${item.checked ? "text-white" : "text-white/30 italic"}`}>{item.label}</span>
                </div>
                <span className={`text-[9px] font-black uppercase tracking-widest px-3 py-1 rounded-lg ${
                  item.status === "Verified" ? "bg-teal-500/10 text-teal-400" :
                  item.status === "Pending" ? "bg-red-500/10 text-red-400" :
                  "bg-white/10 text-white/40"
                }`}>
                  {item.status}
                </span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
