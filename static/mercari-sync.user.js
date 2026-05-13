// ==UserScript==
// @name         Mercari 持ち物 → Inventory Manager 同期
// @namespace    https://github.com/logic126/inventory-manager
// @version      1.2.0
// @description  Mercari 持ち物一覧のアイテムをワンクリックで Inventory Manager に同期
// @match        *://jp.mercari.com/mypage/inventory*
// @match        *://jp.mercari.com/mypage/inventory/*
// @grant        none
// @run-at       document-idle
// @author       logic126
// ==/UserScript==

(function () {
  "use strict";

  // ── Configuration ──────────────────────────────────────
  // Change this to your Inventory Manager URL
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

    #mercari-sync-btn .icon {
      font-size: 18px !important;
    }

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

    #mercari-sync-toast.success {
      background: #0d1117 !important;
      color: #3fb950 !important;
      border: 1px solid #3fb950 !important;
    }

    #mercari-sync-toast.error {
      background: #0d1117 !important;
      color: #f85149 !important;
      border: 1px solid #f85149 !important;
    }

    #mercari-sync-toast.info {
      background: #0d1117 !important;
      color: #58a6ff !important;
      border: 1px solid #58a6ff !important;
    }

    @keyframes mercari-sync-slide-in {
      from { opacity: 0; transform: translateY(10px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 600px) {
      #mercari-sync-fab {
        bottom: 16px !important;
        right: 16px !important;
      }
      #mercari-sync-btn {
        padding: 10px 14px !important;
        font-size: 13px !important;
      }
      #mercari-sync-toast {
        bottom: 70px !important;
        right: 12px !important;
        left: 12px !important;
        max-width: none !important;
      }
    }
  `;

  // ── Extraction Logic ──────────────────────────────────
  function extractItems() {
    const items = [];

    // Collect all item links in document order
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

    // Parse body text for the 4-line pattern
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
    // Inject styles
    const styleEl = document.createElement("style");
    styleEl.textContent = STYLES;
    document.head.appendChild(styleEl);

    // Container
    const container = document.createElement("div");
    container.id = "mercari-sync-fab";

    // Button
    const btn = document.createElement("button");
    btn.id = "mercari-sync-btn";
    btn.innerHTML = '<span class="icon">📦</span> <span>在庫同期</span>';
    btn.addEventListener("click", handleSync);

    container.appendChild(btn);
    document.body.appendChild(container);
  }

  // ── Toast Notification ────────────────────────────────
  function showToast(message, type = "info", duration = 5000) {
    // Remove existing toasts
    const existing = document.getElementById("mercari-sync-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.id = "mercari-sync-toast";
    toast.className = type;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.transition = "opacity 0.3s ease";
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // ── Sync Handler ──────────────────────────────────────
  async function handleSync() {
    const btn = document.getElementById("mercari-sync-btn");
    if (!btn) return;

    // Prevent double-click
    btn.classList.add("syncing");
    btn.innerHTML = '<span class="icon">⏳</span> <span>同期中...</span>';

    try {
      // Extract items
      const items = extractItems();

      if (items.length === 0) {
        showToast("⚠️ 商品が見つかりませんでした。持ち物一覧ページで再試行してください。", "error");
        resetButton();
        return;
      }

      showToast(`📡 ${items.length} 件の商品を同期中...`, "info", 3000);

      // POST to API
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        mode: "cors",
        body: JSON.stringify({ items }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      const result = await response.json();

      // Build result message
      const parts = [];
      if (result.created > 0) parts.push(`✅ ${result.created} 件追加`);
      if (result.updated > 0) parts.push(`🔄 ${result.updated} 件更新`);
      if (result.skipped > 0) parts.push(`⏭ ${result.skipped} 件スキップ`);

      const message = parts.join("  ") || "✅ 変更なし";
      showToast(message, "success", 6000);

      // Brief success animation on button
      btn.innerHTML = '<span class="icon">✅</span> <span>完了!</span>';
      setTimeout(resetButton, 2000);

    } catch (error) {
      console.error("[Mercari Sync] Error:", error);
      let errorMsg = "❌ 同期に失敗しました";

      if (error.message.includes("Failed to fetch") || error.message.includes("NetworkError")) {
        errorMsg += "\n🔧 Inventory Manager に接続できません。ネットワークを確認してください。";
      } else if (error.message.includes("CORS")) {
        errorMsg += "\n🔧 CORS エラー。Inventory Manager の設定を確認してください。";
      } else {
        errorMsg += `\n${error.message}`;
      }

      showToast(errorMsg, "error", 8000);
      resetButton();
    }
  }

  function resetButton() {
    const btn = document.getElementById("mercari-sync-btn");
    if (btn) {
      btn.classList.remove("syncing");
      btn.innerHTML = '<span class="icon">📦</span> <span>在庫同期</span>';
    }
  }

  // ── Wait for page load then inject UI ─────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      setTimeout(createUI, 1500); // Wait for SPA content to render
    });
  } else {
    setTimeout(createUI, 1500);
  }
})();
