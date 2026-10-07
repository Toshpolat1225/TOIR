import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function POST(request: Request) {
  const payload = await request.json().catch(() => ({}))

  const backendResponse = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: String(payload.email ?? "").trim().toLowerCase(),
      password: String(payload.password ?? ""),
    }),
  })

  const backendData = await backendResponse.json().catch(() => null)

  if (!backendResponse.ok) {
    return NextResponse.json(
      { detail: backendData?.detail || "Authentication failed" },
      { status: backendResponse.status || 401 },
    )
  }

  const accessToken = backendData?.access_token
  const refreshToken = backendData?.refresh_token
  if (!accessToken) {
    return NextResponse.json({ detail: "Authentication token was not returned." }, { status: 401 })
  }

  const meResponse = await fetch(`${BACKEND_URL}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  const profile = await meResponse.json().catch(() => null)

  if (!meResponse.ok || !profile) {
    return NextResponse.json(
      { detail: profile?.detail || "Could not load current user profile." },
      { status: meResponse.status || 401 },
    )
  }

  return NextResponse.json({
    access_token: accessToken,
    refresh_token: refreshToken,
    token_type: "bearer",
    expires_in: backendData?.expires_in ?? 1800,
    user: profile,
  })
}
