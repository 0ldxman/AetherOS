// Вики: архив порта.
module.exports = {
  as: "player",
  async run({ page, base, pause }) {
    await page.goto(`${base}/apps/wiki/`);
    await pause(1500);
    await page.locator('text=Harbor').first().dblclick();
    await pause(1500);
  },
};
