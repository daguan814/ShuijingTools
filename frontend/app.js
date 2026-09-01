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

const fileIcon = `
  <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
    <path d="M14 2v6h6"></path>
  </svg>`;

const folderIcon = `
  <svg class="folder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
  </svg>`;

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
  document.getElementById("rootBtn")?.addEventListener("click", () =>
    navigateTo("")
  );
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
    showStorage();
    await loadCurrentDirectory();
  } catch (_err) {
    clearSession();
    showLogin();
  }
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
      const icon = isFolder ? folderIcon : fileIcon;
      const canPreview = !isFolder && isPreviewableFile(entry.name);
      const nameCell = isFolder
        ? `<button type="button" class="entry-link" data-path="${escapeAttr(entry.path)}">${icon}<span>${escapeHtml(entry.name)}</span></button>`
        : canPreview
          ? `<button type="button" class="file-open-btn" data-path="${escapeAttr(entry.path)}">${icon}<span>${escapeHtml(entry.name)}</span></button>`
          : `<span class="entry-name">${icon}<span>${escapeHtml(entry.name)}</span></span>`;

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
  document
    .querySelectorAll(".sidebar-link")
    .forEach((button) => button.classList.toggle("active", path === ""));
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
  } catch (_err) {
    showToast("删除失败。");
  }
}

async function batchDownloadSelected() {
  const paths = Array.from(selectedPaths);
  if (!paths.length) return;

  try {
    const response = await api("/files/batch-download", {
      method: "POST",
      json: {
        paths,
        base: currentPath,
      },
    });
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "下载失败。");
      return;
    }

    const blob = await response.blob();
    triggerDownloadBlob(blob, "selected_files.zip");
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
    const response = await api(
      `/files/preview?path=${encodeURIComponent(path)}`
    );
    if (!response.ok) {
      const data = await safeJson(response);
      showToast(data?.detail || "打开文件失败。");
      previewWindow.close();
      return;
    }

    const blob = await response.blob();
    const previewUrl = URL.createObjectURL(blob);
    previewWindow.location.href = previewUrl;
  } catch (_err) {
    previewWindow.close();
    showToast("打开文件失败。");
  }
}

function triggerDownloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
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
          ${folderIcon}<span>${escapeHtml(folder.name)}</span>
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
