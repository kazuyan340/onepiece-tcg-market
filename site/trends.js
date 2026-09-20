/* 価格の動き(直近上昇/上昇傾向/直近下降/下降傾向)。全ショップ平均価格(「全体」系列)のみ表示する。 */
(function () {
  "use strict";

  function renderSection(gridId, emptyId, items, cardsById, pricesLatest) {
    const grid = document.getElementById(gridId);
    const empty = document.getElementById(emptyId);
    const pooled = items.filter((i) => i.site === "全体");

    if (pooled.length === 0) {
      grid.replaceChildren();
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");

    const frag = document.createDocumentFragment();
    for (const item of pooled) {
      const card = cardsById.get(item.card_id);
      if (!card) continue;
      const sign = item.change_pct > 0 ? "+" : "";
      const badge = `<div class="trend-badge">${sign}${item.change_pct}%　¥${item.previous_price.toLocaleString()}→¥${item.latest_price.toLocaleString()}</div>`;
      frag.appendChild(createCardTile(card, pricesLatest, badge));
    }
    grid.replaceChildren(frag);
  }

  async function init() {
    const [cards, meta, pricesLatest, trendsRes] = await Promise.all([
      loadCardData(),
      loadSiteMeta(),
      loadPricesLatest(),
      fetchFresh("data/trends.json"),
    ]);
    const trends = await trendsRes.json();
    const cardsById = new Map(cards.map((c) => [c.id, c]));
    renderLastUpdated();

    renderSection("recent-up-grid", "recent-up-empty", trends.recent_up, cardsById, pricesLatest);
    renderSection("trend-up-grid", "trend-up-empty", trends.trend_up, cardsById, pricesLatest);
    renderSection("recent-down-grid", "recent-down-empty", trends.recent_down, cardsById, pricesLatest);
    renderSection("trend-down-grid", "trend-down-empty", trends.trend_down, cardsById, pricesLatest);

    bindModalEvents();
    bindNavMenuToggle();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
