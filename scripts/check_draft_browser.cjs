// Invoked by check_draft_browser.py with an isolated synthetic server.
const [lib, executablePath, output, url, mid] = process.argv.slice(2);
const { chromium } = require(lib);
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch(executablePath ? {executablePath} : {});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 900}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const shot = name => page.screenshot({path: path.join(output, name + '.png'), animations:'disabled'});
    async function mail() {
      await page.locator('[data-view=mail]').click();
      await page.locator('[data-select-mail="'+mid+'"]').click();
      await page.waitForSelector('[data-message-id="'+mid+'"]');
    }
    await page.goto(url);
    await mail();
    await page.getByRole('button',{name:'加入草稿生成队列'}).click();
    await page.getByText('等待 WorkBuddy 处理',{exact:true}).waitFor();
    await shot('01-workbuddy-queue');
    await page.locator('[data-withdraw-job]').click();
    await page.getByText('任务已撤回',{exact:true}).waitFor();

    await page.locator('[data-view=settings]').click();
    const form = page.locator('#draft-ai-settings');
    await form.locator('[name=mode]').selectOption('api');
    assert.equal(await form.locator('[name=provider] option').count(),6);
    await form.locator('[name=provider]').selectOption('mimo');
    await form.locator('[name=model]').fill('synthetic-mail-fixture');
    await form.locator('[name=key]').fill('synthetic-local-test');
    await form.getByRole('button',{name:'保存 AI 设置'}).click();
    await page.locator('#test-draft-api').click();
    await page.getByText('连接成功，模型已返回合成草稿').waitFor();
    await page.locator('#toast').waitFor({state:'hidden'});
    await shot('02-api-settings');
    await mail();
    await page.locator('#generate-mail-draft').click();
    await page.locator('.draft-body').waitFor();
    assert.match(await page.locator('.draft-body').inputValue(),/USD 42/);
    await shot('03-generated');
    await page.locator('.draft-feedback summary').click();
    await page.locator('#draft-feedback-form textarea').fill('缩短回复，保留 USD 42。');
    await page.locator('#draft-feedback-form button').click();
    await page.getByText('缩短回复，保留 USD 42。',{exact:true}).first().waitFor();
    await page.getByRole('button',{name:'按反馈重写'}).click();
    await page.waitForFunction(()=>document.querySelectorAll('[data-draft-tab]').length===2);
    assert.match(await page.locator('.draft-body').inputValue(),/Dispatch date to be confirmed/);
    await shot('04-rewritten');
    await page.locator('[data-draft-tab]').last().click();
    assert.match(await page.locator('.draft-body').inputValue(),/Thank you for your note/);
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    assert.deepEqual(errors,[]);
    console.log('PASS: queue, withdrawal, six providers, synthetic connection, generation, feedback, rewrite, original draft, narrow layout.');
  } finally { await browser.close(); }
})().catch(e => {console.error(e);process.exitCode=1;});
