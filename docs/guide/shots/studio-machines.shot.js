// Список машин.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/machines`);
    await page.getByText("aether-main", { exact: true }).first().waitFor();
    await pause(1200);
  },
};
