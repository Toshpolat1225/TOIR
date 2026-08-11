/**
 * Подсказка для Wialon: данные принимает отдельный приёмник на порту 3002.
 * В Wialon укажите URL: http://<IP_сервера>:3002/input
 * Запуск приёмника: npm run wialon
 */

import { NextRequest, NextResponse } from "next/server";

const HELP = "Wialon: use http://<IP>:3002/input and run: npm run wialon";

export async function GET() {
  return NextResponse.json({ ok: true, message: HELP }, { status: 200 });
}

export async function POST(request: NextRequest) {
  try {
    await request.text(); // consume body
  } catch (_) {}
  return NextResponse.json({ ok: true, message: HELP }, { status: 200 });
}
