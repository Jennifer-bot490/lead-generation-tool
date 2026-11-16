// Front-end logic. Scraping happens on the server; this page just starts a job and polls it.
const $ = (id) => document.getElementById(id);
const COLS = ["name", "phone", "email", "website", "address", "city", "category", "source"];
const HKEY = "leadscout_history";
let results = [], visible = [];

const toast = (msg, type = "ok") => {
  const t = Object.assign(document.createElement("div"), { className: `toast ${type}`, textContent: msg });
  $("toasts").appendChild(t); setTimeout(() => t.remove(), 5000);
};
const has = (v) => v && v !== "N/A";
const getHistory = () => { try { return JSON.parse(localStorage.getItem(HKEY)) || []; } catch { return []; } };
const setHistory = (h) => { try { localStorage.setItem(HKEY, JSON.stringify(h.slice(0, 30))); } catch {} };

function renderHistory() {
  const h = getHistory(), ul = $("historyList");
  ul.innerHTML = "";
  if (!h.length) ul.innerHTML = '<li class="muted">No searches yet.</li>';
  h.forEach((e) => {
    const li = document.createElement("li");
    li.textContent = `${e.keyword} · ${e.location} · ${e.count} found · ${e.time}`;
    li.onclick = () => { $("keyword").value = e.keyword; $("location").value = e.location; location.hash = "search"; };
    ul.appendChild(li);
  });
  $("allTime").textContent = h.reduce((s, e) => s + e.count, 0);
}

function td(text, cls) {
  const c = document.createElement("td");
  c.textContent = text; if (!has(text)) c.className = "na"; if (cls) c.classList.add(cls);
  return c;
}

function render() {
  const q = $("filter").value.toLowerCase();
  visible = results.filter((r) =>
    (!q || COLS.some((c) => String(r[c]).toLowerCase().includes(q))) &&
    (!$("onlyPhone").checked || has(r.phone)) && (!$("onlyEmail").checked || has(r.email)));
  const tb = $("tbody"); tb.innerHTML = "";
  if (!visible.length) tb.innerHTML = `<tr><td colspan="9" class="empty">${results.length ? "No rows match your filter." : "Run a search to see leads here."}</td></tr>`;
  visible.forEach((r, i) => {
    const tr = document.createElement("tr");
    tr.appendChild(td(i + 1));
    COLS.forEach((c) => {
      if (c === "website" && /^https?:\/\//i.test(r[c])) {
        const cell = document.createElement("td"), a = document.createElement("a");
        a.href = r[c]; a.target = "_blank"; a.rel = "noopener noreferrer";
        a.textContent = r[c].replace(/^https?:\/\/(www\.)?/i, "").replace(/\/$/, "");
        cell.appendChild(a); tr.appendChild(cell);
      } else tr.appendChild(td(r[c]));
    });
    tb.appendChild(tr);
  });
  $("total").textContent = results.length;
  $("withPhone").textContent = results.filter((r) => has(r.phone)).length;
  $("withEmail").textContent = results.filter((r) => has(r.email)).length;
  $("shown").textContent = results.length ? `(${visible.length} shown)` : "";
  $("csvBtn").disabled = $("xlsxBtn").disabled = !visible.length;
}

async function poll(jobId, entry) {
  const res = await fetch(`/api/jobs/${jobId}`), job = await res.json();
  if (!res.ok) throw new Error(job.error);
  if (job.status === "running") {
    $("loaderMsg").textContent = job.message;
    return new Promise((ok) => setTimeout(() => ok(poll(jobId, entry)), 1500));
  }
  if (job.status === "error") throw new Error(job.error);
  results = job.results; render();
  setHistory([{ ...entry, count: results.length, time: new Date().toLocaleString() }, ...getHistory()]);
  renderHistory();
  (job.warnings || []).forEach((w) => toast(w, "err"));
  toast(job.message); location.hash = "results";
}

$("searchForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const entry = { keyword: $("keyword").value.trim(), location: $("location").value.trim() };
  $("searchBtn").disabled = true; $("loader").hidden = false; $("loaderMsg").textContent = "Starting…";
  try {
    const res = await fetch("/api/search", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...entry, source: $("source").value, limit: $("limit").value, enrich: $("enrich").checked }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Search failed.");
    await poll(data.job_id, entry);
  } catch (err) { toast(err.message, "err"); }
  finally { $("loader").hidden = true; $("searchBtn").disabled = false; }
});

async function exportFile(fmt) {
  try {
    const res = await fetch(`/api/export/${fmt}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ results: visible }),
    });
    if (!res.ok) throw new Error((await res.json()).error || "Export failed.");
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: `leads.${fmt}` });
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    toast(`${fmt.toUpperCase()} downloaded (${visible.length} rows).`);
  } catch (err) { toast(err.message, "err"); }
}

$("csvBtn").onclick = () => exportFile("csv");
$("xlsxBtn").onclick = () => exportFile("xlsx");
["filter", "onlyPhone", "onlyEmail"].forEach((id) => $(id).addEventListener("input", render));
$("clearHistory").onclick = () => { setHistory([]); renderHistory(); };
$("menuBtn").onclick = () => $("sidebar").classList.toggle("open");
document.querySelectorAll(".sidebar a").forEach((a) => a.addEventListener("click", () => {
  document.querySelectorAll(".sidebar a").forEach((x) => x.classList.remove("active"));
  a.classList.add("active"); $("sidebar").classList.remove("open");
}));

fetch("/api/sources").then((r) => r.json()).then((d) => {
  const sel = $("source");
  if (d.sources.length > 1) sel.innerHTML = '<option value="all">All permitted sources</option>';
  d.sources.forEach((s) => sel.add(new Option(s.label, s.key)));
});
renderHistory(); render();
