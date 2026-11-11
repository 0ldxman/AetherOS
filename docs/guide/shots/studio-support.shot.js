// Поддержка: обращение игрока.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/support`);
    await pause(1200);
    await page.getByText("Door code does not work").first().click();
    await pause(1800);
  },
};
