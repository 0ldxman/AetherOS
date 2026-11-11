// Диски машины: образ, монтирования, экспорты.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/machines`);
    await page.getByText("aether-main", { exact: true }).first().click();
    await page.locator("nav.tabs a.tab", { hasText: "Диски" }).first().click();
    await pause(1800);
  },
};
