// valheim-status-page: reads the JSON files written by the worker in data/
const $ = (id) => document.getElementById(id);
const site = { page: { refresh_seconds: 15, restart_warning_minutes: 30 }, features: {} };
const live = { online: false, sessions: [], nextRestart: null, restartText: "" };
let allMods = [];

// ---------- helpers ----------
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function prettyName(name) {
  return String(name).replace(/[_-]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/\b\w/g, (c) => c.toUpperCase());
}

// "2 d 3 h", "1 h 20 min", "5 min", "less than a minute"
function fmtDuration(sec) {
  sec = Math.max(0, Math.floor(sec));
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  if (d) return `${d} d ${h} h`;
  if (h) return `${h} h ${m} min`;
  if (m) return `${m} min`;
  return "less than a minute";
}

// Play time in hours: "27 h 5 min", "45 min"
function fmtPlayed(sec) {
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  if (h) return `${h} h ${m} min`;
  return m ? `${m} min` : "less than a minute";
}

function fmtAgo(sec) {
  sec = Math.max(0, sec);
  if (sec < 90) return "just now";
  if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} h ago`;
  const d = Math.floor(sec / 86400);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

const fmtShortDate = (ts) => new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });

function setBar(id, pct) {
  $(id).style.width = `${Math.max(0, Math.min(100, pct))}%`;
}

async function getJSON(path) {
  try {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) return null;
    if (!(r.headers.get("content-type") || "").includes("json")) return null;
    return await r.json();
  } catch (e) { return null; }
}

// ---------- site settings ----------
async function loadSite() {
  const s = await getJSON("data/site.json");
  if (!s) return;
  Object.assign(site.page, s.page || {});
  site.features = s.features || {};
  if (site.page.subtitle) $("subtitle").textContent = site.page.subtitle;
  if (site.page.join_hint) { $("join-hint").textContent = site.page.join_hint; $("join-hint").hidden = false; }
  if (site.page.map_url) {
    $("map-frame").src = site.page.map_url;
    $("map-link").href = site.page.map_url;
    $("map-panel").hidden = false;
  }
}

// ---------- live status ----------
function setOnline(online, reachable) {
  const pill = $("pill");
  pill.classList.toggle("online", online);
  pill.classList.toggle("offline", !online);
  $("pill-text").textContent = online ? "Online" : reachable ? "Offline" : "Offline or starting";
}

function renderPlayers(count, max, sessions) {
  $("players-count").textContent = `${count} / ${max || "–"}`;
  setBar("players-bar", max ? (count / max) * 100 : 0);
  $("players-small").textContent = count ? (count === 1 ? "1 online" : `${count} online`) : "";
  $("players-list").innerHTML = sessions.length
    ? sessions.map((s) => `
        <li><span class="avatar">${esc(String(s.name).charAt(0).toUpperCase())}</span>
          <span class="who">${esc(s.name)}<small data-joined-for="${esc(s.name)}"></small></span></li>`).join("")
    : count > 0 ? `<li class="empty">${count} players online</li>` : `<li class="empty">Nobody right now. The world awaits…</li>`;
}

function renderMods() {
  const q = $("mod-search").value.trim().toLowerCase();
  const shown = allMods.filter((m) => !q || m.name.toLowerCase().includes(q) || prettyName(m.name).toLowerCase().includes(q));
  $("mods-list").innerHTML = shown.length
    ? shown.map((m) => `<li><span class="name" title="${esc(m.name)}">${esc(prettyName(m.name))}</span><span class="ver">${esc(m.version)}</span></li>`).join("")
    : `<li class="empty">No mod found</li>`;
}

function renderRestart() {
  const box = $("jobs");
  if (!live.nextRestart) { box.hidden = true; $("alerts").innerHTML = ""; return; }
  box.hidden = false;
  const left = live.nextRestart - Date.now() / 1000;
  $("jobs-list").innerHTML = `
    <div class="job">
      <div class="row"><span class="title">${esc(live.restartText)}</span><span class="next">${left > 0 ? "in " + esc(fmtDuration(left)) : ""}</span></div>
      <div class="meta"><span>The server is offline for a few minutes during the restart.</span></div>
    </div>`;
  const soon = live.online && left > 0 && left / 60 <= site.page.restart_warning_minutes;
  $("alerts").innerHTML = soon
    ? `<div class="alert warn">🔄 Scheduled restart in ${esc(fmtDuration(left))}: save and find a safe spot!</div>`
    : "";
}

function tick() {
  const now = Date.now() / 1000;
  for (const s of live.sessions) {
    const el = document.querySelector(`[data-joined-for="${CSS.escape(s.name)}"]`);
    if (el && s.joined_at) el.textContent = `online for ${fmtDuration(now - s.joined_at)}`;
  }
}

async function refreshStatus() {
  const s = await getJSON("data/status.json");
  const stale = !s || Date.now() / 1000 - (s.updated_at || 0) > 120;
  if (!s || stale) {
    live.online = false;
    setOnline(false, false);
    $("updated").textContent = `No fresh data from the server (${new Date().toLocaleTimeString()}). Retrying…`;
    return;
  }
  live.online = !!s.online;
  setOnline(live.online, s.reachable);
  const name = site.page.title || s.name;
  if (name) { $("server-name").textContent = name; document.title = `${name} · Server status`; }
  $("version").textContent = s.version || "–";
  live.sessions = s.sessions || [];
  renderPlayers(s.players || 0, s.max_players || 0, live.sessions);
  allMods = s.mods || [];
  $("mods-count").textContent = allMods.length;
  $("mods-small").textContent = allMods.length ? `${allMods.length} in total` : "";
  renderMods();
  live.nextRestart = s.next_restart;
  live.restartText = s.restart_text || "";
  renderRestart();
  tick();
  $("updated").textContent = `Updated at ${new Date().toLocaleTimeString()} · refreshes every ${site.page.refresh_seconds} seconds`;
}

// ---------- world progression and leaderboard ----------
let stats = null;

function bossWhen(b) {
  if (b.day_to == null) return "";
  const day = b.day_from == null ? `By day ${b.day_to}` : b.day_to - b.day_from <= 0 ? `Day ${b.day_to}` : `Day ${b.day_from}–${b.day_to}`;
  const tip = "The game does not record the exact moment: this is worked out from the server saves";
  return `<span class="when" title="${esc(tip)}">${esc(day)}${b.at ? `<small>${esc(fmtShortDate(b.at))}</small>` : ""}</span>`;
}

function renderWorld(w) {
  $("progress-panel").hidden = !w;
  if (!w) return;
  $("world-day").textContent = w.day;
  $("world-saved").textContent = w.saved_at ? `last save: ${fmtAgo(Date.now() / 1000 - w.saved_at)}` : "";
  const bosses = w.bosses || [];
  const done = bosses.filter((b) => b.defeated).length;
  $("bosses-count").textContent = `${done} / ${bosses.length}`;
  setBar("bosses-bar", bosses.length ? (done / bosses.length) * 100 : 0);
  const next = bosses.find((b) => !b.defeated);
  $("next-boss").innerHTML = next
    ? `Next target: <strong>${esc(next.name)}</strong>${next.biome ? ` · ${esc(next.biome)}` : ""}`
    : "All bosses defeated. Skål!";
  $("bosses-list").innerHTML = bosses.map((b, i) => {
    const cls = b.defeated ? "done" : b === next ? "next" : "locked";
    const label = b.defeated ? "✓ Defeated" : b === next ? "Next" : "Ahead";
    return `<li class="boss ${cls}"><span class="num">${i + 1}</span><span class="boss-name">${esc(b.name)}</span>
      <span class="biome">${esc(b.biome || "")}</span><span class="state">${label}</span>${b.defeated ? bossWhen(b) : ""}</li>`;
  }).join("");
  const ms = w.milestones || [];
  $("milestones").innerHTML = ms.length ? `<span class="label">Milestones</span>${ms.map((m) => `<span class="chip">${esc(m)}</span>`).join("")}` : "";
}

function renderBoard() {
  const lb = stats && stats.leaderboard;
  $("board-panel").hidden = !(lb && (lb.players || []).length);
  if ($("board-panel").hidden) return;
  const now = Date.now() / 1000;
  const rows = lb.players.map((p) => ({ ...p, played: p.total + (p.online_since ? Math.max(0, now - p.online_since) : 0) }))
    .sort((a, b) => b.played - a.played);
  const top = rows[0].played || 1;
  const total = rows.reduce((t, p) => t + p.played, 0);
  $("board-small").textContent = lb.since ? `since ${fmtShortDate(lb.since)}` : "";
  const peak = lb.peak && lb.peak.count
    ? `<div class="record"><span class="label">Most online</span><span class="value">${lb.peak.count}</span><span class="sub">${lb.peak.at ? esc(fmtShortDate(lb.peak.at)) : ""}</span></div>` : "";
  $("records").innerHTML = `
    <div class="record"><span class="label">Total play time</span><span class="value">${esc(fmtPlayed(total))}</span><span class="sub">everyone together</span></div>
    <div class="record"><span class="label">Vikings</span><span class="value">${rows.length}</span><span class="sub">have played here</span></div>${peak}`;
  $("board-list").innerHTML = rows.map((p, i) => {
    const seen = p.online_since ? `<span class="on">● online now</span>` : `seen ${esc(fmtAgo(now - p.last_seen))}`;
    const sessions = p.sessions + (p.online_since ? 1 : 0);
    return `<li><span class="rank">${["🥇", "🥈", "🥉"][i] || i + 1}</span>
      <span class="avatar">${esc(String(p.name).charAt(0).toUpperCase())}</span>
      <div class="who">
        <div class="top"><span class="pname">${esc(p.name)}</span><span class="hours">${esc(fmtPlayed(p.played))}</span></div>
        <div class="bar"><span style="width:${Math.max(2, (p.played / top) * 100)}%"></span></div>
        <div class="meta"><span>${seen}</span><span>${sessions} ${sessions === 1 ? "session" : "sessions"}${p.longest >= 60 ? ` · best ${esc(fmtPlayed(p.longest))}` : ""}</span></div>
      </div></li>`;
  }).join("");
}

async function refreshStats() {
  const s = await getJSON("data/stats.json");
  if (!s) return;
  stats = s;
  if (s.world_name) $("world").textContent = s.world_name;
  renderWorld(s.world);
  renderBoard();
}

// ---------- news ----------
const NEWS_SHOWN = 5;
const CHANGE_ICONS = { add: "+", remove: "−", update: "↑", game: "★" };
const TAGS = { announcement: ["Announcement", "annuncio"], mods: ["Mods", ""], settings: ["Settings", "config"], boss: ["Boss", "boss"] };
let newsAll = [], newsExpanded = false;

// Announcement text: blank-line separated blocks, "Title:" first line, "- " bullet lines
function formatText(text) {
  return String(text).replace(/\r/g, "").split(/\n\s*\n/).map((chunk) => {
    const lines = chunk.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!lines.length) return "";
    let html = "";
    if (lines.length > 1 && lines[0].endsWith(":")) html += `<div class="news-sub">${esc(lines.shift().slice(0, -1))}</div>`;
    let list = [];
    const flush = () => { if (list.length) { html += `<ul class="news-points">${list.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`; list = []; } };
    for (const l of lines) {
      if (l.startsWith("- ")) list.push(l.slice(2));
      else { flush(); html += `<p>${esc(l)}</p>`; }
    }
    flush();
    return `<div class="news-block">${html}</div>`;
  }).join("");
}

function renderNews() {
  const list = $("news-list");
  if (!newsAll.length) { list.innerHTML = `<li class="empty">No news yet.</li>`; $("news-more").hidden = true; return; }
  const shown = newsExpanded ? newsAll : newsAll.slice(0, NEWS_SHOWN);
  list.innerHTML = shown.map((n) => {
    const d = new Date(n.date);
    const day = d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
    const rest = d.toLocaleDateString(undefined, { year: "numeric" }) + (n.date_only ? "" : " · " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    const [tagText, tagClass] = TAGS[n.kind] || ["", ""];
    const tag = tagText ? `<span class="tag ${tagClass}">${tagText}</span>` : "";
    const items = (n.items || []).map((it) => `<li class="${esc(it.type)}"><span class="ic">${CHANGE_ICONS[it.type] || "•"}</span><span>${esc(it.text)}</span></li>`).join("");
    return `<li class="news-item">
      <div class="news-date"><strong>${esc(day)}</strong>${esc(rest)}</div>
      <div><div class="news-title">${esc(n.title)} ${tag}</div>${n.text ? `<div class="news-text">${formatText(n.text)}</div>` : ""}${items ? `<ul class="changes">${items}</ul>` : ""}</div>
    </li>`;
  }).join("");
  $("news-more").hidden = newsAll.length <= NEWS_SHOWN || newsExpanded;
}

async function refreshNews() {
  const n = await getJSON("data/news.json");
  newsAll = (n && n.entries) || [];
  renderNews();
}

// ---------- EpicLoot enchantments ----------
const ENCH_SHOWN = 12;
const ENCH_TYPES = ["one-handed weapons", "two-handed weapons", "bows", "crossbows", "staffs", "torches", "tools",
  "helmets", "chest armor", "leg armor", "capes", "shields", "belts & rings", "trinkets"];
let enchAll = [], enchType = "", enchExpanded = false;

function renderEnch() {
  const q = $("ench-search").value.trim().toLowerCase();
  const shown = enchAll.filter((e) => (!enchType || !e.types.length || e.types.includes(enchType)) &&
    (!q || e.name.toLowerCase().includes(q) || e.desc.toLowerCase().includes(q)));
  const list = q || enchExpanded ? shown : shown.slice(0, ENCH_SHOWN);
  $("ench-small").textContent = `${shown.length} of ${enchAll.length}`;
  $("ench-list").innerHTML = list.length ? list.map((e) => `
    <li><div class="ench-name">${esc(e.name)}</div><div class="ench-desc">${esc(e.desc)}</div>
      <div class="ench-meta"><span>${esc((e.where || []).join(", "))}</span>${e.rarity.length ? `<span class="ench-rar">${esc(e.rarity.join(" / "))} only</span>` : ""}</div></li>`).join("")
    : `<li class="empty">No enchantment found</li>`;
  $("ench-more").hidden = !!q || enchExpanded || shown.length <= ENCH_SHOWN;
}

function renderEnchFilters() {
  $("ench-filters").innerHTML = ["", ...ENCH_TYPES].map((t) =>
    `<button type="button" class="chip-btn${t === enchType ? " active" : ""}" data-type="${esc(t)}">${esc(t || "all")}</button>`).join("");
}

async function loadEnch() {
  const d = await getJSON("data/enchantments.json");
  if (!d || !(d.effects || []).length) return;
  enchAll = d.effects;
  $("ench-panel").hidden = false;
  renderEnchFilters();
  renderEnch();
}

// ---------- start ----------
$("mod-search").addEventListener("input", renderMods);
$("news-more-btn").addEventListener("click", () => { newsExpanded = true; renderNews(); });
$("ench-search").addEventListener("input", renderEnch);
$("ench-more-btn").addEventListener("click", () => { enchExpanded = true; renderEnch(); });
$("ench-filters").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-type]");
  if (!b) return;
  enchType = b.dataset.type;
  renderEnchFilters();
  renderEnch();
});

(async () => {
  await loadSite();
  refreshStatus(); refreshStats(); refreshNews(); loadEnch();
  setInterval(refreshStatus, site.page.refresh_seconds * 1000);
  setInterval(refreshStats, 60 * 1000);
  setInterval(refreshNews, 2 * 60 * 1000);
  setInterval(tick, 1000);
  setInterval(renderRestart, 30 * 1000);
  setInterval(renderBoard, 15 * 1000);
})();
