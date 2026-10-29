// Клиент API студии. Пути и типы берутся из схемы OpenAPI (npm run api), поэтому опечатка в адресе или поле это ошибка
// TypeScript, а не 404 в браузере. Сайт может жить под префиксом прокси (/proxy/8000/): его даёт страница (window.STUDIO).
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

declare global {
  interface Window {
    STUDIO: { api: string; admin: string; site: string };
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

/** Текст ошибки из ответа API: {detail} от сервера или общая фраза. */
export function problem(error: unknown, fallback = "Что-то пошло не так."): string {
  if (error && typeof error === "object" && "detail" in error && typeof error.detail === "string") return error.detail;
  return fallback;
}

/** Адрес страницы старой админки (на время переезда экранов). */
export function adminUrl(path: string): string {
  return window.STUDIO.admin + path.replace(/^\//, "");
}
