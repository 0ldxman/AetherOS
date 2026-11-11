// Песочница автора: окно с рабочим столом песочного игрока поверх Студии.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/machines`);
    await pause(1500);
    await page.locator("a.row, a.item, .rows a").first().click().catch(() => {});
    await pause(1500);
    await page.getByRole("tab", { name: "Проверка входа" }).click().catch(() => {});
    await pause(1200);
    await page.getByRole("button", { name: "Открыть песочницу" }).click().catch(() => {});
    await pause(5000);
  },
};
