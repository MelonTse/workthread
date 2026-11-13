const [lib,exe,url,version="1.0.0rc5"]=process.argv.slice(2);
(async()=>{
 const browser=await require(lib).chromium.launch({executablePath:exe,headless:true});
 try{
  const page=await browser.newPage();
  page.setDefaultTimeout(120000);
  await page.goto(url+'/#settings');
  await page.locator('[data-settings-tab="update"]').click();
  await page.getByRole('button',{name:'检查更新',exact:true}).click();
  await page.getByText('可用版本：'+version,{exact:false}).waitFor();
  await page.getByRole('button',{name:'下载并检查'}).click();
  page.once('dialog',d=>d.dismiss());
  await page.getByRole('button',{name:'备份并重启更新'}).click();
  if (!(await page.getByRole('button',{name:'备份并重启更新'}).isEnabled())) throw Error('cancel did not preserve session');
  const before = await page.evaluate(async () => (await fetch('/api/v1/software-update')).json());
  if (!before.ready) throw Error('download not verified');
  await page.reload();
  await page.getByRole('button',{name:'备份并重启更新'}).waitFor();
  page.once('dialog',d=>d.accept());
  await page.getByRole('button',{name:'备份并重启更新'}).click();
  await page.getByText('正在备份并重启。请保持此页面打开。').waitFor();
  const pending = await page.evaluate(() => JSON.parse(sessionStorage.getItem('workthread-update-pending')));
  if (!pending?.id) throw Error('missing current update identity');
  await page.getByText('已更新至 '+version,{exact:false}).waitFor({timeout:120000});
  if (!(await page.locator('#update-status').innerText()).includes('当前版本：'+version)) throw Error('wrong active version');
  const after = await page.evaluate(async () => (await fetch('/api/v1/software-update')).json());
  if (after.attempt?.id !== pending.id || after.attempt.phase !== 'succeeded' ||
      after.attempt.target_commit !== after.current_commit) throw Error('stale or unverified result');
  console.log('Browser PASS: check, download, cancel, confirm, disconnect, reconnect, version and result.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
