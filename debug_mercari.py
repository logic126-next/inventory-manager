#!/usr/bin/env python3
"""Debug: Inspect Mercari inventory page DOM structure."""
import asyncio
from playwright.async_api import async_playwright

# Get fresh cookie from .env on Mac Mini
COOKIE = None

async def main():
    global COOKIE
    
    # Read cookie from local .env first, then try Mac Mini
    import subprocess
    try:
        result = subprocess.run(
            ['ssh', 'logic126@192.168.1.203', 
             "grep MERCARI_COOKIE ~/workspace/inventory-manager/.env | cut -d= -f2-"],
            capture_output=True, text=True, timeout=10
        )
        COOKIE = result.stdout.strip()
    except:
        pass
    
    if not COOKIE:
        print("No cookie found!")
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        )
        
        # Parse cookies
        cookies = []
        for part in COOKIE.split('; '):
            if '=' in part:
                name, value = part.split('=', 1)
                cookies.append({'name': name.strip(), 'value': value.strip(), 'domain': '.jp.mercari.com', 'path': '/'})
        
        await context.add_cookies(cookies)
        page = await context.new_page()
        
        print("Navigating to Mercari inventory...")
        resp = await page.goto('https://jp.mercari.com/mypage/inventory', wait_until='networkidle', timeout=30000)
        
        # Wait for content to load
        await page.wait_for_timeout(5000)
        
        print(f"Page title: {await page.title()}")
        print(f"URL: {page.url}")
        print(f"Status: {resp.status}")
        
        if 'login' in page.url.lower():
            print("❌ Redirected to login page - cookie expired!")
            await browser.close()
            return
        
        # Find all /inventory/ links
        inv_links = await page.query_selector_all('a[href*="/inventory/"]')
        print(f"\n/inventory/ links found: {len(inv_links)}")
        
        if len(inv_links) == 0:
            print("No inventory links found!")
            await browser.close()
            return
        
        # Analyze first 3 items in detail
        for idx in range(min(3, len(inv_links))):
            link = inv_links[idx]
            href = await link.get_attribute('href')
            
            print(f"\n{'='*60}")
            print(f"Item {idx+1}:")
            print(f"  Link href: {href}")
            
            # Get the full DOM path from link to body
            path = await link.evaluate("""el => {
                var path = [];
                var current = el;
                while (current && current !== document.body) {
                    path.unshift({
                        tag: current.tagName,
                        classes: (current.className || '').toString().substring(0, 150),
                        text: (current.textContent || '').trim().substring(0, 100),
                        id: current.id || ''
                    });
                    current = current.parentElement;
                }
                return path;
            }""")
            
            print(f"  DOM path ({len(path)} levels):")
            for i, p in enumerate(path[:8]):  # First 8 levels
                indent = "    " + "  " * i
                classes_short = p['classes'][:60] if p['classes'] else ''
                text_short = p['text'][:50].replace('\n', ' ')
                print(f"{indent}<{p['tag']} class=\"{classes_short}\" text=\"{text_short}\">")
            
            # Get the closest article/div that looks like a card
            card = await link.evaluate("""el => {
                var p = el;
                // Go up until we find a reasonable card container
                for (var d = 0; d < 10; d++) {
                    if (!p || !p.parentElement) break;
                    p = p.parentElement;
                    var classes = (p.className || '').toString();
                    // Look for common card-like patterns
                    if (classes.includes('Item') || classes.includes('Card') || 
                        classes.includes('item') || classes.includes('card') ||
                        classes.includes('List') || classes.includes('list')) {
                        return {
                            tag: p.tagName,
                            classes: classes.substring(0, 200),
                            text: (p.textContent || '').trim().substring(0, 300)
                        };
                    }
                }
                // Fallback: just go up 5 levels
                p = el;
                for (var d = 0; d < 5; d++) {
                    if (!p.parentElement) break;
                    p = p.parentElement;
                }
                return {
                    tag: p.tagName,
                    classes: (p.className || '').toString().substring(0, 200),
                    text: (p.textContent || '').trim().substring(0, 300)
                };
            }""")
            
            print(f"  Card element:")
            print(f"    tag: {card['tag']}")
            print(f"    classes: {card['classes'][:150]}")
            print(f"    text: {card['text'][:200]}")
        
        # Get the full page HTML structure (first 5000 chars)
        body_html = await page.evaluate("document.body.innerHTML.substring(0, 5000)")
        print(f"\n{'='*60}")
        print("Body HTML (first 5000 chars):")
        print(body_html[:3000])
        
        await browser.close()

asyncio.run(main())
