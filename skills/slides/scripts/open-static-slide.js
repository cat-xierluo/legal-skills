'use strict';

const { pathToFileURL } = require('node:url');

// Select the authored static view before measuring or capturing any slide.
// The opt-in CSS affects scene content only; background handling is separate.
async function openStaticSlide(page, filePath, options) {
  await page.goto(pathToFileURL(filePath).href, options);
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-slides-static-export', '');
  });
}

module.exports = { openStaticSlide };
