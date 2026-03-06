const TOKEN_STORAGE_KEY = "news_xhs_publish_token";
const TITLE_MAX_LEN = 20;

function esc(text) {
  const value = `${text ?? ""}`;
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function errorToMessage(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload === "string") return payload;
  if (Array.isArray(payload)) {
    return payload.map((item) => errorToMessage(item, "")).filter(Boolean).join("; ");
  }
  if (payload.msg) return payload.msg;
  if (payload.message) return payload.message;
  if (payload.detail) return errorToMessage(payload.detail, fallback);
  if (payload.raw) return payload.raw;
  return fallback;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (_) {
    payload = { raw: text };
  }
  if (!response.ok) {
    throw new Error(errorToMessage(payload, `HTTP ${response.status}`));
  }
  return payload;
}

function showToast(message, type = "info", duration = 3200) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  container.appendChild(node);
  window.setTimeout(() => node.remove(), duration);
}

function setActionStatus(text, level = "") {
  const node = document.getElementById("action-status");
  if (!node) return;
  node.textContent = text;
  node.className = `status-line ${level}`.trim();
}

function setButtonLoading(button, loading, label = "Processing...") {
  if (!button) return;
  if (loading) {
    if (!button.dataset.originalText) {
      button.dataset.originalText = button.textContent || "";
    }
    button.disabled = true;
    button.classList.add("is-loading");
    button.textContent = label;
    return;
  }
  button.disabled = false;
  button.classList.remove("is-loading");
  if (button.dataset.originalText) {
    button.textContent = button.dataset.originalText;
  }
}

async function runWithButton(button, fn, loadingText) {
  setButtonLoading(button, true, loadingText);
  try {
    await fn();
  } catch (error) {
    showToast(error.message || "Unknown error", "error");
    setActionStatus(`Failed: ${error.message}`, "error");
    throw error;
  } finally {
    setButtonLoading(button, false);
  }
}

function getPublishTokenInput() {
  return document.getElementById("publish-token");
}

function getStoredPublishToken() {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY) || "";
}

function setStoredPublishToken(token) {
  const value = `${token || ""}`.trim();
  if (value) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, value);
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

function getPublishHeaders() {
  const token = getStoredPublishToken();
  if (!token) return {};
  return { "X-Publish-Token": token };
}

function confirmPublishAction() {
  const first = window.confirm("Confirm publish this draft?");
  if (!first) return false;
  const second = window.prompt('Type "PUBLISH" to continue', "");
  return second === "PUBLISH";
}

function splitTags(value) {
  return `${value || ""}`
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function updateTitleLimitHint() {
  const input = document.getElementById("draft-title");
  const hint = document.getElementById("title-limit-hint");
  if (!input || !hint) return;
  if (input.value.length > TITLE_MAX_LEN) {
    input.value = input.value.slice(0, TITLE_MAX_LEN);
  }
  hint.textContent = `${input.value.length}/${TITLE_MAX_LEN}`;
}

function formData() {
  const titleInput = document.getElementById("draft-title");
  const title = `${titleInput.value || ""}`.trim().slice(0, TITLE_MAX_LEN);
  titleInput.value = title;
  updateTitleLimitHint();
  return {
    title,
    content: document.getElementById("draft-content").value.trim(),
    tags: splitTags(document.getElementById("draft-tags").value),
    cover_image_url: document.getElementById("draft-cover").value.trim(),
    editor_notes: document.getElementById("draft-notes").value.trim(),
  };
}

function renderPreview() {
  const title = document.getElementById("draft-title").value;
  const content = document.getElementById("draft-content").value;
  const tags = splitTags(document.getElementById("draft-tags").value);
  const cover = document.getElementById("draft-cover").value;

  const tagHtml = tags.map((tag) => `<span class="preview-tag">#${esc(tag)}</span>`).join("");
  const body = esc(content).replaceAll("\n", "<br>");
  const coverHtml = cover ? `<p><b>Cover:</b> <a href="${esc(cover)}" target="_blank">${esc(cover)}</a></p>` : "";

  document.getElementById("preview-box").innerHTML = `
    <h2 class="preview-title">${esc(title)}</h2>
    ${coverHtml}
    <div class="preview-tags">${tagHtml}</div>
    <div>${body}</div>
  `;
}

function setMeta(text) {
  const node = document.getElementById("draft-meta");
  if (node) node.textContent = text;
}

async function loadDraft() {
  const id = window.DRAFT_ID;
  const draft = await requestJson(`/api/drafts/${id}`);

  document.getElementById("draft-topic").value = draft.topic || "";
  document.getElementById("draft-title").value = `${draft.title || ""}`.slice(0, TITLE_MAX_LEN);
  document.getElementById("draft-content").value = draft.content || "";
  document.getElementById("draft-tags").value = (draft.tags || []).join(", ");
  document.getElementById("draft-cover").value = draft.cover_image_url || "";
  document.getElementById("draft-notes").value = draft.editor_notes || "";
  setMeta(`status=${draft.status}, updated_at=${draft.updated_at}`);
  setActionStatus("Draft loaded.", "success");
  updateTitleLimitHint();
  renderPreview();
}

async function saveDraft() {
  const id = window.DRAFT_ID;
  const payload = formData();
  await requestJson(`/api/drafts/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await loadDraft();
  showToast("Draft saved.", "success");
}

async function approveDraft() {
  const id = window.DRAFT_ID;
  await requestJson(`/api/drafts/${id}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes: document.getElementById("draft-notes").value || "" }),
  });
  await loadDraft();
  showToast("Draft approved.", "success");
}

async function rejectDraft() {
  const id = window.DRAFT_ID;
  await requestJson(`/api/drafts/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes: document.getElementById("draft-notes").value || "" }),
  });
  await loadDraft();
  showToast("Draft rejected.", "info");
}

async function publishDraft() {
  const id = window.DRAFT_ID;
  const sure = confirmPublishAction();
  if (!sure) return;
  const tokenInput = getPublishTokenInput();
  if (tokenInput && tokenInput.value.trim()) {
    setStoredPublishToken(tokenInput.value);
  }
  setActionStatus("Publishing, please wait...", "warning");
  const result = await requestJson(`/api/publish/${id}`, {
    method: "POST",
    headers: getPublishHeaders(),
  });
  await loadDraft();
  if (result.success) {
    showToast(`Publish success: ${result.message}`, "success", 4200);
    setActionStatus(`Publish success: ${result.message}`, "success");
  } else {
    showToast(`Publish failed: ${result.message}`, "error", 5200);
    setActionStatus(`Publish failed: ${result.message}`, "error");
  }
}

async function publishStatus() {
  const id = window.DRAFT_ID;
  const result = await requestJson(`/api/publish/${id}/status`);
  showToast(`task=${result.id}, status=${result.status}, error=${result.error_message || "none"}`, "info", 5200);
  setActionStatus(`publish task=${result.id}, status=${result.status}`, result.status === "succeeded" ? "success" : "");
}

async function uploadLocalCover() {
  const fileInput = document.getElementById("cover-file");
  if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
    throw new Error("Please select a local image first.");
  }
  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append("file", file);

  const result = await requestJson("/api/uploads/cover", {
    method: "POST",
    body: formData,
  });
  if (!result.success) {
    throw new Error(result.message || "Cover upload failed.");
  }

  const coverPath = result.cover_image_url || "";
  if (!coverPath) {
    throw new Error("Upload succeeded but no cover path returned.");
  }
  document.getElementById("draft-cover").value = coverPath;
  renderPreview();
  showToast("Local cover uploaded.", "success");
  setActionStatus("Local cover uploaded, click Save Draft to persist.", "success");
}

function bindEvents() {
  const tokenInput = getPublishTokenInput();
  if (tokenInput) {
    tokenInput.value = getStoredPublishToken();
    tokenInput.addEventListener("input", () => {
      setStoredPublishToken(tokenInput.value);
    });
  }

  const bind = (id, fn, loadingText) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.onclick = async () => {
      try {
        await runWithButton(node, fn, loadingText);
      } catch (_) {
        // already handled by runWithButton
      }
    };
  };

  bind("btn-reload", loadDraft, "Loading...");
  bind("btn-save", saveDraft, "Saving...");
  bind("btn-approve", approveDraft, "Approving...");
  bind("btn-reject", rejectDraft, "Rejecting...");
  bind("btn-publish", publishDraft, "Publishing...");
  bind("btn-status", publishStatus, "Checking...");
  bind("btn-upload-cover", uploadLocalCover, "Uploading...");

  document.getElementById("draft-title").addEventListener("input", () => {
    updateTitleLimitHint();
    renderPreview();
  });
  document.getElementById("draft-content").addEventListener("input", renderPreview);
  document.getElementById("draft-tags").addEventListener("input", renderPreview);
  document.getElementById("draft-cover").addEventListener("input", renderPreview);
}

async function init() {
  bindEvents();
  try {
    await loadDraft();
  } catch (error) {
    showToast(`Load draft failed: ${error.message}`, "error", 5200);
    setActionStatus(`Load failed: ${error.message}`, "error");
  }
}

window.addEventListener("DOMContentLoaded", init);
