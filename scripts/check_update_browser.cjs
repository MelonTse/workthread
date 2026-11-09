const [lib,exe,url]=process.argv.slice(2);
(async()=>{
 const browser=await require(lib).chromium.launch({executablePath:exe,headless:true});
 try{
  const page=await browser.newPage();
  page.setDefaultTimeout(120000);
  await page.goto(url+'/#settings');
  await page.locator('[data-settings-tab="update"]').click();
  await page.getByRole('button',{name:'检查更新',exact:true}).click();
  await page.getByText('可用版本：1.0.0rc5',{exact:false}).waitFor();
  await page.getByRole('button',{name:'下载并检查'}).click();
  page.once('dialog',d=>d.dismiss());
  await page.getByRole('button',{name:'备份并重启更新'}).click();
  if (!(await page.getByRole('button',{name:'备份并重启更新'}).isEnabled())) throw Error('cancel did not preserve session');
  page.once('dialog',d=>d.accept());
  await page.getByRole('button',{name:'备份并重启更新'}).click();
  await page.getByText('正在备份并重启。请保持此页面打开。').waitFor();
  await page.getByText('已更新至 1.0.0rc5',{exact:false}).waitFor({timeout:120000});
  if (!(await page.locator('#update-status').innerText()).includes('当前版本：1.0.0rc5')) throw Error('wrong active version');
  console.log('Browser PASS: check, download, cancel, confirm, disconnect, reconnect, version and result.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
