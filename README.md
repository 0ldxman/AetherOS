# AetherOS

Игра в виде операционной системы: рабочий стол, терминал, вики, почта и карта. Игрок подключается к машинам, читает файлы,
добывает ключи и пароли. Мир описывают авторы в студии (`/studio/`) и, пока экраны переезжают, в админке Django.

## Карта проекта

| Папка | Что внутри |
|---|---|
| `config/` | настройки, urls, wsgi |
| `docs/` | спецификации; `docs/storage-spec.md` описывает хранилище, права, политику входа, часы и сетевые диски |
| **Ядро мира** | |
| `secure/` | условия по ключам (`access`), реестр ключей (`keys`), где используется ключ (`usage`) |
| `machines/` | машины, учётные записи, группы и привилегии, политика входа, сетевые подключения, мосты, часы. Подпапки: `models/`, `admin/`, `access/` (политика входа, группы, окна времени), `network/` (подключение к хосту, мосты), `world/` (места, диалекты путей, часы, облик машины) |
| `filesystem/` | тома, объекты, размещения, слой игрока, права. Подпапки: `models`, `machine_view/` (вид машины для игрока), `layers/` (защитные слои и хуки), `content/` (байты файла, форматы, источники, окно файла), `manager/` (файловый менеджер админки), `admin/` |
| **Что видит игрок** | |
| `desktop/` | рабочий стол и экран загрузки |
| `terminal/` | терминал: `engine/` (команды), `scenes/` (анимации вокруг ответов), `views` |
| `documents/` | свои форматы (.doc, .scan, .snp, .rec): парсер `markup/`, `widgets/`, окно документа `/view/doc/`, стили `static/document/`, редактор и предпросмотр в админке (`editor`) |
| `wiki/` | вики как проводник: `library` (разделы по хостам), дерево, список, поиск; файл открывается окном по своему формату; `admin/` |
| `mail/` | почта |
| `map/` | карта и редактор сцен |
| `monitor/` | окно сессий |
| `assets/` | хранилище ассетов (Nextcloud) и вьюверы |
| `users/` | вход, гость, выход |
| `scenes/` | движок консольных сцен и сцены экранов (загрузка, вход) |
| `static/ui`, `templates/ui` | общая оболочка: стили, шрифты, базовый шаблон |
| **Для авторов** | |
| `studio/` | студия, новая админка: `api/` (django-ninja, `/studio/api/`, схема `/studio/api/docs`), `frontend/` (Svelte 5, TypeScript, Vite) |

Тесты каждого приложения лежат в его папке `tests/`; общие помощники тестов: `filesystem/testing.py`, `terminal/testing.py`,
`wiki/testing.py`.

## Запуск

```
pip install -r requirements.txt
cp .env.example .env              # настройки окружения
python manage.py migrate
python manage.py seed_demo        # демонстрационный мир: машины aether-main (ivan / demo) и aether-core
python manage.py runserver
```

Студия (нужен Node 22): собранный фронт ложится в `studio/static/studio/app` и в git не хранится.
`manage.py runserver` сам запускает сборку в режиме наблюдения (`npm run watch`), правки фронта видны после обновления
страницы; `--no-studio` её отключает. Вручную:

```
cd studio/frontend
npm ci
npm run build                     # один раз; во время работы над фронтом: npm run watch
npm run api                       # после правки API: схема OpenAPI и типы TypeScript (src/lib/schema.d.ts)
npm run check                     # проверка типов
```

Тесты:

```
python manage.py test
```

## С чего читать код

1. `docs/storage-spec.md`: как устроены тома, вид машины, права, сеть.
2. `filesystem/machine_view/`: как собирается дерево файлов, которое видит игрок.
3. `terminal/engine/commands/`: команды терминала.
4. `machines/access/entry.py`: кто и когда может войти на запись.
