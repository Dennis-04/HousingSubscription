const SVG_NS = "http://www.w3.org/2000/svg";
const BASE_VIEW = { x: 0, y: 0, width: 1000, height: 1000 };

const svg = document.querySelector("#korea-map");
const mapCard = document.querySelector("#map-card");
const mapLayer = document.querySelector("#map-layer");
const tooltip = document.querySelector("#map-tooltip");
const cursorDot = document.querySelector("#cursor-dot");
const pattern = document.querySelector("#dot-pattern");
const patternDot = document.querySelector("#pattern-dot");
const breadcrumb = document.querySelector("#breadcrumb");
const levelBadge = document.querySelector("#level-badge");
const backButton = document.querySelector("#back-button");
const mapStatus = document.querySelector("#map-status");

let currentView = { ...BASE_VIEW };
let currentGroups = new Map();
let groupElements = new Map();
let hoveredKey = null;
let activeKey = null;
let isAnimating = false;
let pointerFrame = 0;
let pendingPointer = null;
let resizeFrame = 0;
let noticeCounts = new Map();

const state = {
  level: "province",
  province: null,
  city: null,
  leaf: null,
};

const compiledFeatures = window.KOREA_REGION_PATHS ?? [];
if (!compiledFeatures.length) throw new Error("행정경계 데이터를 불러오지 못했습니다.");

const features = compiledFeatures.map((feature) => ({
  sgg: feature.c,
  sggnm: feature.n,
  province: { id: feature.p[0], name: feature.p[1] },
  bounds: {
    minX: feature.b[0],
    minY: feature.b[1],
    maxX: feature.b[2],
    maxY: feature.b[3],
  },
  path: feature.d,
}));

function emptyBounds() {
  return { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
}

function mergeBounds(target, source) {
  target.minX = Math.min(target.minX, source.minX);
  target.minY = Math.min(target.minY, source.minY);
  target.maxX = Math.max(target.maxX, source.maxX);
  target.maxY = Math.max(target.maxY, source.maxY);
  return target;
}

function finalizeGroups(groups) {
  groups.forEach((group) => {
    group.path = group.features.map((feature) => feature.path).join("");
  });
  return groups;
}

function groupBy(items, getKey, createMeta) {
  const groups = new Map();
  items.forEach((item) => {
    const key = getKey(item);
    if (!groups.has(key)) groups.set(key, createMeta(item, key));
    const group = groups.get(key);
    group.features.push(item);
    mergeBounds(group.bounds, item.bounds);
  });
  return finalizeGroups(groups);
}

const provinceGroups = groupBy(
  features,
  (feature) => `province:${feature.province.id}`,
  (feature, key) => ({
    key,
    id: feature.province.id,
    name: feature.province.name,
    kind: "province",
    features: [],
    bounds: emptyBounds(),
  }),
);

const municipalityCache = new Map();
const districtCache = new Map();

function isDirectDistrictProvince(provinceName) {
  return /특별시$|광역시$|특별자치시$/.test(provinceName);
}

function municipalityGroupsFor(province) {
  if (municipalityCache.has(province.id)) return municipalityCache.get(province.id);

  const groups = groupBy(
    province.features,
    (feature) => {
      const city = feature.sggnm.match(/^(.+?시)(.+구)$/);
      return city && !isDirectDistrictProvince(province.name)
        ? `city:${city[1]}`
        : `sgg:${feature.sgg}`;
    },
    (feature, key) => {
      const city = feature.sggnm.match(/^(.+?시)(.+구)$/);
      const isCity = Boolean(city) && !isDirectDistrictProvince(province.name);
      return {
        key,
        id: isCity ? city[1] : feature.sgg,
        name: isCity ? city[1] : feature.sggnm,
        kind: isCity ? "city" : "leaf",
        features: [],
        bounds: emptyBounds(),
      };
    },
  );

  municipalityCache.set(province.id, groups);
  return groups;
}

function districtGroupsFor(city) {
  if (districtCache.has(city.id)) return districtCache.get(city.id);

  const groups = new Map(
    city.features.map((feature) => {
      const key = `district:${feature.sgg}`;
      return [
        key,
        {
          key,
          id: feature.sgg,
          name: feature.sggnm.replace(city.name, ""),
          kind: "leaf",
          features: [feature],
          bounds: { ...feature.bounds },
          path: feature.path,
        },
      ];
    }),
  );

  districtCache.set(city.id, groups);
  return groups;
}

function createSvgElement(tagName, attributes) {
  const element = document.createElementNS(SVG_NS, tagName);
  Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
  return element;
}

function setGroupHighlight(key, className, enabled) {
  groupElements.get(key)?.classList.toggle(className, enabled);
}

function clearHover() {
  if (hoveredKey) setGroupHighlight(hoveredKey, "is-hovered", false);
  hoveredKey = null;
  pendingPointer = null;
  if (pointerFrame) cancelAnimationFrame(pointerFrame);
  pointerFrame = 0;
  mapLayer.classList.remove("has-hover");
  tooltip.classList.remove("visible");
  cursorDot.classList.remove("visible");
}

function updatePointer() {
  pointerFrame = 0;
  if (!pendingPointer) return;

  const { x, y, name } = pendingPointer;
  const cardBounds = mapCard.getBoundingClientRect();
  tooltip.textContent = name;
  tooltip.style.left = `${x - cardBounds.left}px`;
  tooltip.style.top = `${y - cardBounds.top}px`;
  tooltip.classList.add("visible");

  const point = svg.createSVGPoint();
  point.x = x;
  point.y = y;
  const local = point.matrixTransform(svg.getScreenCTM().inverse());
  const spacing = Number(pattern.getAttribute("width"));
  cursorDot.setAttribute("cx", Math.round(local.x / spacing) * spacing);
  cursorDot.setAttribute("cy", Math.round(local.y / spacing) * spacing);
  cursorDot.classList.add("visible");
}

function showHover(meta, event) {
  mapLayer.classList.add("has-hover");
  if (hoveredKey !== meta.key) {
    if (hoveredKey) setGroupHighlight(hoveredKey, "is-hovered", false);
    hoveredKey = meta.key;
    setGroupHighlight(meta.key, "is-hovered", true);
  }

  const count = noticeCountFor(meta);
  const name = count === null ? meta.name : `${meta.name} · 공고 ${count}건`;
  pendingPointer = { x: event.clientX, y: event.clientY, name };
  if (!pointerFrame) pointerFrame = requestAnimationFrame(updatePointer);
}

function noticeCountFor(meta) {
  if (noticeCounts.has(String(meta.id))) return noticeCounts.get(String(meta.id));
  const childCounts = (meta.features ?? [])
    .map((feature) => noticeCounts.get(String(feature.sgg)))
    .filter((value) => typeof value === "number");
  return childCounts.length ? childCounts.reduce((sum, value) => sum + value, 0) : null;
}

async function loadNoticeCounts() {
  if (!window.HousingApi) return;
  try {
    const rows = await window.HousingApi.regionSummary();
    noticeCounts = new Map(
      rows.map((row) => [String(row.region_code), Number(row.count) || 0]),
    );
  } catch {
    noticeCounts = new Map();
  }
}

function setActiveGroup(key) {
  if (activeKey) setGroupHighlight(activeKey, "is-active", false);
  activeKey = key;
  if (activeKey) setGroupHighlight(activeKey, "is-active", true);
}

function renderGroups(groups, level) {
  clearHover();
  activeKey = null;
  currentGroups = groups;
  groupElements = new Map();
  mapLayer.replaceChildren();
  mapLayer.dataset.level = level;

  const fragment = document.createDocumentFragment();
  let index = 0;

  groups.forEach((meta) => {
    const group = createSvgElement("g", {
      class: "region",
      "data-group-key": meta.key,
      role: "button",
      "aria-label": `${meta.name} 지도 확대`,
      tabindex: "0",
    });
    const shape = createSvgElement("path", {
      class: "region-shape",
      d: meta.path,
      mask: "url(#dot-mask)",
    });

    group.style.animationDelay = `${Math.min(index * 8, 180)}ms`;
    group.append(shape);
    fragment.append(group);
    groupElements.set(meta.key, group);
    index += 1;
  });

  mapLayer.append(fragment);
  mapLayer.classList.add("is-entering");
  window.setTimeout(() => mapLayer.classList.remove("is-entering"), 720);
}

function renderProvinces() {
  renderGroups(provinceGroups, "province");
}

function renderMunicipalities(province) {
  renderGroups(municipalityGroupsFor(province), "municipality");
}

function renderDistricts(city) {
  renderGroups(districtGroupsFor(city), "district");
}

function metaFromEvent(event) {
  const region = event.target.closest?.(".region");
  return region ? currentGroups.get(region.dataset.groupKey) : null;
}

mapLayer.addEventListener("pointerover", (event) => {
  const meta = metaFromEvent(event);
  if (meta) showHover(meta, event);
});

mapLayer.addEventListener("pointermove", (event) => {
  const meta = metaFromEvent(event);
  if (meta) showHover(meta, event);
});

mapLayer.addEventListener("pointerout", (event) => {
  const from = event.target.closest?.(".region")?.dataset.groupKey;
  const to = event.relatedTarget?.closest?.(".region")?.dataset.groupKey;
  if (from && from !== to) clearHover();
});

mapLayer.addEventListener("click", (event) => {
  const meta = metaFromEvent(event);
  if (meta) handleGroupClick(meta);
});

mapLayer.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const meta = metaFromEvent(event);
  if (!meta) return;
  event.preventDefault();
  handleGroupClick(meta);
});

function easeInOutCubic(value) {
  return value < 0.5
    ? 4 * value * value * value
    : 1 - Math.pow(-2 * value + 2, 3) / 2;
}

function viewForBounds(bounds, paddingRatio = 0.16) {
  let width = Math.max(4, bounds.maxX - bounds.minX) * (1 + paddingRatio * 2);
  let height = Math.max(4, bounds.maxY - bounds.minY) * (1 + paddingRatio * 2);
  const aspect = (svg.clientWidth || 760) / (svg.clientHeight || 760);

  if (width / height < aspect) width = height * aspect;
  else height = width / aspect;

  return {
    x: (bounds.minX + bounds.maxX - width) / 2,
    y: (bounds.minY + bounds.maxY - height) / 2,
    width,
    height,
  };
}

function updateDotPattern(view) {
  const unitsPerPixel = view.width / (svg.clientWidth || 760);
  const spacing = Math.max(0.8, unitsPerPixel * 7.4);
  const radius = spacing * 0.255;

  pattern.setAttribute("width", spacing);
  pattern.setAttribute("height", spacing);
  patternDot.setAttribute("cx", spacing / 2);
  patternDot.setAttribute("cy", spacing / 2);
  patternDot.setAttribute("r", radius);
  cursorDot.setAttribute("r", radius * 1.75);
}

function applyViewBox(view, updatePattern = true) {
  currentView = view;
  svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);
  if (updatePattern) updateDotPattern(view);
}

function animateViewBox(target, duration = 680) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    applyViewBox(target);
    return Promise.resolve();
  }

  const start = { ...currentView };
  const startedAt = performance.now();
  let lastPatternUpdate = 0;
  isAnimating = true;
  mapCard.classList.add("is-zooming");

  return new Promise((resolve) => {
    function frame(now) {
      const progress = Math.min(1, (now - startedAt) / duration);
      const eased = easeInOutCubic(progress);
      const view = {
        x: start.x + (target.x - start.x) * eased,
        y: start.y + (target.y - start.y) * eased,
        width: start.width + (target.width - start.width) * eased,
        height: start.height + (target.height - start.height) * eased,
      };
      const shouldUpdatePattern = progress === 1 || now - lastPatternUpdate >= 32;
      applyViewBox(view, shouldUpdatePattern);
      if (shouldUpdatePattern) lastPatternUpdate = now;

      if (progress < 1) requestAnimationFrame(frame);
      else {
        isAnimating = false;
        mapCard.classList.remove("is-zooming");
        resolve();
      }
    }
    requestAnimationFrame(frame);
  });
}

async function changeLayer(render) {
  mapLayer.classList.add("is-changing");
  await new Promise((resolve) => window.setTimeout(resolve, 170));
  render();
  requestAnimationFrame(() => mapLayer.classList.remove("is-changing"));
}

async function handleGroupClick(meta) {
  if (isAnimating) return;
  clearHover();
  setActiveGroup(meta.key);
  mapStatus.textContent = `${meta.name} 선택됨`;

  if (state.level === "province") {
    state.province = meta;
    state.city = null;
    state.leaf = null;
    updateChrome();
    await animateViewBox(viewForBounds(meta.bounds, 0.1));
    state.level = "municipality";
    await changeLayer(() => renderMunicipalities(meta));
    updateChrome();
    return;
  }

  if (state.level === "municipality" && meta.kind === "city") {
    state.city = meta;
    state.leaf = null;
    updateChrome();
    await animateViewBox(viewForBounds(meta.bounds, 0.12));
    state.level = "district";
    await changeLayer(() => renderDistricts(meta));
    updateChrome();
    return;
  }

  state.leaf = meta;
  state.level = "leaf";
  updateChrome();
  await animateViewBox(viewForBounds(meta.bounds, 0.22));
  setActiveGroup(meta.key);
}

function breadcrumbItem(label, action, current = false) {
  const element = document.createElement(current ? "span" : "button");
  if (current) element.className = "current";
  else {
    element.type = "button";
    element.dataset.nav = action;
  }
  element.textContent = label;
  return element;
}

function separator() {
  const element = document.createElement("span");
  element.className = "separator";
  element.textContent = "/";
  element.setAttribute("aria-hidden", "true");
  return element;
}

function updateChrome() {
  const items = [];
  items.push(breadcrumbItem("전국", "nationwide", state.level === "province"));

  if (state.province) {
    items.push(separator());
    items.push(
      breadcrumbItem(
        state.province.name,
        "province",
        state.level === "municipality" && !state.city && !state.leaf,
      ),
    );
  }
  if (state.city) {
    items.push(separator());
    items.push(
      breadcrumbItem(
        state.city.name,
        "city",
        state.level === "district" && !state.leaf,
      ),
    );
  }
  if (state.leaf) {
    items.push(separator(), breadcrumbItem(state.leaf.name, "leaf", true));
  }

  breadcrumb.replaceChildren(...items);
  backButton.hidden = state.level === "province";

  if (state.level === "province") levelBadge.textContent = "시·도";
  else if (state.level === "district") levelBadge.textContent = "구";
  else if (state.level === "leaf") levelBadge.textContent = "선택";
  else if (isDirectDistrictProvince(state.province?.name ?? "")) levelBadge.textContent = "구";
  else levelBadge.textContent = "시·군";
}

async function goNationwide() {
  if (isAnimating) return;
  Object.assign(state, { level: "province", province: null, city: null, leaf: null });
  updateChrome();
  await changeLayer(renderProvinces);
  await animateViewBox({ ...BASE_VIEW });
}

async function goProvince() {
  if (isAnimating || !state.province) return;
  Object.assign(state, { level: "municipality", city: null, leaf: null });
  updateChrome();
  await changeLayer(() => renderMunicipalities(state.province));
  await animateViewBox(viewForBounds(state.province.bounds, 0.1));
}

async function goCity() {
  if (isAnimating || !state.city) return;
  Object.assign(state, { level: "district", leaf: null });
  updateChrome();
  await changeLayer(() => renderDistricts(state.city));
  await animateViewBox(viewForBounds(state.city.bounds, 0.12));
}

function goBack() {
  if (state.level === "municipality") return goNationwide();
  if (state.level === "district") return goProvince();
  if (state.level === "leaf") return state.city ? goCity() : goProvince();
}

breadcrumb.addEventListener("click", (event) => {
  const action = event.target.closest("button")?.dataset.nav;
  if (action === "nationwide") goNationwide();
  else if (action === "province") goProvince();
  else if (action === "city") goCity();
});

backButton.addEventListener("click", goBack);
svg.addEventListener("pointerleave", clearHover);
window.addEventListener("resize", () => {
  if (resizeFrame) return;
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = 0;
    updateDotPattern(currentView);
  });
});

renderProvinces();
applyViewBox(BASE_VIEW);
updateChrome();
loadNoticeCounts();
