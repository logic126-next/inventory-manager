// ==UserScript==
// @name         Mercari 持ち物 → Inventory Manager 同期
// @namespace    https://github.com/logic126/inventory-manager
// @version      1.3.0
// @description  Mercari 持ち物一覧のアイテムをワンクリックで Inventory Manager に同期
// @match        *://jp.mercari.com/mypage/inventory*
// @match        *://jp.mercari.com/mypage/inventory/*
// @grant        none
// @run-at       document-end
// @author       logic126
// ==/UserScript==

(function () {
  "use strict";

  const API_URL = "https://192.168.1.203/inventory/api/scrapers/mercari/owned/push";

  // ── Styles ─────────────────────────────────────────────
  const STYLES = `
    #mercari-sync-fab {
      position: fixed !important;
      bottom: 24px !important;
      right: 24px !important;
      z-index: 99999 !important;
      display: flex !important;
      flex-direction: column !important;
      align-items: flex-end !important;
      gap: 8px !important;
      font-family: -apple-system, 'Hiragino Sans', 'Meiryo', sans-serif !important;
    }
    #mercari-sync-btn {
      display: flex !important;
      align-items: center !important;
      gap: 8px !important;
      padding: 12px 20px !important;
      background: linear-gradient(135deg, #161b22, #1a2332) !important;
      color: #e6edf3 !important;
      border: 2px solid #30363d !important;
      border-radius: 12px !important;
      font-size: 14px !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      box-shadow: 0 4px 16px rgba(0,0,0,0.4) !important;
      transition: all 0.2s ease !important;
      user-select: none !important;
      white-space: nowrap !important;
    }
    #mercari-sync-btn:hover {
      border-color: #58a6ff !important;
      box-shadow: 0 4px 24px rgba(88,166,255,0.3) !important;
      transform: translateY(-1px) !important;
    }
    #mercari-sync-btn.syncing {
      opacity: 0.7 !important;
      cursor: wait !important;
      pointer-events: none !important;
    }
    #mercari-sync-btn .icon { font-size: 18px !important; }
    #mercari-sync-toast {
      position: fixed !important;
      bottom: 80px !important;
      right: 24px !important;
      z-index: 99999 !important;
      padding: 14px 20px !important;
      border-radius: 10px !important;
      font-size: 13px !important;
      font-weight: 500 !important;
      box-shadow: 0 4px 16px rgba(0,0,0,0.3) !important;
      animation: mercari-sync-slide-in 0.3s ease !important;
      max-width: 340px !important;
      line-height: 1.5 !important;
    }
    #mercari-sync-toast.success { background: #0d1117 !important; color: #3fb950 !important; border: 1px solid #3fb950 !important; }
    #mercari-sync-toast.error { background: #0d1117 !important; color: #f85149 !important; border: 1px solid #f85149 !important; }
    #mercari-sync-toast.info { background: #0d1117 !important; color: #58a6ff !important; border: 1px solid #58a6ff !important; }
    @keyframes mercari-sync-slide-in {
      from { opacity: 0; transform: translateY(10px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @media (max-width: 600px) {
      #mercari-sync-fab { bottom: 16px !important; right: 16px !important; }
      #mercari-sync-btn { padding: 10px 14px !important; font-size: 13px !important; }
      #mercari-sync-toast { bottom: 70px !important; right: 12px !important; left: 12px !important; max-width: none !important; }
    }
  `;

  // ── Extraction Logic ──────────────────────────────────
  function extractItems() {
    const items = [];

    // Collect all item links
    const allLinks = Array.from(document.querySelectorAll("a"))
      .filter((a) => {
        const href = a.getAttribute("href") || a.href || "";
        return href.match(/\/inventory\/m\d+/);
      })
      .map((a) => a.href);
    const links = [...new Set(allLinks)];

    // Collect all product images
    const allImgs = Array.from(document.querySelectorAll("img")).flatMap((img) => {
      const candidates = [
        img.src,
        img.getAttribute("data-src") || "",
        img.getAttribute("data-lazy-src") || "",
        img.getAttribute("data-original") || "",
      ].filter((s) => s && !s.startsWith("data:") && s !== window.location.href);
      return candidates;
    });
    const images = [...new Set(allImgs)].filter((s) => s.match(/\/photos\/m\d+/));

    // Parse body text for the pattern: name / ¥ / price / status
    const bodyText = document.body.innerText;
    const lines = bodyText.split("\n").map((l) => l.trim()).filter((l) => l);

    let linkIdx = 0;
    let imgIdx = 0;

    for (let i = 0; i < lines.length - 3; i++) {
      if (lines[i + 1] === "¥") {
        const name = lines[i].trim();
        const priceStr = lines[i + 2].trim();
        const status = lines[i + 3].trim();
        const price = parseInt(priceStr.replace(/,/g, ""));

        let url = null;
        if (linkIdx < links.length) {
          url = links[linkIdx].replace("/sell/inventory/", "/inventory/");
        }
        let image_url = null;
        if (imgIdx < images.length) {
          image_url = images[imgIdx];
        }

        if (name.length >= 2 && price > 0 && status) {
          items.push({ name, price, status, url, image_url });
          linkIdx++;
          imgIdx++;
          i += 3;
        }
      }
    }

    return items;
  }

  // ── UI Elements ───────────────────────────────────────
  function createUI() {
    if (document.getElementById("mercari-sync-fab")) return; // Already injected

    const styleEl = document.createElement("style");
    styleEl.textContent = STYLES;
    document.head.appendChild(styleEl);

    const container = document.createElement("div");
    container.id = "mercari-sync-fab";

    const btn = document.createElement("button");
    btn.id = "mercari-sync-btn";
    btn.innerHTML = '<span class="icon">📦</span> <span>在庫同期</span>';
    btn.addEventListener("click", handleSync);

    container.appendChild(btn);
    document.body.appendChild(container);

    console.log("[Mercari Sync] Button injected ✓");
  }

  // ── Toast Notification ────────────────────────────────
  function showToast(message, type, duration) {
    duration = duration || 5000;
    const existing = document.getElementById("mercari-sync-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.id = "mercari-sync-toast";
    toast.className = type;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(function () {
      toast.style.transition = "opacity 0.3s ease";
      toast.style.opacity = "0";
      setTimeout(function () { toast.remove(); }, 300);
    }, duration);
  }

  // ── Sync Handler ──────────────────────────────────────
  function handleSync() {
    var btn = document.getElementById("mercari-sync-btn");
    if (!btn) return;

    btn.classList.add("syncing");
    btn.innerHTML = '<span class="icon">⏳</span> <span>同期中...</span>';

    var items = extractItems();

    if (items.length === 0) {
      showToast("⚠️ 商品が見つかりませんでした。持ち物一覧ページで再試行してください。", "error");
      resetButton();
      return;
    }

    showToast("\uD83D\uDCE2 " + items.length + " 件の商品を同期中...", "info", 3000);

    var xhr = new XMLHttpRequest();
    xhr.open("POST", API_URL, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.timeout = 30000;

    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;

      if (xhr.status === 0 || xhr.status >= 400) {
        var errorMsg = "\u274C 同期に失敗しました";
        if (xhr.status === 0) {
          errorMsg += "\n\u{1F527} Inventory Manager に接続できません。";
        } else {
          errorMsg += "\n" + xhr.responseText;
        }
        showToast(errorMsg, "error", 8000);
        resetButton();
        return;
      }

      try {
        var result = JSON.parse(xhr.responseText);
        var parts = [];
        if (result.created > 0) parts.push("\u2705 " + result.created + " 件追加");
        if (result.updated > 0) parts.push("\uD83D\uDD04 " + result.updated + " 件更新");
        if (result.skipped > 0) parts.push("\u23ED " + result.skipped + " 件スキップ");

        var message = parts.join("  ") || "\u2705 変更なし";
        showToast(message, "success", 6000);
        btn.innerHTML = '<span class="icon">\u2705</span> <span>完了!</span>';
        setTimeout(resetButton, 2000);
      } catch (e) {
        showToast("\u274C 同期失敗: " + e.message, "error", 8000);
        resetButton();
      }
    };

    xhr.onerror = function () {
      showToast("\u274C 接続エラー。ネットワークを確認してください。", "error", 8000);
      resetButton();
    };

    xhr.send(JSON.stringify({ items: items }));
  }

  function resetButton() {
    var btn = document.getElementById("mercari-sync-btn");
    if (btn) {
      btn.classList.remove("syncing");
      btn.innerHTML = '<span class="icon">\uD83D\uDCE6</span> <span>在庫同期</span>';
    }
  }

  // ── SPA-aware injection: wait for Mercari content ─────
  // Mercari is a SPA — wait until inventory items actually appear
  var uiInjected = false;

  function waitForContent() {
    // Check if Mercari has rendered inventory items (look for ¥ sign or inventory links)
    var hasContent = document.body.innerText.indexOf("¥") !== -1
      || document.querySelector('a[href*="/inventory/m"]') !== null;

    if (hasContent && !uiInjected) {
      uiInjected = true;
      createUI();
      return true;
    }
    return false;
  }

  // Strategy 1: Poll every 500ms for up to 15 seconds
  var pollCount = 0;
  var pollInterval = setInterval(function () {
    pollCount++;
    if (waitForContent()) {
      clearInterval(pollInterval);
    }
    if (pollCount >= 30) { // 15 seconds max
      clearInterval(pollInterval);
      // Force inject anyway — user can still click it
      if (!uiInjected) {
        uiInjected = true;
        createUI();
      }
    }
  }, 500);

  // Strategy 2: MutationObserver for SPA content changes
  try {
    var observer = new MutationObserver(function (mutations) {
      if (!uiInjected) {
        if (waitForContent()) {
          observer.disconnect();
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  } catch (e) {
    // Fallback: observer not available
  }

})();
