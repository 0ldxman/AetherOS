// Песочница: игрок на первом шаге выбирает ответ, применяем исход и идём дальше.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/mail`);
    await pause(900);
    await page.locator("a.talk").first().click();
    await page.locator(".svelte-flow__node").first().waitFor();
    await pause(1200);
    await page.click('button[role="tab"]:has-text("Песочница")');
    await pause(1500);
    await page.click(".offer:has-text('Ask for dock access')");
    await pause(1000);
    await page.locator('textarea[aria-label="Набранный текст"]').pressSequentially("I need access to the docks.", { delay: 40 });
    await pause(500);
    await page.click('button:has-text("Отправить")');
    await pause(2000);
    await page.click('button:has-text("Применить и идти дальше")');
    await pause(2500);
  },
};
