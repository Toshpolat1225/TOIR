import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.SUPABASE_URL
const supabaseKey = process.env.SUPABASE_KEY
if (!supabaseUrl || !supabaseKey) {
  throw new Error('Set SUPABASE_URL and SUPABASE_KEY environment variables before running this script.')
}
const supabase = createClient(supabaseUrl, supabaseKey)

// Общий счёт
const { count: total } = await supabase.from('fixed_assets').select('*', { count: 'exact', head: true })
const { count: locos } = await supabase.from('fixed_assets').select('*', { count: 'exact', head: true }).eq('asset_type', 'locomotive')
const { count: wagons } = await supabase.from('fixed_assets').select('*', { count: 'exact', head: true }).eq('asset_type', 'wagon')

console.log(`Всего в БД:    ${total}`)
console.log(`Локомотивы:    ${locos}`)
console.log(`Вагоны:        ${wagons}`)

// Первые 5 локомотивов
const { data: locoList } = await supabase.from('fixed_assets').select('id,name,series,inv_number,asset_type').eq('asset_type', 'locomotive').limit(5)
console.log('\nПервые 5 локомотивов:')
locoList?.forEach(r => console.log(' ', JSON.stringify(r)))

// Проверка дублей по inv_number
const { data: all } = await supabase.from('fixed_assets').select('id,inv_number,asset_type').eq('asset_type', 'locomotive')
const ids = all?.map(r => r.id) ?? []
const unique = new Set(ids)
console.log(`\nЛокомотивов в БД: ${all?.length}, уникальных ID: ${unique.size}`)

// Дубли инв. номеров
const invNums = all?.map(r => r.inv_number) ?? []
const dupInv = invNums.filter((v, i) => invNums.indexOf(v) !== i)
if (dupInv.length > 0) console.log('⚠ Дублирующиеся инв. номера:', dupInv)
else console.log('✓ Дублирующихся инв. номеров нет')
