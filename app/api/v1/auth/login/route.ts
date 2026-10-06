import { createClient } from "@supabase/supabase-js"
import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"

export async function POST(request: Request) {
  const { email, password } = await request.json()
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { auth: { persistSession: false, autoRefreshToken: false } },
  )

  const { data, error } = await supabase.auth.signInWithPassword({
    email: String(email ?? "").trim().toLowerCase(),
    password: String(password ?? ""),
  })

  if (error) {
    const status = error.code === "email_not_confirmed" ? 403 : 401
    return NextResponse.json({ detail: error.message }, { status })
  }
  if (!data.session) {
    return NextResponse.json({ detail: "Authentication session was not created." }, { status: 401 })
  }

  const { data: profile, error: profileError } = await supabase
    .from("profiles")
    .select("id, email, full_name, role, section")
    .eq("id", data.user.id)
    .maybeSingle()

  if (profileError) {
    return NextResponse.json({ detail: profileError.message }, { status: 500 })
  }
  if (!profile) {
    return NextResponse.json({ detail: "User profile was not found." }, { status: 404 })
  }

  return NextResponse.json({
    access_token: data.session.access_token,
    refresh_token: data.session.refresh_token,
    token_type: "bearer",
    user: profile,
  })
}
