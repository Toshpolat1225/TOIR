import * as XLSX from 'xlsx'
import { readFileSync } from 'fs'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'https://qowgaahijzamnprtfyko.supabase.co',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFvd2dhYWhpanphbW5wcnRmeWtvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE0Njc2MTQsImV4cCI6MjA4NzA0MzYxNH0.zo-bAha0qyNw37yRkitt6f-nF1Gt2hYnanZ5zah-eaA'
)

// Конвертация Excel-даты (serial number) в строку ДД.ММ.ГГГГ
function excelDateToStr(serial) {
  if (!serial || typeof serial !== 'number') return ''
  const date = new Date(Math.round((serial - 25569) * 86400 * 1000))
  const d = date.getUTCDate().toString().padStart(2, '0')
  const m = (date.getUTCMonth() + 1).toString().padStart(2, '0')
  const y = date.getUTCFullYear()
  return `${d}.${m}.${y}`
}

function readSheet(path) {
  const buf = readFileSync(path)
  const wb  = XLSX.read(buf, { type: 'buffer' })
  return XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: '' })
}

// ── 1. Вагоны (ВС.xlsx) → fixed_assets (asset_type = 'wagon') ─────────────
const wagonsRaw = readSheet('C:\\Users\\User\\Desktop\\ВС.xlsx')

const wagons = wagonsRaw.map((r, i) => ({
  id:           `wagon-${String(r['ивв. Номер'] || i + 1).trim()}`,
  asset_type:   'wagon',
  name:         String(r['Наименование'] || '').trim(),
  series:       String(r['Тип'] || '').trim(),
  depot:        String(r['Марка'] || '').trim(),           // Марка → depot (номер/марка вагона)
  status:       'operational',
  comm_date:    String(r['Ввод экс.'] || '').trim(),       // год ввода в эксплуатацию
  year_built:   String(r['Ввод экс.'] || '').trim(),
  mileage:      String(r['тара вагона'] || '0').trim(),    // тара вагона → mileage
  last_maint:   excelDateToStr(r['дата ремонта']),         // дата ремонта
  next_maint:   '—',
  inv_number:   String(r['ивв. Номер'] || '').trim(),      // инв. номер
  initial_cost: String(r['завю номер'] || '').trim(),      // заводской номер → initial_cost
  owner:        String(r['примечания'] || '').trim(),      // примечания → owner
}))

// ── 2. Электровозы (Электравоз.xlsx) → fixed_assets (asset_type = 'locomotive') ──
const locoRaw = readSheet('C:\\Users\\User\\Desktop\\Электравоз.xlsx')

const locos = locoRaw.map((r, i) => ({
  id:           `loco-${String(r['ивв. Номер'] || i + 1).trim()}`,
  asset_type:   'locomotive',
  name:         String(r['Наименование'] || '').trim(),
  series:       String(r['Тип'] || '').trim(),
  depot:        '',
  status:       'operational',
  comm_date:    '',
  year_built:   '',
  mileage:      '0',
  last_maint:   '—',
  next_maint:   '—',
  inv_number:   String(r['ивв. Номер'] || '').trim(),
  initial_cost: '',
  owner:        '',
}))

const allAssets = [...wagons, ...locos]
console.log(`Подготовлено к импорту: ${wagons.length} вагонов + ${locos.length} электровозов = ${allAssets.length} записей`)

// ── Вставка пачками по 100 ──────────────────────────────────────────────────
const BATCH = 100
let inserted = 0
let errors   = 0

for (let i = 0; i < allAssets.length; i += BATCH) {
  const batch = allAssets.slice(i, i + BATCH)
  const { error } = await supabase
    .from('fixed_assets')
    .upsert(batch, { onConflict: 'id' })

  if (error) {
    console.error(`❌ Ошибка в пачке ${i}–${i + BATCH}:`, error.message)
    errors += batch.length
  } else {
    inserted += batch.length
    process.stdout.write(`\r✓ Загружено: ${inserted}/${allAssets.length}`)
  }
}

console.log(`\n\n═══════════════════════════════`)
console.log(`✅ Импорт завершён`)
console.log(`   Успешно: ${inserted}`)
console.log(`   Ошибок:  ${errors}`)
