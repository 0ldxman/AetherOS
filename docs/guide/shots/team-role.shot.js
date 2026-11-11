// Роль «Полный доступ» с правами по разделам.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/team`);
    await pause(1200);
    await page.locator('a.item[href^="#/team/roles/"]').first().click();
    await pause(1200);
  },
};
