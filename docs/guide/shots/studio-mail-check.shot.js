// Вкладка «Проверка» сценария.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/mail`);
    await pause(900);
    await page.locator("a.talk").first().click();
    await page.locator(".svelte-flow__node").first().waitFor();
    await pause(1200);
    await page.locator("button[role=tab]", { hasText: "Проверка" }).click();
    await pause(1200);
  },
};
