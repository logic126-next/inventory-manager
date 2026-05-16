// Mercari 持ち物同期ブックマークレット（v4 - ページネーション対応）
// 使い方: このファイルをドラッグしてブックマークバーに配置
// https://jp.mercari.com/mypage/inventory で実行

javascript:(function() {
'use strict';

const IM_URL = 'IM_URL_PLACEHOLDER';

// デバッグ用オーバーレイ
var ov = document.createElement('div');
ov.id = 'ms-overlay';
ov.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.9);z-index:2147483647;display:flex;align-items:center;justify-content:center;font-family:-apple-system,sans-serif;color:#e6edf3;overflow-y:auto';
ov.innerHTML = '<div style="text-align:center;padding:40px;max-width:600px;margin:0 auto">' +
  '<div id="ms-icon" style="font-size:48px;margin-bottom:16px">🔄</div>' +
  '<div id="ms-title" style="font-size:18px;font-weight:600;margin-bottom:8px">同期中...</div>' +
  '<div id="ms-status" style="font-size:14px;color:#8b949e;margin-bottom:16px"></div>' +
  '<pre id="ms-debug" style="text-align:left;font-size:12px;background:#1a1d20;padding:16px;border-radius:8px;overflow-x:auto;max-height:300px;white-space:pre-wrap;word-break:break-all"></pre>' +
  '</div>';
document.body.appendChild(ov);

var debug = document.getElementById('ms-debug');
var title = document.getElementById('ms-title');
var status = document.getElementById('ms-status');
var icon = document.getElementById('ms-icon');

function log(msg) {
  debug.textContent += msg + '\n';
}

function updateState(i, t, s) {
  if (i) icon.textContent = i;
  if (t) title.textContent = t;
  if (s) status.textContent = s;
}

// Mercari ページか確認
if (!window.location.hostname.includes('mercari.com')) {
  updateState('⚠️', 'Mercari のページではありません');
  setTimeout(function() { document.body.removeChild(ov); }, 3000);
  return;
}

log('🔍 Mercari ブックマークレット v4（ページネーション対応）');

// key: inventory ID, value: {name, price, image_url}
var itemsMap = {};

// 単一ページから商品データを抽出
function extractPage() {
  var pageItems = {};
  var allLinks = document.querySelectorAll('a[href*="/inventory/"]');
  
  for (var l = 0; l < allLinks.length; l++) {
    var link = allLinks[l];
    var href = link.getAttribute('href') || '';
    
    // ID を抽出
    var parts = href.split('/');
    var id = parts[parts.length - 1];
    if (!id || id.length < 6) continue;
    
    // 同一 ID はスキップ
    if (pageItems[id]) continue;
    
    // LI 要素を探す（商品カードのコンテナ）
    var li = link;
    for (var d = 0; d < 5; d++) {
      if (!li.parentElement) break;
      li = li.parentElement;
      if (li.tagName === 'LI') break;
    }
    
    var card = li && li.tagName === 'LI' ? li : link.parentElement;
    if (!card) continue;
    
    var name = '';
    var price = 0;
    var image_url = '';
    
    try {
      var linkText = link.textContent.trim();
      if (linkText.length > 2 && !linkText.includes('持ち物一覧') && !linkText.includes('出品する')) {
        name = linkText;
      }
      
      var cardText = card.textContent || '';
      var priceMatch = cardText.match(/¥\s*(\d[\d,]+)/);
      if (priceMatch) {
        price = parseInt(priceMatch[1].replace(/,/g, ''));
      }
      
      // 画像: DOM → ID から推測
      var allImgs = card.querySelectorAll('img');
      for (var i = 0; i < allImgs.length; i++) {
        var imgEl = allImgs[i];
        var src = imgEl.getAttribute('src') || '';
        var dataSrc = imgEl.getAttribute('data-src') || '';
        var dataOriginal = imgEl.getAttribute('data-original') || '';
        if (src && src.includes('mercdn.net')) { image_url = src; break; }
        if (dataSrc && dataSrc.includes('mercdn.net')) { image_url = dataSrc; break; }
        if (dataOriginal && dataOriginal.includes('mercdn.net')) { image_url = dataOriginal; break; }
      }
      if (!image_url && id) {
        image_url = 'https://static.mercdn.net/photos/' + id + '_1.jpg';
      }
    } catch(e) {}
    
    if (name.length >= 2 && price > 0) {
      pageItems[id] = {
        name: name,
        price: price,
        status: '在庫',
        url: 'https://jp.mercari.com/inventory/' + id,
        image_url: image_url
      };
    }
  }
  
  return pageItems;
}

// 「次ページ」ボタンを探す
function findNextPageButton() {
  // デバッグ: 利用可能な候補をすべて表示
  var candidates = [];
  
  // 1. 「次ページ」「次へ」「Next」を含む a タグ
  var allLinks = document.querySelectorAll('a');
  for (var i = 0; i < allLinks.length; i++) {
    var text = allLinks[i].textContent.trim();
    if (text === '次ページ' || text === '次へ' || text === 'Next') {
      candidates.push({ type: 'text_match', text: text, el: allLinks[i] });
    }
  }
  
  // 2. aria-label
  var ariaNext = document.querySelector('a[aria-label="Next"], a[aria-label="次ページ"]');
  if (ariaNext) candidates.push({ type: 'aria', text: ariaNext.getAttribute('aria-label'), el: ariaNext });
  
  // 3. button 要素
  var buttons = document.querySelectorAll('button');
  for (var b = 0; b < buttons.length; b++) {
    var bText = buttons[b].textContent.trim();
    if (bText === '次ページ' || bText === '次へ' || bText === 'Next' || bText.includes('›') || bText.includes('→')) {
      candidates.push({ type: 'button', text: bText, el: buttons[b] });
    }
  }
  
  // 4. ページネーション内の数字リンク
  var paginations = document.querySelectorAll('.pagination, [class*="pagination"], nav[role="navigation"], [class*="paginat"]');
  for (var p = 0; p < paginations.length; p++) {
    var links = paginations[p].querySelectorAll('a, button');
    for (var j = 0; j < links.length; j++) {
      var t = links[j].textContent.trim();
      if (/\d+/.test(t) && t.length <= 3) {
        candidates.push({ type: 'page_num', text: t, el: links[j] });
      }
    }
  }
  
  // 最初の有効な候補を返す（disabled 除外）
  for (var k = 0; k < candidates.length; k++) {
    var el = candidates[k].el;
    if (!el.classList.contains('disabled') && !el.disabled) {
      return el;
    }
  }
  
  return null;
}

// 現在のページ数を推測
function getCurrentPage() {
  var urlParams = new URLSearchParams(window.location.search);
  var page = urlParams.get('page');
  if (page) return parseInt(page);
  return 1;
}

// 待機関数
function sleep(ms) {
  return new Promise(function(resolve) { setTimeout(resolve, ms); });
}

// ページ読み込み完了を待つ
// Mercari は SPA なので、商品カードが更新されるのを待つ
function waitForPageLoad() {
  return new Promise(function(resolve) {
    // まず少し待つ（SPA レンダリング開始まで）
    setTimeout(function() {
      var initialIds = getCurrentItemIds();
      var attempts = 0;
      var check = function() {
        attempts++;
        var currentIds = getCurrentItemIds();
        // 商品IDが変化したら読み込み完了
        if (currentIds.length > 0 && currentIds.join(',') !== initialIds.join(',')) {
          resolve();
        } else if (attempts > 20) { // 最大2秒
          resolve();
        } else {
          setTimeout(check, 100);
        }
      };
      check();
    }, 500);
  });
}

// 現在表示中の商品IDを取得
function getCurrentItemIds() {
  var ids = [];
  var links = document.querySelectorAll('a[href*="/inventory/"]');
  for (var i = 0; i < links.length; i++) {
    var href = links[i].getAttribute('href') || '';
    var parts = href.split('/');
    var id = parts[parts.length - 1];
    if (id && id.length >= 6) ids.push(id);
  }
  // 重複除去
  var unique = {};
  for (var j = 0; j < ids.length; j++) {
    unique[ids[j]] = true;
  }
  return Object.keys(unique);
}

// 全ページを巡回してデータを収集
async function collectAllPages() {
  var pageNum = 0;
  
  while (true) {
    pageNum++;
    var currentPage = getCurrentPage();
    log('📄 ページ ' + pageNum + ' (URL: page=' + currentPage + ') 読み込み中...');
    
    // 1ページ目の場合は即抽出、それ以外は待機
    if (pageNum > 1) {
      await waitForPageLoad();
    }
    
    var pageItems = extractPage();
    var newCount = 0;
    for (var id in pageItems) {
      if (!itemsMap[id]) {
        itemsMap[id] = pageItems[id];
        newCount++;
      }
    }
    log('  → 新規: ' + newCount + '件 (累計: ' + Object.keys(itemsMap).length + '件)');
    
    // 次ページがあるか確認
    var nextBtn = findNextPageButton();
    if (!nextBtn) {
      log('📄 次ページボタンなし - 収集完了');
      break;
    }
    
    updateState('🔄', 'ページ ' + pageNum + ' 完了...', '累計: ' + Object.keys(itemsMap).length + '件');
    log('  → 次ページ...');
    
    // 次ページをクリック
    nextBtn.click();
    await sleep(2000); // SPA 読み込み待機
  }
  
  return pageNum;
}

// 収集開始
updateState('🔄', '全ページ読み込み中...', '持ち物データを収集しています');
log('📦 全ページ収集開始...');

collectAllPages().then(function(totalPages) {
  // Map → Array
  var items = [];
  for (var key in itemsMap) {
    items.push(itemsMap[key]);
  }
  
  var withImage = items.filter(function(x){return x.image_url.length > 0}).length;
  log('');
  log('✅ 収集完了: ' + totalPages + 'ページ / ' + items.length + '件 (画像あり: ' + withImage + '件)');
  
  if (items.length === 0) {
    updateState('❌', '商品データが抽出できませんでした');
    setTimeout(function() { document.body.removeChild(ov); }, 3000);
    return;
  }
  
  // Inventory Manager に送信
  updateState('📤', items.length + '件を送信中...', 'Inventory Manager に接続中');
  log('📡 API: ' + IM_URL + '/api/scrapers/mercari/owned/sync');
  
  var data = JSON.stringify({ items: items });
  
  var api_key = 'IM_API_KEY_PLACEHOLDER';
  var headers = { 'Content-Type': 'application/json' };
  if (api_key) headers['X-API-Key'] = api_key;

  fetch(IM_URL + '/api/scrapers/mercari/owned/sync', {
    method: 'POST',
    headers: headers,
    body: data
  })
  .then(function(response) {
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  })
  .then(function(result) {
    updateState('✅', '同期完了！', 'ページ: ' + totalPages + ' | 新規: ' + result.created + ' 更新: ' + result.updated + ' スキップ: ' + result.skipped);
    log('✅ API 応答: ' + JSON.stringify(result));
    setTimeout(function() { document.body.removeChild(ov); }, 5000);
  })
  .catch(function(error) {
    log('❌ fetch エラー: ' + error.message);
    updateState('⚠️', '送信エラー', 'Inventory Manager に接続できません');
    
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(data).then(function() {
        updateState('📋', 'クリップボードにコピーしました', 'Inventory Manager の JSON インポートから貼り付けてください');
        log('✅ クリップボードにコピー');
      }).catch(function() {
        updateState('❌', '送信失敗', '再度お試しください');
      });
    } else {
      updateState('❌', '送信失敗');
    }
    setTimeout(function() { document.body.removeChild(ov); }, 8000);
  });
}).catch(function(error) {
  log('❌ 収集エラー: ' + error.message);
  updateState('❌', 'エラーが発生しました');
  setTimeout(function() { document.body.removeChild(ov); }, 5000);
});

})();
