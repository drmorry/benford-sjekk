"use strict";

const $ = (s) => document.querySelector(s);
const DIGITS = [1, 2, 3, 4, 5, 6, 7, 8, 9];
const EXPECTED = DIGITS.map((d) => Math.log10(1 + 1 / d));
const fmtPct = (x, dec = 1) => (x * 100).toLocaleString("nb-NO", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + " %";
const fmtNum = (x, dec = 0) => x.toLocaleString("nb-NO", { minimumFractionDigits: dec, maximumFractionDigits: dec });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

let data = null; // last server response
let included = new Set();
let exLimit = 100;

// ---------------------------------------------------------------- input UI

document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", t === tab);
      t.setAttribute("aria-selected", t === tab);
    });
    document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.dataset.panel !== tab.dataset.tab));
  })
);

const fileInput = $("#pdf-file");
const drop = $("#drop");
function showFiles() {
  const files = [...fileInput.files];
  $("#file-names").textContent = files.length ? files.map((f) => f.name).join(", ") : "Flere filer analyseres samlet";
  $("#pdf-go").disabled = !files.length;
}
fileInput.addEventListener("change", showFiles);
["dragenter", "dragover"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); })
);
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("over")));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  const pdfs = [...e.dataTransfer.files].filter((f) => f.type === "application/pdf" || /\.pdf$/i.test(f.name));
  if (!pdfs.length) return setStatus("Bare PDF-filer støttes.", true);
  const dt = new DataTransfer();
  pdfs.forEach((f) => dt.items.add(f));
  fileInput.files = dt.files;
  showFiles();
});

function extractOptions() {
  return { drop_repeated: $("#drop-repeated").checked, space_thousands: $("#space-thousands").checked };
}

function setStatus(msg, isError = false, busy = false) {
  const el = $("#status");
  el.className = "status" + (isError ? " error" : "");
  el.innerHTML = (busy ? '<span class="spinner"></span>' : "") + esc(msg);
}

async function run(promise, busyMsg) {
  setStatus(busyMsg, false, true);
  document.querySelectorAll("button.primary").forEach((b) => (b.dataset.wasDisabled = b.disabled, b.disabled = true));
  const t0 = performance.now();
  try {
    const res = await promise;
    const body = await res.json().catch(() => ({ error: `Serveren svarte ${res.status}` }));
    if (!res.ok || body.error) throw new Error(body.error || `Serveren svarte ${res.status}`);
    data = body;
    included = new Set(data.categories.filter((c) => c.included).map((c) => c.key));
    exLimit = 100;
    renderAll();
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    setStatus(`Ferdig på ${secs} s – ${fmtNum(data.numbers.length)} tall funnet.` + (data.truncated ? " (Listen er avkortet.)" : ""));
    $("#results").hidden = false;
    $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    document.querySelectorAll("button.primary").forEach((b) => (b.disabled = b.dataset.wasDisabled === "true"));
  }
}

$("#pdf-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const fd = new FormData();
  [...fileInput.files].forEach((f) => fd.append("file", f));
  fd.append("options", JSON.stringify(extractOptions()));
  run(fetch("/api/pdf", { method: "POST", body: fd }), "Leser PDF og finner tall …");
});

$("#url-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const body = {
    url: $("#url").value,
    max_depth: +$("#max-depth").value,
    max_pages: +$("#max-pages").value,
    same_site: $("#same-site").checked,
    include_pdfs: $("#include-pdfs").checked,
    strip_boilerplate: $("#strip-boilerplate").checked,
    respect_robots: $("#respect-robots").checked,
    ...extractOptions(),
  };
  run(
    fetch("/api/url", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    `Skanner inntil ${body.max_pages} sider, ${body.max_depth} nivå(er) ut … dette kan ta litt tid.`
  );
});

// ---------------------------------------------------------------- statistics

// Upper tail of the chi-square distribution with 8 degrees of freedom
// (closed form for even df).
function chi2pDf8(x) {
  const h = x / 2;
  let term = 1, sum = 1;
  for (let k = 1; k <= 3; k++) { term *= h / k; sum += term; }
  return Math.exp(-h) * sum;
}

function analysedNumbers() {
  const keys = data.categories.map((c) => c.key);
  const unique = $("#unique-only").checked;
  const seen = new Set();
  const out = [];
  for (const n of data.numbers) {
    if (n[0] === 0 || !included.has(keys[n[1]])) continue;
    if (unique) {
      const k = n[3].replace(/\s/g, "");
      if (seen.has(k)) continue;
      seen.add(k);
    }
    out.push(n);
  }
  return out;
}

function computeStats(nums) {
  const counts = Array(9).fill(0);
  nums.forEach((n) => counts[n[0] - 1]++);
  const N = nums.length;
  const obs = counts.map((c) => (N ? c / N : 0));
  let chi2 = 0, mad = 0;
  const z = [];
  DIGITS.forEach((d, i) => {
    const e = EXPECTED[i];
    if (N) chi2 += (counts[i] - N * e) ** 2 / (N * e);
    mad += Math.abs(obs[i] - e) / 9;
    const zi = N ? (Math.abs(obs[i] - e) - 1 / (2 * N)) / Math.sqrt((e * (1 - e)) / N) : 0;
    z.push(Math.max(0, zi));
  });
  return { N, counts, obs, chi2, p: chi2pDf8(chi2), mad, z };
}

function conformity(mad) {
  if (mad <= 0.006) return { cls: "good", text: "Nært samsvar med Benfords lov" };
  if (mad <= 0.012) return { cls: "ok", text: "Akseptabelt samsvar med Benfords lov" };
  if (mad <= 0.015) return { cls: "warn", text: "Marginalt samsvar med Benfords lov" };
  return { cls: "bad", text: "Følger ikke Benfords lov" };
}

// ---------------------------------------------------------------- rendering

function renderAll() {
  renderCategories();
  renderAnalysis();
  renderSources();
}

function renderAnalysis() {
  const s = computeStats(analysedNumbers());
  renderVerdict(s);
  renderChart(s);
  renderTable(s);
  renderExamples();
}

function renderVerdict(s) {
  let c, note;
  if (s.N < 50) {
    c = { cls: "na", text: "For få tall til en meningsfull test" };
    note = `Bare ${fmtNum(s.N)} tall teller med. Benford-analyse trenger helst flere hundre tall; prøv flere sider, en større PDF, eller ta med flere kategorier.`;
  } else {
    c = conformity(s.mad);
    const sigDigits = DIGITS.filter((d, i) => s.z[i] > 1.96);
    note = (sigDigits.length
      ? `Siffer med signifikant avvik (|z| > 1,96): ${sigDigits.join(", ")}. `
      : "Ingen enkeltsiffer avviker signifikant. ")
      + (s.N < 300 ? "Utvalget er lite, så tolk resultatet med forsiktighet. " : "")
      + (s.N > 5000 && s.p < 0.05 && s.mad <= 0.012 ? "Kjikvadrattesten slår ut, men det er vanlig ved store utvalg – MAD er et bedre mål her." : "");
  }
  const pTxt = s.N ? (s.p < 0.0001 ? "< 0,0001" : fmtNum(s.p, 4)) : "–";
  $("#verdict").innerHTML = `
    <div class="verdict-head"><span class="badge ${c.cls}"><span class="dot"></span>${esc(c.text)}</span></div>
    <p>${esc(note)}</p>
    <div class="stats">
      <div class="stat"><div class="k">Tall analysert</div><div class="v">${fmtNum(s.N)}</div><div class="s">av ${fmtNum(data.numbers.length)} funnet</div></div>
      <div class="stat"><div class="k">MAD</div><div class="v">${s.N ? fmtNum(s.mad, 4) : "–"}</div><div class="s">≤ 0,006 nært · ≤ 0,012 akseptabelt · ≤ 0,015 marginalt</div></div>
      <div class="stat"><div class="k">Kjikvadrat (8 fg)</div><div class="v">${s.N ? fmtNum(s.chi2, 1) : "–"}</div><div class="s">kritisk verdi 15,5 ved 5 %</div></div>
      <div class="stat"><div class="k">p-verdi</div><div class="v">${pTxt}</div><div class="s">${s.N && s.p < 0.05 ? "signifikant avvik" : "ikke signifikant avvik"}</div></div>
    </div>`;
}

function renderChart(s) {
  const W = 640, H = 300, m = { t: 16, r: 8, b: 40, l: 44 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const maxV = Math.max(0.35, ...s.obs, ...EXPECTED);
  const yMax = Math.ceil(maxV / 0.05) * 0.05;
  const y = (v) => m.t + ih - (v / yMax) * ih;
  const band = iw / 9;
  const bw = Math.min(40, band * 0.6);
  const cx = (i) => m.l + band * i + band / 2;
  const sel = $("#ex-digit").value;

  let g = "";
  for (let v = 0; v <= yMax + 1e-9; v += 0.05) {
    g += `<line class="gridline" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/>`;
    g += `<text x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end">${Math.round(v * 100)} %</text>`;
  }
  DIGITS.forEach((d, i) => {
    const h = ih * (s.obs[i] / yMax);
    const x = cx(i) - bw / 2, top = y(s.obs[i]);
    const r = Math.min(4, h);
    const dim = sel && +sel !== d ? " dim" : "";
    if (h > 0) {
      g += `<path class="bar${dim}" d="M${x},${y(0)} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${y(0)} Z"/>`;
    }
    g += `<text x="${cx(i)}" y="${H - m.b + 18}" text-anchor="middle" style="font-size:13px;fill:var(--text)">${d}</text>`;
    if (s.N >= 50 && s.z[i] > 1.96) g += `<text class="zflag" x="${cx(i)}" y="${Math.min(top, y(EXPECTED[i])) - 8}" text-anchor="middle">*</text>`;
  });
  g += `<line class="baseline" x1="${m.l}" x2="${W - m.r}" y1="${y(0)}" y2="${y(0)}"/>`;
  g += `<polyline class="exp-line" points="${DIGITS.map((d, i) => `${cx(i)},${y(EXPECTED[i])}`).join(" ")}"/>`;
  DIGITS.forEach((d, i) => (g += `<circle class="exp-dot" cx="${cx(i)}" cy="${y(EXPECTED[i])}" r="5"/>`));
  g += `<text class="axis-label" x="${m.l + iw / 2}" y="${H - 4}" text-anchor="middle">Første siffer</text>`;
  DIGITS.forEach((d, i) => (g += `<rect class="hit" data-i="${i}" x="${m.l + band * i}" y="${m.t}" width="${band}" height="${ih}" rx="6"/>`));

  const el = $("#chart");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Søylediagram: observert andel per første siffer sammenlignet med Benfords lov">${g}</svg>`;
  const tip = $("#tooltip");
  el.querySelectorAll(".hit").forEach((r) => {
    const i = +r.dataset.i;
    r.addEventListener("mousemove", (e) => {
      tip.hidden = false;
      tip.innerHTML = `<b>Siffer ${i + 1}</b>
        <div class="r"><span>Observert</span><span>${fmtPct(s.obs[i])} (${fmtNum(s.counts[i])})</span></div>
        <div class="r"><span>Benford</span><span>${fmtPct(EXPECTED[i])} (${fmtNum(EXPECTED[i] * s.N, 0)})</span></div>
        <div class="r"><span>z</span><span>${fmtNum(s.z[i], 2)}${s.z[i] > 1.96 ? " *" : ""}</span></div>`;
      const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
      tip.style.left = x + "px";
      tip.style.top = e.clientY + 14 + "px";
    });
    r.addEventListener("mouseleave", () => (tip.hidden = true));
    r.addEventListener("click", () => {
      const v = String(i + 1);
      $("#ex-digit").value = $("#ex-digit").value === v ? "" : v;
      if ($("#ex-cat").value === "all") $("#ex-cat").value = "included";
      exLimit = 100;
      renderChart(s);
      renderExamples();
    });
  });
}

function renderTable(s) {
  const rows = DIGITS.map((d, i) => `<tr>
      <td>${d}</td><td>${fmtNum(s.counts[i])}</td><td>${fmtPct(s.obs[i])}</td><td>${fmtPct(EXPECTED[i])}</td>
      <td>${(s.obs[i] - EXPECTED[i] >= 0 ? "+" : "−") + fmtPct(Math.abs(s.obs[i] - EXPECTED[i]))}</td>
      <td class="${s.z[i] > 1.96 ? "sig" : ""}">${fmtNum(s.z[i], 2)}</td></tr>`).join("");
  $("#digit-table").innerHTML = `<table><thead><tr><th>Siffer</th><th>Antall</th><th>Observert</th><th>Benford</th><th>Avvik</th><th>z</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderCategories() {
  const counts = {};
  data.numbers.forEach((n) => (counts[n[1]] = (counts[n[1]] || 0) + 1));
  const html = data.categories.map((c, idx) => {
    const n = counts[idx] || 0;
    const fixed = c.key === "zero";
    const sep = c.key === "year" ? "<hr>" : "";
    return `${sep}<label class="${n ? "" : "empty"}"><input type="checkbox" data-key="${c.key}" ${included.has(c.key) ? "checked" : ""} ${fixed ? "disabled" : ""}>
      <span>${esc(c.label)}</span><span class="n">${fmtNum(n)}</span></label>`;
  }).join("");
  $("#categories").innerHTML = html;
  $("#categories").querySelectorAll("input").forEach((cb) =>
    cb.addEventListener("change", () => {
      cb.checked ? included.add(cb.dataset.key) : included.delete(cb.dataset.key);
      exLimit = 100;
      renderAnalysis();
    })
  );
  const exCat = $("#ex-cat");
  const prev = exCat.value || "included";
  exCat.innerHTML = `<option value="included">Tall som telles med</option><option value="excluded">Tall som er filtrert bort</option><option value="all">Alle tall</option>`
    + data.categories.map((c, idx) => (counts[idx] ? `<option value="c${idx}">${esc(c.label)}</option>` : "")).join("");
  exCat.value = [...exCat.options].some((o) => o.value === prev) ? prev : "included";
}

function renderExamples() {
  const keys = data.categories.map((c) => c.key);
  const f = $("#ex-cat").value;
  const d = $("#ex-digit").value;
  const pool = f === "included" ? analysedNumbers() : data.numbers;
  const list = pool.filter((n) => {
    if (d && n[0] !== +d) return false;
    if (f === "excluded") return !included.has(keys[n[1]]) || n[0] === 0;
    if (f.startsWith("c")) return n[1] === +f.slice(1);
    return true;
  });
  const label = { included: "Tall som telles med", excluded: "Tall som er filtrert bort", all: "Alle tall" }[f]
    || data.categories[+f.slice(1)].label;
  $("#examples-title").textContent = `${label}${d ? ` – første siffer ${d}` : ""} (${fmtNum(list.length)})`;
  const multiSource = data.sources.length > 1;
  $("#examples").innerHTML = list.slice(0, exLimit).map((n) => {
    const ctx = esc(n[4]).replace("⟦", "<mark>").replace("⟧", "</mark>");
    const src = multiSource ? ` · ${esc(shortName(data.sources[n[2]].name))}` : "";
    return `<li><span class="num">${esc(n[3])}</span><span class="ctx">${ctx}</span><span class="tag">${esc(data.categories[n[1]].label.split(" (")[0])}${src}</span></li>`;
  }).join("") || '<li><span class="ctx">Ingen tall å vise.</span></li>';
  $("#more").hidden = list.length <= exLimit;
}

function shortName(name) {
  try {
    const u = new URL(name);
    return (u.pathname === "/" ? u.host : u.pathname.split("/").filter(Boolean).pop()) || u.host;
  } catch { return name; }
}

function renderSources() {
  const rows = data.sources.map((s) => {
    const name = /^https?:/.test(s.name) ? `<a href="${esc(s.name)}" target="_blank" rel="noopener noreferrer" title="${esc(s.name)}">${esc(s.name)}</a>` : esc(s.name);
    return `<tr><td>${name}</td><td>${s.kind.toUpperCase()}</td><td>${s.depth}</td><td>${s.pages}</td>
      <td>${s.error ? `<span class="err">${esc(s.error)}</span>` : fmtNum(s.numbers)}</td></tr>`;
  }).join("");
  const ok = data.sources.filter((s) => !s.error).length;
  $("#sources").innerHTML = `<p class="hint">${ok} av ${data.sources.length} kilder lest.</p>
    <table><thead><tr><th>Kilde</th><th>Type</th><th>Nivå</th><th>Sider</th><th>Tall</th></tr></thead><tbody>${rows}</tbody></table>`;
}

$("#ex-cat").addEventListener("change", () => { exLimit = 100; renderExamples(); });
$("#ex-digit").addEventListener("change", () => { exLimit = 100; renderAnalysis(); });
$("#unique-only").addEventListener("change", () => renderAnalysis());
$("#more").addEventListener("click", () => { exLimit += 200; renderExamples(); });
