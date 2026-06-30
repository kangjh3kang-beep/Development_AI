import { NextRequest } from "next/server";

const VWORLD_WMTS_BASE = "https://api.vworld.kr/req/wmts/1.0.0";
const SUPPORTED_LAYERS = new Set(["Base", "gray", "midnight", "Hybrid", "Satellite"]);

type RouteContext = {
  params: Promise<{
    layer: string;
    z: string;
    y: string;
    x: string;
  }>;
};

function vworldKey(): string {
  return (process.env.VWORLD_API_KEY || process.env.NEXT_PUBLIC_VWORLD_API_KEY || "").trim();
}

export async function GET(_request: NextRequest, context: RouteContext) {
  const { layer, z, y, x } = await context.params;
  const key = vworldKey();
  const cleanLayer = SUPPORTED_LAYERS.has(layer) ? layer : "Base";
  const cleanX = x.replace(/\.png$/i, "");

  if (!key) {
    return new Response("VWORLD_API_KEY is not configured", {
      status: 503,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  }

  const targetUrl = `${VWORLD_WMTS_BASE}/${encodeURIComponent(key)}/${cleanLayer}/${z}/${y}/${cleanX}.png`;

  try {
    const resp = await fetch(targetUrl, {
      headers: { Referer: "https://www.4t8t.net" },
      next: { revalidate: 60 * 60 * 24 },
    });
    if (!resp.ok) {
      return new Response(`VWorld WMTS failed: ${resp.status}`, {
        status: resp.status,
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-store",
        },
      });
    }
    const buf = await resp.arrayBuffer();
    return new Response(buf, {
      status: 200,
      headers: {
        "Content-Type": resp.headers.get("content-type") ?? "image/png",
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
      },
    });
  } catch (error) {
    return new Response(`VWorld WMTS proxy failed: ${String(error)}`, {
      status: 502,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  }
}
