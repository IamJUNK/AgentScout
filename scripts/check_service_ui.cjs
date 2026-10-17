// Requires compose.test.yaml on localhost:8081; only Mock is ever submitted.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
async function main(){
  const browser=await chromium.launch({...(process.env.CI?{}:{channel:'chrome'}),headless:true});
  const errors=[];
  const directory=path.resolve(__dirname,'../data/upgrade-local');
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
    const page=await context.newPage();
    page.on('pageerror',e=>errors.push(String(e)));
    await page.goto('http://127.0.0.1:8081/');
    await page.getByRole('switch',{name:'Mock 演示（不验证真实结论）'}).check();
    await page.getByRole('textbox',{name:'研究需求',exact:true}).fill('比较 LangGraph 和 CrewAI 的适用场景');
    await page.getByRole('button',{name:'提交研究',exact:true}).click();
    await page.waitForURL('**/tasks/*');
    const taskURL=page.url();
    const taskID=taskURL.split('/').at(-1);
    await page.getByRole('button',{name:'下载 Markdown',exact:true}).waitFor({timeout:45000});
    await page.getByText('Mock 演示：不证明真实研究质量',{exact:true}).waitFor();
    await page.getByText('相邻上下文',{exact:true}).click();
    const downloadPromise=page.waitForEvent('download');
    await page.getByRole('button',{name:'下载 Markdown',exact:true}).click();
    const download=await downloadPromise;
    await download.saveAs(path.join(directory,'service-ui-report.md'));
    const second=await browser.newContext();
    const other=await second.newPage();
    other.on('pageerror',e=>errors.push(String(e)));
    await other.goto(taskURL);
    await other.getByRole('button',{name:'下载 Markdown',exact:true}).waitFor();
    await page.reload();
    await page.getByRole('button',{name:'下载 Markdown',exact:true}).waitFor();
    await page.getByRole('button',{name:'重新执行',exact:true}).click();
    await page.getByText(/第 2 次：succeeded/).waitFor({timeout:45000});
    await page.getByRole('button',{name:'下载 Markdown',exact:true}).waitFor();
    const attempts=await (await page.request.get('http://127.0.0.1:8081/api/v1/tasks/'+taskID+'/attempts')).json();
    if(attempts.length!==2)throw Error('Retry did not retain both attempts');
    const reports=await Promise.all(attempts.map(a=>page.request.get('http://127.0.0.1:8081/api/v1/attempts/'+a.id+'/report')));
    if(reports.some(r=>r.status()!==200))throw Error('Historical report missing');
    await page.getByRole('combobox',{name:'执行尝试'}).click();
    await page.getByRole('option',{name:/第 1 次/}).click();
    await page.getByText(/第 1 次：succeeded/).waitFor();
    await page.goto('http://127.0.0.1:8081/history');
    await page.getByRole('link',{name:'比较 LangGraph 和 CrewAI 的适用场景',exact:true}).first().waitFor();
    await page.goto(taskURL);
    await page.getByRole('button',{name:'下载 Markdown',exact:true}).waitFor();
    await page.screenshot({path:path.resolve(__dirname,'../docs/screenshots/nicegui-service-mock.png')});
    await page.setViewportSize({width:390,height:844});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
    if(overflow)throw Error('Mobile overflow');
    if(errors.length)throw Error(errors.join(';'));
    fs.writeFileSync(path.join(directory,'service-ui.json'),JSON.stringify({timestamp:new Date().toISOString(),task_id:taskID,mode:'mock_real_service',submit:true,report:true,evidence:true,download:true,reload:true,two_browser_sessions:true,retry_history:true,mobile_overflow:overflow,browser_errors:errors},null,2));
    console.log('Real service UI passed: submit, report, evidence, download, reload, two sessions, retry/history.');
    await second.close();await context.close();
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
