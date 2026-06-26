const canvas = document.getElementById("trafficCanvas");
const ctx = canvas.getContext("2d");

let width = 0;
let height = 0;
let dpr = 1;

const roads = [
  { a: [0.05, 0.78], b: [0.96, 0.2], color: "#2f4858" },
  { a: [0.0, 0.42], b: [1.0, 0.62], color: "#334f62" },
  { a: [0.18, 0.0], b: [0.62, 1.0], color: "#2f4858" },
  { a: [0.68, 0.0], b: [0.38, 1.0], color: "#334f62" },
  { a: [0.0, 0.18], b: [0.92, 0.92], color: "#293f4d" },
];

const nodes = [
  [0.2, 0.68],
  [0.36, 0.49],
  [0.52, 0.6],
  [0.7, 0.36],
  [0.82, 0.55],
  [0.44, 0.24],
];

function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  width = canvas.clientWidth;
  height = canvas.clientHeight;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function point(pair) {
  return [pair[0] * width, pair[1] * height];
}

function drawRoad(road) {
  const [x1, y1] = point(road.a);
  const [x2, y2] = point(road.b);

  ctx.lineCap = "round";
  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
  ctx.lineWidth = 34;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();

  ctx.strokeStyle = road.color;
  ctx.lineWidth = 26;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();

  ctx.strokeStyle = "rgba(255, 255, 255, 0.34)";
  ctx.lineWidth = 2;
  ctx.setLineDash([18, 20]);
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawVehicle(road, offset, color) {
  const [x1, y1] = point(road.a);
  const [x2, y2] = point(road.b);
  const x = x1 + (x2 - x1) * offset;
  const y = y1 + (y2 - y1) * offset;
  const angle = Math.atan2(y2 - y1, x2 - x1);

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 16;
  ctx.fillRect(-9, -4, 18, 8);
  ctx.restore();
}

function drawNodes(time) {
  nodes.forEach(([nx, ny], index) => {
    const x = nx * width;
    const y = ny * height;
    const pulse = 0.5 + Math.sin(time / 650 + index) * 0.5;

    ctx.fillStyle = `rgba(119, 224, 213, ${0.14 + pulse * 0.14})`;
    ctx.beginPath();
    ctx.arc(x, y, 30 + pulse * 12, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = index % 2 === 0 ? "#77e0d5" : "#f0a424";
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
  });
}

function render(time = 0) {
  ctx.clearRect(0, 0, width, height);

  const background = ctx.createLinearGradient(0, 0, width, height);
  background.addColorStop(0, "#111f2a");
  background.addColorStop(0.55, "#16323a");
  background.addColorStop(1, "#24333a");
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, width, height);

  roads.forEach(drawRoad);
  drawNodes(time);

  roads.forEach((road, index) => {
    const base = (time / (4600 + index * 500) + index * 0.18) % 1;
    drawVehicle(road, base, index % 2 === 0 ? "#77e0d5" : "#f0a424");
    drawVehicle(road, (base + 0.46) % 1, index % 2 === 0 ? "#f0a424" : "#78a7ff");
  });

  requestAnimationFrame(render);
}

resize();
window.addEventListener("resize", resize);
requestAnimationFrame(render);
