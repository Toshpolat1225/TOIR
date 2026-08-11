import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'https://qowgaahijzamnprtfyko.supabase.co',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFvd2dhYWhpanphbW5wcnRmeWtvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE0Njc2MTQsImV4cCI6MjA4NzA0MzYxNH0.zo-bAha0qyNw37yRkitt6f-nF1Gt2hYnanZ5zah-eaA'
)

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
