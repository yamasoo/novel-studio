/* 設定頁（轉移計畫 §8.2.13）：從 app.js 的 viewSettings（原 1385-1638）搬過來。
   nsPage("settings","settings",{clearBook:true},render)——舊 route() 對 settings 就是 setBook(null, true)。
   留誰誰走的判定（grep 依據見回報）：本頁用到的 top-level 名稱全部是別頁／Panel／boot 也在用的，
   所以都留在 app.js，這裡直接呼叫：provOpts／provChoices／provName／stepProv／STEP_OF_ACTION／AI_STEP_LABELS
   （Panel.openForm、Panel.renderProv、pipeModal、boot.js）、attachPicker（書架、插圖頁）、
   renderIllSettings（插圖頁）、restartServer（window.restartServer 匯出）、readFiles／bookOpts（共用庫、匯入頁）。
   沒有「只有設定頁在用」的 top-level 名稱，所以這一頁沒有帶走任何 helper。
   provOpts 仍是字串版，這裡用 nsShared.nodesFromHtml 轉成 option 節點（不碰 innerHTML）。 */
(function () {
  "use strict";

  const { h } = FE;
  const { nodesFromHtml } = nsShared;
  const enc = encodeURIComponent;

  const EFFORT_LABEL = { off: "關閉", low: "低", medium: "中", high: "高", max: "最高" };
  const PERM_OPTIONS = [
    ["acceptEdits", "acceptEdits：可自動讀寫書目錄內的檔案（建議）"],
    ["default", "default：需要權限的動作會被拒絕"],
    ["bypassPermissions", "bypassPermissions：全部放行（風險較高）"],
  ];

  async function render(ctx) {
    const signal = ctx.signal;
    const r = await FE.api("/api/config", { signal });
    const RM = await FE.api("/api/reasoning", { signal }).catch(() => ({}));
    S.config = r.config;
    S.claudeFound = r.claude_found;
    S.keyStatus = r.key_status;
    const c = r.config;

    // ── 服務 ──
    const portInput = h("input", { type: "number", id: "c-port", value: String(r.port), min: "1024", max: "65535" });
    const restartBtn = h("button", { id: "c-restart", disabled: !r.can_restart }, "重新啟動服務");

    // ── 書庫 ──
    const libInput = h("input", { type: "text", id: "c-lib", value: c.library || "" });

    // ── Claude Code ──
    const cmdInput = h("input", { type: "text", id: "c-cmd", value: c.claude_cmd || "", placeholder: "例如 C:\\Users\\你\\.local\\bin\\claude.exe" });
    const modelInput = h("input", { type: "text", id: "c-model", value: c.model || "", placeholder: "例如 opus、sonnet" });
    const permSel = h("select", { id: "c-perm" },
      PERM_OPTIONS.map(([v, l]) => h("option", { value: v, selected: c.permission_mode === v }, l)));
    const dirsArea = h("textarea", { id: "c-dirs", rows: "2" }, (c.add_dirs || []).join(String.fromCharCode(10)));
    const toolsArea = h("textarea", { id: "c-tools", rows: "5" }, (c.allowed_tools || []).join(String.fromCharCode(10)));

    // ── AI 執行者 ──
    const defProvSel = h("select", { id: "c-defprov" }, nodesFromHtml(provOpts(c.default_provider)));
    const keyStoreBox = h("div", { id: "key-store", style: "margin-bottom:10px" });
    const provList = h("div", { id: "prov-list" });
    const provAddBtn = h("button", { class: "sm", id: "prov-add" }, "＋ 新增 OpenAI 相容服務");

    // ── 寫稿品質 ──
    const reconBox = h("input", { type: "checkbox", id: "c-recon", checked: c.reconcile_before_write !== false });
    const goalBox = h("input", { type: "checkbox", id: "c-goal", checked: c.goal_check_after_write !== false });

    // ── 整章自動流程 ──
    const psevBoxes = ["必須修", "建議修", "提醒"].map((x) => h("label", { class: "cb" },
      h("input", { type: "checkbox", value: x, checked: (c.pipeline_severities || ["必須修", "建議修"]).includes(x) }),
      " " + x));
    const pmodeRadios = [
      ["stop", "寫一章停一章", c.pipeline_mode !== "continue"],
      ["continue", "連續寫到最後一章", c.pipeline_mode === "continue"],
    ].map(([v, label, checked]) => h("label", {},
      h("input", { type: "radio", name: "c-pmode", value: v, checked }),
      h("span", {}, label)));
    const pscheckBox = h("input", { type: "checkbox", id: "c-pscheck", checked: c.pipeline_style_check !== false });
    const apeInput = h("input", { type: "number", id: "c-ape", min: "0", value: String(c.autopilot_every != null ? c.autopilot_every : 0) });
    const apsmInput = h("input", { type: "number", id: "c-apsm", min: "1", value: String(c.autopilot_stop_must != null ? c.autopilot_stop_must : 1) });
    const apssInput = h("input", { type: "number", step: "0.1", id: "c-apss", min: "1", value: String(c.autopilot_stop_style != null ? c.autopilot_stop_style : 2.4) });
    const pprovGrid = h("div", { class: "grid g4", id: "c-pprov" },
      AI_STEP_LABELS.map(([k, l]) => h("label", { class: "f" },
        h("span", {}, l),
        h("select", { "data-step": k },
          h("option", { value: "" }, "跟流程的執行者"),
          nodesFromHtml(provOpts((c.pipeline_providers || {})[k]))))));

    // ── 插圖設定 ──
    const illCard = h("div", { class: "card", id: "ill-settings" });

    // ── 警示 ──
    const sfInput = h("input", { type: "number", id: "c-sf", value: String(c.stale_foreshadow) });
    const scInput = h("input", { type: "number", id: "c-sc", value: String(c.stale_character) });

    const saveBtn = h("button", { class: "primary", id: "c-save" }, "儲存設定");

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {}, h("h1", {}, "設定"), h("div", { class: "sub" }, "小說工作台 v" + (r.version || "")))),
      h("div", { class: "card" },
        h("h2", { style: "margin-bottom:12px" }, "服務"),
        h("div", { class: "row", style: "align-items:flex-end" },
          h("label", { class: "f", style: "margin:0;width:160px" }, h("span", {}, "連接埠"), portInput),
          h("span", { class: "grow muted small" },
            "目前網址 ", h("code", {}, location.origin),
            (r.port !== r.running_port && r.running_port)
              ? ["　", h("span", { class: "badge b-warn" }, "已改成 " + r.port + "，重新啟動後生效")]
              : null),
          restartBtn),
        h("div", { class: "muted small", style: "margin-top:8px" },
          "改了連接埠、更新了工作台的程式檔，或服務怪怪的時候用。有任務在執行時無法重新啟動。",
          r.can_restart ? null : [h("br"), "目前的啟動方式不支援自動重新啟動，請關閉黑色視窗後重新執行 start.bat。"])),
      h("div", { class: "card" },
        h("h2", { style: "margin-bottom:12px" }, "書庫"),
        h("label", { class: "f" }, h("span", {}, "書庫資料夾（每本書是裡面的一個子資料夾）"), libInput),
        h("div", { class: "muted small" }, r.library_exists ? "✓ 資料夾存在" : "✗ 資料夾不存在，儲存時會自動建立")),
      h("div", { class: "card" },
        h("h2", { style: "margin-bottom:12px" }, "Claude Code 執行者"),
        h("div", { class: "kv", style: "margin-bottom:12px" },
          h("span", { class: "k" }, "偵測結果"),
          h("span", {}, r.claude_found
            ? [h("span", { class: "badge b-ok" }, "找到"), " ", h("code", {}, r.claude_found)]
            : h("span", { class: "badge b-bad" }, "找不到 claude 指令"))),
        h("label", { class: "f" }, h("span", {}, "claude 執行檔路徑（留空＝自動尋找）"), cmdInput),
        h("label", { class: "f" }, h("span", {}, "模型（留空＝Claude Code 預設）"), modelInput),
        h("label", { class: "f" }, h("span", {}, "權限模式"), permSel),
        h("label", { class: "f" }, h("span", {}, "額外允許讀取的資料夾（一行一個）"), dirsArea),
        h("div", { class: "muted small", style: "margin:-6px 0 12px" },
          "novel-* skills 已內建在工作台的 ", h("code", {}, "plugin"), " 資料夾，會自動載入，不用填。這裡只放你想讓 Claude 額外讀取的資料夾（例如參考資料）。"),
        h("label", { class: "f" }, h("span", {}, "額外允許的工具（一行一個）"), toolsArea),
        h("div", { class: "muted small" }, "預設允許 skill、python 檢查腳本與 git。Claude 會在書目錄裡執行，看不到書目錄以外的東西。")),
      h("div", { class: "card" },
        h("h2", { style: "margin-bottom:4px" }, "AI 執行者"),
        h("div", { class: "muted small", style: "margin-bottom:12px" },
          "Claude Code 用你的訂閱，會自己讀寫檔案，所有功能都能用。其他模型（DeepSeek、本機 llama.cpp 等 OpenAI 相容服務）由工作台組裝資料再送出，所有按鈕都能用，結果由工作台檢查後寫檔。"),
        h("label", { class: "f" }, h("span", {}, "預設執行者"), defProvSel),
        keyStoreBox,
        provList,
        provAddBtn),
      h("div", { class: "card" },
        h("h2", { style: "margin-bottom:12px" }, "寫稿品質（非 Claude 模型）"),
        h("label", { class: "cb" }, reconBox, " 寫章節前先做定稿對帳（多一次小呼叫，比對章綱事件和已定稿事實）"),
        h("label", { class: "cb" }, goalBox, " 寫完候選稿後自動核對章綱（逐項附原文引句，由程式驗證）"),
        h("div", { class: "muted small" }, "用 Claude Code 寫稿時，對帳與核對寫在 novel-write skill 的流程裡；章節頁的「核對章綱」按鈕兩種執行者都能用。")),
      h("div", { class: "card" },
        h("h2", { style: "margin-bottom:12px" }, "整章自動流程"),
        h("div", { class: "muted small", style: "margin-bottom:8px" },
          "章綱 → 寫章節（候選稿）→ 章綱核對 → 去 AI 味 → 文風檢查 → 審查意見 → 自動勾選 → 依勾選意見修訂 → 全部套用 → 定稿並回寫追蹤。7 個步驟各呼叫一次 AI；文風檢查、自動勾選、全部套用是本機計算，不呼叫模型。"),
        h("div", { class: "f" }, h("span", {}, "自動勾選哪些等級的審查意見")),
        h("div", { class: "row", id: "c-psev" }, psevBoxes),
        h("div", { class: "f", style: "margin-top:8px" }, h("span", {}, "預設跑法")),
        h("div", { class: "seg compact", id: "c-pmode" }, pmodeRadios),
        h("div", { class: "muted small", style: "margin-top:6px" }, "章綱核對發現沒寫到的情節點，會一併交給修訂。開始時也可以臨時改這兩項。"),
        h("label", { class: "cb", style: "margin-top:10px" }, pscheckBox, " 文風檢查（本機計算，不花錢；關掉就跳過這一步）"),
        h("div", { class: "f", style: "margin-top:12px" }, h("span", {}, "自動駕駛：每幾章停下來檢查一次（0＝不檢查）")),
        h("div", { class: "grid g3" },
          h("label", { class: "f" }, h("span", {}, "每幾章檢查"), apeInput),
          h("label", { class: "f" }, h("span", {}, "必須修幾項就停"), apsmInput),
          h("label", { class: "f" }, h("span", {}, "文風偏離幾倍就停"), apssInput)),
        h("div", { class: "muted small" }, "連續寫才有效。檢查點會看這幾章有沒有「必須修」與文風偏離，不及格就停在那一章等人（漂移線索只記錄、不停）。成本：每次檢查都是本機計算，不花錢。"),
        h("div", { class: "f", style: "margin-top:12px" }, h("span", {}, "各步驟的執行者（面板上對應的按鈕也預設用這裡的分配）")),
        pprovGrid,
        h("div", { class: "muted small" }, "建議：寫章節、去 AI 味、修訂用寫作品質最好的模型；審查可以換另一個模型交叉檢查；定稿回寫追蹤會改寫時間線與伏筆，不建議交給小型本機模型。指定的執行者連不上時，流程會停在那一步。")),
      illCard,
      h("div", { class: "card" },
        h("h2", { style: "margin-bottom:12px" }, "警示"),
        h("div", { class: "grid g2" },
          h("label", { class: "f" }, h("span", {}, "伏筆幾章沒出現就提醒"), sfInput),
          h("label", { class: "f" }, h("span", {}, "角色幾章沒登場就提醒"), scInput))),
      h("div", { class: "row", style: "margin-top:14px" }, h("span", { class: "grow" }), saveBtn));

    renderIllSettings(illCard).catch(FE.fail);
    attachPicker(libInput, { mode: "dir", title: "選擇書庫資料夾" });
    attachPicker(cmdInput, { mode: "file", title: "選擇 claude 執行檔" });
    attachPicker(dirsArea, { mode: "dir", title: "加入允許讀取的資料夾" }, true);

    const provs = JSON.parse(JSON.stringify((c.providers || []).filter((p) => p.type !== "claude_code")));
    const keys = {};

    function provCard(p, i) {
      const field = (label, input) => h("label", { class: "f" }, h("span", {}, label), input);
      const keyHint = S.keyStatus && S.keyStatus[p.id] ? h("span", { class: "badge " + (S.keyStatus[p.id].startsWith("secrets.json") ? "b-warn" : "b-ok") }, S.keyStatus[p.id]) : null;
      const keyInput = h("input", {
        type: "password", "data-key": "1", value: keys[p.id] || "",
        placeholder: S.keyStatus && S.keyStatus[p.id] ? "留空＝不變更" : "本機服務可留空",
      });
      const modelInput2 = h("input", { type: "text", "data-k": "model", value: p.model || "", list: "ml-" + i, placeholder: "按「測試連線」可以選" });
      const cjkInput = h("input", { type: "number", step: "0.05", min: "0.2", max: "3", "data-k": "cjk_token_ratio", value: p.cjk_token_ratio || "", placeholder: "自動", style: "flex:1" });
      const calibBtn = h("button", { class: "sm", "data-a": "calib", title: "llama.cpp 用 /tokenize 實際算" }, "校正");

      const card = h("div", { class: "prov-card", "data-i": String(i) },
        h("div", { class: "row", style: "margin-bottom:8px" },
          h("b", {}, p.name || p.id),
          h("span", { class: "badge" }, p.id),
          h("span", { class: "grow" }),
          h("button", { class: "sm", "data-a": "test" }, "測試連線／抓模型清單"),
          h("button", { class: "sm danger", "data-a": "del" }, "刪除")),
        h("div", { class: "grid g2" },
          field("顯示名稱", h("input", { type: "text", "data-k": "name", value: p.name || "" })),
          field("網址（Base URL）", h("input", { type: "text", "data-k": "base_url", value: p.base_url || "", placeholder: "https://api.deepseek.com 或 http://127.0.0.1:8080/v1" })),
          field("模型名稱", h("div", {}, modelInput2, h("datalist", { id: "ml-" + i }))),
          h("label", { class: "f" }, h("span", {}, "API 金鑰 ", keyHint), keyInput),
          field("或用環境變數名稱", h("input", { type: "text", "data-k": "key_env", value: p.key_env || "", placeholder: "例如 DEEPSEEK_API_KEY" })),
          field("上下文長度（tokens）", h("input", { type: "number", "data-k": "context_tokens", value: p.context_tokens == null ? "" : String(p.context_tokens) })),
          field("最大輸出（tokens）", h("input", { type: "number", "data-k": "max_output", value: p.max_output == null ? "" : String(p.max_output) })),
          field("每個中文字約幾 token（估算上下文用；空白＝自動：DeepSeek 0.6、其他 1.2）", h("div", { class: "row" }, cjkInput, calibBtn)),
          field("溫度", h("input", { type: "number", step: "0.1", "data-k": "temperature", value: p.temperature == null ? "" : String(p.temperature) })),
          field("輸入價格（每百萬 tokens，美元，選填）", h("input", { type: "number", step: "0.01", "data-k": "price_in", value: String(p.price_in || 0) })),
          field("輸出價格（每百萬 tokens，美元，選填）", h("input", { type: "number", step: "0.01", "data-k": "price_out", value: String(p.price_out || 0) }))));

      if (p.id !== "llamacpp") {
        const modelsBox = h("div", { "data-mchips": "" === "" ? "" : "", class: "small", style: "margin-top:6px" });
        const addmBtn = h("button", { class: "sm", "data-a": "addm" }, "新增模型");
        const rows = (p.models || []).map((m, j) => h("div", { class: "row", style: "gap:6px;margin-top:6px;flex-wrap:wrap" },
          h("input", { type: "text", "data-m": String(j), "data-mk": "id", value: m.id || "", placeholder: "模型代號", list: "ml-" + i, style: "width:190px" }),
          h("input", { type: "text", "data-m": String(j), "data-mk": "name", value: m.name || "", placeholder: "顯示名稱（選填）", style: "width:130px" }),
          h("input", { type: "number", "data-m": String(j), "data-mk": "context_tokens", value: m.context_tokens || "", placeholder: "上下文長度", style: "width:110px" }),
          h("input", { type: "number", "data-m": String(j), "data-mk": "max_output", value: m.max_output || "", placeholder: "最大輸出", style: "width:100px" }),
          h("input", { type: "number", step: "0.01", "data-m": String(j), "data-mk": "price_in", value: m.price_in || "", placeholder: "輸入價格", style: "width:90px" }),
          h("input", { type: "number", step: "0.01", "data-m": String(j), "data-mk": "price_out", value: m.price_out || "", placeholder: "輸出價格", style: "width:90px" }),
          h("input", { type: "number", step: "0.05", "data-m": String(j), "data-mk": "cjk_token_ratio", value: m.cjk_token_ratio || "", placeholder: "中文 token 比例", style: "width:120px" }),
          h("button", { class: "sm danger", "data-mdel": String(j), title: "移除這個模型" }, "✕")));
        card.append(
          h("div", { class: "reason-box" },
            h("div", { class: "row", style: "margin-bottom:4px" },
              h("b", { class: "small" }, "可用模型"),
              h("span", { class: "muted small" },
                "預設模型是上面的「模型名稱」。這裡加上其他模型後，各處的執行者選單就能選「" + (p.name || p.id) + " · 模型」；金鑰共用，空白的欄位沿用上面的設定。"),
              h("span", { class: "grow" }),
              addmBtn),
            (p.models || []).length
              ? h("div", { class: "row muted small", style: "gap:6px;margin-top:4px;flex-wrap:wrap" },
                h("span", { style: "width:190px" }, "模型代號"),
                h("span", { style: "width:130px" }, "顯示名稱"),
                h("span", { style: "width:110px" }, "上下文長度"),
                h("span", { style: "width:100px" }, "最大輸出"),
                h("span", { style: "width:90px" }, "輸入價格"),
                h("span", { style: "width:90px" }, "輸出價格"),
                h("span", { style: "width:120px" }, "每個中文字幾 token"))
              : null,
            rows.length ? rows : h("div", { class: "muted small" }, "還沒有其他模型。按「測試連線／抓模型清單」後，可以從清單點選加入。"),
            modelsBox));
      }

      card.append(
        h("label", { class: "cb" }, h("input", { type: "checkbox", "data-k": "json_mode", checked: p.json_mode !== false }), " 支援 JSON 模式（response_format）"),
        h("div", { class: "reason-box" },
          h("div", { class: "row", style: "margin-bottom:6px" },
            h("b", { class: "small" }, "思考強度"),
            h("span", { class: "muted small" }, "推理模型的思考也算在輸出 token 裡；整理 JSON 這類格式任務通常可以關閉。")),
          h("label", { class: "f" }, h("span", {}, "控制方式"), h("select", { "data-r": "adapter" },
            Object.entries(RM.adapters || {}).map(([k, v]) => h("option", { value: k, selected: ((p.reasoning || {}).adapter || "none") === k }, v)))),
          h("div", { class: "grid g4" },
            Object.entries(RM.stages || {}).map(([st, lbl]) => h("label", { class: "f" },
              h("span", {}, lbl),
              h("select", { "data-r": st },
                (RM.efforts || []).map((e) => h("option", { value: e, selected: ((p.reasoning || {})[st] || "") === e }, EFFORT_LABEL[e]))))))),
        h("label", { class: "f" }, h("span", {}, "額外參數（JSON，會合併進請求，選填）"),
          h("textarea", { "data-k": "extra", rows: "2", placeholder: '例如 {"top_p": 0.95}' },
            p.extra && Object.keys(p.extra).length ? JSON.stringify(p.extra) : "")),
        h("div", { class: "small muted", "data-msg": "" }));

      return card;
    }

    function renderProvs() {
      provList.replaceChildren(...(provs.length
        ? provs.map((p, i) => provCard(p, i))
        : [h("div", { class: "muted small", style: "margin-bottom:8px" }, "沒有其他服務。")]));

      // 重新綁事件（每次重畫都重綁，和舊版一樣）
      provList.querySelectorAll(".prov-card").forEach((card) => {
        const i = +card.dataset.i;
        card.querySelectorAll("[data-k]").forEach((inp) => {
          inp.oninput = inp.onchange = () => {
            const k = inp.dataset.k;
            provs[i][k] = inp.type === "checkbox" ? inp.checked : inp.value;
          };
        });
        card.querySelector("[data-key]").oninput = (ev) => { keys[provs[i].id] = ev.target.value; };
        card.querySelectorAll("[data-mk]").forEach((inp) => {
          inp.oninput = () => {
            const m = provs[i].models[+inp.dataset.m];
            m[inp.dataset.mk] = inp.value.trim();
          };
        });
        card.querySelectorAll("[data-mdel]").forEach((b) => {
          b.onclick = () => { provs[i].models.splice(+b.dataset.mdel, 1); renderProvs(); };
        });
        if (card.querySelector('[data-a="addm"]')) {
          card.querySelector('[data-a="addm"]').onclick = () => {
            provs[i].models = provs[i].models || [];
            provs[i].models.push({ id: "" });
            renderProvs();
          };
        }
        const chips = (models) => {
          const box = card.querySelector("[data-mchips]");
          if (!box) return;
          const have = new Set([provs[i].model, ...(provs[i].models || []).map((m) => m.id)]);
          const left = models.filter((m) => !have.has(m));
          box.replaceChildren(...(left.length
            ? [h("span", { class: "muted" }, "點一下加入："),
              left.map((m) => h("button", {
                class: "sm ghost", "data-addm": m,
                onclick: () => { provs[i].models = provs[i].models || []; provs[i].models.push({ id: m }); renderProvs(); },
              }, "＋ " + m))]
            : []));
        };
        if (provs[i]._fetched) chips(provs[i]._fetched);
        card.querySelectorAll("[data-r]").forEach((sel) => {
          sel.onchange = () => {
            provs[i].reasoning = Object.assign({}, provs[i].reasoning || {}, { [sel.dataset.r]: sel.value });
          };
        });
        card.querySelector('[data-a="calib"]').onclick = async () => {
          const msg = card.querySelector("[data-msg]");
          msg.textContent = "校正中……";
          try {
            await saveProvs();
            const rr = await FE.api("/api/providers/" + enc(provs[i].id) + "/calibrate", { method: "POST", signal });
            provs[i].cjk_token_ratio = rr.ratio;
            card.querySelector('[data-k="cjk_token_ratio"]').value = rr.ratio;
            await saveProvs();
            msg.replaceChildren(h("span", { class: "badge b-ok" }, "已校正"), " 每個中文字約 " + rr.ratio + " token，已儲存");
          } catch (e) {
            msg.replaceChildren(h("span", { class: "badge b-bad" }, "無法校正"), " " + (e.message || String(e)));
          }
        };
        card.querySelector('[data-a="del"]').onclick = async () => {
          if (await FE.confirm("刪除這個服務設定？")) { provs.splice(i, 1); renderProvs(); }
        };
        card.querySelector('[data-a="test"]').onclick = async () => {
          const msg = card.querySelector("[data-msg]");
          msg.textContent = "連線中……";
          try {
            await saveProvs();
            const rr = await FE.api("/api/providers/" + enc(provs[i].id) + "/models", { method: "POST", signal });
            card.querySelector("#ml-" + i).replaceChildren(...rr.models.map((m) => h("option", { value: m })));
            msg.replaceChildren(h("span", { class: "badge b-ok" }, "連線成功"), " 可用模型：" + (rr.models.map((m) => m).join("、") || "（伺服器沒有列出）"));
            provs[i]._fetched = rr.models;
            chips(rr.models);
            if (!provs[i].model && rr.models.length === 1) {
              provs[i].model = rr.models[0];
              card.querySelector('[data-k="model"]').value = rr.models[0];
            }
          } catch (e) {
            msg.replaceChildren(h("span", { class: "badge b-bad" }, "失敗"), " " + (e.message || String(e)));
          }
        };
      });
    }

    function renderKeyStore() {
      if (r.key_store) {
        if (r.secrets_pending) {
          const migrateBtn = h("button", { class: "sm primary", id: "key-mig" }, "搬進" + r.key_store);
          migrateBtn.onclick = async () => {
            try {
              const m = await FE.api("/api/secrets/migrate", { method: "POST", signal });
              Object.assign(r, m);
              S.keyStatus = m.key_status;
              FE.toast(m.left ? "搬了 " + m.moved + " 個，還有 " + m.left + " 個沒搬成功" : "已搬進" + m.key_store + "，secrets.json 已刪除", m.left ? "err" : undefined);
              renderKeyStore();
              renderProvs();
            } catch (e) { FE.fail(e); }
          };
          keyStoreBox.replaceChildren(h("div", { class: "alert warn" },
            h("span", { class: "k" }, "金鑰"),
            h("span", { class: "t" },
              "secrets.json 裡還有 " + r.secrets_pending + " 個 API 金鑰。搬進" + r.key_store + "後，由系統加密並綁定你的登入帳號，專案資料夾裡就不會留金鑰檔。"),
            migrateBtn));
        } else {
          keyStoreBox.replaceChildren(h("div", { class: "muted small" },
            "新輸入的 API 金鑰會存進" + r.key_store + "（由系統加密，綁定你的登入帳號），不放在專案資料夾。"));
        }
      } else {
        keyStoreBox.replaceChildren(h("div", { class: "muted small" },
          "這台電腦沒有可用的系統金鑰庫，API 金鑰存在工作台資料夾的 secrets.json（不會進 git）。"));
      }
    }

    const saveProvs = async () => {
      const rr = await FE.api("/api/providers", { method: "POST", body: { providers: provs, keys }, signal });
      S.config = rr.config;
      S.keyStatus = rr.key_status;
      Object.keys(keys).forEach((k) => delete keys[k]);
      Panel.renderProv();
      return rr;
    };

    renderProvs();
    renderKeyStore();

    provAddBtn.onclick = () => {
      let n = 1;
      while (provs.find((p) => p.id === "custom" + n)) n++;
      provs.push({
        id: "custom" + n, type: "openai", name: "自訂服務 " + n, base_url: "", model: "", key_env: "",
        context_tokens: 32768, max_output: 4096, temperature: 0.8, json_mode: true, price_in: 0, price_out: 0, extra: {},
      });
      renderProvs();
    };

    restartBtn.onclick = async () => {
      const newPort = parseInt(portInput.value, 10);
      if (newPort && newPort !== r.port) {
        try { await FE.api("/api/config", { method: "POST", body: { port: newPort }, signal }); }
        catch (e) { return FE.fail(e); }
      }
      restartServer();
    };

    saveBtn.onclick = async () => {
      try {
        await saveProvs();
        const r2 = await FE.api("/api/config", {
          method: "POST",
          signal,
          body: {
            default_provider: defProvSel.value,
            library: libInput.value.trim(), claude_cmd: cmdInput.value.trim(), model: modelInput.value.trim(),
            permission_mode: permSel.value,
            allowed_tools: toolsArea.value.split(String.fromCharCode(10)).map((s) => s.trim()).filter(Boolean),
            add_dirs: dirsArea.value.split(String.fromCharCode(10)).map((s) => s.trim()).filter(Boolean),
            reconcile_before_write: reconBox.checked, goal_check_after_write: goalBox.checked,
            pipeline_severities: Array.from(document.querySelectorAll("#c-psev input:checked")).map((x) => x.value),
            pipeline_mode: document.querySelector('input[name="c-pmode"]:checked').value,
            pipeline_style_check: pscheckBox.checked,
            autopilot_every: parseInt(apeInput.value, 10) || 0,
            autopilot_stop_must: parseInt(apsmInput.value, 10) || 1,
            autopilot_stop_style: parseFloat(apssInput.value) || 2.4,
            pipeline_providers: Object.fromEntries(Array.from(document.querySelectorAll("#c-pprov select")).map((x) => [x.dataset.step, x.value])),
            stale_foreshadow: parseInt(sfInput.value, 10) || 10, stale_character: parseInt(scInput.value, 10) || 15, create_library: true,
            port: parseInt(portInput.value, 10) || r.port,
          },
        });
        S.config = r2.config;
        S.claudeFound = r2.claude_found;
        S.keyStatus = r2.key_status;
        S.books = (await FE.api("/api/books", { signal })).books;
        Panel.renderProv();
        Panel.renderActions();
        FE.toast("已儲存");
        await FE.route();
      } catch (e) { FE.fail(e); }
    };
  }

  nsPage("settings", "settings", { clearBook: true }, render);
})();
