// Диск с файлами.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/volumes`);
    await pause(1500);
    await page.getByText("Harbor archive").first().click();
    await pause(1500);
    await page.getByText("ports", { exact: true }).first().click().catch(() => {});
    await pause(1800);
  },
};
