/* デッキ作成ツール(ワンピースカードゲームの公式ルールに準拠した簡易デッキビルダー)。
   ルール:
   - リーダー1枚 + デッキ(キャラ/イベント/ステージ)ちょうど50枚。
   - 同じカード(カード番号基準・レアリティ違い/再録含む)は最大4枚まで。
   - デッキに入れるカードは、リーダーの色を1色以上含んでいる必要がある
     (リーダーは1〜2色を持つ。例: 赤/緑リーダーになら赤 or 緑 or 赤/緑のカードだけ入れられる)。
   左側にリーダー+デッキ全体を常に表示し、右側の検索パネルはタブで「リーダーを探す」/
   「デッキ用を探す」を切り替える(conan-tcg-market/pokemon-tcg-marketのデッキビルダーの
   構成を踏襲しつつ、保存は単一デッキに簡略化している。カードのidは数値ではなく
   "EB01-001"のような文字列なのでNumber()変換はしない)。 */

const DECK_SIZE = 50;
const MAX_COPIES = 4;
const DECK_KEY = "onepieceTcgDeckBuilder";
const INCLUDE_LEADER_KEY = "onepieceTcgDeckIncludeLeader";
const DECK_CARD_TYPES = ["CHARACTER", "EVENT", "STAGE"];

const FILTER_FIELDS = {
  color: { listId: "filter-color-list", groupId: "filter-color-group" },
  rarity: { listId: "filter-rarity-list", groupId: "filter-rarity-group" },
  pack: { listId: "filter-pack-list", groupId: "filter-pack-group" },
};

let allCards = [];
let cardById = new Map();
let pricesLatest = {};
let filteredCards = [];
// 検索パネルのタブ: "leader"ならLEADERカードだけ、"deck"ならキャラ/イベント/ステージだけを表示する。
let focusedZone = "deck";

// deck = { leader: cardId|null, main: { cardId: count } }
let deck = { leader: null, main: {} };
let hasUnsavedUrlDeck = false;
let includeLeaderInTotal = localStorage.getItem(INCLUDE_LEADER_KEY) !== "false";

const filterState = {
  color: { include: new Set(), exclude: new Set() },
  rarity: { include: new Set(), exclude: new Set() },
  pack: { include: new Set(), exclude: new Set() },
};

const grid = document.getElementById("card-grid");
const resultCount = document.getElementById("result-count");
const keywordInput = document.getElementById("keyword");
const sortSelect = document.getElementById("sort-select");
const deckSortSelect = document.getElementById("deck-sort-select");
let deckSortMode = "name_asc";

async function init() {
  const [cards, meta, prices] = await Promise.all([
    loadCardData(),
    loadSiteMeta(),
    loadPricesLatest(),
  ]);
  allCards = cards;
  pricesLatest = prices;
  cardById = new Map(allCards.map((c) => [c.id, c]));

  populateFilterOptions(meta);
  bindEvents();
  bindModalEvents();
  bindNavMenuToggle();
  loadDeckFromUrlOrStorage();
  applyFilters();
  renderDeckPanel();
  renderLastUpdated();
}

// ---- 色の判定 ----
function splitColors(colorStr) {
  return String(colorStr || "")
    .split("/")
    .map((s) => s.trim())
    .filter(Boolean);
}

function colorsOverlap(a, b) {
  return a.some((c) => b.includes(c));
}

function leaderCard() {
  return deck.leader ? cardById.get(deck.leader) : null;
}

function cardMatchesLeaderColor(card) {
  const leader = leaderCard();
  if (!leader) return true; // リーダー未選択の間は色の制限なし
  return colorsOverlap(splitColors(card.color), splitColors(leader.color));
}

function updateLegalityNote() {
  const note = document.getElementById("color-legality-note");
  const leader = leaderCard();
  if (!leader) {
    note.textContent = "リーダーを選ぶと、デッキに入れられる色が自動で判定されます。";
    return;
  }
  const colors = splitColors(leader.color).join("・");
  note.textContent = `リーダー「${leader.name}」の色: ${colors}。この色を1色も含まないカードはデッキに入れられません。`;
}

function populateFilterOptions(meta) {
  buildTriStateList("filter-color-list", meta.colors || [], filterState.color.include, filterState.color.exclude, applyFilters);
  buildTriStateList("filter-rarity-list", meta.rarities || [], filterState.rarity.include, filterState.rarity.exclude, applyFilters);
  const packValues = [...(meta.packs || [])];
  sortPackValues(packValues);
  buildTriStateList("filter-pack-list", packValues, filterState.pack.include, filterState.pack.exclude, applyFilters, packGroupFor);
}

function resetFilterUI() {
  keywordInput.value = "";
  for (const key of Object.keys(FILTER_FIELDS)) {
    filterState[key].include.clear();
    filterState[key].exclude.clear();
  }
  const meta = { colors: [], rarities: [], packs: [] };
  // 選択状態だけリセットし、一覧そのものは再構築しない(既存のボタンの見た目を戻す)。
  for (const [field, { listId }] of Object.entries(FILTER_FIELDS)) {
    const container = document.getElementById(listId);
    for (const btn of container.querySelectorAll(".tri-filter-item")) {
      btn.dataset.state = "none";
      btn.textContent = "☐ " + btn.textContent.replace(/^(✅ |🚫 |☐ )/, "");
    }
    updateFilterCountBadgeSafe(listId);
  }
  void meta;
}

function updateFilterCountBadgeSafe(listId) {
  const groupId = listId.replace(/-list$/, "-group");
  const badge = document.querySelector(`#${groupId} .count-badge`);
  if (badge) badge.classList.add("hidden");
}

function bindEvents() {
  keywordInput.addEventListener("input", debounce(applyFilters, 200));
  sortSelect.addEventListener("change", applyFilters);
  deckSortSelect.addEventListener("change", () => {
    deckSortMode = deckSortSelect.value;
    renderDeckPanel();
  });

  const includeCheckbox = document.getElementById("include-leader");
  includeCheckbox.checked = includeLeaderInTotal;
  includeCheckbox.addEventListener("change", () => {
    includeLeaderInTotal = includeCheckbox.checked;
    localStorage.setItem(INCLUDE_LEADER_KEY, String(includeLeaderInTotal));
    renderDeckPanel();
  });

  document.getElementById("clear-deck").addEventListener("click", () => {
    if (!confirm("このデッキの内容をすべてクリアします。よろしいですか?")) return;
    deck.leader = null;
    deck.main = {};
    saveDeck();
    renderDeckPanel();
  });

  document.getElementById("share-deck").addEventListener("click", shareDeckUrl);
  document.getElementById("max-rarity-deck").addEventListener("click", () => swapDeckToExtremeRarity(true));
  document.getElementById("min-rarity-deck").addEventListener("click", () => swapDeckToExtremeRarity(false));

  document.querySelectorAll(".deck-zone-tab").forEach((btn) => {
    btn.addEventListener("click", () => focusZone(btn.dataset.zone));
  });

  document.addEventListener("click", (e) => {
    for (const details of document.querySelectorAll(".filter-group[open]")) {
      if (!details.contains(e.target)) details.removeAttribute("open");
    }
  });
}

function focusZone(zone) {
  focusedZone = zone;
  document.querySelectorAll(".deck-zone-tab").forEach((b) => b.classList.toggle("active", b.dataset.zone === zone));
  applyFilters();
  document.querySelector(".deck-search-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// ---- 保存・共有 ----
function saveDeck() {
  try {
    localStorage.setItem(DECK_KEY, JSON.stringify(deck));
  } catch {
    // localStorageが使えない環境では保存をあきらめる(致命的ではない)
  }
}

function loadDeckFromUrlOrStorage() {
  try {
    const raw = localStorage.getItem(DECK_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        deck = { leader: parsed.leader ?? null, main: parsed.main || {} };
      }
    }
  } catch {
    // 壊れたデータは無視して初期状態のまま
  }

  const fromUrl = new URLSearchParams(location.search).get("deck");
  if (fromUrl) {
    try {
      const decoded = JSON.parse(decodeURIComponent(escape(atob(fromUrl))));
      if (decoded && typeof decoded === "object" && confirm("共有されたデッキを読み込みますか?(今のデッキは上書きされます)")) {
        deck = { leader: decoded.leader ?? null, main: decoded.main || {} };
        saveDeck();
      }
      history.replaceState(null, "", location.pathname);
    } catch {
      // URLのデッキデータが壊れている場合は無視する
    }
  }
}

function shareDeckUrl() {
  const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(deck))));
  const url = `${location.origin}${location.pathname}?deck=${encoded}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).then(
      () => alert("デッキのURLをコピーしました。"),
      () => prompt("このURLをコピーしてください:", url)
    );
  } else {
    prompt("このURLをコピーしてください:", url);
  }
}

// ---- 価格 ----
function cardPrice(card) {
  const info = pricesLatest[card.id];
  return info ? info.pooled_avg : null;
}

function deckCount() {
  return Object.values(deck.main).reduce((sum, n) => sum + n, 0);
}

function copyGroupKey(card) {
  return card.card_num;
}

// 現在デッキに入っている、同じカード(レアリティ違い含む)の合計枚数。
function copiesInGroup(card) {
  const key = copyGroupKey(card);
  let total = 0;
  for (const [id, count] of Object.entries(deck.main)) {
    const other = cardById.get(id);
    if (other && copyGroupKey(other) === key) total += count;
  }
  return total;
}

function computeDeckTotal() {
  let total = 0;
  if (includeLeaderInTotal) {
    const leader = leaderCard();
    if (leader) {
      const p = cardPrice(leader);
      if (p !== null) total += p;
    }
  }
  for (const [id, count] of Object.entries(deck.main)) {
    const card = cardById.get(id);
    if (!card) continue;
    const p = cardPrice(card);
    if (p !== null) total += p * count;
  }
  return total;
}

// ---- カード追加/削除 ----
function trySetLeader(card) {
  const entries = Object.entries(deck.main);
  if (entries.length > 0) {
    const newColors = splitColors(card.color);
    const illegal = entries.filter(([id]) => {
      const c = cardById.get(id);
      return c && !colorsOverlap(splitColors(c.color), newColors);
    });
    if (illegal.length > 0) {
      const names = illegal
        .map(([id]) => (cardById.get(id) || {}).name)
        .filter(Boolean)
        .join("、");
      const ok = confirm(`リーダーを「${card.name}」に変更すると、色が合わないカード(${names})がデッキから外れます。よろしいですか?`);
      if (!ok) return;
      for (const [id] of illegal) delete deck.main[id];
    }
  }
  deck.leader = card.id;
  saveDeck();
  renderDeckPanel();
}

function addCard(card) {
  if (card.card_type === "LEADER") {
    trySetLeader(card);
    return;
  }
  if (!cardMatchesLeaderColor(card)) {
    const leader = leaderCard();
    alert(`「${card.name}」はリーダー(${splitColors(leader.color).join("・")})と色が一致しないため、デッキに入れられません。`);
    return;
  }
  if (copiesInGroup(card) >= MAX_COPIES) {
    alert(`同じカード(レアリティ違いを含む)は最大${MAX_COPIES}枚までです。`);
    return;
  }
  if (deckCount() >= DECK_SIZE) {
    alert(`デッキは${DECK_SIZE}枚までです。`);
    return;
  }
  deck.main[card.id] = (deck.main[card.id] || 0) + 1;
  saveDeck();
  renderDeckPanel();
}

function removeOneFromMainDeck(cardId) {
  const current = deck.main[cardId] || 0;
  if (current <= 1) delete deck.main[cardId];
  else deck.main[cardId] = current - 1;
  saveDeck();
  renderDeckPanel();
}

// デッキ内の各カードを、同じカード(card_num基準・レアリティ違い/再録含む)の中で
// 相場が一番高い/安いバリアントに一括で入れ替える。
function bestVariantId(cardId, wantMax) {
  const currentCard = cardById.get(cardId);
  if (!currentCard) return cardId;
  const key = copyGroupKey(currentCard);
  const priced = allCards
    .filter((c) => copyGroupKey(c) === key)
    .map((c) => ({ id: c.id, price: cardPrice(c) }))
    .filter((v) => v.price !== null);
  if (priced.length === 0) return cardId;
  const best = priced.reduce((acc, cur) => {
    if (wantMax) return cur.price > acc.price ? cur : acc;
    return cur.price < acc.price ? cur : acc;
  });
  return best.id;
}

function swapDeckToExtremeRarity(wantMax) {
  const newMain = {};
  for (const [id, count] of Object.entries(deck.main)) {
    const newId = bestVariantId(id, wantMax);
    newMain[newId] = (newMain[newId] || 0) + count;
  }
  deck.main = newMain;
  if (deck.leader) deck.leader = bestVariantId(deck.leader, wantMax);
  saveDeck();
  renderDeckPanel();
}

// ---- 検索・絞り込み ----
function cardAllowedInFocusedZone(card) {
  if (focusedZone === "leader") return card.card_type === "LEADER";
  return DECK_CARD_TYPES.includes(card.card_type);
}

function applyFilters() {
  const keyword = keywordInput.value.trim().toLowerCase();

  filteredCards = allCards.filter((c) => {
    if (!cardAllowedInFocusedZone(c)) return false;
    if (keyword && !String(c.name || "").toLowerCase().includes(keyword)) return false;
    if (!matchesTriState(c.color, filterState.color.include, filterState.color.exclude)) return false;
    if (!matchesTriState(c.rarity, filterState.rarity.include, filterState.rarity.exclude)) return false;
    if (!matchesTriState(c.pack, filterState.pack.include, filterState.pack.exclude)) return false;
    return true;
  });

  filteredCards = sortCards(filteredCards, sortSelect.value);
  resultCount.textContent = `${filteredCards.length} 件`;
  renderResults();
}

function sortCards(cards, sortMode) {
  const cut = sortMode.lastIndexOf("_");
  const field = sortMode.slice(0, cut);
  const direction = sortMode.slice(cut + 1);
  const sign = direction === "desc" ? -1 : 1;

  return [...cards].sort((a, b) => {
    if (field === "id") return sign * String(a.card_num || a.id).localeCompare(String(b.card_num || b.id), "ja", { numeric: true });
    if (field === "cost" || field === "power") {
      const av = a[field] === null || a[field] === undefined ? null : Number(a[field]);
      const bv = b[field] === null || b[field] === undefined ? null : Number(b[field]);
      const aMissing = av === null || Number.isNaN(av);
      const bMissing = bv === null || Number.isNaN(bv);
      if (aMissing && bMissing) return a.name.localeCompare(b.name, "ja");
      if (aMissing) return 1;
      if (bMissing) return -1;
      return sign * (av - bv);
    }
    return sign * a.name.localeCompare(b.name, "ja");
  });
}

function createSearchTile(card) {
  const tile = document.createElement("div");
  tile.className = "card-tile";
  tile.title = card.name;
  const price = cardPrice(card);
  const priceText = price !== null ? `${price.toLocaleString()}円` : "-";
  const legal = card.card_type === "LEADER" || cardMatchesLeaderColor(card);

  tile.innerHTML = `
    <div class="trend-badge">${escapeHtml(priceText)}</div>
    <div class="deck-tile-img-wrap">
      <img src="${card.image_url || ""}" alt="${escapeHtml(card.name)}" loading="lazy">
      <button type="button" class="deck-info-btn" title="詳細を見る">🔍</button>
    </div>
  `;
  if (!legal) tile.style.opacity = "0.45";

  tile.addEventListener("click", () => addCard(card));
  tile.querySelector(".deck-info-btn").addEventListener("click", (e) => {
    e.stopPropagation();
    openModal(card, pricesLatest);
  });

  return tile;
}

function renderResults() {
  grid.innerHTML = "";
  filteredCards.forEach((card) => grid.appendChild(createSearchTile(card)));
}

// ---- デッキパネル描画 ----
function renderLeaderSlot() {
  const el = document.getElementById("deck-leader");
  const leader = leaderCard();
  el.classList.toggle("empty", !leader);
  el.onclick = () => focusZone("leader");

  if (!leader) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `
    <img src="${leader.image_url || ""}" alt="${escapeHtml(leader.name)}">
    <button type="button" class="deck-slot-clear" title="解除">&times;</button>
  `;
  el.querySelector(".deck-slot-clear").addEventListener("click", (e) => {
    e.stopPropagation();
    deck.leader = null;
    saveDeck();
    renderDeckPanel();
  });
}

function deckEntryCompare(a, b, sortMode) {
  const cut = sortMode.lastIndexOf("_");
  const field = sortMode.slice(0, cut);
  const direction = sortMode.slice(cut + 1);
  const sign = direction === "desc" ? -1 : 1;

  if (field === "card_num") {
    return sign * (a.card.card_num || "").localeCompare(b.card.card_num || "", "ja", { numeric: true });
  }
  if (field === "cost" || field === "power") {
    const av = a.card[field];
    const bv = b.card[field];
    const aMissing = av === null || av === undefined;
    const bMissing = bv === null || bv === undefined;
    if (aMissing && bMissing) return a.card.name.localeCompare(b.card.name, "ja");
    if (aMissing) return 1;
    if (bMissing) return -1;
    if (av !== bv) return sign * (av - bv);
  }
  return sign * a.card.name.localeCompare(b.card.name, "ja");
}

function renderDeckPanel() {
  renderLeaderSlot();
  updateLegalityNote();

  const mainGrid = document.getElementById("deck-main-grid");
  mainGrid.innerHTML = "";

  const entries = Object.entries(deck.main)
    .map(([id, count]) => ({ card: cardById.get(id), count }))
    .filter((e) => e.card)
    .sort((a, b) => deckEntryCompare(a, b, deckSortMode));

  let slotsFilled = 0;
  for (const { card, count } of entries) {
    for (let i = 0; i < count; i++) {
      const slot = document.createElement("div");
      slot.className = "deck-slot-box";
      slot.title = `${card.name}(クリックで1枚減らす)`;
      slot.innerHTML = `<img src="${card.image_url || ""}" alt="${escapeHtml(card.name)}">`;
      slot.addEventListener("click", () => removeOneFromMainDeck(card.id));
      mainGrid.appendChild(slot);
      slotsFilled++;
    }
  }
  for (let i = slotsFilled; i < DECK_SIZE; i++) {
    const slot = document.createElement("div");
    slot.className = "deck-slot-box empty";
    slot.addEventListener("click", () => focusZone("deck"));
    mainGrid.appendChild(slot);
  }

  const count = deckCount();
  const countEl = document.getElementById("deck-count");
  countEl.textContent = `デッキ ${count}/${DECK_SIZE}枚${deck.leader ? "" : "(リーダー未選択)"}`;
  countEl.classList.toggle("deck-count-ok", count === DECK_SIZE && !!deck.leader);
  countEl.classList.toggle("deck-count-warn", count > DECK_SIZE);

  document.getElementById("deck-total").textContent = `合計 ${computeDeckTotal().toLocaleString()}円`;

  // 検索結果側もリーダー変更後に合法/非合法の見た目(薄表示)を更新する。
  renderResults();
}

init();
