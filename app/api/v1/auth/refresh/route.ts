import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function POST(request: Request) {
  const payload = await request.json().catch(() => ({}))
  const refreshToken = String(payload.refresh_token ?? "")

  if (!refreshToken) {
    return NextResponse.json({ detail: "Refresh token required." }, { status: 400 })
  }

  const backendResponse = await fetch(`${BACKEND_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })

  const backendData = await backendResponse.json().catch(() => null)

  if (!backendResponse.ok) {
    return NextResponse.json(
      { detail: backendData?.detail || "Refresh failed" },
      { status: backendResponse.status || 401 },
    )
  }

  return NextResponse.json({
    access_token: backendData.access_token,
    refresh_token: backendData.refresh_token,
    token_type: backendData.token_type || "bearer",
    expires_in: backendData.expires_in ?? 1800,
    user: backendData.user ?? null,
  })
}
