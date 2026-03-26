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


def fetch_amazon_mobile_html(keyword: str, user_image: Image.Image, position: int = 5) -> str:
    """
    Amazon.co.jpのモバイル版検索結果HTMLを取得し、position番目の商品画像を差し替える
    """
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Accept-Language": "ja-JP,ja;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    session.headers.update(headers)

    try:
        session.get("https://www.amazon.co.jp/", timeout=10)

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

        # imgタグのsrcから商品画像を探す（最も確実な方法）
        img_srcs = re.findall(r'<img[^>]+src="(https://m\.media-amazon\.com/images/I/[^"]+\.jpg)"', html)

        seen_bases = set()
        product_count = 0
        target_base = None

        for src_url in img_srcs:
            base_match = re.search(r'/I/([A-Za-z0-9+_]+)', src_url)
            if not base_match:
                continue
            base_id = base_match.group(1)
            if base_id in seen_bases:
                continue
            # ロゴやアイコンを除外
            if len(base_id) < 10:
                continue
            # サムネイルサイズの画像だけカウント（SX148等）
            if '_AC_SX' not in src_url and '_AC_SR' not in src_url and '_AC_SY' not in src_url:
                continue
            seen_bases.add(base_id)
            product_count += 1

            if product_count == position:
                target_base = base_id
                break

        if target_base:
            # このベースIDを持つ全画像URLを差し替え
            html = re.sub(
                rf'https://m\.media-amazon\.com/images/I/{re.escape(target_base)}[A-Za-z0-9._+-]*\.jpg',
                user_data_url,
                html
            )

        # URL修正
        html = html.replace('href="/', 'href="https://www.amazon.co.jp/')
        html = html.replace("href='/", "href='https://www.amazon.co.jp/")
        html = html.replace('<a ', '<a onclick="return false;" ')

        # モバイル用スタイル調整（2列グリッド強制）
        style_inject = """
        <style>
            body { margin: 0; padding: 0; overflow-x: hidden; font-size: 13px; }
            * { max-width: 100% !important; }
            #nav-belt, #nav-main, .nav-footer, #rhf,
            .s-mobile-toolbar, #s-skipTo { display: none !important; }

            /* 検索結果を2列グリッドに強制 */
            .s-main-slot > .s-result-item,
            .s-search-results > .s-result-item,
            [data-component-type="s-search-result"] {
                display: inline-block !important;
                width: 48% !important;
                vertical-align: top !important;
                margin: 1% !important;
                box-sizing: border-box !important;
            }
            .s-main-slot,
            .s-search-results {
                display: block !important;
                font-size: 0 !important;
            }
            .s-main-slot > *,
            .s-search-results > * {
                font-size: 13px !important;
            }
            /* 商品画像を中央寄せ */
            .s-image {
                display: block !important;
                margin: 0 auto !important;
                max-height: 140px !important;
                width: auto !important;
            }
            /* 広告バナーは全幅 */
            .AdHolder, .s-result-item[data-component-type="sp-sponsored-result"] {
                width: 100% !important;
                display: block !important;
            }
        </style>
        """
        html = html.replace('</head>', style_inject + '</head>')

        return html

    except Exception as e:
        return f"<html><body><p>取得失敗: {e}</p></body></html>"
