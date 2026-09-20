/* 値上がり/値下がり一覧。movers-up.html/movers-down.htmlの両方から
   window.MOVERS_DIRECTION("up"|"down")で共用する。全ショップ平均価格(「全体」系列)のみ表示。 */
(function () {
  "use strict";

  async function init() {
    const direction = window.MOVERS_DIRECTION;
    const [cards, meta, pricesLatest, moversRes] = await Promise.all([
      loadCardData(),
      loadSiteMeta(),
      loadPricesLatest(),
      fetchFresh("data/movers.json"),
    ]);
    const movers = await moversRes.json();
    const cardsById = new Map(cards.map((c) => [c.id, c]));
    renderLastUpdated();

    const items = (movers[direction] || []).filter((i) => i.site === "全体");
    const grid = document.getElementById("card-grid");
    const emptyMsg = document.getElementById("empty-message");
    document.getElementById("result-count").textContent = `${items.length}件`;

    if (items.length === 0) {
      emptyMsg.classList.remove("hidden");
    } else {
      const frag = document.createDocumentFragment();
      for (const item of items) {
        const card = cardsById.get(item.card_id);
        if (!card) continue;
        const sign = item.change_pct > 0 ? "+" : "";
        const badge = `<div class="trend-badge">${sign}${item.change_pct}%　¥${item.previous_price.toLocaleString()}→¥${item.latest_price.toLocaleString()}</div>`;
        frag.appendChild(createCardTile(card, pricesLatest, badge));
      }
      grid.replaceChildren(frag);
    }

    bindModalEvents();
    bindNavMenuToggle();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
