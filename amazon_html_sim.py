"""
Amazon検索結果のHTMLを取得し、指定位置の商品画像をユーザー画像に差し替える
"""

import requests
import re
import base64
import urllib.parse
from io import BytesIO
from PIL import Image


def fetch_amazon_search_html(keyword: str, user_image: Image.Image, position: int = 5) -> str:
    """
    Amazon.co.jpの検索結果HTMLを取得し、position番目の商品画像をuser_imageに差し替える
    Returns: 表示用HTML文字列
    """
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    session.headers.update(headers)

    try:
        # Cookieを取得
        session.get("https://www.amazon.co.jp/", timeout=10)

        # 検索結果を取得
        encoded = urllib.parse.quote(keyword)
        url = f"https://www.amazon.co.jp/s?k={encoded}"
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        html = resp.text

        # ユーザー画像をbase64に変換
        buf = BytesIO()
        user_image.convert("RGB").save(buf, format="JPEG", quality=90)
        user_b64 = base64.b64encode(buf.getvalue()).decode()
        user_data_url = f"data:image/jpeg;base64,{user_b64}"

        # 商品画像のURLパターン（検索結果のメインサムネイル）
        img_pattern = r'(https://m\.media-amazon\.com/images/I/[A-Za-z0-9+_.-]+\.(?:jpg|png))'
        matches = list(re.finditer(img_pattern, html))

        # ユニークな画像URLを追跡して、position番目を差し替え
        seen_bases = set()
        product_count = 0
        target_url = None

        for m in matches:
            img_url = m.group(1)
            # ベースIDで重複排除
            base_match = re.search(r'/I/([A-Za-z0-9+_]+)', img_url)
            if not base_match:
                continue
            base_id = base_match.group(1)
            if base_id in seen_bases:
                continue
            seen_bases.add(base_id)
            product_count += 1

            if product_count == position:
                target_url = base_id
                break

        # 対象商品の全画像URLを差し替え
        if target_url:
            html = re.sub(
                rf'https://m\.media-amazon\.com/images/I/{re.escape(target_url)}[A-Za-z0-9._-]*\.(?:jpg|png)',
                user_data_url,
                html
            )

        # 外部リソースの参照を修正（CSS、画像のURL）
        # 相対パスを絶対パスに変換
        html = html.replace('href="/', 'href="https://www.amazon.co.jp/')
        html = html.replace("href='/", "href='https://www.amazon.co.jp/")

        # リンクのクリックを無効化（iframe内で遷移させない）
        html = html.replace('<a ', '<a onclick="return false;" ')

        # スクロール可能なコンテナ用にbodyスタイルを追加
        style_inject = """
        <style>
            body { margin: 0; padding: 0; overflow-x: hidden; }
            * { max-width: 100% !important; }
            #nav-belt, #nav-main, .nav-footer, #rhf,
            .s-desktop-toolbar, #s-skipTo { display: none !important; }
        </style>
        """
        html = html.replace('</head>', style_inject + '</head>')

        return html

    except Exception as e:
        return f"<html><body><p>検索結果の取得に失敗しました: {e}</p></body></html>"
