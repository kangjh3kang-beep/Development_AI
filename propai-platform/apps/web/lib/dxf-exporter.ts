/**
 * DXF 내보내기 — 브라우저에서 직접 AutoCAD DXF 파일 생성
 *
 * CAD 캔버스의 도형 데이터를 DXF 형식으로 변환하여 다운로드합니다.
 * AutoCAD/Rhino/BricsCAD 등에서 열 수 있습니다.
 */

import type { DesignPayload } from "@/components/cad/types";

export function exportToDXF(payload: DesignPayload): string {
  const S = payload.scale || 10;
  const lines: string[] = [];

  // DXF Header
  lines.push("0", "SECTION", "2", "HEADER");
  lines.push("9", "$ACADVER", "1", "AC1015"); // AutoCAD 2000 format
  lines.push("9", "$INSUNITS", "70", "6"); // meters
  lines.push("0", "ENDSEC");

  // Tables (minimal)
  lines.push("0", "SECTION", "2", "TABLES");
  lines.push("0", "TABLE", "2", "LAYER", "70", "3");
  // Layer 0
  lines.push("0", "LAYER", "2", "0", "70", "0", "62", "7", "6", "CONTINUOUS");
  // Layer A-WALL
  lines.push("0", "LAYER", "2", "A-WALL", "70", "0", "62", "1", "6", "CONTINUOUS");
  // Layer A-TEXT
  lines.push("0", "LAYER", "2", "A-TEXT", "70", "0", "62", "2", "6", "CONTINUOUS");
  lines.push("0", "ENDTAB");
  lines.push("0", "ENDSEC");

  // Entities
  lines.push("0", "SECTION", "2", "ENTITIES");

  // Lines
  for (const ln of payload.lines) {
    const sp = payload.points.find((p) => p.id === ln.startPointId);
    const ep = payload.points.find((p) => p.id === ln.endPointId);
    if (!sp || !ep) continue;

    lines.push("0", "LINE");
    lines.push("8", "A-WALL"); // layer
    lines.push("10", String(sp.x / S)); // start X (meters)
    lines.push("20", String(-sp.y / S)); // start Y (DXF Y is inverted)
    lines.push("30", "0"); // start Z
    lines.push("11", String(ep.x / S)); // end X
    lines.push("21", String(-ep.y / S)); // end Y
    lines.push("31", "0"); // end Z
  }

  // Rectangles as LWPOLYLINE
  for (const rc of payload.rects ?? []) {
    const x = rc.x / S;
    const y = -rc.y / S;
    const w = rc.width / S;
    const h = rc.height / S;

    lines.push("0", "LWPOLYLINE");
    lines.push("8", "A-WALL");
    lines.push("90", "4"); // vertex count
    lines.push("70", "1"); // closed
    lines.push("10", String(x), "20", String(y));
    lines.push("10", String(x + w), "20", String(y));
    lines.push("10", String(x + w), "20", String(y - h));
    lines.push("10", String(x), "20", String(y - h));
  }

  // Circles
  for (const ci of payload.circles ?? []) {
    lines.push("0", "CIRCLE");
    lines.push("8", "A-WALL");
    lines.push("10", String(ci.cx / S));
    lines.push("20", String(-ci.cy / S));
    lines.push("30", "0");
    lines.push("40", String(ci.radius / S));
  }

  // Texts
  for (const tx of payload.texts ?? []) {
    lines.push("0", "TEXT");
    lines.push("8", "A-TEXT");
    lines.push("10", String(tx.x / S));
    lines.push("20", String(-tx.y / S));
    lines.push("30", "0");
    lines.push("40", "0.3"); // text height in meters
    lines.push("1", tx.text);
  }

  // Points
  for (const pt of payload.points) {
    lines.push("0", "POINT");
    lines.push("8", "0");
    lines.push("10", String(pt.x / S));
    lines.push("20", String(-pt.y / S));
    lines.push("30", "0");
  }

  lines.push("0", "ENDSEC");
  lines.push("0", "EOF");

  return lines.join("\n");
}

/**
 * DXF를 브라우저에서 다운로드
 */
export function downloadDXF(payload: DesignPayload, filename = "floor_plan.dxf") {
  const dxfContent = exportToDXF(payload);
  const blob = new Blob([dxfContent], { type: "application/dxf" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
