import { chromium, devices } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";

const url = process.env.USER_URL || "https://liyong828.com/";
const outputDir = path.resolve("output");
const desktopShot = path.join(outputDir, "user-desktop-validation.png");
const mobileShot = path.join(outputDir, "user-mobile-validation.png");
const dumpPath = path.join(outputDir, "user-validation.json");

async function validateDesktop(browser) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1024 },
  });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  await page.locator("#startConsultBtn").waitFor();
  const startLabel = await page.locator("#startConsultBtn").innerText();
  const hasVoiceBtn = await page.locator("#voiceInputBtn").isVisible();
  await page.locator("#message").fill("慢性鼻窦炎反复发作，一般要先做什么检查？");
  await page.locator("#askBtn").click();
  await page.waitForFunction(() => {
    const rows = [...document.querySelectorAll("#chatHistory .msg-row.ai .bubble")];
    const last = rows.at(-1);
    return rows.length >= 2 && last && !last.querySelector(".typing-dots") && last.textContent.trim().length > 6;
  }, { timeout: 90000 });
  const answer = await page.locator("#chatHistory .msg-row.ai .bubble").last().innerText();
  await page.screenshot({ path: desktopShot, fullPage: true });
  await context.close();
  return {
    startLabel,
    hasVoiceBtn,
    answer,
    screenshot: desktopShot,
  };
}

async function validateMobile(browser) {
  const context = await browser.newContext({
    ...devices["iPhone 13"],
  });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  await page.locator("#startConsultBtn").waitFor();
  const startLabel = await page.locator("#startConsultBtn").innerText();
  const hasVoiceBtn = await page.locator("#voiceInputBtn").isVisible();
  await page.screenshot({ path: mobileShot, fullPage: true });
  await context.close();
  return {
    startLabel,
    hasVoiceBtn,
    screenshot: mobileShot,
  };
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const desktop = await validateDesktop(browser);
  const mobile = await validateMobile(browser);
  const summary = {
    url,
    desktop,
    mobile,
  };
  await fs.writeFile(dumpPath, JSON.stringify(summary, null, 2), "utf-8");
  console.log(JSON.stringify(summary, null, 2));
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
