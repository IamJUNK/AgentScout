// Start scripts/demo_app.py on port 8502 before running this script.
// All examples explicitly use Mock, with both Judges disabled.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const output = path.resolve(__dirname, '../docs/screenshots');
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    page.setDefaultTimeout(45000);
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto('http://127.0.0.1:8502', { waitUntil: 'domcontentloaded' });
    const research = page.getByRole('tabpanel', { name: 'Research', exact: true });
    const trace = page.getByRole('tabpanel', { name: 'Trace', exact: true });
    const evaluation = page.getByRole('tabpanel', { name: 'Evaluation', exact: true });
    const idle = async () => {
      await page.waitForFunction(() => !Array.from(document.querySelectorAll('[data-testid=stStatusWidget], [data-stale=true]')).some(el => el.getClientRects().length));
    };
    const frame = async locator => {
      await locator.evaluate(el => {
        el.scrollIntoView({ block: 'start' });
        let parent = el.parentElement;
        while (parent) {
          if (parent.scrollHeight > parent.clientHeight && /auto|scroll/.test(getComputedStyle(parent).overflowY)) {
            parent.scrollTop -= 80;
            break;
          }
          parent = parent.parentElement;
        }
      });
    };
    const shot = async name => {
      await idle();
      await page.screenshot({ path: path.join(output, name), animations: 'disabled' });
    };
    const model = research.getByRole('textbox', { name: '模型名称', exact: true });
    if ((await model.inputValue()) !== '') throw new Error('Use isolated demo_app.py with empty model settings.');
    await research.getByRole('checkbox', { name: 'Mock 演示（不验证真实研究质量）', exact: true }).check();
    await research.getByRole('checkbox', { name: '独立 LLM Judge（可能收费）', exact: true }).uncheck();
    await research.getByRole('textbox', { name: '研究需求', exact: true }).fill('比较 LangGraph 和 CrewAI 的适用场景');
    await page.getByRole('heading', { name: 'AgentScout', exact: true }).click();
    await shot('01-research.png');
    await research.getByRole('button', { name: '开始研究', exact: true }).click();
    await research.getByRole('button', { name: '下载 Markdown', exact: true }).waitFor();
    await idle();
    await frame(research.getByText('演示资料', { exact: true }).first());
    await shot('02-report.png');
    const evidence = research.locator('[data-testid=stExpander]').filter({ has: page.getByText('证据片段与来源', { exact: true }) });
    await evidence.locator('summary').click();
    await idle();
    await evidence.screenshot({ path: path.join(output, '03-evidence.png'), animations: 'disabled' });
    await page.getByRole('tab', { name: 'Trace', exact: true }).click();
    await trace.locator('[data-testid=stPlotlyChart]').first().waitFor();
    await idle();
    await trace.locator('[data-testid=stPlotlyChart]').first().screenshot({ path: path.join(output, '04-trace.png'), animations: 'disabled' });
    await page.getByRole('tab', { name: 'Evaluation', exact: true }).click();
    await evaluation.getByRole('checkbox', { name: 'Mock 评测', exact: true }).check();
    await evaluation.getByRole('checkbox', { name: '独立 Judge', exact: true }).uncheck();
    await evaluation.getByRole('spinbutton', { name: '评测任务数量', exact: true }).fill('20');
    await evaluation.getByRole('button', { name: '运行评测集', exact: true }).click();
    await evaluation.getByRole('button', { name: '下载评测 JSON', exact: true }).waitFor();
    await idle();
    await page.setViewportSize({ width: 1440, height: 1200 });
    await frame(page.getByRole('heading', { name: 'AgentScout', exact: true }));
    await shot('05-evaluation.png');
    if (await page.locator('[data-testid=stException]').count() || errors.length) throw new Error('Browser or Streamlit errors: ' + errors.join('; '));
    fs.writeFileSync(path.join(output, 'capture.json'), JSON.stringify({
      captured_at: new Date().toISOString(), mode: 'mock',
      source: 'app.py via scripts/demo_app.py',
      viewport: { width: 1440, height: 1000 }, evaluation_viewport: { width: 1440, height: 1200 }, evaluation_tasks: 20,
      files: ['01-research.png', '02-report.png', '03-evidence.png', '04-trace.png', '05-evaluation.png']
    }, null, 2));
    console.log('Captured five current UI screenshots using Mock research and evaluation.');
    await context.close();
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
