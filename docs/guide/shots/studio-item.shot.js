// Объект с защитой: вкладка «Защита».
module.exports = {
  as: "author",
  async run({ page, base, pause }) {
    await page.goto(`${base}/studio/#/items`);
    await pause(1500);
    await page.getByText("door.bin").first().click();
    await pause(1200);
    await page.locator("nav.pagetabs").getByText("Защита").first().click();
    await pause(1500);
  },
};
