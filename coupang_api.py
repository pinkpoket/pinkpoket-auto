#!/usr/bin/env python3
"""쿠팡 파트너스 Open API — 키워드로 상품을 찾아 파트너스 링크를 돌려준다.

GitHub 비밀값 COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY 가 있어야 동작한다.
없거나 오류가 나면 빈 목록을 돌려주고, 글·쇼츠 발행은 그대로 진행된다.
표준 라이브러리만 쓴다.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

DOMAIN = "https://api-gateway.coupang.com"
BASE = "/v2/providers/affiliate_open_api/apis/openapi/v1"


def enabled():
    return bool(os.environ.get("COUPANG_ACCESS_KEY", "").strip() and
                os.environ.get("COUPANG_SECRET_KEY", "").strip())


def _authorization(method, url_path):
    access = os.environ["COUPANG_ACCESS_KEY"].strip()
    secret = os.environ["COUPANG_SECRET_KEY"].strip()
    path, _, query = url_path.partition("?")
    t = time.gmtime()
    signed = time.strftime("%y%m%d", t) + "T" + time.strftime("%H%M%S", t) + "Z"
    sig = hmac.new(secret.encode(), (signed + method + path + query).encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access}, signed-date={signed}, signature={sig}"


def _call(method, url_path, body=None):
    req = urllib.request.Request(
        DOMAIN + url_path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": _authorization(method, url_path),
                 "Content-Type": "application/json;charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            js = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"쿠팡 API HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}") from None
    if str(js.get("rCode", "0")) != "0":
        raise RuntimeError(f"쿠팡 API 오류: {js.get('rMessage')}")
    return js.get("data")


def search(keyword, limit=5, sub_id=""):
    params = {"keyword": keyword, "limit": limit}
    if sub_id:
        params["subId"] = sub_id
    data = _call("GET", f"{BASE}/products/search?{urllib.parse.urlencode(params)}") or {}
    out = []
    for p in data.get("productData", []):
        out.append({"name": (p.get("productName") or "").strip(), "url": p.get("productUrl"),
                    "price": p.get("productPrice"), "rocket": bool(p.get("isRocket")),
                    "image": p.get("productImage")})
    return [p for p in out if p["url"] and p["name"]]


def short_name(name, limit=28):
    name = " ".join(name.split())
    return name if len(name) <= limit else name[:limit].rstrip() + "…"


def pick(keywords, count=1, sub_id="", exclude=()):
    """키워드마다 검색해서 로켓배송 상품 위주로 count 개를 고른다. 실패하면 []."""
    if not enabled():
        return []
    chosen, seen = [], set(exclude)
    for kw in keywords:
        kw = str(kw).strip()
        if not kw:
            continue
        try:
            items = search(kw, limit=5, sub_id=sub_id)
        except Exception as e:  # noqa: BLE001
            print(f"[쿠팡] '{kw}' 검색 실패: {e}")
            continue
        items.sort(key=lambda p: (not p["rocket"],))
        for p in items:
            if p["url"] in seen:
                continue
            seen.add(p["url"])
            chosen.append({"url": p["url"], "name": short_name(p["name"]), "keyword": kw})
            break
        if len(chosen) >= count:
            break
        time.sleep(1)
    return chosen


def deeplink(urls, sub_id=""):
    """쿠팡 주소(메인·기획전 등)를 내 파트너스 링크로 바꾼다. [(원래주소, 짧은링크)]"""
    body = {"coupangUrls": list(urls)}
    if sub_id:
        body["subId"] = sub_id
    data = _call("POST", f"{BASE}/deeplink", body) or []
    return [(d.get("originalUrl"), d.get("shortenUrl")) for d in data]


if __name__ == "__main__":
    # 사용: python coupang_api.py https://www.coupang.com/ ...
    import sys
    for orig, short in deeplink(sys.argv[1:] or ["https://www.coupang.com/"],
                                sub_id=os.environ.get("COUPANG_SUB_ID", "").strip()):
        print(f"[파트너스 링크] {orig} → {short}")
