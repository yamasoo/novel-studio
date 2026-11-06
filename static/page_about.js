/* 關於頁（轉移計畫 §8.2.1）：從 app.js 的 viewAbout／ABOUT_LINKS 搬過來（原本 3263-3330）。
   全部用 FE.h 建節點、只寫 ctx.view；about 不碰 S.book（舊 route() 對它也沒有 setBook）。 */
(function () {
  "use strict";

  const { h } = FE;

  const ABOUT_LINKS = [
    ["設計參考", [
      ["oh-story-claudecode", "https://github.com/worldwonderer/oh-story-claudecode", "MIT", "novel-* skills 的部分設計概念改寫自此專案（授權全文見 plugin/THIRD_PARTY_NOTICES.md）"],
      ["Chinese-WebNovel-Skill", "https://github.com/Tomsawyerhu/Chinese-WebNovel-Skill", "", "參考中文網文寫作 skill 的流程分工（只參考概念）"],
      ["moshu 墨書", "https://github.com/huihuijiangqiang/moshu", "", "頁面分工與「AI 草稿先進候選區」的概念（未使用其程式碼）"],
      ["Pagekin（AI-Novel-Writer）", "https://github.com/EthanYoQ/AI-Novel-Writer", "GPL-3.0", "思考強度分階段、寫稿前對帳、章綱核對、審查與修訂分開、恢復稿等做法（只參考概念，未使用其程式碼）"],
      ["Novelcrafter：effective style entries", "https://www.novelcrafter.com/courses/codex-cookbook/effective-style-entries", "", "文風寫「怎麼寫」、給彈性範圍不給死數字（novel-style 參考概念）"],
      ["Sudowrite：Style", "https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/style/4gqKgVVjdN6XTKo71HChqV", "", "依場景類型給有標籤的範例段落（參考概念）"],
      ["Scriveno：STYLE-GUIDE", "https://cdn.jsdelivr.net/npm/scriveno@3.8.0/templates/STYLE-GUIDE.md", "", "文風的面向分類與 Always／Never／Consider 三分（參考概念）"],
      ["Leech & Short 文體分析清單", "https://www.lancaster.ac.uk/fass/projects/stylistics/topic10/12method.htm", "", "《Style in Fiction》的詞彙、語法、修辭、銜接分析框架（參考概念）"],
    ]],
    ["工作台使用的套件", [
      ["FastAPI", "https://github.com/fastapi/fastapi", "MIT", "網頁伺服器"],
      ["Uvicorn", "https://github.com/encode/uvicorn", "BSD-3-Clause", "網頁伺服器"],
      ["PyYAML", "https://github.com/yaml/pyyaml", "MIT", "讀取設定檔的 frontmatter"],
      ["OpenCC（opencc-python-reimplemented）", "https://github.com/yichen0831/opencc-python", "Apache-2.0", "匯入舊稿時簡體轉台灣繁體"],
      ["marked", "https://github.com/markedjs/marked", "MIT", "在網頁上顯示 Markdown（經 fekit 的 FE.md，檔案在 vendor/fekit/vendor/marked）"],
    ]],
    ["可以連接的 AI 與工具（不隨專案附帶）", [
      ["Claude Code", "https://docs.claude.com/en/docs/claude-code/overview", "", "用 Claude 訂閱執行 novel-* skills"],
      ["DeepSeek API", "https://api-docs.deepseek.com/", "", "OpenAI 相容服務"],
      ["llama.cpp", "https://github.com/ggml-org/llama.cpp", "MIT", "本機模型（OpenAI 相容服務）"],
      ["Stable Diffusion WebUI Forge – Neo", "https://github.com/Haoming02/sd-webui-forge-classic/tree/neo", "", "插圖出圖（需用 --api 啟動）"],
      ["ComfyUI", "https://github.com/comfyanonymous/ComfyUI", "GPL-3.0", "插圖出圖的另一個後端（透過 API，只用內建節點）"],
      ["Anima", "https://huggingface.co/circlestone-labs/Anima", "", "提示詞格式依此模型的建議（標籤＋自然語言）"],
      ["a1111-sd-webui-tagcomplete", "https://github.com/DominikDoom/a1111-sd-webui-tagcomplete", "MIT", "標籤檢查與中文對照表使用它附的 tags 檔案（從 Forge 資料夾讀取，不隨專案附帶）"],
      ["StyleSelectorXL", "https://github.com/ahgsql/StyleSelectorXL", "MIT", "樣式表格式相容（範例在 examples/styles.example.json）"],
      ["EPUBCheck", "https://github.com/w3c/epubcheck", "", "匯出的 EPUB 用它驗證過"],
    ]],
  ];

  function linkCard([group, rows]) {
    return h("div", { class: "card about", style: "margin-top:14px" },
      h("h2", { style: "margin-bottom:10px" }, group),
      h("table", {}, rows.map(([name, url, license, desc]) => h("tr", {},
        h("td", { class: "nm" }, h("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, name)),
        h("td", {}, license ? h("span", { class: "badge" }, license) : null),
        h("td", { class: "small" }, desc)))));
  }

  async function render(ctx) {
    let ver = "";
    // 版本號只有這個端點有（boot.js 只留了 config）；拿不到就留白，和舊版一樣。
    try { ver = (await FE.api("/api/config", { signal: ctx.signal })).version; } catch (e) { /* ignore */ }

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "關於小說工作台"),
          h("div", { class: "sub" }, "Novel Studio v" + ver + "　·　MIT 授權"))),
      h("div", { class: "card about" },
        h("p", {}, "用 AI 寫繁體中文長篇連載小說的本機工作台。小說資料（設定、大綱、追蹤、正文）全部是純 Markdown＋YAML，存在你自己的書庫資料夾；網頁介面負責專案管理，寫作流程可以交給 Claude Code，或 DeepSeek、llama.cpp 等 OpenAI 相容模型。"),
        h("ul", { class: "small" },
          h("li", {}, "只在本機執行（127.0.0.1），不會對外開放；工作台本身不會把資料傳到任何地方，只有你按下 AI 動作時，才會把需要的內容送給你選的 AI 服務。"),
          h("li", {}, "你的設定（config.json）與 API 金鑰（secrets.json）只存在工作台資料夾，不會進 git。"),
          h("li", {}, "書庫、共用庫（書庫的 ", h("code", {}, "_共用"), "）、插圖都在你的書庫資料夾，和工作台程式分開。")),
        h("p", { class: "small muted" }, "本專案以 MIT 授權發布，全文見專案根目錄的 ", h("code", {}, "LICENSE"), "。")),
      ABOUT_LINKS.map(linkCard));
  }

  nsPage("about", "about", {}, render);
})();
