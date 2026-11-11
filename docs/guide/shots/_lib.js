// Помощники для видео: плавный курсор, клики, набор текста и «камера» (приближение области экрана).
// Курсор рисует run.js; здесь только движение. Файл с подчёркиванием run.js за сценарий не считает.

const W = 1280, H = 720;
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const place = (page) => (page.__pos ||= { x: W / 2, y: H / 2 });

/** Ведёт курсор в точку по плавной кривой за ms миллисекунд. */
async function glide(page, x, y, ms = 800) {
  const from = { ...place(page) };
  const steps = Math.max(10, Math.round(ms / 16));
  const bend = Math.hypot(x - from.x, y - from.y) * 0.06;                 // лёгкая дуга, чтобы движение не было линейкой
  for (let i = 1; i <= steps; i++) {
    const t = ease(i / steps), arc = Math.sin(Math.PI * t) * bend;
    const px = from.x + (x - from.x) * t + arc, py = from.y + (y - from.y) * t - arc;
    await page.mouse.move(px, py);
    await page.waitForTimeout(ms / steps);
  }
  await page.mouse.move(x, y);
  page.__pos = { x, y };
}

const center = async (locator) => {
  await locator.scrollIntoViewIfNeeded();
  const b = await locator.boundingBox();
  return { x: b.x + b.width / 2, y: b.y + b.height / 2, box: b };
};

/** Подводит курсор к элементу и нажимает. */
async function click(page, locator, ms = 800) {
  const { x, y } = await center(locator);
  await glide(page, x, y, ms);
  await page.waitForTimeout(180);
  await page.mouse.down();
  await page.waitForTimeout(90);
  await page.mouse.up();
}

/** Печатает в поле по символу, как живой человек. */
async function type(page, locator, text, delay = 55) {
  await click(page, locator, 600);
  await page.keyboard.type(text, { delay });
}

/** Тащит от точки к точке: from и to это {x, y}. */
async function drag(page, from, to, ms = 1100) {
  await glide(page, from.x, from.y, 700);
  await page.waitForTimeout(150);
  await page.mouse.down();
  await page.waitForTimeout(120);
  await glide(page, to.x, to.y, ms);
  await page.waitForTimeout(150);
  await page.mouse.up();
}

/** Камера: плавно приближает прямоугольник экрана {x, y, w, h}; без аргумента возвращает общий план.
 *  Не тащите мышью при включённой камере: холст карты считает сдвиги без поправки на масштаб. */
async function camera(page, rect, { ms = 1100, max = 1.7 } = {}) {
  await page.evaluate(({ rect, ms, max, W, H }) => {
    const body = document.body;
    document.documentElement.style.overflow = "hidden";
    body.style.transformOrigin = "0 0";
    body.style.transition = `transform ${ms}ms cubic-bezier(.45,.05,.25,1)`;
    if (!rect) { body.style.transform = "none"; return; }
    const s = Math.min(max, W / rect.w, H / rect.h);
    const tx = Math.min(0, Math.max(W - W * s, W / 2 - (rect.x + rect.w / 2) * s));
    const ty = Math.min(0, Math.max(H - H * s, H / 2 - (rect.y + rect.h / 2) * s));
    body.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
  }, { rect, ms, max, W, H });
  await page.waitForTimeout(ms + 150);
}

/** Приближение самого холста карты колесом мыши в точке (родное, поэтому тащить можно). */
async function zoomMap(page, x, y, notches = 4) {
  await glide(page, x, y, 600);
  for (let i = 0; i < notches; i++) {
    await page.mouse.wheel(0, -90);
    await page.waitForTimeout(110);
  }
  await page.waitForTimeout(500);
}

module.exports = { glide, click, type, drag, camera, zoomMap, center };
