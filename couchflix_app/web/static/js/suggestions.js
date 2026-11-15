// Sugerencias: personalized carousel (top) and Random Couch Sessions (bottom) — two separate concepts.
import { api } from "./api.js";
import { icon } from "./icons.js";
import { $, createCarousel, emptyState, esc, h, revealInto, skeletonRow, openOnActivate } from "./ui.js";

const root = $("#view-suggestions");
let personal, discoveryBox, loaded = false;

export function init(openSettings) {
  root.innerHTML = `
    <header class="view-head"><div><p class="eyebrow tagline">Less scrolling. More chilling.</p><h1>Sugerencias</h1></div></header>
    <p class="notice" id="notice" hidden data-testid="provider-notice">${icon("alert")}<span></span></p>
    <section class="row" aria-labelledby="h-personal" data-testid="personal">
      <div class="row-head"><h2 class="row-title" id="h-personal">Para ti</h2>
        <button class="icon-btn" id="refresh-personal" data-tip="Nuevas sugerencias" aria-label="Nuevas sugerencias" data-testid="refresh-personal">${icon("refresh")}</button></div>
      <div id="personal-slot"></div>
    </section>
    <section class="row" aria-labelledby="h-discovery" data-testid="discovery">
      <div class="row-head"><h2 class="row-title" id="h-discovery">${icon("shuffle")} Random Couch Sessions</h2>
        <button class="icon-btn" id="refresh-discovery" data-tip="Nuevas sesiones aleatorias" aria-label="Nuevas sesiones aleatorias" data-testid="refresh-discovery">${icon("shuffle")}</button></div>
      <div id="discovery-slot"></div>
    </section>`;
  personal = createCarousel({ label: "Recomendaciones personalizadas" });
  $("#personal-slot").append(personal.el);
  discoveryBox = $("#discovery-slot");
  discoveryBox.append(sessionSkeleton());
  $("#refresh-personal").onclick = (e) => loadPersonal(true, e.currentTarget);
  $("#refresh-discovery").onclick = (e) => loadDiscovery(true, e.currentTarget);
  root.openSettings = openSettings;
}

export async function show() {
  if (loaded) return;          // navigating back never triggers new searches
  loaded = true;
  await Promise.all([loadPersonal(false), loadDiscovery(false)]);
}

/** Settings changed what "mine" means (platforms, country…): rebuild on next view. */
export function reload() {
  loaded = false;
  if (root.classList.contains("active")) show();
}

function notice(warnings) {
  const el = $("#notice");
  el.hidden = !warnings?.length;
  if (warnings?.length) $("span", el).textContent = "Algunas fuentes no responden · mostrando los datos guardados";
}

function setup() {
  return emptyState("film", "Conecta un catálogo para empezar", "COUCHFLIX necesita un proveedor (TMDB) para encontrar películas y series.",
    { label: "Configurar", onClick: () => root.openSettings() });
}

async function loadPersonal(refresh, button) {
  button?.classList.add("spin");
  personal.skeleton();
  try {
    const data = refresh ? await api.post("/api/suggestions/personal/refresh") : await api.get("/api/suggestions/personal");
    notice(data.warnings);
    if (data.setup) return personal.message(setup());
    if (!data.items.length) return personal.message(emptyState("compass", "Aún no hay sugerencias", "Pulsa el icono de refrescar para volver a intentarlo."));
    await personal.show(data.items);
  } catch { personal.message(emptyState("alert", "No hemos podido cargar tus sugerencias", "Inténtalo de nuevo en un momento.")); }
  finally { button?.classList.remove("spin"); }
}

function sessionSkeleton() {
  const wrap = h(`<div data-testid="discovery-skeleton"></div>`);
  const car = createCarousel({ label: "Cargando" });
  wrap.append(car.el);
  return wrap;
}

function themeRow(title, items, testid = "theme") {
  const car = createCarousel({ skeletons: 0, label: title });
  const el = h(`<div class="row" style="margin-bottom:26px" data-testid="${testid}"><h3 class="row-title" style="font-size:16px;color:var(--muted);font-weight:600">${esc(title)}</h3></div>`);
  el.append(car.el);
  car.track.replaceChildren(...skeletonRow(Math.min(items.length, 7)));
  car.show(items);
  return el;
}

async function loadDiscovery(refresh, button) {
  button?.classList.add("spin");
  discoveryBox.replaceChildren(sessionSkeleton());
  try {
    const data = refresh ? await api.post("/api/suggestions/discovery/refresh") : await api.get("/api/suggestions/discovery");
    if (data.setup) return discoveryBox.replaceChildren(setup());
    const rows = [];
    if (data.last_search?.items.length) rows.push(themeRow(`Tu última búsqueda · “${data.last_search.query}”`, data.last_search.items, "last-search"));
    data.themes.forEach((t) => rows.push(themeRow(t.title, t.items)));
    discoveryBox.replaceChildren(...(rows.length ? rows : [emptyState("shuffle", "Sin sesiones por ahora", "Pulsa el icono de mezclar para generar otras nuevas.")]));
  } catch { discoveryBox.replaceChildren(emptyState("alert", "No hemos podido preparar las sesiones", "Inténtalo de nuevo en un momento.")); }
  finally { button?.classList.remove("spin"); }
}

/** Reflect interaction changes made in the detail view on already-rendered cards. */
export function syncCard(id, state) {
  root.querySelectorAll(`.card[data-id="${id}"]`).forEach((c) => c.classList.toggle("watched", !!(state.watched || state.rating)));
}
