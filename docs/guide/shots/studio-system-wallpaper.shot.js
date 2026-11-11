// ОС: картинка и узор рабочего стола.
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/systems/AETHER/style`);
    await pause(2500);
    await page.getByText("Картинка и узор").first().scrollIntoViewIfNeeded();
    await pause(1000);
  },
};
