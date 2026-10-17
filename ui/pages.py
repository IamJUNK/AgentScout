from uuid import uuid4
from pathlib import Path
import json
import asyncio
from datetime import date
from nicegui import ui, run
from models.tasks import TaskRequest, TERMINAL
from storage.repository import NotFound, Conflict

CSS='''
body {background:#f5f7fb;color:#1b2940;font-family:Inter,"Microsoft YaHei",sans-serif}
.nicegui-content {padding:0;gap:0}.shell {max-width:1240px;width:100%;margin:auto;padding:32px 28px}
.q-card {box-shadow:0 3px 20px #12233b08;border:1px solid #e5eaf2;border-radius:18px}
.eyebrow {letter-spacing:2px;color:#5c7191;font-size:11px;font-weight:700}
.title {font-size:34px;font-weight:750;line-height:1.3;letter-spacing:-1px}
.muted {color:#6c7b92}.pill {padding:6px 12px;border-radius:20px;background:#eaf0fb;color:#3155a6;font-size:12px}
.prose {line-height:1.9;overflow-wrap:anywhere}.q-btn {text-transform:none;border-radius:10px}
.prose h1{font-size:28px;line-height:1.4;font-weight:700}.prose h2{font-size:21px;line-height:1.5;font-weight:650}.prose h3{font-size:18px;font-weight:600}
.shell,.report-grid,.q-tab-panel,.q-card {min-width:0}.q-btn__content{overflow-wrap:anywhere}
.navlink {color:#c6d2e7;text-decoration:none;font-size:14px}.evidence {white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:760px){.shell{padding:20px 14px}.title{font-size:27px}.report-grid{grid-template-columns:1fr!important}.q-header{padding:16px}.q-header>div{flex-wrap:wrap}.q-card{padding:18px!important}.prose table{display:block;overflow-x:auto}.q-tab-panel{padding:0}}
'''

def install(app,service):
    def frame():
        ui.add_css(CSS)
        with ui.header().classes('items-center justify-between px-8 py-4').style('background:#14213a'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('travel_explore',size='28px').classes('text-blue-300')
                ui.label('AgentScout').classes('text-xl font-bold')
            with ui.row().classes('gap-6 items-center'):
                for name,url in [('研究工作台','/'),('历史任务','/history'),('评测结果','/evaluations')]:ui.link(name,url).classes('navlink')
            ui.label('已保存结果 · 只读预览' if getattr(service,'preview',False) else 'RESEARCH WORKSPACE').classes('text-xs text-blue-200')
        return ui.column().classes('shell gap-6')

    async def invoke(fn,*args,quiet=False,**kwargs):
        try:return await run.io_bound(fn,*args,**kwargs)
        except (Conflict,NotFound) as exc:
            if not quiet:ui.notify(str(exc),type='warning')
        except Exception:
            if not quiet:ui.notify('操作未完成，请检查服务状态和执行记录。',type='negative')
        return None

    @ui.page('/')
    def home():
        key=str(uuid4())
        with frame():
            ui.label('EVIDENCE FIRST · RESEARCH ASSISTANT').classes('eyebrow')
            ui.label('从问题出发，让结论有据可查。').classes('title')
            ui.label('拆解研究需求、追踪执行过程，并在报告中逐条查看支持结论的原文。').classes('muted text-base')
            with ui.row().classes('w-full gap-5 flex-wrap items-stretch'):
                with ui.card().classes('p-7 flex-grow').style('flex-basis:650px'):
                    ui.label('开始一项研究').classes('text-xl font-semibold')
                    topic=ui.textarea('研究需求',placeholder='例如：根据 SQLite 官方文档，分别解释 WAL 的写入者限制与 SQLITE_BUSY 发生条件。').props('outlined autogrow').classes('w-full')
                    material=ui.textarea('补充材料（可选）',placeholder='只分析材料时，请注明“仅根据提供材料，不要联网”。').props('outlined').classes('w-full')
                    mock=ui.switch('Mock 演示（不验证真实结论）',value=True)
                    retrieval=ui.select({'bm25':'BM25 关键词检索','hybrid':'混合检索（需配置 Embedding）'},value='bm25',label='检索方式').classes('w-full')
                    with ui.expansion('执行预算与限制',icon='tune').classes('w-full'):
                        prefixes=ui.textarea('官方文档地址前缀（每行一个，可选）',placeholder='https://sqlite.org/').props('outlined').classes('w-full')
                        budget=ui.number('本次 Token 上限',value=30000,min=1000,max=100000,step=1000)
                        timeout=ui.number('执行时间上限（秒）',value=180,min=10,max=600)
                        ui.label('具体上限受服务端配置约束；搜索与模型可能产生费用。').classes('muted text-xs')
                    async def submit():
                        button.disable()
                        try:
                            request=TaskRequest(input_text=topic.value or '',supplied_text=material.value or '',mock=mock.value,retrieval_mode=retrieval.value,max_tokens=int(budget.value),timeout_seconds=int(timeout.value),official_source_prefixes=[p.strip() for p in (prefixes.value or '').splitlines() if p.strip()])
                            result=await invoke(service.submit,request,key)
                            if result:ui.navigate.to('/tasks/'+result['id'])
                        except ValueError:ui.notify('请填写研究需求，并检查预算范围。',type='warning')
                        finally:button.enable()
                    button=ui.button('提交研究',icon='arrow_forward',on_click=submit).classes('mt-2 px-6').props('unelevated')
                    if getattr(service,'preview',False):
                        button.disable()
                        ui.link('打开已保存报告 →','/tasks/saved').classes('text-blue-700 font-semibold')
                with ui.column().classes('gap-4').style('flex:1;min-width:250px'):
                    for n,title,description in [('01','明确研究边界','独立问题分别回答，来源和时间限制贯穿研究。'),('02','后台持续执行','页面可关闭；服务模式下任务由独立 Worker 执行。'),('03','逐条核验证据','查看原文、支持关系与未解决缺口，不把执行成功当事实正确。')]:
                        with ui.card().classes('p-6 w-full'):
                            ui.label(n).classes('eyebrow');ui.label(title).classes('font-semibold text-lg');ui.label(description).classes('muted text-sm')

    @ui.page('/history')
    async def history():
        with frame():
            ui.label('RESEARCH LIBRARY').classes('eyebrow');ui.label('历史研究').classes('title')
            status=ui.select({'all':'全部状态','pending_dispatch':'等待派发','queued':'排队中','running':'执行中','succeeded':'执行结束','failed':'失败','cancelled':'已取消'},value='all',label='执行状态').classes('w-52')
            with ui.row().classes('w-full flex-wrap'):
                since=ui.input('开始日期（UTC）').props('type=date')
                until=ui.input('结束日期（UTC）').props('type=date')
            container=ui.column().classes('w-full gap-3');cursor=None
            async def refresh(reset=True):
                nonlocal cursor
                if reset:cursor=None;container.clear()
                start=date.fromisoformat(since.value) if since.value else None
                end=date.fromisoformat(until.value) if until.value else None
                if start and end and start>end:
                    ui.notify('开始日期不能晚于结束日期',type='warning');return
                value=await invoke(service.list_tasks,20,cursor,None if status.value=='all' else status.value,start,end)
                if not value:return
                with container:
                    if not value['items']:ui.label('暂无研究任务。').classes('muted')
                    for t in value['items']:
                        with ui.card().classes('w-full p-5'):
                            ui.link(t['input_text'],'/tasks/'+t['id']).classes('text-base font-semibold no-underline')
                            a=t['current_attempt'];ui.label(f"{t['created_at']} · 第 {a['number']} 次尝试 · {a['execution_status']} / {a['quality_status']}").classes('muted text-xs')
                cursor=value['next_cursor'];more.set_visibility(bool(cursor))
            status.on_value_change(lambda:refresh())
            since.on_value_change(lambda:refresh());until.on_value_change(lambda:refresh())
            more=ui.button('加载更多',on_click=lambda:refresh(False)).props('outline')
            await refresh()

    @ui.page('/tasks/{task_id}')
    async def detail(task_id:str):
        with frame():
            task=await invoke(service.get_task,task_id)
            if not task:ui.label('任务不可用');return
            ui.label('RESEARCH DETAIL').classes('eyebrow');ui.label(task['request']['input_text']).classes('text-2xl font-bold break-words')
            status_label=ui.label().classes('pill')
            ui.label('执行状态与研究质量独立记录；重试会保留此前报告。').classes('muted text-sm')
            attempts=await invoke(service.attempts,task_id) or []
            selector=ui.select({a['id']:f"第 {a['number']} 次 · {a['execution_status']}" for a in attempts},value=task['current_attempt']['id'],label='执行尝试').classes('w-full')
            with ui.row():
                async def cancel():await invoke(service.cancel,task_id);await refresh()
                async def retry():
                    result=await invoke(service.retry,task_id)
                    if result:ui.navigate.to('/tasks/'+task_id)
                cancel_button=ui.button('取消当前任务',on_click=cancel).props('outline')
                retry_button=ui.button('重新执行',icon='replay',on_click=retry).props('outline')
            with ui.tabs().classes('w-full') as tabs:
                report_tab=ui.tab('报告与证据');trace_tab=ui.tab('执行轨迹')
            with ui.tab_panels(tabs,value=report_tab).classes('w-full bg-transparent'):
                with ui.tab_panel(report_tab).classes('p-0'):
                    with ui.element('div').classes('report-grid w-full grid gap-5').style('grid-template-columns:minmax(0,1.6fr) minmax(0,1fr)'):
                        report_area=ui.column().classes('w-full');evidence_area=ui.column().classes('w-full')
                with ui.tab_panel(trace_tab):event_area=ui.column().classes('w-full')
            last=None
            event_cursor=0
            event_attempt=None
            refreshing=asyncio.Lock()
            async def refresh():
                nonlocal last,event_cursor,event_attempt
                current=await invoke(service.get_task,task_id,quiet=True)
                if not current:return
                a=current['current_attempt']
                cancel_button.set_enabled(a['execution_status'] not in TERMINAL);retry_button.set_enabled(a['execution_status'] in TERMINAL)
                if getattr(service,'preview',False):cancel_button.disable();retry_button.disable()
                chosen=selector.value;chosen_status=await invoke(service.get_attempt,chosen,quiet=True)
                if not chosen_status:return
                cancellation=' · 已请求取消，等待执行边界停止' if chosen_status.get('cancel_requested') and chosen_status['execution_status']=='running' else ''
                status_label.set_text(f"第 {chosen_status['number']} 次：{chosen_status['execution_status']} · 质量：{chosen_status['quality_status']} · 已知 Token：{chosen_status['token_usage']} · 未确认预留：{chosen_status['reserved_tokens']}"+cancellation)
                marker=(chosen,chosen_status['updated_at'],chosen_status['execution_status'])
                if event_attempt!=chosen:
                    event_area.clear();event_cursor=0;event_attempt=chosen
                events=await invoke(service.events,chosen,event_cursor,100,quiet=True)
                event_cursor=(events or {}).get('next_cursor',event_cursor)
                with event_area:
                    for event in (events or {}).get('items',[]):
                        with ui.card().classes('p-4 w-full'):
                            ui.label(f"{event.get('node_name','')} · {event.get('event_type','')} · {event.get('duration_ms','—')} ms").classes('font-medium text-sm')
                            ui.label(f"Token {event.get('token_usage',0)} · 模型调用 {event.get('llm_calls',0)} · 搜索 {event.get('search_calls',0)}").classes('muted text-xs')
                            if event.get('error_message'):ui.label(event['error_message']).classes('text-red-700 text-sm break-words')
                if marker==last:return
                with event_area:
                    if chosen_status.get('error_code'):ui.label(chosen_status['error_code']).classes('text-red-700')
                report_area.clear();evidence_area.clear()
                if chosen_status['execution_status'] not in TERMINAL:
                    with report_area:
                        with ui.card().classes('p-8 w-full'):ui.spinner(size='lg');ui.label('研究正在进行，完成后显示报告和证据。')
                    return
                result=await invoke(service.report,chosen,quiet=True)
                if not result:
                    with report_area:ui.label('本次尝试未生成报告。').classes('muted')
                    return
                evidence=await invoke(service.evidence,chosen,0,100,quiet=True) or []
                with evidence_area:
                    with ui.card().classes('w-full p-5'):ui.label('证据原文').classes('text-lg font-semibold');evidence_box=ui.column().classes('w-full')
                async def show_evidence(e):
                    evidence_box.clear()
                    with evidence_box:
                        ui.label(e['title']).classes('font-semibold');ui.label(f"{e['kind']} · 位置 {e['start']}–{e['end']}").classes('muted text-xs')
                        if e['url'].startswith(('https://','http://')):ui.link('打开来源',e['url'],new_tab=True)
                        ui.label(e['text']).classes('evidence text-sm');ui.label('获取时间：'+e.get('retrieved_at','未知')).classes('muted text-xs')
                        source=await invoke(service.source,chosen,e['source_id'],quiet=True)
                        if source:
                            from agent.quality import source_type
                            ui.label('来源类型：'+source_type(source.get('final_url') or source['url'],service.settings.official_source_prefixes)).classes('muted text-xs')
                            content=source.get('snippet','') if e['kind']=='snippet' else source.get('content','')
                            with ui.expansion('相邻上下文').classes('w-full'):ui.label(content[max(0,e['start']-350):e['end']+350]).classes('evidence text-sm')
                with report_area:
                    with ui.card().classes('w-full p-7'):
                        with ui.row().classes('w-full justify-between'):
                            ui.label('研究报告').classes('text-xl font-semibold')
                            ui.button('下载 Markdown',icon='download',on_click=lambda:ui.download(result['markdown'].encode('utf-8'),f'report-{chosen}.md')).props('flat')
                        if result['quality_status']=='demo':ui.label('Mock 演示：不证明真实研究质量').classes('text-amber-800')
                        ui.markdown(result['markdown'],sanitize=True).classes('prose w-full')
                        by_id={e['id']:e for e in evidence}
                        for section in result.get('structured',{}).get('sections',[]):
                            for claim in section.get('claims',[]):
                                with ui.expansion('核对结论 '+claim['id']+'：'+claim['text'][:80]).classes('w-full'):
                                    verdict=next((v for v in result.get('review',{}).get('claims',[]) if v['claim_id']==claim['id']),None)
                                    if verdict:ui.label(verdict['status']+' · '+verdict.get('explanation','')).classes('muted text-sm')
                                    for support in claim.get('supports',[]):
                                        e=by_id.get(support['evidence_id'])
                                        ui.label(support['quote']).classes('evidence text-sm')
                                        if e:ui.button('查看 '+e['id']+' 原文',on_click=lambda e=e:show_evidence(e)).props('flat dense')
                        ui.separator();ui.label('查看引用证据').classes('font-semibold')
                        for e in evidence:ui.button(e['id']+' · '+e['title'],on_click=lambda e=e:show_evidence(e)).props('flat dense').classes('text-left max-w-full')
                if evidence:await show_evidence(evidence[0])
                last=marker
            async def guarded_refresh():
                if refreshing.locked():return
                async with refreshing:await refresh()
            selector.on_value_change(guarded_refresh)
            await guarded_refresh()
            timer=ui.timer(3,guarded_refresh)
            ui.context.client.on_disconnect(lambda: timer.deactivate())
            ui.context.client.on_connect(lambda: timer.activate())
            ui.context.client.on_delete(lambda: timer.cancel())

    @ui.page('/evaluations')
    def evaluations():
        with frame():
            ui.label('QUALITY LAB').classes('eyebrow');ui.label('评测与验证').classes('title')
            ui.label('流程测试、固定资料实验和真实联网结果分别记录。未运行不等于通过。').classes('muted')
            path=Path(__file__).resolve().parents[1]/'evals'/'results'/'upgrade-summary.json'
            with ui.card().classes('w-full p-6'):
                if path.exists():
                    data=json.loads(path.read_text(encoding='utf-8'))
                    live=data.get('live',{})
                    with ui.row().classes('gap-6 flex-wrap'):
                        for label,value in [('真实任务',live.get('tasks','未运行')),('已知 Token',live.get('known_tokens','未知')),('搜索调用',live.get('searches','未知'))]:
                            with ui.column().classes('gap-1'):ui.label(str(value)).classes('text-3xl font-bold');ui.label(label).classes('muted')
                    ui.label('小样本迭代验证，不代表通用准确率；未独立人工复核。').classes('muted')
                    columns=[{'name':k,'label':v,'field':k,'align':'left'} for k,v in [('case','任务'),('status','研究质量'),('tokens','Token'),('searches','搜索')]]
                    ui.table(columns=columns,rows=live.get('results',[]),row_key='id').classes('w-full')
                    ui.label('固定资料检索对比').classes('text-lg font-semibold')
                    rows=[{'split':split,'method':method,**scores} for split,methods in data.get('retrieval',{}).get('summary',{}).items() for method,scores in methods.items()]
                    ui.table(columns=[{'name':k,'label':label,'field':k,'align':'left'} for k,label in [('split','集合'),('method','方法'),('recall_at_3','Recall@3'),('reciprocal_rank','MRR')]],rows=rows).classes('w-full')
                    ui.label('合成夹具仅用于检索诊断；开发集混合排序低于纯向量，未隐藏退化。').classes('muted text-sm')
                    with ui.expansion('完整验证元数据').classes('w-full'):ui.code(json.dumps(data,ensure_ascii=False,indent=2),language='json').classes('w-full')
                else:ui.label('当前版本尚未生成升级评测汇总。')
    ui.run_with(app,title='AgentScout · 研究工作台',language='zh-CN',storage_secret=service.settings.ui_secret or None,show_welcome_message=False)
