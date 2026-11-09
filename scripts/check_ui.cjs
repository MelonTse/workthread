/* Invoke through check_ui.py: it owns and removes the synthetic server workspace. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.WORKTHREAD_PLAYWRIGHT || 'playwright');
const url = process.env.WORKTHREAD_UI_TEST_URL;
if (!url || !process.env.WORKTHREAD_UI_OUTPUT) throw Error('Run check_ui.py to create an isolated test server');
const out = process.env.WORKTHREAD_UI_OUTPUT;
const results = [], errors = [];
let browser;
const check = (name, value) => {assert.ok(value, name);results.push(name);};
(async () => {
 browser = await chromium.launch(process.env.WORKTHREAD_BROWSER ? {executablePath:process.env.WORKTHREAD_BROWSER} : {});
 const p = await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});
 p.on('pageerror',e=>errors.push(e.message));
 p.on('console',m=>{if(m.type()==='error' && !m.text().includes('409 (CONFLICT)')) errors.push(m.text());});
 // A failed initial snapshot used to leave every navigation target blank.
 const cold = await browser.newPage();
 const renderErrors = [];
 cold.on('pageerror', error => renderErrors.push(error.message));
 const snapshotRoute = '**/api/v1/snapshot?summary=1';
 const failSnapshot = route => route.fulfill({status:503,
   contentType:'application/json',body:JSON.stringify({error:'合成读取超时'})});
 await cold.route(snapshotRoute, failSnapshot);
 await cold.goto(url);
 await cold.waitForSelector('#retry-load:visible');
 for (const view of ['mail','knowledge','todos','settings']) {
   await cold.locator('nav [data-view='+view+']').click();
   check('cold read failure offers retry on '+view,await cold.locator('#retry-load').isVisible());
 }
 await cold.waitForSelector('#update-status:text("当前版本")');
 await cold.unroute(snapshotRoute);
 await cold.locator('#retry-load').click();
 await cold.waitForSelector('#health-check:visible');
 check('can recover initial load without a browser refresh',!renderErrors.length);
 await cold.route(snapshotRoute, failSnapshot);
 await cold.locator('#queue-ai').click(); // Settings' refresh action
 await cold.getByText('刷新失败，当前显示上次读取的数据。',{exact:false}).waitFor();
 await cold.locator('nav [data-view=todos]').click();
 check('last successful snapshot remains navigable during a failed refresh',await cold.locator('.todo-row').first().isVisible());
 await cold.close();
 await p.goto(url);
 await p.waitForSelector('.todo-row');
 async function api(route,method='GET',body) {
   return p.evaluate(async({route,method,body})=>{
    const r=await fetch('/api/v1'+route,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name=csrf-token]').content},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await r.json();if(!r.ok)throw Error(JSON.stringify(data));return data;
   },{route,method,body});
 }
 const make = (title,status,priority) => api('/todos','POST',{title,raw_input:title,no_due_date:true,due_date:null,status,priority});
 const a=await make('UI 合成事项 A · '+ '长标题用于验证中文换行和布局 '.repeat(5),'open','high');
 const b=await make('UI 合成事项 B','waiting','normal');
 const done=await make('UI 已完成事项','done','high');
 const cancelled=await make('UI 已取消事项','cancelled','urgent');
 await p.reload(); await p.waitForSelector('.metric');
 const snapshot=await api('/snapshot');
 const expected={active:snapshot.todos.filter(t=>!t.merged_into_id&&!['done','cancelled'].includes(t.status)),priority:snapshot.todos.filter(t=>!t.merged_into_id&&!['done','cancelled'].includes(t.status)&&['high','urgent'].includes(t.priority)),waiting:snapshot.todos.filter(t=>!t.merged_into_id&&t.status==='waiting'),done:snapshot.todos.filter(t=>!t.merged_into_id&&t.status==='done')};
 for(const scope of Object.keys(expected)){
   await p.locator('button[data-view=overview]').click();
   check('stat count '+scope,Number(await p.locator(`[data-work-scope=${scope}] strong`).textContent())===expected[scope].length);
   await p.locator(`[data-work-scope=${scope}]`).click();
   check('stat filter '+scope,JSON.stringify((await p.locator('[data-todo]').evaluateAll(els=>els.map(e=>e.dataset.todo))).sort())===JSON.stringify(expected[scope].map(t=>t.todo_id).sort()));
 }
 await p.locator('#clear-todo-scope').click();
 await p.locator(`[data-todo="${a.todo_id}"]`).click();await p.waitForSelector('#todo-title');
 check('drawer nonmodal',await p.locator('#detail-dialog').evaluate(e=>e.open&&!e.matches(':modal')));
 await p.locator('#todo-title').fill('A 未保存草稿');
 await p.locator(`[data-todo="${b.todo_id}"]`).click();await p.waitForFunction(()=>document.querySelector('#todo-title').value==='UI 合成事项 B');
 check('click switches detail',await p.locator('#todo-title').inputValue()==='UI 合成事项 B');
 check('switch does not save', (await api('/todos/'+a.todo_id)).title===a.title);
 await p.locator(`[data-todo="${a.todo_id}"]`).click();await p.waitForFunction(()=>document.querySelector('#todo-title').value==='A 未保存草稿');
 check('per-item draft retained',await p.locator('#todo-title').inputValue()==='A 未保存草稿');
 await p.locator('#save-todo').click();await p.waitForFunction(()=>!document.querySelector('#detail-dialog').open);
 check('real save persisted',(await api('/todos/'+a.todo_id)).title==='A 未保存草稿');
 // Deliberately resolve A after B; the latest click must win.
 await p.route('**/api/v1/todos/'+a.todo_id,async route=>{await new Promise(r=>setTimeout(r,180));await route.continue();});
 await p.locator(`[data-todo="${a.todo_id}"]`).click();await p.locator(`[data-todo="${b.todo_id}"]`).click();
 await p.waitForFunction(()=>document.querySelector('#todo-title')?.value==='UI 合成事项 B');
 await p.waitForTimeout(250);
 check('late response cannot replace selected item',await p.locator('#todo-title').inputValue()==='UI 合成事项 B');
 await p.unroute('**/api/v1/todos/'+a.todo_id);
 await p.locator('[data-todo-detail-tab=progress]').click();
 await p.locator('#progress-content').fill('UI 合成进展');await p.locator('#progress-form button[type=submit]').click();
 await p.waitForFunction(()=>document.querySelector('.timeline')?.textContent.includes('UI 合成进展'));
 check('progress persisted',(await api('/todos/'+b.todo_id)).logs.some(l=>l.content==='UI 合成进展'));
 await p.keyboard.press('Escape');check('Escape closes drawer',!await p.locator('#detail-dialog').evaluate(e=>e.open));
 // A cached edit must retain the original revision and reject an external change.
 await p.locator(`[data-todo="${a.todo_id}"]`).click();await p.waitForSelector('#todo-title');
 await p.locator('#todo-title').fill('不得覆盖外部修改');
 await p.locator(`[data-todo="${b.todo_id}"]`).click();await p.waitForFunction(()=>document.querySelector('#todo-title').value==='UI 合成事项 B');
 const current=await api('/todos/'+a.todo_id);
 await api('/todos/'+a.todo_id,'PATCH',{changes:{title:'外部已更新'},expected_revision:current.revision});
 await p.locator(`[data-todo="${a.todo_id}"]`).click();await p.waitForFunction(()=>document.querySelector('#todo-title').value==='不得覆盖外部修改');
 const conflict=p.waitForResponse(r=>r.url().endsWith('/todos/'+a.todo_id)&&r.request().method()==='PATCH');
 await p.locator('#save-todo').click();check('stale draft blocked',(await conflict).status()===409);
 check('conflict retains typed draft',await p.locator('#todo-title').inputValue()==='不得覆盖外部修改');
 check('external change preserved',(await api('/todos/'+a.todo_id)).title==='外部已更新');
 await p.reload();await p.waitForSelector('[data-todo]');
 await p.locator('#queue-ai').click();await p.waitForSelector('#todo-title');
 await p.locator('#todo-title').fill('UI 新建事项');
 await p.locator('#save-todo').click();check('missing deadline blocks submit',await p.locator('#todo-due-date').evaluate(e=>!e.checkValidity()));
 await p.locator('#no-due-date').check();await p.locator('#save-todo').click();await p.waitForFunction(()=>!document.querySelector('#detail-dialog').open);
 check('new indefinite todo saved',(await api('/snapshot')).todos.some(t=>t.title==='UI 新建事项'&&t.no_due_date));
 // Real mail edit / feedback / queue paths, preserving ID association.
 await p.locator('button[data-view=mail]').click();await p.waitForSelector('.draft-body');
 const did=await p.locator('#mail-draft-form').getAttribute('data-draft');
 await p.locator('.draft-body').fill('Saved synthetic draft body');await p.locator('#save-mail-draft').click();
 await p.waitForFunction(()=>document.querySelector('#toast').textContent.includes('这份草稿已保存'));
 await p.locator('.draft-feedback summary').click();await p.locator('#draft-feedback-form textarea').fill('Shorter, please.');
 await p.locator('#draft-feedback-form button').click();await p.waitForSelector('.feedback-entry');
 const queued=p.waitForResponse(r=>r.url().endsWith('/drafts/'+did+'/queue'));
 await p.locator('#queue-rewrite').click();const queueResponse=await queued;check('rewrite queues through backend',queueResponse.status()===200);const queuedJob=(await queueResponse.json()).queued[0].job_id;
 const pending=(await api('/snapshot')).jobs.filter(j=>j.state==='pending');
 check('rewrite remains pending',pending.length>0);
 const input=JSON.parse(fs.readFileSync(path.join(process.env.WORKTHREAD_UI_TEST_WORKSPACE,'agent-workspace','exchange','inputs',queuedJob+'.json'),'utf8')).context.draft_rewrite;
 check('rewrite contains saved body and feedback',input.draft_id===did&&input.body==='Saved synthetic draft body'&&input.feedback.some(f=>f.content==='Shorter, please.'));
 await p.locator('.draft-body').fill('Unsaved draft stays in browser');await p.locator('#queue-rewrite').click();
 check('unsaved edits not silently queued',await p.locator('#toast').textContent()==='请先保存草稿及修改意见，再加入 AI 重写队列');
 await p.locator('[data-select-mail]').nth(1).click();await p.waitForSelector('.draft-body');
 await p.locator('[data-select-mail]').first().click();await p.waitForSelector('.draft-body');
 check('mail switching retains draft edits',await p.locator('.draft-body').inputValue()==='Unsaved draft stays in browser');
 await p.locator('#mail-query').fill('Aurora');await p.locator('#mail-search button[type=submit]').click();await p.waitForFunction(()=>document.querySelector('.mail-index .card-heading small').textContent.includes('匹配'));
 check('mail full text search returns results',await p.locator('[data-select-mail]').count()>0);
 await p.locator('#clear-mail-search').click();
 // Knowledge saves to the correct scope, with the existing revision checks.
 await p.locator('button[data-view=knowledge]').click();await p.locator('#queue-ai').click();
 await p.locator('#knowledge-form textarea').fill('UI 合成个人习惯');await p.locator('#knowledge-form button[type=submit]').click();await p.waitForFunction(()=>!document.querySelector('#detail-dialog').open);
 check('knowledge persisted',(await api('/snapshot')).knowledge_items.some(k=>k.content==='UI 合成个人习惯'&&k.scope==='personal'));
 for(const scope of ['personal','customer','case']){await p.locator(`[data-knowledge-scope=${scope}]`).click();check('light object list '+scope,await p.locator('.object-index').evaluate(e=>getComputedStyle(e).backgroundColor==='rgb(241, 244, 246)'));}
 // Browser backup download and preview / restore run only in this disposable workspace.
 await p.locator('button[data-view=settings]').click();await p.locator('[data-settings-tab=backup]').click();
 const downloading=p.waitForEvent('download');await p.locator('[data-backup=full]').click();const download=await downloading;
 const archive=path.join(out,'synthetic-backup.zip');await download.saveAs(archive);
 check('real ZIP download',fs.readFileSync(archive).subarray(0,2).toString()==='PK');
 await p.locator('#restore-form input').setInputFiles(archive);await p.locator('#restore-form button[type=submit]').click();await p.waitForSelector('#apply-restore:visible');
 check('backup preview works',(await p.locator('#restore-preview').textContent()).includes('校验通过'));
 const beforeRestore=(await api('/snapshot')).todos.map(t=>[t.todo_id,t.title]);
 await p.locator('#apply-restore').click();await p.waitForFunction(()=>document.querySelector('#toast').textContent.includes('恢复完成'));
 check('restore preserves todo records',JSON.stringify((await api('/snapshot')).todos.map(t=>[t.todo_id,t.title]))===JSON.stringify(beforeRestore));
 await p.reload();await p.waitForSelector('[data-settings-tab]');await p.locator('[data-settings-tab=backup]').click();
 check('reload retains restored records',JSON.stringify((await api('/snapshot')).todos.map(t=>[t.todo_id,t.title]))===JSON.stringify(beforeRestore));
 await p.locator('#restore-form input').setInputFiles({name:'corrupt.zip',mimeType:'application/zip',buffer:Buffer.from('corrupt')});
 const invalid=p.waitForResponse(r=>r.url().endsWith('/restore'));await p.locator('#restore-form button[type=submit]').click();
 check('corrupt ZIP rejected',(await invalid).status()===400);check('corrupt ZIP cannot reveal apply',!await p.locator('#apply-restore').isVisible());
 check('corrupt ZIP leaves records intact',JSON.stringify((await api('/snapshot')).todos.map(t=>[t.todo_id,t.title]))===JSON.stringify(beforeRestore));
 // Responsive, focus and invariant navigation geometry across all five pages.
 for(const width of [1920,1440,1024,800,390]){
  await p.setViewportSize({width,height:1000});
  for(const v of ['overview','mail','todos','knowledge','settings']){
   await p.locator(`button[data-view=${v}]`).click();if(v==='mail')await p.waitForSelector('.source-mail');
   check('no overflow '+width+' '+v,await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   for(const search of await p.locator('.search-field input').all()){
    await search.focus();check('search no ring '+width+' '+v,await search.evaluate(e=>getComputedStyle(e).outlineStyle==='none'&&getComputedStyle(e).boxShadow==='none'));
   }
   if(v==='mail'){
     const source=await p.locator('.source-mail').boundingBox(), reply=await p.locator('.reply-section').boundingBox();
     check('mail layout '+width,width>=1280?Math.abs(source.y-reply.y)<2&&reply.x>source.x:reply.y>source.y);
     await p.locator('.draft-feedback summary').click();
     for(const q of ['.draft-body','#draft-feedback-form textarea']){await p.locator(q).focus();check('inset focus '+width+' '+q,await p.locator(q).evaluate(e=>{const s=getComputedStyle(e);return parseFloat(s.outlineOffset)+parseFloat(s.outlineWidth)<=0}));}
   }
   if(width===1440||width===390)await p.screenshot({animations:'disabled',path:path.join(out,`${width}-${v}.png`)});
  }
  const before=await p.locator('#navigation button svg').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y]}));
  await p.locator('#nav-toggle').click();
  const frames=await p.evaluate(async()=>{const frames=[];const start=performance.now();while(performance.now()-start<320){await new Promise(requestAnimationFrame);frames.push([...document.querySelectorAll('#navigation button svg')].map(e=>{const r=e.getBoundingClientRect();return[r.x,r.y]}));}return frames;});
  check('nav icons never shift '+width,frames.every(frame=>frame.every((r,i)=>Math.abs(r[0]-before[i][0])<.1&&Math.abs(r[1]-before[i][1])<.1)));
  check('collapsed nav remains named '+width,await p.locator('#navigation button').evaluateAll(es=>es.every(e=>e.getAttribute('aria-label')&&e.getAttribute('title'))));
  await p.locator('#nav-toggle').click();await p.waitForTimeout(300);
 }
 await p.setViewportSize({width:1440,height:1000});await p.locator('button[data-view=todos]').click();
 await p.locator('[data-todo]').first().focus();await p.keyboard.press('Enter');await p.waitForSelector('#todo-title');
 check('keyboard opens detail',await p.locator('#detail-dialog').evaluate(e=>e.open));
 await p.screenshot({animations:'disabled',path:path.join(out,'1440-todo-drawer.png')});
 await p.keyboard.press('Escape');
 check('keyboard focus returns to list',await p.locator('[data-todo]').first().evaluate(e=>document.activeElement===e));
 check('no unexpected browser errors',errors.filter(e=>!e.includes('400 (BAD REQUEST)')).length===0);
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({passed:results.length,checks:results,errors},null,2));
 console.log('Browser regression PASS: '+results.length+' checks');
})().catch(e=>{console.error(e);fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({passed:results,errors,error:e.stack},null,2));process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();});
