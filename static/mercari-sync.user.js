// ==UserScript==
// @name         Mercari 持ち物 → Inventory Manager 同期
// @namespace    https://github.com/logic126/inventory-manager
// @version      1.4.0
// @description  Mercari 持ち物一覧のアイテムをワンクリックで Inventory Manager に同期
// @match        *://jp.mercari.com/mypage/inventory*
// @match        *://jp.mercari.com/mypage/inventory/*
// @match        *://jp.mercari.com/sell/inventory*
// @match        *://jp.mercari.com/mypage/*inventory*
// @match        *://jp.mercari.com/*inventory*
// @grant        GM_xmlhttpRequest
// @run-at       document-idle
// @author       logic126
// ==/UserScript==

(function () {
  "use strict";

  console.log("[Mercari Sync] Script loaded ✓ URL:", window.location.href);

  var API_URL = "https://192.168.1.203/inventory/api/scrapers/mercari/owned/push";

  // ── Styles ─────────────────────────────────────────────
  var STYLES = [
    "#mercari-sync-fab{position:fixed!important;bottom:24px!important;right:24px!important;z-index:99999!important;display:flex!important;flex-direction:column!important;align-items:flex-end!important;gap:8px!important;font-family:-apple-system,'Hiragino Sans','Meiryo',sans-serif!important}",
    "#mercari-sync-btn{display:flex!important;align-items:center!important;gap:8px!important;padding:12px 20px!important;background:linear-gradient(135deg,#161b22,#1a2332)!important;color:#e6edf3!important;border:2px solid #30363d!important;border-radius:12px!important;font-size:14px!important;font-weight:600!important;cursor:pointer!important;box-shadow:0 4px 16px rgba(0,0,0,0.4)!important;transition:all 0.2s ease!important;user-select:none!important;white-space:nowrap!important}",
    "#mercari-sync-btn:hover{border-color:#58a6ff!important;box-shadow:0 4px 24px rgba(88,166,255,0.3)!important;transform:translateY(-1px)!important}",
    "#mercari-sync-btn.syncing{opacity:0.7!important;cursor:wait!important;pointer-events:none!important}",
    "#mercari-sync-btn .icon{font-size:18px!important}",
    "#mercari-sync-toast{position:fixed!important;bottom:80px!important;right:24px!important;z-index:99999!important;padding:14px 20px!important;border-radius:10px!important;font-size:13px!important;font-weight:500!important;box-shadow:0 4px 16px rgba(0,0,0,0.3)!important;animation:mercari-sync-slide-in 0.3s ease!important;max-width:340px!important;line-height:1.5!important}",
    "#mercari-sync-toast.success{background:#0d1117!important;color:#3fb950!important;border:1px solid #3fb950!important}",
    "#mercari-sync-toast.error{background:#0d1117!important;color:#f85149!important;border:1px solid #f85149!important}",
    "#mercari-sync-toast.info{background:#0d1117!important;color:#58a6ff!important;border:1px solid #58a6ff!important}",
    "@keyframes mercari-sync-slide-in{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}",
    "@media(max-width:600px){#mercari-sync-fab{bottom:16px!important;right:16px!important}#mercari-sync-btn{padding:10px 14px!important;font-size:13px!important}#mercari-sync-toast{bottom:70px!important;right:12px!important;left:12px!important;max-width:none!important}}"
  ].join("\n");

  // ── Extraction Logic ──────────────────────────────────
  function extractItems() {
    var items = [];

    var allLinks = Array.prototype.slice.call(document.querySelectorAll("a"))
      .filter(function (a) {
        var href = a.getAttribute("href") || a.href || "";
        return /\/inventory\/m\d+/.test(href);
      })
      .map(function (a) { return a.href; });
    var links = allLinks.filter(function (item, pos, self) {
      return self.indexOf(item) === pos;
    });

    var allImgs = Array.prototype.slice.call(document.querySelectorAll("img")).reduce(function (acc, img) {
      var candidates = [
        img.src,
        img.getAttribute("data-src") || "",
        img.getAttribute("data-lazy-src") || "",
        img.getAttribute("data-original") || "",
      ].filter(function (s) { return s && !s.startsWith("data:") && s !== window.location.href; });
      return acc.concat(candidates);
    }, []);
    var images = allImgs.filter(function (item, pos, self) {
      return self.indexOf(item) === pos;
    }).filter(function (s) { return /\/photos\/m\d+/.test(s); });

    var bodyText = document.body.innerText;
    var lines = bodyText.split("\n").map(function (l) { return l.trim(); }).filter(function (l) { return l; });

    var linkIdx = 0;
    var imgIdx = 0;

    for (var i = 0; i < lines.length - 3; i++) {
      if (lines[i + 1] === "\u00a5") {
        var name = lines[i].trim();
        var priceStr = lines[i + 2].trim();
        var status = lines[i + 3].trim();
        var price = parseInt(priceStr.replace(/,/g, ""));

        var url = null;
        if (linkIdx < links.length) {
          url = links[linkIdx].replace("/sell/inventory/", "/inventory/");
        }
        var image_url = null;
        if (imgIdx < images.length) {
          image_url = images[imgIdx];
        }

        if (name.length >= 2 && price > 0 && status) {
          items.push({ name: name, price: price, status: status, url: url, image_url: image_url });
          linkIdx++;
          imgIdx++;
          i += 3;
        }
      }
    }

    console.log("[Mercari Sync] Extracted", items.length, "items");
    return items;
  }

  // ── UI Elements ───────────────────────────────────────
  function createUI() {
    if (document.getElementById("mercari-sync-fab")) {
      console.log("[Mercari Sync] UI already exists, skipping");
      return;
    }

    console.log("[Mercari Sync] Creating UI...");

    var styleEl = document.createElement("style");
    styleEl.textContent = STYLES;
    document.head.appendChild(styleEl);

    var container = document.createElement("div");
    container.id = "mercari-sync-fab";

    var btn = document.createElement("button");
    btn.id = "mercari-sync-btn";
    btn.innerHTML = '<span class="icon">\uD83D\uDCE6</span> <span>\u8CAFD\u540C\u671F</span>';

    // Use direct onclick instead of addEventListener to avoid scope issues
    btn.setAttribute("onclick", "window.__mercariSync()");

    container.appendChild(btn);
    document.body.appendChild(container);

    console.log("[Mercari Sync] Button injected \u2713");
  }

  // ── Toast Notification ────────────────────────────────
  function showToast(message, type, duration) {
    duration = duration || 5000;
    var existing = document.getElementById("mercari-sync-toast");
    if (existing) existing.remove();

    var toast = document.createElement("div");
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

  // ── Sync Handler (exposed to global scope for onclick) ──
  window.__mercariSync = function () {
    var btn = document.getElementById("mercari-sync-btn");
    if (!btn) return;

    btn.classList.add("syncing");
    btn.innerHTML = '<span class="icon">\u23F3</span> <span>\u540C\u671F\u4E2D...</span>';

    var items = extractItems();

    if (items.length === 0) {
      showToast("\u26A0\uFE0F \u5546\u54C1\u304C\u898B\u3064\u304B\u308A\u307E\u305B\u306D\u3044\u305F\u3002\u6301\u3061\u7269\u4E00\u89A7\u30DA\u30FC\u30B8\u3067\u518D\u8A66\u884C\u3057\u3066\u304F\u3060\u3055\u3044\u3002", "error");
      resetButton();
      return;
    }

    showToast("\uD83D\uDCE2 " + items.length + " \u4EF6\u306E\u5546\u54C1\u3092\u540C\u671F\u4E2D...", "info", 3000);

    // Use GM_xmlhttpRequest to avoid CORS issues
    GM_xmlhttpRequest({
      method: "POST",
      url: API_URL,
      headers: { "Content-Type": "application/json" },
      data: JSON.stringify({ items: items }),
      timeout: 30000,
      onload: function (response) {
        if (response.status >= 400) {
          showToast("\u274C \u540C\u671F\u306B\u4E0D\u529B\u3057\u307E\u3057\u305F\n" + response.responseText, "error", 8000);
          resetButton();
          return;
        }

        var result;
        try {
          result = JSON.parse(response.responseText);
        } catch (e) {
          showToast("\u274C \u540C\u671F\u4E0D\u529B: " + e.message, "error", 8000);
          resetButton();
          return;
        }

        var parts = [];
        if (result.created > 0) parts.push("\u2705 " + result.created + " \u4EF6\u8FFD\u52A0");
        if (result.updated > 0) parts.push("\uD83D\uDD04 " + result.updated + " \u4EF6\u66F4\u65B0");
        if (result.skipped > 0) parts.push("\u23ED " + result.skipped + " \u4EF6\u30B9\u30AD\u30C3\u30D7");

        var message = parts.join("  ") || "\u2705 \u5909\u66F4\u306A\u3057";
        showToast(message, "success", 6000);
        btn.innerHTML = '<span class="icon">\u2705</span> <span>\u5B8C\u4E86!</span>';
        setTimeout(resetButton, 2000);
      },
      onerror: function (err) {
        showToast("\u274C \u63A5\u7D9A\u30A8\u30E9\u30FC\u3002\u30CD\u30C3\u30C8\u30EF\u30FC\u30AF\u3092\u78BA\u8A8D\u3057\u3066\u304F\u3060\u3055\u3044\u3002", "error", 8000);
        resetButton();
      },
      ontimeout: function () {
        showToast("\u274C \u30BF\u30A4\u30E0\u30A2\u30A6\u30C8\u3057\u307E\u3057\u305F\u3002\u3057\u3068\u3046\u3082\u3046\u4E00\u5EA6\u8981\u308A\u304F\u3060\u3055\u3044\u3002", "error", 8000);
        resetButton();
      }
    });
  };

  function resetButton() {
    var btn = document.getElementById("mercari-sync-btn");
    if (btn) {
      btn.classList.remove("syncing");
      btn.innerHTML = '<span class="icon">\uD83D\uDCE6</span> <span>\u8CAFD\u540C\u671F</span>';
    }
  }

  // ── SPA-aware: inject immediately + retry on content ──
  // Inject right away — button works even before content loads
  setTimeout(createUI, 1000);

  // Also watch for content changes (SPA navigation)
  try {
    var observer = new MutationObserver(function () {
      if (!document.getElementById("mercari-sync-fab")) {
        createUI();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  } catch (e) {
    console.log("[Mercari Sync] MutationObserver not available");
  }

})();
