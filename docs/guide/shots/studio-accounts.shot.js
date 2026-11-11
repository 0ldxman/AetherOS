// Учётки машины aether-main.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/machines`);
    await page.getByText("aether-main", { exact: true }).first().click();
    await page.locator("nav.tabs a.tab", { hasText: "Учётки" }).first().click();
    await pause(1200);
    await page.locator(".item, a.row").first().click().catch(() => {});
    await pause(1200);
  },
};
