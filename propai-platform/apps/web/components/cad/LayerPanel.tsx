"use client";

import { useCadStore } from "@/store/use-cad-store";

/** KS A ISO 13567 기반 레이어 관리 패널. */
export default function LayerPanel() {
  const layers = useCadStore((s) => s.layers);
  const toggleVis = useCadStore((s) => s.toggleLayerVisibility);
  const toggleLock = useCadStore((s) => s.toggleLayerLock);

  return (
    <div className="border rounded-lg bg-white p-3 text-sm">
      <h3 className="font-bold text-xs mb-2 text-gray-600 uppercase tracking-wide">
        Layers
      </h3>
      <ul className="space-y-1">
        {layers.map((layer) => (
          <li
            key={layer.name}
            className="flex items-center gap-2 py-1 px-1 rounded hover:bg-gray-50"
          >
            {/* 색상 칩 */}
            <span
              className="inline-block w-3 h-3 rounded-sm border border-gray-300"
              style={{ backgroundColor: layer.color }}
            />

            {/* 레이어명 */}
            <span
              className={`flex-1 font-mono text-xs ${
                layer.visible ? "text-gray-800" : "text-gray-400 line-through"
              }`}
            >
              {layer.name}
            </span>

            {/* 가시성 토글 */}
            <button
              onClick={() => toggleVis(layer.name)}
              className="text-xs px-1 hover:bg-gray-200 rounded"
              title={layer.visible ? "숨기기" : "보이기"}
            >
              {layer.visible ? "👁" : "—"}
            </button>

            {/* 잠금 토글 */}
            <button
              onClick={() => toggleLock(layer.name)}
              className="text-xs px-1 hover:bg-gray-200 rounded"
              title={layer.locked ? "잠금 해제" : "잠금"}
            >
              {layer.locked ? "🔒" : "🔓"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
