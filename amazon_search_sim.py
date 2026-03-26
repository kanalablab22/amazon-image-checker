"""
Amazon検索結果シミュレーション
キーワードで検索した結果のサムネイル画像を取得し、
5番目にユーザーの商品画像を挿入したシミュレーション画像を生成する
"""

import requests
import re
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import urllib.parse


def fetch_amazon_thumbnails(keyword: str, count: int = 8) -> list:
    """
    Amazon.co.jpでキーワード検索し、商品サムネイル画像URLを取得する
    Returns: PIL Image のリスト
    """
    encoded = urllib.parse.quote(keyword)
    url = f"https://www.amazon.co.jp/s?k={encoded}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        html = resp.text

        # 商品画像URLを抽出（Amazon検索結果のサムネイル）
        # data-image-sourceで高画質サムネを取得
        patterns = [
            r'"https://m\.media-amazon\.com/images/I/[^"]+\._AC_UL320_\.jpg"',
            r'"https://m\.media-amazon\.com/images/I/[^"]+\._AC_UL400_\.jpg"',
            r'"https://m\.media-amazon\.com/images/I/[^"]+\._AC_UL200_\.jpg"',
            r'"https://m\.media-amazon\.com/images/I/[^"]+\._AC_SX[0-9]+_\.jpg"',
            r'"https://m\.media-amazon\.com/images/I/[^"]+\._AC_SR[0-9,]+_\.jpg"',
        ]

        image_urls = []
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for m in matches:
                clean_url = m.strip('"')
                if clean_url not in image_urls:
                    image_urls.append(clean_url)
            if len(image_urls) >= count + 5:
                break

        # 画像をダウンロード
        images = []
        seen = set()
        for img_url in image_urls:
            if len(images) >= count:
                break
            # 重複チェック（ベース名で）
            base = re.sub(r'\._AC_[^.]+\.', '.', img_url)
            if base in seen:
                continue
            seen.add(base)

            try:
                img_resp = requests.get(img_url, headers=headers, timeout=5)
                img = Image.open(BytesIO(img_resp.content)).convert("RGBA")
                images.append(img)
            except Exception:
                continue

        return images

    except Exception:
        return []


def create_search_simulation(
    keyword: str,
    user_image: Image.Image,
    position: int = 5,
    competitor_images: list = None,
) -> Image.Image:
    """
    Amazon検索結果のシミュレーション画像を生成する

    Args:
        keyword: 検索キーワード
        user_image: ユーザーの商品画像
        position: ユーザー画像を挿入する位置（1-indexed）
        competitor_images: 競合の画像リスト（Noneの場合は自動取得）

    Returns: シミュレーション画像（PIL Image）
    """
    # 競合画像を取得
    if competitor_images is None:
        competitor_images = fetch_amazon_thumbnails(keyword, count=7)

    # グリッドレイアウト設定
    cols = 4
    thumb_size = 200
    padding = 15
    header_height = 70
    label_height = 25
    cell_w = thumb_size + padding * 2
    cell_h = thumb_size + padding * 2 + label_height

    total_items = max(8, len(competitor_images) + 1)
    rows = (total_items + cols - 1) // cols

    canvas_w = cols * cell_w + padding
    canvas_h = header_height + rows * cell_h + padding

    # キャンバス作成（Amazon風の白背景）
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # ヘッダー（検索バー風）
    draw.rectangle([0, 0, canvas_w, header_height], fill=(35, 47, 62))

    # 検索バー
    bar_x = padding
    bar_y = 15
    bar_w = canvas_w - padding * 2
    bar_h = 40
    draw.rounded_rectangle(
        [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
        radius=8,
        fill=(255, 255, 255),
    )

    # 検索テキスト
    try:
        font_small = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", 14)
        font_label = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", 11)
        font_header = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", 14)
    except Exception:
        font_small = ImageFont.load_default()
        font_label = ImageFont.load_default()
        font_header = font_small

    draw.text((bar_x + 10, bar_y + 10), keyword, fill=(0, 0, 0), font=font_small)

    # 検索結果ラベル
    result_label = f'"{keyword}" の検索結果シミュレーション'
    draw.text((padding, header_height + 5), result_label, fill=(100, 100, 100), font=font_label)

    # 画像を配置用リストに整列
    all_items = list(competitor_images)
    # position位置にユーザー画像を挿入（0-indexed で position-1）
    insert_idx = min(position - 1, len(all_items))
    all_items.insert(insert_idx, ("USER", user_image))

    # グリッドに画像を配置
    for idx in range(min(total_items, len(all_items))):
        row = idx // cols
        col = idx % cols

        x = padding + col * cell_w
        y = header_height + 20 + row * cell_h

        item = all_items[idx]
        is_user = isinstance(item, tuple) and item[0] == "USER"

        if is_user:
            img = item[1]
            # ユーザー画像のハイライト枠
            draw.rectangle(
                [x, y, x + cell_w - padding, y + cell_h - 5],
                outline=(255, 153, 0),  # Amazonオレンジ
                width=3,
            )
            border_color = (255, 153, 0)
        else:
            img = item
            draw.rectangle(
                [x, y, x + cell_w - padding, y + cell_h - 5],
                outline=(230, 230, 230),
                width=1,
            )
            border_color = None

        # 画像をリサイズしてセンタリング
        img_rgb = img.convert("RGB") if img.mode != "RGB" else img
        img_rgb.thumbnail((thumb_size - 10, thumb_size - 10), Image.Resampling.LANCZOS)
        paste_x = x + (cell_w - padding - img_rgb.width) // 2
        paste_y = y + (thumb_size - img_rgb.height) // 2 + padding // 2
        canvas.paste(img_rgb, (paste_x, paste_y))

        # ラベル
        if is_user:
            label_y = y + cell_h - label_height - 5
            draw.rectangle(
                [x + 2, label_y, x + cell_w - padding - 2, label_y + 20],
                fill=(255, 153, 0),
            )
            draw.text((x + 8, label_y + 3), "▶ あなたの商品", fill=(255, 255, 255), font=font_label)
        else:
            # 競合のダミー価格ライン
            price_y = y + cell_h - label_height - 5
            draw.rectangle([x + 5, price_y + 2, x + 60, price_y + 4], fill=(200, 200, 200))
            draw.rectangle([x + 5, price_y + 10, x + 100, price_y + 12], fill=(220, 220, 220))

    # 競合が取得できなかった場合のプレースホルダー
    if len(all_items) < total_items:
        for idx in range(len(all_items), total_items):
            row = idx // cols
            col = idx % cols
            x = padding + col * cell_w
            y = header_height + 20 + row * cell_h
            draw.rectangle(
                [x + 5, y + 5, x + cell_w - padding - 5, y + thumb_size + padding],
                fill=(245, 245, 245),
                outline=(220, 220, 220),
            )
            draw.text(
                (x + cell_w // 3, y + thumb_size // 2),
                "No Image",
                fill=(180, 180, 180),
                font=font_label,
            )

    return canvas
