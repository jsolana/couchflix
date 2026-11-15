// App shell: sidebar, hash router, views kept alive between navigations.
import { icon } from "./icons.js";
import { $, $$, toast } from "./ui.js";
import * as suggestions from "./suggestions.js";
import * as search from "./search.js";
import * as profile from "./profile.js";
import * as detail from "./detail.js";
import { open as openSettingsPanel } from "./settings.js";
const openSettings = () => openSettingsPanel(() => suggestions.reload());

const VIEWS = { suggestions, search, profile };
const ICONS = { suggestions: "compass", search: "search", profile: "user" };
let lastView = "#/suggestions";

// sidebar
$("#logo").innerHTML = icon("sofa");
$$(".nav-item[data-route]").forEach((a) => ($(".ic", a).innerHTML = icon(ICONS[a.dataset.route])));
$("#settings-btn .ic").innerHTML = icon("sliders");
$("#collapse-btn .ic").innerHTML = icon("panel");
const app = $("#app");
const setCollapsed = (v) => {
  app.classList.toggle("collapsed", v);
  $("#collapse-btn").setAttribute("aria-expanded", String(!v));
  try { localStorage.setItem("couchflix.sidebar", v ? "collapsed" : "expanded"); } catch {}
};
try { setCollapsed(localStorage.getItem("couchflix.sidebar") === "collapsed"); } catch {}
$("#collapse-btn").onclick = () => setCollapsed(!app.classList.contains("collapsed"));
$("#settings-btn").onclick = () => openSettings();

suggestions.init(openSettings);
search.init(openSettings);
detail.setOnChange((id, state) => { suggestions.syncCard(id, state); search.syncCard(id, state); });

function route() {
  const hash = location.hash || "#/suggestions";
  const m = hash.match(/^#\/c\/(\d+)/);
  if (m) {
    detail.open(+m[1], () => (location.hash = lastView));
    if (!$(".view.active")) activate("suggestions");
    return;
  }
  detail.close();
  lastView = hash;
  activate(hash.replace("#/", "") in VIEWS ? hash.replace("#/", "") : "suggestions");
}

function activate(name) {
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  $$(".nav-item[data-route]").forEach((a) => { const on = a.dataset.route === name; a.classList.toggle("active", on); on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"); });
  document.title = `${{ suggestions: "Sugerencias", search: "Buscar", profile: "Perfil" }[name]} · COUCHFLIX`;
  VIEWS[name].show();
}

addEventListener("hashchange", route);
addEventListener("offline", () => toast("Sin conexión", "err"));
addEventListener("online", () => toast("De vuelta en línea"));
route();
