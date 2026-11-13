const [lib,exe,url,out,total]=process.argv.slice(2);
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await require(lib).chromium.launch({executablePath:exe,headless:true});
 const passed=[],errors=[];
 try{
  const p=await browser.newPage({viewport:{width:1440,height:960}});
  p.on('pageerror',e=>errors.push(e.message));
  await p.goto(url+'/#mail');
  await p.locator('#mail-total').filter({hasText:`共 ${total} 封`}).waitFor();
  assert.equal(await p.locator('.mail-choice').count(),50);passed.push('真实总数超过500，每页50封');
  await p.locator('#mail-detail h2').first().waitFor();
  await p.waitForTimeout(400); // settle initial navigation width transition before screenshots
  await p.screenshot({animations:'disabled',path:path.join(out,'mail-page-1.png'),fullPage:true});
  const ids=await p.locator('.mail-choice').evaluateAll(xs=>xs.map(x=>x.dataset.selectMail));
  await p.locator('#mail-next').click();
  await p.waitForFunction(()=>document.querySelector('[aria-label="邮件页码"]').value==='2');
  const second=await p.locator('.mail-choice').evaluateAll(xs=>xs.map(x=>x.dataset.selectMail));
  assert(!second.some(id=>ids.includes(id)));passed.push('下一页无重复');
  await p.getByLabel('邮件页码').fill('13');await p.locator('#mail-pagination button[type=submit]').click();
  await p.waitForFunction(()=>document.querySelector('[aria-label="邮件页码"]').value==='13' && !document.querySelector('#mail-pagination button[type=submit]').disabled);
  assert.equal(await p.locator('.mail-choice').count(),Number(total)-600);passed.push('跳至末页包含500以外邮件');
  await p.locator('[data-select-mail="page-0000"]').click();
  await p.getByText('分页合成样本 0000',{exact:true}).last().waitFor();
  await p.locator('#mail-query').fill('分页合成样本');await p.locator('#mail-query').press('Enter');
  await p.locator('#mail-total').filter({hasText:'匹配 623 封'}).waitFor();
  await p.getByLabel('邮件页码').fill('13');await p.locator('#mail-pagination button[type=submit]').click();
  await p.waitForFunction(()=>document.querySelector('[aria-label="邮件页码"]').value==='13' && !document.querySelector('#mail-pagination button[type=submit]').disabled);
  assert.equal(await p.locator('.mail-choice').count(),23);passed.push('搜索结果超过100也可翻页');
  await p.screenshot({animations:'disabled',path:path.join(out,'mail-search-last.png'),fullPage:true});
  await p.locator('#mail-query').fill('不存在的合成字符串');await p.locator('#mail-query').press('Enter');
  await p.getByText('没有匹配邮件。',{exact:true}).waitFor();
  assert(await p.locator('#mail-next').isDisabled());passed.push('空结果与禁用翻页');
  await p.locator('#clear-mail-search').click();await p.locator('#mail-total').filter({hasText:`共 ${total} 封`}).waitFor();
  await p.locator('#refresh-mail-list').click();await p.waitForFunction(()=>!document.querySelector('#refresh-mail-list').disabled);
  passed.push('清空搜索与刷新归档');
  await p.setViewportSize({width:390,height:844});
  await p.screenshot({animations:'disabled',path:path.join(out,'mail-narrow.png'),fullPage:true});
  const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
  assert(!overflow,'narrow horizontal overflow');passed.push('窄屏无横向溢出');
  assert.deepEqual(errors,[]);passed.push('无浏览器脚本异常');
  fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({passed,errors},null,2));
  console.log(JSON.stringify({passed,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
