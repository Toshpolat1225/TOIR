/**
 * Проверка Wialon Receiver (должен быть запущен: npm run wialon)
 * Запуск: npm run test:wialon
 */

const WIALON_PORT = process.env.WIALON_PORT || 3002;
const BASE = `http://127.0.0.1:${WIALON_PORT}`;

async function get(url) {
  const res = await fetch(url);
  const text = await res.text();
  return { status: res.status, body: text };
}

async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  return { status: res.status, body: text };
}

async function main() {
  console.log('🔍 Проверка Wialon Receiver на', BASE, '\n');

  try {
    const health = await get(`${BASE}/health`);
    console.log('GET /health:', health.status, health.status === 200 ? '✅' : '❌');
    if (health.status === 200) {
      try {
        console.log('   ', JSON.stringify(JSON.parse(health.body), null, 2));
      } catch (_) {
        console.log('   ', health.body);
      }
    }

    const postResult = await post(`${BASE}/input`, {
      i: '12345',
      nm: 'ПЭ-2У 168',
      mileage: 95,
      speed: 0,
    });
    console.log('\nPOST /input (ПЭ-2У 168, 95 км):', postResult.status, postResult.status === 200 ? '✅' : '❌');
    console.log('   Ответ:', postResult.body || '(пусто)');
  } catch (e) {
    console.error('❌ Ошибка:', e.message);
    console.log('\nЗапустите приёмник: npm run wialon');
    process.exit(1);
  }
}

main();
