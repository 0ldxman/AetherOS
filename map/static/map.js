const COLORS = {
  land: '#2b2f36',
  water: '#0f1b2d',
  forest: '#1f3a2e',
  road: '#5b6573',
  roadCasing: '#15181d',
  building: '#3d444f',
  grid: '#8fb4d9',
};

const GRID_STEP = 10; // шаг сетки в градусах; жирные линии каждые 30°
const DEFAULT_PROVINCE_COLOR = '#cccccc';

let provinceCodes = {}; // adm1_code -> code из БД

const pmtilesProtocol = new pmtiles.Protocol();

maplibregl.addProtocol(
  'pmtiles',
  pmtilesProtocol.tile
);

const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/liberty',
  center: [10, 50],
  zoom: 2,
});

// Глобус по умолчанию (при сильном приближении MapLibre сам переходит в плоский вид)
map.on('style.load', () => {
  map.setProjection({ type: 'globe' });
});

const isBackground = (l) => l.type === 'background';
const isWaterLayer = (l) =>
  l.type === 'fill' && l['source-layer'] === 'water';
const isForestLayer = (l) =>
  l.type === 'fill' &&
  l['source-layer'] === 'landcover' &&
  /wood|forest/i.test(l.id);
const isRoadLayer = (l) =>
  l.type === 'line' && l['source-layer'] === 'transportation';

// Выражение раскраски провинций: adm1_code -> цвет страны
function buildColorExpression(colors) {
  const entries = Object.entries(colors);
  if (entries.length === 0) return DEFAULT_PROVINCE_COLOR;

  const expr = ['match', ['get', 'adm1_code']];
  for (const [code, color] of entries) {
    expr.push(code, color);
  }
  expr.push(DEFAULT_PROVINCE_COLOR);
  return expr;
}

// Загрузка цветов и кодов с сервера и применение к слою заливки
function loadProvinceColors() {
  if (typeof PROVINCE_COLORS_URL === 'undefined') {
    console.error('PROVINCE_COLORS_URL не объявлена в шаблоне');
    return;
  }

  fetch(PROVINCE_COLORS_URL)
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((data) => {
      const colors = {};
      provinceCodes = {};
      for (const [sourceCode, item] of Object.entries(data)) {
        colors[sourceCode] = item.color;
        provinceCodes[sourceCode] = item.code;
      }
      console.log('Цвета провинций загружены:', Object.keys(colors).length);
      map.setPaintProperty('adm1-fill', 'fill-color', buildColorExpression(colors));
    })
    .catch((err) => console.error('Не удалось загрузить цвета провинций', err));
}

// Координатная сетка: меридианы и параллели
function makeGraticule(step) {
  const features = [];

  for (let lng = -180; lng < 180; lng += step) {
    features.push({
      type: 'Feature',
      properties: { major: lng % 30 === 0 },
      geometry: { type: 'LineString', coordinates: [[lng, -85], [lng, 85]] },
    });
  }

  for (let lat = -80; lat <= 80; lat += step) {
    features.push({
      type: 'Feature',
      properties: { major: lat % 30 === 0 },
      geometry: { type: 'LineString', coordinates: [[-180, lat], [180, lat]] },
    });
  }

  return { type: 'FeatureCollection', features };
}

map.on('load', () => {
  const layers = map.getStyle().layers;

  // Для отладки: посмотреть, что было в стиле
  console.table(layers.map(l => ({
    id: l.id,
    type: l.type,
    sourceLayer: l['source-layer'],
  })));

  // Запоминаем источник зданий до удаления: нужен для своего плоского слоя
  const buildingRef = layers.find(l => l['source-layer'] === 'building');

  // Оставляем фон, воду, леса и дороги. Здания из стиля (в том числе 3D) удаляются.
  for (const layer of layers) {
    const keep =
      isBackground(layer) ||
      isWaterLayer(layer) ||
      isForestLayer(layer) ||
      isRoadLayer(layer);

    if (!keep) map.removeLayer(layer.id);
  }

  // Перекраска
  for (const layer of map.getStyle().layers) {
    if (isBackground(layer)) {
      map.setPaintProperty(layer.id, 'background-color', COLORS.land);
    } else if (isWaterLayer(layer)) {
      map.setPaintProperty(layer.id, 'fill-color', COLORS.water);
    } else if (isForestLayer(layer)) {
      map.setPaintProperty(layer.id, 'fill-color', COLORS.forest);
      map.setPaintProperty(layer.id, 'fill-opacity', 1);
    } else if (isRoadLayer(layer)) {
      const color = /casing/i.test(layer.id) ? COLORS.roadCasing : COLORS.road;
      map.setPaintProperty(layer.id, 'line-color', color);
    }
  }

  // Плоские здания: свой fill-слой, вставленный под первую дорогу
  if (buildingRef) {
    const firstRoad = map.getStyle().layers.find(isRoadLayer);

    map.addLayer({
      id: 'buildings-flat',
      type: 'fill',
      source: buildingRef.source,
      'source-layer': 'building',
      minzoom: 13,
      paint: {
        'fill-color': COLORS.building,
        'fill-opacity': 1,
      },
    }, firstRoad ? firstRoad.id : undefined);
  }

  // Острова Aether: кладём наверх
  map.addSource('aether-lands', {
    type: 'geojson',
    data: ISLANDS_URL,
  });

  map.addLayer({
    id: 'aether-lands-fill',
    type: 'fill',
    source: 'aether-lands',
    paint: { 'fill-color': COLORS.land },
  });

  map.addSource('adm1', {
    type: 'vector',
    url: `pmtiles://${ADM1_PMTILES_URL}`,
  });

  // Границы провинций: пунктир
  map.addLayer({
    id: 'adm1-boundaries',
    type: 'line',
    source: 'adm1',
    'source-layer': 'aether_provinces',
    paint: {
      'line-color': '#8fb4d9',
      'line-dasharray': [3, 2],
      'line-width': [
        'interpolate',
        ['linear'],
        ['zoom'],
        1, 0.35,
        3, 0.5,
        5, 0.8,
        8, 1.2,
        12, 1.5,
      ],
      'line-opacity': [
        'interpolate',
        ['linear'],
        ['zoom'],
        1, 0.2,
        3, 0.35,
        5, 0.55,
        8, 0.7,
        11, 0.7,
        14, 0,
      ],
    },
  });

  // Заливка провинций: под границами, ~20% непрозрачности,
  // на больших зумах (8 -> 11) плавно исчезает
  map.addLayer({
    id: 'adm1-fill',
    type: 'fill',
    source: 'adm1',
    'source-layer': 'aether_provinces',
    paint: {
      'fill-color': DEFAULT_PROVINCE_COLOR,
      'fill-opacity': [
        'interpolate',
        ['linear'],
        ['zoom'],
        0, 0.2,
        8, 0.2,
        11, 0,
      ],
    },
  }, 'adm1-boundaries');

  map.on('click', 'adm1-fill', (e) => {
    console.log(e.features[0].properties);
  });

  // Леса, здания и дороги переносим наверх, поверх островов, заливки и границ.
  const overlayIds = map.getStyle().layers
    .filter(l =>
      !isBackground(l) &&
      !isWaterLayer(l) &&
      l.id !== 'aether-lands-fill' &&
      l.id !== 'adm1-fill' &&
      l.id !== 'adm1-boundaries'
    )
    .map(l => l.id);

  overlayIds.forEach(id => map.moveLayer(id));

  // Координатная сетка: самым последним слоем, поверх всего
  map.addSource('graticule', {
    type: 'geojson',
    data: makeGraticule(GRID_STEP),
  });

  map.addLayer({
    id: 'graticule-lines',
    type: 'line',
    source: 'graticule',
    paint: {
      'line-color': COLORS.grid,
      'line-width': ['case', ['get', 'major'], 1, 0.5],
      'line-opacity': ['case', ['get', 'major'], 0.35, 0.15],
    },
  });

  // Цвета стран: в самом конце, чтобы ошибка здесь ничего не ломала
  loadProvinceColors();
});

// Курсор-прицел
const crosshair = document.createElement('div');
crosshair.id = 'crosshair';
crosshair.innerHTML = '<div class="h"></div><div class="v"></div><div class="box"></div>';
document.body.appendChild(crosshair);

// Подпись у курсора: координаты (мелко) и код провинции из БД (чуть крупнее)
const info = document.createElement('div');
info.id = 'cursor-info';
info.innerHTML = '<span class="coords"></span><span class="prov"></span>';
document.body.appendChild(info);

const coordsEl = info.querySelector('.coords');
const provEl = info.querySelector('.prov');

const fmtCoord = (v, pos, neg) => `${Math.abs(v).toFixed(2)}°${v >= 0 ? pos : neg}`;

let infoFrame = 0;
let lastMapEvent = null;

map.on('mousemove', (e) => {
  lastMapEvent = e;
  if (infoFrame) return;
  infoFrame = requestAnimationFrame(() => {
    infoFrame = 0;
    const { lngLat, point } = lastMapEvent;

    coordsEl.textContent =
      Number.isFinite(lngLat.lat) && Number.isFinite(lngLat.lng)
        ? `${fmtCoord(lngLat.lat, 'N', 'S')} ${fmtCoord(lngLat.lng, 'E', 'W')}`
        : '';

    const hit = map.getLayer('adm1-fill')
      ? map.queryRenderedFeatures(point, { layers: ['adm1-fill'] })[0]
      : null;
    provEl.textContent = hit ? (provinceCodes[hit.properties.adm1_code] || '') : '';
  });
});

window.addEventListener('mousemove', (e) => {
  crosshair.style.setProperty('--x', `${e.clientX}px`);
  crosshair.style.setProperty('--y', `${e.clientY}px`);
  crosshair.classList.add('visible');

  info.style.transform = `translate(${e.clientX + 16}px, ${e.clientY + 16}px)`;
  info.classList.add('visible');
});

document.documentElement.addEventListener('mouseleave', () => {
  crosshair.classList.remove('visible');
  info.classList.remove('visible');
});