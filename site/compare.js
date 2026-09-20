/* お気に入り一覧(localStorageに保存したカードだけを表示)。 */
(function () {
  "use strict";

  function render(cards, pricesLatest) {
    const favIds = loadFavorites();
    const favCards = cards.filter((c) => favIds.has(c.id));
    const grid = document.getElementById("card-grid");
    const emptyMsg = document.getElementById("empty-message");
    document.getElementById("result-count").textContent = `${favCards.length}件`;

    if (favCards.length === 0) {
      grid.replaceChildren();
      emptyMsg.classList.remove("hidden");
      return;
    }
    emptyMsg.classList.add("hidden");

    const frag = document.createDocumentFragment();
    for (const card of favCards) {
      frag.appendChild(createCardTile(card, pricesLatest));
    }
    grid.replaceChildren(frag);
  }

  async function init() {
    const [cards, meta, pricesLatest] = await Promise.all([
      loadCardData(),
      loadSiteMeta(),
      loadPricesLatest(),
    ]);
    renderLastUpdated();
    render(cards, pricesLatest);

    // 星をクリックして解除した場合、一覧からも即座に消えるようにする。
    document.getElementById("card-grid").addEventListener("click", (e) => {
      if (e.target.classList.contains("favorite-star")) {
        setTimeout(() => render(cards, pricesLatest), 0);
      }
    });

    bindModalEvents();
    bindNavMenuToggle();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
