import { NextRequest, NextResponse } from "next/server";


const API_BASE_URL = "http://api:8000/api/v1";

async function handleProxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const resolvedParams = await params;
    const path = resolvedParams.path.join("/");
    const url = new URL(request.url);
    const targetUrl = `${API_BASE_URL}/${path}${url.search}`;

    const headers = new Headers(request.headers);
    headers.delete("host"); // Let the fetch API handle the host header

    const fetchOptions: RequestInit = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    // Only add body for methods that allow it
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method)) {
      if (request.body) {
        fetchOptions.body = request.body;
      }
    }

    const response = await fetch(targetUrl, fetchOptions);

    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("content-encoding"); // Let Next.js handle compression

    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("Proxy error:", error);
    return new NextResponse("Internal Server Error", { status: 500 });
  }
}

export const GET = handleProxy;
export const POST = handleProxy;
export const PUT = handleProxy;
export const PATCH = handleProxy;
export const DELETE = handleProxy;
export const OPTIONS = handleProxy;
