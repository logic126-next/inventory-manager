// 在 Chrome Console 里运行（在 https://jp.mercari.com/mypage/inventory 页面）
// 提取所有持ち物（库存）数据并输出 JSON

(function() {
  const items = [];
  
  // Get all text content and parse it
  const bodyText = document.body.innerText;
  
  // Split by price pattern to extract items
  // Pattern: name followed by ¥price followed by action text
  const lines = bodyText.split('\n').map(l => l.trim()).filter(l => l);
  
  let currentItem = null;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    // Check if this line contains a price
    const priceMatch = line.match(/¥([\d,]+)/);
    if (priceMatch) {
      const priceStr = priceMatch[1].replace(/,/g, '');
      const price = parseInt(priceStr);
      
      // The previous lines (up to 3) should be the item name
      let name = '';
      for (let j = i - 1; j >= Math.max(0, i - 3); j--) {
        const prevLine = lines[j];
        // Skip non-name lines
        if (prevLine.includes('出品する') || prevLine.includes('出品中') || prevLine.includes('¥')) {
          break;
        }
        name = prevLine + ' ' + name;
      }
      name = name.trim();
      
      // Get status text from next lines
      let statusText = '';
      for (let j = i + 1; j <= Math.min(lines.length - 1, i + 3); j++) {
        const nextLine = lines[j];
        if (nextLine.includes('出品する') || nextLine.includes('出品中') || nextLine.includes('出品済み')) {
          statusText = nextLine;
          break;
        }
      }
      
      // Filter out non-item entries
      if (name.length < 3) continue;
      if (name.includes('出品') || name.includes('購入') || name.includes('設定') || 
          name.includes('ヘルプ') || name.includes('ガイド') || name.includes('利用規約') ||
          name.includes('プライバシー') || name.includes('メルカリShops')) continue;
      if (name.includes('コンテンツ') || name.includes('シェア') || name.includes('リンク')) continue;
      
      items.push({
        name: name,
        price: price,
        status: statusText || 'unknown',
      });
    }
  }
  
  console.log('Found', items.length, 'items');
  console.log('Copy this JSON:');
  console.log(JSON.stringify(items, null, 2));
  
  // Also save to file via download
  const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'mercari_owned_items.json';
  a.click();
  URL.revokeObjectURL(url);
  
  console.log('Downloaded as mercari_owned_items.json');
})();
