import { chromium } from "playwright";
import path, { dirname } from "path";
import dotenv from "dotenv";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ✅ Load .env
dotenv.config({ path: path.join(__dirname, "../.env") });

const query = process.argv.slice(2).join(" ");
if (!query) {
  console.error("❌ No query provided!");
  process.exit(1);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // ✅ Spoof a real Chrome browser fingerprint
  await page.setExtraHTTPHeaders({
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
  });

  // ✅ Use Bing instead of Google/DuckDuckGo (less bot detection)
  const searchUrl = `https://www.bing.com/search?q=${encodeURIComponent(query)}`;
  console.log(`🔍 Searching: ${searchUrl}`);

  await page.goto(searchUrl, { waitUntil: "domcontentloaded" });

  // ✅ Extract top 5 results
  const results = await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll("li.b_algo"));
    return items.slice(0, 5).map((item) => ({
      title: item.querySelector("h2")?.innerText || "",
      snippet: item.querySelector(".b_caption p")?.innerText || "",
      url: item.querySelector("h2 a")?.href || "",
    }));
  });

  console.log(JSON.stringify({ top_results: results }, null, 2));

  await browser.close();
})();
