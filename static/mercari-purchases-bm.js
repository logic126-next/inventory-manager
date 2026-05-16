(function() {
  'use strict';

  // Get server URL from global variable set by bookmarklet, or fall back to script src
  var serverUrl = window.__MERCARI_SERVER_URL || '';
  if (!serverUrl) {
    var scripts = document.getElementsByTagName('script');
    for (var i = scripts.length - 1; i >= 0; i--) {
      if (scripts[i].src && scripts[i].src.indexOf('mercari-purchases-bm.js') >= 0) {
        serverUrl = scripts[i].src.replace(/\/static\/mercari-purchases-bm\.js(\?.*)?$/, '');
        break;
      }
    }
  }

  var api = serverUrl + '/api/scrapers/mercari/purchases/sync';

  if (!location.hostname.includes('mercari.com')) {
    alert('Mercari.jpのページで実行してください');
    return;
  }

  // Create overlay
  var ov = document.createElement('div');
  ov.id = 'mercari-purchases-overlay';
  ov.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.85);z-index:2147483647;display:flex;align-items:center;justify-content:center;font-family:-apple-system,sans-serif;color:#e6edf3';
  ov.innerHTML = '<div style="text-align:center;padding:40px"><div id="ms-icon" style="font-size:48px;margin-bottom:16px">🛒</div><div id="ms-text" style="font-size:18px;font-weight:600">読み込み中...</div><div id="ms-sub" style="font-size:14px;color:#8b949e;margin-top:8px"></div></div>';
  document.body.appendChild(ov);

  var msText = document.getElementById('ms-text');
  var msSub = document.getElementById('ms-sub');
  var msIcon = document.getElementById('ms-icon');

  function setStatus(icon, text, sub) {
    msIcon.textContent = icon;
    msText.textContent = text;
    if (sub) msSub.textContent = sub;
  }

  var items = [];
  var seen = new Set();

  function parseDate(text) {
    var m = text.match(/(\d{4})年(\d{1,2})月(\d{1,2})日/);
    if (m) return m[1] + '-' + m[2].padStart(2, '0') + '-' + m[3].padStart(2, '0');
    m = text.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
    if (m) return m[1] + '-' + m[2].padStart(2, '0') + '-' + m[3].padStart(2, '0');
    m = text.match(/(\d{1,2})月(\d{1,2})日/);
    if (m) {
      var year = new Date().getFullYear();
      return year + '-' + m[1].padStart(2, '0') + '-' + m[2].padStart(2, '0');
    }
    return null;
  }

  function extractItems() {
    items = [];
    seen.clear();

    var allImgs = document.querySelectorAll('img');
    for (var i = 0; i < allImgs.length; i++) {
      var img = allImgs[i];
      var src = img.getAttribute('src') || img.getAttribute('data-src') || img.getAttribute('data-lazy-src') || '';
      if (!src || src.length < 10) continue;

      var parent = img.closest('div');
      if (!parent || parent.textContent.trim().length < 10) continue;

      var ct = parent.textContent.trim();

      // Extract name
      var name = '';
      var txts = parent.querySelectorAll('*');
      for (var t = 0; t < txts.length && t < 20; t++) {
        if (txts[t].children.length === 0) {
          var n = txts[t].textContent.trim();
          if (n.length > 3 && n.length < 100 && !n.includes('\u00a5') && !n.match(/^[0-9,]+$/) && !n.match(/^[0-9\/年月日]+$/)) {
            name = n;
            break;
          }
        }
      }

      if (!name || seen.has(name)) continue;
      seen.add(name);

      // Extract price
      var price = 0;
      var pm = ct.match(/\u00a5\s*(\d[\d,]*)/g);
      if (pm) {
        for (var pi = 0; pi < pm.length; pi++) {
          var pv = parseInt(pm[pi].replace(/[^0-9]/g, ''));
          if (pv >= 100 && pv <= 9999999) {
            price = pv;
            break;
          }
        }
      }

      // Extract purchase date
      var purchaseDate = parseDate(ct);

      // Extract link
      var link = parent.querySelector('a');
      var fullUrl = '';
      if (link) {
        var href = link.getAttribute('href');
        if (href) fullUrl = href.startsWith('https://') ? href : 'https://jp.mercari.com' + href;
      }

      items.push({
        name: name,
        price: price,
        status: '',
        url: fullUrl,
        image_url: src,
        purchase_date: purchaseDate
      });
    }
  }

  function scrollLoad() {
    return new Promise(function(resolve) {
      var done = false;
      var lastCount = 0;
      var scrollNum = 0;

      function doScroll() {
        if (done) return;
        extractItems();
        var curCount = items.length;

        if (curCount === lastCount && scrollNum > 3) { done = true; resolve(); return; }
        if (scrollNum >= 30) { done = true; resolve(); return; }
        if (lastCount > 0 && curCount === lastCount) { setTimeout(doScroll, 500); return; }

        lastCount = curCount;
        scrollNum++;
        setStatus('\ud83d\udd04', '商品を読み込み中...', '' + items.length + '件取得');

        window.scrollBy({ top: 300, left: 0, behavior: 'smooth' });
        setTimeout(doScroll, 800);
      }
      doScroll();
    });
  }

  setStatus('\ud83d\udccb', '商品を読み込み中...');

  scrollLoad().then(function() {
    extractItems();

    if (items.length === 0) {
      setStatus('\u26a0\ufe0f', '商品が見つかりませんでした',
        'img: ' + document.querySelectorAll('img').length + '件 / server: ' + serverUrl);
      setTimeout(function() { document.body.removeChild(ov); }, 8000);
      return;
    }

    setStatus('\ud83d\udce4', '' + items.length + '件をサーバーに送信中...');
    msSub.textContent = 'API: ' + api;

    var xhr = new XMLHttpRequest();
    xhr.open('POST', api, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.timeout = 30000;
    xhr.onreadystatechange = function() {
      if (xhr.readyState !== 4) return;
      if (xhr.status === 0) {
        setStatus('\u274c', 'ネットワークエラー', 'API: ' + api);
        setTimeout(function() { document.body.removeChild(ov); }, 8000);
        return;
      }
      try {
        var resp = JSON.parse(xhr.responseText);
        if (resp.detail) {
          setStatus('\u274c', 'APIエラー (' + xhr.status + ')', resp.detail + '\n' + api);
          setTimeout(function() { document.body.removeChild(ov); }, 10000);
          return;
        }
        if (resp.error) {
          setStatus('\u274c', 'エラー', resp.error);
          setTimeout(function() { document.body.removeChild(ov); }, 8000);
          return;
        }
        setStatus('\u2705', '同期完了！',
          (resp.created || 0) + '件新規 / ' + (resp.updated || 0) + '件更新 / ' + (resp.skipped || 0) + '件スキップ');
        setTimeout(function() { document.body.removeChild(ov); }, 5000);
      } catch (e) {
        setStatus('\u274c', 'エラー', '' + e.message + '\n' + xhr.responseText.substring(0, 200));
        setTimeout(function() { document.body.removeChild(ov); }, 10000);
      }
    };
    xhr.onerror = function() {
      setStatus('\u274c', 'ネットワークエラー', 'API: ' + api);
      setTimeout(function() { document.body.removeChild(ov); }, 8000);
    };
    xhr.ontimeout = function() {
      setStatus('\u23f1\ufe0f', 'タイムアウト', 'API: ' + api);
      setTimeout(function() { document.body.removeChild(ov); }, 8000);
    };
    xhr.send(JSON.stringify({ items: items }));
  });

})();
