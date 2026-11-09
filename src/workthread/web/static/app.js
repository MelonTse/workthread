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
let data = {},
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
async function api(path, method = 'GET', body) {
  const opt = {
    method,
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
async function refresh() {
  data = await api('/snapshot');
  render()
}

function switchView(v) {
  closeDetail();
  view = v;
  if (location.hash !== '#' + v) history.replaceState(null, '', '#' + v);
  selected = null;
  render()
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
  ({
    overview: overview,
    todos: todoView,
    mail: mailView,
    knowledge: knowledgeView,
    settings: settingsView
  } [view])();
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
    `<div class="metrics">${Object.entries(scopeNames).map(([key,label])=>`<button class="metric" data-work-scope="${key}"><span class="metric-label">${label}</span><strong>${String(scopedTodos(key).length).padStart(2,'0')}</strong></button>`).join('')}</div><div class="dashboard-grid"><div>${card('工作清单',todoRows([...active].sort((a,b)=>['urgent','high','normal','low'].indexOf(a.priority)-['urgent','high','normal','low'].indexOf(b.priority)).slice(0,6)),'<button class="text-link" data-go="todos">查看全部 →</button>')}${card('最近沟通',data.messages.slice(0,3).map(m=>`<div class="mail-item" data-mail="${E(m.message_id)}"><strong>${E(m.subject)}</strong><p>${E(m.body_text.slice(0,100))}</p></div>`).join('')||'<div class="empty">暂无邮件</div>')}</div><div>${card('最近 AI 建议',`<div class="card-body"><div class="insight"><p>${E(data.analyses.at(-1)?.advice||'暂无处理建议')}</p></div><p class="section-space">${E(data.analyses.at(-1)?.summary||'尚无分析结果')}</p></div>`)}${card('工作脉络',`<div class="card-body stack"><div class="label-line"><span class="small">客户与企业</span><b>${data.customers.length}</b></div><div class="label-line"><span class="small">项目与订单</span><b>${data.cases.length}</b></div><div class="label-line"><span class="small">待确认建议</span>${badge('',review.length+' 项')}</div><div class="label-line"><span class="small">已确认知识</span><b>${data.knowledge_items.filter(k=>k.confirmed).length}</b></div></div>`)}<p class="small queue-status">${data.jobs.filter(j=>j.state==='pending').length} 项待处理 · 等待 WorkBuddy</p></div></div>`;
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

function todoView() {
  const todos = scopedTodos(todoState.scope);
  $('#workspace-content').innerHTML =
    `
    <div class="toolbar">${searchField('todo-search','搜索 To Do','搜索事项、客户或描述…',todoState.query)}<button id="clear-todo-search" ${todoState.query?'':'disabled'}>清空搜索</button><button id="find-duplicates">查重</button></div>
    ${todoState.scope!=='all'?`<div class="scope-bar"><span>工作清单 · ${scopeNames[todoState.scope]}</span><button id="clear-todo-scope" class="text-link">显示全部事项</button></div>`:''}
    ${tabBar([['','全部'],...Object.entries(states)],todoState.status,'todo-status','To Do 状态')}
    ${card('事项清单',`<div id="todo-list"></div>`,`<small id="todo-count"></small>`)}<div id="duplicate-list"></div>`;
  const filter = () => {
    const visible = todos.filter(t => (!todoState.status || t.status === todoState.status) && (t.title +
        ' ' + t.description + ' ' + (data.customers.find(c => c.customer_id === t.customer_id)?.name ||
          '') + ' ' + (data.cases.find(c => c.case_id === t.case_id)?.title || '')).toLowerCase()
      .includes(todoState.query.toLowerCase()));
    $('#todo-list').innerHTML = todoRows(visible);
    $('#todo-count').textContent = `${visible.length} / ${todos.length} 项`;
    $('#clear-todo-search').disabled = !todoState.query;
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
  bindTabs('[data-todo-status]', key => {
    todoState.status = key;
    markTabs('[data-todo-status]', key);
    filter()
  });
  filter();
  $('#find-duplicates').onclick = attempt(async () => {
    const pairs = await api('/duplicates');
    $('#duplicate-list').innerHTML = card('可能重复', pairs.map((p, i) =>
      `<div class="compact-row"><span>${E(p.left.title)} ↔ ${E(p.right.title)}</span><button data-merge="${i}">合并</button></div>`
    ).join('') || '<div class="empty">暂无重复建议</div>');
    document.querySelectorAll('[data-merge]').forEach(button => button.onclick = attempt(async () => {
      const pair = pairs[+button.dataset.merge];
      if (!confirm('合并并保留全部来源、日志？')) return;
      const a = await api('/todos/' + pair.left.todo_id),
        b = await api('/todos/' + pair.right.todo_id);
      await api('/merge', 'POST', {
        keep: a.todo_id,
        other: b.todo_id,
        versions: {
          [a.todo_id]: a.revision,
          [b.todo_id]: b.revision
        }
      });
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
      <form id="progress-form" class="stack compact-form"><textarea id="progress-content" aria-label="进展内容" placeholder="记录进展…" required>${E(todoDetail.progress)}</textarea>
        <div class="inline-form"><label>发生时间 · ${E(data.timezone)}<input id="occurred-at" type="datetime-local" value="${E(todoDetail.occurredAt)}"></label><button class="primary" type="submit">追加进展</button><button type="button" id="cancel-correction" ${todoDetail.correct?'':'hidden'}>取消更正</button></div>
      </form>
      <div class="timeline">${[...t.logs].reverse().map(log=>`<div class="timeline-item"><small>${E(date(log.occurred_at))} · ${E(log.source_type)}${log.corrects_log_id?' · 更正':''}</small><p>${E(log.content)}</p><div class="log-footer"><small>写入 ${E(date(log.recorded_at))}</small><button class="text-link" data-correct="${E(log.log_id)}">更正</button></div></div>`).join('')||'<p class="muted">暂无进展</p>'}</div>
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
    <section data-todo-detail-panel="source" ${todoDetail.tab==='source'?'':'hidden'}><div class="mini-heading">原始录入 · ${E(date(t.input_at))} · ${E(t.input_timezone)}</div><div class="detail-raw">${E(t.raw_input)}</div><div class="small prewrap section-space">${E(t.sources.map(s=>s.source_type+' · '+s.source_ref).join('\n'))}</div><div class="timeline">${[...t.status_events].reverse().map(event=>`<div class="timeline-item"><small>${E(date(event.recorded_at))} · ${E(event.source)}</small><p>${E(states[event.old_status]||'新建')} → ${E(states[event.new_status])}</p></div>`).join('')}</div></section>`;
  if ($('#detail-dialog').matches(':modal')) $('#detail-dialog').close();
  if (!$('#detail-dialog').open) $('#detail-dialog').show();
  document.body.classList.add('todo-open');
  document.querySelectorAll('[data-todo]').forEach(el => el.classList.toggle('selected', el.dataset.todo ===
    id));
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
  const rows = mailState.results ?? data.messages;
  if (!rows.some(m => m.message_id === mailState.messageId)) {
    mailState.messageId = rows[0]?.message_id ?? null;
    mailState.draftId = null;
  }
  const unlinked = data.drafts.filter(d => !d.message_id || !data.messages.some(m => m.message_id === d
    .message_id));
  // A draft whose mail is outside the snapshot is not guessed to belong to another message.
  const reviews = data.review_items.filter(r => r.state === 'pending');
  $('#workspace-content').innerHTML = `
    <div class="mail-workspace">
      <article class="card mail-index">
        <div class="card-heading"><h2>最近邮件</h2><small>${rows.length} 封${mailState.results ? '匹配' : ''}</small></div>
        <form id="mail-search" class="toolbar mail-search">
      ${searchField('mail-query','搜索邮件','搜索邮件…',mailState.query)}
      <button type="submit">搜索</button>
      <button type="button" id="clear-mail-search" ${mailState.query ? '' : 'disabled'}>清空搜索</button>
    </form>

        <div id="mail-list">${rows.map(m => `
          <button class="mail-choice ${m.message_id === mailState.messageId ? 'selected' : ''}"
                  data-select-mail="${E(m.message_id)}" aria-pressed="${m.message_id === mailState.messageId}">
            <small class="sender">${E(mailAddress(m.sender))}</small>
            <strong>${E(m.subject || '（无主题）')}</strong>
            <span>${E(m.body_text.slice(0, 100))}</span>
            <small>${E(date(m.date))}</small>
          </button>`).join('') || '<div class="empty">没有匹配邮件。</div>'}</div>
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
    const query = searchInput.value.trim();
    if (!query) {
      clearMailSearch();
      return;
    }
    const requestId = ++mailState.searchRequest;
    const result = await api('/mail/search?q=' + encodeURIComponent(query));
    if (requestId !== mailState.searchRequest || view !== 'mail') return;
    mailState.query = query;
    mailState.results = result;
    mailView();
  });
  $('#clear-mail-search').onclick = clearMailSearch;
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

function clearMailSearch() {
  ++mailState.searchRequest;
  mailState.query = '';
  mailState.results = null;
  mailView();
  $('#mail-query').focus();
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
          <div class="reply-actions"><button type="submit" form="mail-draft-form" class="primary" id="save-mail-draft">保存草稿</button><button type="button" id="queue-rewrite">加入 AI 重写队列</button><button type="button" id="copy-mail-draft">复制正文</button></div><p class="form-note">草稿不会自动发送</p>
          <details class="draft-feedback" data-feedback-for="${E(draft.draft_id)}" ${mailState.feedbackEdits[draft.draft_id] ? 'open' : ''}>
            <summary>给这份草稿提供反馈${feedback.length ? ` · ${feedback.length}` : ''}</summary>
            ${feedback.length ? `<div class="feedback-history">${feedback.map(f => `<div class="feedback-entry"><small>${E(date(f.created_at))}</small><div class="prewrap">${E(f.content)}</div></div>`).join('')}</div>` : ''}
            <form id="draft-feedback-form" class="stack"><label>修改意见<textarea name="content" aria-label="这份草稿的反馈" placeholder="例如：语气再简洁一些，补充交期说明。" required>${E(mailState.feedbackEdits[draft.draft_id] || '')}</textarea></label><button type="submit">保存这份草稿的反馈</button></form>
          </details>` : `<div class="empty">暂无对应草稿</div>`}
      </section>
    </article>`;
  document.querySelector('.source-mail').scrollTop = sourceScroll;
  $('#mail-thread').onclick = attempt(() => openMail(m.message_id));
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
  $('#queue-rewrite').onclick = attempt(async e => {
    const button = e.currentTarget;
    if (mailState.edits[draft.draft_id] || mailState.feedbackEdits[draft.draft_id]?.trim()) {
      toast('请先保存草稿及修改意见，再加入 AI 重写队列');
      return;
    }
    button.disabled = true;
    try {
      const result = await api('/drafts/' + draft.draft_id + '/queue', 'POST', {});
      toast(result.existing ? '这份草稿已在队列中，等待 WorkBuddy 处理' : '已加入 AI 重写队列，等待 WorkBuddy 处理');
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
    <div>${card(current?E(current.name):'知识',items.map(k=>`<div class="knowledge-row"><div><span class="badge">${k.confirmed?'已确认':'候选'}</span><p class="prewrap">${E(k.content)}</p></div><button data-edit-knowledge="${E(k.knowledge_id)}">${k.confirmed?'编辑':'确认 / 编辑'}</button></div>`).join('')||'<div class="empty">暂无知识</div>',`<small>${items.length} 条</small>`)}
    ${contacts.length||cases.length?`<details class="card related-objects"><summary>联系人 ${contacts.length} · 项目 / 订单 ${cases.length}</summary><div class="card-body">${contacts.map(c=>`<div class="compact-row"><strong>${E(c.name)}</strong><span>${E(c.address)}</span></div>`).join('')}${cases.map(c=>`<div class="compact-row"><span>${E(c.title)}</span>${badge('',c.stage||'未设阶段')}</div>`).join('')}</div></details>`:''}
    ${scope==='case'&&current?`<div class="small muted">${E(data.cases.find(c=>c.case_id===current.id)?.stage||'未设阶段')}</div>`:''}</div></div>`;
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
  tab: 'runtime'
};
async function showSoftwareUpdate() {
  const status = $('#update-status'), actions = $('#update-actions');
  const paint = (r, checked=false) => {
    actions.replaceChildren();
    const lines = ['当前版本：'+r.current];
    if (r.last) lines.push(r.last.error ? '上次更新失败：'+r.last.error : '已更新至 '+r.last.version);
    if (r.transaction === 'rolled-back') lines.push('原版本与工作空间已恢复。');
    if (r.offer) lines.push('可用版本：'+r.offer.version, r.offer.notes);
    else if (checked) lines.push('暂无适用于此安装的已发布更新。');
    if (!r.enabled) lines.push('请在 Windows 正式工作空间中检查更新。');
    status.textContent = lines.filter(Boolean).join('\n');
    const button = (label, operation) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.disabled = !r.enabled;
      b.onclick = async () => {
        if (operation === 'apply' && !window.confirm('请先关闭 WorkBuddy。工作台将暂停、备份两个工作空间，并重启更新。继续吗？')) return;
        for (const el of actions.children) el.disabled = true;
        try {
          const next = await api('/software-update/'+operation,'POST',{confirmed:operation==='apply'});
          if (operation !== 'apply') { paint(next,true); return; }
          actions.replaceChildren();
          status.textContent = '正在备份并重启。请保持此页面打开。';
          const deadline = Date.now()+15*60*1000;
          const timer = setInterval(async () => {
            if (Date.now()>deadline) {
              clearInterval(timer);
              status.textContent = '尚未重新连接。请从原 Start.cmd 查看更新或恢复状态，不要覆盖工作空间。';
              return;
            }
            try {
              const s = await api('/software-update');
              if (s.last) { clearInterval(timer); sessionStorage.setItem('workthread-update-return','1'); location.reload(); }
            } catch (_) { /* detached updater owns the install lock */ }
          }, 2000);
        } catch (err) {
          paint(r);
          status.textContent += '\n'+err.message;
        }
      };
      actions.append(b);
    };
    button('检查更新','check');
    if (r.offer && !r.ready) button('下载并检查','download');
    if (r.ready) button('备份并重启更新','apply');
  };
  paint(await api('/software-update'));
}

const runStates = {
  pending: '待执行',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  partial: '部分完成',
  superseded: '已过期'
};

function settingsView() {
  $('#workspace-content').innerHTML = `${tabBar([['runtime','运行与 AI'],['accounts','邮箱'],['backup','备份与恢复'],['update','软件更新']],settingsState.tab,'settings-tab','设置分类')}
    <section data-settings-panel="runtime" ${settingsState.tab==='runtime'?'':'hidden'}>
      <div class="status-strip"><span>${badge('',data.health.ok?'运行正常':'需要检查')}</span><span>AI：${data.health.ai_schedule.enabled?'已启用':'未启用'}</span><button id="health-check">健康检查</button><button id="consume-results">读取 AI 结果</button>${data.accounts.some(a=>a.account_id==='demo')?'<button id="demo-ai">模拟分析</button>':''}</div>
      <div class="split">${card('执行计划',`<form id="schedule-form" class="card-body form-grid compact-form"><label>工作时区<input name="timezone" value="${E(data.timezone)}"></label><label>每日分析时间<input name="time" type="time" value="${E(data.health.ai_schedule.time)}"></label><label>邮件同步间隔（分钟）<input name="interval" type="number" min="1" max="1440" value="${E(data.imap_interval_minutes)}"></label><div class="form-note">每日一次</div><button type="submit" class="primary">保存计划</button></form>`)}
      ${card('最近任务',`<div class="table-scroll"><table><thead><tr><th>时间</th><th>状态</th></tr></thead><tbody>${data.jobs.slice(0,6).map(j=>`<tr><td>${E(date(j.created_at))}</td><td>${badge('',runStates[j.state]||j.state)}</td></tr>`).join('')||'<tr><td colspan="2">暂无任务</td></tr>'}</tbody></table></div>`)}</div>
      <details class="card related-objects"><summary>运行信息与同步记录</summary><div class="card-body"><p class="prewrap">${E(data.health.workspace)}</p><div class="small muted">Windows / 真实邮箱 / WorkBuddy 无人值守：待验收</div>${data.sync_runs.slice(-5).map(r=>`<div class="compact-row"><time>${E(date(r.started_at))}</time>${badge('',runStates[r.state]||r.state)}</div>`).join('')||'<p>暂无同步记录</p>'}</div></details>
    </section>
    <section data-settings-panel="accounts" ${settingsState.tab==='accounts'?'':'hidden'}>
      ${card('邮箱',data.accounts.map(a=>`<div class="account-row"><div><strong>${E(a.label)}</strong><p>${E(a.username)} · ${a.enabled?'同步已启用':'同步已暂停'}</p></div><div class="button-row"><button data-sync="${E(a.account_id)}">同步</button>${a.account_id!=='demo'?`<button data-account-toggle="${E(a.account_id)}">${a.enabled?'暂停':'启用'}同步</button>`:''}</div></div>`).join('')||'<div class="empty">暂无邮箱</div>')}
      <details class="card related-objects" id="account-editor"><summary>添加邮箱</summary>
      <form id="account-form" class="card-body form-grid compact-form"><label>名称<input name="label" required></label><label>账号<input name="username" required autocomplete="off"></label><label>IMAP 主机<input name="host" placeholder="imap.example.org" required></label><label>TLS 端口<input name="port" type="number" value="993"></label><label class="wide">授权码<input name="password" type="password" autocomplete="new-password"></label>
      <details class="wide advanced-fields"><summary>文件夹设置</summary><div class="form-grid"><label>收件箱<input name="inbox_folder" placeholder="INBOX"></label><label>已发送<input name="sent_folder" placeholder="自动识别"></label><label class="wide">其他文件夹<input name="extra_folders" placeholder="逗号分隔"></label></div></details>
      <button type="submit" class="primary">保存配置</button><span class="form-note">保存后同步默认暂停；授权码存入系统凭证库</span></form></details>
    </section>
    <section data-settings-panel="update" ${settingsState.tab==='update'?'':'hidden'}>
      ${card('软件更新','<div class="card-body stack"><div id="update-status" class="prewrap" role="status"></div><div id="update-actions" class="button-row"></div></div>')}
    </section>
    <section data-settings-panel="backup" ${settingsState.tab==='backup'?'':'hidden'}><div class="split">
      ${card('备份',`<div class="card-body stack compact-form"><div class="button-row"><button data-backup="todos">备份 To Do</button><button data-backup="full" class="primary">完整备份</button></div><span class="form-note">普通 ZIP，无需密码，不含邮箱授权码</span></div>`)}
      ${card('恢复',`<form id="restore-form" class="card-body stack compact-form"><label>备份文件<input type="file" name="file" accept=".zip" required></label><button type="submit">校验备份</button><div id="restore-preview" class="small prewrap"></div><button type="button" id="apply-restore" class="primary" hidden>确认恢复</button></form>`)}</div>
    </section>`;
  bindTabs('[data-settings-tab]', key => {
    settingsState.tab = key;
    if (key === 'update') attempt(showSoftwareUpdate)();
    markTabs('[data-settings-tab]', key);
    document.querySelectorAll('[data-settings-panel]').forEach(panel => panel.hidden = panel.dataset
      .settingsPanel !== key)
  });
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
    if (el.dataset.sync !== 'demo' && !confirm('现在连接此邮箱并同步？')) return;
    await api('/accounts/' + el.dataset.sync + '/sync', 'POST', {});
    toast('同步已完成');
    await refresh()
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
attempt(refresh)();
setInterval(() => {
  if (!$('#detail-dialog').open && view === 'overview') attempt(refresh)()
}, 15000);
