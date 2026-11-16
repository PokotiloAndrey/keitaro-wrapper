const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const base = process.env.TEST_URL || 'http://127.0.0.1:8766';
const password = process.env.TEST_PASSWORD || 'ui-test-password';
const dom = new JSDOM(fs.readFileSync('app/static/index.html', 'utf8'), {url:base, runScripts:'outside-only'});
const w = dom.window;
w.crypto.randomUUID = crypto.randomUUID;
w.fetch = (url, options={}) => fetch(new URL(url, base), {...options, headers:{...options.headers, Authorization:'Basic '+Buffer.from('admin:'+password).toString('base64')}});
w.eval(fs.readFileSync('app/static/app.js', 'utf8'));
const $ = id => w.document.getElementById(id);
async function waitFor(fn) {
  for(let i=0; i<200; i++) {if(fn()) return; await new Promise(r=>setTimeout(r,25));}
  throw Error('Timeout: '+$('status').textContent);
}
async function click(text) {
  const button=[...w.document.querySelectorAll('button')].find(b=>b.textContent===text && !b.disabled);
  assert.ok(button,text);
  button.click();
  await waitFor(()=>!button.disabled || !button.isConnected);
  await new Promise(r=>setTimeout(r,50));
}
(async()=>{
 await waitFor(()=>$('status').textContent.startsWith('Готово'));
 assert.ok($('mode').textContent.includes('ДЕМО'), 'UI test requires DEMO_MODE=true');
 $('name').value='ui_'+Date.now();
 for(const id of ['offer','domain','group','source']) $(id).value='1';
 $('create').dispatchEvent(new w.Event('submit',{cancelable:true}));
 await waitFor(()=>$('status').textContent.startsWith('Кампания создана'));
 const add=()=>w.document.querySelector('[aria-label="Добавить оффер"]');
 add().value='2'; await click('Добавить');
 assert.ok(w.document.querySelector('article.pending'));
 assert.deepEqual([...w.document.querySelectorAll('td input[type=number]')].map(x=>x.value),['50','50']);
 await click('Применить в Keitaro');
 assert.equal(w.document.querySelectorAll('article.pending').length,0);
 await click('Убрать'); await click('Применить в Keitaro');
 assert.ok([...w.document.querySelectorAll('button')].some(b=>b.textContent==='Вернуть'));
 await click('Вернуть'); await click('Применить в Keitaro');
 assert.deepEqual([...w.document.querySelectorAll('td input[type=number]')].map(x=>x.value),['50','50']);
 add().value='3'; await click('Добавить');
 await click('Отменить черновик');
 assert.equal(w.document.querySelectorAll('td input[type=number]').length,2);
 console.log('UI PASS: create, add, shares, dirty status, push, archive, restore, cancel');
 dom.window.close();
})().catch(e=>{console.error(e);process.exit(1)});
