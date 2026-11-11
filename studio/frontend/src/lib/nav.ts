// Разделы Студии для боковой панели: группы, значки и права. Первая группа без заголовка и не сворачивается.
export type NavItem = { href: string; label: string; section: string[]; right: string; icon: string };
export type NavGroup = { id: string; title: string; items: NavItem[] };

export const GROUPS: NavGroup[] = [
  {
    id: "work", title: "", items: [
      { href: "#/home", label: "Главная", section: ["home"], right: "", icon: "home" },
      { href: "#/boards", label: "Доска", section: ["boards"], right: "", icon: "board" },
      { href: "#/tasks", label: "Задачи", section: ["tasks", "task"], right: "", icon: "tasks" },
      { href: "#/guide", label: "Справка", section: ["guide"], right: "", icon: "guide" },
    ],
  },
  {
    id: "players", title: "Игроки", items: [
      { href: "#/players", label: "Игроки", section: ["players"], right: "players", icon: "players" },
      { href: "#/mail", label: "Почта", section: ["mail", "talk"], right: "mail", icon: "mail" },
      { href: "#/news", label: "Новости", section: ["news"], right: "news", icon: "news" },
      { href: "#/support", label: "Поддержка", section: ["support"], right: "support", icon: "support" },
      { href: "#/air", label: "Эфир", section: ["air"], right: "air", icon: "radio" },
    ],
  },
  {
    id: "data", title: "Содержимое", items: [
      { href: "#/items", label: "Объекты", section: ["items", "item"], right: "items", icon: "items" },
      { href: "#/volumes", label: "Диски и файлы", section: ["volumes", "volume", "text"], right: "disks", icon: "disks" },
      { href: "#/formats", label: "Форматы", section: ["formats", "encodings"], right: "formats", icon: "formats" },
      { href: "#/systems", label: "Операционные системы", section: ["systems"], right: "systems", icon: "systems" },
      { href: "#/machines", label: "Машины", section: ["machines", "machine"], right: "machines", icon: "machines" },
    ],
  },
  {
    id: "world", title: "Мир", items: [
      { href: "#/world", label: "Мир", section: ["world"], right: "world", icon: "world" },
      { href: "#/map", label: "Карта", section: ["map"], right: "map", icon: "map" },
      { href: "#/scenes", label: "Сцены", section: ["scenes"], right: "scenes", icon: "scenes" },
      { href: "#/policies", label: "Политики входа", section: ["policies"], right: "policies", icon: "policies" },
    ],
  },
];

export const NAV: NavItem[] = GROUPS.flatMap((group) => group.items);
