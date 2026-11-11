// Новый шаг на карте и стрелка к нему от выхода варианта.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/mail`);
    await pause(900);
    await page.locator("a.talk").first().click();
    await page.locator(".svelte-flow__node").first().waitFor();
    await pause(1500);
    await page.click('button:has-text("+ Шаг")');
    await pause(1200);
    // новый шаг появляется поверх других: уводим его в свободное место, расстановка ручная
    const head = page.locator('.svelte-flow__node:has(.name:text-is("step")) header');
    const at = await head.boundingBox();
    await page.mouse.move(at.x + 40, at.y + 12, { steps: 12 });
    await page.mouse.down();
    await page.mouse.move(at.x + 250, at.y + 160, { steps: 25 });
    await page.mouse.up();
    await pause(900);
    const handle = page.locator('.svelte-flow__node:has(.name:text-is("ask")) .socket .svelte-flow__handle').last();
    const target = page.locator('.svelte-flow__node:has(.name:text-is("step")) header');
    const from = await handle.boundingBox();
    const to = await target.boundingBox();
    await page.mouse.move(from.x + 90, from.y - 60, { steps: 12 });
    await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2, { steps: 10 });
    await page.mouse.down();
    await page.mouse.move(from.x + 60, from.y + 10, { steps: 10 });
    await page.mouse.move(to.x + 60, to.y + 10, { steps: 25 });
    await pause(400);
    await page.mouse.up();
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
