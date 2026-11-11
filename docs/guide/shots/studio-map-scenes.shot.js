// Карта: редактор сцены.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/map/scenes`);
    await pause(1500);
    await page.locator("a.card").first().click().catch(() => {});
    await pause(5000);
  },
};
