const API_BASE =
  window.STORAGE_API_BASE ||
  (location.protocol === "file:" || location.port !== "8080"
    ? "http://127.0.0.1:8080"
    : "");

let token = localStorage.getItem("storage_token") || "";
let currentUser = null;
let currentPath = "";
let entries = [];
let selectedPaths = new Set();
let moveDestination = "";
let textNotes = [];
let logEntries = [];
let activeLogFilter = "all";
let activeView = "files";

const PREVIEW_EXTENSIONS = new Set([
  "html",
  "htm",
  "png",
  "jpg",
  "jpeg",
  "gif",
  "svg",
  "webp",
  "bmp",
  "ico",
  "pdf",
  "txt",
  "md",
  "json",
  "css",
  "js",
  "xml",
  "mp4",
  "webm",
  "mp3",
  "wav",
]);

const FILE_TYPE_EXTENSIONS = {
  image: ["jpg", "jpeg", "png", "gif", "svg", "webp", "bmp", "ico", "heic", "raw"],
  video: ["mp4", "mov", "mkv", "avi", "webm", "m4v", "flv"],
  audio: ["mp3", "wav", "flac", "m4a", "aac", "ogg", "wma"],
  pdf: ["pdf"],
  word: ["doc", "docx", "odt", "rtf"],
  sheet: ["xls", "xlsx", "csv", "ods"],
  slides: ["ppt", "pptx", "odp", "key"],
  archive: ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"],
  code: ["html", "htm", "css", "js", "jsx", "ts", "tsx", "py", "java", "c", "cpp", "h", "go", "rs", "php", "vue", "sh", "sql", "json", "xml", "yaml", "yml"],
  text: ["txt", "md", "log", "ini", "conf"],
  app: ["exe", "msi", "dmg", "pkg", "apk", "appimage", "deb", "rpm"],
  font: ["ttf", "otf", "woff", "woff2", "eot"],
  database: ["db", "sqlite", "sqlite3", "mdb"],
};

const FILE_ICON_PATHS = {
  generic: '<path d="M7 2.75h7l4.25 4.25v14.25H7z"/><path d="M14 2.75V7h4.25"/>',
  image: '<rect x="3.25" y="4.25" width="17.5" height="15.5" rx="2.25"/><circle cx="8.5" cy="9" r="1.5"/><path d="m4.5 17 4.6-4.5 3.2 3 2.2-2.1 5 4.6"/>',
  video: '<rect x="3.25" y="5" width="17.5" height="14" rx="2.25"/><path d="m10 9 5 3-5 3z"/>',
  audio: '<path d="M9 18V6l9-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="15.5" cy="16" r="2.5"/><path d="M9 9.5 18 7.5"/>',
  pdf: '<path d="M7 2.75h7l4.25 4.25v14.25H7z"/><path d="M14 2.75V7h4.25"/><path d="M9 16v-5h2a1.5 1.5 0 0 1 0 3H9m5-3h1.25a2 2 0 0 1 2 2v1a2 2 0 0 1-2 2H14z"/>',
  word: '<path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  sheet: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 9h16M4 15h16M10 9v12M15 9v12"/>',
  slides: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4m-2-13 5 2.5-5 2.5z"/>',
  archive: '<path d="M7 2.75h7l4.25 4.25v14.25H7z"/><path d="M14 2.75V7h4.25M10 3v2m0 2v2m0 2v2m0 2v3h3v-3z"/>',
  code: '<path d="M7 2.75h7l4.25 4.25v14.25H7z"/><path d="M14 2.75V7h4.25M11 11l-2 2 2 2m3-4 2 2-2 2"/>',
  text: '<path d="M7 2.75h7l4.25 4.25v14.25H7z"/><path d="M14 2.75V7h4.25M9.5 11h6M9.5 14.5h6M9.5 18h4"/>',
  app: '<rect x="3.5" y="4" width="17" height="16" rx="2.5"/><path d="M3.5 9h17M8 14l2 2-2 2m4 0h4"/>',
  font: '<path d="M7 20 12 4l5 16M9 14h6"/>',
  database: '<ellipse cx="12" cy="5.5" rx="7.5" ry="3"/><path d="M4.5 5.5v6c0 1.65 3.36 3 7.5 3s7.5-1.35 7.5-3v-6M4.5 11.5v6c0 1.65 3.36 3 7.5 3s7.5-1.35 7.5-3v-6"/>',
};

function fileTypeForName(name) {
  const text = String(name || "");
  const dot = text.lastIndexOf(".");
  const extension = dot > 0 && dot < text.length - 1
    ? text.slice(dot + 1).toLowerCase()
    : "";
  return Object.entries(FILE_TYPE_EXTENSIONS).find(([, extensions]) =>
    extensions.includes(extension)
  )?.[0] || "generic";
}

function fileIcon(name) {
  const type = fileTypeForName(name);
  return `<span class="file-icon-wrap file-icon-wrap--${type}">
    <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${FILE_ICON_PATHS[type]}</svg>
  </span>`;
}

function folderTypeForName(name) {
  const value = String(name || "").toLowerCase();
  if (/(图片|照片|photo|picture|image)/.test(value)) return "image";
  if (/(视频|电影|video|movie)/.test(value)) return "video";
  if (/(音乐|音频|music|audio)/.test(value)) return "audio";
  if (/(代码|项目|code|project|src)/.test(value)) return "code";
  if (/(下载|download)/.test(value)) return "download";
  if (/(文档|资料|document|docs)/.test(value)) return "document";
  return "default";
}

function folderIcon(name = "") {
  const type = folderTypeForName(name);
  return `<span class="folder-icon-wrap folder-icon-wrap--${type}">
    <svg class="folder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path class="folder-icon-fill" d="M2.75 7.25A2.25 2.25 0 0 1 5 5h4.1l2 2H19a2.25 2.25 0 0 1 2.25 2.25v8.5A2.25 2.25 0 0 1 19 20H5a2.25 2.25 0 0 1-2.25-2.25z"/>
      <path d="M2.75 9h18.5"/>
    </svg>
  </span>`;
}

document.addEventListener("DOMContentLoaded", () => {
  bindLogin();
  bindStorage();
  bindGlobalDropProtection();

  if (token) {
    loadCurrentUser();
  } else {
    showLogin();
  }
});

function bindLogin() {
  const form = document.getElementById("loginForm");
  const input = document.getElementById("usernameInput");
  const error = document.getElementById("loginError");

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";
    const username = input.value.trim();
    if (!username) return;

    const button = form.querySelector("button[type='submit']");
    button.disabled = true;
    try {
      const response = await api("/auth/login", {
        method: "POST",
        json: { username },
      });
      if (response.status === 404) {
        error.textContent = "用户不存在，请检查用户名。";
        return;
      }
      if (!response.ok) {
        const data = await safeJson(response);
        error.textContent = data?.detail || "登录失败。";
        return;
      }

      const data = await response.json();
      token = data.token;
      currentUser = data.user;
      localStorage.setItem("storage_token", token);
      localStorage.setItem("storage_user", JSON.stringify(currentUser));
      currentPath = "";
      showStorage();
      await loadUserInfo();
      await loadCurrentDirectory();
    } catch (_err) {
      error.textContent = "无法连接服务，请稍后重试。";
    } finally {
      button.disabled = false;
    }
  });

}

function bindStorage() {
  document.getElementById("logoutBtn")?.addEventListener("click", logout);
  document.getElementById("rootBtn")?.addEventListener("click", () => {
    switchView("files");
    navigateTo("");
  });
  document.getElementById("textsBtn")?.addEventListener("click", () => {
    switchView("texts");
    loadTextNotes();
  });
  document.getElementById("logsBtn")?.addEventListener("click", () => {
    switchView("logs");
    loadLogs();
  });
  document.getElementById("uploadFileBtn")?.addEventListener("click", () =>
    document.getElementById("fileInput").click()
  );
  document.getElementById("uploadFolderBtn")?.addEventListener("click", () =>
    document.getElementById("folderInput").click()
  );
  document.getElementById("newFolderBtn")?.addEventListener("click", createFolder);
  document.getElementById("refreshBtn")?.addEventListener("click", () =>
    loadCurrentDirectory()
  );
  document
    .getElementById("selectAllCheckbox")
    ?.addEventListener("change", (event) =>
      selectAllVisible(event.target.checked)
    );
  document
    .getElementById("batchDownloadBtn")
    ?.addEventListener("click", batchDownloadSelected);
  document
    .getElementById("batchMoveBtn")
    ?.addEventListener("click", openMoveModal);
  document
    .getElementById("batchDeleteBtn")
    ?.addEventListener("click", batchDeleteSelected);

  const addTextForm = document.getElementById("addTextForm");
  addTextForm?.addEventListener("submit", addTextNote);
  const textCards = document.getElementById("textCards");
  textCards?.addEventListener("click", handleTextCardClick);
  document.getElementById("refreshLogsBtn")?.addEventListener("click", loadLogs);
  document.getElementById("logFilters")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-log-filter]");
    if (!button) return;
    activeLogFilter = button.dataset.logFilter || "all";
    renderLogs();
  });

  document.getElementById("fileInput")?.addEventListener("change", (event) => {
    collectInputFiles(event.target);
    event.target.value = "";
  });

  document.getElementById("folderInput")?.addEventListener("change", (event) => {
    collectFolderInput(event.target);
    event.target.value = "";
  });

  const breadcrumb = document.getElementById("breadcrumb");
  breadcrumb?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-path]");
    if (button) navigateTo(button.dataset.path || "");
  });

  const tableBody = document.getElementById("fileTableBody");
  tableBody?.addEventListener("click", handleTableClick);
  tableBody?.addEventListener("change", handleSelectionChange);

  const dropZone = document.getElementById("dropZone");
  dropZone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    dropZone.classList.add("drag-over");
  });
  dropZone?.addEventListener("dragleave", (event) => {
    if (!dropZone.contains(event.relatedTarget)) {
      dropZone.classList.remove("drag-over");
    }
  });
  dropZone?.addEventListener("drop", handleDrop);

  const moveBreadcrumb = document.getElementById("moveBreadcrumb");
  moveBreadcrumb?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-path]");
    if (button) loadMoveDirectory(button.dataset.path || "");
  });

  const moveFolderList = document.getElementById("moveFolderList");
  moveFolderList?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-path]");
    if (button) loadMoveDirectory(button.dataset.path || "");
  });

  document.getElementById("moveCloseBtn")?.addEventListener("click", closeMoveModal);
  document.getElementById("moveCancelBtn")?.addEventListener("click", closeMoveModal);
  document
    .getElementById("moveConfirmBtn")
    ?.addEventListener("click", confirmMove);
  document.getElementById("moveModal")?.addEventListener("click", (event) => {
    if (event.target === event.currentTarget) closeMoveModal();
  });
}

function bindGlobalDropProtection() {
  ["dragover", "drop"].forEach((eventName) => {
    window.addEventListener(eventName, (event) => {
      event.preventDefault();
    });
  });
}

async function api(path, options = {}) {
  const { json, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let body = fetchOptions.body;
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }

  const response = await fetch(`${API_BASE}/api${path}`, {
    ...fetchOptions,
    headers,
    body,
  });

  if (response.status === 401) {
    clearSession();
    showLogin();
    throw new Error("unauthorized");
  }

  return response;
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch (_err) {
    return null;
  }
}

async function loadCurrentUser() {
  try {
    const response = await api("/auth/me");
    if (!response.ok) {
      clearSession();
      showLogin();
      return;
    }
    const data = await response.json();
    currentUser = data.user;
    localStorage.setItem("storage_user", JSON.stringify(currentUser));
    renderUserInfo();
    showStorage();
    await loadCurrentDirectory();
  } catch (_err) {
    clearSession();
    showLogin();
  }
}

async function loadUserInfo() {
  if (!token) return;
  try {
    const response = await api("/auth/me");
    if (!response.ok) return;
    const data = await response.json();
    currentUser = data.user;
    localStorage.setItem("storage_user", JSON.stringify(currentUser));
    renderUserInfo();
  } catch (_err) {
    // ignore transient user info refresh errors
  }
}

function renderUserInfo() {
  const el = document.getElementById("userInfo");
  if (!el) return;

  const username = currentUser?.username || "";
  const storage = currentUser?.storage;
  let usage = "";
  if (storage) {
    usage = `已用 ${storage.used_display} / 磁盘 ${storage.disk_total_display}`;
  }
  el.textContent = [username, usage].filter(Boolean).join(" · ");
}

async function loadCurrentDirectory() {
  if (!token) return;
  try {
    const response = await api(
      `/files?path=${encodeURIComponent(currentPath)}`
    );
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "读取目录失败。");
      return;
    }
    const data = await response.json();
    currentPath = data.path || "";
    entries = data.entries || [];
    selectedPaths.clear();
    renderBreadcrumb();
    renderTable();
  } catch (_err) {
    showToast("无法连接服务。");
  }
}

function renderBreadcrumb() {
  const container = document.getElementById("breadcrumb");
  if (!container) return;

  const parts = currentPath ? currentPath.split("/").filter(Boolean) : [];
  let html = `<button type="button" class="crumb" data-path="">全部文件</button>`;
  let cumulative = "";

  parts.forEach((part) => {
    cumulative = cumulative ? `${cumulative}/${part}` : part;
    html += `<span class="crumb-sep">/</span>`;
    html += `<button type="button" class="crumb" data-path="${escapeAttr(cumulative)}">${escapeHtml(part)}</button>`;
  });

  container.innerHTML = html;
}

function renderTable() {
  const body = document.getElementById("fileTableBody");
  const empty = document.getElementById("emptyState");
  if (!body || !empty) return;

  if (!entries.length) {
    body.innerHTML = "";
    empty.classList.remove("hidden");
    updateSelectionUi();
    return;
  }
  empty.classList.add("hidden");

  body.innerHTML = entries
    .map((entry) => {
      const isFolder = entry.type === "folder";
      const icon = isFolder ? folderIcon(entry.name) : fileIcon(entry.name);
      const canPreview = !isFolder && isPreviewableFile(entry.name);
      const nameCell = isFolder
        ? `<button type="button" class="entry-link" data-path="${escapeAttr(entry.path)}">${icon}<span>${escapeHtml(entry.name)}</span></button>`
        : canPreview
          ? `<button type="button" class="file-open-btn" data-path="${escapeAttr(entry.path)}">${icon}<span>${escapeHtml(entry.name)}</span></button>`
          : `<button type="button" class="file-download-btn" data-path="${escapeAttr(entry.path)}" title="点击下载">${icon}<span>${escapeHtml(entry.name)}</span></button>`;

      const checked = selectedPaths.has(entry.path) ? "checked" : "";

      return `
        <tr data-path="${escapeAttr(entry.path)}" data-type="${entry.type}">
          <td class="select-cell">
            <input class="row-checkbox" type="checkbox" data-path="${escapeAttr(entry.path)}" ${checked} aria-label="选择 ${escapeAttr(entry.name)}">
          </td>
          <td>${nameCell}</td>
          <td>${escapeHtml(formatDate(entry.modified_at))}</td>
          <td>${escapeHtml(entry.size_display)}</td>
        </tr>`;
    })
    .join("");
  updateSelectionUi();
}

function handleSelectionChange(event) {
  const checkbox = event.target.closest(".row-checkbox");
  if (!checkbox) return;
  setSelected(checkbox.dataset.path || "", checkbox.checked);
}

function setSelected(path, checked) {
  if (!path) return;
  if (checked) {
    selectedPaths.add(path);
  } else {
    selectedPaths.delete(path);
  }
  updateSelectionUi();
}

function toggleSelected(path) {
  if (!path) return;
  setSelected(path, !selectedPaths.has(path));
}

function selectAllVisible(checked) {
  entries.forEach((entry) => {
    if (checked) {
      selectedPaths.add(entry.path);
    } else {
      selectedPaths.delete(entry.path);
    }
  });
  updateSelectionUi();
}

function updateSelectionUi() {
  const count = selectedPaths.size;
  const countEl = document.getElementById("selectionCount");
  const downloadBtn = document.getElementById("batchDownloadBtn");
  const moveBtn = document.getElementById("batchMoveBtn");
  const deleteBtn = document.getElementById("batchDeleteBtn");
  const selectAll = document.getElementById("selectAllCheckbox");

  if (countEl) countEl.textContent = `已选择 ${count} 项`;
  const disabled = count === 0;
  if (downloadBtn) downloadBtn.disabled = disabled;
  if (moveBtn) moveBtn.disabled = disabled;
  if (deleteBtn) deleteBtn.disabled = disabled;
  if (selectAll) {
    selectAll.checked =
      entries.length > 0 && entries.every((entry) => selectedPaths.has(entry.path));
  }
  document.querySelectorAll(".row-checkbox").forEach((checkbox) => {
    checkbox.checked = selectedPaths.has(checkbox.dataset.path || "");
  });
}

async function handleTableClick(event) {
  if (event.target.closest(".row-checkbox")) {
    return;
  }

  const openButton = event.target.closest(".file-open-btn");
  if (openButton) {
    openFilePreview(openButton.dataset.path || "");
    return;
  }

  const downloadButton = event.target.closest(".file-download-btn");
  if (downloadButton) {
    startDownload([downloadButton.dataset.path || ""]);
    return;
  }

  const row = event.target.closest("tr[data-path]");
  if (!row) return;

  if (row.dataset.type === "folder") {
    navigateTo(row.dataset.path || "");
  } else {
    toggleSelected(row.dataset.path || "");
  }
}

async function navigateTo(path) {
  currentPath = path || "";
  await loadCurrentDirectory();
  document.getElementById("rootBtn")?.classList.add("active");
  document.getElementById("textsBtn")?.classList.remove("active");
  document.getElementById("logsBtn")?.classList.remove("active");
}

function switchView(view) {
  activeView = view;
  document.getElementById("filesView")?.classList.toggle("hidden", view !== "files");
  document.getElementById("textsView")?.classList.toggle("hidden", view !== "texts");
  document.getElementById("logsView")?.classList.toggle("hidden", view !== "logs");
  document.getElementById("rootBtn")?.classList.toggle("active", view === "files");
  document.getElementById("textsBtn")?.classList.toggle("active", view === "texts");
  document.getElementById("logsBtn")?.classList.toggle("active", view === "logs");
}

async function loadLogs() {
  if (!token) return;
  try {
    const response = await api("/logs");
    if (!response.ok) return;
    logEntries = await response.json();
    renderLogs();
  } catch (_err) {
    showToast("读取日志失败。");
  }
}

function renderLogs() {
  const tableBody = document.getElementById("logTableBody");
  const empty = document.getElementById("logEmpty");
  if (!tableBody || !empty) return;

  document.querySelectorAll("[data-log-filter]").forEach((button) => {
    button.classList.toggle("active", button.dataset.logFilter === activeLogFilter);
  });

  const visibleEntries = logEntries.filter(
    (entry) => activeLogFilter === "all" || getLogCategory(entry.content) === activeLogFilter
  );
  empty.classList.toggle("hidden", visibleEntries.length > 0);
  tableBody.innerHTML = visibleEntries
    .map(
      (entry) => {
        const category = getLogCategory(entry.content);
        const label = getLogCategoryLabel(category);
        return `
          <tr>
            <td class="log-time">${escapeHtml(formatDate(entry.created_at))}</td>
            <td><span class="log-type log-type--${category}">${label}</span></td>
            <td class="log-content">${escapeHtml(entry.content)}</td>
          </tr>`;
      }
    )
    .join("");
}

function getLogCategory(content = "") {
  const action = String(content).split("：", 1)[0];
  if (action.startsWith("上传")) return "upload";
  if (action.startsWith("新建")) return "create";
  if (action.startsWith("下载") || action.startsWith("批量下载")) return "download";
  if (action.startsWith("移动")) return "move";
  if (action.startsWith("删除")) return "delete";
  return "other";
}

function getLogCategoryLabel(category) {
  return {
    upload: "上传",
    create: "新建",
    download: "下载",
    move: "移动",
    delete: "删除",
    other: "其他",
  }[category] || "其他";
}

async function loadTextNotes() {
  if (!token) return;
  try {
    const response = await api("/texts");
    if (!response.ok) return;
    textNotes = await response.json();
    renderTextCards();
  } catch (_err) {
    showToast("读取文本失败。");
  }
}

function renderTextCards() {
  const container = document.getElementById("textCards");
  if (!container) return;

  if (!textNotes.length) {
    container.innerHTML = `<div class="text-empty">还没有保存文本。</div>`;
    return;
  }

  container.innerHTML = textNotes
    .map(
      (note) => `
        <article class="text-card" data-id="${note.id}">
          <div class="text-card-meta">${escapeHtml(formatDate(note.created_at))}</div>
          <div class="text-card-content" data-content="${escapeAttr(note.content)}"></div>
          <div class="text-card-actions">
            <button type="button" class="row-btn copy-text-btn" data-content="${escapeAttr(note.content)}">复制</button>
            <button type="button" class="row-btn danger delete-text-btn" data-id="${note.id}">删除</button>
          </div>
        </article>`
    )
    .join("");

  container.querySelectorAll(".text-card-content").forEach((el) => {
    linkifyTextElement(el);
  });
}

function linkifyTextElement(el) {
  const raw = el.dataset.content || "";
  el.textContent = "";
  const fragment = document.createDocumentFragment();
  const regex = /(https?:\/\/[^\s<]+)/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(raw)) !== null) {
    if (match.index > lastIndex) {
      fragment.appendChild(document.createTextNode(raw.slice(lastIndex, match.index)));
    }
    const link = document.createElement("a");
    link.href = match[0];
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = match[0];
    fragment.appendChild(link);
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < raw.length) {
    fragment.appendChild(document.createTextNode(raw.slice(lastIndex)));
  }
  el.appendChild(fragment);
}

async function addTextNote(event) {
  event.preventDefault();
  const input = document.getElementById("textContent");
  const content = input.value.trim();
  if (!content) return;

  try {
    const response = await api("/texts", {
      method: "POST",
      json: { content },
    });
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "保存失败。");
      return;
    }
    input.value = "";
    await loadTextNotes();
    showToast("文本已保存。");
  } catch (_err) {
    showToast("保存失败。");
  }
}

async function handleTextCardClick(event) {
  const copyButton = event.target.closest(".copy-text-btn");
  if (copyButton) {
    copyText(copyButton.dataset.content || "");
    return;
  }

  const deleteButton = event.target.closest(".delete-text-btn");
  if (!deleteButton) return;

  if (!window.confirm("确认删除这条文本吗？")) return;
  try {
    const response = await api(`/texts/${deleteButton.dataset.id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      showToast("删除失败。");
      return;
    }
    await loadTextNotes();
    showToast("已删除。");
  } catch (_err) {
    showToast("删除失败。");
  }
}

function copyText(content) {
  if (!content) return;
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(content).then(
      () => showToast("已复制"),
      () => fallbackCopyText(content)
    );
    return;
  }
  fallbackCopyText(content);
}

function fallbackCopyText(content) {
  const textarea = document.createElement("textarea");
  textarea.value = content;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand("copy");
    showToast("已复制");
  } catch (_err) {
    showToast("复制失败");
  }
  document.body.removeChild(textarea);
}

async function createFolder() {
  const name = window.prompt("输入新文件夹名称");
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed) return;

  try {
    const response = await api("/files/mkdir", {
      method: "POST",
      json: { path: currentPath, name: trimmed },
    });
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "创建文件夹失败。");
      return;
    }
    showToast("文件夹已创建。");
    await loadCurrentDirectory();
    await loadUserInfo();
  } catch (_err) {
    showToast("创建文件夹失败。");
  }
}

async function batchDeleteSelected() {
  const paths = Array.from(selectedPaths);
  if (!paths.length) return;
  if (!window.confirm(`确认删除选中的 ${paths.length} 项吗？`)) return;

  try {
    const response = await api("/files/batch-delete", {
      method: "POST",
      json: { paths },
    });
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "删除失败。");
      return;
    }

    const data = await response.json();
    const failed = (data.results || []).filter((item) => !item.deleted);
    if (failed.length) {
      showToast(`删除完成，${failed.length} 项未删除。`);
    } else {
      showToast("删除完成。");
    }
    selectedPaths.clear();
    await loadCurrentDirectory();
    await loadUserInfo();
  } catch (_err) {
    showToast("删除失败。");
  }
}

async function batchDownloadSelected() {
  const paths = Array.from(selectedPaths);
  if (!paths.length) return;

  await startDownload(paths);
}

async function startDownload(paths) {
  const validPaths = paths.filter(Boolean);
  if (!validPaths.length) return;

  try {
    const response = await api("/files/download/prepare", {
      method: "POST",
      json: {
        paths: validPaths,
        base: currentPath,
      },
    });
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "下载失败。");
      return;
    }

    const data = await response.json();
    const baseUrl = API_BASE || window.location.origin;
    const anchor = document.createElement("a");
    anchor.href = new URL(data.url, baseUrl).href;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    showToast("下载已开始。");
  } catch (_err) {
    showToast("下载失败。");
  }
}

function isPreviewableFile(name) {
  const parts = String(name || "").split(".");
  const extension = parts.length > 1 ? parts.pop().toLowerCase() : "";
  return PREVIEW_EXTENSIONS.has(extension);
}

async function openFilePreview(path) {
  if (!path) return;
  const previewWindow = window.open("", "_blank");
  if (!previewWindow) {
    showToast("浏览器阻止了新窗口，请允许弹出窗口。");
    return;
  }

  try {
    const response = await api("/files/preview/start", {
      method: "POST",
      json: { path },
    });
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "打开文件失败。");
      previewWindow.close();
      return;
    }

    const data = await response.json();
    const baseUrl = API_BASE || window.location.origin;
    const previewUrl = new URL(data.url, baseUrl).href;
    previewWindow.location.href = previewUrl;
  } catch (_err) {
    previewWindow.close();
    showToast("打开文件失败。");
  }
}

function openMoveModal() {
  if (!selectedPaths.size) return;
  moveDestination = "";
  document.getElementById("moveModal")?.classList.remove("hidden");
  loadMoveDirectory("");
}

function closeMoveModal() {
  document.getElementById("moveModal")?.classList.add("hidden");
}

async function loadMoveDirectory(path) {
  try {
    const response = await api(
      `/files?path=${encodeURIComponent(path || "")}`
    );
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "读取目标文件夹失败。");
      return;
    }
    const data = await response.json();
    moveDestination = data.path || "";
    renderMoveBreadcrumb();
    renderMoveFolders(data.entries || []);
    updateMoveDestinationLabel();
  } catch (_err) {
    showToast("读取目标文件夹失败。");
  }
}

function renderMoveBreadcrumb() {
  const container = document.getElementById("moveBreadcrumb");
  if (!container) return;

  const parts = moveDestination
    ? moveDestination.split("/").filter(Boolean)
    : [];
  let html = `<button type="button" class="crumb" data-path="">全部文件</button>`;
  let cumulative = "";

  parts.forEach((part) => {
    cumulative = cumulative ? `${cumulative}/${part}` : part;
    html += `<span class="crumb-sep">/</span>`;
    html += `<button type="button" class="crumb" data-path="${escapeAttr(cumulative)}">${escapeHtml(part)}</button>`;
  });

  container.innerHTML = html;
}

function renderMoveFolders(entries) {
  const container = document.getElementById("moveFolderList");
  if (!container) return;

  const folders = entries.filter((entry) => entry.type === "folder");
  if (!folders.length) {
    container.innerHTML = `<div class="move-empty">当前目录没有子文件夹</div>`;
    return;
  }

  container.innerHTML = folders
    .map(
      (folder) => `
        <button type="button" class="move-folder-item" data-path="${escapeAttr(folder.path)}">
          ${folderIcon(folder.name)}<span>${escapeHtml(folder.name)}</span>
        </button>`
    )
    .join("");
}

function updateMoveDestinationLabel() {
  const label = document.getElementById("moveDestinationLabel");
  if (!label) return;
  label.textContent = `目标：${moveDestination || "全部文件"}`;
}

async function confirmMove() {
  const paths = Array.from(selectedPaths);
  if (!paths.length) return;

  try {
    const response = await api("/files/move", {
      method: "POST",
      json: {
        paths,
        destination: moveDestination,
      },
    });
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "移动失败。");
      return;
    }

    const data = await response.json();
    showToast(`已移动 ${(data.moved || []).length} 项。`);
    selectedPaths.clear();
    closeMoveModal();
    await loadCurrentDirectory();
    await loadUserInfo();
  } catch (_err) {
    showToast("移动失败。");
  }
}

function collectInputFiles(input) {
  const files = Array.from(input.files || []);
  const relativePaths = files.map((file) => file.name);
  uploadFiles(files, relativePaths);
}

function collectFolderInput(input) {
  const files = Array.from(input.files || []);
  const relativePaths = files.map((file) => file.webkitRelativePath || file.name);
  uploadFiles(files, relativePaths);
}

async function handleDrop(event) {
  event.preventDefault();
  const dropZone = document.getElementById("dropZone");
  dropZone?.classList.remove("drag-over");

  const dataTransfer = event.dataTransfer;
  if (!dataTransfer) return;

  try {
    const files = [];
    const relativePaths = [];

    if (dataTransfer.items?.length) {
      const entries = [];
      for (const item of dataTransfer.items) {
        const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();
        if (entry) {
          entries.push(entry);
        } else {
          const file = item.getAsFile();
          if (file) {
            files.push(file);
            relativePaths.push(file.name);
          }
        }
      }
      for (const entry of entries) {
        await walkEntry(entry, "", files, relativePaths);
      }
    } else if (dataTransfer.files?.length) {
      for (const file of dataTransfer.files) {
        files.push(file);
        relativePaths.push(file.name);
      }
    }

    uploadFiles(files, relativePaths);
  } catch (_err) {
    showToast("无法读取拖入的内容。");
  }
}

async function walkEntry(entry, prefix, files, relativePaths) {
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => {
      entry.file(resolve, reject);
    });
    files.push(file);
    relativePaths.push(prefix + entry.name);
    return;
  }

  if (entry.isDirectory) {
    const reader = entry.createReader();
    const children = [];
    while (true) {
      const batch = await new Promise((resolve, reject) => {
        reader.readEntries(resolve, reject);
      });
      if (!batch.length) break;
      children.push(...batch);
    }
    for (const child of children) {
      await walkEntry(child, `${prefix}${entry.name}/`, files, relativePaths);
    }
  }
}

function uploadFiles(files, relativePaths) {
  if (!files.length) return;

  const formData = new FormData();
  formData.append("path", currentPath);
  files.forEach((file, index) => {
    formData.append("files", file);
    formData.append("relative_paths", relativePaths[index] || file.name);
  });

  const progressWrap = document.getElementById("uploadProgress");
  const progressBar = document.getElementById("progressBar");
  const progressText = document.getElementById("progressText");
  progressWrap?.classList.remove("hidden");
  updateProgress(0);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", `${API_BASE}/api/files/upload`);
  xhr.setRequestHeader("Authorization", `Bearer ${token}`);

  xhr.upload.onprogress = (event) => {
    if (!event.lengthComputable) return;
    updateProgress(Math.round((event.loaded / event.total) * 100));
  };

  xhr.onload = async () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      showToast("上传完成。");
      await loadCurrentDirectory();
      await loadUserInfo();
    } else {
      let message = "上传失败。";
      try {
        const data = JSON.parse(xhr.responseText);
        message = data.detail || message;
      } catch (_err) {
        // keep fallback message
      }
      showToast(message);
    }
    setTimeout(() => progressWrap?.classList.add("hidden"), 700);
  };

  xhr.onerror = () => {
    showToast("上传失败，请检查服务是否可用。");
    progressWrap?.classList.add("hidden");
  };

  xhr.send(formData);
}

function updateProgress(percent) {
  const progressBar = document.getElementById("progressBar");
  const progressText = document.getElementById("progressText");
  if (progressBar) progressBar.style.width = `${percent}%`;
  if (progressText) progressText.textContent = `${percent}%`;
}

async function logout() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (_err) {
    // local session still gets cleared below
  }
  clearSession();
  showLogin();
}

function clearSession() {
  token = "";
  currentUser = null;
  currentPath = "";
  entries = [];
  selectedPaths.clear();
  moveDestination = "";
  localStorage.removeItem("storage_token");
  localStorage.removeItem("storage_user");
}

function showLogin() {
  document.getElementById("loginView")?.classList.remove("hidden");
  document.getElementById("storageView")?.classList.add("hidden");
  document.getElementById("moveModal")?.classList.add("hidden");
}

function showStorage() {
  document.getElementById("loginView")?.classList.add("hidden");
  document.getElementById("storageView")?.classList.remove("hidden");
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

let toastTimer = null;
function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}
