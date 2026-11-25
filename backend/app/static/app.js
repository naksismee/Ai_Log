const $ = (id) => document.getElementById(id);

function fmtTs(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

function pill(sev) {
  const cls =
    sev === "HIGH" ? "pill high" : sev === "MEDIUM" ? "pill medium" : "pill low";
  return `<span class="${cls}">${sev}</span>`;
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const ct = res.headers.get("content-type") || "";
  const payload = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = payload?.detail || payload?.message || (typeof payload === "string" ? payload : "Request failed");
    throw new Error(msg);
  }
  return payload;
}

async function refreshHealth() {
  try {
    const health = await api("/health");
    const demo = health.mode === "demo";
    $("healthStatus").textContent = demo ? "Demo: local keyword vectors" : "Semantic analysis ready";
    if (demo) {
      $("uploadHint").textContent = "Demo mode uses local keyword vectors, with no model download or API key. Try the sample log to explore the workflow.";
      $("modelInput").value = "demo-keyword-vectors";
      $("modelInput").disabled = true;
      $("alertInput").checked = false;
    }
    $("healthStatus").classList.remove("bad");
    $("healthStatus").classList.add("ok");
  } catch {
    $("healthStatus").textContent = "API: unreachable";
    $("healthStatus").classList.remove("ok");
    $("healthStatus").classList.add("bad");
  }
}

function renderClusters(result) {
  $("resultMeta").textContent =
    `${result.filename || "upload"} • ${result.issues_found} issue lines • ` +
    `${result.clusters.length} clusters • threshold ${result.threshold}`;

  $("overallSummary").textContent = result.summary || "";

  const body = $("clustersBody");
  if (!result.clusters?.length) {
    body.innerHTML = `<tr><td colspan="5" class="empty">No ERROR/WARNING clusters found.</td></tr>`;
    return;
  }
  body.innerHTML = result.clusters
    .map((c) => {
      const known = c.known_issue
        ? `#${c.known_issue.issue_id} (${(c.known_issue.score * 100).toFixed(1)}%)`
        : "—";
      const expl = c.ai_explanation ? esc(c.ai_explanation) : "—";
      return `
        <tr>
          <td class="mono">${c.cluster_id}</td>
          <td>${pill(c.severity)}</td>
          <td class="mono">${c.count}</td>
          <td>
            <div class="mono">${esc(c.representative)}</div>
            <div class="itemSub">${esc(c.summary || "")}</div>
            <details class="details">
              <summary>AI explanation</summary>
              <pre class="pre">${expl}</pre>
            </details>
          </td>
          <td class="mono">${esc(known)}</td>
        </tr>
      `;
    })
    .join("");
}

async function refreshKnownIssues() {
  const wrap = $("knownIssuesList");
  wrap.innerHTML = `<div class="item"><div class="itemSub">Loading…</div></div>`;
  try {
    const data = await api("/known-issues?limit=50");
    const items = data.items || [];
    if (!items.length) {
      wrap.innerHTML = `<div class="item"><div class="itemSub">No known issues stored yet.</div></div>`;
      return;
    }
    wrap.innerHTML = items
      .map(
        (x) => `
        <div class="item">
          <div class="itemTitle">
            <div class="mono">#${x.id}</div>
            <div class="pill">${x.occurrences}×</div>
          </div>
          <div class="itemSub mono">${esc(x.representative)}</div>
          <div class="itemSub">Last seen: ${fmtTs(x.last_seen_ts)}</div>
        </div>`
      )
      .join("");
  } catch (e) {
    wrap.innerHTML = `<div class="item"><div class="itemSub">Error: ${esc(e.message)}</div></div>`;
  }
}

async function refreshRuns() {
  const wrap = $("runsList");
  wrap.innerHTML = `<div class="item"><div class="itemSub">Loading…</div></div>`;
  try {
    const data = await api("/recent-runs?limit=20");
    const items = data.items || [];
    if (!items.length) {
      wrap.innerHTML = `<div class="item"><div class="itemSub">No stored runs yet. Scheduler will create them, or use /analyze-path.</div></div>`;
      return;
    }
    wrap.innerHTML = items
      .map(
        (r) => `
        <div class="item">
          <div class="itemTitle">
            <div class="mono"><span class="link" data-run="${r.id}">Run #${r.id}</span> • ${esc(r.source_name || "unknown")}</div>
            <div class="pill">${r.issues_found} issues</div>
          </div>
          <div class="itemSub">${fmtTs(r.analyzed_ts)} • threshold ${r.threshold} • model ${esc(r.model_name)}</div>
          <div class="itemSub">${esc(r.summary || "")}</div>
        </div>`
      )
      .join("");

    wrap.querySelectorAll("[data-run]").forEach((el) => {
      el.addEventListener("click", async () => {
        const runId = el.getAttribute("data-run");
        const run = await api(`/runs/${runId}`);
        renderClusters({
          filename: run.source_name,
          total_lines: run.total_lines,
          issues_found: run.issues_found,
          threshold: run.threshold,
          model_name: run.model_name,
          summary: run.summary,
          clusters: run.clusters || [],
        });
      });
    });
  } catch (e) {
    wrap.innerHTML = `<div class="item"><div class="itemSub">Error: ${esc(e.message)}</div></div>`;
  }
}

async function onUploadSubmit(ev) {
  ev.preventDefault();
  const file = $("fileInput").files?.[0];
  if (file) await analyzeFile(file);
}

async function analyzeFile(f) {
  const threshold = Number($("thresholdInput").value || "0.8");
  const model = $("modelInput").value || "all-MiniLM-L6-v2";
  const remember = $("rememberInput").checked ? "true" : "false";
  const alert = $("alertInput").checked ? "true" : "false";

  const form = new FormData();
  form.append("file", f);

  $("footerNote").textContent = "Analyzing…";
  try {
    const res = await api(
      `/analyze-log?threshold=${encodeURIComponent(threshold)}&model_name=${encodeURIComponent(
        model
      )}&remember=${remember}&alert=${alert}`,
      { method: "POST", body: form }
    );
    renderClusters(res);
    $("footerNote").textContent = "Done.";
    await refreshKnownIssues();
    await refreshRuns();
  } catch (e) {
    $("footerNote").textContent = `Error: ${e.message}`;
  }
}

async function onClearKnownIssues() {
  $("footerNote").textContent = "Clearing known issues…";
  try {
    await api("/known-issues", { method: "DELETE" });
    $("footerNote").textContent = "Known issues cleared.";
    await refreshKnownIssues();
  } catch (e) {
    $("footerNote").textContent = `Error: ${e.message}`;
  }
}

async function init() {
  $("uploadForm").addEventListener("submit", onUploadSubmit);
  $("clearBtn").addEventListener("click", onClearKnownIssues);
  $("sampleBtn").addEventListener("click", async () => {
    $("sampleBtn").disabled = true;
    try {
      const response = await fetch("/sample-log");
      if (!response.ok) throw new Error("Could not load the sample log.");
      const file = new File([await response.blob()], "recruiter.log", { type: "text/plain" });
      await analyzeFile(file);
    } catch (error) {
      $("footerNote").textContent = error.message;
    } finally { $("sampleBtn").disabled = false; }
  });
  $("searchForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const q = $("searchInput").value || "";
    const wrap = $("searchResults");
    wrap.innerHTML = `<div class="item"><div class="itemSub">Searching…</div></div>`;
    try {
      const data = await api(`/semantic-search?q=${encodeURIComponent(q)}&k=8`);
      const hits = data.hits || [];
      if (!hits.length) {
        wrap.innerHTML = `<div class="item"><div class="itemSub">No matches.</div></div>`;
        return;
      }
      wrap.innerHTML = hits
        .map(
          (h) => `
          <div class="item">
            <div class="itemTitle">
              <div class="mono">${esc(h.id)}</div>
              <div class="pill">${(h.score * 100).toFixed(1)}%</div>
            </div>
            <div class="itemSub mono">${esc(h.document || "")}</div>
            <div class="itemSub">meta: <span class="mono">${esc(JSON.stringify(h.metadata || {}))}</span></div>
          </div>`
        )
        .join("");
    } catch (e) {
      wrap.innerHTML = `<div class="item"><div class="itemSub">Error: ${esc(e.message)}</div></div>`;
    }
  });
  await refreshHealth();
  await refreshKnownIssues();
  await refreshRuns();
}

init();

