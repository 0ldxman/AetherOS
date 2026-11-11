// Обсуждение на странице машины aether-core.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/machines`);
    await page.getByText("aether-core", { exact: true }).first().click();
    await pause(1500);
    await page.getByRole("button", { name: /Обсуждение/ }).first().click();
    await pause(1500);
  },
};
