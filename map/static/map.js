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

// Подписи стран по рангам (ранг задаётся в БД у CountryLabel).
// minzoom - с какого зума подпись видна, size - пары [зум, размер текста].
const LABEL_RANKS = {
  1: { minzoom: 0,   size: [1, 12, 4, 18, 7, 26] },
  2: { minzoom: 2.5, size: [2.5, 10, 5, 15, 8, 22] },
  3: { minzoom: 4,   size: [4, 10, 7, 14, 9, 18] },
  4: { minzoom: 5.5, size: [5.5, 9, 8, 12, 10, 15] },
};
const labelLayerId = (rank) => `country-labels-${rank}`;

// Режимы карты. Для каждого режима перечислены слои, которые видны ТОЛЬКО в нём
// (воду, леса и дороги режимы не трогают). Слой, которого нет в списке
// текущего режима, но есть в списке другого, скрывается.
// Позже сюда добавятся слои названий объектов.
// Режим редактора территорий: /apps/map/?edit=1 (карта внутри админки)
const EDIT_MODE = new URLSearchParams(window.location.search).get('edit') === '1';

const DEFAULT_MODE = 'political';
const MODE_LAYERS = {
  political: [
    'adm1-fill',
    'adm1-boundaries',
    'adm1-selected',
    'adm1-selected-line',
    ...Object.keys(LABEL_RANKS).map(labelLayerId),
  ],
  physical: [],
};

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
  hash: true,
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

// Режим из адреса страницы: ?mode=political|physical (неизвестное значение = по умолчанию)
function getUrlMode() {
  const mode = new URLSearchParams(window.location.search).get('mode');
  return Object.hasOwn(MODE_LAYERS, mode) ? mode : DEFAULT_MODE;
}

let currentMode = getUrlMode();
let layersReady = false; // true, когда все наши слои добавлены в карту

// Показывает слои текущего режима, прячет слои остальных, подсвечивает кнопку
function applyMode() {
  for (const btn of document.querySelectorAll('#mode-panel [data-mode]')) {
    btn.classList.toggle('active', btn.dataset.mode === currentMode);
  }
  if (!layersReady) return;

  const visibleIds = new Set(MODE_LAYERS[currentMode]);
  const allIds = new Set(Object.values(MODE_LAYERS).flat());
  for (const id of allIds) {
    if (!map.getLayer(id)) continue;
    map.setLayoutProperty(id, 'visibility', visibleIds.has(id) ? 'visible' : 'none');
  }
}

// Переключение режима: обновляет карту и пишет ?mode=... в адрес (хэш и ?date= сохраняются)
function setMapMode(mode) {
  if (!Object.hasOwn(MODE_LAYERS, mode)) return;
  currentMode = mode;

  const params = new URLSearchParams(window.location.search);
  params.set('mode', mode);
  history.replaceState(
    history.state,
    '',
    `${window.location.pathname}?${params}${window.location.hash}`
  );

  applyMode();
}

document.querySelectorAll('#mode-panel [data-mode]').forEach((btn) => {
  btn.addEventListener('click', () => setMapMode(btn.dataset.mode));
});
applyMode(); // подсветка кнопки при старте

// Дата из адреса страницы: ?date=YYYY-MM-DD (без параметра - последние владельцы)
function getUrlDate() {
  return new URLSearchParams(window.location.search).get('date');
}

// Добавляет ?date=... к адресу API, если дата есть в адресе страницы
function withDate(url) {
  const date = getUrlDate();
  return date ? `${url}?date=${encodeURIComponent(date)}` : url;
}

// Подписи стран: загрузка точек из БД и показ на карте
function loadCountryLabels() {
  if (typeof COUNTRY_LABELS_URL === 'undefined') {
    console.error('COUNTRY_LABELS_URL не объявлена в шаблоне');
    return;
  }

  fetch(withDate(COUNTRY_LABELS_URL))
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((labels) => {
      map.getSource('country-labels').setData({
        type: 'FeatureCollection',
        features: labels.map((l) => ({
          type: 'Feature',
          properties: { text: l.text, rank: l.rank },
          geometry: { type: 'Point', coordinates: [l.lng, l.lat] },
        })),
      });
    })
    .catch((err) => console.error('Не удалось загрузить подписи стран', err));
}

// Загрузка цветов и кодов с сервера и применение к слою заливки
function loadProvinceColors() {
  if (typeof PROVINCE_COLORS_URL === 'undefined') {
    console.error('PROVINCE_COLORS_URL не объявлена в шаблоне');
    return;
  }

  fetch(withDate(PROVINCE_COLORS_URL))
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

  // Выделение провинций (только в режиме редактора): подсветка и контур.
  // Список выделенных задаётся фильтром, см. applySelection().
  if (EDIT_MODE) {
    const noProvinces = ['in', ['get', 'adm1_code'], ['literal', []]];

    map.addLayer({
      id: 'adm1-selected',
      type: 'fill',
      source: 'adm1',
      'source-layer': 'aether_provinces',
      filter: noProvinces,
      paint: { 'fill-color': '#ffcf4d', 'fill-opacity': 0.45 },
    }, 'graticule-lines');

    map.addLayer({
      id: 'adm1-selected-line',
      type: 'line',
      source: 'adm1',
      'source-layer': 'aether_provinces',
      filter: noProvinces,
      paint: { 'line-color': '#ffcf4d', 'line-width': 2 },
    }, 'graticule-lines');
  }

  // Названия стран: самыми верхними слоями, по одному слою на ранг.
  // Слои добавляются от мелкого ранга к крупному: верхний слой первым
  // занимает место, поэтому при пересечении побеждает более крупная страна.
  map.addSource('country-labels', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  });

  for (const rank of Object.keys(LABEL_RANKS).sort((a, b) => b - a)) {
    const style = LABEL_RANKS[rank];
    map.addLayer({
      id: labelLayerId(rank),
      type: 'symbol',
      source: 'country-labels',
      minzoom: style.minzoom,
      filter: ['==', ['get', 'rank'], Number(rank)],
      layout: {
        'text-field': ['get', 'text'],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], ...style.size],
        'text-transform': 'uppercase',
        'text-letter-spacing': 0.15,
        'text-max-width': 8,
      },
      paint: {
        'text-color': '#dce6f0',
        'text-halo-color': '#05070a',
        'text-halo-width': 1.5,
        'text-opacity': ['interpolate', ['linear'], ['zoom'], 0, 0.85, 8, 0.85, 10, 0],
      },
    });
  }

  // Режим карты (слои уже все на месте)
  layersReady = true;
  applyMode();
  applySelection();

  // Цвета стран: в самом конце, чтобы ошибка здесь ничего не ломала
  loadProvinceColors();
  loadCountryLabels();
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

// ---------------------------------------------------------------------------
// Режим выбора точки: /apps/map/?pick=1
// Карта открыта внутри админки (iframe). Клик ставит маркер и отправляет
// координаты родительской странице; родитель может прислать координаты обратно
// (например, когда их ввели руками), тогда маркер сдвигается.
// Сообщения принимаются и отправляются только в рамках одного адреса сайта.
// ---------------------------------------------------------------------------
const PICK_MODE = new URLSearchParams(window.location.search).get('pick') === '1';
let pickMarker = null;

function setPickPoint(lng, lat) {
  if (!pickMarker) {
    const el = document.createElement('div');
    el.className = 'pick-marker';
    pickMarker = new maplibregl.Marker({ element: el });
  }
  pickMarker.setLngLat([lng, lat]).addTo(map);
}

function clearPickPoint() {
  if (pickMarker) {
    pickMarker.remove();
    pickMarker = null;
  }
}

if (PICK_MODE) {
  map.on('click', (e) => {
    const { lng, lat } = e.lngLat.wrap();
    setPickPoint(lng, lat);
    window.parent.postMessage({ type: 'aether-map-pick', lng, lat }, window.location.origin);
  });

  window.addEventListener('message', (e) => {
    if (e.origin !== window.location.origin || e.source !== window.parent) return;
    const d = e.data || {};
    if (d.type !== 'aether-map-set') return;

    if (Number.isFinite(d.lng) && Number.isFinite(d.lat)) {
      setPickPoint(d.lng, d.lat);
      map.easeTo({ center: [d.lng, d.lat], zoom: Math.max(map.getZoom(), 3) });
    } else {
      clearPickPoint();
    }
  });

  // Сообщаем родителю, что карта готова принимать координаты
  window.parent.postMessage({ type: 'aether-map-ready' }, window.location.origin);
}

// ---------------------------------------------------------------------------
// Режим редактора территорий: /apps/map/?edit=1
// Карта открыта внутри админки. Клик по провинции отправляется родительской
// странице (она хранит выделение), родитель присылает список выделенных
// провинций обратно, и карта их подсвечивает.
// ---------------------------------------------------------------------------
let selectionCodes = []; // adm1_code выделенных провинций

function applySelection() {
  if (!EDIT_MODE || !layersReady || !map.getLayer('adm1-selected')) return;

  const filter = ['in', ['get', 'adm1_code'], ['literal', selectionCodes]];
  map.setFilter('adm1-selected', filter);
  map.setFilter('adm1-selected-line', filter);
}

if (EDIT_MODE) {
  map.on('click', 'adm1-fill', (e) => {
    const code = e.features[0].properties.adm1_code;
    const ev = e.originalEvent;
    const toggle = ev.shiftKey || ev.ctrlKey || ev.metaKey;
    window.parent.postMessage(
      { type: 'aether-map-province-click', code, toggle },
      window.location.origin
    );
  });

  window.addEventListener('message', (e) => {
    if (e.origin !== window.location.origin || e.source !== window.parent) return;
    const d = e.data || {};

    if (d.type === 'aether-map-selection' && Array.isArray(d.codes)) {
      selectionCodes = d.codes;
      applySelection();
    }
  });

  // Сообщаем родителю, что карта готова: он пришлёт текущее выделение
  window.parent.postMessage({ type: 'aether-map-ready' }, window.location.origin);
}