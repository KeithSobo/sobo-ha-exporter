(function () {
  "use strict";

  // Helper to construct API URLs respecting Ingress base path
  function getApiUrl(endpoint) {
    const base = window.location.pathname.endsWith("/")
      ? window.location.pathname
      : window.location.pathname + "/";
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint.slice(1) : endpoint;
    return base + cleanEndpoint;
  }

  // DOM Elements
  const elStatusBadge = document.getElementById("status-badge");
  const elAppVersion = document.getElementById("app-version");
  const btnRefresh = document.getElementById("btn-refresh");
  const btnRunExport = document.getElementById("btn-run-export");
  const btnTestGit = document.getElementById("btn-test-git");
  const btnCopyKey = document.getElementById("btn-copy-key");

  // Tab switching
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      tabBtns.forEach((b) => b.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));

      btn.classList.add("active");
      document.getElementById(targetId).classList.add("active");
    });
  });

  // Fetch API helper
  async function fetchJson(endpoint, options = {}) {
    try {
      const res = await fetch(getApiUrl(endpoint), options);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      return await res.json();
    } catch (err) {
      console.warn(`Error fetching ${endpoint}:`, err);
      return null;
    }
  }

  // Load Status & Overview
  async function loadStatus() {
    const data = await fetchJson("api/status");
    if (!data) return;

    if (elAppVersion) elAppVersion.textContent = `v${data.exporter_version || "0.2.0"}`;

    const st = (data.status || "idle").toLowerCase();
    elStatusBadge.className = `status-badge status-${st}`;
    elStatusBadge.textContent = st.replace("_", " ").toUpperCase();

    document.getElementById("ov-status").textContent = st.toUpperCase();
    document.getElementById("ov-last-attempt").textContent = formatDate(data.last_attempt_at);
    document.getElementById("ov-last-success").textContent = formatDate(data.last_success_at);
    document.getElementById("ov-last-commit").textContent = data.last_commit || "-";
    document.getElementById("ov-next-run").textContent = formatDate(data.next_run);
    document.getElementById("ov-repo").textContent = data.destination_repository || "-";
    document.getElementById("ov-branch").textContent = data.branch || "main";

    const schedText = data.schedule_enabled
      ? `Enabled (${data.schedule_time || "03:00"} ${data.schedule_timezone || "UTC"})`
      : "Disabled";
    document.getElementById("ov-schedule").textContent = schedText;
    document.getElementById("ov-secret-scan").textContent = data.secret_scan_status || "NOT_RUN";
    document.getElementById("ov-git-conn").textContent = data.git_connection_status || "untested";

    const counts = data.counts || {};
    document.getElementById("cnt-entities").textContent = counts.entities || 0;
    document.getElementById("cnt-devices").textContent = counts.devices || 0;
    document.getElementById("cnt-areas").textContent = counts.areas || 0;
    document.getElementById("cnt-labels").textContent = counts.labels || 0;
    document.getElementById("cnt-integrations").textContent = counts.integrations || 0;
    document.getElementById("cnt-automations").textContent = counts.automations || 0;
    document.getElementById("cnt-scripts").textContent = counts.scripts || 0;
    document.getElementById("cnt-helpers").textContent = counts.helpers || 0;

    const cardErr = document.getElementById("card-last-error");
    const txtErr = document.getElementById("txt-last-error");
    if (data.last_error) {
      cardErr.style.display = "block";
      txtErr.textContent = data.last_error;
    } else {
      cardErr.style.display = "none";
    }
  }

  // Load Preview
  async function loadPreview() {
    const data = await fetchJson("api/export-preview");
    const summaryEl = document.getElementById("preview-summary");
    const tbody = document.getElementById("tbl-preview-categories");
    const treeEl = document.getElementById("tree-preview-files");

    if (!data || !data.categories) {
      summaryEl.textContent = "No export preview manifest available.";
      tbody.innerHTML = '<tr><td colspan="4">No data</td></tr>';
      treeEl.textContent = "No preview file list.";
      return;
    }

    summaryEl.textContent = `Files staged: ${data.total_files || 0} | Total staged size: ${formatBytes(data.total_bytes || 0)}`;

    tbody.innerHTML = "";
    Object.keys(data.categories)
      .sort()
      .forEach((cat) => {
        const info = data.categories[cat];
        const tr = document.createElement("tr");
        tr.innerHTML = `
        <td><strong>${cat}/</strong></td>
        <td>${info.enabled ? '<span class="text-success">Enabled</span>' : '<span class="text-muted">Disabled</span>'}</td>
        <td>${info.file_count || 0} files</td>
        <td>${formatBytes(info.size_bytes || 0)}</td>
      `;
        tbody.appendChild(tr);
      });

    if (data.files && data.files.length) {
      treeEl.textContent = data.files.join("\n");
    } else {
      treeEl.textContent = "No staged files.";
    }
  }

  // Load Diagnostics
  async function loadDiagnostics() {
    const data = await fetchJson("api/diagnostics");
    const bannerEl = document.getElementById("diag-status-container");
    const wrapperEl = document.getElementById("diag-findings-wrapper");
    const tbody = document.getElementById("tbl-diag-findings");
    const omittedEl = document.getElementById("diag-omitted-msg");

    if (!data || !data.findings) {
      bannerEl.className = "diag-banner status-success";
      bannerEl.textContent = "Secret Scanner Result: PASS (No active diagnostic findings)";
      wrapperEl.style.display = "none";
      return;
    }

    bannerEl.className = "diag-banner status-blocked";
    bannerEl.textContent = `Secret Scanner Result: BLOCKED (${data.total_findings || data.findings.length} findings detected)`;
    wrapperEl.style.display = "block";

    tbody.innerHTML = "";
    const displayList = data.findings.slice(0, 25);
    displayList.forEach((f) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code>${escapeHtml(f.relative_path || "-")}</code></td>
        <td><strong class="text-error">${escapeHtml(f.rule_name || "-")}</strong></td>
        <td>${f.line_number || "-"}</td>
        <td>${formatBytes(f.size_bytes || 0)}</td>
      `;
      tbody.appendChild(tr);
    });

    if (data.total_findings > 25) {
      omittedEl.style.display = "block";
      omittedEl.textContent = `${data.total_findings - 25} additional findings omitted from the UI. Download the full safe manifest above.`;
    } else {
      omittedEl.style.display = "none";
    }
  }

  // Load Generated Output
  async function loadGeneratedOutput() {
    const data = await fetchJson("api/generated-output");
    const summaryEl = document.getElementById("output-summary");
    const tbody = document.getElementById("tbl-output-dirs");
    const treeEl = document.getElementById("tree-output-files");

    if (!data || !data.directories) {
      summaryEl.textContent = "No generated output manifest available from last successful export.";
      tbody.innerHTML = '<tr><td colspan="3">No output data</td></tr>';
      treeEl.textContent = "No output file tree.";
      return;
    }

    summaryEl.textContent = `Total files: ${data.total_files || 0} | Total size: ${formatBytes(data.total_bytes || 0)} | Last Generated: ${formatDate(data.last_generated_at)}`;

    tbody.innerHTML = "";
    Object.keys(data.directories)
      .sort()
      .forEach((d) => {
        const info = data.directories[d];
        const tr = document.createElement("tr");
        tr.innerHTML = `
        <td><strong>${d}/</strong></td>
        <td>${info.file_count || 0} files</td>
        <td>${formatBytes(info.size_bytes || 0)}</td>
      `;
        tbody.appendChild(tr);
      });

    if (data.file_list && data.file_list.length) {
      treeEl.textContent = data.file_list.join("\n");
    } else {
      treeEl.textContent = "No output files.";
    }
  }

  // Load Setup
  async function loadSetup() {
    const data = await fetchJson("api/setup");
    if (!data) return;

    document.getElementById("txt-deploy-key").value = data.public_key || "No public key generated.";
    document.getElementById("setup-repo").textContent = data.destination_repository || "-";
    document.getElementById("setup-branch").textContent = data.branch || "main";
    document.getElementById("setup-conn-status").textContent = data.connection_status || "untested";
  }

  // Run Export Now
  btnRunExport.addEventListener("click", async () => {
    btnRunExport.disabled = true;
    btnRunExport.textContent = "Exporting...";
    try {
      const res = await fetchJson("api/run-export", { method: "POST" });
      if (res && res.message) {
        alert(res.message);
      }
    } finally {
      btnRunExport.disabled = false;
      btnRunExport.textContent = "Run Export Now";
      refreshAll();
    }
  });

  // Test Git Connection
  btnTestGit.addEventListener("click", async () => {
    btnTestGit.disabled = true;
    btnTestGit.textContent = "Testing...";
    const resultEl = document.getElementById("git-test-result");
    resultEl.style.display = "none";

    try {
      const res = await fetchJson("api/test-git", { method: "POST" });
      resultEl.style.display = "block";
      if (res && res.success) {
        resultEl.className = "diag-banner status-success";
        resultEl.textContent = `GitHub Connection Success: ${res.message}`;
      } else {
        resultEl.className = "diag-banner status-error";
        resultEl.textContent = `GitHub Connection Failed: ${(res && res.message) || "Unknown error"}`;
      }
    } finally {
      btnTestGit.disabled = false;
      btnTestGit.textContent = "Test GitHub Connection";
      loadSetup();
    }
  });

  // Copy Deploy Key
  btnCopyKey.addEventListener("click", () => {
    const txt = document.getElementById("txt-deploy-key");
    txt.select();
    navigator.clipboard.writeText(txt.value).then(() => {
      btnCopyKey.textContent = "Copied!";
      setTimeout(() => {
        btnCopyKey.textContent = "Copy Deploy Key";
      }, 2000);
    });
  });

  // Refresh All
  btnRefresh.addEventListener("click", refreshAll);

  function refreshAll() {
    loadStatus();
    loadPreview();
    loadDiagnostics();
    loadGeneratedOutput();
    loadSetup();
  }

  // Utilities
  function formatDate(isoStr) {
    if (!isoStr) return "-";
    try {
      const d = new Date(isoStr);
      return d.toLocaleString();
    } catch (e) {
      return isoStr;
    }
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Initial Load
  refreshAll();
})();
