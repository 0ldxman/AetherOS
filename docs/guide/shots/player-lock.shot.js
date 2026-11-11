// Экран замка: история подключения и выбор входа (без входа в игру).
module.exports = {
  as: "anon",
  async run({ page, base, pause }) {
    await page.goto(`${base}/lock/`);
    await page.waitForFunction(() => /discord|external authority/i.test(document.body.innerText), null, { timeout: 60000 });
    await pause(1500);
  },
};
