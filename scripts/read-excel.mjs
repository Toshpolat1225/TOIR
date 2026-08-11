import * as XLSX from 'xlsx'
import { readFileSync } from 'fs'

function readExcel(path) {
  const buf  = readFileSync(path)
  const wb   = XLSX.read(buf, { type: 'buffer' })
  console.log('\n═══════════════════════════════')
  console.log('FILE:', path)
  console.log('Sheets:', wb.SheetNames)
  wb.SheetNames.forEach(name => {
    const ws   = wb.Sheets[name]
    const rows = XLSX.utils.sheet_to_json(ws, { defval: '' })
    console.log(`\n── Sheet: "${name}" (${rows.length} rows) ──`)
    if (rows.length > 0) {
      console.log('Columns:', Object.keys(rows[0]))
      console.log('First 3 rows:')
      rows.slice(0, 3).forEach((r, i) => console.log(`  [${i}]`, JSON.stringify(r, null, 0)))
    }
  })
}

readExcel('C:\\Users\\User\\Desktop\\ВС.xlsx')
readExcel('C:\\Users\\User\\Desktop\\Электравоз.xlsx')
