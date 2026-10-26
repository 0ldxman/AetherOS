const DEFAULT_COLORS = {
  land: '#2b2f36',
  water: '#0f1b2d',
  forest: '#1f3a2e',
  road: '#5b6573',
  roadCasing: '#15181d',
  building: '#3d444f',
  grid: '#8fb4d9',
};

// Тема встроенной карты (?theme=print|term, её выбирает виджет ::map по стилю документа):
// print: карта на бумаге для doc, scan и светлого web; term: терминальная для rec и инфобокса
const THEME = new URLSearchParams(window.location.search).get('theme');
const accentToken = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#3fd0ff';

const THEMES = {
  print: {
    colors: {
      land: '#e8dfcb', water: '#c9d4d6', forest: '#d9d8b8', road: '#a89a80',
      roadCasing: '#e8dfcb', building: '#cfc4ac', grid: '#7a6a4f',
    },
    boundary: '#6b5b3e',
    provinceOpacity: 0.28,
    keepCountryColors: true,
    labelText: '#2e2518',
    labelHalo: '#e8dfcb',
    region: '#b3261e',
    dim: '#e8dfcb',
  },
  term: {
    colors: {
      land: '#0d1717', water: '#060b0b', forest: '#0f1f1d', road: '#1f4a49',
      roadCasing: '#0a1211', building: '#143231', grid: accentToken,
    },
    boundary: accentToken,
    provinceOpacity: 0.12,
    keepCountryColors: false,
    labelText: accentToken,
    labelHalo: '#050909',
    region: accentToken,
    dim: '#050909',
  },
};

THEMES.scan = THEMES.print;   // scan: та же бумажная карта, отличаются только метки
const THEME_STYLE = THEMES[THEME] || null;

// Цвета выделения и меток из разметки виджета (red, blue...). Те же имена и значения у легенды
// в wiki/static/wiki/blocks.css (--mc-*): при правке менять оба места, тест следит за совпадением.
const MARK_COLORS = {
  print: {
    red: '#b00d1c', blue: '#12307a', green: '#14612a', orange: '#b85200',
    purple: '#5a1f8a', yellow: '#b88a00', teal: '#0e6b6b', grey: '#2f2c28',
  },
  term: {
    red: '#ff5a5f', blue: '#5aa9ff', green: '#3fe0a0', orange: '#ffa13d',
    purple: '#b58cff', yellow: '#ffd84d', teal: '#3fd0ff', grey: '#9aa5a5',
  },
};
const markPalette = MARK_COLORS[THEME === 'term' || !THEME_STYLE ? 'term' : 'print'];
const markColor = (name, fallback) => markPalette[name] || fallback;
const COLORS = THEME_STYLE ? THEME_STYLE.colors : DEFAULT_COLORS;

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

// Встроенная карта (виджет ::map в документе): ?embed=1 без панелей, &static=1 без управления
const SEARCH = new URLSearchParams(window.location.search);
const EMBED = SEARCH.get('embed') === '1';
const STATIC_VIEW = EMBED && SEARCH.get('static') === '1';
// ?regions=adm1_code[:цвет],...
const REGION_ITEMS = EMBED
  ? (SEARCH.get('regions') || '').split(',').filter(Boolean).map((raw) => {
      const [code, color, link] = raw.split(':');
      return { code, color, url: link ? decodeURIComponent(link) : '' };
    })
  : [];
// Камера сохранённой карты: ?bounds=w,s,e,n ограничивает область, minzoom/maxzoom пределы, flat=1 плоская карта
const CAMERA_BOUNDS = EMBED ? (SEARCH.get('bounds') || '').split(',').map(Number) : [];
const CAMERA_LIMITED = CAMERA_BOUNDS.length === 4 && CAMERA_BOUNDS.every(Number.isFinite);
const numberParam = (name) => (SEARCH.get(name) === null || SEARCH.get(name) === '' ? undefined : Number(SEARCH.get(name)));
const FLAT_VIEW = EMBED && SEARCH.get('flat') === '1';
// Редактор сохранённой карты: /apps/map/?embed=1&scene_edit=1 внутри админки (инструменты и свойства у родителя)
const SCENE_EDIT = EMBED && SEARCH.get('scene_edit') === '1';
const MARKERS = EMBED
  ? SEARCH.getAll('m').map((raw) => {
      const [lat, lon, color, link, ...label] = raw.split(',');
      return { lat: Number(lat), lon: Number(lon), color, url: link ? decodeURIComponent(link.replace(/\+/g, ' ')) : '', label: label.join(',') };
    }).filter((m) => Number.isFinite(m.lat) && Number.isFinite(m.lon))
  : [];
const PROVINCE_NAMES = EMBED && SEARCH.get('labels') !== '0';
const PROVINCE_OPACITY = THEME_STYLE ? THEME_STYLE.provinceOpacity : 0.2;
if (EMBED) document.body.classList.add('embed');
if (EMBED && THEME === 'scan') {
  // шероховатость линий: края слегка гуляют, как у шариковой ручки на бумаге
  document.body.insertAdjacentHTML('beforeend',
    '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><filter id="pen-rough">' +
    '<feTurbulence type="fractalNoise" baseFrequency="0.07" numOctaves="2" seed="4" result="n"/>' +
    '<feDisplacementMap in="SourceGraphic" in2="n" scale="2" xChannelSelector="R" yChannelSelector="G"/>' +
    '</filter></svg>');
}
if (THEME) document.body.classList.add('theme-' + THEME);

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
  interactive: !STATIC_VIEW,
  attributionControl: !EMBED,
  ...(EMBED && numberParam('minzoom') !== undefined ? { minZoom: numberParam('minzoom') } : {}),
  ...(EMBED && numberParam('maxzoom') !== undefined ? { maxZoom: numberParam('maxzoom') } : {}),
  ...(CAMERA_LIMITED ? { maxBounds: [[CAMERA_BOUNDS[0], CAMERA_BOUNDS[1]], [CAMERA_BOUNDS[2], CAMERA_BOUNDS[3]]] } : {}),
});

// Глобус по умолчанию (при сильном приближении MapLibre сам переходит в плоский вид)
map.on('style.load', () => {
  map.setProjection({ type: FLAT_VIEW ? 'mercator' : 'globe' });
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
      // терминальная тема одноцветная: цвета стран ей не нужны
      if (!THEME_STYLE || THEME_STYLE.keepCountryColors) {
        map.setPaintProperty('adm1-fill', 'fill-color', buildColorExpression(colors));
      }
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
      'line-color': THEME_STYLE ? THEME_STYLE.boundary : '#8fb4d9',
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
      'line-opacity': THEME_STYLE
        ? ['interpolate', ['linear'], ['zoom'], 1, 0.45, 3, 0.65, 5, 0.85, 8, 0.95, 11, 0.95, 14, 0]
        : [
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
        0, PROVINCE_OPACITY,
        8, PROVINCE_OPACITY,
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

// Выделение провинций виджета ::map: выбранные залиты и обведены, остальные притушены.
// Слои есть всегда (во встроенной карте), состав выделения задаёт setRegions(): из адреса
// (?regions=adm1_code[:цвет[:ссылка]]) и из пометок сохранённой карты, которые приходят позже.
if (EMBED) {
  const nothing = ['in', ['get', 'adm1_code'], ['literal', []]];

  map.addLayer({
    id: 'regions-dim',
    type: 'fill',
    source: 'adm1',
    'source-layer': 'aether_provinces',
    filter: nothing,
    layout: { visibility: 'none' },
    paint: { 'fill-color': THEME_STYLE ? THEME_STYLE.dim : '#0f1b2d', 'fill-opacity': 0.55 },
  });
  map.addLayer({
    id: 'regions-fill',
    type: 'fill',
    source: 'adm1',
    'source-layer': 'aether_provinces',
    filter: nothing,
    paint: { 'fill-color': '#ffcf4d', 'fill-opacity': 0.4 },
  });
  map.addLayer({
    id: 'regions-line',
    type: 'line',
    source: 'adm1',
    'source-layer': 'aether_provinces',
    filter: nothing,
    paint: { 'line-color': '#ffcf4d', 'line-width': 2.2 },
  });
}

// Названия провинций во встроенной карте (?labels=0 отключает): с зума 4, выделенные заметнее
if (PROVINCE_NAMES) {
  const textColor = THEME_STYLE ? THEME_STYLE.labelText : '#dce6f0';
  const halo = THEME_STYLE ? THEME_STYLE.labelHalo : '#05070a';

  map.addLayer({
    id: 'province-names',
    type: 'symbol',
    source: 'adm1',
    'source-layer': 'aether_provinces',
    minzoom: 4,
    layout: {
      'text-field': ['coalesce', ['get', 'name_ru'], ['get', 'name']],
      'text-font': ['Noto Sans Regular'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 4, 9, 7, 12, 10, 15],
      'text-max-width': 7,
    },
    paint: {
      'text-color': textColor,
      'text-halo-color': halo,
      'text-halo-width': 1.4,
      'text-opacity': ['interpolate', ['linear'], ['zoom'], 4, 0.75, 7, 0.95],
    },
  });
}

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
        'text-color': THEME_STYLE ? THEME_STYLE.labelText : '#dce6f0',
        'text-halo-color': THEME_STYLE ? THEME_STYLE.labelHalo : '#05070a',
        'text-halo-width': 1.5,
        'text-opacity': ['interpolate', ['linear'], ['zoom'], 0, 0.85, 8, 0.85, 10, 0],
      },
    });
  }

  // Режим карты (слои уже все на месте)
  layersReady = true;
  applyMode();
  applySelection();
  setRegions([]);
  applyScene();

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

// ---------------------------------------------------------------------------
// Встроенная карта (виджет ::map): нумерованные метки и сообщения родителю о текущем виде,
// по которым страница документа обновляет масштаб и координаты в подписи
// ---------------------------------------------------------------------------
if (EMBED) {
  MARKERS.forEach((item, index) => addMarker(item, index));

  const reportView = () => {
    const c = map.getCenter();
    window.parent.postMessage({
      type: 'aether-map-view',
      lat: c.lat,
      lon: c.lng,
      zoom: map.getZoom(),
      width: map.getContainer().clientWidth,
    }, window.location.origin);
  };

  map.on('load', reportView);
  map.on('moveend', reportView);
}


// ---------------------------------------------------------------------------
// Сохранённая карта (::map scene=слаг): родитель присылает пометки, карта их рисует
// ---------------------------------------------------------------------------
let sceneFeatures = [];   // пометки, уже отфильтрованные сервером по ключам игрока
let regionLinks = new Map();

// Ссылки открывает страница-родитель (окно рабочего стола или обычный переход)
function postLink(url, label) {
  if (url) window.parent.postMessage({ type: 'aether-map-link', url, label: label || '' }, window.location.origin);
}

// Выделение провинций: адрес карты плюс пометки сцены (у последней записи провинции приоритет)
function setRegions(extra) {
  if (!EMBED || !map.getLayer('regions-fill')) return;

  const base = THEME_STYLE ? THEME_STYLE.region : '#ffcf4d';
  const items = new Map();
  for (const item of [...REGION_ITEMS, ...extra]) items.set(item.code, item);

  regionLinks = new Map([...items].filter(([, item]) => item.url).map(([code, item]) => [code, item]));
  const codes = [...items.keys()];
  const inRegions = ['in', ['get', 'adm1_code'], ['literal', codes]];

  const byColor = ['match', ['get', 'adm1_code']];
  for (const [code, item] of items) byColor.push(code, markColor(item.color, base));
  byColor.push(base);

  map.setFilter('regions-fill', inRegions);
  map.setFilter('regions-line', inRegions);
  map.setFilter('regions-dim', ['!', inRegions]);
  map.setLayoutProperty('regions-dim', 'visibility', codes.length ? 'visible' : 'none');
  map.setPaintProperty('regions-fill', 'fill-color', codes.length ? byColor : base);
  map.setPaintProperty('regions-line', 'line-color', codes.length ? byColor : base);
}

if (EMBED) {
  // клик по выделенной провинции открывает её ссылку
  map.on('click', 'regions-fill', (e) => {
    const feature = e.features && e.features[0];
    const item = feature && regionLinks.get(feature.properties.adm1_code);
    if (item) postLink(item.url, item.label);
  });
  map.on('mousemove', 'regions-fill', (e) => {
    const feature = e.features && e.features[0];
    map.getCanvas().style.cursor = feature && regionLinks.has(feature.properties.adm1_code) ? 'pointer' : '';
  });
  map.on('mouseleave', 'regions-fill', () => { map.getCanvas().style.cursor = ''; });
}

const SCENE_SOURCE = 'scene-shapes';
let sceneMarkers = [];

// Круг заданного радиуса: многоугольник из 64 точек по сфере
function circlePolygon(lon, lat, km) {
  const ring = [];
  const d = km / 6371;
  const phi = (lat * Math.PI) / 180;
  const lam = (lon * Math.PI) / 180;
  for (let i = 0; i <= 64; i += 1) {
    const brg = (i / 64) * 2 * Math.PI;
    const p2 = Math.asin(Math.sin(phi) * Math.cos(d) + Math.cos(phi) * Math.sin(d) * Math.cos(brg));
    const l2 = lam + Math.atan2(Math.sin(brg) * Math.sin(d) * Math.cos(phi), Math.cos(d) - Math.sin(phi) * Math.sin(p2));
    ring.push([(((l2 * 180) / Math.PI + 540) % 360) - 180, (p2 * 180) / Math.PI]);
  }
  return ring;
}

// Направление последнего отрезка линии, градусы по часовой от севера (для наконечника стрелки)
function bearing(a, b) {
  const dx = (b[0] - a[0]) * Math.cos(((a[1] + b[1]) / 2) * Math.PI / 180);
  const dy = b[1] - a[1];
  return (Math.atan2(dx, dy) * 180) / Math.PI;
}

function sceneColor(name) {
  return markColor(name, THEME_STYLE ? THEME_STYLE.region : '#ffcf4d');
}

function ensureSceneLayers() {
  if (map.getSource(SCENE_SOURCE)) return;

  if (!map.hasImage('scene-arrow')) {
    const size = 32;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    ctx.moveTo(size / 2, 2);
    ctx.lineTo(size - 4, size - 4);
    ctx.lineTo(size / 2, size - 11);
    ctx.lineTo(4, size - 4);
    ctx.closePath();
    ctx.fill();
    map.addImage('scene-arrow', ctx.getImageData(0, 0, size, size), { sdf: true });
  }

  map.addSource(SCENE_SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  const halo = THEME_STYLE ? THEME_STYLE.labelHalo : '#05070a';
  const text = THEME_STYLE ? THEME_STYLE.labelText : '#dce6f0';
  const before = map.getLayer('graticule-lines') ? 'graticule-lines' : undefined;

  map.addLayer({ id: 'scene-fill', type: 'fill', source: SCENE_SOURCE,
    filter: ['all', ['==', ['geometry-type'], 'Polygon'], ['==', ['get', 'fill'], true]],
    paint: { 'fill-color': ['get', 'c'], 'fill-opacity': 0.25 } }, before);
  map.addLayer({ id: 'scene-outline', type: 'line', source: SCENE_SOURCE,
    filter: ['==', ['geometry-type'], 'Polygon'],
    paint: { 'line-color': ['get', 'c'], 'line-width': 2 } }, before);
  map.addLayer({ id: 'scene-lines', type: 'line', source: SCENE_SOURCE,
    filter: ['all', ['==', ['geometry-type'], 'LineString'], ['!=', ['get', 'dash'], true]],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'c'], 'line-width': ['get', 'w'] } }, before);
  map.addLayer({ id: 'scene-lines-dashed', type: 'line', source: SCENE_SOURCE,
    filter: ['all', ['==', ['geometry-type'], 'LineString'], ['==', ['get', 'dash'], true]],
    paint: { 'line-color': ['get', 'c'], 'line-width': ['get', 'w'], 'line-dasharray': [2, 1.5] } }, before);
  map.addLayer({ id: 'scene-arrows', type: 'symbol', source: SCENE_SOURCE,
    filter: ['==', ['get', 'role'], 'head'],
    layout: { 'icon-image': 'scene-arrow', 'icon-rotate': ['get', 'bearing'], 'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true, 'icon-ignore-placement': true, 'icon-size': ['+', 0.45, ['*', ['get', 'w'], 0.06]] },
    paint: { 'icon-color': ['get', 'c'] } }, before);
  map.addLayer({ id: 'scene-text', type: 'symbol', source: SCENE_SOURCE,
    filter: ['==', ['get', 'role'], 'text'],
    layout: { 'text-field': ['get', 't'], 'text-font': ['Noto Sans Regular'], 'text-size': ['get', 'size'],
      'text-anchor': 'top', 'text-offset': [0, 0.4], 'text-max-width': 12, 'text-allow-overlap': true },
    paint: { 'text-color': ['get', 'c'], 'text-halo-color': halo, 'text-halo-width': 1.4 } });

  // клик по фигуре открывает её ссылку
  for (const id of ['scene-fill', 'scene-outline', 'scene-lines', 'scene-lines-dashed', 'scene-arrows']) {
    map.on('click', id, (e) => {
      const feature = e.features && e.features[0];
      if (feature && feature.properties.url) postLink(feature.properties.url, feature.properties.label);
    });
    map.on('mouseenter', id, (e) => {
      const feature = e.features && e.features[0];
      if (feature && feature.properties.url) map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
  }
  void text;
}

function applyScene() {
  if (!EMBED || !layersReady) return;

  ensureSceneLayers();
  const shapes = [];
  const regions = [];
  sceneMarkers.forEach((marker) => marker.remove());
  sceneMarkers = [];

  for (const item of sceneFeatures) {
    const c = sceneColor(item.color);
    const common = { c, url: item.url || '', label: item.label || '', fid: item.id || '' };

    if (item.type === 'regions') {
      for (const code of item.codes) regions.push({ code, color: item.color, url: item.url || '', label: item.label || '' });
    } else if (item.type === 'line' || item.type === 'arrow') {
      const w = item.width || 3;
      shapes.push({ type: 'Feature', properties: { ...common, w, dash: !!item.dash },
        geometry: { type: 'LineString', coordinates: item.coords } });
      if (item.type === 'arrow') {
        const n = item.coords.length;
        shapes.push({ type: 'Feature', properties: { ...common, w, role: 'head', bearing: bearing(item.coords[n - 2], item.coords[n - 1]) },
          geometry: { type: 'Point', coordinates: item.coords[n - 1] } });
      }
    } else if (item.type === 'polygon') {
      const ring = [...item.coords, item.coords[0]];
      shapes.push({ type: 'Feature', properties: { ...common, fill: item.fill !== false },
        geometry: { type: 'Polygon', coordinates: [ring] } });
    } else if (item.type === 'circle') {
      shapes.push({ type: 'Feature', properties: { ...common, fill: item.fill !== false },
        geometry: { type: 'Polygon', coordinates: [circlePolygon(item.coords[0], item.coords[1], item.radius_km)] } });
    } else if (item.type === 'text') {
      shapes.push({ type: 'Feature', properties: { c, role: 'text', t: item.text, size: item.size || 13 },
        geometry: { type: 'Point', coordinates: item.coords } });
    } else if (item.type === 'marker') {
      sceneMarkers.push(addMarker(item, null, SCENE_EDIT ? {
        selected: item.id === editor.selectedId,
        onSelect: () => editor.select(item.id),
        onMove: (point) => editor.patch(item.id, { coords: point }),
      } : {}));
    }

    // подпись фигуры у первой точки
    if (item.label && ['line', 'arrow', 'polygon', 'circle'].includes(item.type)) {
      const at = item.type === 'circle' ? item.coords : item.coords[0];
      shapes.push({ type: 'Feature', properties: { c, role: 'text', t: item.label, size: 12 },
        geometry: { type: 'Point', coordinates: at } });
    }
  }

  map.getSource(SCENE_SOURCE).setData({ type: 'FeatureCollection', features: shapes });
  setRegions(regions);
}

window.addEventListener('message', (e) => {
  if (!EMBED || e.origin !== window.location.origin || e.source !== window.parent) return;
  const d = e.data || {};
  if (d.type === 'aether-map-scene' && Array.isArray(d.features)) {
    sceneFeatures = d.features;
    applyScene();
  }
});

if (EMBED) {
  map.on('load', () => window.parent.postMessage({ type: 'aether-map-ready' }, window.location.origin));
}


// Метка на карте. index: номер (метки из строк ::map) или null (метки сохранённой карты:
// без номера, с подписью рядом). Вид зависит от темы документа: у scan крестик ручкой.
function addMarker(item, index, opts = {}) {
  const lon = item.coords ? item.coords[0] : item.lon;
  const lat = item.coords ? item.coords[1] : item.lat;
  const seed = index === null ? Math.abs(Math.round(lon * 7 + lat * 13)) : index;
  const numbered = index !== null;
  const text = numbered ? String(index + 1) : '';

  // внешний элемент двигает MapLibre (transform), вид и наклон у вложенного
  const el = document.createElement('div');
  el.title = item.label || '';
  const tag = document.createElement('span');
  tag.className = 'embed-marker';
  if (numbered) tag.setAttribute('aria-label', text);
  tag.style.setProperty('--tilt', `${[-4, 3, -2, 5][seed % 4]}deg`);
  if (markPalette[item.color]) tag.style.setProperty('--mc', markPalette[item.color]);

  if (THEME === 'scan') {
    // пометка красной ручкой: маленький крестик, нарисованный от руки в два росчерка, и номер рядом
    tag.classList.add('embed-marker--pen');
    const crosses = [
      ['M4 5 C9 10 14 15 21 22', 'M21 4 C16 9 10 15 5 21'],
      ['M5 4 C10 11 15 16 20 23', 'M22 6 C17 10 11 16 4 20'],
      ['M3 6 C9 10 16 16 22 21', 'M20 3 C15 9 11 15 6 22'],
    ];
    const [first, second] = crosses[seed % crosses.length];
    tag.innerHTML =
      '<svg viewBox="0 0 26 26" aria-hidden="true">' +
      `<path d="${first}"/><path d="${second}"/></svg>` +
      (numbered ? `<span class="pen-n">${text}</span>` : '');
  } else {
    tag.dataset.n = text;
  }

  el.appendChild(tag);

  if (!numbered && item.label) {
    const label = document.createElement('span');
    label.className = 'marker-label';
    label.textContent = item.label;
    el.appendChild(label);
  }

  if (opts.onSelect) {
    // редактор: метку можно выбрать кликом и двигать
    el.classList.add('marker-edit');
    el.addEventListener('click', (event) => { event.stopPropagation(); opts.onSelect(); });
  } else if (item.url) {
    el.classList.add('marker-link');
    el.addEventListener('click', (event) => {
      event.stopPropagation();
      postLink(item.url, item.label);
    });
  }

  // остриё булавки стоит на точке; крест от руки центрируется на ней
  const marker = new maplibregl.Marker({ element: el, anchor: THEME === 'scan' ? 'center' : 'bottom', draggable: !!opts.onMove })
    .setLngLat([lon, lat])
    .addTo(map);
  if (opts.onMove) marker.on('dragend', () => { const p = marker.getLngLat(); opts.onMove([p.lng, p.lat]); });
  if (opts.selected) el.classList.add('is-selected');
  return marker;
}


// ---------------------------------------------------------------------------
// Редактор сохранённой карты (?scene_edit=1). Родитель (админка) шлёт сообщения:
//   aether-scene-load {features}   aether-scene-tool {tool}   aether-scene-select {id}
//   aether-scene-update {id, patch}   aether-scene-delete {id}   aether-scene-camera
// карта отвечает: aether-scene-features {features}, aether-scene-selected {id, feature},
//   aether-scene-view {lat, lon, zoom, bounds}.
// ---------------------------------------------------------------------------
const editor = {
  features: [],
  tool: 'select',
  selectedId: null,
  draft: null,          // {type, coords, cursor} пока рисуется линия, фигура или круг
  handles: [],
  nextId: 1,

  newId() { this.nextId += 1; return `f${this.nextId}`; },

  // пометки без служебного id уходят родителю
  emit() {
    const features = this.features.map(({ id, ...rest }) => rest);
    window.parent.postMessage({ type: 'aether-scene-features', features }, window.location.origin);
  },

  emitSelected() {
    const feature = this.features.find((f) => f.id === this.selectedId) || null;
    window.parent.postMessage({ type: 'aether-scene-selected', id: this.selectedId, feature }, window.location.origin);
  },

  load(features) {
    this.features = (features || []).map((f) => ({ ...f, id: this.newId() }));
    this.selectedId = null;
    this.render();
  },

  // выделения предпросмотра: код провинции из БД (RUS-32) или страна по префиксу (POL)
  codesFor(token) {
    const key = String(token || '').toUpperCase();
    return Object.entries(provinceCodes)
      .filter(([, code]) => String(code).toUpperCase() === key || String(code).toUpperCase().startsWith(`${key}-`))
      .map(([source]) => source);
  },

  render() {
    sceneFeatures = this.features.map((f) => (f.type === 'region'
      ? { ...f, type: 'regions', codes: this.codesFor(f.token) }
      : f));
    applyScene();
    this.drawHandles();
    this.drawDraft();
  },

  select(id) {
    this.selectedId = id;
    this.render();
    this.emitSelected();
  },

  patch(id, change) {
    const feature = this.features.find((f) => f.id === id);
    if (!feature) return;
    Object.assign(feature, change);
    for (const key of Object.keys(change)) if (change[key] === '' || change[key] === null) delete feature[key];
    this.render();
    this.emit();
    if (id === this.selectedId) this.emitSelected();
  },

  remove(id) {
    this.features = this.features.filter((f) => f.id !== id);
    if (this.selectedId === id) this.selectedId = null;
    this.render();
    this.emit();
    this.emitSelected();
  },

  add(feature) {
    const full = { ...feature, id: this.newId() };
    this.features.push(full);
    this.selectedId = full.id;
    this.tool = 'select';
    this.draft = null;
    this.render();
    this.emit();
    this.emitSelected();
    window.parent.postMessage({ type: 'aether-scene-tool', tool: 'select' }, window.location.origin);
  },

  // ручки выбранной фигуры: вершины линии и многоугольника, центр и радиус круга, точка текста
  drawHandles() {
    this.handles.forEach((h) => h.remove());
    this.handles = [];
    const feature = this.features.find((f) => f.id === this.selectedId);
    if (!feature || feature.type === 'marker' || feature.type === 'region') return;

    const make = (lngLat, onMove, extra = '') => {
      const el = document.createElement('div');
      el.className = `edit-handle ${extra}`;
      const handle = new maplibregl.Marker({ element: el, draggable: true }).setLngLat(lngLat).addTo(map);
      handle.on('drag', () => { const p = handle.getLngLat(); onMove([p.lng, p.lat], false); });
      handle.on('dragend', () => { const p = handle.getLngLat(); onMove([p.lng, p.lat], true); });
      this.handles.push(handle);
    };

    if (feature.type === 'text') {
      make(feature.coords, (point, done) => done && this.patch(feature.id, { coords: point }));
    } else if (feature.type === 'circle') {
      make(feature.coords, (point, done) => done && this.patch(feature.id, { coords: point }));
      const edge = destination(feature.coords, 90, feature.radius_km);
      make(edge, (point, done) => done && this.patch(feature.id, { radius_km: Math.max(1, Math.round(distanceKm(feature.coords, point))) }), 'edit-handle--radius');
    } else {
      feature.coords.forEach((coord, index) => {
        make(coord, (point, done) => {
          if (!done) return;
          const coords = feature.coords.map((c, i) => (i === index ? point : c));
          this.patch(feature.id, { coords });
        });
      });
    }
  },

  // черновик рисуемой фигуры
  drawDraft() {
    if (!map.getSource('scene-draft')) {
      map.addSource('scene-draft', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'scene-draft-fill', type: 'fill', source: 'scene-draft', filter: ['==', ['geometry-type'], 'Polygon'],
        paint: { 'fill-color': '#ffcf4d', 'fill-opacity': 0.2 } });
      map.addLayer({ id: 'scene-draft-line', type: 'line', source: 'scene-draft',
        paint: { 'line-color': '#ffcf4d', 'line-width': 2, 'line-dasharray': [2, 2] } });
      map.addLayer({ id: 'scene-draft-point', type: 'circle', source: 'scene-draft', filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-radius': 4, 'circle-color': '#ffcf4d' } });
    }
    const out = [];
    const d = this.draft;
    if (d) {
      const pts = d.cursor ? [...d.coords, d.cursor] : [...d.coords];
      if (d.type === 'circle' && d.coords.length) {
        const radius = d.cursor ? distanceKm(d.coords[0], d.cursor) : 1;
        out.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [circlePolygon(d.coords[0][0], d.coords[0][1], Math.max(radius, 0.1))] } });
      } else if (d.type === 'polygon' && pts.length >= 3) {
        out.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...pts, pts[0]]] } });
      } else if (pts.length >= 2) {
        out.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: pts } });
      }
      d.coords.forEach((c) => out.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: c } }));
    }
    map.getSource('scene-draft').setData({ type: 'FeatureCollection', features: out });
  },

  finishDraft() {
    const d = this.draft;
    if (!d) return;
    const need = d.type === 'polygon' ? 3 : 2;
    if (d.coords.length >= need) {
      this.add({ type: d.type, coords: d.coords, color: 'red', ...(d.type === 'arrow' ? { width: 3 } : {}) });
    } else {
      this.draft = null;
      this.drawDraft();
    }
  },

  click(e) {
    const point = [e.lngLat.lng, e.lngLat.lat];

    if (this.tool === 'marker') return this.add({ type: 'marker', coords: point, label: 'Метка', color: 'red' });
    if (this.tool === 'text') return this.add({ type: 'text', coords: point, text: 'Текст', color: 'grey', size: 14 });

    if (this.tool === 'region') {
      const hit = map.queryRenderedFeatures(e.point, { layers: ['adm1-fill'] })[0];
      const code = hit && provinceCodes[hit.properties.adm1_code];
      if (code && !this.features.some((f) => f.type === 'region' && f.token === code)) {
        this.add({ type: 'region', token: code, color: 'red' });
      }
      return;
    }

    if (this.tool === 'circle') {
      if (!this.draft) { this.draft = { type: 'circle', coords: [point] }; return; }
      const radius = Math.max(1, Math.round(distanceKm(this.draft.coords[0], point)));
      return this.add({ type: 'circle', coords: this.draft.coords[0], radius_km: radius, color: 'green' });
    }

    if (['line', 'arrow', 'polygon'].includes(this.tool)) {
      if (!this.draft) this.draft = { type: this.tool, coords: [] };
      this.draft.coords.push(point);
      this.drawDraft();
      return;
    }

    // выбор: фигура под курсором или пусто
    const layers = ['scene-fill', 'scene-outline', 'scene-lines', 'scene-lines-dashed', 'scene-arrows', 'scene-text', 'regions-fill']
      .filter((id) => map.getLayer(id));
    const hit = map.queryRenderedFeatures(e.point, { layers })[0];
    if (hit && hit.properties.fid) return this.select(hit.properties.fid);
    if (hit && hit.layer.id === 'regions-fill') {
      const code = provinceCodes[hit.properties.adm1_code];
      const region = this.features.find((f) => f.type === 'region' && this.codesFor(f.token).includes(hit.properties.adm1_code));
      if (region || code) return this.select(region ? region.id : null);
    }
    this.select(null);
  },
};

// Расстояние по сфере и точка на заданном расстоянии и направлении (градусы по часовой от севера)
function distanceKm(a, b) {
  const rad = (v) => (v * Math.PI) / 180;
  const dLat = rad(b[1] - a[1]);
  const dLon = rad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

function destination(from, bearingDeg, km) {
  const rad = (v) => (v * Math.PI) / 180;
  const d = km / 6371;
  const phi = rad(from[1]);
  const lam = rad(from[0]);
  const brg = rad(bearingDeg);
  const p2 = Math.asin(Math.sin(phi) * Math.cos(d) + Math.cos(phi) * Math.sin(d) * Math.cos(brg));
  const l2 = lam + Math.atan2(Math.sin(brg) * Math.sin(d) * Math.cos(phi), Math.cos(d) - Math.sin(phi) * Math.sin(p2));
  return [(((l2 * 180) / Math.PI + 540) % 360) - 180, (p2 * 180) / Math.PI];
}

if (SCENE_EDIT) {
  map.on('click', (e) => { if (layersReady) editor.click(e); });
  map.on('dblclick', (e) => {
    if (editor.draft && editor.draft.type !== 'circle') { e.preventDefault(); editor.finishDraft(); }
  });
  map.on('mousemove', (e) => {
    if (!editor.draft) return;
    editor.draft.cursor = [e.lngLat.lng, e.lngLat.lat];
    editor.drawDraft();
  });
  map.getCanvas().addEventListener('keydown', () => {});
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') editor.finishDraft();
    if (e.key === 'Escape') { editor.draft = null; editor.drawDraft(); }
    if ((e.key === 'Delete' || e.key === 'Backspace') && editor.selectedId) editor.remove(editor.selectedId);
  });

  const reportCamera = () => {
    const c = map.getCenter();
    const b = map.getBounds();
    window.parent.postMessage({
      type: 'aether-scene-view', lat: c.lat, lon: c.lng, zoom: map.getZoom(),
      bounds: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
    }, window.location.origin);
  };
  map.on('moveend', reportCamera);

  window.addEventListener('message', (e) => {
    if (e.origin !== window.location.origin || e.source !== window.parent) return;
    const d = e.data || {};
    if (d.type === 'aether-scene-load') {
      editor.load(d.features);
    } else if (d.type === 'aether-scene-tool') {
      editor.tool = d.tool || 'select';
      editor.draft = null;
      editor.drawDraft();
      map.getCanvas().style.cursor = editor.tool === 'select' ? '' : 'crosshair';
      map.doubleClickZoom[['line', 'arrow', 'polygon'].includes(editor.tool) ? 'disable' : 'enable']();
    } else if (d.type === 'aether-scene-select') {
      editor.select(d.id || null);
    } else if (d.type === 'aether-scene-update') {
      editor.patch(d.id, d.patch || {});
    } else if (d.type === 'aether-scene-delete') {
      editor.remove(d.id);
    } else if (d.type === 'aether-scene-camera') {
      reportCamera();
    }
  });

  // после загрузки слоёв и цветов провинций перерисовываем (выделения регионов нужны коды провинций)
  map.once('idle', () => editor.render());
}
