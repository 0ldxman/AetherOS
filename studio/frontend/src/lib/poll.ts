// Опрос сервера, который молчит на скрытой вкладке и сразу обновляется, когда вкладку открыли снова. Возвращает остановку.
export function poll(load: () => unknown, every: number): () => void {
  const tick = () => { if (!document.hidden) load(); };
  const timer = setInterval(tick, every);
  document.addEventListener("visibilitychange", tick);
  return () => { clearInterval(timer); document.removeEventListener("visibilitychange", tick); };
}
