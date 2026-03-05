#!/usr/bin/env node
import { chromium } from 'playwright';

const url = process.argv[2];
if (!url) {
  console.error('Usage: fetch_rendered_html.mjs <url>');
  process.exit(2);
}

const timeout = Number(process.env.PW_TIMEOUT_MS || 30000);

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36',
  });

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
  await page.waitForTimeout(2500);

  const html = await page.content();
  process.stdout.write(html);
} finally {
  await browser.close();
}
