'use strict';
const $ = s => document.querySelector(s),
  E = s => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  } [c]));
const states = {
    inbox: '待整理',
    open: '待处理',
    in_progress: '进行中',
    waiting: '等待反馈',
    done: '已完成',
    cancelled: '已取消'
  },
  priorities = {
    low: '低',
    normal: '普通',
    high: '高优先级',
    urgent: '紧急'
  };
let data = null,
  view = 'overview',
  selected = null;
const titles = {
  overview: '工作总览',
  todos: 'To Do',
  mail: '邮件与业务处理',
  knowledge: '客户关系与知识',
  settings: '设置与运行状态'
};
const toast = message => {
  $('#toast').textContent = message;
  $('#toast').style.display = 'block';
  setTimeout(() => $('#toast').style.display = 'none', 4000)
};
async function api(path, method = 'GET', body, signal) {
  const opt = {
    method,
    signal,
    headers: {
      'X-CSRF-Token': $('meta[name="csrf-token"]').content
    }
  };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) {
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body)
  }
  const r = await fetch('/api/v1' + path, opt);
  if (!r.ok) {
    let p;
    try {
      p = await r.json()
    } catch {
      p = {
        error: '操作失败'
      }
    }
    throw Error(p.error || r.statusText)
  }
  return r.json()
}
const attempt = fn => async (...args) => {
  try {
    return await fn(...args)
  } catch (e) {
    toast(e.message)
  }
};
const date = s => s ? new Date(s).toLocaleString('zh-CN', {
  timeZone: data.timezone || 'Asia/Shanghai',
  hour12: false
}) : '未记录实际时间';
const badge = (s, label) => `<span class="badge ${E(s)}">${E(label||states[s]||s)}</span>`;
const card = (title, body, extra = '') =>
  `<article class="card"><div class="card-heading"><h2>${title}</h2>${extra}</div>${body}</article>`;
const activeTodos = () => data.todos.filter(t => !t.merged_into_id && !['done', 'cancelled'].includes(t
  .status));
const scopedTodos = scope => data.todos.filter(t => !t.merged_into_id && (
  scope === 'active' ? !['done', 'cancelled'].includes(t.status) :
  scope === 'priority' ? !['done', 'cancelled'].includes(t.status) && ['high', 'urgent'].includes(t
    .priority) :
  scope === 'waiting' ? t.status === 'waiting' : scope === 'done' ? t.status === 'done' : true));
const scopeNames = {
  active: '待推进',
  priority: '优先处理',
  waiting: '等待反馈',
  done: '已完成'
};
const searchIcon =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg>';
const searchField = (id, label, placeholder, value) =>
  `<label class="search-field">${searchIcon}<input type="search" id="${id}" aria-label="${label}" placeholder="${placeholder}" value="${E(value)}"></label>`;

function tabBar(items, active, attribute, label) {
  return `<div class="section-tabs" role="tablist" aria-label="${E(label)}">${items.map(([key,text])=>`<button type="button" role="tab" data-${attribute}="${E(key)}" aria-selected="${key===active}" tabindex="${key===active?0:-1}">${E(text)}</button>`).join('')}</div>`;
}

function markTabs(selector, key) {
  document.querySelectorAll(selector).forEach(button => {
    const active = button.getAttribute(selector.slice(1, -1)) === key;
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1
  })
}

function bindTabs(selector, select) {
  const buttons = [...document.querySelectorAll(selector)],
    attribute = selector.slice(1, -1);
  buttons.forEach((button, index) => {
    button.onclick = () => select(button.getAttribute(attribute));
    button.onkeydown = event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event
        .key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next].click();
      document.querySelectorAll(selector)[next]?.focus({
        preventScroll: true
      });
    };
  });
}

function todoRows(todos) {
  return todos.length ? todos.map(t =>
    `<div class="todo-row ${$('#detail-dialog').open && todoDetail.id===t.todo_id?'selected':''}" tabindex="0" role="button" data-todo="${E(t.todo_id)}"><span class="check-circle">${t.status==='done'?'✓':''}</span><div class="todo-text"><div class="todo-title">${E(t.title)}</div><div class="todo-meta">${badge(t.priority,priorities[t.priority])}<span>${E({html:'手工录入',mail_ai:'邮件分析',workbuddy:'WorkBuddy'}[t.source_type])}</span><span class="${!t.due_date&&!t.no_due_date?'deadline-missing':''}">${E(t.no_due_date?'无限期':t.due_date||'待填写截止日期')}</span></div></div>${badge(t.status)}</div>`
  ).join('') : '<div class="empty">暂无事项</div>'
}

function wireTodos() {
  document.querySelectorAll('[data-todo]').forEach(el => {
    el.onclick = attempt(() => openTodo(el.dataset.todo));
    el.onkeydown = e => {
      if (['Enter', ' '].includes(e.key)) {
        e.preventDefault();
        el.click();
      }
    }
  })
}
let readGeneration = 0;
let reading = false;
function loadStatus(message, retry = false) {
  $('#load-status').hidden = !message;
  $('#load-status span').textContent = message;
  $('#retry-load').hidden = !retry;
}

async function refresh() {
  const generation = ++readGeneration;
  reading = true;
  if (!data) loadStatus('正在读取工作台…');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 35000);
  try {
    const next = await api('/snapshot?summary=1', 'GET', undefined, controller.signal);
    if (generation !== readGeneration) return;
    data = next;
    loadStatus('');
    render();
  } catch (err) {
    if (generation !== readGeneration) return;
    const reason = controller.signal.aborted ? '读取超时' : err.message;
    loadStatus((data ? '刷新失败，当前显示上次读取的数据。' : '工作台数据暂时无法读取。') + reason, true);
    throw err;
  } finally {
    clearTimeout(timeout);
    if (generation === readGeneration) reading = false;
  }
}

function switchView(v) {
  closeDetail();
  view = v;
  if (v === 'todos') todoLane.view = 'list';
  if (location.hash !== '#' + v) history.replaceState(null, '', '#' + v);
  selected = null;
  if (v === 'mail' && mailSyncObserved) {
    mailSyncObserved = false;
    attempt(refresh)();
  } else {
    render();
  }
}

function render() {
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  document.body.dataset.view = view;
  document.querySelectorAll('nav button').forEach(b => b.setAttribute('aria-current', b.dataset.view ===
    view ? 'page' : 'false'));
  $('#page-title').textContent = titles[view];
  $('#queue-ai').textContent = {
    overview: '加入 AI 分析队列',
    mail: '加入 AI 分析队列',
    todos: '＋ 新增 To Do',
    knowledge: '＋ 添加知识',
    settings: '刷新状态'
  } [view];
  $('#quick-toggle').disabled = !data;
  $('#queue-ai').disabled = !data;
  if (!data) {
    $('#workspace-content').innerHTML = view === 'settings' ? updateCard() : '';
    if (view === 'settings') attempt(showSoftwareUpdate)();
    return;
  }
  try {
    ({overview, todos: todoView, mail: mailView, knowledge: knowledgeView, settings: settingsView})[view]();
  } catch (err) {
    $('#workspace-content').innerHTML = view === 'settings' ? updateCard() : '';
    loadStatus('页面未能显示：' + err.message, true);
    if (view === 'settings') attempt(showSoftwareUpdate)();
    return;
  }
  wireTodos();
  document.querySelectorAll('[data-work-scope]').forEach(b => b.onclick = () => {
    Object.assign(todoState, {
      scope: b.dataset.workScope,
      status: '',
      query: ''
    });
    switchView('todos');
  });
  document.querySelectorAll('[data-go]').forEach(b => b.onclick = () => switchView(b.dataset.go))
}

function overview() {
  const active = activeTodos(),
    review = data.review_items.filter(r => r.state === 'pending');
  let content =
    `<div class="metrics">${Object.entries(scopeNames).map(([key,label])=>`<button class="metric" data-work-scope="${key}"><span class="metric-label">${label}</span><strong>${String(scopedTodos(key).length).padStart(2,'0')}</strong></button>`).join('')}</div><div class="dashboard-grid"><div>${card('工作清单',todoRows([...active].sort((a,b)=>['urgent','high','normal','low'].indexOf(a.priority)-['urgent','high','normal','low'].indexOf(b.priority)).slice(0,6)),'<button class="text-link" data-go="todos">查看全部 →</button>')}${card('最近沟通',data.messages.slice(0,3).map(m=>`<div class="mail-item" data-mail="${E(m.message_id)}"><strong>${E(m.subject)}</strong><p>${E(m.preview)}</p></div>`).join('')||'<div class="empty">暂无邮件</div>')}</div><div>${card('最近 AI 建议',`<div class="card-body"><div class="insight"><p>${E(data.analyses.at(-1)?.advice||'暂无处理建议')}</p></div><p class="section-space">${E(data.analyses.at(-1)?.summary||'尚无分析结果')}</p></div>`)}${card('工作脉络',`<div class="card-body stack"><div class="label-line"><span class="small">客户与企业</span><b>${data.customers.length}</b></div><div class="label-line"><span class="small">项目与订单</span><b>${data.cases.length}</b></div><div class="label-line"><span class="small">待确认建议</span>${badge('',review.length+' 项')}</div><div class="label-line"><span class="small">已确认知识</span><b>${data.knowledge_items.filter(k=>k.confirmed).length}</b></div></div>`)}<p class="small queue-status">${data.jobs.filter(j=>j.state==='pending').length} 项待处理 · 等待 WorkBuddy</p></div></div>`;
  $('#workspace-content').innerHTML = content;
  wireMail()
}

const todoState = {
  query: '',
  status: '',
  scope: 'all'
};
const todoDetail = {
  id: null,
  tab: 'details',
  fields: null,
  progress: '',
  occurredAt: '',
  timeInitialized: false,
  timeEdited: false,
  correct: null
};

const todoLane = {view:'list', selected:null};
const proposalNames = {todo_input:'自然语言录入',todo_duplicate:'可能重复',todo_candidate:'新事项',todo_change:'进展建议'};

function todoProposal(r, active) {
  const p = JSON.parse(r.payload);
  const target = data.todos.find(t => t.todo_id === p.target);
  const duplicate = r.kind === 'todo_duplicate', candidate = r.kind === 'todo_candidate' || duplicate;
  const dateFields = !p.due && !p.indefinite ? `<div class="review-date"><label>截止日期<input type="date" name="due"></label><label><input type="checkbox" name="indefinite"> 明确无限期</label></div>` : '';
  const create = '<button data-todo-choice="create">确认创建</button>';
  const ignore = '<button class="text-link" data-todo-choice="dismiss">忽略</button>';
  const source = p.source_kind === 'mail' ? `<button class="text-link" data-origin-mail="${E(p.source_id)}">查看原邮件 ↗</button>` : '';
  let body;
  if (r.kind === 'todo_input') {
    const apiMode = data.draft_ai.mode === 'api';
    body = `<h2>整理原始事项</h2><blockquote>${E(p.raw)}</blockquote>
      <small>${E(date(p.input_at))} · ${E(p.timezone)}</small>
      ${apiMode?`<p class="form-note">将向 ${E(data.draft_providers[data.draft_ai.provider])} 发送这条原文及未关闭待办的标题、描述和状态等信息。</p>`:''}
      <footer><button class="primary" data-normalize="${E(r.review_id)}">${apiMode?'整理这条待办':'加入待办整理队列'}</button></footer>`;
  } else if (duplicate && target) {
    body = `<h2>核对重复事项</h2><p class="review-note">${E(p.note)}</p>
      <fieldset class="merge-comparison"><legend>选择合并后保留的事项</legend>
        <label><input type="radio" name="keep-${E(r.review_id)}" value="keep_existing" checked><span>已有事项</span>
          <strong>${E(target.title)}</strong><small>${E(states[target.status])} · ${E(target.due_date||(target.no_due_date?'无限期':'待填写'))}</small></label>
        <label><input type="radio" name="keep-${E(r.review_id)}" value="keep_incoming"><span>本次提取</span>
          <strong>${E(p.title)}</strong><small>${E(p.due|| (p.indefinite?'无限期':'合并时沿用已有日期'))}</small></label></fieldset>
      <div class="review-evidence"><blockquote>${E(p.raw)}</blockquote><div class="review-links">${source}<button class="text-link" data-target-todo="${E(target.todo_id)}">查看已有事项 ↗</button></div></div>
      <footer><button class="primary" data-todo-choice="merge">确认合并</button>${ignore}</footer>
      <details class="separate-action"><summary>保留为独立事项</summary>${dateFields}${create}</details>`;
  } else {
    body = `<h2>${E(p.title || target?.title || '核对建议')}</h2><p>${E(p.note)}${p.status?' → '+E(states[p.status]):''}</p>
      <div class="review-evidence"><blockquote>${E(p.raw)}</blockquote>${source}</div>
      ${target?`<button class="text-link" data-target-todo="${E(target.todo_id)}">查看已有事项 ↗</button>`:''}
      ${candidate?dateFields:''}<footer><button class="primary" data-todo-choice="${candidate?'create':'accept'}">${candidate?'确认创建':'确认记录'}</button>${ignore}</footer>`;
  }
  return `<article class="review-sheet" data-review-sheet="${E(r.review_id)}" ${r.kind==='todo_input'?'':`data-proposal="${E(r.review_id)}"`} data-revision="${target?.revision||0}" ${active?'':'hidden'}>${body}</article>`;
}

function todoHistory() {
  const labels = {pending:'等待 WorkBuddy',running:'API 处理中',superseded:'已过期',withdrawn:'已撤回',failed:'失败',completed:'已保存'};
  return `<section class="job-ledger"><header><h2>运行记录</h2><button class="text-link" id="refresh-todo-jobs">刷新结果</button></header>${data.todo_ai_history.map(j=>{
    const n=j.payload && JSON.parse(j.payload);
    const summary=n?[['新增',n.created],['进展',n.progress],['待确认',n.review]].filter(([,v])=>v).map(([k,v])=>k+' '+v).join(' · ')||'无待办变化':'';
    return `<div class="job-entry"><time>${E(date(j.created_at))}</time><strong>${E(labels[j.state]||j.state)}</strong><div>${E(j.error||summary)}
      ${[...new Set(n?.todo_ids||[])].map(id=>`<button class="text-link" data-target-todo="${E(id)}">${E(data.todos.find(t=>t.todo_id===id)?.title||'查看事项')} ↗</button>`).join('')}
      ${j.state==='pending'?`<button class="text-link" data-withdraw-todo="${E(j.job_id)}">撤回</button>`:''}</div></div>`;
  }).join('')||'<div class="empty">暂无待办分析记录</div>'}</section>`;
}

function todoAssistPanel() {
  const isApi=data.draft_ai.mode==='api';
  const pending=data.review_items.filter(r=>r.state==='pending' && Object.hasOwn(proposalNames,r.kind));
  if(!pending.some(r=>r.review_id===todoLane.selected)) todoLane.selected=pending[0]?.review_id;
  const queue=pending.map(r=>{
    const p=JSON.parse(r.payload);
    return `<button data-pick-review="${E(r.review_id)}" aria-pressed="${r.review_id===todoLane.selected}"><small>${proposalNames[r.kind]}</small><strong>${E(p.title||p.raw||p.note)}</strong></button>`;
  }).join('');
  return `<div class="todo-workbar">${tabBar([['list','工作清单'],['review','待处理'+(pending.length?' · '+pending.length:'')],['history','运行记录']],todoLane.view,'todo-lane','待办工作区')}
    <div class="todo-tools"><button id="todo-input-toggle" aria-haspopup="dialog">自然语言录入</button>
    <button id="todo-mail-toggle" aria-haspopup="dialog">${isApi?'从新邮件更新待办':'邮件待办入队'}</button></div></div>
    <dialog class="todo-compose" id="todo-raw-dialog" aria-labelledby="raw-heading"><header><h2 id="raw-heading">自然语言录入</h2><button type="button" class="icon-button" aria-label="关闭" data-compose-close>×</button></header>
    <form id="todo-raw-form" class="stack"><label>原始事项<textarea required maxlength="100000" name="raw" placeholder="例如：明天联系供应商确认样品"></textarea></label><p class="compose-error" role="status"></p><footer><button class="primary">保存原文</button></footer></form></dialog>
    <dialog class="todo-compose" id="todo-mail-range" aria-labelledby="mail-range-heading"><header><h2 id="mail-range-heading">选择待处理邮件</h2><button type="button" class="icon-button" aria-label="关闭" data-compose-close>×</button></header>
    <label>邮件范围 <select id="todo-range"><option value="recent">近 90 天</option><option value="historical">历史邮件（逐项确认）</option></select></label>
    <div id="todo-mail-preview"></div><p class="compose-error" role="status"></p><footer><small>${isApi?E(data.draft_providers[data.draft_ai.provider])+' · '+E(data.draft_ai.model):'WorkBuddy 队列'}</small><button class="primary" id="run-mail-todos" disabled>${isApi?'确认分析本批邮件':'确认加入 WorkBuddy 队列'}</button></footer></dialog>
    <section data-lane-panel="review" ${todoLane.view!=='review'?'hidden':''}>${pending.length?`<div class="review-workspace ${pending.length===1?'single-review':''}">${pending.length>1?`<aside class="review-index" aria-label="待处理事项">${queue}</aside>`:''}<div class="review-main">${pending.map(r=>todoProposal(r,r.review_id===todoLane.selected)).join('')}</div></div>`:'<div class="empty">暂无待处理事项</div>'}</section>
    <section data-lane-panel="history" ${todoLane.view!=='history'?'hidden':''}>${todoHistory()}</section>`;
}

function wireTodoAssist() {
  const rawForm=$('#todo-raw-form'), raw=$('#todo-raw-dialog'), range=$('#todo-mail-range');
  bindTabs('[data-todo-lane]', key => {
    todoLane.view=key;
    markTabs('[data-todo-lane]', key);
    document.querySelectorAll('[data-lane-panel]').forEach(panel => {panel.hidden=panel.dataset.lanePanel!==key});
  });
  document.querySelectorAll('[data-pick-review]').forEach(button => button.onclick=()=>{
    todoLane.selected=button.dataset.pickReview;
    document.querySelectorAll('[data-pick-review]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
    document.querySelectorAll('[data-review-sheet]').forEach(sheet=>{sheet.hidden=sheet.dataset.reviewSheet!==todoLane.selected});
  });
  document.querySelectorAll('[data-compose-close]').forEach(button=>button.onclick=()=>button.closest('dialog').close());
  const inDialog=(dialog,fn)=>async e=>{
    const error=dialog.querySelector('[role=status]');
    error.textContent='';
    try {await fn(e)} catch(err){error.textContent=err.message}
  };
  $('#todo-input-toggle').onclick=()=>{raw.showModal();rawForm.elements.raw.focus()};
  let token=crypto.randomUUID(), mails=[], request=0;
  rawForm.onsubmit=inDialog(raw,async e=>{
    e.preventDefault();
    const button=rawForm.querySelector('button');
    button.disabled=true;
    try {
      const result=await api('/todo-ai/inputs','POST',{raw:rawForm.elements.raw.value,token});
      todoLane.selected=result.input_id;
      todoLane.view='review';
      raw.close();
      await refresh();
      document.querySelector('[data-review-sheet]:not([hidden]) [data-normalize]')?.focus();
    }
    finally {button.disabled=false}
  });
  rawForm.oninput=()=>{token=crypto.randomUUID()};
  const run=async (button,args)=>{
    button.disabled=true;
    try {
      const r=await api('/todo-ai/run','POST',{...args,selection:data.draft_ai});
      todoLane.view=r.state==='pending'?'history':r.review?'review':'list';
      if(range.open) range.close();
      toast(r.state==='pending'?'已入队，等待 WorkBuddy':'待办分析已保存');
      await refresh();
    } finally {button.disabled=false}
  };
  const loadRange=async()=>{
    const id=++request;
    const button=$('#run-mail-todos'), preview=$('#todo-mail-preview');
    mails=[];button.disabled=true;
    const scope=await api('/todo-ai/scope?historical='+($('#todo-range').value==='historical'?'1':'0'));
    if(id!==request)return;
    mails=scope.mails;
    preview.innerHTML=`<p>待处理 ${scope.count} 封 · 本批 ${mails.length} 封</p>${mails.map(m=>`<label class="todo-mail-option"><input type="checkbox" data-scope-mail="${E(m.message_id)}" checked> ${E(m.subject)}</label>`).join('')}
      ${mails.length && data.draft_ai.mode==='api'?'<p class="form-note">将发送本批邮件正文及未关闭待办的标题、描述、状态和截止日期。</p>':''}`;
    preview.onchange=()=>{button.disabled=!preview.querySelector("[data-scope-mail]:checked")};
    button.disabled=!mails.length;
  };
  $('#todo-mail-toggle').onclick=inDialog(range,async()=>{range.showModal();await loadRange()});
  $('#todo-range').onchange=inDialog(range,loadRange);
  $('#run-mail-todos').onclick=inDialog(range,e=>run(e.currentTarget,{mail_ids:[...range.querySelectorAll("[data-scope-mail]:checked")].map(b=>b.dataset.scopeMail),historical:$('#todo-range').value==='historical'}));
  document.querySelectorAll('[data-normalize]').forEach(b=>b.onclick=attempt(()=>run(b,{input_id:b.dataset.normalize})));
  document.querySelectorAll('[data-target-todo]').forEach(b=>b.onclick=attempt(()=>openTodo(b.dataset.targetTodo)));
  document.querySelectorAll('[data-origin-mail]').forEach(b=>b.onclick=attempt(()=>openMail(b.dataset.originMail)));
  document.querySelectorAll('[data-todo-choice]').forEach(b=>b.onclick=attempt(async()=>{
    const row=b.closest('[data-proposal]');
    const action=b.dataset.todoChoice==='merge'?row.querySelector('input[type=radio]:checked').value:b.dataset.todoChoice;
    b.disabled=true;
    try {
      await api('/todo-ai/reviews/'+row.dataset.proposal,'POST',{action,revision:Number(row.dataset.revision),
        due_date:row.querySelector('[name=due]')?.value||null,no_due_date:!!row.querySelector('[name=indefinite]')?.checked});
      if(document.querySelectorAll('[data-review-sheet]').length===1) todoLane.view='list';
      await refresh();
    } finally {b.disabled=false}
  }));
  document.querySelectorAll('[data-withdraw-todo]').forEach(b=>b.onclick=attempt(async()=>{
    await api('/todo-ai/withdraw/'+b.dataset.withdrawTodo,'POST',{});await refresh()
  }));
  if ($('#refresh-todo-jobs')) $('#refresh-todo-jobs').onclick=attempt(refresh);
}

function taskLedgerRows(todos) {
  const sources={html:'手工录入',mail_ai:'邮件分析',workbuddy:'WorkBuddy'};
  return todos.map(t=>`<div class="todo-row ${$('#detail-dialog').open && todoDetail.id===t.todo_id?'selected':''}" tabindex="0" role="button" data-todo="${E(t.todo_id)}">
    <div class="todo-text"><div class="todo-title">${E(t.title)}</div><div class="todo-meta">${badge(t.priority,priorities[t.priority])}<span>${E(sources[t.source_type]||'')}</span></div></div>
    <span class="task-date ${!t.due_date&&!t.no_due_date?'deadline-missing':''}">${E(t.no_due_date?'无限期':t.due_date||'待填写截止日期')}</span>
    ${badge(t.status)}</div>`).join('') || '<div class="empty">暂无符合条件的事项</div>';
}

function todoView() {
  const todos = scopedTodos(todoState.scope);
  $('#workspace-content').innerHTML =
    `
    ${todoAssistPanel()}
    <section class="task-ledger" data-lane-panel="list" ${todoLane.view!=='list'?'hidden':''}>
      <div class="ledger-tools">${searchField('todo-search','搜索 To Do','搜索事项、客户或描述…',todoState.query)}
        <button class="text-link" id="clear-todo-search" hidden>清空搜索</button>
        <select id="todo-status-filter" aria-label="按状态筛选"><option value="">全部状态</option>${Object.entries(states).map(([k,v])=>`<option value="${k}" ${todoState.status===k?'selected':''}>${v}</option>`).join('')}</select>
        <button id="find-duplicates">查重</button><small id="todo-count"></small></div>
      ${todoState.scope!=='all'?`<div class="scope-bar"><span>工作清单 · ${scopeNames[todoState.scope]}</span><button id="clear-todo-scope" class="text-link">显示全部事项</button></div>`:''}
      <div class="ledger-columns" aria-hidden="true"><span>事项</span><span>截止日期</span><span>状态</span></div>
      <div id="todo-list"></div><div id="duplicate-list"></div>
    </section>`;
  wireTodoAssist();
  const filter = () => {
    const visible = todos.filter(t => (!todoState.status || t.status === todoState.status) && (t.title +
        ' ' + t.description + ' ' + (data.customers.find(c => c.customer_id === t.customer_id)?.name ||
          '') + ' ' + (data.cases.find(c => c.case_id === t.case_id)?.title || '')).toLowerCase()
      .includes(todoState.query.toLowerCase()));
    $('#todo-list').innerHTML = taskLedgerRows(visible);
    $('#todo-count').textContent = visible.length===todos.length ? `${visible.length} 项` : `${visible.length} / ${todos.length} 项`;
    $('#clear-todo-search').hidden = !todoState.query;
    wireTodos();
  };
  if ($('#clear-todo-scope')) $('#clear-todo-scope').onclick = () => {
    todoState.scope = 'all';
    todoState.status = '';
    todoView();
  };
  $('#todo-search').oninput = e => {
    todoState.query = e.target.value;
    filter()
  };
  $('#clear-todo-search').onclick = () => {
    todoState.query = '';
    $('#todo-search').value = '';
    filter();
    $('#todo-search').focus()
  };
  $('#todo-status-filter').onchange=e=>{
    todoState.status=e.target.value;
    filter();
  };
  filter();
  $('#find-duplicates').onclick = attempt(async () => {
    const pairs = await api('/duplicates');
    $('#duplicate-list').innerHTML = card('可能重复', pairs.map((p, i) =>
      `<div class="todo-proposal"><strong>${E(p.left.title)} ↔ ${E(p.right.title)}</strong>
       <p>${E(p.left.source_ref)} · ${E(p.right.source_ref)}</p>
       <button data-merge="${i}" data-keep="left">保留「${E(p.left.title)}」</button>
       <button data-merge="${i}" data-keep="right">保留「${E(p.right.title)}」</button></div>`
    ).join('') || '<div class="empty">暂无重复建议</div>');
    document.querySelectorAll('[data-merge]').forEach(button => button.onclick = attempt(async () => {
      const pair = pairs[+button.dataset.merge];
      const keep = pair[button.dataset.keep], other = keep === pair.left ? pair.right : pair.left;
      if (!confirm('确认合并至「' + keep.title + '」并保留双方来源和进展？')) return;
      await api('/merge', 'POST', {keep:keep.todo_id,other:other.todo_id,
        versions:{[keep.todo_id]:keep.revision,[other.todo_id]:other.revision}});
      toast('已合并');
      await refresh();
    }));
  });
}

function progressWallTime(instant = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: data.timezone || 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(instant).map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function progressInstant(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw Error('请填写有效的发生时间');
  const parts = match.slice(1).map(Number),
    wall = Date.UTC(parts[0], parts[1] - 1, parts[2], parts[3], parts[4]);
  let instant = wall;
  for (let i = 0; i < 4; i++) {
    const represented = progressWallTime(new Date(instant));
    const p = represented.match(/\d+/g).map(Number);
    const offset = wall - Date.UTC(p[0], p[1] - 1, p[2], p[3], p[4]);
    if (!offset) break;
    instant += offset;
  }
  if (progressWallTime(new Date(instant)) !== value) throw Error('这个时间在工作时区不存在，请重新选择');
  return new Date(instant).toISOString();
}

const todoDrafts = new Map();
let detailRequest = 0;
let detailTrigger = null;

function rememberTodo() {
  if ($('#detail-dialog').open && $('#detail-dialog').classList.contains('todo-dialog') && selected) {
    todoDrafts.set(todoDetail.id, {
      state: structuredClone(todoDetail),
      record: selected
    });
  }
}

function closeDetail(discard = false) {
  ++detailRequest;
  if (!discard) rememberTodo();
  $('#detail-dialog').close();
  document.body.classList.remove('todo-open');
  document.querySelectorAll('.todo-row.selected').forEach(el => el.classList.remove('selected'));
}
async function openTodo(id = null, keepTab = false) {
  rememberTodo();
  const requestId = ++detailRequest;
  if (!$('#detail-dialog').open) detailTrigger = document.activeElement;
  const isNew = id === null;
  let t = isNew ? {
    title: '',
    description: '',
    owner: 'local-user',
    status: 'inbox',
    priority: 'normal',
    due_date: null,
    no_due_date: false,
    customer_id: null,
    case_id: null,
    completion_criteria: '由用户确认工作完成',
    logs: [],
    sources: [],
    status_events: []
  } : await api('/todos/' + id);
  if (requestId !== detailRequest) return;
  const cached = todoDrafts.get(id);
  if (cached) {
    Object.assign(todoDetail, cached.state);
    if (cached.state.fields) t = {
      ...t,
      ...cached.record,
      logs: t.logs,
      status_events: t.status_events
    };
  }
  selected = t;
  if (!cached && (isNew || todoDetail.id !== id)) Object.assign(todoDetail, {
    id,
    tab: 'details',
    fields: null,
    progress: '',
    occurredAt: '',
    timeInitialized: false,
    timeEdited: false,
    correct: null
  });
  if (!keepTab) {
    todoDetail.tab = 'details';
    if (!todoDetail.progress) {
      todoDetail.timeInitialized = false;
      todoDetail.timeEdited = false;
      todoDetail.occurredAt = '';
    }
  }
  if (todoDetail.tab === 'progress' && !todoDetail.timeInitialized) {
    todoDetail.occurredAt = progressWallTime();
    todoDetail.timeInitialized = true;
  }
  const edit = todoDetail.fields || t;
  $('#detail-dialog').className = 'todo-dialog';
  $('#dialog-label').textContent = isNew ? '新增 To Do' : 'To Do';
  $('#detail-content').innerHTML =
    `<div class="todo-heading"><label class="todo-title-field" for="todo-title">标题<input id="todo-title" name="title" form="edit-todo" value="${E(edit.title)}" placeholder="填写工作事项" required maxlength="100000" ${todoDetail.tab==='details'?'':'readonly'}></label></div>
    ${isNew?'':tabBar([['details','详情'],['progress',`进展 ${t.logs.length}`],['source','来源与历史']],todoDetail.tab,'todo-detail-tab','To Do 详情')}
    <section data-todo-detail-panel="progress" ${todoDetail.tab==='progress'?'':'hidden'}>
      <div class="timeline">${[...t.logs].reverse().map(log=>`<div class="timeline-item"><small>${E(date(log.occurred_at))} · ${E(log.source_type)}${log.corrects_log_id?' · 更正':''}</small><p>${E(log.content)}</p>${JSON.parse(log.evidence_refs||"[]").map(ref=>`<blockquote>${E(ref.quote)} <button class="text-link" data-log-mail="${E(ref.message_id)}">原邮件</button></blockquote>`).join("")}<div class="log-footer"><small>写入 ${E(date(log.recorded_at))}</small><button class="text-link" data-correct="${E(log.log_id)}">更正</button></div></div>`).join('')||'<p class="muted">暂无进展</p>'}</div>
      <form id="progress-form" class="stack compact-form"><textarea id="progress-content" aria-label="进展内容" placeholder="记录进展…" required>${E(todoDetail.progress)}</textarea>
        <div class="inline-form"><label>发生时间 · ${E(data.timezone)}<input id="occurred-at" type="datetime-local" value="${E(todoDetail.occurredAt)}"></label><button class="primary" type="submit">追加进展</button><button type="button" id="cancel-correction" ${todoDetail.correct?'':'hidden'}>取消更正</button></div>
      </form>
    </section>
    <section data-todo-detail-panel="details" ${todoDetail.tab==='details'?'':'hidden'}>
      <form id="edit-todo" class="form-grid compact-form">
        <div class="wide due-date-field ${!edit.due_date&&!edit.no_due_date?'missing':''}"><label class="due-date-heading" for="todo-due-date">截止日期 <span id="due-date-hint" class="badge high" ${edit.due_date||edit.no_due_date?'hidden':''}>待填写</span></label>
          <div class="deadline-controls"><input id="todo-due-date" name="due_date" aria-label="截止日期" type="date" value="${E(edit.due_date||'')}" ${edit.no_due_date?'disabled':'required'}>
          <label class="checkbox-label" for="no-due-date"><input type="checkbox" id="no-due-date" name="no_due_date" ${edit.no_due_date?'checked':''}>无限期</label></div>
        </div>
        <div class="wide todo-short-fields">
          <label>状态<select name="status">${Object.entries(states).map(([k,v])=>`<option value="${k}" ${k===edit.status?'selected':''}>${v}</option>`).join('')}</select></label>
          <label>优先级<select name="priority">${Object.entries(priorities).map(([k,v])=>`<option value="${k}" ${k===edit.priority?'selected':''}>${v}</option>`).join('')}</select></label>
          <label>负责人<input name="owner" value="${E(edit.owner)}"></label>
        </div>
        <label>客户<select name="customer_id"><option value="">未关联</option>${data.customers.map(c=>`<option value="${E(c.customer_id)}" ${c.customer_id===edit.customer_id?'selected':''}>${E(c.name)}</option>`).join('')}</select></label>
        <label>项目 / 订单<select name="case_id"><option value="">未关联</option>${data.cases.map(c=>`<option value="${E(c.case_id)}" ${c.case_id===edit.case_id?'selected':''}>${E(c.title)}</option>`).join('')}</select></label>
        <label class="wide">描述<textarea name="description">${E(edit.description)}</textarea></label><label class="wide">完成条件<input name="completion_criteria" value="${E(edit.completion_criteria)}"></label>
        <div class="wide todo-form-actions"><button id="save-todo" type="submit" class="primary">保存</button></div>
      </form>
    </section>
    <section data-todo-detail-panel="source" ${todoDetail.tab==='source'?'':'hidden'}><div class="mini-heading">原始录入 · ${E(date(t.input_at))} · ${E(t.input_timezone)}</div><div class="detail-raw">${E(t.raw_input)}</div>${(t.merged_inputs||[]).map(m=>`<div class="mini-heading">合并保留的原文</div><div class="detail-raw">${E(m.raw_input)}</div>`).join("")}<div class="small prewrap section-space">${E(t.sources.map(s=>s.source_type+' · '+s.source_ref).join('\n'))}</div><div class="timeline">${[...t.status_events].reverse().map(event=>`<div class="timeline-item"><small>${E(date(event.recorded_at))} · ${E(event.source)}</small><p>${E(states[event.old_status]||'新建')} → ${E(states[event.new_status])}</p></div>`).join('')}</div></section>`;
  if ($('#detail-dialog').matches(':modal')) $('#detail-dialog').close();
  if (!$('#detail-dialog').open) $('#detail-dialog').show();
  document.body.classList.add('todo-open');
  document.querySelectorAll('[data-todo]').forEach(el => el.classList.toggle('selected', el.dataset.todo ===
    id));
  document.querySelectorAll('[data-log-mail]').forEach(b=>b.onclick=attempt(()=>openMail(b.dataset.logMail)));
  if (isNew) $('#todo-title').focus();
  bindTabs('[data-todo-detail-tab]', key => {
    todoDetail.tab = key;
    if (key === 'progress' && !todoDetail.timeInitialized) {
      todoDetail.occurredAt = progressWallTime();
      todoDetail.timeInitialized = true;
      $('#occurred-at').value = todoDetail.occurredAt;
    }
    markTabs('[data-todo-detail-tab]', key);
    $('#save-todo').hidden = key !== 'details';
    $('#todo-title').readOnly = key !== 'details';
    document.querySelectorAll('[data-todo-detail-panel]').forEach(panel => panel.hidden = panel.dataset
      .todoDetailPanel !== key)
  });
  const rememberFields = () => {
    const form = $('#edit-todo'),
      indefinite = form.elements.no_due_date.checked;
    form.elements.due_date.disabled = indefinite;
    form.elements.due_date.required = !indefinite;
    const fields = Object.fromEntries(new FormData(form));
    fields.no_due_date = indefinite;
    fields.due_date = indefinite ? null : form.elements.due_date.value;
    todoDetail.fields = fields;
    const missing = !fields.due_date && !indefinite;
    document.querySelector('.due-date-field').classList.toggle('missing', missing);
    $('#due-date-hint').hidden = !missing;
  };
  $('#edit-todo').oninput = rememberFields;
  $('#todo-title').oninput = rememberFields;
  $('#progress-content').oninput = e => {
    if (!todoDetail.progress && !todoDetail.timeEdited) {
      todoDetail.occurredAt = progressWallTime();
      $('#occurred-at').value = todoDetail.occurredAt;
    }
    todoDetail.progress = e.target.value;
  };
  $('#occurred-at').oninput = e => {
    todoDetail.occurredAt = e.target.value;
    todoDetail.timeEdited = true;
  };
  $('#edit-todo').onsubmit = attempt(async e => {
    e.preventDefault();
    const form = e.currentTarget,
      button = $('#save-todo');
    if (button.disabled) return;
    button.disabled = true;
    try {
      const values = Object.fromEntries(new FormData(form));
      values.title = values.title.trim();
      if (!values.title) throw Error('请填写标题');
      values.no_due_date = form.elements.no_due_date.checked;
      if (values.no_due_date) values.due_date = null;
      for (const key of ['due_date', 'customer_id', 'case_id']) values[key] = values[key] || null;
      if (isNew) {
        await api('/todos', 'POST', {
          ...values,
          raw_input: [values.title, values.description].filter(Boolean).join('\n'),
          input_at: new Date().toISOString(),
          input_timezone: data.timezone || 'Asia/Shanghai'
        });
      } else {
        const changes = Object.fromEntries(Object.entries(values).filter(([key, value]) => key ===
          'no_due_date' ? Number(value) !== Number(t[key]) : value !== t[key]));
        if (Object.keys(changes).length) await api('/todos/' + id, 'PATCH', {
          changes,
          expected_revision: t.revision
        });
      }
      if ($('#edit-todo') === form) {
        todoDetail.fields = null;
        closeDetail(true);
      }
      todoDrafts.delete(id);
      toast('已保存');
      await refresh();
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  });
  document.querySelectorAll('[data-correct]').forEach(button => button.onclick = () => {
    todoDetail.correct = button.dataset.correct;
    $('#progress-content').placeholder = '填写更正内容…';
    $('#progress-content').focus();
    $('#cancel-correction').hidden = false
  });
  $('#cancel-correction').onclick = () => {
    todoDetail.correct = null;
    $('#cancel-correction').hidden = true;
    $('#progress-content').placeholder = '记录进展…'
  };
  $('#progress-form').onsubmit = attempt(async e => {
    e.preventDefault();
    const entered = $('#occurred-at').value;
    const correction = todoDetail.correct;
    await api('/todos/' + id + '/progress', 'POST', {
      content: $('#progress-content').value,
      occurred_at: entered ? progressInstant(entered) : null,
      corrects_log_id: correction
    });
    if (todoDetail.id === id) Object.assign(todoDetail, {
      progress: '',
      occurredAt: '',
      timeInitialized: false,
      timeEdited: false,
      correct: null
    });
    const cachedProgress = todoDrafts.get(id);
    if (cachedProgress) Object.assign(cachedProgress.state, {
      progress: '',
      occurredAt: '',
      timeInitialized: false,
      timeEdited: false,
      correct: null
    });
    toast('进展已保存');
    await refresh();
    if ($('#detail-dialog').open && $('#detail-dialog').classList.contains('todo-dialog') &&
      todoDetail.id === id) await openTodo(id, true);
  });
}

function wireMail() {
  document.querySelectorAll('[data-mail]').forEach(el => el.onclick = () => {
    mailState.messageId = el.dataset.mail;
    mailState.results = null; mailState.pagination = null; mailState.query = '';
    switchView('mail')
  })
}
async function openMail(id) {
  const thread = await api('/mail/' + id + '/thread');
  closeDetail();
  $('#detail-dialog').className = '';
  $('#dialog-label').textContent = '邮件会话';
  $('#detail-content').innerHTML =
    `<h2>相关会话 · ${thread.length} 封</h2>${thread.map(m=>`<div class="mini-heading">${E(m.subject)} · ${E(date(m.date))}</div><div class="detail-raw">${E(m.body_text)}</div>`).join('')}`;
  $('#detail-dialog').showModal()
}

const mailState = {
  query: '',
  results: null,
  pagination: null,
  loading: false,
  messageId: null,
  draftId: null,
  detail: null,
  request: 0,
  searchRequest: 0,
  edits: {},
  feedbackEdits: {}
};

function mailAddress(raw) {
  try {
    return JSON.parse(raw).map(person => person.name ? `${person.name} <${person.address}>` : person.address)
      .join(', ');
  } catch {
    return '';
  }
}

function reviewRow(review) {
  const p = JSON.parse(review.payload),
    todo = data.todos.find(t => t.todo_id === p.todo_id);
  const names = {
    status: '状态调整',
    protected_change: '修改建议',
    historical_todo: '历史事项',
    suggest_link: '关联建议',
    suggest_duplicate: '合并建议',
    propose_knowledge: '知识建议',
    suggest_relationship: '客户与联系人',
    suggest_case: '项目 / 订单',
    confirm_entity: '对象确认',
    ambiguous_date: '日期待确认'
  };
  const changes = p.changes ? Object.entries(p.changes).map(([key, value]) => ({
    title: '标题',
    description: '描述',
    priority: '优先级',
    due_date: '截止日期',
    no_due_date: '无限期',
    completion_criteria: '完成条件',
    status: '状态'
  } [key] || '字段') + '：' + (states[value] || priorities[value] || value)).join('\n') : '';
  const description = [p.title, p.name, p.customer_name, p.contact_name, p.contact_address, p.status ?
    `建议状态：${states[p.status]||p.status}` : '', p.reason, p.content, changes
  ].filter(Boolean).join('\n') || '查看关联事项后处理';
  const manualOnly = ['ambiguous_date', 'suggest_duplicate'].includes(review.kind);
  const needDeadline = todo && !todo.due_date && !todo.no_due_date && ['status', 'protected_change',
    'suggest_link'
  ].includes(review.kind);
  return `<div class="card-body review-row"><b class="small">${E(names[review.kind]||'业务建议')}${todo?' · '+E(todo.title):''}</b><p class="prewrap">${E(description)}</p><div class="button-row">${todo?`<button data-review-todo="${E(todo.todo_id)}">打开 To Do</button>`:''}${!manualOnly?`<button data-review="${E(review.review_id)}" data-accept="true" ${needDeadline?'disabled title="请先设置截止日期"':''}>确认</button>`:''}<button data-review="${E(review.review_id)}" data-accept="false">${manualOnly?'关闭提示':'拒绝'}</button></div></div>`;
}

function mailView() {
  if (mailState.results === null) {
    $('#workspace-content').innerHTML = '<div class="card empty" role="status">正在读取邮件列表… <button id="retry-mail-page">重试</button></div>';
    $('#retry-mail-page').onclick = attempt(() => loadMailPage(1, mailState.query, true));
    if (!mailState.loading) attempt(() => loadMailPage(1, mailState.query, true))();
    return;
  }
  const rows = mailState.results, paging = mailState.pagination;
  if (!rows.some(m => m.message_id === mailState.messageId)) {
    mailState.messageId = rows[0]?.message_id ?? null;
    mailState.draftId = null;
  }
  const unlinked = data.drafts.filter(d => !d.message_id);
  // A draft whose mail is outside the snapshot is not guessed to belong to another message.
  const reviews = data.review_items.filter(r => r.state === 'pending' && !r.kind.startsWith('todo_') && !JSON.parse(r.payload).knowledge_job_id);
  $('#workspace-content').innerHTML = `
    <div class="mail-workspace">
      <article class="card mail-index">
        <div class="card-heading"><h2>邮件</h2><small id="mail-total">${mailState.query ? '匹配 ' : '共 '}${paging.total} 封</small></div>
        <form id="mail-search" class="toolbar mail-search">
      ${searchField('mail-query','搜索邮件','搜索邮件…',mailState.query)}
      <button type="submit">搜索</button>
      <button type="button" id="refresh-mail-list">刷新邮件</button>
      <button type="button" id="clear-mail-search" ${mailState.query ? '' : 'disabled'}>清空搜索</button>
    </form>

        <div id="mail-list">${rows.map(m => `
          <button class="mail-choice ${m.message_id === mailState.messageId ? 'selected' : ''}"
                  data-select-mail="${E(m.message_id)}" aria-pressed="${m.message_id === mailState.messageId}">
            <small class="sender">${E(mailAddress(m.sender))}</small>
            <strong>${E(m.subject || '（无主题）')}</strong>
            <span>${E((m.preview ?? m.body_text ?? '').slice(0, 100))}</span>
            <small>${E(date(m.date))}</small>
          </button>`).join('') || '<div class="empty">没有匹配邮件。</div>'}</div>
        <form id="mail-pagination" class="mail-pagination" aria-label="邮件分页">
          <div role="status">${paging.total ? (paging.page-1)*paging.page_size+1 : 0}–${Math.min(paging.page*paging.page_size,paging.total)} / ${paging.total} 封${paging.new_count ? ' · 有新归档，请刷新' : ''}</div>
          <div class="button-row"><button type="button" id="mail-prev" ${paging.page===1?'disabled':''}>上一页</button><button type="button" id="mail-next" ${paging.page===paging.pages?'disabled':''}>下一页</button></div>
          <label>第 <input aria-label="邮件页码" type="number" name="page" min="1" max="${paging.pages}" value="${paging.page}" required> / ${paging.pages} 页</label><button type="submit">跳转</button>
        </form>
      </article>
      <div id="mail-detail" class="mail-detail" aria-live="polite">
        <div class="card empty">${mailState.messageId ? '正在读取对应邮件与草稿…' : '选择邮件查看草稿'}</div>
      </div>
    </div>
    ${unlinked.length ? `<details class="card unlinked-drafts"><summary>未在当前列表关联到原邮件的草稿 · ${unlinked.length} 份</summary>
      <div class="card-body"><p>请先确认原邮件，再处理这些草稿。</p>
      ${unlinked.map(d => `<p class="prewrap">${E(d.subject)} <small>· ${E(d.draft_id)}</small></p>`).join('')}</div></details>` : ''}
    ${reviews.length ? card('待确认',reviews.map(reviewRow).join('')) : ''}`;
  const searchInput = $('#mail-query');
  searchInput.oninput = () => {
    $('#clear-mail-search').disabled = !searchInput.value && !mailState.query;
  };
  $('#mail-search').onsubmit = attempt(async e => {
    e.preventDefault();
    await loadMailPage(1, searchInput.value.trim(), true);
  });
  $('#clear-mail-search').onclick = attempt(clearMailSearch);
  $('#refresh-mail-list').onclick = attempt(() => loadMailPage(1, mailState.query, true));
  $('#mail-prev').onclick = attempt(() => loadMailPage(paging.page-1));
  $('#mail-next').onclick = attempt(() => loadMailPage(paging.page+1));
  $('#mail-pagination').onsubmit = attempt(async e => {
    e.preventDefault();
    await loadMailPage(Number(e.target.elements.page.value));
  });
  document.querySelectorAll('[data-select-mail]').forEach(button => {
    button.onclick = attempt(() => selectMail(button.dataset.selectMail));
  });
  document.querySelectorAll('[data-review-todo]').forEach(button => button.onclick = attempt(() => openTodo(
    button.dataset.reviewTodo)));
  document.querySelectorAll('[data-review]').forEach(button => button.onclick = attempt(async () => {
    await api('/reviews/' + button.dataset.review, 'POST', {
      accept: button.dataset.accept === 'true'
    });
    toast('建议已处理');
    await refresh();
  }));
  if (mailState.messageId) attempt(() => selectMail(mailState.messageId))();
}

async function loadMailPage(page=1, query=mailState.query, reset=false) {
  const requestId = ++mailState.searchRequest;
  mailState.loading = true;
  const params = new URLSearchParams({page, page_size:50, q:query});
  if (!reset && mailState.pagination) params.set('snapshot', mailState.pagination.snapshot);
  document.querySelectorAll('#mail-pagination button,#mail-search button').forEach(b => b.disabled=true);
  try {
    const result = await api('/mail?' + params);
    if (requestId !== mailState.searchRequest || view !== 'mail') return;
    mailState.query = query;
    mailState.results = result.items;
    mailState.pagination = result;
  } finally {
    if (requestId === mailState.searchRequest) {
      mailState.loading = false;
      if (view==='mail' && mailState.results !== null) mailView();
    }
  }
}
async function clearMailSearch() {
  await loadMailPage(1, '', true);
  $('#mail-query')?.focus();
}

async function selectMail(messageId) {
  if (mailState.messageId !== messageId) mailState.draftId = null;
  mailState.messageId = messageId;
  mailState.detail = null;
  const requestId = ++mailState.request;
  document.querySelectorAll('[data-select-mail]').forEach(button => {
    const active = button.dataset.selectMail === messageId;
    button.classList.toggle('selected', active);
    button.setAttribute('aria-pressed', String(active));
  });
  $('#mail-detail').innerHTML = '<div class="card empty">正在读取对应邮件与草稿…</div>';
  const detail = await api('/mail/' + messageId);
  if (requestId !== mailState.request || view !== 'mail') return;
  mailState.detail = detail;
  if (!detail.drafts.some(d => d.draft_id === mailState.draftId)) mailState.draftId = detail.drafts[0]
    ?.draft_id ?? null;
  renderMailDetail();
}

function renderMailDetail() {
  const detail = mailState.detail;
  if (!detail) return;
  const m = detail.message;
  const draft = detail.drafts.find(d => d.draft_id === mailState.draftId);
  const apiMode = data.draft_ai.mode === 'api';
  const providerName = data.draft_providers[data.draft_ai.provider];
  const job = detail.draft_jobs[0];
  const jobStates = {pending:'等待 WorkBuddy 处理',running:'API 请求处理中',failed:'生成失败',superseded:'原文或草稿已更改',withdrawn:'任务已撤回',completed:'草稿已保存'};
  const feedback = detail.feedback.filter(f => f.target_id === draft?.draft_id);
  const edited = mailState.edits[draft?.draft_id] ?? draft;
  const sourceScroll = document.querySelector('.source-mail')?.scrollTop ?? 0;
  $('#mail-detail').innerHTML = `
    <article class="card mail-reply-pair" data-message-id="${E(m.message_id)}">
      <section class="source-mail">
        <div class="pair-heading"><h3>原邮件</h3><button class="text-link" id="mail-thread">相关会话 →</button></div>
        <h2 class="mail-subject">${E(m.subject || '（无主题）')}</h2>
        <div class="mail-envelope"><span>发件人：${E(mailAddress(m.sender))}</span><time>${E(date(m.date))}</time></div>
        <div class="prewrap source-mail-body">${E(m.body_text)}</div>
        ${detail.analyses.length ? `<details class="mail-analysis"><summary>分析建议 · ${detail.analyses.length}</summary>
          ${detail.analyses.map(a => `<div class="insight section-space"><span class="badge">${E(a.work_type)}</span> ${badge('', a.stage)}
          <p class="prewrap">${E(a.summary)}</p><p class="prewrap">${E(a.advice)}</p></div>`).join('')}</details>` : ''}
      </section>
      <section class="reply-section">
        <div class="pair-heading"><h3>回复草稿</h3>${draft?'<span class="badge rose">AI 草稿</span>':''}</div>
        ${draft ? `
          ${detail.drafts.length > 1 ? `<div class="draft-tabs" role="tablist" aria-label="回复草稿">${detail.drafts.map((d, i) => `<button type="button" role="tab" data-draft-tab="${E(d.draft_id)}" aria-selected="${d.draft_id === draft.draft_id}" tabindex="${d.draft_id === draft.draft_id ? 0 : -1}" title="${E(date(d.created_at))} · 修订 ${d.revision}">草稿 ${i + 1}</button>`).join('')}</div>` : ''}
          <form id="mail-draft-form" class="draft-form" data-draft="${E(draft.draft_id)}">
            <label class="draft-subject-label">回复主题
              <textarea name="subject" aria-label="草稿主题" class="draft-subject" rows="2" required>${E(edited.subject)}</textarea>
            </label>
            <label class="draft-body-label">英文回复正文
              <textarea name="body" aria-label="英文草稿" class="draft-body" required>${E(edited.body)}</textarea>
            </label>
          </form>
          <div class="reply-actions"><button type="submit" form="mail-draft-form" class="primary" id="save-mail-draft">保存草稿</button><button type="button" id="queue-rewrite">${apiMode?"按反馈重写":"加入 AI 重写队列"}</button><button type="button" id="copy-mail-draft">复制正文</button></div><p class="form-note">草稿不会自动发送</p>
          <details class="draft-feedback" data-feedback-for="${E(draft.draft_id)}" ${mailState.feedbackEdits[draft.draft_id] ? 'open' : ''}>
            <summary>给这份草稿提供反馈${feedback.length ? ` · ${feedback.length}` : ''}</summary>
            ${feedback.length ? `<div class="feedback-history">${feedback.map(f => `<div class="feedback-entry"><small>${E(date(f.created_at))}</small><div class="prewrap">${E(f.content)}</div></div>`).join('')}</div>` : ''}
            <form id="draft-feedback-form" class="stack"><label>修改意见<textarea name="content" aria-label="这份草稿的反馈" placeholder="例如：语气再简洁一些，补充交期说明。" required>${E(mailState.feedbackEdits[draft.draft_id] || '')}</textarea></label><button type="submit">保存这份草稿的反馈</button></form>
          </details>` : `<div class="empty">暂无对应草稿</div><button type="button" class="primary" id="generate-mail-draft">${apiMode?"生成回复草稿":"加入草稿生成队列"}</button>`}
        <div class="draft-job-info"><small>${apiMode ? E(providerName)+' · '+E(data.draft_ai.model) : 'WorkBuddy 队列'}</small>
          <span role="status" id="draft-run-status">${E(job ? (job.error || jobStates[job.state] || job.state) : '')}</span>
          ${job && ['pending','running'].includes(job.state)?'<button class="text-link" id="refresh-draft-job">刷新结果</button>':''}
          ${detail.draft_jobs.filter(j=>j.state==='pending').map(j=>`<button class="text-link" data-withdraw-job="${E(j.job_id)}">撤回排队任务</button>`).join('')}</div>
      </section>
    </article>`;
  document.querySelector('.source-mail').scrollTop = sourceScroll;
  $('#mail-thread').onclick = attempt(() => openMail(m.message_id));
  const runDraft = attempt(async e => {
    const button = e.currentTarget;
    if (draft && (mailState.edits[draft.draft_id] || mailState.feedbackEdits[draft.draft_id]?.trim())) {
      toast(apiMode ? '请先保存草稿及修改意见，再按反馈重写' : '请先保存草稿及修改意见，再加入 AI 重写队列');
      return;
    }
    button.disabled = true;
    const status = $('#draft-run-status');
    status.textContent = apiMode ? '正在请求 ' + providerName + '…' : '正在加入队列…';
    try {
      const result = draft && !apiMode ?
        await api('/drafts/' + draft.draft_id + '/queue','POST',{}) :
        await api('/mail/' + m.message_id + '/draft','POST',{draft_id:draft?.draft_id, selection:data.draft_ai});
      if (view === 'mail' && mailState.messageId === m.message_id) {
        if (result.state === 'completed') mailState.draftId = result.draft_id;
        await selectMail(m.message_id);
        toast(result.queued ? '已加入队列，等待 WorkBuddy 处理' : '草稿已保存');
      }
    } catch (error) {
      status.textContent = error.message;
      toast(error.message);
    } finally { button.disabled = false; }
  });
  const draftButton = $('#queue-rewrite') || $('#generate-mail-draft');
  draftButton.onclick = runDraft;
  const refreshDraft = $('#refresh-draft-job');
  if (refreshDraft) refreshDraft.onclick = attempt(() => {mailState.draftId = null; return selectMail(m.message_id);});
  document.querySelectorAll('[data-withdraw-job]').forEach(button => button.onclick = attempt(async () => {
    await api('/draft-jobs/' + button.dataset.withdrawJob + '/withdraw','POST',{});
    if (view === 'mail' && mailState.messageId === m.message_id) await selectMail(m.message_id);
  }));

  if (!draft) return;
  document.querySelectorAll('[data-draft-tab]').forEach(button => {
    const activate = id => {
      mailState.draftId = id;
      renderMailDetail();
      document.querySelector('[data-draft-tab][aria-selected="true"]').focus({
        preventScroll: true
      });
    };
    button.onclick = () => activate(button.dataset.draftTab);
    button.onkeydown = event => {
      const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      const index = detail.drafts.findIndex(d => d.draft_id === draft.draft_id);
      const count = detail.drafts.length;
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? count - 1 : (index + (event.key ===
        'ArrowRight' ? 1 : -1) + count) % count;
      activate(detail.drafts[next].draft_id);
    };
  });
  const subjectInput = $('#mail-draft-form').elements.subject;
  const resizeSubject = () => {
    subjectInput.style.height = 'auto';
    subjectInput.style.height = subjectInput.scrollHeight + 'px';
  };
  resizeSubject();
  $('#mail-draft-form').oninput = e => {
    mailState.edits[draft.draft_id] = Object.fromEntries(new FormData(e.currentTarget));
    resizeSubject();
  };
  $('#draft-feedback-form').oninput = e => {
    mailState.feedbackEdits[draft.draft_id] = e.currentTarget.elements.content.value;
  };
  $('#mail-draft-form').onsubmit = attempt(async e => {
    e.preventDefault();
    const form = e.target;
    const button = $('#save-mail-draft');
    button.disabled = true;
    try {
      const values = Object.fromEntries(new FormData(form));
      await api('/drafts/' + draft.draft_id, 'PATCH', {
        ...values,
        expected_revision: draft.revision
      });
      delete mailState.edits[draft.draft_id];
      Object.assign(draft, values, {
        revision: draft.revision + 1
      });
      toast('这份草稿已保存');
    } finally {
      button.disabled = false;
    }
  });
  $('#copy-mail-draft').onclick = attempt(async () => {
    await navigator.clipboard.writeText($('#mail-draft-form').elements.body.value);
    toast('这份草稿正文已复制');
  });
  $('#draft-feedback-form').onsubmit = attempt(async e => {
    e.preventDefault();
    const form = e.target;
    const content = form.elements.content.value;
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const result = await api('/drafts/' + draft.draft_id + '/feedback', 'POST', {
        content
      });
      detail.feedback.push({
        feedback_id: result.feedback_id,
        target_id: draft.draft_id,
        content: content.trim(),
        created_at: new Date().toISOString()
      });
      delete mailState.feedbackEdits[draft.draft_id];
      if (!form.isConnected) return;
      // Only append history: keep any edits in the draft editor intact.
      let history = document.querySelector('.draft-feedback .feedback-history');
      if (!history) {
        history = document.createElement('div');
        history.className = 'feedback-history';
        form.before(history);
      }
      const entry = document.createElement('div');
      entry.className = 'feedback-entry';
      entry.innerHTML =
        `<small>${E(date(detail.feedback.at(-1).created_at))}</small><div class="prewrap">${E(content.trim())}</div>`;
      history.append(entry);
      form.reset();
      toast('反馈已关联到这份草稿');
    } finally {
      button.disabled = false;
    }
  });
}

const knowledgeState = {
  scope: 'personal',
  entityId: null,
  query: ''
};

function knowledgeReviewPanel(scope, subject) {
  const pending = data.review_items.filter(r=>r.kind==='propose_knowledge' && r.state==='pending')
    .map(r=>({...r, proposal:JSON.parse(r.payload)}))
    .filter(r=>r.proposal.scope===scope && (r.proposal.subject_id||null)===subject);
  const jobs = data.knowledge_jobs.filter(j=>j.scope===scope && j.subject_id===subject);
  if (!pending.length && !jobs.length) return '';
  return card('待确认与整理记录', pending.map(r=>{
    const quotes=JSON.parse(r.evidence_refs).map(e=>e.quote).filter(Boolean);
    return `<section class="knowledge-proposal"><p>${E(r.proposal.content)}</p>
      ${quotes.length?`<blockquote>原文 · ${E(quotes.join(' / '))}</blockquote>`:''}
      <div class="button-row"><button class="primary" data-knowledge-review="${E(r.review_id)}" data-accept="true">确认入库</button>
      <button class="text-link" data-knowledge-review="${E(r.review_id)}" data-accept="false">忽略</button></div></section>`;
  }).join('') + jobs.map(j=>`<div class="knowledge-job"><strong>${E(({pending:'等待 WorkBuddy',running:'模型整理中',completed:'未提取到适用知识',failed:'整理失败'})[j.state])}</strong>
    <span>${E(j.raw.slice(0,90))}</span>${j.error?`<small>${E(j.error)}</small>`:''}
    ${j.state==='pending'?`<button class="text-link" data-knowledge-withdraw="${E(j.job_id)}">撤回</button>`:''}
    ${j.state==='failed'?`<button class="text-link" data-knowledge-retry="${E(j.job_id)}">检查原文并重试</button>`:''}</div>`).join(''),
    '<button class="text-link" id="knowledge-refresh">刷新结果</button>');
}

function openKnowledgeInput(scope, subject, name, original='') {
  closeDetail();
  const cfg=data.draft_ai, direct=cfg.mode==='api';
  $('#detail-dialog').className='editor-dialog';
  $('#dialog-label').textContent='整理原文';
  $('#detail-content').innerHTML=`<form id="knowledge-input-form" class="stack compact-form">
    <h2>${E(name)}</h2><label>原文<textarea required maxlength="20000" rows="7" name="raw" placeholder="粘贴客户要求、沟通笔记或工作习惯">${E(original)}</textarea></label>
    <p class="form-note">${direct?`将向 ${E(data.draft_providers[cfg.provider])} 发送此对象名称、范围和原文。`:'由 WorkBuddy 整理，结果将在此页等待确认。'}</p>
    <div class="button-row"><button class="primary" type="submit">${direct?'用模型整理':'加入 WorkBuddy 整理队列'}</button></div>
    <span role="status" class="form-note"></span></form>`;
  const form=$('#knowledge-input-form');
  $('#detail-dialog').showModal();
  form.elements.raw.focus();
  form.onsubmit=async event=>{
    event.preventDefault();
    const button=form.querySelector('button'), status=form.querySelector('[role=status]');
    button.disabled=true;
    status.textContent=direct?'模型正在整理…':'正在加入队列…';
    try {
      const result=await api('/knowledge-ai/run','POST',{scope,subject_id:subject,raw:form.elements.raw.value,selection:cfg});
      if(form.isConnected && $('#detail-dialog').open) $('#detail-dialog').close();
      await refresh();
      toast(result.existing?'相同原文已有整理记录':result.state==='pending'?'已加入 WorkBuddy 队列':result.proposed?'整理完成，请核对建议':'原文中未提取到适用知识');
    } catch(error) {
      status.textContent=error.message;
      button.disabled=false;
    }
  };
}


function knowledgeView() {
  const scope = knowledgeState.scope,
    q = knowledgeState.query.toLowerCase();
  const scoped = data.knowledge_items.filter(k => k.scope === scope);
  let entities = scope === 'personal' ? [{
    id: 'personal',
    name: '个人习惯'
  }] : (scope === 'customer' ? data.customers.map(c => ({
    id: c.customer_id,
    name: c.name
  })) : data.cases.map(c => ({
    id: c.case_id,
    name: c.title
  })));
  if (q && scope !== 'personal') entities = entities.filter(entity => (entity.name + ' ' + scoped.filter(k =>
    k.subject_id === entity.id).map(k => k.content).join(' ') + ' ' + data.contacts.filter(c => c
    .customer_id === entity.id).map(c => c.name + ' ' + c.address).join(' ')).toLowerCase().includes(q));
  if (!entities.some(e => e.id === knowledgeState.entityId)) knowledgeState.entityId = entities[0]?.id ??
    null;
  const current = entities.find(e => e.id === knowledgeState.entityId);
  const entityMatches = !!q && current && (current.name + ' ' + data.contacts.filter(c => c.customer_id ===
    current.id).map(c => c.name + ' ' + c.address).join(' ')).toLowerCase().includes(q);
  const items = scoped.filter(k => (scope === 'personal' || k.subject_id === current?.id) && (!q ||
    entityMatches || k.content.toLowerCase().includes(q)));
  const contacts = scope === 'customer' ? data.contacts.filter(c => c.customer_id === current?.id) : [];
  const cases = scope === 'customer' ? data.cases.filter(c => c.customer_id === current?.id) : [];
  $('#workspace-content').innerHTML =
    `${tabBar([['personal','个人习惯'],['customer','客户'],['case','项目 / 订单']],scope,'knowledge-scope','知识范围')}
    <div class="toolbar">${searchField('knowledge-search','搜索客户与知识','搜索客户、项目或知识…',knowledgeState.query)}<button id="clear-knowledge-search" ${knowledgeState.query?'':'disabled'}>清空搜索</button></div>
    <div class="object-workspace"><article class="card object-index">${entities.map(entity=>`<button class="object-choice ${current?.id===entity.id?'selected':''}" data-knowledge-entity="${E(entity.id)}" aria-pressed="${current?.id===entity.id}"><strong>${E(entity.name)}</strong><small>${scoped.filter(k=>scope==='personal'||k.subject_id===entity.id).length} 条知识</small></button>`).join('')||'<div class="empty">暂无匹配对象</div>'}</article>
    <div>${card(current?E(current.name):'知识',items.map(k=>`<div class="knowledge-row"><div><span class="badge">${k.confirmed?'已确认':'候选'}</span><p class="prewrap">${E(k.content)}</p></div><button data-edit-knowledge="${E(k.knowledge_id)}">${k.confirmed?'编辑':'确认 / 编辑'}</button></div>`).join('')||'<div class="empty">暂无知识</div>',`<div class="button-row"><small>${items.length} 条</small>${current?'<button id="knowledge-organize">整理原文</button>':''}</div>`)}
    ${current?knowledgeReviewPanel(scope,scope==='personal'?null:current.id):''}
    ${contacts.length||cases.length?`<details class="card related-objects"><summary>联系人 ${contacts.length} · 项目 / 订单 ${cases.length}</summary><div class="card-body">${contacts.map(c=>`<div class="compact-row"><strong>${E(c.name)}</strong><span>${E(c.address)}</span></div>`).join('')}${cases.map(c=>`<div class="compact-row"><span>${E(c.title)}</span>${badge('',c.stage||'未设阶段')}</div>`).join('')}</div></details>`:''}
    ${scope==='case'&&current?`<div class="small muted">${E(data.cases.find(c=>c.case_id===current.id)?.stage||'未设阶段')}</div>`:''}</div></div>`;
  const subject=scope==='personal'?null:current?.id;
  if(current) $('#knowledge-organize').onclick=()=>openKnowledgeInput(scope,subject,current.name);
  if($('#knowledge-refresh')) $('#knowledge-refresh').onclick=attempt(refresh);
  document.querySelectorAll('[data-knowledge-review]').forEach(button=>button.onclick=attempt(async()=>{
    await api('/reviews/'+button.dataset.knowledgeReview,'POST',{accept:button.dataset.accept==='true'});
    await refresh();
    toast(button.dataset.accept==='true'?'知识已确认入库':'已忽略建议');
  }));
  document.querySelectorAll('[data-knowledge-withdraw]').forEach(button=>button.onclick=attempt(async()=>{
    await api('/knowledge-ai/withdraw/'+button.dataset.knowledgeWithdraw,'POST',{});
    await refresh();
  }));
  document.querySelectorAll('[data-knowledge-retry]').forEach(button=>button.onclick=()=>{
    const job=data.knowledge_jobs.find(j=>j.job_id===button.dataset.knowledgeRetry);
    openKnowledgeInput(scope,subject,current.name,job.raw);
  });
  bindTabs('[data-knowledge-scope]', key => {
    knowledgeState.scope = key;
    knowledgeState.entityId = null;
    knowledgeView()
  });
  document.querySelectorAll('[data-knowledge-entity]').forEach(button => button.onclick = () => {
    knowledgeState.entityId = button.dataset.knowledgeEntity;
    knowledgeView()
  });
  $('#knowledge-search').oninput = e => {
    const position = e.target.selectionStart;
    knowledgeState.query = e.target.value;
    knowledgeView();
    $('#knowledge-search').focus();
    $('#knowledge-search').setSelectionRange(position, position)
  };
  $('#clear-knowledge-search').onclick = () => {
    knowledgeState.query = '';
    knowledgeView();
    $('#knowledge-search').focus()
  };
  document.querySelectorAll('[data-edit-knowledge]').forEach(button => button.onclick = () =>
    openKnowledgeEditor(data.knowledge_items.find(k => k.knowledge_id === button.dataset.editKnowledge)));
}

function openKnowledgeEditor(item = null) {
  closeDetail();
  $('#detail-dialog').className = 'editor-dialog';
  $('#dialog-label').textContent = '知识';
  const scope = item?.scope || knowledgeState.scope;
  $('#detail-content').innerHTML = `<h2>${item?'编辑知识':'添加知识'}</h2><form id="knowledge-form" class="stack compact-form">
    <label>范围<select name="scope" aria-label="知识范围" ${item?'disabled':''}><option value="personal" ${scope==='personal'?'selected':''}>个人习惯</option><option value="customer" ${scope==='customer'?'selected':''}>客户长期要求</option><option value="case" ${scope==='case'?'selected':''}>项目 / 订单要求</option></select></label>
    <label id="knowledge-subject-label">对象<select name="subject_id" aria-label="知识对象"></select></label>
    <label>内容<textarea name="content" aria-label="知识内容" required>${E(item?.content||'')}</textarea></label>
    <label class="checkbox-label"><input name="confirmed" type="checkbox" ${!item||item.confirmed?'checked':''}>已确认</label>
    <button class="primary" type="submit">保存知识</button></form>`;
  const form = $('#knowledge-form');
  const subjects = () => {
    const selectedScope = form.elements.scope.value,
      options = selectedScope === 'customer' ? data.customers.map(c => [c.customer_id, c.name]) :
      selectedScope === 'case' ? data.cases.map(c => [c.case_id, c.title]) : [];
    $('#knowledge-subject-label').hidden = selectedScope === 'personal';
    form.elements.subject_id.required = selectedScope !== 'personal';
    form.elements.subject_id.innerHTML = options.map(([id, name]) =>
      `<option value="${E(id)}" ${id===(item?.subject_id||knowledgeState.entityId)?'selected':''}>${E(name)}</option>`
    ).join('');
    form.elements.subject_id.disabled = !!item;
  };
  subjects();
  form.elements.scope.onchange = subjects;
  form.onsubmit = attempt(async e => {
    e.preventDefault();
    const p = {
      scope: form.elements.scope.value,
      subject_id: form.elements.scope.value === 'personal' ? null : form.elements.subject_id.value,
      content: form.elements.content.value,
      confirmed: form.elements.confirmed.checked
    };
    if (item) p.expected_revision = item.revision;
    await api('/knowledge' + (item ? '/' + item.knowledge_id : ''), item ? 'PATCH' : 'POST', p);
    knowledgeState.scope = p.scope;
    knowledgeState.entityId = p.subject_id || 'personal';
    $('#detail-dialog').close();
    toast('知识已保存');
    await refresh();
  });
  if (!$('#detail-dialog').open) $('#detail-dialog').showModal();
}

const settingsState = {
  tab: ['accounts','update'].includes(sessionStorage.getItem('workthread-settings-tab')) ? sessionStorage.getItem('workthread-settings-tab') : 'runtime'
};
function updateCard() {
  return card('软件更新','<div class="card-body stack"><div id="update-status" class="prewrap" role="status"></div><div id="update-actions" class="button-row"></div></div>');
}
const updatePhases = {
  check: '检查更新', download: '下载', verify: '校验安装包', apply: '安装',
  quiet: '检查停写', handoff: '启动升级工具', 'waiting-stop': '等待旧工作台退出',
  'snapshot-workspace': '备份正式工作空间', 'snapshot-acceptance': '备份验收工作空间',
  'trial-workspace': '验证正式空间副本', 'trial-acceptance': '验证验收空间副本',
  switching: '切换程序和工作空间', restarting: '启动新版并检查健康状态'
};
async function showSoftwareUpdate() {
  const status = $('#update-status'), actions = $('#update-actions');
  let watching = false;
  const pendingKey = 'workthread-update-pending';
  const active = job => job && !['succeeded', 'failed'].includes(job.phase);
  const paint = (r, checked=false) => {
    if (!status.isConnected) return;
    actions.replaceChildren();
    const lines = ['当前版本：'+r.current];
    const job = r.attempt;
    if (job?.phase === 'succeeded' && job.target_commit === r.current_commit)
      lines.push('已更新至 '+job.target_version);
    else if (job?.phase === 'failed')
      lines.push('更新未完成 · '+(updatePhases[job.failed_stage] || '安装'), job.error);
    else if (!job && r.last) lines.push(r.last.error ? '上次更新失败：'+r.last.error : '已更新至 '+r.last.version);
    if (r.transaction === 'rolled-back') lines.push('原版本与工作空间已恢复。');
    if (r.checked_at) lines.push('上次成功检查：'+date(r.checked_at));
    if (r.offer) lines.push('可用版本：'+r.offer.version, r.offer.notes);
    else if (checked || r.check_message) lines.push(r.check_message || '已成功检查，暂无适用于此安装的已发布更新。');
    if (r.last_error) lines.push(r.last_error.operation+'失败 · '+date(r.last_error.time), r.last_error.message, '诊断编号 '+r.last_error.reference);
    if (!r.enabled) lines.push('请在 Windows 正式工作空间中检查更新。');
    if (active(job)) lines.push('正在备份并重启。请保持此页面打开。', updatePhases[job.phase], '更新编号 '+job.id);
    else if (r.operation) lines.push('正在'+(updatePhases[r.operation] || '处理更新')+'…');
    status.textContent = lines.filter(Boolean).join('\n');
    if (active(job) || r.operation) {
      watch(active(job) ? job.id : null);
      return;
    }
    const button = (label, operation) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.disabled = !r.enabled;
      b.onclick = async () => {
        if (operation === 'apply' && !window.confirm('请先关闭 WorkBuddy。工作台将暂停、备份两个工作空间，并重启更新。继续吗？')) return;
        const id = operation === 'apply' ? crypto.randomUUID().replaceAll('-', '') : null;
        if (id) sessionStorage.setItem(pendingKey, JSON.stringify({id}));
        for (const el of actions.children) el.disabled = true;
        status.textContent += '\n正在'+updatePhases[operation]+'…';
        try {
          const next = await api('/software-update/'+operation,'POST', id ? {confirmed:true, attempt_id:id} : {});
          paint(next, operation === 'check');
        } catch (err) {
          try {
            const latest = await api('/software-update', 'GET', undefined, AbortSignal.timeout(3000));
            if (id && latest.attempt?.id !== id) sessionStorage.removeItem(pendingKey);
            paint(latest);
            if (!latest.last_error && !active(latest.attempt)) status.textContent += '\n'+err.message;
          } catch (_) {
            if (operation === 'apply') {
              actions.replaceChildren();
              status.textContent = '已提交更新确认，等待工作台重新连接。';
              watch(id);
            } else {
              paint(r);
              status.textContent += '\n'+err.message;
            }
          }
        }
      };
      actions.append(b);
    };
    button('检查更新','check');
    if (r.offer && !r.ready) button('下载并检查','download');
    if (r.ready) button('备份并重启更新','apply');
    if (r.last_error || job?.phase === 'failed') {
      const copy = document.createElement('button');
      copy.textContent = '复制诊断信息';
      copy.onclick = attempt(async () => {
        await navigator.clipboard.writeText(JSON.stringify({
          current: r.current, current_commit: r.current_commit,
          attempt: job || null, error: r.last_error || null
        }, null, 2));
        toast('诊断信息已复制');
      });
      actions.append(copy);
    }
  };

  async function watch(id) {
    if (watching) return;
    watching = true;
    if (id) sessionStorage.setItem(pendingKey, JSON.stringify({id}));
    const started = Date.now();
    while (status.isConnected) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      if (!status.isConnected) break;
      try {
        const r = await api('/software-update', 'GET', undefined, AbortSignal.timeout(3000));
        if (id && r.attempt?.id !== id) {
          if (r.operation || Date.now()-started < 15000) continue;
          sessionStorage.removeItem(pendingKey);
          watching = false;
          paint(r);
          status.textContent += '\n未收到本次更新已启动的确认，请核对当前状态。';
          return;
        }
        if (!r.operation && !active(r.attempt)) {
          sessionStorage.removeItem(pendingKey);
          watching = false;
          if (id) {
            sessionStorage.setItem('workthread-update-return','1');
            location.reload();
          } else paint(r);
          return;
        }
        if (!id && r.attempt && active(r.attempt)) {
          id = r.attempt.id;
          sessionStorage.setItem(pendingKey, JSON.stringify({id}));
        }
        if (active(r.attempt))
          status.textContent = '正在备份并重启。请保持此页面打开。\n'+(updatePhases[r.attempt.phase] || '');
      } catch (_) { /* The detached updater owns the installation during restart. */ }
      const seconds = Math.floor((Date.now()-started)/1000);
      if (seconds >= 15*60)
        status.textContent = '尚未确认更新完成，仍在等待工作台连接。请勿重复启动或覆盖安装。';
      else if (!status.textContent.includes('正在备份并重启') && id)
        status.textContent = '正在备份并重启。请保持此页面打开。';
    }
  }

  let pending;
  try { pending = JSON.parse(sessionStorage.getItem(pendingKey)); } catch (_) { sessionStorage.removeItem(pendingKey); }
  try {
    const r = await api('/software-update', 'GET', undefined, AbortSignal.timeout(3000));
    if (pending?.id && r.attempt?.id !== pending.id) {
      status.textContent = '正在等待本次更新结果。';
      watch(pending.id);
      return;
    }
    if (pending && !active(r.attempt)) sessionStorage.removeItem(pendingKey);
    paint(r);
  } catch (err) {
    if (pending) {
      status.textContent = '正在等待工作台重新连接。';
      watch(pending.id);
      return;
    }
    status.textContent = '无法读取本机更新状态：' + err.message;
    const retry = document.createElement('button');
    retry.textContent = '重新读取更新状态';
    retry.onclick = attempt(showSoftwareUpdate);
    actions.replaceChildren(retry);
  }
}

const runStates = {
  pending: '待执行',
  running: '运行中',
  interrupted: '已中断',
  blocked: '文件夹标识已变化',
  completed: '已完成',
  failed: '失败',
  partial: '部分完成',
  superseded: '已过期'
};

const syncLabels = {
  queued: ['任务已受理', '准备拉取…'],
  idle: ['尚未拉取', '开始拉取'],
  running: ['正在拉取', '正在拉取…'],
  database_wait: ['本地数据库暂时被占用，稍后自动继续', '等待数据库…'],
  reconnecting: ['邮箱连接未完成，正在尝试恢复', '正在重连…'],
  interrupted: ['拉取已中断', '继续拉取（断点续传）'],
  blocked: ['文件夹标识已变化，旧断点已停用。请核对邮箱文件夹设置。', '续传已停用'],
  completed: ['本轮拉取完成', '检查新邮件'],
  partial: ['本轮结束，有邮件异常', '再次拉取'],
  failed: ['拉取失败，请按下方原因处理后重试', '重新拉取']
};
let syncPollPending = false;
let mailSyncObserved = false;
const submittedSyncs = new Set();
async function refreshMailProgress() {
  if (view !== 'settings' || settingsState.tab !== 'accounts' || syncPollPending) return;
  syncPollPending = true;
  try {
    const statuses = await api('/accounts/sync-status');
    for (const button of document.querySelectorAll('[data-sync]')) {
      const id = button.dataset.sync, status = statuses[id];
      if (!status) continue;
      const [label, action] = syncLabels[status.state] || syncLabels.failed;
      const lines = [label];
      if (status.task_id) {
        mailSyncObserved = true;
        lines.push('任务编号 ' + status.task_id);
      }
      if (['failed','interrupted','reconnecting','database_wait','blocked'].includes(status.state) && (status.error_detail || status.error)) {
        lines.push([status.stage, status.current_uid ? 'UID '+status.current_uid : '',
          status.error_detail || status.error].filter(Boolean).join(' · '));
      }
      for (const failure of (status.message_errors || []).slice(-5)) {
        lines.push('单封邮件异常 · '+failure.folder+' · UID '+failure.uid+' · '+failure.detail);
      }
      if ((status.message_errors || []).length > 5) lines.push('此处显示最近 5 条单封异常，完整近期记录保存在该任务状态中。');
      if (status.sent_unresolved) {
        if (status.state === 'partial') lines[0] = '本轮收件箱拉取结束';
        lines.push('已发送文件夹未能自动识别，请打开本邮箱的“文件夹设置”。');
      }
      if (status.sent_configured && status.state === 'partial') lines[0] = '文件夹设置已保存，可再次拉取';
      if (status.state === 'reconnecting') lines[0] += '，第 ' + status.attempt + ' 次自动重连';
      if (status.folder && ['running','interrupted','reconnecting','database_wait','failed','blocked'].includes(status.state)) {
        lines[0] += ' · ' + status.folder;
      }
      for (const [name, counts] of Object.entries(status.folders || {})) {
        if (!counts) { lines.push(name + ' · 尚未取得邮件清单'); continue; }
        const pending = counts.total - counts.archived - counts.errors;
        lines.push(name + ' · 已归档 ' + counts.archived + ' / ' + counts.total +
          ' · 待拉取 ' + pending + ' · 异常 ' + counts.errors);
      }
      const target = button.closest('.account-row').querySelector('[data-mail-progress]');
      const message = lines.join('\n');
      if (target.textContent !== message) target.textContent = message;
      button.textContent = action;
      button.disabled = submittedSyncs.has(id) || ['queued','running','reconnecting','database_wait','blocked'].includes(status.state);
    }
  } finally {
    syncPollPending = false;
  }
}

function draftSettingsCard() {
  const cfg = data.draft_ai;
  return card('邮件草稿、待办与知识整理', `<form id="draft-ai-settings" class="card-body form-grid compact-form">
    <label>执行方式<select name="mode"><option value="workbuddy">WorkBuddy 队列</option><option value="api" ${cfg.mode==='api'?'selected':''}>模型 API</option></select></label>
    <fieldset id="draft-provider-fields" ${cfg.mode==='api'?'':'hidden'}>
      <label>服务商<select name="provider">${Object.entries(data.draft_providers).map(([id,name])=>`<option value="${id}" ${cfg.provider===id?'selected':''}>${E(name)}</option>`).join('')}</select></label>
      <label>模型 ID<input name="model" maxlength="160" value="${E(cfg.model)}" placeholder="填写服务商控制台中的模型 ID"></label>
      <label>API Key<input name="key" type="password" autocomplete="new-password" placeholder="留空沿用已保存的密钥"></label>
      <p class="form-note">草稿仅发送相关邮件、知识和反馈。整理待办时，所选服务商会收到所选原文及未关闭待办的标题、描述、状态和截止日期。知识整理仅发送所选对象名称、范围和原文。</p>
    </fieldset>
    <div class="button-row"><button class="primary" type="submit">保存 AI 设置</button><button id="test-draft-api" type="button" ${cfg.mode==='api'?'':'hidden'}>用合成邮件测试连接</button></div>
    <span role="status" id="draft-settings-status"></span></form>`);
}

function wireDraftSettings() {
  const form = $('#draft-ai-settings'), fields = form.elements;
  const sync = () => {
    const enabled = fields.mode.value === 'api';
    $('#draft-provider-fields').hidden = !enabled;
    fields.model.required = enabled;
    $('#test-draft-api').hidden = !enabled;
    $('#test-draft-api').disabled = !enabled || data.draft_ai.mode !== 'api' ||
      fields.provider.value !== data.draft_ai.provider || fields.model.value !== data.draft_ai.model || !!fields.key.value;
  };
  fields.provider.onchange = () => {
    fields.key.value = '';
    fields.model.value = fields.provider.value === data.draft_ai.provider ? data.draft_ai.model : '';
    sync();
  };
  form.oninput = sync;
  sync();
  form.onsubmit = attempt(async e => {
    e.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    data.draft_ai = await api('/draft-ai/settings','POST', values.mode==='api' ? values : {mode:'workbuddy'});
    fields.key.value = '';
    sync();
    $('#draft-settings-status').textContent = 'AI 设置已保存';
  });
  $('#test-draft-api').onclick = attempt(async e => {
    const button = e.currentTarget;
    button.disabled = true;
    const status = $('#draft-settings-status');
    status.textContent = '正在测试…';
    try {
      await api('/draft-ai/test','POST',{selection:data.draft_ai});
      status.textContent = '连接成功，模型已返回合成草稿';
    } catch (error) {
      status.textContent = error.message;
    } finally { sync(); }
  });
}

function settingsView() {
  $('#workspace-content').innerHTML = `${tabBar([['runtime','运行与 AI'],['accounts','邮箱'],['backup','备份与恢复'],['update','软件更新']],settingsState.tab,'settings-tab','设置分类')}
    <section data-settings-panel="runtime" ${settingsState.tab==='runtime'?'':'hidden'}>
      <div class="status-strip"><span>${badge('','工作台已连接')}</span><span>WorkBuddy 定时分析：${data.health.ai_schedule.enabled?'已启用':'未启用'}</span><button id="health-check">健康检查</button><button id="consume-results">读取 AI 结果</button>${data.accounts.some(a=>a.account_id==='demo')?'<button id="demo-ai">模拟分析</button>':''}</div>
      ${draftSettingsCard()}
      <div class="split">${card('执行计划',`<form id="schedule-form" class="card-body form-grid compact-form"><label>工作时区<input name="timezone" value="${E(data.timezone)}"></label><label>每日分析时间<input name="time" type="time" value="${E(data.health.ai_schedule.time)}"></label><label>邮件同步间隔（分钟）<input name="interval" type="number" min="1" max="1440" value="${E(data.imap_interval_minutes)}"></label><div class="form-note">每日一次</div><button type="submit" class="primary">保存计划</button></form>`)}
      ${card('最近任务',`<div class="table-scroll"><table><thead><tr><th>时间</th><th>状态</th></tr></thead><tbody>${data.jobs.slice(0,6).map(j=>`<tr><td>${E(date(j.created_at))}</td><td>${badge('',runStates[j.state]||j.state)}</td></tr>`).join('')||'<tr><td colspan="2">暂无任务</td></tr>'}</tbody></table></div>`)}</div>
      <details class="card related-objects"><summary>运行信息与同步记录</summary><div class="card-body"><p class="prewrap">${E(data.health.workspace)}</p><div class="small muted">Windows / 真实邮箱 / WorkBuddy 无人值守：待验收</div>${data.sync_runs.slice(-5).map(r=>`<div class="compact-row"><time>${E(date(r.started_at))}</time>${badge('',runStates[r.state]||r.state)}</div>`).join('')||'<p>暂无同步记录</p>'}</div></details>
    </section>
    <section data-settings-panel="accounts" ${settingsState.tab==='accounts'?'':'hidden'}>
      ${card('邮箱',data.accounts.map(a=>`<div class="account-row"><div><strong>${E(a.label)}</strong><p>${E(a.username)} · ${a.enabled?'同步已启用':'同步已暂停'}</p><div class="small muted prewrap" role="status" data-mail-progress></div></div><div class="button-row"><button data-sync="${E(a.account_id)}" disabled>读取状态…</button>${a.account_id!=='demo'?`<button data-folder-settings="${E(a.account_id)}">文件夹设置</button><button data-account-toggle="${E(a.account_id)}">${a.enabled?'暂停':'启用'}同步</button><button data-remove-account="${E(a.account_id)}">移除邮箱</button>`:''}</div></div>`).join('')||'<div class="empty">暂无邮箱</div>')}
      <details class="card related-objects" id="account-editor"><summary>添加邮箱</summary>
      <form id="account-form" class="card-body form-grid compact-form"><label>名称<input name="label" required></label><label>账号<input name="username" required autocomplete="off"></label><label>IMAP 主机<input name="host" placeholder="imap.example.org" required></label><label>TLS 端口<input name="port" type="number" value="993"></label><label class="wide">授权码<input name="password" type="password" autocomplete="new-password"></label>
      <details class="wide advanced-fields"><summary>文件夹设置</summary><div class="form-grid"><label>收件箱<input name="inbox_folder" placeholder="INBOX"></label><label>已发送<input name="sent_folder" placeholder="自动识别"></label><label class="wide">其他文件夹<input name="extra_folders" placeholder="逗号分隔"></label></div></details>
      <button type="submit" class="primary">保存配置</button><span class="form-note">保存后同步默认暂停；授权码存入系统凭证库</span></form></details>
    </section>
    <section data-settings-panel="update" ${settingsState.tab==='update'?'':'hidden'}>
      ${updateCard()}
    </section>
    <section data-settings-panel="backup" ${settingsState.tab==='backup'?'':'hidden'}><div class="split">
      ${card('备份',`<div class="card-body stack compact-form"><div class="button-row"><button data-backup="todos">备份 To Do</button><button data-backup="full" class="primary">完整备份</button></div><span class="form-note">普通 ZIP，无需密码，不含邮箱授权码</span></div>`)}
      ${card('恢复',`<form id="restore-form" class="card-body stack compact-form"><label>备份文件<input type="file" name="file" accept=".zip" required></label><button type="submit">校验备份</button><div id="restore-preview" class="small prewrap"></div><button type="button" id="apply-restore" class="primary" hidden>确认恢复</button></form>`)}</div>
    </section>`;
  wireDraftSettings();
  bindTabs('[data-settings-tab]', key => {
    settingsState.tab = key;
    sessionStorage.setItem('workthread-settings-tab', key);
    if (key === 'accounts') attempt(refreshMailProgress)();
    if (key === 'update') attempt(showSoftwareUpdate)();
    markTabs('[data-settings-tab]', key);
    document.querySelectorAll('[data-settings-panel]').forEach(panel => panel.hidden = panel.dataset
      .settingsPanel !== key)
  });
  if (settingsState.tab === 'accounts') attempt(refreshMailProgress)();
  if (settingsState.tab === 'update') attempt(showSoftwareUpdate)();
  $('#health-check').onclick = attempt(async () => {
    const h = await api('/system/status');
    toast(h.ok ? '健康检查通过' : '健康检查发现异常')
  });
  $('#consume-results').onclick = attempt(async () => {
    const r = await api('/ai/consume', 'POST', {});
    toast('已读取 ' + r.length + ' 个交换文件');
    await refresh()
  });
  if ($('#demo-ai')) $('#demo-ai').onclick = attempt(async () => {
    await api('/demo/analyze', 'POST', {});
    toast('模拟分析已导入，草稿已生成');
    await refresh()
  });
  $('#schedule-form').onsubmit = attempt(async e => {
    e.preventDefault();
    const f = e.target.elements;
    await api('/settings', 'POST', {
      timezone: f.timezone.value,
      ai_schedule: {
        enabled: false,
        frequency: 'daily',
        time: f.time.value
      },
      imap_interval_minutes: +f.interval.value
    });
    toast('计划已保存');
    await refresh()
  });
  $('#account-form').onsubmit = attempt(async e => {
    e.preventDefault();
    const p = Object.fromEntries(new FormData(e.target));
    p.enabled = false;
    p.folders = p.sent_folder ? [{
      name: p.inbox_folder || 'INBOX',
      direction: 'inbox'
    }, {
      name: p.sent_folder,
      direction: 'sent'
    }, ...p.extra_folders.split(',').map(x => x.trim()).filter(Boolean).map(name => ({
      name,
      direction: 'other'
    }))] : [];
    for (const k of ['inbox_folder', 'sent_folder', 'extra_folders']) delete p[k];
    await api('/accounts', 'POST', p);
    toast('配置已保存，同步暂停');
    await refresh()
  });
  document.querySelectorAll('[data-sync]').forEach(el => el.onclick = attempt(async () => {
    const id = el.dataset.sync;
    if (id !== 'demo' && !confirm('现在连接此邮箱并拉取尚未归档的邮件？')) return;
    el.disabled = true;
    submittedSyncs.add(id);
    try {
      const key = 'mail-submit:' + id;
      const requestId = sessionStorage.getItem(key) || crypto.randomUUID();
      sessionStorage.setItem(key, requestId);
      const task = await api('/accounts/' + encodeURIComponent(id) + '/sync-tasks', 'POST', {request_id: requestId});
      sessionStorage.removeItem(key);
      toast((syncLabels[task.state] || syncLabels.failed)[0] + ' · ' + task.task_id.slice(0, 8));
    } finally {
      submittedSyncs.delete(id);
      await refreshMailProgress();
    }
  }));
  document.querySelectorAll('[data-folder-settings]').forEach(button => button.onclick = attempt(async () => {
    const path = '/accounts/' + encodeURIComponent(button.dataset.folderSettings) + '/folders';
    button.disabled = true;
    button.textContent = '读取文件夹…';
    try {
      const options = await api(path, 'POST', {});
      if (!button.isConnected || settingsState.tab !== 'accounts') return;
      closeDetail();
      $('#detail-dialog').className = '';
      $('#dialog-label').textContent = '文件夹设置';
      $('#detail-content').innerHTML = `<form class="stack compact-form" id="sent-settings">
        <label>已发送邮件所在的文件夹<select required name="sent"><option value="">请选择</option>
        ${options.names.map((name, i) => `<option value="${i}">${E(name)}</option>`).join('')}
        <option value="skip">跳过已发送文件夹</option></select></label>
        <button class="primary">保存文件夹设置</button></form>`;
      const form = $('#sent-settings');
      const current = options.automatic ? options.detected : options.current;
      const index = options.names.indexOf(current);
      if (index >= 0) form.elements.sent.value = String(index);
      else if (!options.automatic && current === null) form.elements.sent.value = 'skip';
      form.onsubmit = attempt(async e => {
        e.preventDefault();
        const value = form.elements.sent.value;
        if (!value) return;
        const save = form.querySelector('button');
        save.disabled = true;
        try {
          await api(path, 'POST', {sent: value === 'skip' ? null : options.names[Number(value)]});
          if (form.isConnected) closeDetail();
          toast('设置已保存，下次拉取时生效');
          await refreshMailProgress();
        } finally { save.disabled = false }
      });
      $('#detail-dialog').showModal();
    } finally {
      button.disabled = false;
      button.textContent = '文件夹设置';
    }
  }));
  document.querySelectorAll('[data-remove-account]').forEach(button => button.onclick = attempt(async () => {
    const account = data.accounts.find(a => a.account_id === button.dataset.removeAccount);
    if (!confirm(`移除邮箱“${account.label}”（${account.username}）并删除本机保存的授权码？已归档邮件、待办和知识将保留。`)) return;
    await api('/accounts/' + encodeURIComponent(account.account_id), 'DELETE');
    await refresh();
    toast('邮箱已移除，已归档邮件已保留');
  }));
  document.querySelectorAll('[data-account-toggle]').forEach(el => el.onclick = attempt(async () => {
    const a = data.accounts.find(x => x.account_id === el.dataset.accountToggle);
    if (!a.enabled && !confirm('启用后，应用运行期间会按周期连接此邮箱。确认启用？')) return;
    await api('/accounts/' + a.account_id + '/enabled', 'POST', {
      enabled: !a.enabled
    });
    await refresh()
  }));
  document.querySelectorAll('[data-backup]').forEach(el => el.onclick = attempt(async () => {
    const r = await fetch('/api/v1/backup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': $('meta[name="csrf-token"]').content
      },
      body: JSON.stringify({
        scope: el.dataset.backup
      })
    });
    if (!r.ok) throw Error((await r.json()).error);
    const url = URL.createObjectURL(await r.blob()),
      a = document.createElement('a');
    a.href = url;
    a.download = /filename="?([^";]+)"?/.exec(r.headers.get('Content-Disposition') || '')?.[1] ||
      'WorkThread-' + (el.dataset.backup === 'todos' ? 'Todos-' : 'Full-') + new Date().toISOString()
      .slice(0, 10) + '.zip';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    toast('ZIP 备份已生成')
  }));
  const restoreBody = apply => {
    const f = new FormData($('#restore-form'));
    f.append('apply', String(apply));
    return f
  };
  $('#restore-form').onsubmit = attempt(async e => {
    e.preventDefault();
    const p = await api('/restore', 'POST', restoreBody(false));
    $('#restore-preview').textContent = '校验通过 · ' + p.manifest.scope + ' · ' + Object.keys(p.manifest
      .files).length + ' 个文件 · ' + p.manifest.total_size + ' 字节\n' + p.files.map(f => f.path + ' (' +
      f.size + ' 字节)').join('\n') + '\n恢复前保留现有数据副本。';
    $('#apply-restore').hidden = false
  });
  $('#restore-form [name=file]').onchange = () => {
    $('#apply-restore').hidden = true;
    $('#restore-preview').textContent = '';
  };
  $('#apply-restore').onclick = attempt(async () => {
    await api('/restore', 'POST', restoreBody(true));
    toast('恢复完成，请重新授权并检查运行状态');
    await refresh()
  })
}

$('#quick-toggle').onclick = attempt(() => openTodo());
document.querySelectorAll('nav button').forEach(b => b.onclick = () => switchView(b.dataset.view));
$('#close-detail').onclick = () => {
  closeDetail();
  if (detailTrigger?.isConnected) detailTrigger.focus();
};
$('#detail-dialog').addEventListener('cancel', e => {
  e.preventDefault();
  closeDetail();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && $('#detail-dialog').open && !$('#detail-dialog').matches(':modal')) {
    e.preventDefault();
    closeDetail();
    if (detailTrigger?.isConnected) detailTrigger.focus();
  }
});
$('#nav-toggle').onclick = () => {
  const collapsed = document.body.classList.toggle('nav-collapsed');
  $('#nav-toggle').setAttribute('aria-expanded', String(!collapsed));
  $('#nav-toggle').setAttribute('aria-label', collapsed ? '展开导航' : '收起导航');
  $('#nav-toggle').title = collapsed ? '展开导航' : '收起导航';
};
window.addEventListener('hashchange', () => {
  const next = location.hash.slice(1);
  if (titles[next] && next !== view) switchView(next);
});
if (titles[location.hash.slice(1)]) view = location.hash.slice(1);
if (sessionStorage.getItem('workthread-update-return')) {
  sessionStorage.removeItem('workthread-update-return');
  settingsState.tab = 'update';
  view = 'settings';
}
$('#queue-ai').onclick = attempt(async () => {
  if (view === 'todos') {
    await openTodo();
    return
  }
  if (view === 'knowledge') {
    openKnowledgeEditor();
    return
  }
  if (view === 'settings') {
    await refresh();
    toast('状态已刷新');
    return
  }
  const r = await api('/ai/jobs', 'POST', {});
  toast(r.existing ? '已有待处理任务，等待 WorkBuddy 处理' : '已加入 AI 分析队列，等待 WorkBuddy 处理');
  await refresh()
});
$('#retry-load').onclick = attempt(refresh);
render();
attempt(refresh)();
setInterval(() => {
  if (!reading && !document.hidden && !$('#detail-dialog').open && view === 'overview') attempt(refresh)()
}, 15000);

setInterval(() => { if (!document.hidden) attempt(refreshMailProgress)() }, 2000);
