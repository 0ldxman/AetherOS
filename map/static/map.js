const DEFAULT_COLORS = {
  land: '#2b2f36',
  water: '#0f1b2d',
  forest: '#1f3a2e',
  road: '#5b6573',
  roadCasing: '#15181d',
  building: '#3d444f',
  grid: '#8fb4d9',
};

// Тема встроенной карты (?theme=maps|scan|term, её выбирает виджет ::map по стилю документа). Три разных вида:
//   maps  светлая карта в духе онлайн-карт для doc и светлого web: булавки, круглые значки, белые карточки
//   scan  бумажная карта с пометками от руки (ручка, маркер, записки) для scan
//   term  тёмная графическая карта для rec и инфобокса, она же основная карта приложения: линии, прицелы, свечение
// Метки, выноски, выделения и фигуры у виджета и у сохранённой карты общие, тема одна на весь документ.
const THEME_PARAM = new URLSearchParams(window.location.search).get('theme');
const THEME = THEME_PARAM === 'print' ? 'maps' : THEME_PARAM;   // print: прежнее имя темы maps
const accentToken = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#3fd0ff';

const THEMES = {
  maps: {
    colors: {
      land: '#f1efe9', water: '#a9d3f5', forest: '#cfe8c9', road: '#ffffff',
      roadCasing: '#d7d3c8', building: '#e5e1d8', grid: '#9aa0a6',
    },
    boundary: '#8a8f98',
    provinceOpacity: 0.22,
    keepCountryColors: true,
    labelText: '#3c4043',
    labelHalo: '#ffffff',
    region: '#1a73e8',
    dim: '#ffffff',
  },
  scan: {
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

const THEME_STYLE = THEMES[THEME] || null;

// Цвета выделения и меток из разметки виджета (red, blue...). Те же имена и значения у легенды
// в wiki/static/wiki/blocks.css (--mc-*): при правке менять оба места, тест следит за совпадением.
const MARK_COLORS = {
  maps: {
    red: '#d93025', blue: '#1a73e8', green: '#188038', orange: '#e8710a',
    purple: '#8e24aa', yellow: '#f9ab00', teal: '#129eaf', grey: '#5f6368',
  },
  scan: {
    red: '#b00d1c', blue: '#12307a', green: '#14612a', orange: '#b85200',
    purple: '#5a1f8a', yellow: '#b88a00', teal: '#0e6b6b', grey: '#2f2c28',
  },
  term: {
    red: '#ff5a5f', blue: '#5aa9ff', green: '#3fe0a0', orange: '#ffa13d',
    purple: '#b58cff', yellow: '#ffd84d', teal: '#3fd0ff', grey: '#9aa5a5',
  },
};
const markPalette = MARK_COLORS[THEME_STYLE ? THEME : 'term'];
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
const PEN_SCENE = EMBED && THEME === 'scan';
// Сохранённая карта в самом приложении: /apps/map/?scene=слаг (камера, дата и пометки берутся из сцены)
const SCENE_SLUG = !EMBED ? SEARCH.get('scene') : null;
const SCENE_VIEW = !!SCENE_SLUG;
let sceneDate = '';
const START_HASH = window.location.hash;   // вид из адреса до того, как карта сама запишет свой
// формы значков меток (map/icons.py): имя -> {d, closed, solid}
const MARKER_ICONS = (() => {
  try { return JSON.parse(document.getElementById('marker-icons').textContent); } catch (error) { return {}; }
})();
const MARKERS = EMBED
  ? SEARCH.getAll('m').map((raw) => {
      const [lat, lon, color, icon, link, ...label] = raw.split(',');
      return { lat: Number(lat), lon: Number(lon), color, icon, url: link ? decodeURIComponent(link.replace(/\+/g, ' ')) : '', label: label.join(',') };
    }).filter((m) => Number.isFinite(m.lat) && Number.isFinite(m.lon))
  : [];
// Выноски из строк ::map (?c=<json>): текст, место, смещение плашки в пикселях
const CALLOUTS = EMBED
  ? SEARCH.getAll('c').map((raw) => { try { return JSON.parse(raw); } catch (error) { return null; } })
      .filter((c) => c && Number.isFinite(c.lat) && Number.isFinite(c.lon) && c.text)
      .map((c) => ({ coords: [c.lon, c.lat], text: c.text, color: c.color, offset: c.offset, url: c.url }))
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
let provinceLinks = {}; // adm1_code -> ссылка по клику (wiki_url)

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
  preserveDrawingBuffer: SCENE_EDIT,   // нужен, чтобы редактор мог снять миниатюру с холста
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
  return new URLSearchParams(window.location.search).get('date') || sceneDate || null;
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
      provinceLinks = {};
      for (const [sourceCode, item] of Object.entries(data)) {
        colors[sourceCode] = item.color;
        provinceCodes[sourceCode] = item.code;
        if (item.url) provinceLinks[sourceCode] = item.url;
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

  // Клик по провинции в основной карте открывает её ссылку (страница провинции или страны, поле wiki_url)
  if (!EMBED && !EDIT_MODE && !PICK_MODE) {
    map.on('click', 'adm1-fill', (e) => {
      const url = provinceLinks[e.features[0].properties.adm1_code];
      if (url) openProvinceLink(url);
    });
    map.on('mousemove', 'adm1-fill', (e) => {
      map.getCanvas().style.cursor = provinceLinks[e.features[0].properties.adm1_code] ? 'pointer' : '';
    });
    map.on('mouseleave', 'adm1-fill', () => { map.getCanvas().style.cursor = ''; });
  }

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
if (EMBED || SCENE_VIEW) {
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
  // выделение провинций: у каждой темы свой вид (maps: заливка и ровный контур, term: тонкий контур со свечением,
  // scan: штриховка цветным карандашом и контур ручкой в два прохода)
  map.addLayer({
    id: 'regions-fill',
    type: 'fill',
    source: 'adm1',
    'source-layer': 'aether_provinces',
    filter: nothing,
    paint: { 'fill-color': '#ffcf4d', 'fill-opacity': THEME === 'maps' ? 0.22 : THEME === 'term' ? 0.16 : THEME === 'scan' ? 1 : 0.4 },
  });
  if (THEME === 'term' || !THEME_STYLE) {
    map.addLayer({
      id: 'regions-glow',
      type: 'line',
      source: 'adm1',
      'source-layer': 'aether_provinces',
      filter: nothing,
      paint: { 'line-color': '#ffcf4d', 'line-width': 7, 'line-blur': 5, 'line-opacity': 0.4 },
    });
  }
  map.addLayer({
    id: 'regions-line',
    type: 'line',
    source: 'adm1',
    'source-layer': 'aether_provinces',
    filter: nothing,
    layout: THEME === 'scan' ? { 'line-cap': 'round', 'line-join': 'round' } : {},
    paint: { 'line-color': '#ffcf4d', 'line-width': THEME === 'term' ? 1.4 : THEME === 'scan' ? 2.3 : 2.2, 'line-blur': THEME === 'scan' ? 0.35 : 0 },
  });
  if (THEME === 'scan') {
    // второй, более тонкий и смещённый проход ручки: контур выглядит обведённым дважды
    map.addLayer({
      id: 'regions-line2',
      type: 'line',
      source: 'adm1',
      'source-layer': 'aether_provinces',
      filter: nothing,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#ffcf4d', 'line-width': 0.9, 'line-offset': 1.6, 'line-opacity': 0.7 },
    });
  }
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
  startData();
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
  CALLOUTS.forEach((item) => addCallout(item));

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
  if (url && !EMBED) { openProvinceLink(url); return; }   // в самом приложении ссылку открываем сразу
  if (url) window.parent.postMessage({ type: 'aether-map-link', url, label: label || '' }, window.location.origin);
}

// Штриховка цветным карандашом для выделений на scan: плитка 64 px, концы штрихов совпадают на краях,
// поэтому рисунок ложится без швов, а изгиб штриха разный, чтобы не выглядело печатным узором
const hatchImages = new Set();
function hatchName(color) {
  const name = `hatch:${color}`;
  if (hatchImages.has(name) || map.hasImage(name)) return name;
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.13;
  ctx.fillRect(0, 0, size, size);
  ctx.globalAlpha = 0.62;
  ctx.strokeStyle = color;
  ctx.lineCap = 'round';
  const wobble = [1.6, -1.2, 2.1, -1.8, 1.1, -2.2, 1.7, -0.9];
  [3, 11, 19, 27, 35, 43, 51, 59].forEach((y, i) => {
    ctx.lineWidth = 1.1 + (i % 3) * 0.25;
    const w = wobble[i];
    // штрих уходит вниз-вправо и, дойдя до края плитки, продолжается с противоположной стороны
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.quadraticCurveTo((size - y) / 2 + w, (size + y) / 2 - w, size - y, size);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(size - y, 0);
    ctx.quadraticCurveTo(size - y / 2 + w, y / 2 - w, size, y);
    ctx.stroke();
  });
  map.addImage(name, ctx.getImageData(0, 0, size, size), { pixelRatio: 2 });
  hatchImages.add(name);
  return name;
}

// Выделение провинций: адрес карты плюс пометки сцены (у последней записи провинции приоритет)
function setRegions(extra) {
  if (!(EMBED || SCENE_VIEW) || !map.getLayer('regions-fill')) return;

  const base = THEME_STYLE ? THEME_STYLE.region : '#ffcf4d';
  const items = new Map();
  for (const item of [...REGION_ITEMS, ...extra]) items.set(item.code, item);

  regionLinks = new Map([...items].filter(([, item]) => item.url).map(([code, item]) => [code, item]));
  const codes = [...items.keys()];
  const inRegions = ['in', ['get', 'adm1_code'], ['literal', codes]];

  const byColor = ['match', ['get', 'adm1_code']];
  for (const [code, item] of items) byColor.push(code, markColor(item.color, base));
  byColor.push(base);

  for (const id of ['regions-fill', 'regions-line', 'regions-line2', 'regions-glow']) {
    if (map.getLayer(id)) map.setFilter(id, inRegions);
  }
  map.setFilter('regions-dim', ['!', inRegions]);
  map.setLayoutProperty('regions-dim', 'visibility', codes.length ? 'visible' : 'none');
  for (const id of ['regions-line', 'regions-line2', 'regions-glow']) {
    if (map.getLayer(id)) map.setPaintProperty(id, 'line-color', codes.length ? byColor : base);
  }
  if (THEME === 'scan') {
    const pattern = ['match', ['get', 'adm1_code']];
    for (const [code, item] of items) pattern.push(code, hatchName(markColor(item.color, base)));
    pattern.push(hatchName(base));
    map.setPaintProperty('regions-fill', 'fill-pattern', pattern);
  } else {
    map.setPaintProperty('regions-fill', 'fill-color', codes.length ? byColor : base);
  }
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
    paint: { 'fill-color': ['get', 'c'], 'fill-opacity': PEN_SCENE ? 0 : 0.25 } }, before);
  map.addLayer({ id: 'scene-outline', type: 'line', source: SCENE_SOURCE,
    filter: ['==', ['geometry-type'], 'Polygon'],
    paint: { 'line-color': ['get', 'c'], 'line-width': 2, 'line-opacity': PEN_SCENE ? 0 : 1 } }, before);
  if (THEME === 'maps') {
    // маршрут с белой окантовкой, как на онлайн-картах
    map.addLayer({ id: 'scene-lines-casing', type: 'line', source: SCENE_SOURCE,
      filter: ['==', ['geometry-type'], 'LineString'],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': ['+', ['get', 'w'], 3] } }, before);
  } else if (THEME === 'term' || !THEME_STYLE) {
    map.addLayer({ id: 'scene-lines-glow', type: 'line', source: SCENE_SOURCE,
      filter: ['==', ['geometry-type'], 'LineString'],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': ['get', 'c'], 'line-width': ['+', ['get', 'w'], 5], 'line-blur': 4, 'line-opacity': 0.35 } }, before);
  }
  map.addLayer({ id: 'scene-lines', type: 'line', source: SCENE_SOURCE,
    filter: ['all', ['==', ['geometry-type'], 'LineString'], ['!=', ['get', 'dash'], true]],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'c'], 'line-width': ['get', 'w'], 'line-opacity': PEN_SCENE ? 0 : 1 } }, before);
  map.addLayer({ id: 'scene-lines-dashed', type: 'line', source: SCENE_SOURCE,
    filter: ['all', ['==', ['geometry-type'], 'LineString'], ['==', ['get', 'dash'], true]],
    paint: { 'line-color': ['get', 'c'], 'line-width': ['get', 'w'], 'line-dasharray': [2, 1.5], 'line-opacity': PEN_SCENE ? 0 : 1 } }, before);
  map.addLayer({ id: 'scene-arrows', type: 'symbol', source: SCENE_SOURCE,
    filter: ['==', ['get', 'role'], 'head'],
    layout: { 'icon-image': 'scene-arrow', 'icon-rotate': ['get', 'bearing'], 'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true, 'icon-ignore-placement': true, 'icon-size': ['+', 0.45, ['*', ['get', 'w'], 0.06]] },
    paint: { 'icon-color': ['get', 'c'], 'icon-opacity': PEN_SCENE ? 0 : 1 } }, before);
  map.addLayer({ id: 'scene-text', type: 'symbol', source: SCENE_SOURCE,
    filter: ['==', ['get', 'role'], 'text'],
    layout: { 'text-field': ['get', 't'], 'text-font': ['Noto Sans Regular'], 'text-size': ['get', 'size'],
      'text-anchor': 'top', 'text-offset': [0, 0.4], 'text-max-width': 12, 'text-allow-overlap': true },
    paint: { 'text-color': ['get', 'c'], 'text-halo-color': halo, 'text-halo-width': 1.4,
      'text-opacity': PEN_SCENE ? 0 : 1 } });

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
  if (!(EMBED || SCENE_VIEW) || !layersReady) return;

  ensureSceneLayers();
  const shapes = [];
  const pen = [];   // для scan фигуры рисуются от руки поверх карты (SVG), а не слоями карты
  const regions = [];
  sceneMarkers.forEach((marker) => marker.remove());
  sceneMarkers = [];

  for (const item of sceneFeatures) {
    const c = sceneColor(item.color);
    const common = { c, url: item.url || '', label: item.label || '', fid: item.id || '' };
    // для scan те же фигуры дополнительно рисуются от руки; слои карты остаются невидимыми ради выбора в редакторе
    if (PEN_SCENE && ['line', 'arrow', 'polygon', 'circle', 'text'].includes(item.type)) pen.push(item);

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
    } else if (item.type === 'callout') {
      sceneMarkers.push(addCallout(item, SCENE_EDIT ? {
        selected: item.id === editor.selectedId,
        onSelect: () => editor.select(item.id),
        onMove: (point) => editor.patch(item.id, { coords: point }),
        onOffset: (offset) => editor.patch(item.id, { offset }),
      } : {}));
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
  penShapes = pen;
  drawPen();
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


// Контур значка «от руки»: точки пути смещаются плавным шумом, а замкнутый контур идёт чуть дальше
// начала и не попадает в него. seed разный у меток, pass у первого и второго прохода ручки.
function roughPath(d, seed, pass) {
  const ns = 'http://www.w3.org/2000/svg';
  const phase = seed * 1.7 + pass * 2.3;
  const amp = pass ? 0.55 : 0.4;
  return d.split(/(?=M)/).filter(Boolean).map((sub) => {
    const probe = document.createElementNS(ns, 'path');
    probe.setAttribute('d', sub);
    const length = probe.getTotalLength();
    if (!length) return '';
    const closed = /z\s*$/i.test(sub.trim());
    const span = length * (closed ? 1.06 : 1);
    const steps = Math.max(8, Math.round(span / 1));
    const points = [];
    for (let i = 0; i <= steps; i += 1) {
      const t = (i / steps) * span;
      const at = probe.getPointAtLength(t > length ? t - length : t);
      const x = at.x + amp * (Math.sin(t * 0.38 + phase) + 0.4 * Math.sin(t * 0.9 + phase * 2));
      const y = at.y + amp * (Math.cos(t * 0.34 + phase * 1.3) + 0.4 * Math.cos(t * 0.8 + phase));
      points.push(`${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`);
    }
    return points.join('');
  }).join('');
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

  const shape = item.icon && item.icon !== 'pin' ? MARKER_ICONS[item.icon] : null;

  if (shape) {
    // значок-форма: на scan обведён ручкой, на maps белый знак на круглой плашке, на term контур с засечками
    const pen = THEME === 'scan';
    tag.classList.add(pen ? 'embed-marker--pen' : 'embed-marker--icon');
    if (pen) tag.classList.add('embed-marker--pen-shape');
    if (shape.solid) tag.classList.add('is-solid');
    if (!shape.closed) tag.classList.add('is-open');
    // от руки: контур ведётся неровно, замкнутая фигура не сходится ровно, второй проход тоньше и в другом месте
    const first = pen ? roughPath(shape.d, seed, 0) : shape.d;
    const again = pen ? `<path class="again" d="${roughPath(shape.d, seed, 1)}"/>` : '';
    tag.innerHTML =
      `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${first}"/>${again}</svg>` +
      (numbered ? `<span class="${pen ? 'pen-n' : 'icon-n'}">${text}</span>` : '');
  } else if (THEME === 'scan') {
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

  // остриё булавки (maps) стоит на точке; прицел, крест от руки и круглые значки центрируются на ней
  const centered = THEME !== 'maps' || !!shape;
  const marker = new maplibregl.Marker({ element: el, anchor: centered ? 'center' : 'bottom', draggable: !!opts.onMove })
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
  undoStack: [],
  redoStack: [],
  lastPatch: null,
  hidden: new Set(),    // скрыты только в редакторе (в сцену не пишутся)
  previewKeys: null,    // null: видно всё; иначе набор ключей воображаемого игрока
  previewDate: null,    // ГГГГ-ММ-ДД: показать пометки, видимые на эту дату (null: все)

  newId() { this.nextId += 1; return `f${this.nextId}`; },

  // снимок перед изменением для отмены; подряд идущие правки одного поля склеиваются
  remember(coalesce) {
    const now = Date.now();
    if (coalesce && this.lastPatch && this.lastPatch.key === coalesce && now - this.lastPatch.time < 900) {
      this.lastPatch.time = now;
      return;
    }
    this.lastPatch = coalesce ? { key: coalesce, time: now } : null;
    this.undoStack.push(JSON.stringify(this.features));
    if (this.undoStack.length > 100) this.undoStack.shift();
    this.redoStack = [];
  },

  restore(snapshot) {
    this.features = JSON.parse(snapshot);
    if (!this.features.some((f) => f.id === this.selectedId)) this.selectedId = null;
    this.render();
    this.emit();
    this.emitSelected();
  },

  undo() {
    if (!this.undoStack.length) return;
    this.redoStack.push(JSON.stringify(this.features));
    this.lastPatch = null;
    this.restore(this.undoStack.pop());
  },

  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(JSON.stringify(this.features));
    this.lastPatch = null;
    this.restore(this.redoStack.pop());
  },

  // видна ли пометка воображаемому игроку (условие по ключам, как у спойлеров)
  shown(feature) {
    if (this.hidden.has(feature.id)) return false;
    if (this.previewDate && ((feature.from && feature.from > this.previewDate) || (feature.to && this.previewDate > feature.to))) return false;
    return this.previewKeys === null || condSatisfied(feature.key, this.previewKeys);
  },

  // пометки без служебного id уходят родителю
  emit() {
    const features = this.features.map(({ id, ...rest }) => rest);
    window.parent.postMessage({
      type: 'aether-scene-features',
      features,
      ids: this.features.map((f) => f.id),
      hidden: [...this.hidden],
      history: { undo: this.undoStack.length, redo: this.redoStack.length },
    }, window.location.origin);
  },

  emitSelected() {
    const feature = this.features.find((f) => f.id === this.selectedId) || null;
    window.parent.postMessage({ type: 'aether-scene-selected', id: this.selectedId, feature }, window.location.origin);
  },

  load(features) {
    this.features = (features || []).map((f) => ({ ...f, id: this.newId() }));
    this.selectedId = null;
    this.undoStack = [];
    this.redoStack = [];
    this.render();
    this.emit();
  },

  // выделения предпросмотра: код провинции из БД (RUS-32) или страна по префиксу (POL)
  codesFor(token) {
    const key = String(token || '').toUpperCase();
    return Object.entries(provinceCodes)
      .filter(([, code]) => String(code).toUpperCase() === key || String(code).toUpperCase().startsWith(`${key}-`))
      .map(([source]) => source);
  },

  render() {
    sceneFeatures = this.features.filter((f) => this.shown(f)).map((f) => (f.type === 'region'
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
    this.remember(`${id}:${Object.keys(change).sort().join(',')}`);
    Object.assign(feature, change);
    for (const key of Object.keys(change)) if (change[key] === '' || change[key] === null) delete feature[key];
    this.render();
    this.emit();
    if (id === this.selectedId) this.emitSelected();
  },

  remove(id) {
    this.remember();
    this.features = this.features.filter((f) => f.id !== id);
    if (this.selectedId === id) this.selectedId = null;
    this.render();
    this.emit();
    this.emitSelected();
  },

  add(feature) {
    const full = { ...feature, id: this.newId() };
    this.remember();
    this.features.push(full);
    this.selectedId = full.id;
    this.tool = 'select';
    this.draft = null;
    this.render();
    this.emit();
    this.emitSelected();
    window.parent.postMessage({ type: 'aether-scene-tool', tool: 'select' }, window.location.origin);
  },

  // копия пометки со сдвигом на 24 px вправо и вниз (выделение региона не копируется)
  duplicate(id) {
    const feature = this.features.find((f) => f.id === id);
    if (!feature || feature.type === 'region') return;
    const shift = (c) => { const p = map.project(c); const q = map.unproject([p.x + 24, p.y + 24]); return [q.lng, q.lat]; };
    const copy = JSON.parse(JSON.stringify(feature));
    copy.coords = Array.isArray(copy.coords[0]) ? copy.coords.map(shift) : shift(copy.coords);
    delete copy.id;
    this.add(copy);
  },

  // порядок в списке (и слоёв): dir -1 выше, +1 ниже
  reorder(id, dir) {
    const i = this.features.findIndex((f) => f.id === id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= this.features.length) return;
    this.remember();
    [this.features[i], this.features[j]] = [this.features[j], this.features[i]];
    this.render();
    this.emit();
  },

  setHidden(id, hidden) {
    if (hidden) this.hidden.add(id); else this.hidden.delete(id);
    if (hidden && this.selectedId === id) this.selectedId = null;
    this.render();
    this.emit();
    this.emitSelected();
  },

  setPreview(keys) {
    this.previewKeys = keys === null ? null : new Set(keys);
    if (this.selectedId && !this.shown(this.features.find((f) => f.id === this.selectedId) || {})) this.selectedId = null;
    this.render();
    this.emitSelected();
  },

  // ручки выбранной фигуры: вершины линии и многоугольника, центр и радиус круга, точка текста
  drawHandles() {
    this.handles.forEach((h) => h.remove());
    this.handles = [];
    const feature = this.features.find((f) => f.id === this.selectedId);
    if (!feature || ['marker', 'region', 'callout'].includes(feature.type) || feature.smooth) return;

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
      const need = feature.type === 'polygon' ? 3 : 2;
      feature.coords.forEach((coord, index) => {
        make(coord, (point, done) => {
          if (!done) return;
          const coords = feature.coords.map((c, i) => (i === index ? point : c));
          this.patch(feature.id, { coords });
        });
        // двойной клик по вершине убирает её (пока остаётся достаточно точек)
        const el = this.handles[this.handles.length - 1].getElement();
        el.title = 'Двойной клик: убрать вершину';
        el.addEventListener('dblclick', (event) => {
          event.stopPropagation();
          if (feature.coords.length > need) this.patch(feature.id, { coords: feature.coords.filter((_, i) => i !== index) });
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

  // двойной клик по выбранной линии или многоугольнику вставляет вершину в ближайший отрезок
  addVertex(e) {
    const feature = this.features.find((f) => f.id === this.selectedId);
    if (this.tool !== 'select' || !feature || !['line', 'arrow', 'polygon'].includes(feature.type)) return;
    const pts = feature.coords.map((c) => map.project(c));
    const at = e.point;
    const closed = feature.type === 'polygon';
    let best = { index: -1, dist: 14 };
    for (let i = 0; i < pts.length - (closed ? 0 : 1); i += 1) {
      const a = pts[i];
      const b = pts[(i + 1) % pts.length];
      const t = Math.max(0, Math.min(1, ((at.x - a.x) * (b.x - a.x) + (at.y - a.y) * (b.y - a.y)) / (((b.x - a.x) ** 2 + (b.y - a.y) ** 2) || 1)));
      const dist = Math.hypot(at.x - (a.x + t * (b.x - a.x)), at.y - (a.y + t * (b.y - a.y)));
      if (dist < best.dist) best = { index: i, dist };
    }
    if (best.index < 0) return;
    e.preventDefault();
    const coords = [...feature.coords];
    coords.splice(best.index + 1, 0, [e.lngLat.lng, e.lngLat.lat]);
    this.patch(feature.id, { coords });
  },

  click(e) {
    const point = [e.lngLat.lng, e.lngLat.lat];

    if (this.tool === 'marker') return this.add({ type: 'marker', coords: point, label: 'Метка', color: 'red' });
    if (this.tool === 'text') return this.add({ type: 'text', coords: point, text: 'Текст', color: 'grey', size: 14 });
    if (this.tool === 'callout') return this.add({ type: 'callout', coords: point, text: 'Выноска', offset: [70, -50], color: 'grey' });
    if (this.tool === 'freehand') return;   // рисуется протяжкой, клик ничего не делает

    if (this.tool === 'region') {
      const hit = map.queryRenderedFeatures(e.point, { layers: ['adm1-fill'] })[0];
      const code = hit && provinceCodes[hit.properties.adm1_code];
      if (!code) return;
      // Shift+клик выделяет страну целиком (по префиксу кода), повторный клик по выделенному снимает выделение
      const token = e.originalEvent.shiftKey ? String(code).split('-')[0] : code;
      const existing = this.features.find((f) => f.type === 'region' && f.token === token);
      if (existing) this.remove(existing.id);
      else this.add({ type: 'region', token, color: 'red' });
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
    if (editor.draft && editor.draft.type !== 'circle') { e.preventDefault(); editor.finishDraft(); return; }
    editor.addVertex(e);
  });
  map.on('mousemove', (e) => {
    if (!editor.draft) return;
    if (editor.draft.type === 'freehand') {
      // протяжка: новая точка, когда курсор ушёл от последней хотя бы на 3 пикселя
      const last = map.project(editor.draft.coords[editor.draft.coords.length - 1]);
      if (Math.hypot(e.point.x - last.x, e.point.y - last.y) >= 3) {
        editor.draft.coords.push([e.lngLat.lng, e.lngLat.lat]);
        editor.drawDraft();
      }
      return;
    }
    editor.draft.cursor = [e.lngLat.lng, e.lngLat.lat];
    editor.drawDraft();
  });
  map.on('mousedown', (e) => {
    if (editor.tool !== 'freehand') return;
    e.preventDefault();
    editor.draft = { type: 'freehand', coords: [[e.lngLat.lng, e.lngLat.lat]] };
  });
  map.on('mouseup', () => {
    if (!editor.draft || editor.draft.type !== 'freehand') return;
    const coords = simplifyPath(editor.draft.coords);
    editor.draft = null;
    editor.drawDraft();
    if (coords.length >= 2) editor.add({ type: 'line', smooth: true, coords, color: 'red', width: 3 });
  });
  map.getCanvas().addEventListener('keydown', () => {});
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') editor.finishDraft();
    if (e.key === 'Escape') { editor.draft = null; editor.drawDraft(); }
    if ((e.key === 'Delete' || e.key === 'Backspace') && editor.selectedId) editor.remove(editor.selectedId);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); if (e.shiftKey) editor.redo(); else editor.undo(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); editor.redo(); }
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
      map.dragPan[editor.tool === 'freehand' ? 'disable' : 'enable']();
      map.doubleClickZoom[['line', 'arrow', 'polygon'].includes(editor.tool) ? 'disable' : 'enable']();
    } else if (d.type === 'aether-scene-select') {
      editor.select(d.id || null);
    } else if (d.type === 'aether-scene-update') {
      editor.patch(d.id, d.patch || {});
    } else if (d.type === 'aether-scene-delete') {
      editor.remove(d.id);
    } else if (d.type === 'aether-scene-camera') {
      reportCamera();
    } else if (d.type === 'aether-scene-capture') {
      captureThumbnail();
    } else if (d.type === 'aether-scene-undo') {
      editor.undo();
    } else if (d.type === 'aether-scene-redo') {
      editor.redo();
    } else if (d.type === 'aether-scene-duplicate') {
      editor.duplicate(d.id);
    } else if (d.type === 'aether-scene-move') {
      editor.reorder(d.id, d.dir);
    } else if (d.type === 'aether-scene-hide') {
      editor.setHidden(d.id, !!d.hidden);
    } else if (d.type === 'aether-scene-add-region') {
      // выбор из поиска: добавить выделение и подлететь к нему
      if (d.token && !editor.features.some((f) => f.type === 'region' && f.token === d.token)) {
        editor.add({ type: 'region', token: d.token, color: 'red' });
      }
      if (Array.isArray(d.bounds) && d.bounds.length === 4) {
        map.fitBounds([[d.bounds[0], d.bounds[1]], [d.bounds[2], d.bounds[3]]], { padding: 40, maxZoom: 7, duration: 600 });
      }
    } else if (d.type === 'aether-scene-preview-date') {
      editor.previewDate = d.date || null;
      editor.render();
    } else if (d.type === 'aether-scene-preview') {
      editor.setPreview(Array.isArray(d.keys) ? d.keys : null);
    }
  });

  // после загрузки слоёв и цветов провинций перерисовываем (выделения регионов нужны коды провинций)
  map.once('idle', () => editor.render());
}


// Ссылка провинции: путь сайта открывается окном рабочего стола, внешний адрес в новой вкладке
function openProvinceLink(url) {
  if (url.startsWith('/')) {
    let desktop = null;
    try {
      desktop = window.parent !== window && window.parent.desktopAPI;
    } catch (error) {
      desktop = null;
    }
    if (desktop && typeof desktop.openApp === 'function') {
      desktop.openApp(`map-link-${url}`, decodeURIComponent(url.split('/').filter(Boolean).pop() || 'link'), url);
    } else {
      window.location.href = url;
    }
  } else {
    window.open(url, '_blank', 'noopener');
  }
}


// ---------------------------------------------------------------------------
// scan: фигуры сохранённой карты рисуются «ручкой». SVG поверх карты, точки берутся
// из проекции карты, линии слегка гуляют, поверх шероховатость (фильтр pen-rough).
// ---------------------------------------------------------------------------
let penShapes = [];
let penSvg = null;

// детерминированный «случайный» разброс по номеру, чтобы рисунок не дрожал между кадрами
const penRand = (n) => { const x = Math.sin(n * 12.9898) * 43758.5453; return x - Math.floor(x); };

function penPath(points, closed, seed) {
  if (points.length < 2) return '';
  let d = `M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  const last = closed ? points.length : points.length - 1;
  for (let i = 1; i <= last; i += 1) {
    const a = points[i - 1];
    const b = points[i % points.length];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const off = (penRand(seed + i) - 0.5) * Math.min(len * 0.07, 3.4);
    const mx = (a.x + b.x) / 2 - (dy / len) * off;
    const my = (a.y + b.y) / 2 + (dx / len) * off;
    d += ` Q${mx.toFixed(1)} ${my.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
  }
  return d;
}

function penHead(from, to) {
  const ang = Math.atan2(to.y - from.y, to.x - from.x);
  const len = 15;
  const wing = (delta) => ({ x: to.x - len * Math.cos(ang + delta), y: to.y - len * Math.sin(ang + delta) });
  const a = wing(0.45);
  const b = wing(-0.45);
  return `M${a.x.toFixed(1)} ${a.y.toFixed(1)} L${to.x.toFixed(1)} ${to.y.toFixed(1)} L${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
}

function drawPen() {
  if (!PEN_SCENE) return;
  if (!penSvg) {
    penSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    penSvg.setAttribute('class', 'pen-scene');
    map.getCanvasContainer().appendChild(penSvg);
    map.on('render', drawPen);
  }

  const ns = 'http://www.w3.org/2000/svg';
  const project = (c) => map.project(c);
  const parts = ['<defs>'];
  const colors = [...new Set(penShapes.map((f) => sceneColor(f.color)))];
  colors.forEach((c, i) => {
    parts.push(`<pattern id="hatch-${i}" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(40)">` +
      `<line x1="0" y1="0" x2="0" y2="7" stroke="${c}" stroke-width="1" opacity="0.7"/></pattern>`);
  });
  const texts = [];   // надписи вне фильтра шероховатости: иначе буквы расплываются
  parts.push('</defs><g filter="url(#pen-rough)" fill="none" stroke-linecap="round" stroke-linejoin="round">');

  penShapes.forEach((item, n) => {
    const color = sceneColor(item.color);
    const hatch = `url(#hatch-${colors.indexOf(color)})`;
    const width = ((item.width || 3) * 0.62).toFixed(2);
    const seed = n * 17 + 3;
    const dash = item.dash ? ' stroke-dasharray="7 5"' : '';
    let first = null;

    if (item.type === 'line' || item.type === 'arrow') {
      const pts = item.coords.map(project);
      first = pts[0];
      // линия от руки (smooth) уже неровная сама: без искусственных изгибов и второго прохода
      const d = item.smooth ? penSmooth(pts) : penPath(pts, false, seed);
      parts.push(`<path d="${d}" stroke="${color}" stroke-width="${width}"${dash}/>`);
      if (!item.smooth) parts.push(`<path d="${penPath(pts, false, seed + 50)}" stroke="${color}" stroke-width="${(width * 0.5).toFixed(2)}" opacity="0.55"${dash}/>`);
      if (item.type === 'arrow') {
        const head = penHead(pts[pts.length - 2], pts[pts.length - 1]);
        parts.push(`<path d="${head}" stroke="${color}" stroke-width="${width}"/>`);
      }
    } else if (item.type === 'polygon') {
      const pts = item.coords.map(project);
      first = pts[0];
      if (item.fill !== false) parts.push(`<path d="${penPath(pts, true, seed)}" fill="${hatch}" stroke="none"/>`);
      parts.push(`<path d="${penPath(pts, true, seed)}" stroke="${color}" stroke-width="${width}"/>`);
      parts.push(`<path d="${penPath(pts, true, seed + 50)}" stroke="${color}" stroke-width="${(width * 0.5).toFixed(2)}" opacity="0.55"/>`);
    } else if (item.type === 'circle') {
      const ring = circlePolygon(item.coords[0], item.coords[1], item.radius_km).map(project);
      first = project(item.coords);
      const cx = first.x;
      const cy = first.y;
      // заход конца за начало: пара точек чуть дальше от центра
      const over = ring.slice(0, 7).map((p) => ({ x: cx + (p.x - cx) * 1.06, y: cy + (p.y - cy) * 1.06 }));
      const loop = [...ring.slice(0, -1), ...over];
      if (item.fill !== false) parts.push(`<path d="${penPath(ring, true, seed)}" fill="${hatch}" stroke="none"/>`);
      parts.push(`<path d="${penPath(loop, false, seed)}" stroke="${color}" stroke-width="${width}"/>`);
    } else if (item.type === 'text') {
      const p = project(item.coords);
      texts.push(`<text x="${p.x.toFixed(1)}" y="${p.y.toFixed(1)}" fill="${color}" stroke="none" ` +
        `font-family="var(--font-hand, cursive)" font-size="${(item.size || 14) * 1.5}" text-anchor="middle" ` +
        `transform="rotate(-3 ${p.x.toFixed(1)} ${p.y.toFixed(1)})">${escapeXml(item.text)}</text>`);
    }

    if (item.label && first && item.type !== 'text') {
      texts.push(`<text x="${(first.x + 8).toFixed(1)}" y="${(first.y - 8).toFixed(1)}" fill="${color}" stroke="none" ` +
        `font-family="var(--font-hand, cursive)" font-size="21" transform="rotate(-4 ${first.x.toFixed(1)} ${first.y.toFixed(1)})">${escapeXml(item.label)}</text>`);
    }
  });

  parts.push('</g>', ...texts);
  penSvg.innerHTML = parts.join('');
  void ns;
}

function escapeXml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[c]);
}


// Условие по ключам для предпросмотра «как игрок»: те же правила, что secure/access.py и спойлеры вики.
// Условие приходит словарём ({"all": [...]}) или строкой (secret and not other).
function parseCondition(src) {
  const tokens = String(src).replace(/\(/g, ' ( ').replace(/\)/g, ' ) ').split(/\s+/).filter(Boolean);
  let pos = 0;
  const atom = () => {
    const word = tokens[pos]; pos += 1;
    if (word === '(') { const inner = orExpr(); pos += 1; return inner; }
    if (word === 'not') return { not: atom() };
    return word;
  };
  const andExpr = () => {
    const parts = [atom()];
    while (tokens[pos] === 'and') { pos += 1; parts.push(atom()); }
    return parts.length > 1 ? { all: parts } : parts[0];
  };
  const orExpr = () => {
    const parts = [andExpr()];
    while (tokens[pos] === 'or') { pos += 1; parts.push(andExpr()); }
    return parts.length > 1 ? { any: parts } : parts[0];
  };
  return tokens.length ? orExpr() : null;
}

function condSatisfied(req, keys) {
  if (!req) return true;
  if (typeof req === 'string') {
    const parsed = parseCondition(req);
    return typeof parsed === 'string' ? keys.has(parsed) : condSatisfied(parsed, keys);
  }
  if (req.all) return req.all.every((r) => condSatisfied(r, keys));
  if (req.any) return req.any.some((r) => condSatisfied(r, keys));
  if (req.not !== undefined) return !condSatisfied(req.not, keys);
  return false;
}


// Данные карты: у сохранённой карты сначала берём её дату и камеру, потому что от даты зависят цвета и подписи
async function startData() {
  if (SCENE_VIEW) await loadSceneView();
  loadProvinceColors();
  loadCountryLabels();
}

async function loadSceneView() {
  try {
    const response = await fetch(`${SCENES_URL}${encodeURIComponent(SCENE_SLUG)}/${window.location.search.includes('date=') ? `?date=${encodeURIComponent(SEARCH.get('date'))}` : ''}`,
      { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    // дата сцены попадает в адрес, чтобы таймлайн и остальное приложение показывали её же
    if (!SEARCH.get('date') && data.date) {
      const params = new URLSearchParams(window.location.search);
      params.set('date', data.date);
      window.location.replace(`${window.location.pathname}?${params}${START_HASH}`);
      return;
    }
    if (!SEARCH.get('mode') && Object.hasOwn(MODE_LAYERS, data.mode)) { currentMode = data.mode; applyMode(); }
    map.setProjection({ type: data.flat ? 'mercator' : 'globe' });
    if (Array.isArray(data.bounds) && data.bounds.length === 4) map.setMaxBounds([[data.bounds[0], data.bounds[1]], [data.bounds[2], data.bounds[3]]]);
    if (data.min_zoom !== null && data.min_zoom !== undefined) map.setMinZoom(data.min_zoom);
    if (data.max_zoom !== null && data.max_zoom !== undefined) map.setMaxZoom(data.max_zoom);
    if (!START_HASH) map.jumpTo({ center: [data.lon, data.lat], zoom: data.zoom });

    sceneFeatures = data.features;
    applyScene();
    document.title = `${data.title} · ${document.title}`;
  } catch (error) {
    console.error('Не удалось загрузить сохранённую карту', error);
  }
}

// Выбор сохранённой карты: список в углу, выбор перезагружает карту со ?scene=слаг
if (!EMBED && !EDIT_MODE && !PICK_MODE && typeof SCENES_URL !== 'undefined') {
  fetch(SCENES_URL, { credentials: 'same-origin' })
    .then((r) => (r.ok ? r.json() : []))
    .then((scenes) => {
      if (!scenes.length) return;
      const panel = document.createElement('div');
      panel.id = 'scene-panel';
      const select = document.createElement('select');
      const none = document.createElement('option');
      none.value = '';
      none.textContent = 'обычная карта';
      select.appendChild(none);
      scenes.forEach((scene) => {
        const option = document.createElement('option');
        option.value = scene.slug;
        option.textContent = scene.title;
        select.appendChild(option);
      });
      select.value = SCENE_SLUG || '';
      select.addEventListener('change', () => {
        const params = new URLSearchParams(window.location.search);
        if (select.value) params.set('scene', select.value); else params.delete('scene');
        params.delete('date');
        window.location.search = params.toString();
      });
      const title = document.createElement('div');
      title.className = 'title';
      title.textContent = 'map.scene';
      panel.append(title, select);
      document.body.appendChild(panel);
    })
    .catch(() => {});
}


// Свободная линия: точки протяжки упрощаются (Дуглас-Пекер в пикселях), чтобы их осталось не больше 200
function simplifyPath(coords) {
  const pts = coords.map((c) => { const p = map.project(c); return { x: p.x, y: p.y, c }; });
  const dist = (p, a, b) => {
    const dx = b.x - a.x; const dy = b.y - a.y;
    const len = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len));
    return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
  };
  const run = (tol) => {
    const keep = new Array(pts.length).fill(false);
    keep[0] = keep[pts.length - 1] = true;
    const stack = [[0, pts.length - 1]];
    while (stack.length) {
      const [lo, hi] = stack.pop();
      let far = -1; let farDist = tol;
      for (let i = lo + 1; i < hi; i += 1) {
        const d = dist(pts[i], pts[lo], pts[hi]);
        if (d > farDist) { far = i; farDist = d; }
      }
      if (far >= 0) { keep[far] = true; stack.push([lo, far], [far, hi]); }
    }
    return pts.filter((_, i) => keep[i]).map((p) => [Number(p.c[0].toFixed(5)), Number(p.c[1].toFixed(5))]);
  };
  let tol = 1.5;
  let out = run(tol);
  while (out.length > 200 && tol < 40) { tol *= 1.5; out = run(tol); }
  return out;
}

// Миниатюра сцены для списка в админке: холст карты уменьшается до 360 px, метки и выноски дорисовываются точками
function captureThumbnail() {
  map.triggerRepaint();
  map.once('render', () => {
    const src = map.getCanvas();
    const box = map.getContainer();
    const width = 360;
    const height = Math.max(60, Math.round((width * box.clientHeight) / box.clientWidth));
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(src, 0, 0, width, height);
    const k = width / box.clientWidth;
    for (const item of sceneFeatures) {
      if (!['marker', 'callout', 'text'].includes(item.type)) continue;
      const p = map.project(item.coords);
      ctx.fillStyle = markColor(item.color, '#ff5a5f');
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(p.x * k, p.y * k, item.type === 'marker' ? 5 : 3, 0, Math.PI * 2);
      ctx.fill();
      if (item.type === 'marker') ctx.stroke();
    }
    let data = '';
    try { data = canvas.toDataURL('image/jpeg', 0.72); } catch (error) { data = ''; }   // холст мог «испачкаться» чужими тайлами
    window.parent.postMessage({ type: 'aether-scene-thumb', data }, window.location.origin);
  });
}

// Выноска: плашка с текстом и линия к месту. Смещение плашки задаёт offset в пикселях,
// поэтому при зуме она остаётся рядом с местом, а не уезжает.
function addCallout(item, opts = {}) {
  const [dx0, dy0] = item.offset || [70, -50];
  let dx = dx0;
  let dy = dy0;
  const el = document.createElement('div');
  el.className = 'callout';
  if (markPalette[item.color]) el.style.setProperty('--mc', markPalette[item.color]);
  if (opts.selected) el.classList.add('is-selected');

  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('class', 'callout-line');
  svg.setAttribute('width', '1');
  svg.setAttribute('height', '1');
  const line = document.createElementNS(ns, 'line');
  line.setAttribute('x1', '0');
  line.setAttribute('y1', '0');
  const dot = document.createElementNS(ns, 'circle');
  dot.setAttribute('r', '3.2');
  svg.append(line, dot);

  const box = document.createElement('div');
  box.className = 'callout-box';
  box.textContent = item.text;

  const place = () => {
    line.setAttribute('x2', String(dx));
    line.setAttribute('y2', String(dy));
    box.style.left = `${dx}px`;
    box.style.top = `${dy}px`;
  };
  place();
  el.append(svg, box);

  if (opts.onOffset) {
    // правка: плашку можно тянуть, клик выбирает выноску
    box.classList.add('callout-edit');
    box.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      event.stopPropagation();
      opts.onSelect();
      const start = { x: event.clientX, y: event.clientY, dx, dy };
      const move = (e) => { dx = Math.round(start.dx + e.clientX - start.x); dy = Math.round(start.dy + e.clientY - start.y); place(); };
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        if (dx !== start.dx || dy !== start.dy) opts.onOffset([dx, dy]);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    });
    // точку выноски двигает маркер карты
  } else if (item.url) {
    box.classList.add('callout-link');
    box.addEventListener('click', (event) => { event.stopPropagation(); postLink(item.url, item.text); });
  }

  const marker = new maplibregl.Marker({ element: el, anchor: 'center', draggable: !!opts.onMove })
    .setLngLat(item.coords)
    .addTo(map);
  if (opts.onMove) marker.on('dragend', () => { const p = marker.getLngLat(); opts.onMove([p.lng, p.lat]); });
  return marker;
}


// Гладкая линия через точки (квадратичные кривые по серединам отрезков)
function penSmooth(points) {
  if (points.length < 3) return penPath(points, false, 0);
  let d = `M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const mx = (points[i].x + points[i + 1].x) / 2;
    const my = (points[i].y + points[i + 1].y) / 2;
    d += ` Q${points[i].x.toFixed(1)} ${points[i].y.toFixed(1)} ${mx.toFixed(1)} ${my.toFixed(1)}`;
  }
  const last = points[points.length - 1];
  return `${d} L${last.x.toFixed(1)} ${last.y.toFixed(1)}`;
}
