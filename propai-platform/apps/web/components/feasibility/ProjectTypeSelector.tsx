"use client";

import { Card, CardContent } from "@propai/ui";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";

const MODULE_PRESETS = [
  { code: "M01", label: "재개발", icon: "🏗️" },
  { code: "M02", label: "재건축", icon: "🏢" },
  { code: "M03", label: "역세권개발", icon: "🚇" },
  { code: "M04", label: "지역주택조합", icon: "🏠" },
  { code: "M05", label: "임대협동조합", icon: "🤝" },
  { code: "M06", label: "일반분양", icon: "🏬" },
  { code: "M07", label: "주상복합", icon: "🏙️" },
  { code: "M08", label: "오피스텔", icon: "🏨" },
  { code: "M09", label: "지식산업센터", icon: "🏭" },
  { code: "M10", label: "단독주택", icon: "🏡" },
  { code: "M11", label: "전원주택", icon: "🌳" },
  { code: "M12", label: "타운하우스", icon: "🏘️" },
  { code: "M13", label: "도시형생활", icon: "🌆" },
  { code: "M14", label: "공공임대", icon: "🏛️" },
  { code: "M15", label: "민간리츠", icon: "💰" },
];

export function ProjectTypeSelector() {
  const { selectedModule, setSelectedModule } = useFeasibilityV2Store();

  return (
    <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <CardContent className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          개발 유형
        </h3>
        <div className="space-y-1">
          {MODULE_PRESETS.map((m) => (
            <button
              key={m.code}
              onClick={() => setSelectedModule(m.code)}
              className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                selectedModule === m.code
                  ? "bg-blue-50 text-blue-700 font-medium dark:bg-blue-950 dark:text-blue-300"
                  : "text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800"
              }`}
            >
              <span className="text-base">{m.icon}</span>
              <span className="font-mono text-xs text-slate-400">{m.code}</span>
              <span>{m.label}</span>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
