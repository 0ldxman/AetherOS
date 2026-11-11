// Редактор варианта ответа: шаг ask, вариант «Give the password».
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/mail`);
    await pause(900);
    await page.locator("a.talk").first().click();
    await page.locator(".svelte-flow__node").first().waitFor();
    await pause(1200);
    await page.locator(".svelte-flow__node:has(.name:text-is(\"ask\")) header").click();
    await pause(1000);
    await page.locator("text=Give the password").last().click().catch(() => {});
    await pause(600);
    await page.getByText("Когда доступен").first().click().catch(() => {});
    await page.getByText("Вложение и попытки").first().click().catch(() => {});
    await pause(1000);
  },
};
