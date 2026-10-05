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

  // Всё оставленное из подложки, кроме фона и воды (леса, здания, дороги),
  // переносим наверх, поверх островов. Порядок между ними сохраняется.
  const overlayIds = map.getStyle().layers
    .filter(l =>
      !isBackground(l) &&
      !isWaterLayer(l) &&
      l.id !== 'aether-lands-fill'
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
});

// Курсор-прицел
const crosshair = document.createElement('div');
crosshair.id = 'crosshair';
crosshair.innerHTML = '<div class="h"></div><div class="v"></div><div class="box"></div>';
document.body.appendChild(crosshair);

window.addEventListener('mousemove', (e) => {
  crosshair.style.setProperty('--x', `${e.clientX}px`);
  crosshair.style.setProperty('--y', `${e.clientY}px`);
  crosshair.classList.add('visible');
});

document.documentElement.addEventListener('mouseleave', () => {
  crosshair.classList.remove('visible');
});