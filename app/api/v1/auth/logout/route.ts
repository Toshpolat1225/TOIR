import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function POST(request: Request) {
  const payload = await request.json().catch(() => ({}))
  const refreshToken = String(payload.refresh_token ?? "")

  if (!refreshToken) {
    return NextResponse.json({ detail: "Refresh token required." }, { status: 400 })
  }

  const backendResponse = await fetch(`${BACKEND_URL}/api/v1/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })

  const backendData = await backendResponse.json().catch(() => null)

  if (!backendResponse.ok) {
    return NextResponse.json(
      { detail: backendData?.detail || "Logout failed" },
      { status: backendResponse.status || 400 },
    )
  }

  return new NextResponse(null, { status: 204 })
}
