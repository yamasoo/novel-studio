/* fekit graph.js — 關係圖（Cytoscape.js 包裝）。介面與合約見 docs/02_API合約.md 第 9.4 節。
 * 資料用簡單物件描述；顏色與字型取自 tokens.css，換淺色／深色時自動更新。
 * 只加上 FE.graph；載入本身不動 DOM。 */
(function () {
  "use strict";

  const FE = window.FE;
  if (!FE) {
    console.error("fekit：graph.js 要在 core.js 之後載入");
    return;
  }
  if (FE.graph) {
    console.warn("fekit：graph.js 被載入了兩次，第二次已略過");
    return;
  }

  const SELF_URL = (document.currentScript && document.currentScript.src) || "";
  const LAYOUTS = new Set(["cose", "grid", "circle", "concentric", "breadthfirst", "random", "preset"]);

  /* ──────────────── 載入 Cytoscape ──────────────── */

  let loading = null;

  function scriptUrl(path) {
    if (SELF_URL) return new URL(path, SELF_URL).href;
    const mine = Array.from(document.scripts).find((node) => /\/graph\.js(\?|$)/.test(node.src));
    return new URL(path, mine ? mine.src : document.baseURI).href;
  }

  function load(options = {}) {
    if (window.cytoscape) return Promise.resolve();
    if (loading) return loading;
    const src = options.src || scriptUrl("../vendor/cytoscape/cytoscape.min.js");
    loading = new Promise((done, fail) => {
      const node = document.createElement("script");
      node.src = src;
      node.onload = () => (window.cytoscape ? done() : fail(new Error("FE.graph：Cytoscape 載入後找不到 window.cytoscape")));
      node.onerror = () => {
        loading = null;
        fail(new Error(`FE.graph：載入 Cytoscape 失敗（${src}）`));
      };
      document.head.append(node);
    });
    return loading;
  }

  /* ──────────────── 主題 ──────────────── */

  function tokens() {
    const css = getComputedStyle(document.documentElement);
    const get = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
    return {
      fg: get("--fg", "#2b2620"),
      muted: get("--fg-muted", "#6e655a"),
      line: get("--line", "#ddd4c4"),
      strong: get("--line-strong", "#c4b8a3"),
      surface: get("--bg-elev", "#fffdf8"),
      accent: get("--accent", "#8a3b2e"),
      soft: get("--accent-soft", "#f1dfd9"),
      font: canvasFont(get("--font-sans", "sans-serif")),
    };
  }

  // Cytoscape 的 font-family 只收英數、連字號與空白，中文字型名（「微軟正黑體」）會被判定為無效。
  // 拿掉這些之後，中日韓文字由瀏覽器自動找有字的字型補上。
  function canvasFont(list) {
    const names = list.split(",").map((name) => name.trim().replace(/^["']|["']$/g, "")).filter((name) => /^[\w\- ]+$/.test(name));
    if (!names.includes("sans-serif")) names.push("sans-serif");
    return names.join(", ");
  }

  // 節點寬高：Cytoscape 已不建議用 width: label，改成自己量好文字再給數字。
  const FONT_PX = 13;
  const WRAP_PX = 140;
  const measurer = document.createElement("canvas").getContext("2d");

  function sizeOf(label, font) {
    measurer.font = `${FONT_PX}px ${font}`;
    const lines = String(label).split("\n");
    let widest = 0;
    let rows = 0;
    for (const line of lines) {
      const width = measurer.measureText(line).width;
      widest = Math.max(widest, Math.min(width, WRAP_PX));
      rows += Math.max(1, Math.ceil(width / WRAP_PX));
    }
    return { w: Math.ceil(widest) + 22, h: rows * Math.ceil(FONT_PX * 1.4) + 14 };
  }

  function stylesheet(c) {
    return [
      { selector: "node", style: {
        "label": "data(label)", "shape": "round-rectangle", "width": "data(w)", "height": "data(hgt)",
        "text-valign": "center", "text-halign": "center", "text-wrap": "wrap", "text-max-width": "140px",
        "font-family": c.font, "font-size": FONT_PX, "color": c.fg,
        "background-color": c.surface, "border-width": 1.5, "border-color": c.strong,
      } },
      // 方框（可以裝別的節點）：半透明底、標題在左上
      { selector: "node:parent, node[?box]", style: {
        "background-color": c.accent, "background-opacity": 0.09, "border-color": c.accent, "border-width": 1.5,
        "border-style": "dashed", "text-valign": "top", "text-halign": "center", "color": c.muted,
        "padding": "16px", "font-size": 12,
      } },
      { selector: "edge", style: {
        "curve-style": "bezier", "width": 1.5, "line-color": c.strong,
        "target-arrow-shape": "triangle", "target-arrow-color": c.strong, "arrow-scale": 1,
        "label": "data(label)", "font-family": c.font, "font-size": 11, "color": c.muted,
        "text-background-color": c.surface, "text-background-opacity": 0.9, "text-background-padding": "2px",
        "text-rotation": "autorotate",
      } },
      { selector: "edge[!directed]", style: { "target-arrow-shape": "none" } },
      { selector: "edge[?dashed]", style: { "line-style": "dashed" } },
      { selector: ".faded", style: { "opacity": 0.22 } },
      { selector: "node.sel", style: { "border-color": c.accent, "border-width": 3, "background-color": c.soft } },
      { selector: "edge.sel", style: { "line-color": c.accent, "target-arrow-color": c.accent, "width": 2.5, "color": c.fg } },
      { selector: ".hidden", style: { "display": "none" } },
    ];
  }

  /* ──────────────── 掛載 ──────────────── */

  function toElements(data, fontFamily) {
    const nodes = Array.isArray(data.nodes) ? data.nodes : [];
    const edges = Array.isArray(data.edges) ? data.edges : [];
    const ids = new Set(nodes.map((node) => String(node.id)));
    const elements = [];

    for (const node of nodes) {
      if (node.id === undefined || node.id === null || node.id === "") {
        console.warn("fekit：FE.graph 的 node 缺少 id，已略過", node);
        continue;
      }
      const id = String(node.id);
      const label = node.label === undefined ? id : String(node.label);
      const size = sizeOf(label, fontFamily);
      const entry = {
        group: "nodes",
        data: { id, label, w: size.w, hgt: size.h, box: !!node.box, kind: node.kind || "", userdata: node.data },
        classes: node.kind ? `kind-${node.kind}` : "",
      };
      if (node.group !== undefined && node.group !== null && node.group !== "") {
        if (ids.has(String(node.group)) && String(node.group) !== id) entry.data.parent = String(node.group);
        else console.warn(`fekit：FE.graph 的 node ${id} 的 group「${node.group}」不存在，已忽略`);
      }
      if (typeof node.x === "number" && typeof node.y === "number") entry.position = { x: node.x, y: node.y };
      elements.push(entry);
    }

    edges.forEach((edge, index) => {
      const source = String(edge.source);
      const target = String(edge.target);
      if (!ids.has(source) || !ids.has(target)) {
        console.warn(`fekit：FE.graph 的連線 ${source} → ${target} 有端點不存在，已略過`);
        return;
      }
      elements.push({
        group: "edges",
        data: {
          id: edge.id !== undefined && edge.id !== null ? String(edge.id) : `e${index}_${source}_${target}`,
          source, target,
          label: edge.label === undefined ? "" : String(edge.label),
          directed: edge.directed !== false, dashed: !!edge.dashed, userdata: edge.data,
        },
      });
    });
    return elements;
  }

  function toItem(ele) {
    return { type: ele.isNode() ? "node" : "edge", id: ele.id(), data: ele.data("userdata") };
  }

  function mount(el, options = {}) {
    if (!window.cytoscape) throw new Error("FE.graph：還沒載入 Cytoscape，請先 await FE.graph.load()");
    const target = typeof el === "string" ? document.querySelector(el) : el;
    if (!target) throw new Error("FE.graph.mount()：找不到容器");

    const defaultLayout = LAYOUTS.has(options.layout) ? options.layout : "cose";
    const heightOpt = options.height === undefined ? "24rem" : options.height;
    target.classList.add("graph");
    if (heightOpt !== null) target.style.height = typeof heightOpt === "number" ? `${heightOpt}px` : heightOpt;
    target.setAttribute("role", "img");
    target.setAttribute("aria-label", options.label || "關係圖");

    const cy = window.cytoscape({
      container: target,
      elements: toElements(options, tokens().font),
      style: stylesheet(tokens()),
      layout: { name: "preset" },
      minZoom: 0.2,
      maxZoom: 3,
    });

    let destroyed = false;

    // 容器還沒放進頁面（或大小為 0）時，Cytoscape 的 cose 會出錯。先記下來，等容器有大小再排。
    let waiting = null;
    const sized = () => target.isConnected && target.clientWidth > 0 && target.clientHeight > 0;

    function runLayout(name, animate) {
      if (destroyed) return;
      if (!sized()) {
        waiting = { name, animate };
        return;
      }
      waiting = null;
      const layoutName = LAYOUTS.has(name) ? name : defaultLayout;
      const config = { name: layoutName, fit: true, padding: 28, animate: !!animate, nodeDimensionsIncludeLabels: true };
      if (layoutName === "cose") Object.assign(config, { idealEdgeLength: 110, nodeRepulsion: 40000, nestingFactor: 1.4, gravity: 0.6, numIter: 2000, randomize: true });
      cy.layout(config).run();
    }

    function clearSelection() {
      cy.elements().removeClass("sel faded");
    }

    function select(id) {
      clearSelection();
      if (id === null || id === undefined) return;
      const ele = cy.getElementById(String(id));
      if (!ele || ele.empty()) return;
      // 選到的元素與它相關的標亮，其餘淡化。
      const near = ele.isNode() ? ele.closedNeighborhood().union(ele.ancestors()).union(ele.descendants()) : ele.union(ele.connectedNodes());
      cy.elements().not(near).addClass("faded");
      ele.addClass("sel");
    }

    cy.on("tap", (event) => {
      if (event.target === cy) {
        clearSelection();
        if (options.on_select) options.on_select(null);
        return;
      }
      select(event.target.id());
      if (options.on_select) options.on_select(toItem(event.target));
    });

    function update(data, opts = {}) {
      const before = new Map();
      cy.nodes().forEach((node) => before.set(node.id(), node.position()));
      cy.batch(() => {
        cy.elements().remove();
        cy.add(toElements(data, tokens().font));
      });
      if (opts.layout === false) {
        // 保留舊位置；新節點先放在目前畫面的中央附近。
        const center = cy.extent();
        const cx = (center.x1 + center.x2) / 2;
        const cy0 = (center.y1 + center.y2) / 2;
        let added = 0;
        cy.nodes().forEach((node) => {
          if (before.has(node.id())) {
            node.position(before.get(node.id()));
          } else {
            node.position({ x: cx + (added % 5) * 24, y: cy0 + Math.floor(added / 5) * 24 });
            added += 1;
          }
        });
      } else {
        runLayout(typeof opts.layout === "string" ? opts.layout : undefined, false);
      }
    }

    function hide(predicate) {
      cy.batch(() => {
        cy.elements().removeClass("hidden");
        if (typeof predicate !== "function") return;
        cy.elements().forEach((ele) => {
          if (predicate(toItem(ele))) ele.addClass("hidden");
        });
      });
    }

    // 主題切換（手動 data-theme 或系統深淺色）時重新套用顏色。
    const restyle = () => {
      if (!destroyed) cy.style(stylesheet(tokens()));
    };
    const themeObserver = new MutationObserver(restyle);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", restyle);

    // 容器大小改變（外殼拖曳調寬、收合）時，Cytoscape 要重新量尺寸。
    const resizer = new ResizeObserver(() => {
      if (destroyed) return;
      cy.resize();
      if (waiting && sized()) runLayout(waiting.name, waiting.animate);
    });
    resizer.observe(target);

    runLayout(defaultLayout, false);

    return {
      cy,
      update,
      select,
      hide,
      fit: () => cy.fit(undefined, 28),
      relayout: (name) => runLayout(name, false),
      destroy() {
        if (destroyed) return;
        destroyed = true;
        themeObserver.disconnect();
        media.removeEventListener("change", restyle);
        resizer.disconnect();
        cy.destroy();
        target.classList.remove("graph");
        target.removeAttribute("role");
        target.removeAttribute("aria-label");
      },
    };
  }

  FE.graph = { load, mount };
})();
