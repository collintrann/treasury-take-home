"use strict";

// Vanilla JS on purpose: no build step, nothing to install, easy to audit.

const $ = (sel, root = document) => root.querySelector(sel);
const FIELDS = ["brand_name", "class_type", "alcohol_content", "net_contents", "producer_name_address", "country_of_origin"];

const STATUS = {
  pass: { icon: "✔", word: "Match" },
  review: { icon: "⚠", word: "Check" },
  fail: { icon: "✖", word: "Mismatch" },
  missing: { icon: "✖", word: "Not found" },
  skipped: { icon: "–", word: "Skipped" },
};
const BANNER = {
  pass: { icon: "✔", title: "Label matches the application", sub: "Every checked field matches." },
  review: { icon: "⚠", title: "Needs your review", sub: "Nothing is clearly wrong, but some items need a human eye." },
  fail: { icon: "✖", title: "Problems found", sub: "At least one item does not match. See the red items below." },
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function apiError(res) {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch (_) { /* not JSON */ }
  return `The server returned an error (${res.status}). Please try again.`;
}

async function verify(file, application) {
  const fd = new FormData();
  fd.append("image", file, file.name);
  for (const f of FIELDS) fd.append(f, application[f] || "");
  const res = await fetch("/api/verify", { method: "POST", body: fd });
  if (!res.ok) throw new Error(await apiError(res));
  return res.json();
}

// ------------------------------------------------------------------ rendering

function renderDiff(diff) {
  const parts = diff.map((d) =>
    d.op === "equal" ? esc(d.text) : d.op === "missing" ? `<del title="Required but missing">${esc(d.text)}</del>` : `<ins title="On label but not in required text">${esc(d.text)}</ins>`
  );
  return `<div class="diff">${parts.join(" ")}</div>
    <div class="legend"><del>struck out</del> = required wording missing from the label · <ins>underlined</ins> = wording on the label that shouldn't be there</div>`;
}

function renderField(f) {
  const s = STATUS[f.status];
  const showDiff = f.diff && f.diff.some((d) => d.op !== "equal");
  const compare = f.status === "skipped" ? "" : f.field === "government_warning"
    ? (showDiff ? renderDiff(f.diff) : "")
    : `<div class="compare">
         <div><b>Application</b>${esc(f.expected) || "<em>—</em>"}</div>
         <div><b>On the label</b>${esc(f.found) || "<em>not found</em>"}</div>
       </div>`;
  return `<article class="field c-${f.status}">
      <div class="field-head">
        <h3>${esc(f.label)}</h3>
        <span class="pill s-${f.status}">${s.icon} ${s.word}</span>
      </div>
      <p class="note">${esc(f.note)}</p>
      ${compare}
    </article>`;
}

function renderResult(r) {
  const b = BANNER[r.overall];
  return `<div class="banner s-${r.overall}" role="status">
      <span class="icon" aria-hidden="true">${b.icon}</span>
      <div><h2>${b.title}</h2><p>${b.sub}</p></div>
    </div>
    <p class="meta">Checked in ${(r.elapsed_ms / 1000).toFixed(1)} seconds.${r.extraction_note ? " " + esc(r.extraction_note) : ""}</p>
    <div class="fieldlist">${r.fields.map(renderField).join("")}</div>`;
}

// --------------------------------------------------------------------- tabs

document.querySelectorAll('[role="tab"]').forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll('[role="tab"]').forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", on);
      $("#" + t.getAttribute("aria-controls")).hidden = !on;
    });
  });
});

// ------------------------------------------------------------------- single

const form = $("#single-form");
const imageInput = $("#image");
const drop = $("#drop");
let currentFile = null;

function setImage(file) {
  currentFile = file;
  const img = $("#preview");
  if (file) {
    img.src = URL.createObjectURL(file);
    img.alt = `Preview of ${file.name}`;
    img.hidden = false;
    $("#drop-text").hidden = true;
  } else {
    img.hidden = true;
    img.removeAttribute("src");
    $("#drop-text").hidden = false;
  }
}

imageInput.addEventListener("change", () => setImage(imageInput.files[0] || null));
["dragenter", "dragover"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((e) => drop.addEventListener(e, () => drop.classList.remove("over")));
drop.addEventListener("drop", (ev) => {
  ev.preventDefault();
  const file = ev.dataTransfer.files[0];
  if (file) setImage(file);
});

function showError(el, msg) {
  el.textContent = msg;
  el.hidden = !msg;
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const err = $("#single-error");
  showError(err, "");
  if (!currentFile) return showError(err, "Please choose a label image first (step 1).");
  const application = Object.fromEntries(FIELDS.map((f) => [f, form.elements[f].value.trim()]));
  if (!Object.values(application).some(Boolean)) {
    return showError(err, "Please fill in at least one field from the application (step 2).");
  }

  const btn = $("#check-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner" aria-hidden="true"></span>Checking…';
  $("#single-result").innerHTML = "";
  try {
    const result = await verify(currentFile, application);
    $("#single-result").innerHTML = renderResult(result);
    $("#single-result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    showError(err, e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Check label";
  }
});

$("#clear-btn").addEventListener("click", () => {
  form.reset();
  setImage(null);
  $("#single-result").innerHTML = "";
  showError($("#single-error"), "");
  $("#example").value = "";
});

// Examples: lets evaluators try the app without hunting for test images.
let examples = [];
async function fetchSample(filename) {
  const res = await fetch("/samples/" + encodeURIComponent(filename));
  const blob = await res.blob();
  return new File([blob], filename, { type: blob.type });
}

fetch("/api/examples").then((r) => r.json()).then((rows) => {
  examples = rows;
  const sel = $("#example");
  rows.forEach((row, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = row.what_this_tests || row.filename;
    sel.appendChild(opt);
  });
}).catch(() => { $(".examples").hidden = true; });

$("#example").addEventListener("change", async (ev) => {
  const row = examples[ev.target.value];
  if (!row) return;
  for (const f of FIELDS) form.elements[f].value = row.application[f] || "";
  setImage(await fetchSample(row.filename));
  $("#single-result").innerHTML = "";
});


// -------------------------------------------------------------------- batch

const CONCURRENCY = 4; // the server also caps this; 4 keeps the browser responsive
let manifest = [];
let imagesByName = new Map();
let batchResults = [];
let filter = "all";

function updateBatchReady() {
  const matched = manifest.filter((r) => imagesByName.has(r.filename)).length;
  $("#batch-btn").disabled = matched === 0;
  if (manifest.length && imagesByName.size) {
    const missing = manifest.length - matched;
    $("#images-status").textContent = `${imagesByName.size} images selected · ${matched} of ${manifest.length} rows have a matching image` +
      (missing ? ` · ${missing} missing (they will be listed as errors)` : "");
  } else if (imagesByName.size) {
    $("#images-status").textContent = `${imagesByName.size} images selected.`;
  }
}

async function loadManifest(file) {
  const fd = new FormData();
  fd.append("manifest", file, file.name);
  const res = await fetch("/api/parse-manifest", { method: "POST", body: fd });
  if (!res.ok) throw new Error(await apiError(res));
  const data = await res.json();
  manifest = data.rows;
  $("#manifest-status").textContent = `${manifest.length} labels listed.` + (data.errors.length ? ` Skipped: ${data.errors.join(" ")}` : "");
  updateBatchReady();
}

$("#manifest").addEventListener("change", async (ev) => {
  showError($("#batch-error"), "");
  const file = ev.target.files[0];
  if (!file) return;
  try { await loadManifest(file); } catch (e) { manifest = []; $("#manifest-status").textContent = ""; showError($("#batch-error"), e.message); updateBatchReady(); }
});

$("#images").addEventListener("change", (ev) => {
  imagesByName = new Map([...ev.target.files].map((f) => [f.name, f]));
  updateBatchReady();
});

$("#batch-sample-btn").addEventListener("click", async () => {
  showError($("#batch-error"), "");
  try {
    const csv = await (await fetch("/samples/batch.csv")).blob();
    await loadManifest(new File([csv], "batch.csv", { type: "text/csv" }));
    const files = await Promise.all(manifest.map((r) => fetchSample(r.filename)));
    imagesByName = new Map(files.map((f) => [f.name, f]));
    $("#manifest-status").textContent = `${manifest.length} example labels loaded.`;
    updateBatchReady();
  } catch (e) {
    showError($("#batch-error"), "Could not load the examples: " + e.message);
  }
});

function issuesText(r) {
  if (r.error) return r.error;
  return r.result.fields.filter((f) => f.status !== "pass" && f.status !== "skipped").map((f) => `${f.label}: ${f.note}`).join(" · ") || "—";
}

function statusOf(r) { return r.error ? "fail" : r.result.overall; }

function renderBatch() {
  const counts = { pass: 0, review: 0, fail: 0 };
  batchResults.forEach((r) => r && counts[statusOf(r)]++);
  $("#batch-summary").innerHTML =
    `<span class="pill s-pass">✔ ${counts.pass} passed</span>` +
    `<span class="pill s-review">⚠ ${counts.review} need review</span>` +
    `<span class="pill s-fail">✖ ${counts.fail} problems</span>`;

  const rows = batchResults.map((r, i) => {
    if (!r) return "";
    const st = statusOf(r);
    if (filter !== "all" && st !== filter) return "";
    const word = r.error ? "Error" : { pass: "Pass", review: "Review", fail: "Problems" }[st];
    return `<tr>
        <td>${esc(r.filename)}</td>
        <td>${esc(r.application.brand_name)}</td>
        <td><span class="pill s-${st}">${BANNER[st].icon} ${word}</span></td>
        <td class="issues">${esc(issuesText(r))}</td>
        <td>${r.result ? `<button class="link" data-detail="${i}">Details</button>` : ""}</td>
      </tr>
      <tr class="detail" id="detail-${i}" hidden><td colspan="5"></td></tr>`;
  });
  $("#batch-body").innerHTML = rows.join("");
}

$("#batch-body").addEventListener("click", (ev) => {
  const i = ev.target.dataset.detail;
  if (i === undefined) return;
  const row = $("#detail-" + i);
  if (row.hidden) row.firstElementChild.innerHTML = renderResult(batchResults[i].result);
  row.hidden = !row.hidden;
  ev.target.textContent = row.hidden ? "Details" : "Hide";
});

document.querySelectorAll(".filters [data-filter]").forEach((b) => b.addEventListener("click", () => {
  filter = b.dataset.filter;
  document.querySelectorAll(".filters [data-filter]").forEach((x) => x.setAttribute("aria-pressed", x === b));
  renderBatch();
}));

$("#batch-btn").addEventListener("click", async () => {
  const btn = $("#batch-btn");
  btn.disabled = true;
  showError($("#batch-error"), "");
  batchResults = new Array(manifest.length).fill(null);
  $("#batch-progress").hidden = false;
  $("#batch-results").hidden = false;
  let done = 0;
  const started = performance.now();
  const tick = () => {
    $("#bar").style.width = `${(100 * done) / manifest.length}%`;
    $("#progress-text").textContent = done < manifest.length
      ? `Checked ${done} of ${manifest.length}…`
      : `Done: ${manifest.length} labels in ${((performance.now() - started) / 1000).toFixed(0)} s.`;
    renderBatch();
  };
  tick();

  // Simple worker pool: N loops pull the next index until the list is empty.
  let next = 0;
  async function worker() {
    while (next < manifest.length) {
      const i = next++;
      const row = manifest[i];
      const file = imagesByName.get(row.filename);
      const entry = { filename: row.filename, application: row.application };
      if (!file) entry.error = "No image file with this name was selected.";
      else {
        try { entry.result = await verify(file, row.application); }
        catch (e) { entry.error = e.message; }
      }
      batchResults[i] = entry;
      done++;
      tick();
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  btn.disabled = false;
});

function csvCell(v) { return `"${String(v ?? "").replace(/"/g, '""')}"`; }

$("#download-btn").addEventListener("click", () => {
  const header = ["filename", "result", ...FIELDS.map((f) => f + "_status"), "government_warning_status", "issues"];
  const lines = [header.map(csvCell).join(",")];
  for (const r of batchResults) {
    if (!r) continue;
    const byField = Object.fromEntries((r.result?.fields || []).map((f) => [f.field, f.status]));
    lines.push([
      r.filename, r.error ? "error" : r.result.overall,
      ...FIELDS.map((f) => byField[f] || ""), byField.government_warning || "", issuesText(r),
    ].map(csvCell).join(","));
  }
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "label-check-results.csv" });
  a.click();
  URL.revokeObjectURL(url);
});
