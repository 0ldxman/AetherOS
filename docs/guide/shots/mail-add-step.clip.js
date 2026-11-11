// Новый шаг на карте, перенос в свободное место и стрелка к нему от выхода варианта.
const { click, drag, center } = require("./_lib");

module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/mail`);
    await pause(1200);
    await click(page, page.locator("a.talk").first());
    await page.locator(".svelte-flow__node").first().waitFor();
    await pause(1800);
    await click(page, page.locator('button:has-text("+ Шаг")'));
    await pause(1300);
    // новый шаг появляется поверх других: уводим его в свободное место, расстановка ручная
    const head = page.locator('.svelte-flow__node:has(.name:text-is("step")) header');
    const at = await center(head);
    await drag(page, { x: at.x - 60, y: at.y }, { x: at.x + 230, y: at.y + 170 }, 1300);
    await pause(900);
    await click(page, page.locator(".svelte-flow__controls-fitview").first());                  // карта подгоняет масштаб под все шаги
    await pause(1200);
    const handle = page.locator('.svelte-flow__node:has(.name:text-is("ask")) .socket .svelte-flow__handle').last();
    const target = page.locator('.svelte-flow__node:has(.name:text-is("step")) header');
    const from = await center(handle);
    const to = await center(target);
    await drag(page, { x: from.x, y: from.y }, { x: to.x - 20, y: to.y }, 1600);
    await pause(2200);
  },
  // Правки остаются черновиком на сервере: отменяем, чтобы следующие съёмки видели исходный сценарий.
  async cleanup({ page, base, pause }) {
    await page.goto(`${base}/studio/#/mail`);
    await pause(900);
    await page.locator("a.talk").first().click();
    await page.locator(".svelte-flow__node").first().waitFor();
    await pause(800);
    if ((await page.locator(".draft").innerText()).includes("Не сохранено")) {
      await page.click('button:has-text("Отменить правки")');
      await pause(300);
      await page.locator('button:has-text("Отменить правки")').last().click();
      await pause(800);
    }
  },
};
