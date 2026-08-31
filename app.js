const SVG_NS = "http://www.w3.org/2000/svg";
const MAP_SIZE = 1000;
const BASE_VIEW = { x: 0, y: 0, width: MAP_SIZE, height: MAP_SIZE };
const BLUE = "#2563eb";
const GWANGJU_CODES = new Set(["12210", "12240", "12270", "12300", "12330"]);

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

const state = {
  level: "province",
  province: null,
  city: null,
  leaf: null,
};

const sourceFeatures = window.KOREA_SGG_DATA?.features ?? [];

if (!sourceFeatures.length) {
  throw new Error("행정경계 데이터를 불러오지 못했습니다.");
}

function rawMercator([longitude, latitude]) {
  const lambda = (longitude * Math.PI) / 180;
  const safeLatitude = Math.max(-85, Math.min(85, latitude));
  const phi = (safeLatitude * Math.PI) / 180;
  return [lambda, Math.log(Math.tan(Math.PI / 4 + phi / 2))];
}

function visitCoordinates(geometry, callback) {
  if (geometry.type === "Polygon") {
    geometry.coordinates.forEach((ring) => ring.forEach(callback));
    return;
  }

  if (geometry.type === "MultiPolygon") {
    geometry.coordinates.forEach((polygon) =>
      polygon.forEach((ring) => ring.forEach(callback)),
    );
  }
}

const mercatorBounds = {
  minX: Infinity,
  minY: Infinity,
  maxX: -Infinity,
  maxY: -Infinity,
};

sourceFeatures.forEach((feature) => {
  visitCoordinates(feature.geometry, (coordinate) => {
    const [x, y] = rawMercator(coordinate);
    mercatorBounds.minX = Math.min(mercatorBounds.minX, x);
    mercatorBounds.minY = Math.min(mercatorBounds.minY, y);
    mercatorBounds.maxX = Math.max(mercatorBounds.maxX, x);
    mercatorBounds.maxY = Math.max(mercatorBounds.maxY, y);
  });
});

const projectionScale = Math.min(
  888 / (mercatorBounds.maxX - mercatorBounds.minX),
  888 / (mercatorBounds.maxY - mercatorBounds.minY),
);
const projectedWidth = (mercatorBounds.maxX - mercatorBounds.minX) * projectionScale;
const projectedHeight = (mercatorBounds.maxY - mercatorBounds.minY) * projectionScale;
const projectionOffsetX = (MAP_SIZE - projectedWidth) / 2;
const projectionOffsetY = (MAP_SIZE - projectedHeight) / 2;

function project(coordinate) {
  const [x, y] = rawMercator(coordinate);
  return [
    projectionOffsetX + (x - mercatorBounds.minX) * projectionScale,
    projectionOffsetY + (mercatorBounds.maxY - y) * projectionScale,
  ];
}

function emptyBounds() {
  return { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
}

function addPointToBounds(bounds, [x, y]) {
  bounds.minX = Math.min(bounds.minX, x);
  bounds.minY = Math.min(bounds.minY, y);
  bounds.maxX = Math.max(bounds.maxX, x);
  bounds.maxY = Math.max(bounds.maxY, y);
}

function mergeBounds(target, source) {
  target.minX = Math.min(target.minX, source.minX);
  target.minY = Math.min(target.minY, source.minY);
  target.maxX = Math.max(target.maxX, source.maxX);
  target.maxY = Math.max(target.maxY, source.maxY);
  return target;
}

function ringToPath(ring, bounds) {
  return ring
    .map((coordinate, index) => {
      const point = project(coordinate);
      addPointToBounds(bounds, point);
      return `${index === 0 ? "M" : "L"}${point[0].toFixed(2)} ${point[1].toFixed(2)}`;
    })
    .join("") + "Z";
}

function geometryToPath(geometry) {
  const bounds = emptyBounds();
  let path = "";

  if (geometry.type === "Polygon") {
    path = geometry.coordinates.map((ring) => ringToPath(ring, bounds)).join("");
  } else if (geometry.type === "MultiPolygon") {
    path = geometry.coordinates
      .flatMap((polygon) => polygon.map((ring) => ringToPath(ring, bounds)))
      .join("");
  }

  return { path, bounds };
}

function normalizeProvince(properties) {
  if (properties.sidonm === "전남광주통합특별시") {
    if (GWANGJU_CODES.has(properties.sgg)) {
      return { id: "29", name: "광주광역시" };
    }
    return { id: "46", name: "전라남도" };
  }

  return { id: properties.sido, name: properties.sidonm };
}

const features = sourceFeatures.map((feature) => {
  const geometry = geometryToPath(feature.geometry);
  return {
    ...feature.properties,
    province: normalizeProvince(feature.properties),
    path: geometry.path,
    bounds: geometry.bounds,
  };
});

function groupBy(items, getKey, createMeta) {
  const groups = new Map();

  items.forEach((item) => {
    const key = getKey(item);
    if (!groups.has(key)) groups.set(key, createMeta(item, key));
    const group = groups.get(key);
    group.features.push(item);
    mergeBounds(group.bounds, item.bounds);
  });

  return groups;
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

function isDirectDistrictProvince(provinceName) {
  return /특별시$|광역시$|특별자치시$/.test(provinceName);
}

function municipalityGroupsFor(province) {
  const cityGroups = new Map();

  province.features.forEach((feature) => {
    const cityMatch = feature.sggnm.match(/^(.+?시)(.+구)$/);
    const isCityWithDistricts = Boolean(cityMatch) && !isDirectDistrictProvince(province.name);
    const key = isCityWithDistricts ? `city:${cityMatch[1]}` : `sgg:${feature.sgg}`;

    if (!cityGroups.has(key)) {
      cityGroups.set(key, {
        key,
        id: isCityWithDistricts ? cityMatch[1] : feature.sgg,
        name: isCityWithDistricts ? cityMatch[1] : feature.sggnm,
        kind: isCityWithDistricts ? "city" : "leaf",
        features: [],
        bounds: emptyBounds(),
      });
    }

    const group = cityGroups.get(key);
    group.features.push(feature);
    mergeBounds(group.bounds, feature.bounds);
  });

  return cityGroups;
}

function districtGroupsFor(city) {
  return new Map(
    city.features.map((feature) => {
      const districtName = feature.sggnm.replace(city.name, "");
      const key = `district:${feature.sgg}`;
      return [
        key,
        {
          key,
          id: feature.sgg,
          name: districtName,
          kind: "leaf",
          features: [feature],
          bounds: { ...feature.bounds },
        },
      ];
    }),
  );
}

function createSvgElement(tagName, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tagName);
  Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
  return element;
}

function setGroupHighlight(key, className, enabled) {
  groupElements.get(key)?.forEach((element) => element.classList.toggle(className, enabled));
}

function clearHover() {
  if (hoveredKey) setGroupHighlight(hoveredKey, "is-hovered", false);
  hoveredKey = null;
  tooltip.classList.remove("visible");
  cursorDot.classList.remove("visible");
}

function showHover(meta, event) {
  if (hoveredKey !== meta.key) {
    if (hoveredKey) setGroupHighlight(hoveredKey, "is-hovered", false);
    hoveredKey = meta.key;
    setGroupHighlight(meta.key, "is-hovered", true);
  }

  const cardBounds = mapCard.getBoundingClientRect();
  tooltip.textContent = meta.name;
  tooltip.style.left = `${event.clientX - cardBounds.left}px`;
  tooltip.style.top = `${event.clientY - cardBounds.top}px`;
  tooltip.classList.add("visible");

  const svgPoint = svg.createSVGPoint();
  svgPoint.x = event.clientX;
  svgPoint.y = event.clientY;
  const localPoint = svgPoint.matrixTransform(svg.getScreenCTM().inverse());
  const spacing = Number(pattern.getAttribute("width"));
  cursorDot.setAttribute("cx", Math.round(localPoint.x / spacing) * spacing);
  cursorDot.setAttribute("cy", Math.round(localPoint.y / spacing) * spacing);
  cursorDot.classList.add("visible");
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

  let regionIndex = 0;
  const focusAssigned = new Set();

  groups.forEach((meta) => {
    groupElements.set(meta.key, []);

    meta.features.forEach((feature) => {
      const isPrimaryPath = !focusAssigned.has(meta.key);
      const groupAttributes = {
        class: "region",
        "data-group-key": meta.key,
      };

      if (isPrimaryPath) {
        groupAttributes.role = "button";
        groupAttributes["aria-label"] = `${meta.name} 지도 확대`;
        groupAttributes.tabindex = "0";
      } else {
        groupAttributes.role = "presentation";
        groupAttributes["aria-hidden"] = "true";
      }

      const group = createSvgElement("g", groupAttributes);

      const shape = createSvgElement("path", {
        class: "region-shape",
        d: feature.path,
        mask: "url(#dot-mask)",
      });
      const outline = createSvgElement("path", {
        class: "region-outline",
        d: feature.path,
        "fill-rule": "evenodd",
      });

      group.style.animationDelay = `${Math.min(regionIndex * 8, 180)}ms`;
      group.append(shape, outline);
      mapLayer.append(group);
      groupElements.get(meta.key).push(group);
      focusAssigned.add(meta.key);
      regionIndex += 1;

      group.addEventListener("pointerenter", (event) => showHover(meta, event));
      group.addEventListener("pointermove", (event) => showHover(meta, event));
      group.addEventListener("pointerleave", (event) => {
        const nextGroup = event.relatedTarget?.closest?.(".region")?.dataset.groupKey;
        if (nextGroup === meta.key) return;
        clearHover();
      });
      group.addEventListener("click", () => handleGroupClick(meta));
      group.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        handleGroupClick(meta);
      });
    });
  });

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

function easeInOutCubic(value) {
  return value < 0.5
    ? 4 * value * value * value
    : 1 - Math.pow(-2 * value + 2, 3) / 2;
}

function viewForBounds(bounds, paddingRatio = 0.16) {
  let width = Math.max(4, bounds.maxX - bounds.minX);
  let height = Math.max(4, bounds.maxY - bounds.minY);
  width *= 1 + paddingRatio * 2;
  height *= 1 + paddingRatio * 2;

  const screenAspect = (svg.clientWidth || 760) / (svg.clientHeight || 760);
  if (width / height < screenAspect) width = height * screenAspect;
  else height = width / screenAspect;

  return {
    x: (bounds.minX + bounds.maxX - width) / 2,
    y: (bounds.minY + bounds.maxY - height) / 2,
    width,
    height,
  };
}

function updateDotPattern(view) {
  const screenWidth = svg.clientWidth || 760;
  const unitsPerPixel = view.width / screenWidth;
  const spacing = Math.max(0.8, unitsPerPixel * 7.4);
  const radius = spacing * 0.255;

  pattern.setAttribute("width", spacing);
  pattern.setAttribute("height", spacing);
  patternDot.setAttribute("cx", spacing / 2);
  patternDot.setAttribute("cy", spacing / 2);
  patternDot.setAttribute("r", radius);
  cursorDot.setAttribute("r", radius * 1.75);
}

function applyViewBox(view) {
  currentView = view;
  svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);
  updateDotPattern(view);
}

function animateViewBox(target, duration = 680) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    applyViewBox(target);
    return Promise.resolve();
  }

  const start = { ...currentView };
  const startTime = performance.now();
  isAnimating = true;
  mapCard.classList.add("is-zooming");

  return new Promise((resolve) => {
    function frame(now) {
      const progress = Math.min(1, (now - startTime) / duration);
      const eased = easeInOutCubic(progress);
      const view = {
        x: start.x + (target.x - start.x) * eased,
        y: start.y + (target.y - start.y) * eased,
        width: start.width + (target.width - start.width) * eased,
        height: start.height + (target.height - start.height) * eased,
      };

      applyViewBox(view);

      if (progress < 1) {
        requestAnimationFrame(frame);
      } else {
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
  if (current) {
    const span = document.createElement("span");
    span.className = "current";
    span.textContent = label;
    return span;
  }

  const button = document.createElement("button");
  button.type = "button";
  button.dataset.nav = action;
  button.textContent = label;
  return button;
}

function breadcrumbSeparator() {
  const span = document.createElement("span");
  span.className = "separator";
  span.textContent = "/";
  span.setAttribute("aria-hidden", "true");
  return span;
}

function updateChrome() {
  const items = [];
  const isNationwide = state.level === "province";
  items.push(breadcrumbItem("전국", "nationwide", isNationwide));

  if (state.province) {
    items.push(breadcrumbSeparator());
    items.push(
      breadcrumbItem(
        state.province.name,
        "province",
        state.level === "municipality" && !state.city && !state.leaf,
      ),
    );
  }

  if (state.city) {
    items.push(breadcrumbSeparator());
    items.push(
      breadcrumbItem(
        state.city.name,
        "city",
        state.level === "district" && !state.leaf,
      ),
    );
  }

  if (state.leaf) {
    items.push(breadcrumbSeparator());
    items.push(breadcrumbItem(state.leaf.name, "leaf", true));
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
  state.level = "province";
  state.province = null;
  state.city = null;
  state.leaf = null;
  updateChrome();
  await changeLayer(renderProvinces);
  await animateViewBox({ ...BASE_VIEW });
}

async function goProvince() {
  if (isAnimating || !state.province) return;
  state.level = "municipality";
  state.city = null;
  state.leaf = null;
  updateChrome();
  await changeLayer(() => renderMunicipalities(state.province));
  await animateViewBox(viewForBounds(state.province.bounds, 0.1));
}

async function goCity() {
  if (isAnimating || !state.city) return;
  state.level = "district";
  state.leaf = null;
  updateChrome();
  await changeLayer(() => renderDistricts(state.city));
  await animateViewBox(viewForBounds(state.city.bounds, 0.12));
}

async function goBack() {
  if (state.level === "province") return;
  if (state.level === "municipality") return goNationwide();
  if (state.level === "district") return goProvince();
  if (state.city) return goCity();
  return goProvince();
}

breadcrumb.addEventListener("click", (event) => {
  const action = event.target.closest("button")?.dataset.nav;
  if (action === "nationwide") goNationwide();
  if (action === "province") goProvince();
  if (action === "city") goCity();
});

backButton.addEventListener("click", goBack);
svg.addEventListener("pointerleave", clearHover);
window.addEventListener("resize", () => updateDotPattern(currentView));

renderProvinces();
applyViewBox(BASE_VIEW);
updateChrome();
