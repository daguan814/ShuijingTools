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
      <div class="data-card" data-type="text" data-id="${t.id}">
        <div class="data-card-top">
          <small class="text-muted"><i class="bi bi-clock"></i> ${escapeHtml(formatDisplayTime(t.created_at))}</small>
          <button type="button" class="btn btn-outline-warning btn-sm text-favorite-btn" data-id="${t.id}" title="收藏"><i class="bi bi-star"></i> 收藏</button>
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
  const visibleFiles = filesState.filter((f) => !f.is_favorite);
  if (!visibleFiles.length) {
    container.innerHTML = '<div class="empty-state small-empty"><h6>暂无文件</h6></div>';
    return;
  }

  container.innerHTML = visibleFiles.map((f) => `
    <div class="data-card" data-type="file" data-path="${escapeHtml(f.path)}">
      <div class="data-card-top">
        <span class="badge text-bg-secondary">文件</span>
        <small class="text-muted"><i class="bi bi-hdd"></i> ${escapeHtml(f.size)}</small>
      </div>
      <div class="data-card-content">${escapeHtml(f.path)}</div>
      <div class="data-card-actions">
        <button type="button" class="btn btn-outline-warning btn-sm file-favorite-btn" data-path="${escapeHtml(f.path)}"><i class="bi bi-star"></i> 收藏</button>
        <button type="button" class="btn btn-outline-primary btn-sm file-download-btn" data-path="${escapeHtml(f.path)}"><i class="bi bi-download"></i> 下载</button>
        <button type="button" class="btn btn-outline-danger btn-sm file-delete-btn" data-path="${escapeHtml(f.path)}"><i class="bi bi-trash"></i> 删除</button>
      </div>
    </div>`).join('');
}

function renderFavoriteColumns() {
  const g1 = document.getElementById('favoriteGroup1');
  if (!g1) return;

  const group1 = [
    ...favoritesState.map((item) => ({ ...item, favorite_type: 'text' })),
    ...filesState.filter((item) => item.is_favorite).map((item) => ({ ...item, favorite_type: 'file' })),
  ];
  g1.innerHTML = renderFavoriteGroup(group1);

  if (!group1.length) g1.innerHTML = '<div class="favorite-empty">暂无收藏</div>';
}

function renderFavoriteGroup(items) {
  return items.map((item) => {
    if (item.favorite_type === 'file') {
      const safePath = escapeHtml(item.path || '');
      return `
        <div class="favorite-item" data-type="file" data-path="${safePath}">
          <div class="data-card-top">
            <span class="badge text-bg-secondary">文件</span>
            <small class="text-muted"><i class="bi bi-hdd"></i> ${escapeHtml(item.size || '')}</small>
          </div>
          <div class="favorite-item-content">${safePath}</div>
          <div class="favorite-item-actions">
            <button type="button" class="btn btn-outline-primary btn-sm file-download-btn" data-path="${safePath}"><i class="bi bi-download"></i> 下载</button>
            <button type="button" class="btn btn-outline-warning btn-sm file-unfavorite-btn" data-path="${safePath}"><i class="bi bi-star-fill"></i> 取消收藏</button>
            <button type="button" class="btn btn-outline-danger btn-sm file-delete-btn" data-path="${safePath}"><i class="bi bi-trash"></i> 删除</button>
          </div>
        </div>`;
    }

    const safe = escapeHtml(item.content || '');
    return `
      <div class="favorite-item" data-type="text" data-id="${item.id}">
        <div class="favorite-item-content text-content">${safe}</div>
        <div class="favorite-item-actions">
          <button type="button" class="btn btn-outline-secondary btn-sm text-copy-btn" data-content="${safe}"><i class="bi bi-clipboard"></i> 复制</button>
          <button type="button" class="btn btn-outline-warning btn-sm text-unfavorite-btn" data-id="${item.id}"><i class="bi bi-star-fill"></i> 取消收藏</button>
          <button type="button" class="btn btn-outline-danger btn-sm favorite-delete-btn" data-id="${item.id}"><i class="bi bi-trash"></i> 删除</button>
        </div>
      </div>`;
  }).join('');
}

function initAddTextForm() {
  const form = document.getElementById('addTextForm');
  if (!form) return;
  const contentInput = document.getElementById('content');
  const pasteBtn = document.getElementById('pasteTextBtn');

  pasteBtn?.addEventListener('click', async () => {
    try {
      const pasted = await navigator.clipboard.readText();
      if (!pasted.trim()) return showTip('剪贴板没有文本');
      contentInput.value = pasted;
      contentInput.focus();
      showTip('已粘贴');
    } catch (_) {
      alert('浏览器不允许读取剪贴板，请检查权限或使用 Ctrl+V');
    }
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const content = contentInput.value.trim();
    if (!content) return;

    const data = new FormData();
    data.append('content', content);
    const res = await fetch(`${API_PREFIX}/texts`, { method: 'POST', body: data });
    if (!res.ok) return alert('添加失败');

    contentInput.value = '';
    await reloadLibrary();
  });
}

function initUploadForm() {
  const form = document.getElementById('uploadForm');
  if (!form) return;

  const filesInput = document.getElementById('uploadFiles');
  const fileHint = document.getElementById('fileHint');
  const fileNames = document.getElementById('fileNames');
  const dropZone = document.getElementById('fileDropZone');

  const renderSelected = () => {
    const files = filesInput?.files || [];
    if (fileHint) fileHint.textContent = `已选择 ${files.length} 个文件`;
    if (fileNames) fileNames.innerHTML = Array.from(files).map((f) => `<div>${escapeHtml(f.name)}</div>`).join('');
  };

  filesInput?.addEventListener('change', renderSelected);
  dropZone?.addEventListener('dragover', (event) => {
    event.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone?.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone?.addEventListener('drop', (event) => {
    event.preventDefault();
    dropZone.classList.remove('drag-over');
    if (!filesInput || !event.dataTransfer?.files?.length) return;
    filesInput.files = event.dataTransfer.files;
    renderSelected();
  });
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

    const textFavoriteBtn = event.target.closest('.text-favorite-btn');
    if (textFavoriteBtn) {
      await setTextFavorite(textFavoriteBtn.dataset.id, true);
      await reloadLibrary();
      return;
    }

    const textUnfavoriteBtn = event.target.closest('.text-unfavorite-btn');
    if (textUnfavoriteBtn) {
      await setTextFavorite(textUnfavoriteBtn.dataset.id, false);
      await reloadLibrary();
      return;
    }

    const downloadBtn = event.target.closest('.file-download-btn');
    if (downloadBtn) {
      await downloadFile(downloadBtn.dataset.path || '');
      return;
    }

    const fileFavoriteBtn = event.target.closest('.file-favorite-btn');
    if (fileFavoriteBtn) {
      await setFileFavorite(fileFavoriteBtn.dataset.path || '', true);
      await reloadLibrary();
      return;
    }

    const fileUnfavoriteBtn = event.target.closest('.file-unfavorite-btn');
    if (fileUnfavoriteBtn) {
      await setFileFavorite(fileUnfavoriteBtn.dataset.path || '', false);
      await reloadLibrary();
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

async function setTextFavorite(textId, enabled) {
  const existing = favoritesState.find((f) => Number(f.id) === Number(textId));
  if (enabled && existing) return;
  if (!enabled && !existing) return;

  const res = await fetch(`${API_PREFIX}/texts/${textId}/favorite`, { method: 'POST' });
  if (!res.ok) alert('收藏操作失败');
}

async function setFileFavorite(path, enabled) {
  if (!path) return;
  const data = new FormData();
  data.append('path', path);
  data.append('enabled', enabled ? 'true' : 'false');
  const res = await fetch(`${API_PREFIX}/files/favorite`, { method: 'POST', body: data });
  if (!res.ok) alert('收藏操作失败');
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

  container.innerHTML = `
    <div class="table-responsive">
      <table class="table trash-table align-middle">
        <thead>
          <tr>
            <th>内容</th>
            <th class="trash-time-col">创建时间</th>
            <th class="trash-action-col">操作</th>
          </tr>
        </thead>
        <tbody>
          ${texts.map((t) => `
            <tr>
              <td class="trash-content text-content">${escapeHtml(t.content || '')}</td>
              <td class="text-muted">${escapeHtml(formatDisplayTime(t.created_at))}</td>
              <td>
                <div class="d-flex gap-2 flex-wrap">
                  <button type="button" class="btn btn-outline-success btn-sm" data-action="restore-text" data-id="${t.id}"><i class="bi bi-arrow-counterclockwise"></i> 还原</button>
                  <button type="button" class="btn btn-outline-danger btn-sm" data-action="delete-trash-text" data-id="${t.id}"><i class="bi bi-x-circle"></i> 移出回收站</button>
                </div>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function renderTrashFiles(files) {
  const container = document.getElementById('trashFileList');
  if (!container) return;
  if (!files.length) return container.innerHTML = '<div class="empty-state"><i class="bi bi-trash"></i><h4>没有已删除文件</h4></div>';

  container.innerHTML = `
    <div class="table-responsive">
      <table class="table trash-table align-middle">
        <thead>
          <tr>
            <th>文件</th>
            <th class="trash-size-col">大小</th>
            <th class="trash-time-col">删除时间</th>
            <th class="trash-action-col">操作</th>
          </tr>
        </thead>
        <tbody>
          ${files.map((f) => `
            <tr>
              <td class="trash-content">${escapeHtml(f.original_path || '')}</td>
              <td class="text-muted">${escapeHtml(f.size || '')}</td>
              <td class="text-muted">${escapeHtml(formatDisplayTime(f.deleted_at))}</td>
              <td>
                <div class="d-flex gap-2 flex-wrap">
                  <button type="button" class="btn btn-outline-success btn-sm" data-action="restore-file" data-id="${f.id}"><i class="bi bi-arrow-counterclockwise"></i> 还原</button>
                  <button type="button" class="btn btn-outline-danger btn-sm" data-action="delete-trash-file" data-id="${f.id}"><i class="bi bi-x-circle"></i> 移出回收站</button>
                </div>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
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
