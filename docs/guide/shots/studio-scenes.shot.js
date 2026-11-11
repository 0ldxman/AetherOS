// Редактор сцены.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/scenes`);
    await pause(1500);
    await page.locator("a.item, .item").first().click().catch(() => {});
    await pause(1800);
  },
};
