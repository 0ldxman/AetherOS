// Клиент API студии. Пути и типы берутся из схемы OpenAPI (npm run api), поэтому опечатка в адресе или поле это ошибка
// TypeScript, а не 404 в браузере. Сайт может жить под префиксом прокси (/proxy/8000/): его даёт страница (window.STUDIO).
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";
import { ask } from "./confirm.svelte";

declare global {
  interface Window {
    STUDIO: { api: string; admin: string; site: string; mapData: string };
  }
}

export type Schemas = components["schemas"];

const prefix = window.STUDIO.api.replace(/studio\/api\/?$/, "").replace(/\/$/, "");

function csrf(): string {
  return document.cookie.split("; ").find((row) => row.startsWith("csrftoken="))?.split("=")[1] ?? "";
}

export const api = createClient<paths>({ baseUrl: prefix, credentials: "same-origin" });

api.use({
  onRequest({ request }) {
    if (request.method !== "GET") request.headers.set("X-CSRFToken", csrf());
    return request;
  },
});

// Версия при сохранении (team.changes): ответ на чтение несёт номер ленты (X-Version), он запоминается для адреса.
// Правка или удаление шлёт номер самого близкого загруженного адреса (сам адрес или его родитель). Если с тех пор эту
// сущность изменил кто-то другой, сервер отвечает 409, и Студия спрашивает, сохранить ли поверх (X-Force).
const versions = new Map<string, number>();
const retries = new Map<string, Request>();
let nextRequest = 1;

function apiPath(url: string): string {
  const path = new URL(url, location.href).pathname;
  const at = path.indexOf("/studio/api/");
  return at < 0 ? "" : path.slice(at + "/studio/api/".length).replace(/\/+$/, "");
}

function baseFor(path: string): number | undefined {
  let best = -1;
  let found: number | undefined;
  for (const [key, value] of versions) {
    if ((path === key || path.startsWith(key + "/")) && key.length > best) {
      best = key.length;
      found = value;
    }
  }
  return found;
}

api.use({
  onRequest({ request }) {
    if (!["PUT", "PATCH", "DELETE"].includes(request.method)) return request;
    const base = baseFor(apiPath(request.url));
    if (base !== undefined) request.headers.set("X-Base-Version", String(base));
    const id = String(nextRequest++);
    request.headers.set("X-Studio-Request", id);
    retries.set(id, request.clone());
    return request;
  },
  async onResponse({ request, response }) {
    const id = request.headers.get("X-Studio-Request") ?? "";
    const retry = retries.get(id);
    retries.delete(id);
    const remember = (answer: Response) => {
      const version = answer.headers.get("X-Version");
      if (answer.ok && version) versions.set(apiPath(request.url), +version);
    };
    if (response.status !== 409 || !retry) {
      remember(response);
      return response;
    }
    const body = await response.clone().json().catch(() => null);
    if (!body?.stale) return response;
    const over = await ask("Конфликт правок", `${body.detail} Сохранить ваше поверх? Чтобы сначала посмотреть чужую правку, откажитесь и обновите страницу.`, "Сохранить поверх");
    if (!over) return response;
    retry.headers.set("X-Force", "1");
    const forced = await fetch(retry);
    remember(forced);
    return forced;
  },
});

/** Текст ошибки из ответа API: {detail} от сервера или общая фраза. */
export function problem(error: unknown, fallback = "Что-то пошло не так."): string {
  if (error && typeof error === "object" && "detail" in error && typeof error.detail === "string") return error.detail;
  return fallback;
}

/** Адрес страницы старой админки (на время переезда экранов). */
export function adminUrl(path: string): string {
  return window.STUDIO.admin + path.replace(/^\//, "");
}
