/* グッズ一覧(拡張パック/デッキ/その他)。カテゴリタブで絞り込み。 */
(function () {
  "use strict";

  const CATEGORY_TABS = [
    { key: "all", label: "すべて" },
    { key: "boosters", label: "ブースター" },
    { key: "decks", label: "デッキ" },
    { key: "others", label: "その他" },
  ];

  let allGoods = [];
  let selectedCategory = "all";

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
  }

  function render() {
    const grid = document.getElementById("goods-grid");
    const filtered = selectedCategory === "all"
      ? allGoods
      : allGoods.filter((g) => g.category === selectedCategory);

    document.getElementById("result-count").textContent = `${filtered.length}件`;

    const frag = document.createDocumentFragment();
    for (const item of filtered) {
      const tile = document.createElement("div");
      tile.className = "goods-tile";
      const metaParts = [item.category_label, formatDate(item.release_date), item.price_text, item.tag]
        .filter(Boolean).join(" / ");
      tile.innerHTML = `
        <img src="${item.image_url || ""}" alt="${escapeHtml(item.title)}" loading="lazy">
        <div class="goods-title">${escapeHtml(item.title)}</div>
        <div class="goods-meta">${escapeHtml(metaParts)}</div>
        <div class="goods-links">
          ${item.detail_url ? `<a class="goods-link official" href="${item.detail_url}" target="_blank" rel="noopener">🔎 公式サイトで見る</a>` : ""}
          <a class="goods-link amazon" href="${item.amazon_url}" target="_blank" rel="nofollow noopener sponsored">🔍 Amazon <span class="pr-label">PR</span></a>
          <a class="goods-link rakuten" href="${item.rakuten_url}" target="_blank" rel="nofollow noopener sponsored">🔍 楽天市場 <span class="pr-label">PR</span></a>
        </div>
      `;
      frag.appendChild(tile);
    }
    grid.replaceChildren(frag);
  }

  function buildCategoryTabs() {
    const container = document.getElementById("category-tabs");
    const frag = document.createDocumentFragment();
    for (const { key, label } of CATEGORY_TABS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "site-tab" + (key === selectedCategory ? " active" : "");
      btn.textContent = label;
      btn.addEventListener("click", () => {
        selectedCategory = key;
        container.querySelectorAll(".site-tab").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        render();
      });
      frag.appendChild(btn);
    }
    container.replaceChildren(frag);
  }

  async function init() {
    const [goodsRes] = await Promise.all([
      fetchFresh("data/goods.json"),
      loadSiteMeta(),
    ]);
    allGoods = await goodsRes.json();
    renderLastUpdated();
    buildCategoryTabs();
    render();
    bindNavMenuToggle();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
