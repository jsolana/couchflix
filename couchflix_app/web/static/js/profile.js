// Perfil: animated radar ("personality") + chronological activity.
import { api } from "./api.js";
import { icon } from "./icons.js";
import { $, emptyState, esc, fmtDate, h, reduceMotion } from "./ui.js";

const root = $("#view-profile");
const NS = "http://www.w3.org/2000/svg";
const SIZE = 460, C = SIZE / 2, R = 150;
const ease = (t) => 1 - Math.pow(1 - t, 3); // ease-out cubic
const angle = (i, n) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
const at = (i, n, r) => [C + r * Math.cos(angle(i, n)), C + r * Math.sin(angle(i, n))];
const pts = (arr) => arr.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
const svg = (tag, attrs = {}) => Object.entries(attrs).reduce((el, [k, v]) => (el.setAttribute(k, v), el), document.createElementNS(NS, tag));

let token = 0;

export async function show() {
  const [profile, activity] = await Promise.all([api.get("/api/profile"), api.get("/api/activity")]);
  root.innerHTML = `
    <header class="view-head"><div><p class="eyebrow">Mi personalidad audiovisual</p><h1>Perfil</h1></div></header>
    <div class="profile-grid">
      <div id="radar-slot"></div>
      <div><div class="legend" id="legend" data-testid="legend"></div>
        <div class="persona"><p id="description" data-testid="description">${esc(profile.description)}</p>
          <div class="pills" id="top-genres">${profile.top_genres.map((g) => `<span class="pill on">${esc(g)}</span>`).join("")}</div>
          <div class="evo" id="evo" data-testid="evolution"></div></div></div>
    </div>
    <header class="view-head"><div><p class="eyebrow">Mi actividad</p></div></header>
    <div class="timeline" id="timeline" data-testid="timeline"></div>`;
  renderEvolution(profile);
  renderActivity(activity);
  drawRadar($("#radar-slot"), profile);
}

function renderEvolution(p) {
  const { deltas, history } = p.evolution;
  $("#evo").innerHTML = !p.known ? `<span>Valora títulos para ver cómo evoluciona tu perfil.</span>`
    : deltas.length ? `<span>Evolución:</span>${deltas.map((d) => `<span class="pill ${d.delta > 0 ? "up" : "down"}">${esc(d.label)} ${d.delta > 0 ? "+" : ""}${d.delta}</span>`).join("")}`
    : `<span>Tu perfil acaba de empezar: ${history.length} ${history.length === 1 ? "registro" : "registros"} de evolución.</span>`;
}

const LABELS = {
  search: (e) => ["search", `Buscaste <b>«${esc(e.detail)}»</b>`], watched: () => ["eye", "Marcaste como vista"], unwatched: () => ["eye", "Desmarcaste como vista"],
  like: () => ["up", "Te gustó"], love: () => ["up", "Te encantó"], dislike: () => ["down", "No te gustó"], unrate: () => ["x", "Quitaste tu valoración de"],
  comment: (e) => ["chat", `Comentaste <span class="quote">«${esc(e.detail)}»</span> en`],
};

function renderActivity(events) {
  const box = $("#timeline");
  if (!events.length) return box.append(emptyState("film", "Aquí aparecerá tu historial", "Busca, marca lo que has visto y valora para que COUCHFLIX te conozca."));
  box.append(...events.map((e) => {
    const [ic, text] = (LABELS[e.kind] || (() => ["film", e.kind]))(e);
    const tag = e.content_id ? "a" : "div";
    return h(`<${tag} class="event" data-kind="${e.kind}" ${e.content_id ? `href="#/c/${e.content_id}"` : ""}>
      <span class="ev-i">${icon(ic)}</span><span>${text} ${e.title ? `<b>${esc(e.title)}</b>` : ""}</span><small>${fmtDate(e.created_at)}</small></${tag}>`);
  }));
}

function drawRadar(slot, p) {
  const my = ++token, n = p.dimensions.length;
  const s = svg("svg", { viewBox: `0 0 ${SIZE} ${SIZE}`, class: "radar", role: "img", "data-testid": "radar", "data-state": "building",
    "aria-label": "Gráfico radial de tu perfil: " + p.dimensions.map((d) => `${d.label} ${d.value}`).join(", ") + (p.known ? "" : " (por descubrir)") });
  [0.25, 0.5, 0.75, 1].forEach((k) => s.append(svg("polygon", { class: "ring", points: pts(p.dimensions.map((_, i) => at(i, n, R * k))) })));
  p.dimensions.forEach((d, i) => {
    const [x, y] = at(i, n, R);
    s.append(svg("line", { class: "axis", x1: C, y1: C, x2: x, y2: y }));
    const [lx, ly] = at(i, n, R + 48);
    const t = svg("text", { class: "axis-label", x: lx, y: ly + 4 });
    t.textContent = d.label; s.append(t);
  });
  const dims = p.dimensions;
  const shape = svg("polygon", { class: "shape", points: pts(dims.map(() => [C, C])), "data-testid": "radar-shape" });
  const dots = dims.map((d, i) => svg("circle", { class: "dot", cx: C, cy: C, r: 5, "data-dim": d.key }));
  const vals = dims.map((d, i) => { const t = svg("text", { class: "val", x: C, y: C }); t.textContent = d.value; return t; });
  s.append(shape, ...dots, ...vals);   // a new user also gets a radar: every dimension at the neutral 50
  slot.replaceChildren(s);

  const legend = $("#legend");
  legend.classList.remove("show");
  legend.innerHTML = dims.map((d) => `<div class="dim" data-dim="${d.key}"><b>${esc(d.label)}</b><span class="tag">${esc(d.tagline)}</span>
    <span class="num">${d.value}</span><span class="bar"><i style="--w:${d.value}%"></i></span></div>`).join("");

  const finish = () => { if (my !== token) return; s.dataset.state = "done"; s.classList.add("done"); legend.classList.add("show"); };
  const draw = (t) => {   // every point travels from the centre (0,0) to its value, in sync
    const e = ease(t);
    const target = dims.map((d, i) => at(i, n, (R * d.value / 100) * e));
    shape.setAttribute("points", pts(target));
    target.forEach(([x, y], i) => { dots[i].setAttribute("cx", x); dots[i].setAttribute("cy", y); const [vx, vy] = at(i, n, (R * dims[i].value / 100) * e + 18); vals[i].setAttribute("x", vx); vals[i].setAttribute("y", vy + 4); });
  };
  s.classList.add("axes-in");
  if (reduceMotion()) { draw(1); return finish(); }
  const DURATION = 1000, start = performance.now() + 250;     // axes appear first, then the polygon grows
  const frame = (now) => {
    if (my !== token) return;
    const t = Math.min(Math.max((now - start) / DURATION, 0), 1);
    draw(t);
    t < 1 ? requestAnimationFrame(frame) : finish();
  };
  requestAnimationFrame(frame);
}
