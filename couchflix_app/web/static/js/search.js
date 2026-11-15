// Buscar: talk to the agent in natural language, get visual results, refine them.
import { api } from "./api.js";
import { icon } from "./icons.js";
import { $, emptyState, esc, h, openOnActivate, revealInto, skeletonRow } from "./ui.js";

const root = $("#view-search");
const EXAMPLES = ["Algo de ciencia ficción", "Una película de terror que dé mucho miedo", "Algo para ver en familia", "Una serie corta", "Algo parecido a Interstellar", "Una película de los últimos dos años"];
const REFINE = [["recent", "Algo más reciente"], ["action", "Más acción"], ["less_known", "Menos conocido"], ["different", "Algo diferente"], ["more", "Dame otras opciones"]];
let current = null, results, loadedLast = false;

export function init(openSettings) {
  root.innerHTML = `
    <div class="ask">
      <h1>¿Qué te apetece ver hoy?</h1>
      <form class="ask-box" id="ask-form" role="search">
        <input id="ask-input" type="text" autocomplete="off" aria-label="Cuéntale al agente qué te apetece ver" placeholder="Quiero una película de aventuras de menos de dos horas, bien valorada y en Netflix…" data-testid="ask-input">
        <button class="go" type="submit" aria-label="Buscar" data-tip="Buscar" data-testid="ask-submit">${icon("send")}</button>
      </form>
      <div class="pills" id="examples">${EXAMPLES.map((e) => `<button class="pill" type="button">${esc(e)}</button>`).join("")}</div>
    </div>
    <div id="understood" class="understood" hidden></div>
    <div id="results" aria-live="polite"></div>
    <div id="refine" class="pills" style="justify-content:flex-start;margin-top:26px" hidden></div>`;
  results = $("#results");
  $("#ask-form").onsubmit = (e) => { e.preventDefault(); ask($("#ask-input").value.trim()); };
  $("#examples").onclick = (e) => { const b = e.target.closest(".pill"); if (b) { $("#ask-input").value = b.textContent; ask(b.textContent); } };
  $("#refine").innerHTML = REFINE.map(([k, l]) => `<button class="pill" data-refine="${k}" data-testid="refine-${k}">${l}</button>`).join("");
  $("#refine").onclick = (e) => { const b = e.target.closest("[data-refine]"); if (b && current) run({ refine: b.dataset.refine, search_id: current.id }); };
  openOnActivate(results);
  results.openSettings = openSettings;
}

export async function show() {
  if (loadedLast) return;
  loadedLast = true;
  const last = await api.get("/api/search/last").catch(() => ({}));
  if (last.id) { $("#ask-input").value = last.query; render(last); }
}

function ask(text) { if (text) run({ text }); }

async function run(body) {
  $("#understood").hidden = true;
  $("#refine").hidden = true;
  results.innerHTML = `<div class="grid" data-testid="search-loading"></div>`;
  $(".grid", results).append(...skeletonRow(6));
  try { render(await api.post("/api/search", body)); }
  catch { results.replaceChildren(emptyState("alert", "No hemos podido buscar", "Inténtalo de nuevo en un momento.")); }
}

async function render(data) {
  current = data;
  const chips = $("#understood");
  chips.hidden = false;
  chips.innerHTML = `<span class="sub">Entendí:</span>${data.chips.map((c) => `<span class="pill on">${esc(c)}</span>`).join("") || `<span class="pill">sin filtros</span>`}
    <span class="agent-tag" data-testid="agent-tag" title="${data.agent === "llm" ? "Interpretado por un modelo de lenguaje" : "Interpretado por el motor de reglas (sin LLM)"}">${data.agent === "llm" ? "IA" : "Reglas"}</span>`;
  if (data.setup) return results.replaceChildren(emptyState("film", "Conecta un catálogo", "Configura un proveedor para que el agente pueda buscar.", { label: "Configurar", onClick: () => results.openSettings() }));
  if (!data.items.length) {
    results.replaceChildren(emptyState("search", "Nada encaja con eso… todavía", data.warnings.length ? "Algunas fuentes no responden. Prueba de nuevo en un momento." : "Prueba a relajar algún criterio o pide «algo diferente»."));
    $("#refine").hidden = false;
    return;
  }
  const grid = h(`<div class="grid" data-testid="search-results"></div>`);
  grid.append(...skeletonRow(data.items.length));
  results.replaceChildren(grid);
  await revealInto(grid, data.items);
  const reasons = Object.fromEntries(data.items.map((i) => [i.id, i.reason]));
  grid.querySelectorAll(".card[data-id]").forEach((card) => {   // short explanation under every recommendation
    const wrap = h(`<div class="result"></div>`);
    card.replaceWith(wrap);
    wrap.append(card, h(`<p class="why" data-testid="why">${esc(reasons[card.dataset.id] || "")}</p>`));
  });
  $("#refine").hidden = false;
}

export function syncCard(id, state) {
  root.querySelectorAll(`.card[data-id="${id}"]`).forEach((c) => c.classList.toggle("watched", !!(state.watched || state.rating)));
}
