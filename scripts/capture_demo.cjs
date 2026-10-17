// Read-only saved-result preview; does not submit research or call providers.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
async function main() {
  const output = path.resolve(__dirname, '../docs/screenshots');
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({channel:'chrome', headless:true});
  const errors=[];
  try {
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const page=await context.newPage();
    page.on('pageerror',e=>errors.push(String(e)));
    await page.goto('http://127.0.0.1:8502/');
    await page.getByText('从问题出发，让结论有据可查。',{exact:true}).waitFor();
    await page.screenshot({path:path.join(output,'nicegui-workbench.png')});
    await page.goto('http://127.0.0.1:8502/tasks/saved');
    await page.getByRole('button',{name:'下载 Markdown',exact:true}).waitFor();
    await page.getByRole('heading',{name:'研究报告',exact:true}).waitFor();
    await page.screenshot({path:path.join(output,'nicegui-report.png')});
    await page.getByText('相邻上下文',{exact:true}).click();
    await page.screenshot({path:path.join(output,'nicegui-evidence.png')});
    const downloadPromise=page.waitForEvent('download');
    await page.getByRole('button',{name:'下载 Markdown',exact:true}).click();
    const download=await downloadPromise;
    if (!(await download.suggestedFilename()).endsWith('.md')) throw Error('Wrong download extension');
    await page.getByRole('tab',{name:'执行轨迹',exact:true}).click();
    await page.screenshot({path:path.join(output,'nicegui-trace.png')});
    await page.reload();
    await page.getByRole('button',{name:'下载 Markdown',exact:true}).waitFor();
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(output,'nicegui-mobile.png'),fullPage:true});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
    if(overflow) throw Error('Horizontal overflow on 390px viewport');
    await page.goto('http://127.0.0.1:8502/history');
    await page.getByRole('link',{name:/WAL/}).first().waitFor();
    if(errors.length) throw Error(errors.join('; '));
    fs.writeFileSync(path.join(output,'nicegui-capture.json'),JSON.stringify({captured_at:new Date().toISOString(),mode:'saved_result_read_only',browser_errors:errors,mobile_horizontal_overflow:overflow,download:true,reload:true,queue_end_to_end:false},null,2));
    console.log('NiceGUI saved preview: desktop, evidence, trace, mobile, reload and download passed.');
  } finally { await browser.close(); }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
