// Внешний вид карты в Студии. Три стиля это три темы игровой карты (map/static/map.js: dark, maps, scan), чтобы автор видел
// территории так же, как их увидит игрок в приложении, в документах и на «бумажной» карте. Свои тайлы (без внешних сервисов):
// вода, суша и провинции.
export type MapLook = {
  label: string;
  hint: string;
  water: string;
  land: string;
  empty: string;          // провинция без владельца
  line: string;           // границы провинций
  opacity: number;        // заливка провинций
  pick: string;           // выделение
  hover: string;          // обводка под курсором
};

export const LOOKS: Record<string, MapLook> = {
  dark: { label: "Тёмная", hint: "Основная карта приложения, редактор и тёмные документы", water: "#0a1722", land: "#16222d", empty: "#26313c", line: "rgba(220,235,255,.28)", opacity: 0.88, pick: "#ffffff", hover: "#ffd23f" },
  maps: { label: "Карты", hint: "Светлая карта в духе онлайн-карт: документы и светлые страницы", water: "#a9d3f5", land: "#f1efe9", empty: "#e1ddd2", line: "rgba(60,64,67,.45)", opacity: 0.66, pick: "#1a1a1a", hover: "#e8710a" },
  scan: { label: "Бумага", hint: "Бумажная карта с пометками от руки", water: "#c9d4d6", land: "#e8dfcb", empty: "#d8ceb5", line: "rgba(107,91,62,.55)", opacity: 0.62, pick: "#1a1a1a", hover: "#b3261e" },
};

export type MapView = "political" | "physical";
export const VIEWS: { key: MapView; label: string; hint: string }[] = [
  { key: "political", label: "Политическая", hint: "Провинции закрашены по владельцам, видны границы" },
  { key: "physical", label: "Физическая", hint: "Только суша и вода: без цветов владельцев и границ (инструменты по-прежнему работают)" },
];

// Чьи владения показывать: у записи могут быть признаки де-юре (по праву) и де-факто (по контролю)
export type Rights = "all" | "jure" | "facto";
export const RIGHTS: { key: Rights; label: string; hint: string }[] = [
  { key: "all", label: "Все владения", hint: "Провинция закрашена, если у неё есть владелец с любым признаком" },
  { key: "jure", label: "Де-юре", hint: "Только провинции, которыми страна владеет по праву (признанные границы)" },
  { key: "facto", label: "Де-факто", hint: "Только провинции, которые страна реально контролирует" },
];
