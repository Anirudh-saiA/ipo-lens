import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api";

// Forwards a question to the backend, so the browser never calls the API directly.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) return NextResponse.json({ detail: "Bad document id" }, { status: 400 });
  const body = (await request.json()) as { question?: unknown };
  if (typeof body.question !== "string") {
    return NextResponse.json({ detail: "Question missing" }, { status: 400 });
  }
  try {
    const response = await fetch(`${API_URL}/documents/${id}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: body.question }),
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "IPO Lens API is not reachable" }, { status: 503 });
  }
}
