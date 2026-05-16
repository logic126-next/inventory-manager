// Quick test of the bookmarklet code generation
const BOOKMARKLET_SERVER = 'http://192.168.1.203:8080';

function generateBookmarkletCode(serverUrl) {
  var s=encodeURIComponent;
  var c='';
  c+='var api="'+(serverUrl||BOOKMARKLET_SERVER)+'"+"/api/scrapers/mercari/owned/sync";';
  c+='if(!location.hostname.includes("mercari.com")){alert("Mercari.jpのページで実行してください");throw 0;}';
  c+='var ov=document.createElement("div");ov.id="ms-ov";';
  c+='ov.style.cssText="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.85);z-index:2147483647;display:flex;align-items:center;justify-content:center;font-family:-apple-system,sans-serif;color:#e6edf3";';
  c+='ov.innerHTML="<div style=text-align:center;padding:40px><div id=ms-i style="font-size:48px;margin-bottom:16px">🔄</div><div id=ms-t style="font-size:18px;font-weight:600">読み込み中...</div><div id=ms-s style="font-size:14px;color:#8b949e;margin-top:8px"></div></div>";';
  c+='document.body.appendChild(ov);';
  c+='var mt=document.getElementById("ms-t"),ms=document.getElementById("ms-s"),mi=document.getElementById("ms-i");';
  c+='function st(a,b,d){mi.textContent=a;mt.textContent=b;if(d)ms.textContent=d;}';
  c+='var items=[],seen=new Set();';
  c+='function ex(){items=[];seen.clear();var al=document.querySelectorAll(\'a[href*="/inventory/m"]\');';
  c+='for(var i=0;i<al.length;i++){var ln=al[i],h=ln.getAttribute("href");if(!h||seen.has(h))continue;';
  c+='var m=h.match(/\\/inventory\\/m(\\d+)/);if(!m)continue;var id="m"+m[1];seen.add(h);';
  c+='var cd=ln.closest("[data-item-id],article,div[class]");if(!cd)cd=ln.parentElement;';
  c+='var nm="",pr=0,st2="",im="";';
  c+='var ne=cd.querySelector(\'[class*="title"],[class*="Title"],h3,h4,p\');if(ne)nm=ne.textContent.trim();';
  c+='if(!nm){var ts=cd.querySelectorAll("*");for(var t=0;t<ts.length&&t<15;t++){if(ts[t].children.length===0){var n=ts[t].textContent.trim();if(n.length>3&&n.length<100&&!n.includes("¥")){nm=n;break;}}}}';
  c+='var pe=cd.querySelector(\'[class*="price"],[class*="Price"]\');if(pe){var pt=pe.textContent.trim(),pm=pt.match(/¥\\s*(\\d[,\\d]*)/);if(pm)pr=parseInt(pm[1].replace(/,/g,""));}';
  c+='if(!pr){var ap=cd.querySelectorAll("*");for(var pi=0;pi<ap.length&&pi<25;pi++){var p2=ap[pi].textContent.trim(),p3=p2.match(/^(¥\\s*)?(\\d[,\\d]+)$/);if(p3&&parseInt(p3[2].replace(/,/g,""))>0){pr=parseInt(p3[2].replace(/,/g,""));break;}}}';
  c+='var se=cd.querySelector(\'[class*="status"],[class*="Status"]\');if(se)st2=se.textContent.trim();';
  c+='if(!st2){var ss=["出品中","出品停止","在庫切れ","販売中"];for(var si=0;si<ss.length;si++){if(cd.textContent.includes(ss[si])){st2=ss[si];break;}}}';
  c+='var ie=cd.querySelector("img");if(ie)im=ie.getAttribute("src")||ie.getAttribute("data-src")||"";';
  c+='var fu="https://jp.mercari.com/inventory/"+id;if(nm.length>=2&&pr>0)items.push({name:nm,price:pr,status:st2,url:fu,image_url:im});}}';
  c+='}';
  c+='(async function(){try{';
  c+='st("⏳","Mercariの商品を読み込み中...","ページが読み込まれるのを待っています");';
  c+='var w=0;while(w<30){ex();if(items.length>0)break;await new Promise(function(r){setTimeout(r,500);});w++;}';
  c+='if(!items.length){st("⚠️","商品が見つかりません","Mercariの持ち物ページで実行してください");setTimeout(function(){document.body.removeChild(ov);},3000);return;}';
  c+='st("🔄","全商品の読み込み中...",""+items.length+"件取得済み");';
  c+='var lc=0,sn=0;await new Promise(function(res){function ds(){ex();var cc=items.length;if(cc===lc&&sn>3||sn>=50){res();return;}if(lc>0&&cc===lc){setTimeout(ds,500);return;}';
  c+='lc=cc;sn++;st("🔄","商品を読み込み中...",""+items.length+"件取得 ("+sn+")");';
  c+='window.scrollTo(0,Math.random()*window.innerHeight+window.scrollY);setTimeout(ds,400);}ds();});';
  c+='var tot=items.length;st("📤",tot+"件の商品を同期中...","Inventory Managerに送信しています");';
  c+='try{var rp=await fetch(api,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:items})});';
  c+='if(rp.ok){var r=await rp.json();st("✅",tot+"件同期完了！","新規:"+r.created+" 更新:"+r.updated+" スキップ:"+r.skipped);mt.style.color="#3fb950";}';
  c+='else{throw"HTTP "+rp.status;}}catch(fe){';
  c+='try{var f=document.createElement("form");f.method="POST";f.action=api;f.target="_blank";f.style.display="none";';
  c+='var t=document.createElement("textarea");t.name="data";t.value=JSON.stringify({items:items});f.appendChild(t);document.body.appendChild(f);f.submit();document.body.removeChild(f);';
  c+='st("🔗","新しいタブで処理中...","結果は新しいタブで確認できます");mt.style.color="#58a6ff";}catch(x){';
  c+='try{await navigator.clipboard.writeText(JSON.stringify({items:items}));st("📋","クリップボードにコピーしました","Inventory ManagerのJSONインポートから貼り付けてください");mt.style.color="#d29922";}catch(y){';
  c+='st("❌","送信エラー: "+fe,"再度お試しください");mt.style.color="#f85149";}}}';
  c+='setTimeout(function(){document.body.removeChild(ov);},r?5000:8000);}catch(e){st("❌","エラー: "+e.message,"");mt.style.color="#f85149";setTimeout(function(){document.body.removeChild(ov);},5000);}})();';

  return 'javascript:' + s(c) + ';void(0);';
}

// Generate and decode to verify the code is valid
var bmUrl = generateBookmarkletCode('http://192.168.1.203:8080');
console.log('Bookmarklet URL length:', bmUrl.length);
console.log('URL starts with javascript:', bmUrl.startsWith('javascript:'));

// Decode and verify the code
var decoded = decodeURIComponent(bmUrl.replace('javascript:', '').replace(';void(0);', ''));
console.log('\n--- Decoded bookmarklet code (first 500 chars) ---');
console.log(decoded.substring(0, 500));
console.log('\n--- Testing regex parsing ---');

// Test that the decoded code can be evaluated (syntax check)
try {
  new Function(decoded);
  console.log('✅ Syntax is valid!');
} catch(e) {
  console.error('❌ Syntax error:', e.message);
  // Show context around the error
  var lineNum = e.message.match(/line (\d+)/);
  if(lineNum) console.error('Error at line:', lineNum[1]);
}
