/* Data worker: streams + parses the columnar dataset and runs exact/fuzzy
   search off the main thread, so the UI never blocks. */

let fields = [];
let dict = {};            // field -> [distinct values] (dictionary-encoded columns)
let columns = [];         // per-field array; ints (dict index) or raw strings
let fieldIndex = {};      // field name -> column position
let exactIndex = new Map(); // normalised name (taxon + synonyms) -> row index
let searchList = [];      // { idx, name, len, genus, epithet } for fuzzy search

function norm(s) {
  return String(s || "").trim().toLowerCase().replace(/\s+/g, " ");
}

// Read one cell, decoding dictionary columns back to their string value.
function cell(rowIdx, field) {
  const col = columns[fieldIndex[field]];
  const raw = col[rowIdx];
  const d = dict[field];
  return d ? d[raw] : raw;
}

// Rehydrate a full row object (keyed by field name) for display.
function row(idx) {
  const o = { _id: idx };
  for (const f of fields) o[f] = cell(idx, f);
  return o;
}

self.onmessage = (e) => {
  const m = e.data;
  if (m.type === "load") load(m.dataUrl, m.metaUrl);
  else if (m.type === "search") postMessage({ type: "results", id: m.id, results: search(m.queries) });
};

async function load(dataUrl, metaUrl) {
  try {
    let total = 0;
    try {
      const meta = await (await fetch(metaUrl, { cache: "no-cache" })).json();
      total = meta.rawBytes || 0;
    } catch (_) { /* progress falls back to indeterminate */ }

    const resp = await fetch(dataUrl);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    // Stream so we can report download progress (body is already decompressed).
    const reader = resp.body && resp.body.getReader ? resp.body.getReader() : null;
    let text;
    if (reader) {
      const chunks = [];
      let loaded = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        loaded += value.length;
        postMessage({ type: "progress", loaded, total });
      }
      const buf = new Uint8Array(loaded);
      let off = 0;
      for (const c of chunks) { buf.set(c, off); off += c.length; }
      text = new TextDecoder("utf-8").decode(buf);
    } else {
      text = await resp.text();
    }

    postMessage({ type: "parsing" });
    const data = JSON.parse(text);
    fields = data.fields;
    dict = data.dict || {};
    columns = data.columns;
    fields.forEach((f, i) => { fieldIndex[f] = i; });

    buildIndexes();
    postMessage({ type: "ready", meta: data.meta || {}, rows: columns[0] ? columns[0].length : 0 });
  } catch (err) {
    postMessage({ type: "error", message: String(err && err.message || err) });
  }
}

function buildIndexes() {
  exactIndex = new Map();
  searchList = [];
  const nameCol = columns[fieldIndex.taxon_name];
  const synField = "synonyms";
  const n = nameCol.length;
  for (let i = 0; i < n; i++) {
    const name = norm(cell(i, "taxon_name"));
    if (name && !exactIndex.has(name)) exactIndex.set(name, i);
    const syns = cell(i, synField);
    if (syns) {
      for (const s of syns.split(";")) {
        const sn = norm(s);
        if (sn && !exactIndex.has(sn)) exactIndex.set(sn, i);
      }
    }
    if (name) {
      const sp = name.indexOf(" ");
      searchList.push({
        idx: i,
        name,
        len: name.length,
        genus: sp === -1 ? name : name.slice(0, sp),
        epithet: sp === -1 ? "" : name.slice(sp + 1).split(" ")[0],
      });
    }
  }
}

// Bounded Levenshtein: returns distance, or maxDist+1 if it exceeds maxDist.
function boundedLev(a, b, maxDist) {
  const la = a.length, lb = b.length;
  if (Math.abs(la - lb) > maxDist) return maxDist + 1;
  let prev = new Array(lb + 1);
  let curr = new Array(lb + 1);
  for (let j = 0; j <= lb; j++) prev[j] = j;
  for (let i = 1; i <= la; i++) {
    curr[0] = i;
    let rowMin = curr[0];
    const ca = a.charCodeAt(i - 1);
    for (let j = 1; j <= lb; j++) {
      const cost = ca === b.charCodeAt(j - 1) ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
      if (curr[j] < rowMin) rowMin = curr[j];
    }
    if (rowMin > maxDist) return maxDist + 1;
    const tmp = prev; prev = curr; curr = tmp;
  }
  return prev[lb];
}

function fuzzyMatches(query) {
  const q = norm(query);
  if (!q) return [];
  const qLen = q.length;
  const sp = q.indexOf(" ");
  const qGenus = sp === -1 ? q : q.slice(0, sp);
  const qEpithet = sp === -1 ? "" : q.slice(sp + 1).split(" ")[0];
  const maxDist = qLen <= 5 ? 1 : qLen <= 10 ? 2 : 3;

  const seen = new Set();
  const cands = [];
  for (const e of searchList) {
    const epithetMatch = qEpithet && e.epithet === qEpithet && e.genus !== qGenus;
    let dist = maxDist + 1;
    if (Math.abs(e.len - qLen) <= maxDist) dist = boundedLev(q, e.name, maxDist);
    if (dist <= maxDist || epithetMatch) {
      if (seen.has(e.name)) continue;
      seen.add(e.name);
      cands.push({ idx: e.idx, name: cell(e.idx, "taxon_name"), dist: dist <= maxDist ? dist : null, epithetMatch });
    }
  }
  cands.sort((a, b) => {
    const da = a.dist === null ? Number.MAX_SAFE_INTEGER : a.dist;
    const db = b.dist === null ? Number.MAX_SAFE_INTEGER : b.dist;
    if (da !== db) return da - db;
    if (a.epithetMatch !== b.epithetMatch) return a.epithetMatch ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  return cands.slice(0, 8);
}

function search(queries) {
  return queries.map((query) => {
    const q = norm(query);
    const hit = q ? exactIndex.get(q) : undefined;
    if (hit !== undefined) return { query, row: row(hit) };
    const suggestions = fuzzyMatches(query).map((s) => ({
      row: row(s.idx), dist: s.dist, epithetMatch: s.epithetMatch,
    }));
    return { query, noMatch: true, suggestions };
  });
}
