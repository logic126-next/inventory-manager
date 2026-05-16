// Mercari 持ち物ページ DOM デバッグ用ブックマークレット
javascript:(async function() {
'use strict';

const overlay = document.createElement('div');
Object.assign(overlay.style, {
  position:'fixed', top:0, left:0, right:0, bottom:0,
  background:'rgba(0,0,0,0.85)', zIndex:999999,
  display:'flex', alignItems:'center', justifyContent:'center',
  fontFamily:'monospace', color:'#fff', fontSize:'12px'
});
document.body.appendChild(overlay);

const box = document.createElement('div');
Object.assign(box.style, {
  background:'#1a1a2e', padding:24, borderRadius:12, maxWidth:800, width:'90%',
  maxHeight:'80vh', overflowY:'auto', whiteSpace:'pre-wrap'
});
overlay.appendChild(box);

let output = '🔍 Mercari DOM デバッグ\n\n';

// 1. URL
output += `📍 URL: ${window.location.href}\n\n`;

// 2. タイトル
output += `📄 タイトル: ${document.title}\n\n`;

// 3. 全リンク数
const allLinks = document.querySelectorAll('a');
output += `🔗 全リンク数: ${allLinks.length}\n\n`;

// 4. /items/ を含むリンク
const itemLinks = document.querySelectorAll('a[href*="/items/"]');
output += `📦 /items/ リンク数: ${itemLinks.length}\n`;
if (itemLinks.length > 0 && itemLinks.length < 10) {
  for (const link of itemLinks) {
    output += `  - ${link.href}\n`;
    output += `    クラス: ${(link.className || '').substring(0, 100)}\n`;
    output += `    テキスト: ${(link.textContent || '').trim().substring(0, 80)}\n`;
  }
} else if (itemLinks.length >= 10) {
  output += `  最初の3件:\n`;
  for (let i = 0; i < 3; i++) {
    output += `  - ${itemLinks[i].href}\n`;
  }
}
output += '\n';

// 5. data-testid 属性
const testIds = document.querySelectorAll('[data-testid]');
output += `🧪 data-testid 要素数: ${testIds.length}\n`;
if (testIds.length > 0) {
  const idSet = new Set();
  for (const el of testIds) idSet.add(el.getAttribute('data-testid'));
  output += `  種類: ${Array.from(idSet).join(', ')}\n`;
}
output += '\n';

// 6. アイテムカード関連のクラス
const allClasses = new Set();
for (const link of itemLinks) {
  let parent = link.parentElement;
  for (let depth = 0; depth < 3 && parent; depth++) {
    if (parent.className) {
      const classes = typeof parent.className === 'string' ? parent.className.split(' ') : [];
      for (const cls of classes) allClasses.add(cls);
    }
    parent = parent.parentElement;
  }
}
output += `🏷️ アイテム関連クラス (${allClasses.size}種):\n`;
output += Array.from(allClasses).slice(0, 20).join(', ') + '\n\n';

// 7. CSS クラス（b89k4h など）
const mercariItems = document.querySelectorAll('[class*="b89k4h"], [class*="175oi2r"]');
output += `🎯 Mercari クラス: ${mercariItems.length}\n\n`;

// 8. 最初のアイテムの詳細（DOM ツリー）
if (itemLinks.length > 0) {
  output += '📋 最初のアイテム DOM:\n';
  const first = itemLinks[0];
  let parent = first;
  for (let i = 0; i < 5; i++) {
    const tag = parent.tagName;
    const cls = (parent.className || '').toString().substring(0, 80);
    const txt = (parent.textContent || '').trim().substring(0, 60);
    output += `  ${tag} class="${cls}"\n`;
    if (txt && i < 3) output += `    text: "${txt}"\n`;
    parent = parent.parentElement;
    if (!parent) break;
  }
}

// 9. ボタン（出品停止・在庫切れなど）
const buttons = document.querySelectorAll('button, [role="button"]');
output += `\n🔘 ボタン数: ${buttons.length}\n`;

box.textContent = output;

// Close button
const closeBtn = document.createElement('button');
closeBtn.textContent = '閉じる';
Object.assign(closeBtn.style, {
  marginTop: 16, padding: '8px 16px', background: '#4CAF50', color: '#fff',
  border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: '14px'
});
closeBtn.onclick = () => overlay.remove();
box.appendChild(closeBtn);

})();