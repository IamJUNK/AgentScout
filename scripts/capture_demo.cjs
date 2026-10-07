const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const output = path.resolve(__dirname, '../docs');
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  let activePage;
  try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, recordVideo: { dir: output, size: { width: 1440, height: 1000 } } });
  const page = await context.newPage();
  activePage = page;
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto('http://127.0.0.1:8501', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: /开始研究/ }).waitFor();
  await page.getByRole('button', { name: /开始研究/ }).click();
  await page.getByRole('button', { name: /下载 Markdown/ }).first().waitFor();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(output, 'research.png') });
  await page.getByRole('heading', { name: '关键发现', exact: true }).first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, 'report.png') });
  await page.getByRole('tab', { name: 'Trace', exact: true }).click();
  await page.getByText('选择运行', { exact: true }).waitFor();
  await page.waitForTimeout(1000);
  await page.locator('[data-testid="stPlotlyChart"]').first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, 'trace.png') });
  await page.getByRole('tab', { name: 'Evaluation', exact: true }).click();
  await page.getByRole('button', { name: /运行评测集/ }).click();
  await page.getByText('任务详情', { exact: true }).waitFor();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(output, 'evaluation.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('tab', { name: 'Research', exact: true }).click();
  await page.waitForTimeout(300);
  await page.getByRole('heading', { name: 'AgentScout', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, 'mobile.png') });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  if (overflow) throw new Error('Mobile viewport has horizontal page overflow');
  const exceptions = await page.locator('[data-testid="stException"]').count();
  if (exceptions || errors.length) throw new Error(JSON.stringify({ exceptions, errors }));
  const videoPath = await page.video().path();
  await context.close();
  fs.renameSync(videoPath, path.join(output, 'demo.webm'));
  for (const name of fs.readdirSync(output)) {
    if (name === 'browser-error.png' || (/^page@.*\.webm$/.test(name) && fs.statSync(path.join(output, name)).size === 0)) fs.unlinkSync(path.join(output, name));
  }
  console.log('Desktop/mobile screenshots and demo.webm generated; no browser or Streamlit exceptions.');
  } catch (error) {
    if (activePage) {
      console.error(await activePage.locator('body').innerText());
      await activePage.screenshot({ path: path.join(output, 'browser-error.png') });
    }
    throw error;
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exit(1); });
