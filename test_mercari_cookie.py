#!/usr/bin/env python3
"""Test: Try various Mercari internal API patterns."""
import requests
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://jp.mercari.com/mypage/inventory",
    "Origin": "https://jp.mercari.com",
}

cookies = {"mercari-shd-uuid-lb": "364fddf1-af9f-4755-a18a-9aaa11906cf0", "country_code": "JP", "mercari-shd-uuid-lb-ts": "1778562813526", "_gcl_au": "1.1.1562913774.1778562814", "snexid": "bf6b97a3-8d1e-4869-a6b0-0252c307a76d", "snexid_r": "bf6b97a3-8d1e-4869-a6b0-0252c307a76d", "_twpid": "tw.1778562814049.253232827205949305", "__lt__cid": "5fb69cbe-b38a-486f-b037-b18b6fe21048", "_yjsu_yjad": "1778562814.6209a777-c673-4685-811e-6fd6281ddd88", "_fbp": "fb.1.1778562814256.93625545291454568", "_im_id.1019999": "904ea522b488357f.1778562814.", "_tt_enable_cookie": "1", "_ttp": "01KRD9NMD9FJR463JY7D714ZWE_.tt.1", "_pin_unauth": "dWlkPU9XVXpOV0ptTmpFdFpqUTJOQzAwWmpJeExUa3pPVFl0Tm1ZME5qZGtORGhtTjJGaw", "_ga_842NK55EJL": "GS2.1.s1778562821$o1$g0$t1778562838$j43$l0$h0", "_pubcid": "902a6f3c-5f51-4f16-85a7-36c81936fb48", "connectId": "{\"ttl\":86400000,\"lastUsed\":1778562840829,\"lastSynced\":1778562840829}", "_cc_id": "139a75c6180aabb149dcd74807595a61", "_gid": "GA1.2.1606033082.1778722096", "panoramaId_expiry": "1778808497030", "__gads": "ID=51ecaac86d09e494:T=1778562840:RT=1778722096:S=ALNI_MY7vs2HjFEPWAYrs7bFliYjyIWgHA", "__gpi": "UID=0000137ff5077138:T=1778562840:RT=1778722096:S=ALNI_MbDg4cotTTX5FhPeEVXRG1ZXU8MNQ", "__eoi": "ID=16316f652c7dd16b:T=1778562840:RT=1778722096:S=AA-Afjb8sUleyWmYCwkxH6SW8Sp4", "version": "canary", "__cf_bm": "CWuMdbTIPrb2X19JtLITm7aDH3lv8SKawGw_4rFpYbA-1778732432.6884203-1.0.1.1-s4umjOFVPW9Pu8h5GIEB1AR4szGv5F8U0CRm50G_q77vvnEVlZ_p4l6oqHFCA3XPETTRr723VQBbRZbfXmaZaf9JazyXYzrhBVE.fejDpQzWp6EZ4B4MoTcJri5IFWl_", "__lt__sid": "4e1f3dbe-32bcc8b1", "_gat_UA-50190241-1": "1", "_uetsid": "2ece2ab04f3411f1a247f3207bcb2a33", "_uetvid": "530d74c04dc111f1afa527ef589c25c9", "_ga": "GA1.1.1736787058.1778562814", "_ga_4NLR7T2LEN": "GS2.1.s1778733242$o3$g1$t1778733244$j58$l0$h0", "_im_ses.1019999": "1", "cto_bundle": "aaNyE182c0s5WXR5QkxhenF2SlZ2MmZXWlphOCUyQjJmRlBkanFYOCUyQkl6RXh3R3FtQWs3RzBnYnlOeDFOSnB4b1hVUEhUMXdFWmdOaERJJTJCSjZiWG1iJTJGbWVXdjhmR3AlMkJ6YnVTd1VleGtodHJSJTJCSmxYQVhSUWl2VHdkRnRNS1JtR1FtTG5zaw", "ttcsid_D40TROJC77U816ESBQ20": "1778733244570::b7R1zu4FKENN9nzUwlcF.4.1778733254577.1", "ttcsid": "1778733244570::yJHTZtz9RxPjRSWkzfZ9.4.1778733254613.0::1.-2093.0::0.0.0.0::0.0.0", "ttcsid_CL54EO3C77U29UCFMJ7G": "1778733244610::QFjVsDBOAhJSqwq9Drgh.4.1778733254615.1"}

# Try various API patterns - GET requests
get_urls = [
    "https://jp.mercari.com/api/v1/items",
    "https://jp.mercari.com/api/v1/inventory",
    "https://jp.mercari.com/api/v1/me/inventory",
    "https://jp.mercari.com/api/me",
    "https://jp.mercari.com/api/user/me",
]

for url in get_urls:
    print(f"\nGET {url}")
    try:
        r = requests.get(url, cookies=cookies, headers=headers, timeout=10)
        print(f"  Status: {r.status_code}, Length: {len(r.text)}")
        if r.status_code == 200 and len(r.text) < 500:
            try:
                data = r.json()
                print(f"  JSON: {json.dumps(data, ensure_ascii=False)[:300]}")
            except:
                print(f"  Text: {r.text[:200]}")
    except Exception as e:
        print(f"  Error: {e}")

# Try GraphQL endpoints - POST requests
graphql_query = {"query": "{ me { id } }"}
post_urls = [
    "https://jp.mercari.com/api/graphql",
    "https://jp.mercari.com/graphql",
]

for url in post_urls:
    print(f"\nPOST {url}")
    try:
        r = requests.post(url, json=graphql_query, cookies=cookies, headers=headers, timeout=10)
        print(f"  Status: {r.status_code}, Length: {len(r.text)}")
        if r.status_code == 200 and len(r.text) < 500:
            try:
                data = r.json()
                print(f"  JSON: {json.dumps(data, ensure_ascii=False)[:300]}")
            except:
                print(f"  Text: {r.text[:200]}")
    except Exception as e:
        print(f"  Error: {e}")

print("\nDone.")
