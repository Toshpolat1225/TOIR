const { createClient } = require('@supabase/supabase-js');

const url = 'https://mhhxduteyzumqtkceupt.supabase.co';
const key = 'sb_publishable_gfQBDWe4T7tjOCGmo0K49A_KSrMW-aR';

const supabase = createClient(url, key);

async function test() {
  const { data, error } = await supabase.auth.signInWithPassword({
    email: 'admin@agmk.uz',
    password: 'admin123'
  });

  console.log('DATA:', data);
  console.log('ERROR:', error);
}

test();