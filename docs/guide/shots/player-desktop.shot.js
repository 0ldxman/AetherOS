// Рабочий стол игрока на машине aether-main.
module.exports = {
  as: "player",
  async run({ page, base, pause }) {
    await page.goto(`${base}/desktop/`);
    await pause(2500);
  },
};
