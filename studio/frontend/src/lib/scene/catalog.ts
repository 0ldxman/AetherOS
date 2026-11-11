// Что умеет язык сцен: каждая запись это шаблон для вставки, подсказка в автодополнении и строка шпаргалки.
// В шаблонах ${1:имя} это поле, которое заполняют по Tab, а \{ и \} это обычные скобки (так требует snippet() CodeMirror).
export type Snip = {
  group: string;
  title: string;                  // как называется по-человечески
  code: string;                   // как выглядит в тексте: @task или <type>
  args: string;                   // чем заполняется
  doc: string;                    // что делает
  template: string;
  example: string;                // пример сцены; в справке он играет сам
  play: "run" | "instant" | "none";   // как показывать результат: с паузами, сразу или не показывать
};

export const GROUPS = ["Вывод", "Загрузка", "Время", "Эффекты", "Структура"] as const;

export const SNIPPETS: Snip[] = [
  { group: "Вывод", title: "Комментарий", code: "#", args: "текст", doc: "Строка не выводится. Чтобы вывести строку с #, напишите \\#.", template: "# ${1:комментарий}", example: "# Это не выводится\nЗагрузка…", play: "instant" },
  { group: "Вывод", title: "Тусклая строка", code: "~", args: "текст", doc: "Вывод приглушённым цветом.", template: "~ ${1:текст}", example: "~ приглушённая строка\nобычная строка", play: "instant" },
  { group: "Вывод", title: "Печать по буквам", code: "<type>", args: "текст", doc: "Печатается побуквенно. human: живее, typo: с опечатками, speed: мс на букву.", template: "<type human>${1:текст}</type>", example: "$ <type human>ssh ivan@{host}</type>", play: "run" },
  { group: "Вывод", title: "Растущее число", code: "<count/>", args: "to, unit, ms", doc: "Число бежит вверх до значения за время ms (диапазон выбирается заново при каждом показе).", template: "<count to=${1:64000} unit=${2:K} ms=${3:600-1100}/>", example: "Памяти: <count to=64000 unit=K ms=1200/>", play: "run" },
  { group: "Вывод", title: "Курсор", code: "<cursor/>", args: "", doc: "Мигающий курсор после приглашения: > <cursor/>.", template: "<cursor/>", example: "$ <cursor/><type human>reboot</type>", play: "run" },
  { group: "Вывод", title: "Пометка", code: "<mark>", args: "имя", doc: "Помечает кусок текста, чтобы потом исказить его шагом @glitch.", template: "<mark ${1:имя}>${2:текст}</mark>", example: "Статус: <mark st>стабильно</mark>\n@wait 700\n@glitch st | сбой связи", play: "run" },
  { group: "Вывод", title: "Таблица", code: "<table>", args: "ячейки через |", doc: "Колонки с выровненной шириной. gap: пробелов между колонками.", template: "<table gap=${1:4}>\n${2:ячейка} | ${3:ячейка}\n</table>", example: "<table gap=3>\nимя | роль\nivan | admin\nguest | user\n</table>", play: "instant" },

  { group: "Загрузка", title: "Задача", code: "@task", args: "метка | результат | мс", doc: "Строка вида «метка ..... OK» с паузой. Параметры: look=unit|kernel, note=, style=, width=.", template: "@task ${1:метка} | ${2:OK} | ${3:200-450}", example: "@task Диски | OK | 300-600\n@task Сеть | FAIL | 400", play: "run" },
  { group: "Загрузка", title: "Юнит", code: "@unit", args: "имя | описание | результат | мс", doc: "Строка службы в стиле загрузки aeinit.", template: "@unit ${1:имя} | ${2:описание} | ${3:OK} | ${4:200-450}", example: "@unit aeinit | Запуск служб | OK | 400", play: "run" },
  { group: "Загрузка", title: "Полоса прогресса", code: "@bar", args: "метка | мс", doc: "Полоса заполняется за время мс. width: ширина.", template: "@bar ${1:метка} | ${2:900}", example: "@bar Копирование | 1200", play: "run" },
  { group: "Загрузка", title: "Счёт", code: "@count", args: "метка | до | единица | мс", doc: "Число растёт до значения. result=, note=: итог после счёта.", template: "@count ${1:метка} | ${2:64000} | ${3:K} | ${4:800}", example: "@count Блоки | 64000 | K | 900", play: "run" },
  { group: "Загрузка", title: "Строка журнала", code: "@log", args: "сек | тег | сообщение", doc: "Строка с отметкой времени, как в журнале ядра.", template: "@log ${1:0.5} | ${2:тег} | ${3:сообщение}", example: "@log 0.1 | kernel | модуль загружен\n@log 0.4 | net | линк поднят", play: "run" },

  { group: "Время", title: "Пауза", code: "@wait", args: "мс", doc: "Ждать. Число или диапазон 200-450.", template: "@wait ${1:450}", example: "до паузы\n@wait 1000\nпосле паузы", play: "run" },
  { group: "Время", title: "Пауза на чтение", code: "@read", args: "", doc: "Пауза, достаточная, чтобы прочесть строки выше.", template: "@read", example: "Длинное сообщение, которое нужно прочесть.\n@read\nДальше.", play: "run" },
  { group: "Время", title: "Пустые строки", code: "@blank", args: "число", doc: "Пустые строки.", template: "@blank ${1:1}", example: "строка\n@blank 2\nстрока", play: "instant" },

  { group: "Эффекты", title: "Глитч", code: "@glitch", args: "имя | новый текст", doc: "Искажает кусок, помеченный <mark имя>. frames: число кадров.", template: "@glitch ${1:имя} | ${2:новый текст}", example: "Статус: <mark st>стабильно</mark>\n@glitch st | сбой связи", play: "run" },
  { group: "Эффекты", title: "Обратный отсчёт", code: "@countdown", args: "текст с \\{n\\} | секунд", doc: "Строка со счётчиком: n подставляется на каждом шаге.", template: "@countdown ${1:Старт через \\{n\\}с...} | ${2:5}", example: "@countdown Старт через {n}с... | 3", play: "run" },
  { group: "Эффекты", title: "Обрыв", code: "@cut", args: "", doc: "Экран обрывается.", template: "@cut", example: "последняя строка\n@cut", play: "instant" },
  { group: "Эффекты", title: "Вспышка", code: "@flash", args: "", doc: "Короткая вспышка экрана.", template: "@flash", example: "до вспышки\n@flash\nпосле вспышки", play: "run" },
  { group: "Эффекты", title: "Очистить экран", code: "@clear", args: "", doc: "Экран очищается.", template: "@clear", example: "будет стёрто\n@wait 600\n@clear\nчисто", play: "run" },

  { group: "Структура", title: "Вставить сцену", code: "@include", args: "слаг", doc: "Вставляет другую сцену библиотеки (вложенность до 8).", template: "@include ${1:слаг}", example: "@include boot-units", play: "none" },
  { group: "Структура", title: "Блок строк", code: "@rows", args: "подпись | значение | стиль | пояснение", doc: "Строки с отступом выравниваются в колонки. width: ширина подписи.", template: "@rows width=${1:12}\n  ${2:подпись} | ${3:значение} | ${4:стиль} | ${5:пояснение}", example: "@rows width=10\n  host | {host} | dim | имя машины\n  user | ivan | success | кто вошёл", play: "instant" },
  { group: "Структура", title: "Блок полос", code: "@bars", args: "подпись | мс | результат | стоп%", doc: "Несколько полос прогресса разом.", template: "@bars width=${1:14}\n  ${2:подпись} | ${3:900} | ${4:OK} | ${5:100}", example: "@bars width=14\n  ядро | 600 | OK | 100\n  сеть | 900 | FAIL | 60", play: "run" },
  { group: "Структура", title: "Пачка строк", code: "@burst", args: "строки с отступом", doc: "Строки вывода одна за другой с паузой gap (мс, число или диапазон).", template: "@burst gap=${1:8-45}\n  ${2:строка}", example: "@burst gap=8-45\n  строка один\n  строка два\n  строка три", play: "run" },
];

// «слов» для автодополнения: @-шаги и теги
export const STEP_WORDS = SNIPPETS.filter((s) => s.code.startsWith("@"));
export const TAG_WORDS = SNIPPETS.filter((s) => s.code.startsWith("<"));
