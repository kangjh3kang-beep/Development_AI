"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button, Input, Select } from "@propai/ui";
import { useGenerationStore, type GenerationTemplateType } from "@/store/useGenerationStore";
import type { CommonDictionary } from "@/i18n/get-dictionary";

interface ProjectGenerationWizardProps {
  dictionary: CommonDictionary;
  projectId: string;
  areaSqm: number;
  floors: number;
}

export function ProjectGenerationWizard({
  dictionary,
  projectId,
  areaSqm,
  floors,
}: ProjectGenerationWizardProps) {
  const t = dictionary.pages.generation;
  
  const {
    currentTemplate,
    inputs,
    isGenerating,
    status,
    setTemplate,
    setInputValue,
    startGeneration,
    errorMessage,
  } = useGenerationStore();

  const handleTemplateChange = (template: GenerationTemplateType) => {
    setTemplate(template);
  };

  const handleInputChange = (key: string, value: any) => {
    setInputValue(key, value);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isGenerating) return;
    
    // Trigger generation via Zustand
    void startGeneration(projectId, areaSqm, floors, false);
  };

  const STRUCTURE_OPTIONS = [
    { label: "RC (철근콘크리트)", value: "RC" },
    { label: "SRC (철골철근콘크리트)", value: "SRC" },
    { label: "SC (철골조)", value: "SC" },
  ];

  const STYLE_OPTIONS = [
    { label: "Modern", value: "modern" },
    { label: "Minimal", value: "minimal" },
    { label: "Classic", value: "classic" },
  ];

  const RAMP_OPTIONS = [
    { label: t.rampSpiral, value: "spiral" },
    { label: t.rampLinear, value: "linear" },
  ];

  const LEED_OPTIONS = [
    { label: t.leedSilver, value: "silver" },
    { label: t.leedGold, value: "gold" },
    { label: t.leedPlatinum, value: "platinum" },
  ];

  const INSULATION_OPTIONS = [
    { label: t.insulationGrade.replace("{grade}", "1"), value: "1" },
    { label: t.insulationGrade.replace("{grade}", "2"), value: "2" },
    { label: t.insulationGrade.replace("{grade}", "3"), value: "3" },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* ── Template Select Tabs ── */}
      <div className="relative rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-strong)]/40 p-2 shadow-[var(--shadow-lg)] backdrop-blur-2xl">
        <div className="grid grid-cols-3 gap-2">
          {(["residential", "logistics", "eco-office"] as GenerationTemplateType[]).map((temp) => {
            const isActive = currentTemplate === temp;
            return (
              <button
                key={temp}
                onClick={() => handleTemplateChange(temp)}
                className={`relative rounded-2xl py-4 px-3 text-xs font-black uppercase tracking-wider transition-all duration-300 ${
                  isActive
                    ? "text-[var(--accent-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-md)] border border-[var(--accent-strong)]/20"
                    : "text-[var(--text-hint)] hover:text-[var(--text-secondary)]"
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeTabGlow"
                    className="absolute inset-0 -z-10 rounded-2xl bg-[var(--accent-soft)]/20 blur-md"
                  />
                )}
                {temp === "residential" && t.residential}
                {temp === "logistics" && t.logistics}
                {temp === "eco-office" && t.ecoOffice}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Wizard Form ── */}
      <div className="relative group">
        <div className="absolute -inset-1 bg-gradient-to-r from-[var(--accent)]/10 to-indigo-500/10 rounded-[2.5rem] blur-xl opacity-20 group-hover:opacity-40 transition duration-1000" />
        <div className="relative rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-8 shadow-[var(--shadow-2xl)]">
          <div className="mb-6 flex justify-between items-center">
            <h4 className="text-sm font-black uppercase tracking-[0.2em] text-[var(--text-hint)]">
              {t.inputsTitle}
            </h4>
            <span className="text-[10px] font-mono text-[var(--accent-strong)] bg-[var(--accent-soft)] px-3 py-1.5 rounded-xl border border-[var(--accent-strong)]/10">
              ID: {currentTemplate}
            </span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentTemplate}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -15 }}
                transition={{ duration: 0.3 }}
                className="grid gap-6 md:grid-cols-2"
              >
                {/* ── Residential Inputs ── */}
                {currentTemplate === "residential" && (
                  <>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.unitsLabel}
                      </label>
                      <Input
                        type="number"
                        min="1"
                        value={inputs.targetUnits || ""}
                        onChange={(e) => handleInputChange("targetUnits", e.target.value)}
                        placeholder="예: 120"
                        required
                        className="font-bold"
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.parkingLabel}
                      </label>
                      <Input
                        type="number"
                        step="0.1"
                        min="0.1"
                        value={inputs.parkingRatio || ""}
                        onChange={(e) => handleInputChange("parkingRatio", e.target.value)}
                        placeholder="예: 1.2"
                        required
                        className="font-bold"
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.efficiencyLabel}
                      </label>
                      <Input
                        type="number"
                        min="10"
                        max="100"
                        value={inputs.targetEfficiency || ""}
                        onChange={(e) => handleInputChange("targetEfficiency", e.target.value)}
                        placeholder="예: 75"
                        required
                        className="font-bold"
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.styleLabel}
                      </label>
                      <Select
                        value={inputs.style || "modern"}
                        onValueChange={(val) => handleInputChange("style", val)}
                        options={STYLE_OPTIONS}
                      />
                    </div>
                  </>
                )}

                {/* ── Logistics Inputs ── */}
                {currentTemplate === "logistics" && (
                  <>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.docksLabel}
                      </label>
                      <Input
                        type="number"
                        min="1"
                        value={inputs.dockCount || ""}
                        onChange={(e) => handleInputChange("dockCount", e.target.value)}
                        placeholder="예: 24"
                        required
                        className="font-bold"
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.clearHeightLabel}
                      </label>
                      <Input
                        type="number"
                        min="3"
                        max="30"
                        value={inputs.clearHeight || ""}
                        onChange={(e) => handleInputChange("clearHeight", e.target.value)}
                        placeholder="예: 10"
                        required
                        className="font-bold"
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.loadLabel}
                      </label>
                      <Input
                        type="number"
                        min="1"
                        max="50"
                        value={inputs.floorLoad || ""}
                        onChange={(e) => handleInputChange("floorLoad", e.target.value)}
                        placeholder="예: 5"
                        required
                        className="font-bold"
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.rampLabel}
                      </label>
                      <Select
                        value={inputs.rampType || "spiral"}
                        onValueChange={(val) => handleInputChange("rampType", val)}
                        options={RAMP_OPTIONS}
                      />
                    </div>
                  </>
                )}

                {/* ── Eco-Office Inputs ── */}
                {currentTemplate === "eco-office" && (
                  <>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.pvRatioLabel}
                      </label>
                      <Input
                        type="number"
                        min="1"
                        max="100"
                        value={inputs.pvRatio || ""}
                        onChange={(e) => handleInputChange("pvRatio", e.target.value)}
                        placeholder="예: 35"
                        required
                        className="font-bold"
                      />
                    </div>
                    <div className="grid gap-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.insulationLabel}
                      </label>
                      <Select
                        value={inputs.insulationGrade || "1"}
                        onValueChange={(val) => handleInputChange("insulationGrade", val)}
                        options={INSULATION_OPTIONS}
                      />
                    </div>
                    <div className="grid gap-2 col-span-2">
                      <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                        {t.leedLabel}
                      </label>
                      <Select
                        value={inputs.leedTarget || "gold"}
                        onValueChange={(val) => handleInputChange("leedTarget", val)}
                        options={LEED_OPTIONS}
                      />
                    </div>
                  </>
                )}

                {/* ── Common Structure Select ── */}
                <div className="grid gap-2 col-span-2 border-t border-[var(--line-strong)]/40 pt-6">
                  <label className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                    {t.structureType}
                  </label>
                  <Select
                    value={inputs.structureType || "RC"}
                    onValueChange={(val) => handleInputChange("structureType", val)}
                    options={STRUCTURE_OPTIONS}
                  />
                </div>
              </motion.div>
            </AnimatePresence>

            {/* Error Message */}
            {errorMessage && (
              <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-xs font-semibold text-red-400">
                {errorMessage}
              </div>
            )}

            {/* Submit Action Button */}
            <button
              type="submit"
              disabled={isGenerating}
              className="w-full relative overflow-hidden rounded-2xl py-4.5 text-xs font-black uppercase tracking-wider transition-all duration-300 flex items-center justify-center gap-2.5
              disabled:opacity-50 disabled:cursor-not-allowed
              bg-gradient-to-r from-[var(--accent-strong)] to-[#0c6b80] text-white shadow-lg shadow-[var(--shadow-glow)] hover:shadow-xl hover:scale-[1.01] active:scale-[0.99]"
            >
              {isGenerating ? (
                <>
                  <span className="h-4.5 w-4.5 border-3 border-white/20 border-t-white rounded-full animate-spin" />
                  {t.runningAction}
                </>
              ) : (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>
                  {t.startAction}
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
