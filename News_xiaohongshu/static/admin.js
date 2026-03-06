const TOKEN_STORAGE_KEY = "news_xhs_publish_token";
let publishGuardEnabled = false;
let qrPollingTimer = null;
let statusPollingTimer = null;

function escapeHtml(input) {
  return `${input ?? ""}`
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

function setText(id, value, className = "") {
  const node = document.getElementById(id);
  if (!node) return;
  node.textContent = value;
  node.className = `status-line ${className}`.trim();
}

function setMetric(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
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

function showToast(message, type = "info", duration = 3200) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  container.appendChild(node);
  window.setTimeout(() => node.remove(), duration);
}

function setButtonLoading(button, loading, loadingText = "Processing...") {
  if (!button) return;
  if (loading) {
    if (!button.dataset.originalText) {
      button.dataset.originalText = button.textContent || "";
    }
    button.disabled = true;
    button.classList.add("is-loading");
    button.textContent = loadingText;
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
  } finally {
    setButtonLoading(button, false);
  }
}

function statusChip(status) {
  const value = status || "unknown";
  return `<span class="chip ${escapeHtml(value)}">${escapeHtml(value)}</span>`;
}

function normalizeBase64Image(data) {
  if (!data) return "";
  const raw = `${data}`.trim();
  if (!raw) return "";
  if (raw.startsWith("data:image")) return raw;
  return `data:image/png;base64,${raw}`;
}

function stopQrPolling() {
  if (qrPollingTimer) {
    window.clearInterval(qrPollingTimer);
    qrPollingTimer = null;
  }
}

function startQrPolling() {
  stopQrPolling();
  qrPollingTimer = window.setInterval(async () => {
    try {
      await refreshSystemStatus(false);
    } catch (_) {
      // keep silent while polling
    }
  }, 3000);
}

function stopStatusPolling() {
  if (statusPollingTimer) {
    window.clearInterval(statusPollingTimer);
    statusPollingTimer = null;
  }
}

function startStatusPolling() {
  stopStatusPolling();
  statusPollingTimer = window.setInterval(async () => {
    try {
      await refreshSystemStatus(false);
    } catch (_) {
      // keep silent while polling
    }
  }, 15000);
}

async function refreshSystemStatus(showFeedback = true) {
  const sys = await requestJson("/api/system/status");
  publishGuardEnabled = Boolean(sys.publish_guard_enabled);
  const schedulerText = sys.scheduler_started ? "running" : "stopped";
  setText(
    "system-status",
    `service=${sys.service}, provider=${sys.search_provider}, scheduler_started=${sys.scheduler_started}, publish_guard_enabled=${publishGuardEnabled}`
  );
  setMetric("metric-service", sys.service || "-");
  setMetric("metric-provider", sys.search_provider || "-");
  setMetric("metric-scheduler", schedulerText);

  try {
    const xhs = await requestJson("/api/xhs/login-status");
    const xhsStatus = (xhs.status || "unknown").toLowerCase();
    setText("xhs-login-status", `xhs_login_status=${xhsStatus} (${xhs.message || "ok"})`);
    setMetric("metric-xhs", xhsStatus);

    if (xhsStatus === "logged_in") {
      setText("xhs-qrcode-tip", "已登录，小红书功能可用", "success");
      const img = document.getElementById("xhs-qrcode-image");
      if (img) {
        img.style.display = "none";
        img.removeAttribute("src");
      }
      stopQrPolling();
    }
  } catch (error) {
    setText("xhs-login-status", `xhs_login_status=error (${error.message})`, "error");
    setMetric("metric-xhs", "error");
  }

  if (showFeedback) {
    showToast("系统状态已刷新", "success", 1800);
  }
}

async function fetchLoginQrCode() {
  const data = await requestJson("/api/xhs/login-qrcode");
  const tipNode = document.getElementById("xhs-qrcode-tip");
  const imageNode = document.getElementById("xhs-qrcode-image");
  if (!tipNode || !imageNode) return;

  if (data.status === "logged_in") {
    tipNode.textContent = "当前已登录，无需扫码";
    tipNode.className = "status-line success";
    imageNode.style.display = "none";
    imageNode.removeAttribute("src");
    stopQrPolling();
    return;
  }

  const image = normalizeBase64Image(data.img);
  if (!image) {
    throw new Error(data.message || "二维码数据为空");
  }
  imageNode.src = image;
  imageNode.style.display = "block";
  tipNode.textContent = data.timeout
    ? `请在 ${data.timeout} 内使用小红书 App 扫码，状态将自动刷新`
    : "请使用小红书 App 扫码登录";
  tipNode.className = "status-line warning";
  startQrPolling();
}

async function resetXhsLogin() {
  await requestJson("/api/xhs/reset-login", { method: "POST" });
  stopQrPolling();
  const imageNode = document.getElementById("xhs-qrcode-image");
  const tipNode = document.getElementById("xhs-qrcode-tip");
  if (imageNode) {
    imageNode.style.display = "none";
    imageNode.removeAttribute("src");
  }
  if (tipNode) {
    tipNode.textContent = "登录状态已重置，请重新获取二维码";
    tipNode.className = "status-line warning";
  }
  await refreshSystemStatus(false);
}

function renderHotItems(items) {
  const container = document.getElementById("hot-items");
  if (!container) return;
  if (!items || !items.length) {
    container.innerHTML = "<div class='status-line warning'>暂无可展示的新闻条目</div>";
    return;
  }
  container.innerHTML = items
    .map((item, idx) => {
      const title = escapeHtml(item.title || "");
      const summary = escapeHtml(item.summary || "");
      const source = escapeHtml(item.source || "-");
      const publishedAt = escapeHtml(item.published_at || "-");
      const url = escapeHtml(item.url || "");
      return `<article class="news-item">
        <h4>${idx + 1}. ${title}</h4>
        <div class="news-meta">source=${source}, published_at=${publishedAt}</div>
        <div>${summary}</div>
        <a class="news-link" href="${url}" target="_blank" rel="noreferrer">${url}</a>
      </article>`;
    })
    .join("");
}

async function fetchHotNews() {
  const queryNode = document.getElementById("hot-query");
  const limitNode = document.getElementById("hot-limit");
  const periodNode = document.getElementById("hot-period");
  const query = (queryNode?.value || "").trim();
  const limit = Number(limitNode?.value || 20);
  const period = periodNode?.value || "24h";
  if (!query) {
    throw new Error("查询词不能为空");
  }

  const payload = { query, limit, period };
  const data = await requestJson("/api/news/hot/fetch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const summaryNode = document.getElementById("hot-result-summary");
  if (summaryNode) {
    summaryNode.textContent = `provider=${data.provider}, tool=${data.selected_tool}, count=${data.count}`;
    summaryNode.className = "status-line success";
  }

  setText("hot-result", JSON.stringify(data, null, 2));
  renderHotItems(data.items || []);

  const draftTopic = document.getElementById("draft-topic");
  if (draftTopic && (!draftTopic.value.trim() || draftTopic.value.trim() === "热点新闻")) {
    draftTopic.value = query;
  }
}

async function generateDraft() {
  const topic = document.getElementById("draft-topic").value.trim();
  const maxNewsItems = Number(document.getElementById("draft-max-items").value || 5);
  if (!topic) {
    throw new Error("主题不能为空");
  }
  const payload = { topic, max_news_items: maxNewsItems };
  const result = await requestJson("/api/drafts/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshDrafts();
  return result;
}

async function approveDraft(draftId) {
  const notes = window.prompt("Approve notes", "checked facts and wording") || "";
  await requestJson(`/api/drafts/${draftId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
  await refreshDrafts();
}

async function rejectDraft(draftId) {
  const notes = window.prompt("Reject reason", "need rewrite");
  if (notes === null) return;
  await requestJson(`/api/drafts/${draftId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
  await refreshDrafts();
}

function confirmPublishAction() {
  const first = window.confirm("Confirm publish this draft?");
  if (!first) return false;
  const second = window.prompt('Type "PUBLISH" to continue', "");
  return second === "PUBLISH";
}

async function publishDraft(draftId) {
  const sure = confirmPublishAction();
  if (!sure) return;
  if (publishGuardEnabled && !getStoredPublishToken()) {
    throw new Error("Publish token is required. Please fill Publish Token first.");
  }
  const result = await requestJson(`/api/publish/${draftId}`, {
    method: "POST",
    headers: getPublishHeaders(),
  });
  showToast(`Publish result: status=${result.status}, message=${result.message}`, "success");
  await refreshDrafts();
}

async function checkPublishStatus(draftId) {
  const result = await requestJson(`/api/publish/${draftId}/status`);
  showToast(`task=${result.id}, status=${result.status}, error=${result.error_message || "none"}`, "info", 4200);
}

function editDraft(draftId) {
  window.location.href = `/admin/draft/${draftId}`;
}

function bindDraftActions() {
  document.querySelectorAll("[data-action='edit']").forEach((node) => {
    node.onclick = () => editDraft(Number(node.dataset.id));
  });
  document.querySelectorAll("[data-action='approve']").forEach((node) => {
    node.onclick = async () => {
      try {
        await runWithButton(node, () => approveDraft(Number(node.dataset.id)), "Approving...");
        showToast("Draft approved", "success");
      } catch (error) {
        showToast(`Approve failed: ${error.message}`, "error");
      }
    };
  });
  document.querySelectorAll("[data-action='reject']").forEach((node) => {
    node.onclick = async () => {
      try {
        await runWithButton(node, () => rejectDraft(Number(node.dataset.id)), "Rejecting...");
        showToast("Draft rejected", "info");
      } catch (error) {
        showToast(`Reject failed: ${error.message}`, "error");
      }
    };
  });
  document.querySelectorAll("[data-action='publish']").forEach((node) => {
    node.onclick = async () => {
      try {
        await runWithButton(node, () => publishDraft(Number(node.dataset.id)), "Publishing...");
      } catch (error) {
        showToast(`Publish failed: ${error.message}`, "error");
      }
    };
  });
  document.querySelectorAll("[data-action='status']").forEach((node) => {
    node.onclick = async () => {
      try {
        await runWithButton(node, () => checkPublishStatus(Number(node.dataset.id)), "Checking...");
      } catch (error) {
        showToast(`Status failed: ${error.message}`, "error");
      }
    };
  });
}

async function refreshDrafts() {
  const rows = await requestJson("/api/drafts?limit=100");
  const tbody = document.getElementById("drafts-body");
  if (!tbody) return;

  if (!rows || rows.length === 0) {
    tbody.innerHTML = "<tr><td colspan='6'>No drafts</td></tr>";
    return;
  }

  tbody.innerHTML = rows
    .map((row) => {
      const topic = escapeHtml(row.topic || "");
      const title = escapeHtml(row.title || "");
      const shortTitle = title.length > 42 ? `${title.slice(0, 42)}...` : title;
      return `<tr>
        <td>${row.id}</td>
        <td>${statusChip(row.status)}</td>
        <td>${topic}</td>
        <td title="${title}">${shortTitle}</td>
        <td>${escapeHtml(row.updated_at || "")}</td>
        <td>
          <button data-action="edit" data-id="${row.id}">Edit</button>
          <button data-action="approve" data-id="${row.id}">Approve</button>
          <button data-action="reject" data-id="${row.id}">Reject</button>
          <button data-action="publish" data-id="${row.id}">Publish</button>
          <button data-action="status" data-id="${row.id}">Status</button>
        </td>
      </tr>`;
    })
    .join("");

  bindDraftActions();
}

async function refreshJobs() {
  const payload = await requestJson("/api/jobs/history?limit=50");
  const items = payload.items || [];
  const tbody = document.getElementById("jobs-body");
  if (!tbody) return;

  if (!items.length) {
    tbody.innerHTML = "<tr><td colspan='5'>No jobs</td></tr>";
    return;
  }

  tbody.innerHTML = items
    .map((item) => {
      return `<tr>
        <td>${item.id}</td>
        <td>${escapeHtml(item.job_name || "")}</td>
        <td>${statusChip(item.status)}</td>
        <td>${escapeHtml(item.message || "")}</td>
        <td>${escapeHtml(item.created_at || "")}</td>
      </tr>`;
    })
    .join("");
}

function bindActions() {
  const tokenInput = document.getElementById("publish-token");
  if (tokenInput) {
    tokenInput.value = getStoredPublishToken();
    tokenInput.addEventListener("input", () => {
      setStoredPublishToken(tokenInput.value);
    });
  }

  const bind = (id, handler, loadingText) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.onclick = async () => {
      await runWithButton(node, async () => {
        try {
          await handler();
        } catch (error) {
          showToast(error.message, "error");
          throw error;
        }
      }, loadingText);
    };
  };

  bind("btn-refresh-status", async () => refreshSystemStatus(true), "Refreshing...");
  bind("btn-fetch-hot", async () => {
    await fetchHotNews();
    showToast("热点抓取完成", "success");
  }, "Fetching...");
  bind("btn-generate-draft", async () => {
    const result = await generateDraft();
    if (result.auto_cover_generated) {
      showToast(`草稿生成完成，自动封面已生成（${result.auto_cover_provider || "image"}）`, "success");
      return;
    }
    if (result.auto_cover_error) {
      showToast(`草稿已生成，但自动封面失败：${result.auto_cover_error}`, "info", 5200);
      return;
    }
    showToast("草稿生成完成", "success");
  }, "Generating...");
  bind("btn-refresh-drafts", async () => {
    await refreshDrafts();
    showToast("草稿列表已刷新", "success", 1800);
  }, "Refreshing...");
  bind("btn-refresh-jobs", async () => {
    await refreshJobs();
    showToast("任务历史已刷新", "success", 1800);
  }, "Refreshing...");
  bind("btn-xhs-login-qrcode", async () => {
    await fetchLoginQrCode();
    showToast("二维码已更新", "success");
  }, "Loading...");
  bind("btn-xhs-reset-login", async () => {
    const ok = window.confirm("确认重置小红书登录状态并删除 cookies？");
    if (!ok) return;
    await resetXhsLogin();
    showToast("登录状态已重置", "info");
  }, "Resetting...");
}

async function init() {
  bindActions();
  try {
    await refreshSystemStatus(false);
    await refreshDrafts();
    await refreshJobs();
    startStatusPolling();
    showToast("控制台已就绪", "success", 1500);
  } catch (error) {
    showToast(`Init failed: ${error.message}`, "error", 4800);
  }
}

window.addEventListener("DOMContentLoaded", init);
window.addEventListener("beforeunload", () => {
  stopQrPolling();
  stopStatusPolling();
});

