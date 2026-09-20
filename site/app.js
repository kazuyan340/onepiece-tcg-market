/* ワンピースカードゲーム カード図鑑 — 一覧・検索(common.jsの上に乗る一覧ページ専用処理) */
(function () {
  "use strict";

  let allCards = [];
  let pricesLatest = {};

  const state = {
    keyword: "",
    colors: { include: new Set(), exclude: new Set() },
    types: { include: new Set(), exclude: new Set() },
    rarities: { include: new Set(), exclude: new Set() },
    packs: { include: new Set(), exclude: new Set() },
    keywords: { include: new Set(), exclude: new Set() },
  };

  const grid = document.getElementById("card-grid");
  const resultCount = document.getElementById("result-count");
  const keywordInput = document.getElementById("keyword");

  function cardMatches(card) {
    if (state.keyword) {
      const kw = state.keyword;
      const haystack = [card.name, card.feature, card.ability_text, card.trigger_text]
        .filter(Boolean).join(" ");
      if (!haystack.includes(kw)) return false;
    }
    if (!matchesTriState(card.color, state.colors.include, state.colors.exclude)) return false;
    if (!matchesTriState(card.card_type, state.types.include, state.types.exclude)) return false;
    if (!matchesTriState(card.rarity, state.rarities.include, state.rarities.exclude)) return false;
    if (!matchesTriState(card.pack, state.packs.include, state.packs.exclude)) return false;
    if (!matchesTriStateArray(abilityKeywordsForCard(card), state.keywords.include, state.keywords.exclude)) return false;
    return true;
  }

  function renderGrid() {
    const filtered = allCards.filter(cardMatches);
    resultCount.textContent = `${filtered.length}件 / 全${allCards.length}件`;

    const frag = document.createDocumentFragment();
    for (const card of filtered) {
      frag.appendChild(createCardTile(card, pricesLatest));
    }
    grid.replaceChildren(frag);
  }

  function buildAllFilterLists(meta) {
    buildTriStateList("filter-color-list", meta.colors, state.colors.include, state.colors.exclude, renderGrid);
    buildTriStateList("filter-type-list", meta.card_types, state.types.include, state.types.exclude, renderGrid);
    buildTriStateList("filter-rarity-list", meta.rarities, state.rarities.include, state.rarities.exclude, renderGrid);
    const packValues = [...meta.packs];
    sortPackValues(packValues);
    buildTriStateList("filter-pack-list", packValues, state.packs.include, state.packs.exclude, renderGrid, packGroupFor);
    buildTriStateList("filter-keyword-list", ABILITY_KEYWORDS, state.keywords.include, state.keywords.exclude, renderGrid);
  }

  function resetFilters(meta) {
    state.keyword = "";
    keywordInput.value = "";
    for (const key of ["colors", "types", "rarities", "packs", "keywords"]) {
      state[key].include.clear();
      state[key].exclude.clear();
    }
    buildAllFilterLists(meta);
    renderGrid();
  }

  async function init() {
    const [cards, meta, prices] = await Promise.all([
      loadCardData(),
      loadSiteMeta(),
      loadPricesLatest(),
    ]);
    allCards = cards;
    pricesLatest = prices;
    renderLastUpdated();

    buildAllFilterLists(meta);
    renderGrid();

    keywordInput.addEventListener("input", () => {
      state.keyword = keywordInput.value.trim();
      renderGrid();
    });

    document.getElementById("reset-filters").addEventListener("click", () => resetFilters(meta));
    bindModalEvents();
    bindFiltersToggle();
    bindNavMenuToggle();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
