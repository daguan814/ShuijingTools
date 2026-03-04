const API_PREFIX = '/api';
let currentPassword = '';

let textsState = [];
let filesState = [];
let favoritesState = [];

let hasShownAuthExpired = false;
const rawFetch = window.fetch.bind(window);
window.fetch = async (input, init = {}) => {
  const requestUrl = typeof input === 'string' ? input : (input?.url || '');
  const isApiRequest = requestUrl.startsWith(API_PREFIX) || requestUrl.includes('/api/');
  const isAuthVerify = requestUrl.endsWith('/auth/verify');

  const nextInit = { ...init };
  if (isApiRequest && !isAuthVerify) {
    const headers = new Headers(init?.headers || undefined);
    const token = getCookie('text_system_token');
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    nextInit.headers = headers;
  }

  const response = await rawFetch(input, nextInit);

  if (isApiRequest && !isAuthVerify && response.status === 401) {
    clearAuthState();
    if (!hasShownAuthExpired) {
      hasShownAuthExpired = true;
      alert('登录状态已失效，请重新输入密码');
      window.location.reload();
    }
  }
  return response;
};

window.addEventListener('DOMContentLoaded', () => {
  checkLoginStatus();
  document.addEventListener('keydown', (event) => {
    if (event.key >= '1' && event.key <= '9') addNumber(parseInt(event.key, 10));
  });
});

function checkLoginStatus() {
  const loginOk = getCookie('text_system_login') === 'true';
  const token = getCookie('text_system_token');
  if (loginOk && token) {
    showMainContent();
    return;
  }
  clearAuthState();
}

function addNumber(number) {
  currentPassword += number;
  updatePasswordDisplay();
  if (currentPassword.length === 3) checkPassword();
  if (currentPassword.length > 3) {
    currentPassword = currentPassword.slice(0, 3);
    updatePasswordDisplay();
  }
}

async function checkPassword() {
  const passcode = currentPassword;
  try {
    const res = await fetch(`${API_PREFIX}/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passcode }),
    });
    if (res.ok) {
      const data = await res.json();
      if (!data?.token) throw new Error('missing token');
      setCookie('text_system_token', data.token, 7);
      setCookie('text_system_login', 'true', 7);
      showMainContent();
      return;
    }
    if (res.status === 403) {
      alert('当前IP已被封禁7天');
      currentPassword = '';
      updatePasswordDisplay();
      return;
    }
  } catch (_) {
    // fallback to unified error below
  }
  alert('密码错误');
  currentPassword = '';
  updatePasswordDisplay();
}

function updatePasswordDisplay() {
  const display = document.getElementById('passwordDisplay');
  if (!display) return;
  display.textContent = currentPassword ? '•'.repeat(currentPassword.length) : '••••';
}

function showMainContent() {
  document.documentElement.classList.add('logged-in');
  document.getElementById('lockScreen')?.remove();
  document.getElementById('mainContent').style.display = 'grid';

  initSidebar();
  initAddTextForm();
  initUploadForm();
  initTrashActions();
  initGlobalActions();
  initDragTargets();

  reloadLibrary();
}

function initSidebar() {
  const nav = document.getElementById('navSlider');
  if (!nav) return;
  nav.querySelectorAll('.nav-btn').forEach((btn) => {
    btn.addEventListener('click', () => openView(btn.dataset.view));
  });
}

function openView(viewId) {
  document.querySelectorAll('.page-view').forEach((v) => v.classList.add('hidden'));
  document.getElementById(viewId)?.classList.remove('hidden');
  document.querySelectorAll('.nav-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.view === viewId);
  });
  if (viewId === 'trash-view') refreshTrash();
}

async function reloadLibrary() {
  await Promise.all([refreshTextList(), refreshFileList(), refreshFavorites()]);
  renderAll();
}

async function refreshTextList() {
  const res = await fetch(`${API_PREFIX}/texts`);
  if (res.ok) textsState = await res.json();
}

async function refreshFileList() {
  const res = await fetch(`${API_PREFIX}/files`);
  if (res.ok) filesState = await res.json();
}

async function refreshFavorites() {
  const res = await fetch(`${API_PREFIX}/favorites`);
  if (res.ok) favoritesState = await res.json();
}

function renderAll() {
  renderTextCards();
  renderFileCards();
  renderFavoriteColumns();
  processTextContent();
  bindDraggableCards();
}

function renderTextCards() {
  const container = document.getElementById('textCards');
  if (!container) return;
  const visibleTexts = textsState.filter((t) => !favoritesState.some((f) => Number(f.id) === Number(t.id)));
  if (!visibleTexts.length) {
    container.innerHTML = '<div class="empty-state"><i class="bi bi-journal-text"></i><h4>还没有保存任何文本</h4></div>';
    return;
  }

  container.innerHTML = visibleTexts.map((t) => {
    const safe = escapeHtml(t.content || '');
    return `
      <div class="data-card" draggable="true" data-type="text" data-id="${t.id}">
        <div class="data-card-top">
          <small class="text-muted"><i class="bi bi-clock"></i> ${escapeHtml(formatDisplayTime(t.created_at))}</small>
        </div>
        <div class="data-card-content text-content">${safe}</div>
        <div class="data-card-actions">
          <button type="button" class="btn btn-outline-secondary btn-sm text-copy-btn" data-content="${safe}"><i class="bi bi-clipboard"></i> 复制</button>
          <button type="button" class="btn btn-danger btn-sm text-delete-btn" data-id="${t.id}"><i class="bi bi-trash"></i> 删除</button>
        </div>
      </div>`;
  }).join('');
}

function renderFileCards() {
  const container = document.getElementById('fileCards');
  if (!container) return;
  if (!filesState.length) {
    container.innerHTML = '<div class="empty-state small-empty"><h6>暂无文件</h6></div>';
    return;
  }

  container.innerHTML = filesState.map((f) => `
    <div class="data-card" data-type="file" data-path="${escapeHtml(f.path)}">
      <div class="data-card-top">
        <span class="badge text-bg-secondary">文件</span>
        <small class="text-muted"><i class="bi bi-hdd"></i> ${escapeHtml(f.size)}</small>
      </div>
      <div class="data-card-content">${escapeHtml(f.path)}</div>
      <div class="data-card-actions">
        <button type="button" class="btn btn-outline-primary btn-sm file-download-btn" data-path="${escapeHtml(f.path)}"><i class="bi bi-download"></i> 下载</button>
        <button type="button" class="btn btn-outline-danger btn-sm file-delete-btn" data-path="${escapeHtml(f.path)}"><i class="bi bi-trash"></i> 删除</button>
      </div>
    </div>`).join('');
}

function renderFavoriteColumns() {
  const g1 = document.getElementById('favoriteGroup1');
  if (!g1) return;

  const group1 = favoritesState;
  g1.innerHTML = renderFavoriteGroup(group1);

  if (!group1.length) g1.innerHTML = '<div class="favorite-empty">拖到这里</div>';
}

function renderFavoriteGroup(items) {
  return items.map((item) => {
    const safe = escapeHtml(item.content || '');
    return `
      <div class="favorite-item" draggable="true" data-type="text" data-id="${item.id}">
        <div class="favorite-item-content text-content">${safe}</div>
        <div class="favorite-item-actions">
          <button type="button" class="btn btn-outline-secondary btn-sm text-copy-btn" data-content="${safe}"><i class="bi bi-clipboard"></i> 复制</button>
          <button type="button" class="btn btn-outline-danger btn-sm favorite-delete-btn" data-id="${item.id}"><i class="bi bi-trash"></i> 删除</button>
        </div>
      </div>`;
  }).join('');
}

function initAddTextForm() {
  const form = document.getElementById('addTextForm');
  if (!form) return;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const content = document.getElementById('content').value.trim();
    if (!content) return;

    const data = new FormData();
    data.append('content', content);
    const res = await fetch(`${API_PREFIX}/texts`, { method: 'POST', body: data });
    if (!res.ok) return alert('添加失败');

    document.getElementById('content').value = '';
    await reloadLibrary();
  });
}

function initUploadForm() {
  const form = document.getElementById('uploadForm');
  if (!form) return;

  const filesInput = document.getElementById('uploadFiles');
  const fileHint = document.getElementById('fileHint');
  const fileNames = document.getElementById('fileNames');

  const renderSelected = () => {
    const files = filesInput?.files || [];
    if (fileHint) fileHint.textContent = `已选择 ${files.length} 个文件`;
    if (fileNames) fileNames.innerHTML = Array.from(files).map((f) => `<div>${escapeHtml(f.name)}</div>`).join('');
  };

  filesInput?.addEventListener('change', renderSelected);
  renderSelected();

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!filesInput || !filesInput.files || filesInput.files.length === 0) return;

    const progressWrap = document.getElementById('uploadProgress');
    const progressBar = document.getElementById('uploadProgressBar');
    const progressText = document.getElementById('uploadProgressText');

    const data = new FormData();
    Array.from(filesInput.files).forEach((f) => data.append('files', f));

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_PREFIX}/files/upload`);
    const token = getCookie('text_system_token');
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.upload.onprogress = (evt) => {
      if (!evt.lengthComputable || !progressBar || !progressText) return;
      const percent = Math.round((evt.loaded / evt.total) * 100);
      progressBar.style.width = `${percent}%`;
      progressText.textContent = `${percent}%`;
    };

    if (progressWrap) progressWrap.style.display = 'block';
    xhr.onload = async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        filesInput.value = '';
        renderSelected();
        await reloadLibrary();
      } else {
        alert('上传失败');
      }
    };
    xhr.onloadend = () => {
      if (progressWrap) setTimeout(() => { progressWrap.style.display = 'none'; }, 600);
    };

    xhr.send(data);
  });
}

function initTrashActions() {
  const clearBtn = document.getElementById('clearTrashBtn');
  if (!clearBtn) return;
  clearBtn.addEventListener('click', async () => {
    if (!confirm('确认清空回收站吗？只会从回收站列表移除，数据会保留。')) return;
    const res = await fetch(`${API_PREFIX}/trash/clear`, { method: 'POST' });
    if (!res.ok) return alert('清空失败');
    await Promise.all([refreshTrash(), reloadLibrary()]);
  });
}

function initGlobalActions() {
  document.addEventListener('click', async (event) => {
    const copyBtn = event.target.closest('.text-copy-btn');
    if (copyBtn) return copyText(copyBtn.dataset.content || '');

    const deleteBtn = event.target.closest('.text-delete-btn');
    if (deleteBtn) {
      const textId = deleteBtn.dataset.id;
      const res = await fetch(`${API_PREFIX}/texts/${textId}`, { method: 'DELETE' });
      if (!res.ok) return alert('删除失败');
      await Promise.all([reloadLibrary(), refreshTrash()]);
      return;
    }

    const downloadBtn = event.target.closest('.file-download-btn');
    if (downloadBtn) {
      await downloadFile(downloadBtn.dataset.path || '');
      return;
    }

    const fileDeleteBtn = event.target.closest('.file-delete-btn');
    if (fileDeleteBtn) {
      const data = new FormData();
      data.append('path', fileDeleteBtn.dataset.path);
      const res = await fetch(`${API_PREFIX}/files/delete`, { method: 'POST', body: data });
      if (!res.ok) return alert('删除失败');
      await Promise.all([reloadLibrary(), refreshTrash()]);
      return;
    }

    const deleteFavBtn = event.target.closest('.favorite-delete-btn');
    if (deleteFavBtn) {
      const textId = deleteFavBtn.dataset.id;
      const res = await fetch(`${API_PREFIX}/texts/${textId}`, { method: 'DELETE' });
      if (!res.ok) return alert('删除失败');
      await Promise.all([reloadLibrary(), refreshTrash()]);
      return;
    }

    const actionBtn = event.target.closest('button[data-action]');
    if (!actionBtn) return;

    const action = actionBtn.dataset.action;
    const id = actionBtn.dataset.id;
    if (action === 'restore-text') {
      const res = await fetch(`${API_PREFIX}/trash/restore/text/${id}`, { method: 'POST' });
      if (!res.ok) return alert('还原失败');
      await Promise.all([refreshTrash(), reloadLibrary()]);
    }

    if (action === 'restore-file') {
      const data = new FormData();
      data.append('id', id);
      const res = await fetch(`${API_PREFIX}/trash/restore/file`, { method: 'POST', body: data });
      if (!res.ok) return alert('还原失败');
      await Promise.all([refreshTrash(), reloadLibrary()]);
      return;
    }

    if (action === 'delete-trash-text') {
      const res = await fetch(`${API_PREFIX}/trash/text/${id}`, { method: 'DELETE' });
      if (!res.ok) return alert('删除失败');
      await refreshTrash();
      return;
    }

    if (action === 'delete-trash-file') {
      const res = await fetch(`${API_PREFIX}/trash/file/${id}`, { method: 'DELETE' });
      if (!res.ok) return alert('删除失败');
      await refreshTrash();
    }
  });
}

function initDragTargets() {
  document.querySelectorAll('.favorite-column-body').forEach((zone) => {
    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', async (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const textId = getDraggedTextId(e);
      if (!textId) return;
      await ensureFavorite(textId, 1);
      await reloadLibrary();
    });
  });

  const libraryZone = document.getElementById('libraryDropZone');
  if (libraryZone) {
    libraryZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      libraryZone.classList.add('drag-over');
    });
    libraryZone.addEventListener('dragleave', () => libraryZone.classList.remove('drag-over'));
    libraryZone.addEventListener('drop', async (e) => {
      e.preventDefault();
      libraryZone.classList.remove('drag-over');
      const textId = getDraggedTextId(e);
      if (!textId) return;
      await toggleFavorite(textId, false);
      await reloadLibrary();
    });
  }
}

function bindDraggableCards() {
  document.querySelectorAll('[draggable="true"][data-type="text"]').forEach((card) => {
    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.effectAllowed = 'move';
      const id = card.dataset.id || '';
      e.dataTransfer.setData('text-id', id);
      e.dataTransfer.setData('text/plain', id);
    });
  });
}

function getDraggedTextId(event) {
  const transfer = event.dataTransfer;
  if (!transfer) return '';
  return transfer.getData('text-id') || transfer.getData('text/plain') || '';
}

async function ensureFavorite(textId, group) {
  const existing = favoritesState.find((f) => Number(f.id) === Number(textId));
  if (!existing) {
    const favRes = await fetch(`${API_PREFIX}/texts/${textId}/favorite`, { method: 'POST' });
    if (!favRes.ok) {
      alert('收藏失败');
      return;
    }
  }

  const moveRes = await fetch(`${API_PREFIX}/favorites/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: Number(textId), group: Number(group) }),
  });

  if (!moveRes.ok) alert('拖拽分栏失败');
}

async function toggleFavorite(textId, toFavorite) {
  const existing = favoritesState.find((f) => Number(f.id) === Number(textId));
  if (toFavorite && existing) return;
  if (!toFavorite && !existing) return;

  const res = await fetch(`${API_PREFIX}/texts/${textId}/favorite`, { method: 'POST' });
  if (!res.ok) alert('操作失败');
}

async function refreshTrash() {
  const res = await fetch(`${API_PREFIX}/trash`);
  if (!res.ok) return;
  const data = await res.json();
  renderTrashTexts(data.texts || []);
  renderTrashFiles(data.files || []);
}

function renderTrashTexts(texts) {
  const container = document.getElementById('trashTextList');
  if (!container) return;
  if (!texts.length) return container.innerHTML = '<div class="empty-state"><i class="bi bi-journal-x"></i><h4>没有已删除文本</h4></div>';

  container.innerHTML = `<div class="card-grid three-col">${texts.map((t) => `
    <div class="data-card">
      <div class="data-card-content text-content">${escapeHtml(t.content || '')}</div>
      <div class="data-card-actions">
        <small class="text-muted"><i class="bi bi-clock"></i> ${escapeHtml(formatDisplayTime(t.created_at))}</small>
        <div class="d-flex gap-2">
          <button type="button" class="btn btn-outline-success btn-sm" data-action="restore-text" data-id="${t.id}"><i class="bi bi-arrow-counterclockwise"></i> 还原</button>
          <button type="button" class="btn btn-outline-danger btn-sm" data-action="delete-trash-text" data-id="${t.id}"><i class="bi bi-x-circle"></i> 移出回收站</button>
        </div>
      </div>
    </div>`).join('')}</div>`;
}

function renderTrashFiles(files) {
  const container = document.getElementById('trashFileList');
  if (!container) return;
  if (!files.length) return container.innerHTML = '<div class="empty-state"><i class="bi bi-trash"></i><h4>没有已删除文件</h4></div>';

  container.innerHTML = `<div class="card-grid three-col">${files.map((f) => `
    <div class="data-card">
      <div class="data-card-content">${escapeHtml(f.original_path || '')}</div>
      <div class="data-card-actions">
        <small class="text-muted"><i class="bi bi-hdd"></i> ${escapeHtml(f.size || '')}</small>
        <div class="d-flex gap-2">
          <button type="button" class="btn btn-outline-success btn-sm" data-action="restore-file" data-id="${f.id}"><i class="bi bi-arrow-counterclockwise"></i> 还原</button>
          <button type="button" class="btn btn-outline-danger btn-sm" data-action="delete-trash-file" data-id="${f.id}"><i class="bi bi-x-circle"></i> 移出回收站</button>
        </div>
      </div>
    </div>`).join('')}</div>`;
}

function processTextContent() {
  const reg = /(https?:\/\/[^\s]+)/g;
  document.querySelectorAll('.text-content').forEach((el) => {
    const text = el.textContent || '';
    el.innerHTML = text.replace(reg, (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
  });
}

function copyText(content) {
  if (!content) return;
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(content).then(() => showTip('已复制')).catch(() => fallbackCopy(content));
  } else {
    fallbackCopy(content);
  }
}

function fallbackCopy(content) {
  const textarea = document.createElement('textarea');
  textarea.value = content;
  textarea.style.position = 'absolute';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  try { document.execCommand('copy'); showTip('已复制'); } catch (_) { alert('复制失败'); }
  document.body.removeChild(textarea);
}

function showTip(message) {
  const old = document.getElementById('quickTip');
  if (old) old.remove();
  const tip = document.createElement('div');
  tip.id = 'quickTip';
  tip.textContent = message;
  Object.assign(tip.style, {
    position: 'fixed', right: '16px', bottom: '16px', padding: '8px 12px',
    background: 'rgba(0,0,0,0.75)', color: '#fff', borderRadius: '6px', zIndex: '9999'
  });
  document.body.appendChild(tip);
  setTimeout(() => tip.remove(), 1200);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatDisplayTime(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  return raw.replace('T', ' ').replace('Z', '').split('.')[0];
}

async function downloadFile(path) {
  if (!path) {
    alert('文件路径无效');
    return;
  }

  const res = await fetch(`${API_PREFIX}/files/download/${encodeURIComponent(path)}`);
  if (!res.ok) {
    alert(res.status === 404 ? '文件不存在' : '下载失败');
    return;
  }

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = parseDownloadName(res.headers.get('Content-Disposition'), path);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

function parseDownloadName(contentDisposition, fallbackPath) {
  const fallback = String(fallbackPath || '').split('/').pop() || 'download.bin';
  if (!contentDisposition) return fallback;

  const utf8Match = contentDisposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (utf8Match && utf8Match[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch (_) {
      // ignore and fallback
    }
  }

  const filenameMatch = contentDisposition.match(/filename\s*=\s*"?([^";]+)"?/i);
  if (filenameMatch && filenameMatch[1]) return filenameMatch[1];
  return fallback;
}

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  return parts.length === 2 ? parts.pop().split(';').shift() : null;
}

function setCookie(name, value, days) {
  const date = new Date();
  date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
  document.cookie = `${name}=${value}; expires=${date.toUTCString()}; path=/; SameSite=Lax`;
}

function deleteCookie(name) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
}

function clearAuthState() {
  deleteCookie('text_system_login');
  deleteCookie('text_system_token');
}
