const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({headless: "new"});
  const page = await browser.newPage();
  await page.setViewport({width: 1200, height: 3000});
  await page.goto('file:///home/kangjh3kang/My_Projects/Development_AI/propai-platform/kakao_review_template.html', {waitUntil: 'networkidle0'});
  await page.screenshot({path: 'kakao_business_review.png', fullPage: true});
  await browser.close();
})();
