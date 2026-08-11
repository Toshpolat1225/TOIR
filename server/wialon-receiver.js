/**
 * Wialon Receiver — приём данных по пробегу от ретранслятора Wialon.
 * Запуск: npm run wialon
 * URL для Wialon: http://<ваш_IP>:3001/input
 *
 * Формат от Wialon (POST JSON): { "i" или "unitId": id, "nm" или "name": имя, "mileage"/"odo"/"km": пробег в км }
 */

const express = require('express');
const os = require('os');
const { createClient } = require('@supabase/supabase-js');
require('dotenv').config({ path: '.env.local' });

const app = express();
const PORT = process.env.WIALON_PORT || 3002;
const HOST = '0.0.0.0';

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!SUPABASE_URL || !SUPABASE_KEY) {
  console.error('❌ Задайте NEXT_PUBLIC_SUPABASE_URL и NEXT_PUBLIC_SUPABASE_ANON_KEY в .env.local');
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

// Логируем каждый входящий запрос — если строк не появляется, до сервера ничего не доходит
app.use((req, res, next) => {
  const time = new Date().toISOString().split('T')[1].slice(0, 12);
  console.log(`[${time}] ${req.method} ${req.url}`);
  next();
});

app.use(express.json({ limit: '2mb' }));
app.use(express.urlencoded({ extended: true, limit: '2mb' }));
app.use(express.text({ type: 'text/plain', limit: '2mb' }));

const assetCache = new Map();
let lastCache = 0;
const CACHE_TTL = 60000;

function getLocalIP() {
  const ifaces = os.networkInterfaces();
  for (const name of Object.keys(ifaces)) {
    for (const iface of ifaces[name]) {
      if (iface.family === 'IPv4' && !iface.internal) return iface.address;
    }
  }
  return 'localhost';
}

// Извлечь номер агрегата из строки (конец, начало или любая группа 2–4 цифр)
function extractNumber(str) {
  if (!str) return null;
  const s = String(str).trim();
  let m = s.match(/(\d{2,4})\s*$/);   // в конце: "ПЭ-2У 111" → 111
  if (m) return m[1];
  m = s.match(/^\s*(\d{2,4})\b/);     // в начале: "111" или "094"
  if (m) return m[1];
  m = s.match(/\b(\d{2,4})\b/);       // любая группа: "№ 111" или "агрегат 111"
  return m ? m[1] : null;
}

async function refreshCache() {
  if (Date.now() - lastCache < CACHE_TTL && assetCache.size > 0) return;
  try {
    const { data: assets, error } = await supabase
      .from('fixed_assets')
      .select('id, name, wialon_id, asset_type, mileage')
      .in('asset_type', ['locomotive', 'diesel']);
    if (error) {
      console.error('❌ Ошибка загрузки ОС:', error.message);
      return;
    }
    assetCache.clear();
    for (const a of assets || []) {
      if (a.wialon_id) assetCache.set(String(a.wialon_id), a);
      const nameKey = (a.name || '').toLowerCase().trim();
      if (nameKey) assetCache.set(nameKey, a);
      const num = extractNumber(a.name);
      if (num) {
        assetCache.set(`#${num}`, a);
        const numInt = parseInt(num, 10);
        if (!isNaN(numInt)) {
          assetCache.set(`#${numInt}`, a);           // #94 для "094"
          if (num.length <= 3) assetCache.set(`#${String(numInt).padStart(3, '0')}`, a);
        }
      }
    }
    lastCache = Date.now();
    console.log('📦 Кэш ОС:', assetCache.size);
  } catch (e) {
    console.error('❌ Кэш:', e.message);
  }
}

function findAsset(unitId, unitName) {
  const idStr = unitId != null ? String(unitId).trim() : '';
  const nameStr = unitName != null ? String(unitName).trim() : '';
  if (idStr && /^\d+$/.test(idStr)) {
    const byId = assetCache.get(idStr);
    if (byId) return byId;
    const byNumKey = assetCache.get(`#${idStr}`);
    if (byNumKey) return byNumKey;
    const byNumInt = assetCache.get(`#${parseInt(idStr, 10)}`);
    if (byNumInt) return byNumInt;
  }
  const num = extractNumber(idStr) || extractNumber(nameStr);
  if (num) {
    const byNum = assetCache.get(`#${num}`);
    if (byNum) return byNum;
    const byNumInt = assetCache.get(`#${parseInt(num, 10)}`);
    if (byNumInt) return byNumInt;
  }
  const search = (nameStr || idStr).toLowerCase();
  if (search && assetCache.has(search)) return assetCache.get(search);
  if (num) {
    const numVal = parseInt(num, 10);
    if (!isNaN(numVal)) {
      for (const [key, asset] of assetCache.entries()) {
        if (typeof key === 'string' && key.startsWith('#')) {
          if (parseInt(key.slice(1), 10) === numVal) return asset;
        }
      }
    }
  }
  return null;
}

function parsePayload(body) {
  if (!body || typeof body !== 'object') return null;
  const mileageRaw =
    body.mileage ?? body.odo ?? body.odometer ?? body.km ?? body.total_odometer ??
    body.total_km ?? body.run ?? body.total_run ?? body.mileage_km ?? body.odometer_km ?? 0;
  return {
    unitId: body.i ?? body.unitId ?? body.unit_id ?? body.id ?? body.uid ?? body.unit ?? null,
    unitName: body.nm ?? body.name ?? body.unit_name ?? body.na ?? null,
    mileage: parseFloat(mileageRaw) || 0,
    speed: parseFloat(body.speed ?? body.spd ?? body.vel ?? 0) || 0,
  };
}

async function saveData(data, asset) {
  try {
    const now = new Date().toISOString();
    const newMileage = Math.round(data.mileage);
    const currentMileage = parseInt(asset.mileage) || 0;

    const update = {
      wialon_last_sync: now,
      wialon_speed: data.speed,
      wialon_online: true,
    };
    // Пробег от Wialon — источник истины: обновляем при любом переданном значении > 0
    if (data.mileage > 0 && newMileage >= 0) {
      update.mileage = String(newMileage);
      if (newMileage < currentMileage) {
        console.log('📝 Пробег уменьшен (сброс/коррекция):', asset.name, currentMileage, '→', newMileage, 'км');
      }
      // История пробегов для аналитики
      await supabase.from('mileage_history').insert({
        asset_id: asset.id,
        mileage: newMileage,
        source: 'wialon',
      }).then(({ error }) => { if (error) console.warn('mileage_history:', error.message); });
      if (newMileage >= 90) {
        await supabase.from('maintenance_plan').upsert({
          asset_id: asset.id,
          asset_name: asset.name,
          maintenance_type: 'ТО-90',
          status: 'Scheduled',
          trigger_mileage: 90,
          scheduled_date: new Date().toISOString().split('T')[0],
        }, { onConflict: 'asset_id,maintenance_type,trigger_mileage' });
      }
    }

    const { error } = await supabase.from('fixed_assets').update(update).eq('id', asset.id);
    if (error) {
      console.error('❌ Обновление:', error.message);
      return false;
    }
    console.log('✅ Пробег:', asset.name, '—', update.mileage || asset.mileage, 'км');
    return true;
  } catch (e) {
    console.error('❌ Сохранение:', e.message);
    return false;
  }
}

async function handleInput(payload, res) {
  res.status(200).send('OK');
  try {
    if (payload && typeof payload === 'string') {
      try {
        payload = JSON.parse(payload);
      } catch (_) {}
    }
    await refreshCache();
    const data = parsePayload(payload);
    if (!data || (!data.unitId && !data.unitName)) {
      console.log('📥 Запрос без unit_id/unit_name');
      return;
    }
    console.log('📥', data.unitId || data.unitName, '—', data.mileage, 'км');
    const asset = findAsset(data.unitId, data.unitName);
    if (asset) {
      await saveData(data, asset);
    } else {
      console.log('⚠️ Не найден ОС:', data.unitId || data.unitName);
    }
  } catch (e) {
    console.error('❌', e.message);
  }
}

app.post('/input', (req, res) => {
  let body = req.body;
  if (typeof body === 'string' && body.trim()) {
    try {
      body = JSON.parse(body);
    } catch (_) {
    console.log('📨 POST /input тело (как строка):', body.slice(0, 200));
  }
  } else if (body && typeof body === 'object' && Object.keys(body).length) {
    console.log('📨 POST /input', JSON.stringify(body));
  } else {
    console.log('📨 POST /input — тело пустое или не JSON. Content-Type:', req.headers['content-type']);
  }
  handleInput(body, res);
});

app.get('/input', (req, res) => {
  console.log('📨 GET /input', Object.keys(req.query || {}).length ? JSON.stringify(req.query) : '(параметров нет)');
  handleInput(req.query, res);
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', server: 'wialon-receiver', cachedAssets: assetCache.size });
});

app.get('/', (req, res) => {
  const ip = getLocalIP();
  res.send(`
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Wialon Receiver</title></head>
<body>
  <h1>Wialon Receiver — данные по пробегу</h1>
  <p>URL для ретранслятора Wialon: <strong>http://${ip}:${PORT}/input</strong></p>
  <hr>
  <p><strong>Проверка приёма</strong> (должны появиться строки в консоли, где запущен <code>npm run wialon</code>):</p>
  <p>
    <a href="/input?nm=ПЭ-2У%20168&mileage=100" target="_blank" style="margin-right:12px">1. Тест GET (клик)</a>
    <button type="button" onclick="testPost()">2. Тест POST (клик)</button>
  </p>
  <p id="out" style="color:green;font-family:monospace"></p>
  <hr>
  <p>Формат для Wialon: POST/GET, JSON: <code>{"nm":"ПЭ-2У 168","mileage":100}</code></p>
  <p><a href="/health">/health</a></p>
  <script>
    function testPost() {
      document.getElementById('out').textContent = 'Отправка...';
      fetch('/input', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{"nm":"ПЭ-2У 168","mileage":100}' })
        .then(r => r.text()).then(t => { document.getElementById('out').textContent = 'Ответ: ' + t; })
        .catch(e => { document.getElementById('out').textContent = 'Ошибка: ' + e; });
    }
  </script>
</body>
</html>
  `);
});

const server = app.listen(PORT, HOST, () => {
  const ip = getLocalIP();
  console.log(`
════════════════════════════════════════
🚂 WIALON RECEIVER
════════════════════════════════════════
✅ Порт: ${PORT}
📌 URL для Wialon: http://${ip}:${PORT}/input
────────────────────────────────────────
Сервер запущен. Не закрывайте это окно.
Проверка: откройте в браузере http://localhost:${PORT}
и нажмите «Тест GET» или «Тест POST».
════════════════════════════════════════
`);
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error('❌ Порт', PORT, 'уже занят. Задайте другой порт: WIALON_PORT=3003 npm run wialon');
  } else {
    console.error('❌ Ошибка сервера:', err.message);
  }
  process.exit(1);
});
