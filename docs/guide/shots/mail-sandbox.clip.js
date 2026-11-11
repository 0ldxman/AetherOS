// Песочница: игрок на первом шаге выбирает ответ, применяем исход и идём дальше.
const { click, type, camera } = require("./_lib");

module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/mail`);
    await pause(1200);
    await click(page, page.locator("a.talk").first());
    await page.locator(".svelte-flow__node").first().waitFor();
    await pause(1500);
    await click(page, page.locator('button[role="tab"]:has-text("Песочница")'));
    await pause(900);
    await camera(page, { x: 840, y: 150, w: 440, h: 360 }, { max: 2.2 });                   // панель песочницы: что видит игрок в ответе
    await pause(700);
    await click(page, page.locator(".offer:has-text('Ask for dock access')"));
    await pause(500);
    await type(page, page.locator('textarea[aria-label="Набранный текст"]'), "I need access to the docks.");
    await pause(500);
    await click(page, page.locator('button:has-text("Отправить")'));
    await pause(700);
    await camera(page, { x: 840, y: 330, w: 440, h: 390 }, { max: 2.2 });                   // результат и журнал
    await pause(1800);
    await click(page, page.locator('button:has-text("Применить и идти дальше")'));
    await pause(1800);
    await camera(page, null);
    await pause(1500);
  },
};
