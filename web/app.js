const $ = (id) => document.getElementById(id);

const state = {
  animations: [],
  selectedAnimations: new Set(),
  animationPage: 1,
  animationPageSize: 30,
  jsonFiles: [],
  selectedJson: new Set(),
  jsonPage: 1,
  jsonPageSize: 30,
  currentTaskId: null,
  taskTimer: null,
  smsCooldown: 0,
  lastTask: null,
  auth: { hasToken: false, tokenPreview: '' },
};

const terminalStatuses = ['success', 'failed', 'cancelled'];

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function setVisible(id, visible) {
  const el = $(id);
  if (el) el.classList.toggle('hidden', !visible);
}

function showView(view) {
  setVisible('appLoading', false);
  setVisible('loginView', view === 'login');
  setVisible('homeView', view === 'home');
}

function showAlert(targetId, message, type = 'error') {
  const el = $(targetId);
  if (!el) return;
  if (!message) {
    el.className = 'alert hidden';
    el.textContent = '';
    return;
  }
  el.className = `alert ${type}`;
  el.textContent = message;
}

function toast(message, type = 'info', ms = 3800) {
  const host = $('toastHost');
  const item = document.createElement('div');
  item.className = `toast ${type}`;
  item.innerHTML = `<span>${escapeHtml(message)}</span><button type="button" aria-label="关闭">×</button>`;
  item.querySelector('button').onclick = () => item.remove();
  host.appendChild(item);
  setTimeout(() => item.remove(), ms);
}

function getErrorMessage(error) {
  if (!navigator.onLine) return '网络不可用，请检查本机网络或代理设置。';
  return error?.message || '操作失败，请稍后重试。';
}

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
  } catch (error) {
    throw new Error('无法连接本地 GUI 服务，请确认 python gui_server.py 正在运行。');
  }
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(x => x.msg || JSON.stringify(x)).join('；') : data.detail;
    const message = detail || data.message || `请求失败：HTTP ${res.status}`;
    if (res.status === 401) {
      state.auth = { hasToken: false, tokenPreview: '' };
      updateAuthChip();
      showView('login');
      showAlert('loginAlert', '登录状态已失效，请重新登录。');
    }
    throw new Error(message);
  }
  return data;
}

async function withAction(buttonId, label, fn) {
  const btn = $(buttonId);
  const oldText = btn?.textContent;
  if (btn) { btn.disabled = true; btn.textContent = label || '处理中...'; }
  try {
    return await fn();
  } catch (error) {
    const message = getErrorMessage(error);
    toast(message, 'error', 5200);
    showAlert('globalAlert', message);
    throw error;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = oldText; }
  }
}

function checkedValues(selector) {
  return Array.from(document.querySelectorAll(selector)).filter(x => x.checked).map(x => x.value);
}

function selectedCount(selector) { return checkedValues(selector).length; }

function updateAuthChip() {
  const el = $('tokenStatus');
  if (!el) return;
  if (state.auth.hasToken) {
    el.textContent = `已登录 · ${state.auth.tokenPreview || 'Token'}`;
    el.className = 'status-chip ok';
  } else {
    el.textContent = '未登录';
    el.className = 'status-chip warn';
  }
}

async function refreshAuthStatus() {
  const data = await api('/api/auth/status');
  state.auth = { hasToken: Boolean(data.has_token), tokenPreview: data.token_preview || '' };
  updateAuthChip();
  return state.auth;
}

async function initApp() {
  try {
    const auth = await refreshAuthStatus();
    if (auth.hasToken) {
      showView('home');
      await bootstrapHome();
    } else {
      showView('login');
    }
  } catch (error) {
    showView('login');
    showAlert('loginAlert', getErrorMessage(error));
  }
}

function switchLoginTab(tab) {
  const sms = tab === 'sms';
  $('smsTab').classList.toggle('active', sms);
  $('tokenTab').classList.toggle('active', !sms);
  setVisible('smsPanel', sms);
  setVisible('tokenPanel', !sms);
  showAlert('loginAlert', '');
}

function startSmsCooldown(seconds = 60) {
  state.smsCooldown = seconds;
  const btn = $('sendSmsBtn');
  const tick = () => {
    if (state.smsCooldown <= 0) {
      btn.disabled = false;
      btn.textContent = '发送验证码';
      return;
    }
    btn.disabled = true;
    btn.textContent = `${state.smsCooldown}s 后重发`;
    state.smsCooldown -= 1;
    setTimeout(tick, 1000);
  };
  tick();
}

async function sendSms() {
  showAlert('loginAlert', '');
  const mobile = $('mobile').value.trim();
  if (!mobile) return showAlert('loginAlert', '请输入手机号。');
  if (!/^\d{5,}$/.test(mobile)) return showAlert('loginAlert', '手机号格式不正确，请检查后重试。');
  const btn = $('sendSmsBtn');
  const oldText = btn.textContent;
  btn.disabled = true;
  btn.textContent = '发送中...';
  try {
    const data = await api('/api/auth/sms', { method: 'POST', body: JSON.stringify({ mobile }) });
    if (!data.success) throw new Error(data.message || '验证码发送失败。');
    toast('验证码已发送，请查看短信。', 'success');
    showAlert('loginAlert', '验证码已发送，请在有效期内完成登录。', 'success');
    startSmsCooldown(60);
  } catch (error) {
    btn.disabled = false;
    btn.textContent = oldText;
    const message = getErrorMessage(error);
    toast(message, 'error', 5200);
    showAlert('loginAlert', message);
    throw error;
  }
}

async function afterLoginSuccess(message = '登录成功') {
  toast(message, 'success');
  showAlert('loginAlert', '');
  await refreshAuthStatus();
  showView('home');
  await bootstrapHome();
}

async function login() {
  showAlert('loginAlert', '');
  const mobile = $('mobile').value.trim();
  const verify_code = $('verifyCode').value.trim();
  if (!mobile || !verify_code) return showAlert('loginAlert', '请输入手机号和短信验证码。');
  await withAction('loginBtn', '登录中...', async () => {
    await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ mobile, verify_code }) });
    await afterLoginSuccess('登录成功，已进入主页。');
  });
}

async function saveManualToken() {
  showAlert('loginAlert', '');
  const token = $('manualToken').value.trim();
  if (!token) return showAlert('loginAlert', '请先粘贴 Token。');
  await withAction('saveTokenBtn', '保存中...', async () => {
    await api('/api/auth/token', { method: 'POST', body: JSON.stringify({ token }) });
    $('manualToken').value = '';
    await afterLoginSuccess('Token 已保存。');
  });
}

async function logout() {
  const ok = await confirmDialog('退出登录', '将清除本地 token，需要重新登录后才能访问 ukids API。是否继续？', '退出');
  if (!ok) return;
  await withAction('logoutBtn', '退出中...', async () => {
    await api('/api/auth/logout', { method: 'POST' });
    state.auth = { hasToken: false, tokenPreview: '' };
    updateAuthChip();
    showView('login');
    toast('已退出登录。', 'success');
  });
}

async function bootstrapHome() {
  showAlert('globalAlert', '');
  showPanel('sectionOverview');
  restoreAnimationState();
  await Promise.allSettled([refreshJsonFiles(), refreshSeasons(), checkFfmpeg(), restoreLatestTask(), refreshTaskHistory()]);
}


async function restoreLatestTask() {
  try {
    const data = await api('/api/tasks');
    const latest = (data.items || [])[0];
    if (!latest) return;
    state.currentTaskId = latest.task_id;
    renderTask(latest);
    if (!terminalStatuses.includes(latest.status)) watchTask(latest.task_id);
  } catch {}
}


async function refreshTaskHistory() {
  const data = await api('/api/tasks');
  const items = data.items || [];
  const body = $('taskHistoryBody');
  body.innerHTML = items.length ? items.map(task => `
    <div class="task-history-item ${task.task_id === state.currentTaskId ? 'active' : ''}">
      <button class="task-open" type="button" data-task-id="${escapeHtml(task.task_id)}">
        <strong>${escapeHtml(task.task_type || 'task')} · ${escapeHtml(statusText(task.status))}</strong>
        <span>${escapeHtml(task.message || task.task_id)}</span>
        <small>${escapeHtml(task.updated_at || task.created_at || '')}</small>
      </button>
      <button class="md-button text danger task-delete" type="button" data-task-id="${escapeHtml(task.task_id)}">删除</button>
    </div>`).join('') : '<div class="empty-mini">暂无历史任务</div>';

  body.querySelectorAll('.task-open').forEach(btn => {
    btn.onclick = async () => {
      const task = await api(`/api/tasks/${btn.dataset.taskId}`);
      state.currentTaskId = task.task_id;
      renderTask(task);
    };
  });
  body.querySelectorAll('.task-delete').forEach(btn => {
    btn.onclick = async () => deleteTask(btn.dataset.taskId);
  });
}

async function deleteTask(taskId) {
  const ok = await confirmDialog('删除任务', '删除后该任务记录、日志和任务产物会一并移除，是否继续？', '删除');
  if (!ok) return;
  await api(`/api/tasks/${taskId}`, { method: 'DELETE' });
  if (state.currentTaskId === taskId) {
    state.currentTaskId = null;
    state.lastTask = null;
    renderTask({ status: '', progress: 0, done: 0, total: 0, success: 0, failed: 0, current: '', logs: [] });
  }
  await refreshTaskHistory();
  toast('任务已删除。', 'success');
}

async function clearAllTasks() {
  const ok = await confirmDialog('清空所有任务', '将删除所有历史任务、日志记录和可识别的任务产物。正在运行的任务也会从列表移除，是否继续？', '清空');
  if (!ok) return;
  await api('/api/tasks', { method: 'DELETE' });
  state.currentTaskId = null;
  state.lastTask = null;
  renderTask({ status: '', progress: 0, done: 0, total: 0, success: 0, failed: 0, current: '', logs: [] });
  await refreshTaskHistory();
  toast('所有任务已清空。', 'success');
}

async function loadAgeTypes() {
  await withAction('loadAgeBtn', '加载中...', async () => {
    const data = await api('/api/age-types');
    const items = data.items || [];
    const select = $('ageSelect');
    select.innerHTML = items.length
      ? items.map(item => `<option value="${escapeHtml(item.type)}">${escapeHtml(item.name)}</option>`).join('')
      : '<option value="">暂无年龄段</option>';
    select.disabled = items.length === 0 || $('modeSelect').value !== 'age';
    toast(`已加载 ${items.length} 个年龄段。`, 'success');
  });
}

function filteredAnimations() {
  const filter = $('animationFilter').value.trim().toLowerCase();
  return state.animations
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => !filter || String(item.name || '').toLowerCase().includes(filter));
}

function updateAnimationSelectionInfo(totalFiltered, pageItems, pageCount) {
  $('animationCount').textContent = state.animations.length;
  $('animationSelectedInfo').textContent = `已选 ${state.selectedAnimations.size}`;
  $('animationPageInfo').textContent = `${totalFiltered} 条`;
  $('animationPaginationText').textContent = `第 ${pageCount ? state.animationPage : 0} / ${pageCount} 页`;
  $('animationPrevBtn').disabled = state.animationPage <= 1;
  $('animationNextBtn').disabled = state.animationPage >= pageCount;
}

function renderAnimations() {
  const visible = filteredAnimations();
  const pageCount = Math.ceil(visible.length / state.animationPageSize);
  if (state.animationPage > pageCount) state.animationPage = Math.max(pageCount, 1);
  const start = (state.animationPage - 1) * state.animationPageSize;
  const pageItems = visible.slice(start, start + state.animationPageSize);

  setVisible('animationsEmpty', visible.length === 0);
  $('animationsBody').innerHTML = pageItems.map(({ item, index }) => `
    <label class="list-item compact-item">
      <input class="anim-check" type="checkbox" value="${index}" ${state.selectedAnimations.has(index) ? 'checked' : ''}>
      <div>
        <div class="item-title">${escapeHtml(item.name || '未知动画')}</div>
        <div class="item-subtitle">ipId: ${escapeHtml(item.ipId || '-')}</div>
      </div>
      <div class="item-meta">
        <span class="pill">${escapeHtml(item.lang === 2 ? '英文' : item.lang === 0 ? '中文' : `lang ${item.lang ?? '-'}`)}</span>
        <span class="pill">#${index + 1}</span>
      </div>
    </label>`).join('');

  document.querySelectorAll('.anim-check').forEach(input => {
    input.onchange = () => {
      const idx = Number(input.value);
      if (input.checked) state.selectedAnimations.add(idx);
      else state.selectedAnimations.delete(idx);
      updateAnimationSelectionInfo(visible.length, pageItems, pageCount);
    };
  });
  updateAnimationSelectionInfo(visible.length, pageItems, pageCount);
}

async function loadAnimations() {
  await withAction('loadAnimationsBtn', '加载中...', async () => {
    const mode = $('modeSelect').value;
    const lang = $('langSelect').value;
    let url = `/api/animations?mode=${mode}&lang=${lang}`;
    if (mode === 'age') {
      const ageType = $('ageSelect').value;
      if (!ageType) throw new Error('请先加载并选择年龄段。');
      url += `&age_type=${encodeURIComponent(ageType)}`;
    }
    const data = await api(url);
    state.animations = data.items || [];
    state.selectedAnimations.clear();
    state.animationPage = 1;
    persistAnimationState();
    renderAnimations();
    toast(`已加载 ${state.animations.length} 个动画。`, 'success');
  });
}

function selectedAnimations() {
  return Array.from(state.selectedAnimations).map(idx => state.animations[Number(idx)]).filter(Boolean);
}

async function startMetadataTask() {
  const selected = selectedAnimations();
  if (!selected.length) return showAlert('globalAlert', '请先在资源列表中选择至少一个动画。');
  const ok = await confirmDialog('开始采集元数据', `将采集 ${selected.length} 个动画，过程可能耗时较久。是否继续？`, '开始采集');
  if (!ok) return;
  await withAction('startMetadataBtn', '创建任务...', async () => {
    const mode = $('modeSelect').value;
    const ageName = mode === 'age' ? $('ageSelect').selectedOptions[0]?.textContent : null;
    const data = await api('/api/tasks/metadata', {
      method: 'POST',
      body: JSON.stringify({ mode, lang: Number($('langSelect').value), age_name: ageName, animations: selected }),
    });
    watchTask(data.task_id);
    scrollToSection('sectionTask');
  });
}

function renderJsonFiles() {
  const items = state.jsonFiles;
  const pageCount = Math.ceil(items.length / state.jsonPageSize);
  if (state.jsonPage > pageCount) state.jsonPage = Math.max(pageCount, 1);
  const start = (state.jsonPage - 1) * state.jsonPageSize;
  const pageItems = items.slice(start, start + state.jsonPageSize);

  $('jsonCount').textContent = items.length;
  setVisible('jsonEmpty', items.length === 0);
  $('jsonPageInfo').textContent = `${items.length} 条`;
  $('jsonSelectedInfo').textContent = `已选 ${state.selectedJson.size}`;
  $('jsonPaginationText').textContent = `第 ${pageCount ? state.jsonPage : 0} / ${pageCount} 页`;
  $('jsonPrevBtn').disabled = state.jsonPage <= 1;
  $('jsonNextBtn').disabled = state.jsonPage >= pageCount;

  $('jsonBody').innerHTML = pageItems.map(item => `
    <label class="list-item compact-item">
      <input class="json-check" type="checkbox" value="${escapeHtml(item.path)}" ${state.selectedJson.has(item.path) ? 'checked' : ''}>
      <div>
        <div class="item-title">${escapeHtml(item.name)}</div>
        <div class="item-subtitle">${escapeHtml(item.path)}</div>
      </div>
      <div class="item-meta">
        <span class="pill">${escapeHtml(item.source === 'all' ? '全部动画' : '分龄动画')}</span>
        <span class="pill">${escapeHtml(item.episodes)} 集</span>
      </div>
    </label>`).join('');

  document.querySelectorAll('.json-check').forEach(input => {
    input.onchange = () => {
      if (input.checked) state.selectedJson.add(input.value);
      else state.selectedJson.delete(input.value);
      $('jsonSelectedInfo').textContent = `已选 ${state.selectedJson.size}`;
    };
  });
}

async function refreshJsonFiles() {
  const source = $('jsonSource').value;
  const data = await api(`/api/files/json?source=${encodeURIComponent(source)}`);
  state.jsonFiles = data.items || [];
  state.selectedJson.clear();
  state.jsonPage = 1;
  renderJsonFiles();
}

async function deleteSelectedJsonFiles() {
  const paths = Array.from(state.selectedJson);
  if (!paths.length) return showAlert('globalAlert', '请先选择要删除的 JSON 文件。');
  const ok = await confirmDialog('删除本地文件', `将删除 ${paths.length} 个本地 JSON 文件及其同名下载目录。此操作不可恢复，是否继续？`, '删除');
  if (!ok) return;
  await withAction('deleteJsonBtn', '删除中...', async () => {
    const data = await api('/api/files/delete', { method: 'POST', body: JSON.stringify({ paths }) });
    state.selectedJson.clear();
    await refreshJsonFiles();
    if (data.failed && data.failed.length) {
      toast(`已删除 ${data.deleted.length} 个，失败 ${data.failed.length} 个。`, 'error', 5200);
      showAlert('globalAlert', `部分文件删除失败：${data.failed.map(x => x.path).join('，')}`);
    } else {
      toast(`已删除 ${data.deleted.length} 个文件。`, 'success');
      showAlert('globalAlert', '本地 JSON 文件已删除。', 'success');
    }
  });
}

async function startDownloadTask() {
  const json_paths = Array.from(state.selectedJson);
  if (!json_paths.length) return showAlert('globalAlert', '请先选择要下载的 JSON 文件。');
  const ok = await confirmDialog('开始下载资源', `将下载 ${json_paths.length} 个 JSON 文件对应的视频片段。是否继续？`, '开始下载');
  if (!ok) return;
  await withAction('startDownloadBtn', '创建任务...', async () => {
    const data = await api('/api/tasks/download', { method: 'POST', body: JSON.stringify({ json_paths }) });
    watchTask(data.task_id);
    scrollToSection('sectionTask');
  });
}

async function checkFfmpeg() {
  const data = await api('/api/system/ffmpeg');
  const el = $('ffmpegStatus');
  const text = $('ffmpegText');
  if (data.available) {
    el.textContent = 'ffmpeg 可用';
    el.className = 'merge-status-text ok';
    text.textContent = '可用';
  } else {
    el.textContent = 'ffmpeg 不可用';
    el.className = 'merge-status-text warn';
    text.textContent = '缺失';
  }
}

async function refreshSeasons() {
  const source = $('seasonSource').value;
  const data = await api(`/api/files/seasons?source=${encodeURIComponent(source)}`);
  const items = data.items || [];
  $('seasonCount').textContent = items.length;
  setVisible('seasonsEmpty', items.length === 0);
  $('seasonsBody').innerHTML = items.map(item => `
    <label class="list-item">
      <input class="season-check" type="checkbox" value="${escapeHtml(item.path)}">
      <div>
        <div class="item-title">${escapeHtml(item.name)}</div>
        <div class="item-subtitle">${escapeHtml(item.path)}</div>
      </div>
      <div class="item-meta">
        <span class="pill">${escapeHtml(item.source)}</span>
        <span class="pill">${escapeHtml(item.episodes)} 集</span>
        <span class="pill">MP4 ${escapeHtml(item.mp4_count)}</span>
        <span class="pill">无字幕 ${escapeHtml(item.mp4_nosub_count)}</span>
      </div>
    </label>`).join('');
}

async function startMergeTask() {
  const season_dirs = checkedValues('.season-check');
  if (!season_dirs.length) return showAlert('globalAlert', '请先选择要合并的季目录。');
  const ok = await confirmDialog('开始合并 MP4', `将合并 ${season_dirs.length} 个季目录。合并过程会占用较多 CPU，是否继续？`, '开始合并');
  if (!ok) return;
  await withAction('startMergeBtn', '创建任务...', async () => {
    const embed_subtitle = $('embedSubtitle').checked;
    const data = await api('/api/tasks/merge', { method: 'POST', body: JSON.stringify({ season_dirs, embed_subtitle }) });
    watchTask(data.task_id);
    scrollToSection('sectionTask');
  });
}

function renderTask(task) {
  state.lastTask = task;
  const progress = Math.max(0, Math.min(100, Number(task.progress || 0)));
  $('progressBar').style.width = `${progress}%`;
  $('taskStatus').textContent = task.message ? `${statusText(task.status)} · ${task.message}` : statusText(task.status);
  $('taskProgress').textContent = `${progress.toFixed(1)}%`;
  $('taskCurrent').textContent = task.current || '-';
  $('taskDone').textContent = `${task.done || 0} / ${task.total || 0}`;
  $('taskSuccess').textContent = task.success || 0;
  $('taskFailed').textContent = task.failed || 0;
  $('taskLogs').textContent = (task.logs || []).join('\n') || '暂无日志';
  $('taskLogs').scrollTop = $('taskLogs').scrollHeight;
  $('cancelTaskBtn').disabled = !task.task_id || terminalStatuses.includes(task.status);
}

function statusText(status) {
  return ({ pending: '等待中', running: '运行中', success: '已完成', failed: '失败', cancelled: '已取消' })[status] || (status || '无任务');
}

function watchTask(taskId) {
  state.currentTaskId = taskId;
  $('cancelTaskBtn').disabled = false;
  if (state.taskTimer) clearInterval(state.taskTimer);
  toast(`任务已创建：${taskId}`, 'success');
  showAlert('globalAlert', '任务已创建，可在任务区查看进度。', 'info');
  refreshTaskHistory().catch(() => {});

  const tick = async () => {
    try {
      const task = await api(`/api/tasks/${taskId}`);
      renderTask(task);
      if (terminalStatuses.includes(task.status)) {
        clearInterval(state.taskTimer);
        state.taskTimer = null;
        $('cancelTaskBtn').disabled = true;
        const type = task.status === 'success' ? 'success' : task.status === 'failed' ? 'error' : 'info';
        toast(`任务${statusText(task.status)}：${task.message || task.task_id}`, type);
        await Promise.allSettled([refreshJsonFiles(), refreshSeasons(), refreshTaskHistory()]);
      }
    } catch (error) {
      clearInterval(state.taskTimer);
      state.taskTimer = null;
      toast(getErrorMessage(error), 'error');
    }
  };
  tick();
  state.taskTimer = setInterval(tick, 1000);
}

async function cancelTask() {
  if (!state.currentTaskId) return;
  const ok = await confirmDialog('取消任务', '取消请求会在当前步骤结束后生效，是否继续？', '取消任务');
  if (!ok) return;
  await api(`/api/tasks/${state.currentTaskId}/cancel`, { method: 'POST' });
  toast('已请求取消任务。', 'info');
}

function selectAll(selector, checked = true) {
  document.querySelectorAll(selector).forEach(x => {
    x.checked = checked;
    if (selector === '.anim-check') {
      const idx = Number(x.value);
      if (checked) state.selectedAnimations.add(idx);
      else state.selectedAnimations.delete(idx);
    }
    if (selector === '.json-check') {
      if (checked) state.selectedJson.add(x.value);
      else state.selectedJson.delete(x.value);
    }
  });
  if (selector === '.anim-check') renderAnimations();
  if (selector === '.json-check') renderJsonFiles();
}

function persistAnimationState() {
  try {
    localStorage.setItem('ukids.animations', JSON.stringify({
      items: state.animations,
      savedAt: Date.now(),
    }));
  } catch {}
}

function restoreAnimationState() {
  try {
    const raw = localStorage.getItem('ukids.animations');
    if (!raw) return;
    const data = JSON.parse(raw);
    if (Array.isArray(data.items)) {
      state.animations = data.items;
      state.animationPage = 1;
      renderAnimations();
    }
  } catch {}
}

async function clearTaskLogs() {
  if (!state.currentTaskId) {
    $('taskLogs').textContent = '暂无日志';
    return;
  }
  await api(`/api/tasks/${state.currentTaskId}/logs/clear`, { method: 'POST' });
  if (state.lastTask) state.lastTask.logs = [];
  $('taskLogs').textContent = '暂无日志';
  toast('任务日志已清空。', 'success');
}

function showPanel(id) {
  document.querySelectorAll('.workspace-section').forEach(section => {
    const active = section.id === id;
    section.classList.toggle('active-section', active);
    section.classList.toggle('hidden-section', !active);
  });
  document.querySelectorAll('.nav-item').forEach(x => x.classList.toggle('active', x.dataset.target === id));
}

function scrollToSection(id) {
  showPanel(id);
  $(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function confirmDialog(title, message, okText = '确认') {
  const dialog = $('confirmDialog');
  $('confirmTitle').textContent = title;
  $('confirmMessage').textContent = message;
  $('confirmOkBtn').textContent = okText;
  if (!dialog.showModal) return Promise.resolve(window.confirm(message));
  dialog.showModal();
  return new Promise(resolve => {
    dialog.onclose = () => resolve(dialog.returnValue === 'ok');
  });
}

function bind() {
  $('smsTab').onclick = () => switchLoginTab('sms');
  $('tokenTab').onclick = () => switchLoginTab('token');
  $('sendSmsBtn').onclick = () => sendSms().catch(() => {});
  $('loginBtn').onclick = () => login().catch(() => {});
  $('saveTokenBtn').onclick = () => saveManualToken().catch(() => {});
  $('logoutBtn').onclick = () => logout().catch(() => {});

  $('loadAgeBtn').onclick = () => loadAgeTypes().catch(() => {});
  $('loadAnimationsBtn').onclick = () => loadAnimations().catch(() => {});
  $('animationFilter').oninput = () => { state.animationPage = 1; renderAnimations(); };
  $('startMetadataBtn').onclick = () => startMetadataTask().catch(() => {});
  $('refreshJsonBtn').onclick = () => withAction('refreshJsonBtn', '刷新中...', refreshJsonFiles).catch(() => {});
  $('startDownloadBtn').onclick = () => startDownloadTask().catch(() => {});
  $('checkFfmpegBtn').onclick = () => withAction('checkFfmpegBtn', '检查中...', checkFfmpeg).catch(() => {});
  $('refreshSeasonsBtn').onclick = () => withAction('refreshSeasonsBtn', '刷新中...', refreshSeasons).catch(() => {});
  $('startMergeBtn').onclick = () => startMergeTask().catch(() => {});
  $('cancelTaskBtn').onclick = () => cancelTask().catch(error => toast(getErrorMessage(error), 'error'));

  $('modeSelect').onchange = async () => {
    const ageMode = $('modeSelect').value === 'age';
    $('ageSelect').disabled = !ageMode;
    if (ageMode && (!$('ageSelect').value || $('ageSelect').options.length <= 1)) {
      await loadAgeTypes().catch(() => {});
    }
  };
  $('jsonSource').onchange = () => refreshJsonFiles().catch(() => {});
  $('seasonSource').onchange = () => refreshSeasons().catch(() => {});
  $('selectAllAnimationsBtn').onclick = () => selectAll('.anim-check', true);
  $('clearAnimationsBtn').onclick = () => { state.selectedAnimations.clear(); renderAnimations(); };
  $('selectAllJsonBtn').onclick = () => selectAll('.json-check', true);
  $('clearJsonBtn').onclick = () => { state.selectedJson.clear(); renderJsonFiles(); };
  $('deleteJsonBtn').onclick = () => deleteSelectedJsonFiles().catch(() => {});
  $('selectAllSeasonsBtn').onclick = () => selectAll('.season-check', true);
  $('animationPrevBtn').onclick = () => { state.animationPage = Math.max(1, state.animationPage - 1); renderAnimations(); };
  $('animationNextBtn').onclick = () => { state.animationPage += 1; renderAnimations(); };
  $('jsonPrevBtn').onclick = () => { state.jsonPage = Math.max(1, state.jsonPage - 1); renderJsonFiles(); };
  $('jsonNextBtn').onclick = () => { state.jsonPage += 1; renderJsonFiles(); };
  $('clearLogsBtn').onclick = (event) => { event.preventDefault(); clearTaskLogs().catch(error => toast(getErrorMessage(error), 'error')); };
  $('refreshTasksBtn').onclick = () => refreshTaskHistory().catch(error => toast(getErrorMessage(error), 'error'));
  $('clearAllTasksBtn').onclick = () => clearAllTasks().catch(error => toast(getErrorMessage(error), 'error'));
  document.querySelectorAll('.nav-item').forEach(btn => btn.onclick = () => scrollToSection(btn.dataset.target));
  document.querySelectorAll('.quick-card').forEach(btn => btn.onclick = () => scrollToSection(btn.dataset.target));
  $('overviewRefreshBtn').onclick = () => withAction('overviewRefreshBtn', '刷新中...', async () => {
    await Promise.all([refreshJsonFiles(), refreshSeasons(), checkFfmpeg()]);
    toast('概览数据已刷新。', 'success');
  }).catch(() => {});
  ['mobile', 'verifyCode'].forEach(id => $(id).addEventListener('keydown', event => { if (event.key === 'Enter') login().catch(() => {}); }));
}

bind();
initApp();
