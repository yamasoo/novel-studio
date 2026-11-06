/* 插圖頁與插圖區塊（轉移計畫 §8.2.17）：從 app.js 搬 viewIllust（原 948-993）＋ renderIllust（629-901）
   ＋ imageModal（609-626）＋ pickStyles（569-607）＋ imgUrl（547）。
   對外維持 window.renderIllust：page_chapter.js（章節插圖分頁）與 page_bible.js（角色視覺卡下方）都呼叫它。
   留在 app.js 的（有別頁呼叫端，搬了會壞）：illCfg／illProvOptions／tagAppend／waitJob／renderCard（設定頁的視覺卡與 renderCard 在用）、
   loraRowsHtml／bindLoraRows／COMFY_KINDS（只有 renderIllSettings 在用，而 renderIllSettings 由設定頁呼叫）、
   ILL（illCfg 與 renderIllSettings 的狀態）、pickPath／attachPicker。
   全部改成 h() 節點；圖片預覽用 h("img",{src,alt})；imageModal／pickStyles 改 FE.modal；任務照舊 Panel.attach(job)；
   重新載入用 FE.route()。 */
(function () {
  "use strict";

  const { h } = FE;
  const enc = encodeURIComponent;
  const imgUrl = (path) => B("/illust/image?path=" + enc(path));

  async function pickStyles(selected, onDone) {
    let data;
    try { data = await FE.api("/api/illust/styles"); } catch (e) { return FE.fail(e); }
    if (data.missing) return FE.toast("找不到畫風樣式表：到「設定 → 插畫」選一個 .xlsx 或 .json", "err");
    let sel = [...(selected || [])], cat = "", q = "";
    const tops = [...new Set(data.categories.map(([c]) => c.split(" > ")[0]))];
    const catsBox = h("div", { class: "ps-cats", id: "ps-cats" });
    const listBox = h("div", { class: "ps-list", id: "ps-list" });
    const selBox = h("span", { id: "ps-sel" });
    const qInput = h("input", { type: "text", id: "ps-q", placeholder: "搜尋名稱、中文名、提示詞", style: "flex:1" });
    const nsfwBox = h("input", { type: "checkbox", id: "ps-nsfw" });

    const renderSel = () => { selBox.textContent = sel.length ? sel.join("　＋　") : "（不套用）"; };
    const renderCats = () => {
      catsBox.replaceChildren(...[["", "全部"], ...tops.map((x) => [x, x])].map(([v, l]) => h("div", {
        class: "ps-cat" + (v === cat ? " on" : ""), "data-c": v,
        onclick: () => { cat = v; renderCats(); renderList(); },
      }, l)));
    };
    const renderList = () => {
      const ql = q.toLowerCase();
      const rows = data.styles.filter((s) => (!cat || s.categories.some((c) => c === cat || c.startsWith(cat + " >")))
        && (!ql || (s.name + s.zh + s.prompt + s.natural).toLowerCase().includes(ql))).slice(0, 300);
      listBox.replaceChildren(...(rows.length ? rows.map((s) => h("label", { class: "ps-item" },
        h("input", {
          type: "checkbox", "data-n": s.name, checked: sel.includes(s.name),
          onchange: (ev) => {
            sel = ev.target.checked ? [...sel, s.name] : sel.filter((x) => x !== s.name);
            renderSel();
          },
        }),
        h("span", {},
          h("b", {}, s.zh || s.name), " ", h("span", { class: "muted small" }, s.name),
          h("br"),
          h("span", { class: "muted small" }, s.prompt || s.natural)))) : [h("div", { class: "muted small" }, "沒有符合的畫風。")]));
    };

    const close = FE.modal({
      title: "選畫風",
      body: [
        h("div", { class: "row", style: "margin-bottom:8px" }, qInput,
          h("label", { class: "cb", style: "margin:0" }, nsfwBox, " 顯示 nsfw 分類")),
        h("div", { class: "ps-wrap" }, catsBox, listBox),
        h("div", { class: "small muted", style: "margin-top:8px" }, "已選（依順序套用）：", selBox),
      ],
      foot: (done) => [
        h("button", { class: "btn", type: "button", id: "ps-clear", onclick: () => { sel = []; renderSel(); renderList(); } }, "全部取消"),
        h("span", { class: "grow" }),
        h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
        h("button", { class: "btn btn-primary", type: "button", id: "ps-ok", onclick: () => { done(true); onDone(sel); } }, "確定"),
      ],
    });
    qInput.oninput = (e) => { q = e.target.value; renderList(); };
    nsfwBox.onchange = async (e) => {
      const nsfw = e.target.checked;
      try { data = await FE.api("/api/illust/styles?nsfw=" + nsfw); } catch (er) { return FE.fail(er); }
      tops.splice(0, tops.length, ...new Set(data.categories.map(([c]) => c.split(" > ")[0])));
      renderCats(); renderList();
    };
    renderCats(); renderList(); renderSel();
    return close;
  }

  function imageModal(target, img, reload, reuse) {
    const origin = img.origin === "upload" ? "上傳"
      : img.origin === "comfy" ? "ComfyUI" + (img.comfy_profile ? "・" + img.comfy_profile : "") : "Forge";
    const mainBtn = img.main
      ? h("span", { class: "badge b-ok" }, "主圖")
      : h("button", { class: "sm primary", id: "iv-main" }, "設為主圖");
    const copyBtn = img.prompt ? h("button", { class: "sm", id: "iv-copy" }, "複製提示詞") : null;
    const reuseBtn = img.prompt ? h("button", { class: "sm", id: "iv-reuse" }, "用這組提示詞再出圖") : null;
    const delBtn = h("button", { class: "sm danger", id: "iv-del" }, "刪除");
    const close = FE.modal({
      title: "插圖",
      body: [
        h("div", { class: "img-view" }, h("img", { src: imgUrl(img.path), alt: "" })),
        h("div", { class: "row small muted", style: "margin:8px 0" },
          img.file + "　" + (img.width ? img.width + "×" + img.height : "") + "　" + (img.seed ? "seed " + img.seed : "") + "　" + origin),
        img.prompt
          ? h("details", {},
            h("summary", { class: "small" }, "提示詞"),
            h("pre", { class: "pre" }, img.prompt),
            img.negative ? h("pre", { class: "pre muted" }, "負面：" + img.negative) : null)
          : null,
      ],
      foot: (done) => [
        h("div", { class: "row", style: "margin-right:auto" },
          mainBtn, copyBtn, reuseBtn,
          h("a", { class: "btn sm", href: imgUrl(img.path), download: img.file }, "下載")),
        h("button", { class: "btn btn-danger", type: "button", id: "iv-del2", onclick: () => done(false) }, "關閉"),
      ],
    });
    // 刪除鈕放在 body 的最後一列（與舊版一致）
    close.el.querySelector(".modal-body").append(h("div", { class: "row", style: "margin-top:10px" }, delBtn));
    if (!img.main) {
      mainBtn.onclick = async () => {
        try {
          await FE.api(B("/illust/main"), { method: "POST", body: { target, file: img.file } });
          close();
          reload();
        } catch (e) { FE.fail(e); }
      };
    }
    if (copyBtn) copyBtn.onclick = () => { navigator.clipboard.writeText(img.prompt).then(() => FE.toast("已複製")); };
    if (reuseBtn) reuseBtn.onclick = () => { close(); reuse(img); };
    delBtn.onclick = async () => {
      if (!(await FE.confirm("刪除這張圖？（會移到 .studio/備份/插圖）"))) return;
      try {
        await FE.api(B("/illust/delete"), { method: "POST", body: { target, file: img.file } });
        close();
        reload();
      } catch (e) { FE.fail(e); }
    };
  }

  // 插圖區塊：target = cover | chapter:N | entity:設定/角色/X.md
  async function renderIllust(el, target, opts = {}) {
    const cfgR = await illCfg();
    let info;
    try { info = await FE.api(B("/illust?target=" + enc(target))); }
    catch (e) { el.replaceChildren(h("div", { class: "card muted" }, (e && e.message) || String(e))); return; }
    const cfg = cfgR.config;
    const bs = info.style || {};
    const isCh = target.startsWith("chapter:"), isEnt = target.startsWith("entity:"), isCover = target === "cover";
    const D = Object.assign({
      passage: "", chars: [], places: [], action_tags: "", scene_tags: "", composition: "", sentences: "",
      extra: "", format: cfg.format, styles: bs.styles || [], artist: bs.artist || "", seed: -1, count: 1,
    }, info.draft || {});
    const isComfy = cfg.backend === "comfy";
    const profs = cfg.comfy_profiles || [];
    if (!profs.find((p) => p.id === D.profile)) D.profile = cfg.comfy_profile || (profs[0] || {}).id;
    const curProf = () => profs.find((p) => p.id === D.profile) || profs[0] || {};
    const genName = () => (isComfy ? "ComfyUI" : "Forge");
    if (!info.draft || !info.draft.styles) D.styles = bs.styles || [];
    if (!info.draft || info.draft.artist === undefined) D.artist = bs.artist || "";
    let ents = null, picks = null, zh = null, final = null;
    let open = opts.open || (isCh && !info.images.length);
    const sizeW = D.width || (isCover ? bs.cover_width : bs.width) || cfg.width;
    const sizeH = D.height || (isCover ? bs.cover_height : bs.height) || cfg.height;
    D.width = sizeW; D.height = sizeH;
    const reload = () => renderIllust(el, target, Object.assign({}, opts, { open }));
    if (!Array.isArray(D.texts)) D.texts = [];
    const bookName = () => ((S.books || []).find((b) => b.id === S.book) || {}).name || "";
    const TX_KIND = [["title", "標題"], ["sign", "招牌、標語"], ["bubble", "對白氣泡"], ["caption", "說明文字"], ["other", "其他"]];
    const TX_POS = [["tl", "左上"], ["t", "上方"], ["tr", "右上"], ["l", "左側"], ["c", "中央"], ["r", "右側"], ["bl", "左下"], ["b", "下方"], ["br", "右下"]];
    const TX_SIZE = [["l", "大"], ["m", "中"], ["s", "小"]];
    const TX_FONT = [["", "字體不指定"], ["brush", "書法"], ["bold", "粗黑體"], ["serif", "襯線印刷體"], ["hand", "手寫"], ["pixel", "像素字"]];
    const txSel = (i, f, list, v) => h("select", { "data-tx": String(i), "data-tf": f },
      list.map(([k, l]) => h("option", { value: k, selected: (v || "") === k }, l)));

    const textSection = () => [
      h("h3", {}, "圖中文字"),
      h("div", { class: "muted small", style: "margin-bottom:6px" },
        "MOSS-Image 會照引號裡的字畫出來，中文、英文都可以（英文最穩）。要換行就在文字裡打 " + String.fromCharCode(92) + "n。最多 6 條；沒有加就不放文字。"),
      isCover
        ? h("label", {
          class: "chip" + (D.texts.some((x) => x.book) ? " on" : ""), style: "margin-bottom:6px",
        }, h("input", {
          type: "checkbox", id: "il-booktitle", checked: D.texts.some((x) => x.book),
        }), "放書名")
        : null,
      D.texts.length
        ? h("table", { class: "ill-chars" }, D.texts.map((x, i) => h("tr", {},
          h("td", {}, h("input", { type: "text", "data-tx": String(i), "data-tf": "text", value: x.text || "", placeholder: "要出現在圖上的字" })),
          h("td", {}, txSel(i, "kind", TX_KIND, x.kind || "title")),
          h("td", {}, txSel(i, "pos", TX_POS, x.pos || "t")),
          h("td", {}, txSel(i, "size", TX_SIZE, x.size || "l")),
          h("td", {}, txSel(i, "font", TX_FONT, x.font || "")),
          h("td", {}, h("input", { type: "text", "data-tx": String(i), "data-tf": "color", value: x.color || "", placeholder: "顏色（英文，例如 gold）", style: "width:9em" })),
          h("td", {}, h("button", { class: "sm", "data-txdel": String(i), title: "刪除" }, "✕")))))
        : null,
      D.texts.length < 6
        ? h("div", { class: "row", style: "margin:6px 0 10px" }, h("button", { class: "sm", id: "il-txadd" }, "＋ 加一條文字"))
        : null,
    ];

    const gallery = () => (info.images.length
      ? h("div", { class: "ill-gallery" }, info.images.map((im, i) => h("div", {
        class: "ill-thumb" + (im.main ? " main" : ""), "data-i": String(i),
      },
        h("img", { loading: "lazy", src: imgUrl(im.path), alt: "" }),
        im.main ? h("span", { class: "badge b-ok" }, "主圖") : null)))
      : h("div", { class: "muted small" },
        "還沒有插圖。" + (isCh ? "可以挑一段來畫，或直接上傳。" : "可以產生提示詞送 Forge，或直接上傳。")));

    const charRows = () => {
      if (!ents) return h("div", { class: "muted small" }, "載入中……");
      const pool = ents.all.filter((e) => e.kind === "角色");
      const places = ents.all.filter((e) => e.kind !== "角色");
      const onChars = D.chars.map((c) => c.name), onPlaces = (D.places || []).map((p) => p.name);
      const card = (name) => (ents.cards[name] || {});
      return [
        h("div", { class: "ill-chips" }, pool.length
          ? pool.map((e) => h("label", { class: "chip" + (onChars.includes(e.name) ? " on" : ""), title: card(e.name).tags || "沒有視覺卡" },
            h("input", { type: "checkbox", "data-ch": e.name, checked: onChars.includes(e.name) }),
            e.name,
            e.has_card ? null : h("span", { class: "warn-dot", title: "沒有視覺卡" }, "!")))
          : h("span", { class: "muted small" }, "這本書還沒有角色設定檔。")),
        D.chars.length
          ? h("table", { class: "ill-chars" }, D.chars.map((c, i) => h("tr", {},
            h("td", { class: "nm" }, c.name),
            h("td", {}, h("select", { "data-pos": String(i) },
              [["", "自動"], ["left", "左"], ["right", "右"], ["center", "中"], ["back", "後方"]]
                .map(([v, l]) => h("option", { value: v, selected: (c.position || "") === v }, l)))),
            h("td", {}, h("input", { type: "text", "data-act": String(i), value: c.action || "", placeholder: "這張圖裡的動作、表情（英文標籤）" })),
            h("td", { class: "small muted" }, c.tags
              ? (c.tags.length > 60 ? c.tags.slice(0, 60) : c.tags)
              : h("a", { href: "#/b/" + enc(S.book) + "/bible?t=" + enc("角色") + "&f=" + enc(c.file || "") }, "先建立視覺卡")))))
          : null,
        places.length
          ? [h("div", { class: "small muted", style: "margin:8px 0 4px" }, "地點、物件（有視覺卡的會帶入場景）"),
            h("div", { class: "ill-chips" }, places.map((e) => h("label", { class: "chip" + (onPlaces.includes(e.name) ? " on" : "") },
              h("input", { type: "checkbox", "data-pl": e.name, checked: onPlaces.includes(e.name) }),
              e.name,
              e.has_card ? null : h("span", { class: "warn-dot", title: "沒有視覺卡" }, "!"))))]
          : null,
      ];
    };

    const render = () => {
      el.replaceChildren(h("div", { class: "card ill-card" },
        h("div", { class: "card-title" },
          h("h2", {}, "插圖 ", h("span", { class: "badge" }, String(info.images.length))),
          h("div", { class: "row" },
            h("label", { class: "btn sm" }, "上傳圖片",
              h("input", { type: "file", id: "il-up", accept: "image/png,image/jpeg,image/webp", multiple: true, hidden: true })),
            h("button", { class: "sm" + (open ? "" : " primary"), id: "il-toggle" }, open ? "收起出圖" : "出圖"))),
        gallery(),
        h("div", { id: "il-q", class: "small", style: "margin-top:6px" }),
        open ? h("div", { class: "ill-editor" },
          isCh ? [
            h("h3", {}, "1. 要畫哪一段"),
            h("div", { class: "row" },
              h("button", { class: "sm", id: "il-pick-h" }, "挑精華段落"),
              h("button", { class: "sm", id: "il-pick-a" }, "挑動作最強的段落"),
              h("span", { class: "muted small" }, "程式在本機依動作詞、畫面詞、章綱情節點打分，不用 AI；也可以直接貼上或修改下面的文字。")),
            picks
              ? h("div", { class: "ill-picks" }, picks.map((p, i) => h("div", { class: "ill-pick", "data-p": String(i) },
                h("div", { class: "small muted" }, "分數 " + p.score + "　" + p.reasons),
                p.text.length > 160 ? p.text.slice(0, 160) + "……" : p.text)))
              : null,
            h("textarea", { id: "il-passage", rows: "4", placeholder: "要畫的片段" }, D.passage),
          ] : null,
          h("h3", {}, (isCh ? "2. " : "") + "出場角色與地點"),
          h("div", { id: "il-chars" }, charRows()),
          h("h3", {}, (isCh ? "3. " : "") + "畫面描述"),
          h("div", { class: "row", style: "margin-bottom:8px" },
            h("select", { id: "il-prov" }, nsShared.nodesFromHtml(illProvOptions(cfgR))),
            h("button", { class: "sm primary", id: "il-ai" }, "AI 產生畫面描述"),
            h("button", { class: "sm", id: "il-zh" }, "本機查標籤"),
            h("span", { class: "muted small" }, "AI 只寫下面幾欄（一小段 JSON）；角色外觀、品質、畫風由程式組裝。")),
          zh
            ? [h("div", { class: "ill-chips", style: "margin-bottom:8px" }, zh.length
              ? zh.map((x) => h("span", { class: "chip add", "data-tag": x.tag, title: x.zh }, x.zh + " → " + x.tag))
              : h("span", { class: "muted small" }, "對照表裡沒有查到。")),
              h("div", { class: "muted small", style: "margin:-4px 0 8px" }, "點一下加進「場景標籤」。對照表是 tagcomplete 附的中文翻譯，有些詞不準，請挑著用。")]
            : null,
          h("div", { class: "grid g2" },
            h("label", { class: "f" }, h("span", {}, "動作、互動標籤"), h("input", { type: "text", "data-k": "action_tags", value: D.action_tags || "" })),
            h("label", { class: "f" }, h("span", {}, "場景標籤（地點、時間、光線）"), h("input", { type: "text", "data-k": "scene_tags", value: D.scene_tags || "" })),
            h("label", { class: "f" }, h("span", {}, "構圖、鏡頭標籤"), h("input", { type: "text", "data-k": "composition", value: D.composition || "", placeholder: "cowboy shot, from side, close-up" })),
            h("label", { class: "f" }, h("span", {}, "額外標籤"), h("input", { type: "text", "data-k": "extra", value: D.extra || "" }))),
          h("label", { class: "f" }, h("span", {}, "英文描述（兩三句）"), h("textarea", { "data-k": "sentences", rows: "3" }, D.sentences || "")),
          h("h3", {}, (isCh ? "4. " : "") + "畫風與出圖"),
          h("div", { class: "grid g2" },
            h("div", { class: "f" }, h("span", {}, "畫風"),
              h("div", { class: "row" },
                h("span", { class: "small" }, D.styles.length ? D.styles.join("　＋　") : h("span", { class: "muted" }, "不套用")),
                h("button", { class: "sm", id: "il-styles" }, "選畫風…"))),
            h("label", { class: "f" }, h("span", {}, "畫師標籤（會自動加 @）"), h("input", { type: "text", "data-k": "artist", value: D.artist || "" })),
            isComfy
              ? h("label", { class: "f" }, h("span", {}, "ComfyUI 出圖設定"),
                h("select", { "data-k": "profile", id: "il-prof" }, profs.map((p) => h("option", {
                  value: p.id, selected: p.id === D.profile,
                }, p.name + (p.upsampler ? "（Upsampler）" : "") + ((p.loras || []).some((x) => x.on !== false && x.name) ? "（LoRA）" : "")))))
              : null,
            (isComfy && curProf().kind === "moss")
              ? h("div", { class: "f" }, h("span", {}, "格式"), h("div", { class: "small muted" }, "MOSS-Image 用英文自然語言，不加品質、分級與畫師標籤"))
              : h("label", { class: "f" }, h("span", {}, "格式"),
                h("select", { "data-k": "format" },
                  [["mixed", "標籤＋自然語言（Anima 建議）"], ["tags", "只有標籤"], ["natural", "自然語言為主"]]
                    .map(([v, l]) => h("option", { value: v, selected: D.format === v }, l)))),
            h("label", { class: "f" }, h("span", {}, "尺寸"),
              h("select", { id: "il-size" },
                cfgR.sizes.map(([n, w, hh]) => h("option", { value: w + "x" + hh, selected: w === +D.width && hh === +D.height }, n + " " + w + "×" + hh)),
                cfgR.sizes.some(([, w, hh]) => w === +D.width && hh === +D.height)
                  ? null
                  : h("option", { value: D.width + "x" + D.height, selected: true }, "目前 " + D.width + "×" + D.height))),
            h("label", { class: "f" }, h("span", {}, "種子（-1＝隨機）"), h("input", { type: "number", "data-k": "seed", value: String(D.seed) })),
            h("label", { class: "f" }, h("span", {}, "張數"),
              h("select", { "data-k": "count" }, [1, 2, 3, 4].map((n) => h("option", { value: String(n), selected: +D.count === n }, String(n)))))),
          (isComfy && curProf().kind === "moss") ? textSection() : null,
          h("div", { class: "row" },
            h("button", { class: "sm", id: "il-asm" }, "組裝提示詞"),
            h("span", { class: "muted small" }, "組裝後可以直接修改最終提示詞，或複製到 " + genName() + " 自己用。")),
          final ? [
            h("label", { class: "f", style: "margin-top:8px" }, h("span", {}, "正向提示詞"), h("textarea", { id: "il-pos", rows: "7" }, final.positive)),
            h("label", { class: "f" }, h("span", {}, "負面提示詞"), h("textarea", { id: "il-neg", rows: "2" }, final.negative)),
            (final.notes && final.notes.length) ? h("div", { class: "small muted" }, "標籤檢查：" + final.notes.join("；")) : null,
            h("div", { class: "row", style: "margin-top:8px" },
              h("button", { class: "sm", id: "il-copy" }, "複製正向提示詞"),
              h("span", { class: "grow" }),
              h("button", { class: "primary", id: "il-gen" }, "送 " + genName() + " 出圖")),
          ] : null)
          : null));
      bind();
    };

    const collect = () => {
      el.querySelectorAll("[data-k]").forEach((i) => { D[i.dataset.k] = i.type === "number" ? parseInt(i.value, 10) : i.value; });
      const ps = el.querySelector("#il-passage");
      if (ps) D.passage = ps.value;
      el.querySelectorAll("[data-act]").forEach((i) => { D.chars[+i.dataset.act].action = i.value; });
      el.querySelectorAll("[data-pos]").forEach((i) => { D.chars[+i.dataset.pos].position = i.value; });
      el.querySelectorAll("[data-tx]").forEach((i) => { if (D.texts[+i.dataset.tx]) D.texts[+i.dataset.tx][i.dataset.tf] = i.value; });
      const sz = el.querySelector("#il-size");
      if (sz) { const [w, hh] = sz.value.split("x").map(Number); D.width = w; D.height = hh; }
    };

    const loadEnts = async () => {
      const text = isCh ? (D.passage || "") : "";
      const r = await FE.api(B("/illust/detect"), { method: "POST", body: { text, target } });
      const cards = {};
      r.entities.forEach((e) => { cards[e.name] = e.card || {}; });
      r.all.forEach((e) => { if (!cards[e.name]) cards[e.name] = null; });
      ents = { all: r.all, cards, found: r.entities };
      const full = {};
      for (const e of r.entities) full[e.name] = e;
      ents.full = full;
      if (!D.chars.length && !info.draft.chars) {
        D.chars = r.entities.filter((e) => e.kind === "角色").slice(0, 3).map((e) => ({ name: e.name, file: e.file, tags: (e.card || {}).tags || "", description: (e.card || {}).description || "", position: "", action: "" }));
        D.places = r.entities.filter((e) => e.kind !== "角色").slice(0, 2).map((e) => ({ name: e.name, file: e.file, tags: (e.card || {}).tags || "", description: (e.card || {}).description || "" }));
      }
    };
    const cardOf = async (name) => {
      if (ents.full[name]) return ents.full[name];
      const e = ents.all.find((x) => x.name === name);
      const r = await FE.api(B("/illust/detect"), { method: "POST", body: { text: name, target } });
      const hit = r.entities.find((x) => x.name === name) || e;
      ents.full[name] = hit;
      return hit;
    };

    const pollQueue = async () => {
      for (;;) {
        let list;
        try { list = await FE.api("/api/illust/queue?book=" + enc(S.book)); } catch (e) { return; }
        const mine = list.filter((x) => x.target === target);
        const active = mine.filter((x) => x.status === "queued" || x.status === "running");
        const q = el.querySelector("#il-q");
        if (!q) return;
        const others = list.filter((x) => x.target !== target && (x.status === "queued" || x.status === "running")).length;
        q.replaceChildren(
          ...active.map((x) => (x.status === "running"
            ? (x.backend === "comfy"
              ? h("div", { class: "ill-prog" },
                h("span", {}, "ComfyUI " + (x.phase === "pending" ? "排隊中" : "出圖中") + "（" + x.profile + "，" + (x.elapsed || 0) + " 秒）"),
                h("div", { class: "bar indet" }, h("i", {})),
                h("button", { class: "sm", "data-cancel": String(x.id) }, "停止"))
              : h("div", { class: "ill-prog" },
                h("span", {}, "Forge 出圖中 " + Math.round(x.progress * 100) + "%" + (x.eta ? "（約 " + Math.ceil(x.eta) + " 秒）" : "")),
                h("div", { class: "bar" }, h("i", { style: "width:" + Math.round(x.progress * 100) + "%" })),
                h("button", { class: "sm", "data-cancel": String(x.id) }, "停止")))
            : h("div", {}, "排隊中（seed " + x.seed + "）", h("button", { class: "sm", "data-cancel": String(x.id) }, "取消")))),
          others ? h("div", { class: "muted" }, "另外還有 " + others + " 張在排隊") : null,
          mine.filter((x) => x.status === "error" && Date.now() / 1000 - x.created < 600).slice(-1)
            .map((x) => h("div", { class: "err" }, "出圖失敗：" + x.error)));
        q.querySelectorAll("[data-cancel]").forEach((b) => {
          b.onclick = () => FE.api("/api/illust/queue/" + b.dataset.cancel + "/cancel", { method: "POST" });
        });
        if (!active.length) {
          const doneNow = mine.some((x) => x.status === "done" && x.files.some((f) => !info.images.find((im) => im.file === f)));
          if (doneNow) {
            info = await FE.api(B("/illust?target=" + enc(target)));
            collect();
            render();
          }
          return;
        }
        await new Promise((r) => setTimeout(r, 1200));
      }
    };

    const bindChars = () => {
      el.querySelectorAll("[data-ch]").forEach((cb) => {
        cb.onchange = async () => {
          collect();
          const name = cb.dataset.ch;
          if (cb.checked) {
            const e = await cardOf(name);
            D.chars.push({ name, file: e.file, tags: (e.card || {}).tags || "", description: (e.card || {}).description || "", position: "", action: "" });
          } else D.chars = D.chars.filter((c) => c.name !== name);
          final = null;
          render();
        };
      });
      el.querySelectorAll("[data-pl]").forEach((cb) => {
        cb.onchange = async () => {
          collect();
          const name = cb.dataset.pl;
          if (cb.checked) {
            const e = await cardOf(name);
            D.places = [...(D.places || []), { name, file: e.file, tags: (e.card || {}).tags || "", description: (e.card || {}).description || "" }];
          } else D.places = (D.places || []).filter((p) => p.name !== name);
          final = null;
          render();
        };
      });
    };

    const bind = () => {
      const q = (sel) => el.querySelector(sel);
      const profSel = q("#il-prof");
      if (profSel) profSel.onchange = () => { collect(); final = null; render(); };
      const txAdd = q("#il-txadd");
      if (txAdd) txAdd.onclick = () => { collect(); D.texts.push({ text: "", kind: "title", pos: "t", size: "l", font: "", color: "" }); final = null; render(); };
      el.querySelectorAll("[data-txdel]").forEach((b) => {
        b.onclick = () => { collect(); D.texts.splice(+b.dataset.txdel, 1); final = null; render(); };
      });
      const bookTitle = q("#il-booktitle");
      if (bookTitle) bookTitle.onchange = (ev) => {
        collect();
        if (ev.target.checked) D.texts.unshift({ text: bookName(), kind: "title", pos: "t", size: "l", font: "", color: "", book: true });
        else D.texts = D.texts.filter((x) => !x.book);
        D.texts = D.texts.slice(0, 6); final = null; render();
      };
      el.querySelectorAll(".ill-thumb").forEach((node) => {
        node.onclick = () => imageModal(target, info.images[+node.dataset.i], reload, (img) => {
          open = true;
          final = { positive: img.prompt, negative: img.negative || "", notes: [] };
          D.seed = img.seed || -1;
          render();
        });
      });
      q("#il-up").onchange = async (ev) => {
        try {
          const files = await readFiles(ev.target);
          await FE.api(B("/illust/upload"), { method: "POST", body: { target, files } });
          FE.toast("已上傳 " + files.length + " 張");
          reload();
        } catch (e) { FE.fail(e); }
      };
      q("#il-toggle").onclick = async () => { collect(); open = !open; if (open && !ents) await loadEnts(); render(); };
      if (!open) return;
      if (!ents) {
        loadEnts().then(() => {
          const c = q("#il-chars");
          if (c) { c.replaceChildren(charRows()); bindChars(); }
        }).catch(FE.fail);
      }
      bindChars();
      const pick = async (mode) => {
        collect();
        try {
          const r = await FE.api(B("/illust/pick"), { method: "POST", body: { chapter: opts.chapter, mode } });
          picks = r.passages;
          render();
        } catch (e) { FE.fail(e); }
      };
      const btnH = q("#il-pick-h"), btnA = q("#il-pick-a");
      if (btnH) btnH.onclick = () => pick("highlight");
      if (btnA) btnA.onclick = () => pick("action");
      el.querySelectorAll(".ill-pick").forEach((d) => {
        d.onclick = async () => {
          collect();
          D.passage = picks[+d.dataset.p].text;
          picks = null;
          D.chars = [];
          info.draft = {};
          await loadEnts();
          render();
        };
      });
      q("#il-zh").onclick = async () => {
        collect();
        const text = isCh ? D.passage : (opts.entityText || "");
        if (!text.trim()) return FE.toast(isCh ? "請先挑一段片段" : "沒有可以查的文字", "err");
        try {
          const r = await FE.api("/api/illust/zh", { method: "POST", body: { text } });
          if (!r.has_dict) return FE.toast("找不到中文對照表：到「設定 → 插畫」填 Forge 資料夾（會自動找 tagcomplete 的對照表）", "err");
          zh = r.tags;
          render();
        } catch (e) { FE.fail(e); }
      };
      el.querySelectorAll(".chip.add").forEach((c) => {
        c.onclick = () => { collect(); D.scene_tags = tagAppend(D.scene_tags, c.dataset.tag); render(); };
      });
      q("#il-styles").onclick = () => { collect(); pickStyles(D.styles, (sel) => { D.styles = sel; render(); }); };
      q("#il-ai").onclick = async () => {
        collect();
        if (isCh && !D.passage.trim()) return FE.toast("請先挑一段要畫的片段", "err");
        const prov = q("#il-prov").value;
        const params = { target, passage: D.passage, chars: D.chars.map((c) => c.name), places: (D.places || []).map((p) => p.name) };
        try {
          await FE.api(B("/illust/draft"), { method: "POST", body: { target, draft: D } });
          const job = await FE.api(B("/jobs"), { method: "POST", body: { action: "illust_prompt", params, provider: prov } });
          Panel.attach(job);
          const btn = q("#il-ai");
          if (btn) { btn.disabled = true; btn.textContent = "AI 產生中……"; }
          const j = await waitJob(job.id);
          if (j.status !== "done") { FE.toast("產生失敗，詳情看右側面板", "err"); render(); return; }
          info = await FE.api(B("/illust?target=" + enc(target)));
          Object.assign(D, info.draft || {});
          final = null;
          render();
        } catch (e) { FE.fail(e); render(); }
      };
      q("#il-asm").onclick = async () => {
        collect();
        try {
          final = await FE.api(B("/illust/assemble"), { method: "POST", body: { draft: D, profile: isComfy ? D.profile : null } });
          await FE.api(B("/illust/draft"), { method: "POST", body: { target, draft: D } });
          render();
        } catch (e) { FE.fail(e); }
      };
      const copyBtn = q("#il-copy");
      if (copyBtn) copyBtn.onclick = () => navigator.clipboard.writeText(q("#il-pos").value).then(() => FE.toast("已複製"));
      const genBtn = q("#il-gen");
      if (genBtn) genBtn.onclick = async () => {
        collect();
        final.positive = q("#il-pos").value;
        final.negative = q("#il-neg").value;
        try {
          await FE.api(B("/illust/generate"), {
            method: "POST",
            body: {
              target, positive: final.positive, negative: final.negative, seed: D.seed, count: +D.count,
              width: D.width, height: D.height, draft: D, profile: isComfy ? D.profile : null,
            },
          });
          FE.toast("已送到 " + genName());
          pollQueue();
        } catch (e) { FE.fail(e); }
      };
    };

    if (open) await loadEnts();
    render();
    pollQueue();
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const t = ctx.query.t || "總覽";
    const tabs = ["總覽", "封面", "本書畫風"];
    const body = h("div", { id: "il-body" });
    const cfgR = await illCfg();
    const alertNode = (!cfgR.config.forge_url || cfgR.sheet_error)
      ? h("div", { class: "alert warn", style: "margin-bottom:10px" }, h("span", { class: "t" }, cfgR.sheet_error || ""))
      : null;

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "插圖"),
          h("div", { class: "sub" }, "每章、每個角色或地點都可以有插圖，全部選用。圖存在書資料夾的 ", h("code", {}, "插圖"), " 裡（預設不進 git）"))),
      tabsNodeOf(t, tabs),
      alertNode,
      body);

    if (t === "封面") return renderIllust(body, "cover", { open: true });
    if (t === "本書畫風") {
      const bs = (await FE.api(B("/illust/overview"), { signal })).style;
      let styles = bs.styles || [];
      const draw = () => {
        const artistInput = h("input", { type: "text", id: "bs-artist", value: bs.artist || "" });
        const extraInput = h("input", { type: "text", id: "bs-extra", value: bs.extra || "" });
        const negInput = h("input", { type: "text", id: "bs-neg", value: bs.negative_extra || "" });
        const sizeSel = h("select", { id: "bs-size" },
          h("option", { value: "" }, "用全域預設（" + cfgR.config.width + "×" + cfgR.config.height + "）"),
          cfgR.sizes.map(([n, w, hh]) => h("option", { value: w + "x" + hh, selected: w === bs.width && hh === bs.height }, n + " " + w + "×" + hh)));
        const csizeSel = h("select", { id: "bs-csize" },
          cfgR.sizes.map(([n, w, hh]) => h("option", { value: w + "x" + hh, selected: w === bs.cover_width && hh === bs.cover_height }, n + " " + w + "×" + hh)));
        const pickBtn = h("button", { class: "sm", id: "bs-st" }, "選畫風…");
        const saveBtn = h("button", { class: "primary", id: "bs-save" }, "儲存");
        const stylesLine = h("span", { class: "row" },
          h("span", {}, styles.length ? styles.join("　＋　") : h("span", { class: "muted" }, "不套用")),
          pickBtn);
        body.replaceChildren(h("div", { class: "card", style: "max-width:820px" },
          h("p", { class: "muted small" }, "這本書所有插圖的預設值；每張圖出圖時還可以再改。品質、分級、負面提示詞的全域預設在「設定 → 插畫」。"),
          h("div", { class: "f" }, h("span", {}, "畫風"), stylesLine),
          h("div", { class: "grid g2" },
            h("label", { class: "f" }, h("span", {}, "畫師標籤（會自動加 @）"), artistInput),
            h("label", { class: "f" }, h("span", {}, "每張都加的標籤"), extraInput),
            h("label", { class: "f" }, h("span", {}, "每張都加的負面提示詞"), negInput),
            h("label", { class: "f" }, h("span", {}, "插圖尺寸"), sizeSel),
            h("label", { class: "f" }, h("span", {}, "封面尺寸"), csizeSel)),
          h("div", { class: "row" }, h("span", { class: "grow" }), saveBtn)));
        pickBtn.onclick = () => pickStyles(styles, (sel) => { styles = sel; draw(); });
        saveBtn.onclick = async () => {
          const [w, hh] = (sizeSel.value || "x").split("x").map((x) => parseInt(x, 10) || null);
          const [cw, chh] = csizeSel.value.split("x").map(Number);
          try {
            await FE.api(B("/illust/style"), {
              method: "POST", signal,
              body: {
                styles, artist: artistInput.value.trim(), extra: extraInput.value.trim(),
                negative_extra: negInput.value.trim(), width: w, height: hh, cover_width: cw, cover_height: chh,
              },
            });
            FE.toast("已儲存");
          } catch (e) { FE.fail(e); }
        };
      };
      return draw();
    }

    const o = await FE.api(B("/illust/overview"), { signal });
    const link = (it) => (it.target === "cover" ? "#/b/" + enc(S.book) + "/illust?t=" + enc("封面")
      : it.target.startsWith("chapter:") ? "#/b/" + enc(S.book) + "/ch/" + it.target.split(":")[1] + "?tab=illust"
        : "#/b/" + enc(S.book) + "/bible?t=" + enc(it.target.split("/")[1]) + "&f=" + enc(it.target.slice(7)));
    body.replaceChildren(o.items.length
      ? h("div", { class: "ill-overview" }, o.items.map((it) => h("a", { class: "ill-ov", href: link(it) },
        h("img", { loading: "lazy", src: imgUrl(it.main), alt: "" }),
        h("div", {}, h("b", {}, it.label), " ", h("span", { class: "muted small" }, it.count + " 張")))))
      : h("div", { class: "card empty" },
        h("div", { class: "big" }, "✎"),
        "還沒有任何插圖。",
        h("br"),
        "到章節頁的「插圖」分頁、設定集的角色，或這裡的「封面」開始。"));
  }

  function tabsNodeOf(t, tabs) {
    return h("div", { class: "tabs" }, tabs.map((x) => h("button", {
      class: "tab" + (x === t ? " active" : ""),
      onclick: () => FE.go("#/b/" + enc(S.book) + "/illust?t=" + enc(x)),
    }, x)));
  }

  window.renderIllust = renderIllust;
  nsPage("b/:book/illust", "illust", { book: true }, render);
})();
