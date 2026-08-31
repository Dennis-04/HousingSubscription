const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const INPUT = path.join(ROOT, "assets", "sgg.json");
const OUTPUT = path.join(ROOT, "assets", "regions-paths.js");
const MAP_SIZE = 1000;
const PADDING = 56;
const GWANGJU_CODES = new Set(["12210", "12240", "12270", "12300", "12330"]);

const source = JSON.parse(fs.readFileSync(INPUT, "utf8"));

function mercator([longitude, latitude]) {
  const lambda = (longitude * Math.PI) / 180;
  const phi = (Math.max(-85, Math.min(85, latitude)) * Math.PI) / 180;
  return [lambda, Math.log(Math.tan(Math.PI / 4 + phi / 2))];
}

function visitCoordinates(geometry, callback) {
  if (geometry.type === "Polygon") {
    geometry.coordinates.forEach((ring) => ring.forEach(callback));
  } else {
    geometry.coordinates.forEach((polygon) =>
      polygon.forEach((ring) => ring.forEach(callback)),
    );
  }
}

const world = [Infinity, Infinity, -Infinity, -Infinity];
source.features.forEach((feature) => {
  visitCoordinates(feature.geometry, (coordinate) => {
    const [x, y] = mercator(coordinate);
    world[0] = Math.min(world[0], x);
    world[1] = Math.min(world[1], y);
    world[2] = Math.max(world[2], x);
    world[3] = Math.max(world[3], y);
  });
});

const scale = Math.min(
  (MAP_SIZE - PADDING * 2) / (world[2] - world[0]),
  (MAP_SIZE - PADDING * 2) / (world[3] - world[1]),
);
const width = (world[2] - world[0]) * scale;
const height = (world[3] - world[1]) * scale;
const offsetX = (MAP_SIZE - width) / 2;
const offsetY = (MAP_SIZE - height) / 2;

function project(coordinate) {
  const [x, y] = mercator(coordinate);
  return [
    offsetX + (x - world[0]) * scale,
    offsetY + (world[3] - y) * scale,
  ];
}

function ringPath(ring, bounds) {
  return ring
    .map((coordinate, index) => {
      const [x, y] = project(coordinate);
      bounds[0] = Math.min(bounds[0], x);
      bounds[1] = Math.min(bounds[1], y);
      bounds[2] = Math.max(bounds[2], x);
      bounds[3] = Math.max(bounds[3], y);
      return `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join("") + "Z";
}

function geometryPath(geometry) {
  const bounds = [Infinity, Infinity, -Infinity, -Infinity];
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  const d = polygons
    .flatMap((polygon) => polygon.map((ring) => ringPath(ring, bounds)))
    .join("");
  return { d, bounds: bounds.map((value) => Number(value.toFixed(1))) };
}

function province(properties) {
  if (properties.sidonm !== "전남광주통합특별시") {
    return [properties.sido, properties.sidonm];
  }
  return GWANGJU_CODES.has(properties.sgg)
    ? ["29", "광주광역시"]
    : ["46", "전라남도"];
}

const compiled = source.features.map((feature) => {
  const shape = geometryPath(feature.geometry);
  const area = feature.properties;
  return {
    c: area.sgg,
    n: area.sggnm,
    p: province(area),
    b: shape.bounds,
    d: shape.d,
  };
});

fs.writeFileSync(
  OUTPUT,
  `window.KOREA_REGION_PATHS=${JSON.stringify(compiled)};\n`,
);

console.log(`Compiled ${compiled.length} regions to ${path.relative(ROOT, OUTPUT)}`);
