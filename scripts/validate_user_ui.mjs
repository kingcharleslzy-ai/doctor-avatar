import { chromium, devices } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";

const url = process.env.USER_URL || "https://liyong828.com/hospital-ai";
const outputDir = path.resolve("output");
const desktopShot = path.join(outputDir, "user-desktop-validation.png");
const mobileShot = path.join(outputDir, "user-mobile-validation.png");
const dumpPath = path.join(outputDir, "user-validation.json");

const chromeCandidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
].filter(Boolean);

async function firstExisting(paths) {
  for (const candidate of paths) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch (_) {}
  }
  return null;
}

async function launchBrowser() {
  const executablePath = await firstExisting(chromeCandidates);
  return chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });
}

async function validateDesktop(browser) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1024 },
  });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
  await page.locator("#startConsultBtn").waitFor();
  const startLabel = await page.locator("#startConsultBtn").innerText();
  const hasVoiceBtn = await page.locator("#voiceInputBtn").isVisible();
  const missingButtonLabels = await page.evaluate(() => {
    const ids = ["askBtn", "vcMuteBtn", "vcEndBtn", "vcTranscriptBtn", "vcTranscriptClose"];
    return ids.filter((id) => {
      const button = document.getElementById(id);
      return !button || !button.getAttribute("aria-label");
    });
  });
  if (missingButtonLabels.length) {
    throw new Error(`缺少按钮 aria-label: ${missingButtonLabels.join(", ")}`);
  }
  await page.locator("#message").fill("慢性鼻窦炎反复发作，一般要先做什么检查？");
  await page.locator("#askBtn").click();
  await waitForSettledAssistantAnswer(page);
  const answer = await page.locator("#chatHistory .msg-row.ai .bubble").last().innerText();
  if (answer.includes("你现在最主要的不舒服是什么")) {
    throw new Error(`慢性鼻窦炎检查问题被错误引导回主诉确认：${answer}`);
  }
  if (answer.includes("？") || answer.includes("?") || answer.includes("请问")) {
    throw new Error(`慢性鼻窦炎检查问题不应追加追问：${answer}`);
  }
  await page.screenshot({ path: desktopShot, fullPage: true });
  await context.close();
  return {
    startLabel,
    hasVoiceBtn,
    answer,
    screenshot: desktopShot,
  };
}

async function waitForSettledAssistantAnswer(page) {
  await page.waitForFunction(() => {
    const rows = [...document.querySelectorAll("#chatHistory .msg-row.ai .bubble")];
    const last = rows.at(-1);
    return rows.length >= 2 && last && !last.querySelector(".typing-dots") && last.textContent.trim().length > 8;
  }, { timeout: 90000 });

  let lastText = "";
  let stableCount = 0;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const state = await page.evaluate(() => {
      const rows = [...document.querySelectorAll("#chatHistory .msg-row.ai .bubble")];
      return {
        text: rows.at(-1)?.textContent.trim() || "",
        status: document.getElementById("voiceStatus")?.textContent || "",
      };
    });
    if (state.text === lastText) stableCount += 1;
    else stableCount = 0;
    lastText = state.text;
    if (stableCount >= 2 && !["正在回答", "正在生成回答", "正在生成回答..."].includes(state.status)) {
      return;
    }
    await page.waitForTimeout(1000);
  }
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
  const browser = await launchBrowser();
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
