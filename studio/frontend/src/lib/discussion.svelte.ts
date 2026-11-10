// Обсуждение сущности, на которой сейчас автор: путь API этой сущности по адресу страницы Студии (как ключ ленты
// team.changes) и открыта ли боковая панель обсуждения.
export const discussion = $state({ open: false });

const RULES: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^\/machines\/(\d+)/, (m) => `machines/${m[1]}`],
  [/^\/items\/(\d+)/, (m) => `items/${m[1]}`],
  [/^\/volumes\/(\d+)\/text\/(\d+)/, (m) => `volumes/${m[1]}/text-files/${m[2]}`],
  [/^\/volumes\/(\d+)/, (m) => `volumes/${m[1]}`],
  [/^\/policies\/(\d+)/, (m) => `policies/${m[1]}`],
  [/^\/systems\/([^/]+)/, (m) => `systems/${m[1]}`],
  [/^\/scenes\/([^/]+)/, (m) => `scenes/${m[1]}`],
  [/^\/formats\/([^/]+)/, (m) => `file-formats/${m[1]}`],
  [/^\/encodings\/([^/]+)/, (m) => `file-encodings/${m[1]}`],
  [/^\/map\/(scenes|countries|provinces)\/(\d+)/, (m) => `map/${m[1]}/${m[2]}`],
  [/^\/map\/territory/, () => "map/territory"],
  [/^\/players\/(\d+)/, (m) => `players/${m[1]}`],
  [/^\/boards\/(\d+)/, (m) => `boards/${m[1]}`],
  [/^\/team\/roles\/(\d+)/, (m) => `team/roles/${m[1]}`],
  [/^\/world/, () => "world"],
];

/** Сущность Студии по адресу страницы (#/machines/3/accounts → machines/3) или пусто, если обсуждать нечего. */
export function targetOf(path: string): string {
  for (const [pattern, make] of RULES) {
    const found = path.match(pattern);
    if (found) return make(found);
  }
  return "";
}
