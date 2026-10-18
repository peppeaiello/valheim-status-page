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
  // World tab only when there is something to show in it
  $("tab-world").hidden = site.features.world_progress === false && !site.page.map_url;
  updateWorldEmpty();
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
  const names = sessions.map((s) => s.name);
  $("sum-players-names").textContent = names.length ? names.join(", ") : count ? `${count} online` : "nobody right now";
  const badge = $("tab-count-players");
  badge.hidden = !count;
  badge.textContent = count || "";
  badge.title = count ? `${count} online now` : "";
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
  const box = $("sum-restart-box");
  if (!live.nextRestart) {
    $("sum-restart").textContent = "–";
    $("sum-restart-sub").textContent = "no scheduled restart";
    box.classList.remove("soon");
    $("alerts").innerHTML = "";
    return;
  }
  const left = live.nextRestart - Date.now() / 1000;
  $("sum-restart").textContent = left > 0 ? "in " + fmtDuration(left) : "now";
  $("sum-restart-sub").textContent = live.restartText;
  const soon = live.online && left > 0 && left / 60 <= site.page.restart_warning_minutes;
  box.classList.toggle("soon", soon);
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

function updateWorldEmpty() {
  $("world-empty").hidden = !$("progress-panel").hidden || !$("map-panel").hidden;
}

function renderWorld(w) {
  $("progress-panel").hidden = !w;
  updateWorldEmpty();
  if (!w) return;
  $("world-day").textContent = w.day;
  $("world-saved").textContent = w.saved_at ? `last save: ${fmtAgo(Date.now() / 1000 - w.saved_at)}` : "";
  const bosses = w.bosses || [];
  const done = bosses.filter((b) => b.defeated).length;
  $("bosses-count").textContent = `${done} / ${bosses.length}`;
  setBar("bosses-bar", bosses.length ? (done / bosses.length) * 100 : 0);
  const next = bosses.find((b) => !b.defeated);
  $("sum-day").textContent = w.day;
  $("sum-bosses").textContent = `${done}/${bosses.length}`;
  setBar("sum-bosses-bar", bosses.length ? (done / bosses.length) * 100 : 0);
  $("sum-next-boss").textContent = next ? ` · next: ${next.name}` : bosses.length ? " · all defeated!" : "";
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
  if (s.world_name) $("world-name").textContent = s.world_name;
  renderWorld(s.world);
  renderBoard();
}

// ---------- Hall of Valhalla ----------
const HALL_ICONS = { valhalla: "💀", immortal: "🛡️", streak: "🔥", night: "🦉", dawn: "🐓",
  solo: "🐺", pack: "🍻", risen: "🧟", weekend: "🪓" };

function hallValue(t) {
  if (t.key === "valhalla") return `${t.value} ${t.value === 1 ? "death" : "deaths"}`;
  if (t.key === "streak") return `${t.value} days`;
  if (t.key === "risen") return `${t.value} deaths in one session`;
  return fmtPlayed(t.value);
}

function renderHall(h) {
  $("hall-panel").hidden = !(h && (h.players || []).length);
  if ($("hall-panel").hidden) return;
  const now = Date.now() / 1000;
  $("hall-small").textContent = h.since ? `since ${fmtShortDate(h.since)}` : "";
  const titles = h.titles || [];
  $("hall-titles").innerHTML = titles.length
    ? titles.map((t) => `
      <div class="title-card">
        <span class="icon" aria-hidden="true">${HALL_ICONS[t.key] || "⚔️"}</span>
        <span class="tname">${esc(t.title)}</span>
        <span class="holder">${t.names.map(esc).join(", ")}</span>
        <span class="why">${esc(t.why)} · ${esc(hallValue(t))}</span>
      </div>`).join("")
    : `<p class="empty">No titles yet: they are earned by playing.</p>`;
  const falls = h.recent || [];
  $("hall-falls").innerHTML = falls.length
    ? falls.map((f) => `<li><span class="pname">${esc(f.name)}</span> fell in battle <span class="ago">${esc(fmtAgo(now - f.at))}</span></li>`).join("")
    : `<li class="empty">Nobody has fallen so far. So far.</li>`;
  const rows = [...h.players].sort((a, b) => b.deaths - a.deaths || b.life - a.life);
  $("hall-rows").innerHTML = rows.map((p) => `
    <tr>
      <td>${esc(p.name)}${p.online ? ` <span class="on" title="Online now">●</span>` : ""}</td>
      <td>${p.deaths}</td>
      <td>${p.life >= 60 ? esc(fmtPlayed(p.life)) : "—"}</td>
      <td>${p.streak ? `${p.streak} ${p.streak === 1 ? "day" : "days"}${p.streak_now > 1 ? ` <small>(now: ${p.streak_now})</small>` : ""}` : "—"}</td>
    </tr>`).join("");
}

async function refreshHall() {
  renderHall(await getJSON("data/hall.json"));
}

// ---------- news ----------
const NEWS_SHOWN = 5;
const CHANGE_ICONS = { add: "+", remove: "−", update: "↑", game: "★" };
const TAGS = { announcement: ["Announcement", "annuncio"], mods: ["Mods", ""], settings: ["Settings", "config"], boss: ["Boss", "boss"] };
// News filters: label and the kinds they group
const NEWS_FILTERS = [
  { key: "", label: "All" },
  { key: "announcement", label: "Announcements" },
  { key: "mods", label: "Mods" },
  { key: "settings", label: "Settings" },
  { key: "boss", label: "Bosses" },
];
let newsAll = [], newsExpanded = false, newsKind = "";
const newsMatches = (n, key) => !key || n.kind === key;

function renderNewsFilters() {
  const box = $("news-filters");
  const avail = NEWS_FILTERS.filter((f) => !f.key || newsAll.some((n) => newsMatches(n, f.key)));
  if (avail.length <= 2) { box.hidden = true; newsKind = ""; return; }
  if (!avail.some((f) => f.key === newsKind)) newsKind = "";
  box.hidden = false;
  box.innerHTML = avail.map((f) => {
    const n = newsAll.filter((x) => newsMatches(x, f.key)).length;
    return `<button type="button" class="chip-btn${f.key === newsKind ? " active" : ""}" data-kind="${esc(f.key)}" aria-pressed="${f.key === newsKind}">${esc(f.label)} <span class="n">${n}</span></button>`;
  }).join("");
}

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
  const filtered = newsAll.filter((n) => newsMatches(n, newsKind));
  if (!filtered.length) { list.innerHTML = `<li class="empty">No news yet.</li>`; $("news-more").hidden = true; return; }
  const shown = newsExpanded ? filtered : filtered.slice(0, NEWS_SHOWN);
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
  $("news-more").hidden = filtered.length <= NEWS_SHOWN || newsExpanded;
}

async function refreshNews() {
  const n = await getJSON("data/news.json");
  newsAll = (n && n.entries) || [];
  renderNewsFilters();
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
    `<button type="button" class="chip-btn${t === enchType ? " active" : ""}" data-type="${esc(t)}" aria-pressed="${t === enchType}">${esc(t || "all")}</button>`).join("");
}

async function loadEnch() {
  const d = await getJSON("data/enchantments.json");
  if (!d || !(d.effects || []).length) return;
  enchAll = d.effects;
  $("ench-panel").hidden = false;
  $("tab-mods-long").textContent = "Mods & Enchantments";
  renderEnchFilters();
  renderEnch();
}

// ---------- tabs and collapsible panels ----------
// The chosen tab stays in the address (#world, #players…) and in the browser for the next visit
const TABS = ["news", "world", "players", "mods"];
const DEFAULT_TAB = "news";
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage not available */ } },
};

const tabAvailable = (name) => TABS.includes(name) && !$("tab-" + name).hidden;

function tabFromHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  return TABS.includes(h) ? h : null;
}

// scroll: "auto" brings the start of the tab into view only if the page was scrolled past the tabs,
// "always" goes there anyway (used by the summary cards)
function showTab(name, scroll) {
  if (!tabAvailable(name)) name = DEFAULT_TAB;
  for (const t of TABS) {
    const on = t === name;
    $(t).hidden = !on;
    const b = $("tab-" + t);
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1;
  }
  store.set("vsp.tab", name);
  if (scroll) {
    const top = $("tabs").getBoundingClientRect().top + window.scrollY;
    if (scroll === "always" || window.scrollY > top) window.scrollTo({ top, behavior: "auto" });
  }
}

function goTab(name, scroll) {
  if (!tabAvailable(name)) return;
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  showTab(name, scroll);
}

function initTabs() {
  $("tabs").addEventListener("click", (ev) => {
    const a = ev.target.closest("[data-tab]");
    if (!a) return;
    ev.preventDefault();
    goTab(a.dataset.tab, "auto");
  });
  $("tabs").addEventListener("keydown", (ev) => {
    if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
    const tabs = TABS.filter(tabAvailable);
    const cur = tabs.findIndex((t) => $("tab-" + t).classList.contains("active"));
    const next = tabs[(cur + (ev.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    ev.preventDefault();
    goTab(next, "auto");
    $("tab-" + next).focus();
  });
  document.querySelectorAll("[data-goto]").forEach((a) => a.addEventListener("click", (ev) => {
    ev.preventDefault();
    goTab(a.dataset.goto, "always");
  }));
  window.addEventListener("hashchange", () => { const t = tabFromHash(); if (t) showTab(t, "always"); });
  showTab(tabFromHash() || store.get("vsp.tab") || DEFAULT_TAB);

  // Long sections (mods, enchantments) can be collapsed: the state is remembered
  document.querySelectorAll("details[data-fold]").forEach((d) => {
    const key = "vsp.fold." + d.dataset.fold;
    const saved = store.get(key);
    if (saved !== null) d.open = saved === "1";
    d.addEventListener("toggle", () => store.set(key, d.open ? "1" : "0"));
  });
}

// ---------- start ----------
$("mod-search").addEventListener("input", renderMods);
$("news-more-btn").addEventListener("click", () => { newsExpanded = true; renderNews(); });
$("news-filters").addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-kind]");
  if (!b) return;
  newsKind = b.dataset.kind;
  newsExpanded = false;
  renderNewsFilters();
  renderNews();
});
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
  initTabs();
  await loadSite();
  // the World tab may have been turned off by the site settings
  if (!tabAvailable(tabFromHash() || store.get("vsp.tab") || DEFAULT_TAB)) showTab(DEFAULT_TAB);
  refreshStatus(); refreshStats(); refreshNews(); refreshHall(); loadEnch();
  setInterval(refreshStatus, site.page.refresh_seconds * 1000);
  setInterval(refreshStats, 60 * 1000);
  setInterval(refreshHall, 60 * 1000);
  setInterval(refreshNews, 2 * 60 * 1000);
  setInterval(tick, 1000);
  setInterval(renderRestart, 30 * 1000);
  setInterval(renderBoard, 15 * 1000);
})();
