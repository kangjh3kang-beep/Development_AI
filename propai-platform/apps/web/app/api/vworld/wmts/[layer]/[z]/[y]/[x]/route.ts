import { NextRequest } from "next/server";
import { proxyVWorldWmts } from "@/lib/vworld-wmts-proxy";

type RouteContext = {
  params: Promise<{
    layer: string;
    z: string;
    y: string;
    x: string;
  }>;
};

export async function GET(_request: NextRequest, context: RouteContext) {
  return proxyVWorldWmts(await context.params);
}
