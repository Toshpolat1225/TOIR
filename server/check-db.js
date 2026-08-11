const { createClient } = require('@supabase/supabase-js');
require('dotenv').config({ path: '.env.local' });

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL, 
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);

async function check() {
  const { data, error } = await supabase
    .from('fixed_assets')
    .select('name, mileage, wialon_online, wialon_speed, wialon_last_sync')
    .in('asset_type', ['locomotive', 'diesel'])
    .not('mileage', 'eq', '0')
    .not('mileage', 'is', null)
    .limit(10);

  if (error) {
    console.error('Error:', error.message);
    return;
  }

  console.log('\n=== ОС с пробегами из Wialon ===\n');
  
  if (!data || data.length === 0) {
    console.log('Пока нет данных с пробегами');
    return;
  }

  data.forEach(a => {
    const online = a.wialon_online ? '🟢 Online' : '⚪ Offline';
    const sync = a.wialon_last_sync ? new Date(a.wialon_last_sync).toLocaleString('ru-RU') : 'никогда';
    console.log(`${online} ${a.name}`);
    console.log(`   Пробег: ${a.mileage} км`);
    console.log(`   Скорость: ${a.wialon_speed || 0} км/ч`);
    console.log(`   Синхр.: ${sync}\n`);
  });
}

check();
