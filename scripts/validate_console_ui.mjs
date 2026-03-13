import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";

const url = process.env.CONSOLE_URL || "https://liyong828.com/console";
const username = process.env.CONSOLE_USERNAME || "admin";
const password = process.env.CONSOLE_PASSWORD || "";
const outputDir = path.resolve("output");
const screenshotPath = path.join(outputDir, "console-validation.png");
const textPath = path.join(outputDir, "console-validation.txt");

function includesAny(text, patterns) {
  const normalized = text.toLowerCase();
  return patterns.some((pattern) => normalized.includes(pattern.toLowerCase()));
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1200 },
    extraHTTPHeaders: password
      ? {
          Authorization: `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`,
        }
      : {},
  });

  const page = await context.newPage();
  await page.goto(url, { waitUntil: "networkidle" });

  const bodyText = await page.locator("body").innerText();
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await fs.writeFile(textPath, bodyText, "utf-8");

  const summary = {
    title: await page.title(),
    url: page.url(),
    screenshot: screenshotPath,
    textDump: textPath,
    hasCpu: includesAny(bodyText, ["CPU Load", "CPU LOAD"]),
    hasMemory: includesAny(bodyText, ["Memory Usage", "MEMORY USAGE"]),
    hasDisk: includesAny(bodyText, ["Disk Usage", "DISK USAGE"]),
    hasActiveUsers: includesAny(bodyText, ["Active Users", "ACTIVE USERS"]),
    hasReadOnly: includesAny(bodyText, ["Read-only Monitor", "只读模式", "只读监控", "Read-only"]),
    hasMemoryCode: includesAny(bodyText, ["MEMORY CODE", "资料库暗号"]),
    hasRequests: includesAny(bodyText, ["REQUESTS TOTAL", "请求总量"]),
  };

  console.log(JSON.stringify(summary, null, 2));
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
