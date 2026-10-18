const app = document.getElementById("app");
const inr = n => "₹" + Math.round(n).toLocaleString("en-IN");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const COLORS = ["var(--c1)", "var(--c2)", "var(--c3)"], DASH = ["", "7 4", "2 4"];

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).detail || ""; } catch (e) { /* no body */ }
    throw new Error(r.status === 404 ? "We couldn't find that product." : (typeof detail === "string" && detail) ? detail : "Something went wrong (" + r.status + ").");
  }
  return r.json();
}

/* ---------- search page ---------- */
const PRICE_STEPS = [[15000, "Under ₹15,000"], [25000, "Under ₹25,000"], [40000, "Under ₹40,000"], [60000, "Under ₹60,000"]];
const itemHtml = (p, sub) => `<li><a class="item" href="#/product/${p.id}"><span class="nm">${esc(p.name)}<span class="sub">${sub}</span></span><span class="px">${inr(p.lowest_price ?? p.current)}</span></a></li>`;

function viewSearch() {
  app.innerHTML = `<section class="hero"><h1>What are you buying?</h1>
    <p>See the price in every store, and how it has moved.</p>
    <input id="q" type="search" placeholder="Try “galaxy s24” or “redmi note”" autocomplete="off" aria-label="Search phones">
    <div class="filters"><select id="fb" aria-label="Brand"><option value="">All brands</option></select>
      <select id="fp" aria-label="Price"><option value="">Any price</option>${PRICE_STEPS.map(([v, t]) => `<option value="${v}">${t}</option>`).join("")}</select>
      <select id="fs" aria-label="Sort"><option value="name">A to Z</option><option value="price_asc">Cheapest first</option><option value="price_desc">Most expensive first</option></select></div>
    <div class="chips"><a href="#/search/galaxy">galaxy</a><a href="#/search/iphone">iphone</a><a href="#/search/redmi">redmi</a><a href="#/search/oneplus">oneplus</a></div></section>
    <section id="deals" class="deals" hidden></section>
    <p id="msg" class="msg"></p><ul id="results" class="list"></ul><div id="livebox"></div>`;
  const $ = id => document.getElementById(id);
  const q = $("q"), ul = $("results"), msg = $("msg"), deals = $("deals"), fb = $("fb"), fp = $("fp"), fs = $("fs"), livebox = $("livebox");
  let timer, ticket = 0, haveDeals = false;
  const searching = () => q.value.trim().length >= 2 || fb.value || fp.value;
  async function run() {
    const text = q.value.trim(), my = ++ticket;
    deals.hidden = !haveDeals || !!searching();
    if (!searching()) { ul.innerHTML = ""; msg.textContent = ""; return; }
    const params = new URLSearchParams();
    if (text.length >= 2) params.set("q", text);
    if (fb.value) params.set("brand", fb.value);
    if (fp.value) params.set("max_price", fp.value);
    params.set("sort", fs.value);
    try {
      const d = await api("/search?" + params);
      if (my !== ticket) return;
      const n = d.results.length;
      msg.textContent = n >= 30 ? "Showing the first 30 phones. Add a brand or lower the price to narrow it down."
        : n ? n + (n === 1 ? " phone" : " phones") : "No phones match that. Try fewer filters.";
      livebox.innerHTML = "";
      if (!n && text.length >= 3 && !fb.value && !fp.value) offerLive(text);
      ul.innerHTML = d.results.map(p => itemHtml(p, `${p.store_count} ${p.store_count === 1 ? "store" : "stores"}`)).join("");
    } catch (e) { if (my === ticket) { ul.innerHTML = ""; msg.textContent = e.message + " Is the API running?"; } }
  }
  function offerLive(text) {
    msg.innerHTML = 'Nothing in our database matches that yet. <button type="button" id="livebtn" class="btn">Check live prices online</button>';
    $("livebtn").addEventListener("click", () => runLive(text));
  }
  async function runLive(text) {
    livebox.innerHTML = `<p class="msg">Asking the stores for live prices…</p>`;
    try { const d = await api("/live-search?q=" + encodeURIComponent(text)); msg.textContent = ""; livebox.innerHTML = liveHtml(d); }
    catch (e) { livebox.innerHTML = `<p class="msg">${esc(e.message)}</p>`; }
  }
  const later = () => { clearTimeout(timer); timer = setTimeout(run, 250); };
  q.addEventListener("input", later);
  [fb, fp, fs].forEach(el => el.addEventListener("change", run));
  api("/brands").then(d => d.brands.forEach(x => fb.insertAdjacentHTML("beforeend", `<option value="${esc(x.brand)}">${esc(x.brand)} (${x.n})</option>`))).catch(() => { fb.hidden = true; });
  api("/deals").then(d => {
    if (!d.deals.length) return;
    haveDeals = true;
    deals.innerHTML = `<h2>Priced below their usual</h2><ul class="list">${d.deals.map(x => itemHtml(x, `${Math.abs(x.below_pct).toFixed(0)}% below its 90-day average, cheapest at ${esc(x.store)}`)).join("")}</ul>`;
    deals.hidden = !!searching();
  }).catch(() => {});
  return q;
}

/* ---------- product page ---------- */
function verdict(h) {
  const v = h.vs_30_day_average_pct;
  if (v == null) return "Not enough history yet to compare.";
  if (v <= -3) return Math.abs(v) + "% below its 30-day average.";
  if (v >= 3) return v + "% above its 30-day average.";
  return "About its usual price.";
}

function statsHtml(st) {
  const names = { last_30_days: "Last 30 days", last_90_days: "Last 90 days", last_365_days: "Last 365 days" };
  return Object.keys(names).map(k => {
    const s = st[k];
    return `<div class="stat"><h3>${names[k]}${s ? " (" + s.days + " days recorded)" : ""}</h3>` + (s
      ? `<dl><dt>Lowest</dt><dd>${inr(s.low)}</dd><dt>Highest</dt><dd>${inr(s.high)}</dd><dt>Average</dt><dd>${inr(s.average)}</dd></dl>`
      : `<p class="note">No data yet.</p>`) + `</div>`;
  }).join("");
}

function drawChart(series, names) {
  const slugs = [...new Set(series.flatMap(x => Object.keys(x.by_store)))].sort();
  const W = 720, H = 260, L = 8, R = 8, T = 10, B = 24;
  const vals = series.flatMap(x => Object.values(x.by_store));
  const realLo = Math.min(...vals), realHi = Math.max(...vals);
  const pad = (realHi - realLo) * 0.12 || realHi * 0.03;
  const lo = realLo - pad, hi = realHi + pad;
  const X = i => L + (series.length < 2 ? 0 : i / (series.length - 1)) * (W - L - R);
  const Y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const lines = slugs.map((s, k) => {
    let pts = [];
    series.forEach((d, i) => { if (d.by_store[s] != null) pts.push(X(i).toFixed(1) + "," + Y(d.by_store[s]).toFixed(1)); });
    return `<polyline points="${pts.join(" ")}" fill="none" stroke="${COLORS[k % 3]}" stroke-width="2.2" stroke-dasharray="${DASH[k % 3]}" stroke-linejoin="round"/>`;
  }).join("");
  const legend = slugs.map((s, k) => `<span><i style="border-color:${COLORS[k % 3]};border-top-style:${DASH[k % 3] ? "dashed" : "solid"}"></i>${esc(names[s] || s)}</span>`).join("");
  const svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Price history by store">
    <text x="${L}" y="${H - 6}" font-size="12" fill="currentColor" opacity=".7">${esc(series[0].date)}</text>
    <text x="${W - R}" y="${H - 6}" font-size="12" text-anchor="end" fill="currentColor" opacity=".7">${esc(series[series.length - 1].date)}</text>
    <text x="${L}" y="${Y(realHi) - 7}" font-size="12" fill="currentColor" opacity=".7">${inr(realHi)}</text>
    <text x="${L}" y="${Y(realLo) + 16}" font-size="12" fill="currentColor" opacity=".7">${inr(realLo)}</text>
    ${lines}<line id="guide" y1="${T}" y2="${H - B}" stroke="currentColor" stroke-opacity=".4" visibility="hidden"/></svg>`;
  return { svg, legend, slugs, X: null, W, L, R };
}

async function viewProduct(id) {
  app.innerHTML = `<p class="msg">Loading…</p>`;
  let p, h, f, mv;
  try { [p, h, f, mv] = await Promise.all([api("/products/" + id), api("/products/" + id + "/history?days=90"),
    api("/products/" + id + "/forecast").catch(() => ({ available: false, reason: "The forecast is not available right now." })),
    api("/products/" + id + "/moves").catch(() => null)]); }
  catch (e) { app.innerHTML = `<a class="back" href="#/">← Back to search</a><p class="msg">${esc(e.message)}</p>`; return; }
  const prod = p.product, best = p.cheapest;
  const names = {}; p.offers.forEach(o => names[o.store] = o.store_name);
  const byStore = {};
  p.offers.forEach(o => (byStore[o.store] = byStore[o.store] || []).push(o));
  const rows = Object.values(byStore).map(l => ({ ...l[0], extra: l.length - 1 })).sort((a, b) => a.price - b.price);
  const spec = [prod.ram_gb && prod.ram_gb + " GB RAM", prod.storage_gb && prod.storage_gb + " GB storage"].filter(Boolean).join(" · ");
  app.innerHTML = `<a class="back" href="#/">← Back to search</a>
  <div class="top">
    <div class="tag"><h1>${esc(prod.brand)} ${esc(prod.model)}</h1><p class="spec">${esc(spec)}</p>
      <div class="big">${best ? inr(best.price) : "—"}</div>
      <p class="where">${best ? "Cheapest now at " + esc(best.store_name) : "No prices yet"}</p>
      <p class="verdict">${esc(verdict(h))}</p></div>
    <div><h2>Prices today</h2><ul class="offers">${rows.map((o, i) => `<li class="offer ${i === 0 ? "best" : ""}">
      <span><strong>${esc(o.store_name)}</strong>${i === 0 ? '<span class="best-label">Cheapest</span>' : ""}<span class="t">${esc(o.title)}</span>${o.extra ? `<span class="t">+${o.extra} more ${o.extra === 1 ? "listing" : "listings"} (other colors)</span>` : ""}</span>
      <span class="px">${inr(o.price)}</span>${o.url ? `<a href="${esc(o.url)}" target="_blank" rel="noopener">View</a>` : "<span></span>"}</li>`).join("")}</ul></div>
  </div>
  ${forecastHtml(f)}
  <section class="hist"><div class="bar"><h2>Price history</h2>
    <div class="range" id="range">${[30, 90, 365].map(n => `<button data-d="${n}" aria-pressed="${n === 90}">${n} days</button>`).join("")}</div></div>
    <div class="legend" id="legend"></div><div id="readout">Move over the chart to see prices by day.</div><div id="chartbox"></div>
    <div class="stats" id="stats"></div>
    <p class="note">${esc(h.note)} Based on ${h.days_of_history} days of recorded prices.</p></section>
  ${movesHtml(mv)}`;
  document.getElementById("stats").innerHTML = statsHtml(h.stats);

  function paint(hist) {
    const box = document.getElementById("chartbox");
    if (!hist.series.length) { box.innerHTML = `<p class="msg">No history yet.</p>`; return; }
    const c = drawChart(hist.series, names);
    box.innerHTML = c.svg; document.getElementById("legend").innerHTML = c.legend;
    const svg = box.querySelector("svg"), guide = svg.querySelector("#guide"), out = document.getElementById("readout");
    function move(ev) {
      const r = svg.getBoundingClientRect(), x = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) / r.width * c.W;
      const i = Math.max(0, Math.min(hist.series.length - 1, Math.round((x - c.L) / (c.W - c.L - c.R) * (hist.series.length - 1))));
      const d = hist.series[i], gx = c.L + (hist.series.length < 2 ? 0 : i / (hist.series.length - 1)) * (c.W - c.L - c.R);
      guide.setAttribute("x1", gx); guide.setAttribute("x2", gx); guide.setAttribute("visibility", "visible");
      out.textContent = d.date + ":  " + c.slugs.filter(s => d.by_store[s] != null).map(s => (names[s] || s) + " " + inr(d.by_store[s])).join("  ·  ");
    }
    svg.addEventListener("mousemove", move); svg.addEventListener("touchmove", move);
  }
  paint(h);
  document.getElementById("range").addEventListener("click", async e => {
    const b = e.target.closest("button"); if (!b) return;
    document.querySelectorAll("#range button").forEach(x => x.setAttribute("aria-pressed", x === b));
    try { paint(await api("/products/" + id + "/history?days=" + b.dataset.d)); } catch (err) { document.getElementById("chartbox").innerHTML = `<p class="msg">${esc(err.message)}</p>`; }
  });
}


/* ---------- forecast ---------- */
function forecastHtml(f) {
  const head = `<section class="fc"><h2>Where the price may go</h2>`;
  if (!f || !f.available) return head + `<p class="note">${esc((f && f.reason) || "No forecast yet.")}</p></section>`;
  const H = f.horizons, cur = f.current;
  const lo = Math.min(cur, ...H.map(x => x.low)), hi = Math.max(cur, ...H.map(x => x.high));
  const span = (hi - lo) || 1, pct = v => 4 + (v - lo) / span * 92;
  const same = x => Math.abs(x.expected - cur) <= Math.max(150, cur * 0.005);
  const d30 = H[H.length - 1], chg = (d30.expected / cur - 1) * 100;
  let line = chg <= -3 ? `Likely to fall about ${Math.abs(chg).toFixed(0)}% over the next 30 days.`
    : chg >= 3 ? `Likely to rise about ${chg.toFixed(0)}% over the next 30 days.` : "Likely to stay about the same over the next 30 days.";
  if (Math.abs(chg) < 3) {          // say the risk in words too, not only in the bar
    const dip = d30.low < cur * 0.95, up = d30.high > cur * 1.05;
    if (dip && up) line += ` It could range from ${inr(d30.low)} to ${inr(d30.high)}.`;
    else if (dip) line += ` It could dip as low as ${inr(d30.low)}.`;
    else if (up) line += ` It could climb to ${inr(d30.high)}.`;
  }
  const rows = H.map(x => { const a = pct(x.low), b = pct(x.high);
    return `<li class="frow"><span class="fl">In ${x.days} days</span>
      <span class="fbar" role="img" aria-label="Likely range ${inr(x.low)} to ${inr(x.high)}"><span class="fr" style="left:${a}%;width:${Math.max(b - a, 1)}%"></span>${same(x) ? "" : `<span class="fd" style="left:${pct(x.expected)}%"></span>`}<span class="fnow" style="left:${pct(cur)}%"></span></span>
      <span class="ft"><strong>${same(x) ? "About the same" : inr(x.expected)}</strong><span class="sub">${inr(x.low)} to ${inr(x.high)}</span></span></li>`; }).join("");
  const held = d30.range_held_pct != null ? ` In testing, the 30-day range held about ${d30.range_held_pct}% of the time (we aim for 80%).` : "";
  return head + `<p class="verdict2">${esc(line)}</p><ul class="flist">${rows}</ul>
    <p class="note">Red line: today's price (${inr(cur)}). Dot: most likely. Bar: likely range. This is an estimate, not a promise.${held} <a href="#/accuracy">How we measure this</a></p></section>`;
}

async function viewAccuracy() {
  app.innerHTML = `<p class="msg">Loading…</p>`;
  let r; try { r = await api("/accuracy"); } catch (e) { r = { available: false }; }
  const back = `<a class="back" href="#/">← Back to search</a>`;
  if (!r.available) { app.innerHTML = back + `<h2>How accurate are we?</h2><p class="msg">No accuracy report yet.</p>`; return; }
  const rep = r.report, ks = Object.keys(rep.horizons).sort((a, b) => a - b);
  const row = k => { const x = rep.horizons[k]; return `<li class="arow"><strong>${k} days</strong>
    <span><b>${x.mae_model_pct}%</b> typical miss<span class="sub">${x.mae_naive_pct}% if we just assumed no change</span></span>
    <span><b>${x.coverage_model_pct}%</b> range held<span class="sub">we aim for 80%. Range width ${x.width_model_pct}%</span></span></li>`; };
  const ev = k => { const x = rep.horizons[k], e = x.event, n = x.no_event;
    return `<li class="arow"><strong>${k} days</strong>
      <span>${e ? `<b>${e.mae_model_pct}%</b> vs ${e.mae_naive_pct}% (no change)<span class="sub">when a sale starts or ends (${e.n} tests)</span>` : "Not enough tests"}</span>
      <span>${n ? `<b>${n.mae_model_pct}%</b> vs ${n.mae_naive_pct}% (no change)<span class="sub">in quiet periods (${n.n} tests)</span>` : "Not enough tests"}</span></li>`; };
  const total = ks.reduce((a, k) => a + rep.horizons[k].n_test, 0);
  app.innerHTML = back + `<h2>How accurate are we?</h2>
    <p class="lead">To test the forecast, we hide the last ${rep.test_days} days (from ${esc(rep.cutoff)}) from the model, ask it to predict them, then compare with what really happened. Across ${rep.products} phones that is ${total.toLocaleString("en-IN")} predictions. "Typical miss" is the average gap between the forecast and the real price.</p>
    <h3 class="sh">Overall</h3><ul class="alist">${ks.map(row).join("")}</ul>
    <h3 class="sh">Where the forecast helps</h3><ul class="alist">${ks.map(ev).join("")}</ul>
    <p class="note">The prices behind these numbers are simulated, so real-world results will differ. A forecast is only useful if it beats simply assuming the price stays put, which is why that comparison is shown.</p>`;
}


/* ---------- why the price moved ---------- */
const niceDate = iso => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
function movesHtml(mv) {
  const head = `<section class="mvs"><h2>Why the price moved</h2>`;
  if (!mv) return head + `<p class="note">This is not available right now.</p></section>`;
  if (!mv.moves.length) return head + `<p class="note">No big price moves in the last year.</p></section>`;
  const items = mv.moves.map(m => {
    const up = m.direction === "up", when = m.kind === "gradual" ? niceDate(m.start) + " to " + niceDate(m.end) : niceDate(m.start);
    const why = m.reasons.length ? m.reasons.map(r => `<div class="why"><span class="chip c-${esc(r.confidence)}">${esc(r.label)}</span><span class="ev">${esc(r.evidence)}</span><span class="conf">${r.confidence === "strong" ? "Strong match" : r.confidence === "likely" ? "Likely" : "Possible"}</span></div>`).join("")
      : `<div class="why"><span class="chip c-none">No clear reason found</span></div>`;
    return `<li class="mv"><div class="mh"><span class="mp ${up ? "up" : "down"}">${up ? "▲" : "▼"} ${Math.abs(m.change_pct).toFixed(1)}%</span>
      <span>${inr(m.start_price)} to ${inr(m.end_price)}<span class="sub">${m.kind === "gradual" ? "Gradual, " : ""}${esc(when)}</span></span></div>${why}</li>`;
  }).join("");
  return head + `<ul class="mlist">${items}</ul><p class="note">${esc(mv.note)}</p></section>`;
}


/* ---------- live search results ---------- */
function liveHtml(d) {
  if (!d.groups.length) return `<p class="msg">No store returned prices for that. Check the spelling, or try a shorter name.</p>`;
  const groups = d.groups.map(g => `<li class="lg"><div class="lh"><strong>${esc(g.name)}</strong>
      <span class="badge ${g.verified ? "ok" : "warn"}">${g.verified ? "Matched" : "Unverified match"}</span></div>
    ${g.verified ? `<a class="lk" href="#/product/${g.product_id}">Open the full page</a>` : `<span class="sub">We could not confirm these listings are the same phone. Check the titles.</span>`}
    <ul class="offers">${g.offers.map((o, i) => `<li class="offer ${i === 0 ? "best" : ""}"><span><strong>${esc(o.store_name)}</strong>${i === 0 ? '<span class="best-label">Cheapest</span>' : ""}<span class="t">${esc(o.title)}</span></span>
      <span class="px">${inr(o.price)}</span>${o.url ? `<a href="${esc(o.url)}" target="_blank" rel="noopener">View</a>` : "<span></span>"}</li>`).join("")}</ul></li>`).join("");
  return `<p class="note live-note">Live prices from ${esc(d.source)}${d.cached ? " (saved a few minutes ago)" : ""}. We have started tracking these phones, so their price history builds from today.</p><ul class="lgs">${groups}</ul>`;
}

/* ---------- routing ---------- */
function route() {
  const hash = location.hash || "#/";
  if (hash === "#/accuracy") { viewAccuracy(); window.scrollTo(0, 0); return; }
  let m;
  if ((m = hash.match(/^#\/product\/(\d+)$/))) { viewProduct(m[1]); window.scrollTo(0, 0); return; }
  const q = viewSearch();
  if ((m = hash.match(/^#\/search\/(.+)$/))) { q.value = decodeURIComponent(m[1]); q.dispatchEvent(new Event("input")); }
  else q.focus();
}
window.addEventListener("hashchange", route);
route();
