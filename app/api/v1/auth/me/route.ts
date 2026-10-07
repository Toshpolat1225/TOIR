import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function GET(request: Request) {
  const authorization = request.headers.get("authorization")
  const token = authorization?.match(/^Bearer\s+(.+)$/i)?.[1]

  if (!token) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 })
  }

  const backendResponse = await fetch(`${BACKEND_URL}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  const payload = await backendResponse.json().catch(() => null)

  if (!backendResponse.ok) {
    return NextResponse.json(
      { detail: payload?.detail || "Could not validate credentials." },
      { status: backendResponse.status || 401 },
    )
  }

  return NextResponse.json(payload)
}
