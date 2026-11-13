"use strict";
/* Renders briefs.json. All text from the data goes in as plain text, never as markup,
   because the data comes from documents that are treated as hostile. */
const $ = (s, el = document) => el.querySelector(s);
const el = (tag, props = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const k of kids) if (k) n.append(k);
  return n;
};
const KIND = { flag: "Flag", hidden_text: "Hidden text", related_party: "Related party", conflict: "Withheld", unchecked: "Not checked" };
let DATA = null, filter = new Set(), query = "";

const count = (f, k) => f.read_first.filter((i) => i.kind === k).length;
const safeUrl = (u) => (/^https:\/\//.test(u) ? u : null);
const pageLink = (f, p, label) => {
  const base = safeUrl(f.source);
  return base ? el("a", { class: "pg", href: `${base}#page=${p}`, target: "_blank", rel: "noopener noreferrer", text: label ?? `p.${p}` }) : el("span", { class: "pg", text: label ?? `p.${p}` });
};
const money = (m) => el("span", { class: m.neg ? "neg" : null, text: m.text });

function renderRows() {
  const tbody = $("#rows");
  tbody.replaceChildren();
  const q = query.trim().toLowerCase();
  const list = DATA.filings.filter((f) => (!q || f.issuer.toLowerCase().includes(q)) && [...filter].every((k) => count(f, k) > 0));
  for (const f of list) {
    const tr = el("tr", { tabindex: "0", role: "link", "aria-label": `Open the brief for ${f.issuer}` },
      el("td", {}, el("strong", { text: f.issuer })),
      el("td", { text: f.doc_type }),
      el("td", { text: f.filed ?? "–" }),
      el("td", { class: "num", text: String(f.read_first.length) }),
      el("td", { class: "num", text: String(count(f, "flag")) }),
      el("td", { class: "num", text: String(count(f, "related_party")) }),
      el("td", { class: "num", text: String(count(f, "conflict")) }),
      el("td", { class: "num", text: `${f.rules_checked[0]} of ${f.rules_checked[1]}` }));
    const open = () => { location.hash = `#/${f.id}`; };
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
    tbody.append(tr);
  }
  if (!list.length) tbody.append(el("tr", {}, el("td", { colspan: "8", class: "note", text: "No filing matches." })));
  $("#count").textContent = `${list.length} of ${DATA.filings.length} filings shown.`;
}

function renderBrief(f) {
  const box = $("#brief");
  box.replaceChildren();
  box.hidden = false;
  const items = f.read_first.length
    ? el("ol", {}, ...f.read_first.map((i) => el("li", {},
        el("span", { class: `tag ${i.kind}`, text: KIND[i.kind] ?? i.kind }), document.createTextNode(i.text + " "),
        i.page != null ? pageLink(f, i.page) : null,
        i.section ? el("span", { class: "note", text: ` (${i.section})` }) : null,
        i.evidence.length ? el("ul", { class: "ev" }, ...i.evidence.map((e) => el("li", {}, el("code", { text: e.text }), document.createTextNode(" "), pageLink(f, e.page)))) : null)))
    : el("p", {}, document.createTextNode("Nothing flagged and nothing withheld. That is "), el("strong", { text: "not" }), document.createTextNode(` a clean bill of health: only ${f.rules_checked[0]} of ${f.rules_checked[1]} applicable rules could be evaluated.`));

  const issue = f.issue.length
    ? el("div", { class: "table-wrap", style: "box-shadow:none" }, el("table", {}, el("thead", {}, el("tr", {}, el("th"), el("th", { class: "num", text: "₹ crore" }), el("th", { text: "Page" }))),
        el("tbody", {}, ...f.issue.map((r) => el("tr", {}, el("th", { text: r.label }), el("td", { class: "num" }, money(r)), el("td", {}, pageLink(f, r.page)))))))
    : el("p", { class: "note", text: "No issue size is stated in a form that could be read (placeholders such as [●] are not read as figures)." });
  const fin = f.metrics.length
    ? el("div", { class: "table-wrap", style: "box-shadow:none" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", { text: "₹ crore" }), ...f.years.map((y) => el("th", { class: "num", text: y })), el("th", { class: "num", text: "Change" }))),
        el("tbody", {}, ...f.metrics.map((m) => el("tr", {}, el("th", { text: m.label }),
          ...m.cells.map((c) => el("td", { class: "num" }, c ? money(c) : document.createTextNode("–"), c ? document.createTextNode(" ") : null, c ? pageLink(f, c.page) : null)),
          el("td", { class: "num", text: m.change ?? "" }))))))
    : el("p", { class: "note", text: "No annual figures could be read with enough confidence." });

  const [d, a] = f.rules_checked, [v, t] = f.numbers_verified;
  box.append(el("div", { class: "brief" },
    el("h3", { text: f.issuer }),
    el("div", { class: "meta" }, document.createTextNode(`${f.doc_type} · ${f.platform ?? "platform not recorded"} · filed ${f.filed ?? "not recorded"} · `),
      safeUrl(f.source) ? el("a", { href: f.source, target: "_blank", rel: "noopener noreferrer", text: "public source" }) : null),
    el("h4", { text: "Read first" }), items,
    el("div", { class: "grid2" }, el("div", {}, el("h4", { text: "The issue" }), issue), el("div", {}, el("h4", { text: "Financials" }), fin)),
    el("h4", { text: "How far to trust this" }),
    el("p", { text: `${d} of ${a} applicable rules could be evaluated. ${v} of ${t} extracted numbers were found again on their cited page. A figure the document's tables disagreed on is listed above, not shown. ${f.sections} sections mapped.` }),
    ...f.notes.map((n) => el("p", { class: "note", text: n }))));
  box.scrollIntoView({ block: "start", behavior: "smooth" });
}

function route() {
  const id = decodeURIComponent((location.hash.match(/^#\/(.+)$/) || [])[1] || "");
  const f = DATA && DATA.filings.find((x) => x.id === id);
  if (f) renderBrief(f); else if (DATA) $("#brief").hidden = true;
}

function renderStats() {
  const b = DATA.meta.benchmark;
  if (!b) { $("#bench").textContent = "Accuracy figures are exported with each release."; return; }
  $("#bench").textContent = `The reader is scored against ${b.labelled} hand-labelled fields over ${DATA.meta.labelled_filings} filings.`;
  const rows = [[`${b.correct}/${b.present}`, "present fields read correctly"], [String(b.wrong), "wrong values shown"], [String(b.withheld), "withheld, with the reason"], [String(DATA.meta.count), "filings in this demo"]];
  $("#stats").replaceChildren(...rows.map(([n, l]) => el("div", { class: "card stat" }, el("b", { text: n }), el("span", { text: l }))));
}

fetch("briefs.json").then((r) => r.json()).then((d) => {
  DATA = d;
  $("#gen").textContent = `Demo data exported ${d.meta.generated}.`;
  renderStats(); renderRows(); route();
}).catch(() => { $("#count").textContent = "The demo data could not be loaded."; });
$("#q").addEventListener("input", (e) => { query = e.target.value; renderRows(); });
document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
  const k = c.dataset.f; const on = !filter.has(k);
  on ? filter.add(k) : filter.delete(k); c.setAttribute("aria-pressed", String(on)); renderRows();
}));
window.addEventListener("hashchange", route);
