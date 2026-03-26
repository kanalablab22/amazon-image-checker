"""
Amazon商品画像チェッカー - チェックロジック
商品面積比・影検出・明るさ・白背景・サイズをチェック
"""

import numpy as np
from PIL import Image, ImageDraw, ImageStat
from dataclasses import dataclass


@dataclass
class CheckResult:
    """チェック結果を格納するデータクラス"""
    name: str           # チェック項目名
    passed: bool        # True=OK, False=NG
    value: str          # 数値や結果の表示用文字列
    detail: str         # 詳細・改善アドバイス
    level: str = "ok"   # "ok", "ng", "warn"


@dataclass
class ImageCheckReport:
    """画像1枚のチェックレポート"""
    filename: str
    width: int
    height: int
    results: list       # CheckResult のリスト
    product_ratio: float
    bbox: tuple         # (left, top, right, bottom) 商品の外接矩形
    annotated_image: Image.Image  # bbox赤枠付き画像


def _get_product_mask(image: Image.Image, threshold: int = 240) -> np.ndarray:
    """
    商品領域のマスクを作成する。
    True = 商品ピクセル, False = 背景ピクセル
    """
    arr = np.array(image.convert("RGBA"))

    # アルファチャンネルで判定（透過PNG）
    alpha = arr[:, :, 3]
    has_transparency = np.any(alpha < 250)

    if has_transparency:
        # 透過がある場合：アルファ > 10 を商品とみなす
        mask = alpha > 10
    else:
        # 白背景の場合：RGB全てが threshold 以上を背景とみなす
        rgb = arr[:, :, :3]
        white_mask = np.all(rgb >= threshold, axis=2)
        mask = ~white_mask

    return mask


def _get_bbox(mask: np.ndarray) -> tuple:
    """マスクからバウンディングボックスを取得 (left, top, right, bottom)"""
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)

    if not np.any(rows) or not np.any(cols):
        # 商品が検出できない場合は画像全体を返す
        return (0, 0, mask.shape[1], mask.shape[0])

    top = np.argmax(rows)
    bottom = mask.shape[0] - np.argmax(rows[::-1])
    left = np.argmax(cols)
    right = mask.shape[1] - np.argmax(cols[::-1])

    return (int(left), int(top), int(right), int(bottom))


def check_product_ratio(image: Image.Image, threshold: int = 240) -> tuple:
    """
    チェック1: 商品面積比（Amazon公式: 85%以上）
    2段階のアプローチ:
      1) 実際の商品ピクセル数ベース（斜め置きなどに正確）
      2) bboxベース（外接矩形）も参考値として表示
    面積比は「ピクセルベース」をメインに使う。
    Returns: (CheckResult, product_mask, bbox)
    """
    mask = _get_product_mask(image, threshold)
    bbox = _get_bbox(mask)

    total_area = image.width * image.height

    # ピクセルベースの面積比（実際に商品が写っているピクセル数）
    pixel_count = int(np.sum(mask))
    pixel_ratio = pixel_count / total_area if total_area > 0 else 0

    # bboxベースの面積比（参考値）
    left, top, right, bottom = bbox
    bbox_area = (right - left) * (bottom - top)
    bbox_ratio = bbox_area / total_area if total_area > 0 else 0

    # 判定はbbox比をメインに（Amazon公式の定義に近い）
    ratio = bbox_ratio
    passed = ratio >= 0.85
    level = "ok" if passed else ("warn" if ratio >= 0.70 else "ng")

    if passed:
        detail = "Amazon基準（85%以上）を満たしています"
    elif ratio >= 0.70:
        detail = f"あと{(0.85 - ratio) * 100:.1f}%で基準達成。もう少し商品を大きく配置しましょう"
    else:
        detail = "商品が小さすぎます。余白を減らして商品をもっと大きく配置しましょう"

    result = CheckResult(
        name="商品面積比",
        passed=passed,
        value=f"{ratio * 100:.1f}%（実ピクセル: {pixel_ratio * 100:.1f}%）",
        detail=detail,
        level=level,
    )
    return result, mask, bbox


def check_shadow(image: Image.Image, mask: np.ndarray, bbox: tuple) -> CheckResult:
    """
    チェック2: 影の有無
    3つの方法で検出:
      1) 商品bboxの外側にある「影グレー帯」ピクセルを探す
      2) 商品周辺（bbox外周マージン）にグラデーションがあるか
      3) 画像全体で背景上のグレーピクセルの分布を確認
    """
    h, w = image.height, image.width
    arr = np.array(image.convert("RGB"))

    r = arr[:, :, 0].astype(float)
    g = arr[:, :, 1].astype(float)
    b = arr[:, :, 2].astype(float)
    luminance = r * 0.299 + g * 0.587 + b * 0.114

    # --- 方法1: 商品の外側にある影グレーピクセルを検出 ---
    # 影 = 商品マスクの外側 AND 純白ではない AND 暗すぎない AND 低彩度
    outside_product = ~mask
    is_not_pure_white = luminance < 252  # 純白より少し暗い
    is_not_too_dark = luminance > 150    # 暗すぎるのは影じゃない
    is_low_saturation = (
        (np.abs(r - g) < 30)
        & (np.abs(g - b) < 30)
        & (np.abs(r - b) < 30)
    )
    shadow_pixels = outside_product & is_not_pure_white & is_not_too_dark & is_low_saturation

    total_bg_pixels = int(np.sum(outside_product))
    shadow_count = int(np.sum(shadow_pixels))
    shadow_ratio = shadow_count / total_bg_pixels if total_bg_pixels > 0 else 0

    # --- 方法2: 商品bbox周辺のグラデーション検出 ---
    left, top, right, bottom = bbox
    margin = max(int(min(h, w) * 0.05), 10)  # bboxから外側5%のマージン

    has_gradient = False
    gradient_details = []

    # bbox周辺4方向をチェック
    regions = {
        "下": (max(0, bottom), min(h, bottom + margin * 3), max(0, left - margin), min(w, right + margin)),
        "右下": (max(0, bottom - margin), min(h, bottom + margin * 3), max(0, right - margin), min(w, right + margin * 3)),
        "右": (max(0, top - margin), min(h, bottom + margin), max(0, right), min(w, right + margin * 3)),
        "左下": (max(0, bottom - margin), min(h, bottom + margin * 3), max(0, left - margin * 3), min(w, left + margin)),
    }

    for direction, (y1, y2, x1, x2) in regions.items():
        if y2 <= y1 or x2 <= x1:
            continue
        region_lum = luminance[y1:y2, x1:x2]
        if region_lum.size < 20:
            continue

        # この領域の平均輝度が純白(>252)より暗ければ影の可能性
        region_mean = float(np.mean(region_lum))
        region_min = float(np.min(region_lum))

        # 純白背景(~255)より明らかに暗い部分があるか
        if region_mean < 248 and region_min < 240:
            has_gradient = True
            gradient_details.append(direction)

    # --- 方法3: 背景全体でグレー帯の割合が十分か ---
    # 背景ピクセルの輝度分布を見る
    bg_luminance = luminance[outside_product]
    if len(bg_luminance) > 100:
        # 純白(>252)でない背景ピクセルの割合
        non_white_bg_ratio = float(np.sum(bg_luminance < 252)) / len(bg_luminance)
    else:
        non_white_bg_ratio = 0

    # --- 総合判定 ---
    has_shadow = (
        shadow_ratio > 0.003           # 背景の0.3%以上が影グレー
        or has_gradient                 # 商品周辺にグラデーションあり
        or non_white_bg_ratio > 0.02   # 背景の2%以上が非純白
    )

    if has_shadow:
        if has_gradient:
            dirs = "・".join(gradient_details)
            detail = f"商品の{dirs}にドロップシャドウが検出されました"
        else:
            detail = "ドロップシャドウまたは鏡面反射が検出されました"
    else:
        detail = "影が検出されません。ドロップシャドウや鏡面反射を追加すると高級感が出ます"

    return CheckResult(
        name="影の有無",
        passed=has_shadow,
        value="あり" if has_shadow else "なし",
        detail=detail,
        level="ok" if has_shadow else "ng",
    )


def check_image_size(image: Image.Image) -> CheckResult:
    """チェック3: 画像サイズ（Amazon公式: 長辺500px以上、10,000px以下）"""
    w, h = image.size
    long_side = max(w, h)

    if long_side < 500:
        passed = False
        level = "ng"
        detail = "長辺500px未満です。Amazon公式基準（500px以上）を満たしていません"
    elif long_side > 10000:
        passed = False
        level = "ng"
        detail = "長辺10,000pxを超えています。Amazon公式基準（10,000px以下）を満たしていません"
    else:
        passed = True
        level = "ok"
        detail = "Amazon公式基準（長辺500px以上、10,000px以下）を満たしています"

    return CheckResult(
        name="画像サイズ",
        passed=passed,
        value=f"{w} x {h}px",
        detail=detail,
        level=level,
    )


def check_brightness(image: Image.Image, mask: np.ndarray) -> CheckResult:
    """チェック4: 明るさ（暗すぎ/明るすぎNG）"""
    arr = np.array(image.convert("RGB"))

    if not np.any(mask):
        return CheckResult(
            name="明るさ",
            passed=True,
            value="計測不可",
            detail="商品領域が検出できませんでした",
            level="warn",
        )

    # 商品部分のみの輝度を計算
    product_pixels = arr[mask]
    luminance = (
        product_pixels[:, 0].astype(float) * 0.299
        + product_pixels[:, 1].astype(float) * 0.587
        + product_pixels[:, 2].astype(float) * 0.114
    )
    avg_lum = float(np.mean(luminance))

    if avg_lum < 60:
        passed = False
        level = "ng"
        detail = "商品が暗すぎます。明るさを調整して、どんよりしない印象にしましょう"
    elif avg_lum < 80:
        passed = True
        level = "warn"
        detail = "やや暗めです。もう少し明るくするとより映えます"
    elif avg_lum > 240:
        passed = False
        level = "ng"
        detail = "商品が白すぎて背景と区別がつきにくいです"
    elif avg_lum > 220:
        passed = True
        level = "warn"
        detail = "商品がかなり明るく、背景と溶け込みやすいので注意してください"
    else:
        passed = True
        level = "ok"
        detail = "明るさは適正です"

    return CheckResult(
        name="明るさ",
        passed=passed,
        value=f"平均輝度 {avg_lum:.0f}",
        detail=detail,
        level=level,
    )


def check_white_background(image: Image.Image) -> CheckResult:
    """チェック5: 白背景の確認（四隅+辺の中央8点）"""
    arr = np.array(image.convert("RGB"))
    h, w = arr.shape[:2]

    margin = 5  # 端から5pxの位置をサンプル
    sample_points = [
        (margin, margin),                    # 左上
        (w - margin - 1, margin),            # 右上
        (margin, h - margin - 1),            # 左下
        (w - margin - 1, h - margin - 1),    # 右下
        (w // 2, margin),                    # 上辺中央
        (w // 2, h - margin - 1),            # 下辺中央
        (margin, h // 2),                    # 左辺中央
        (w - margin - 1, h // 2),            # 右辺中央
    ]

    white_count = 0
    for x, y in sample_points:
        r, g, b = int(arr[y, x, 0]), int(arr[y, x, 1]), int(arr[y, x, 2])
        if r >= 240 and g >= 240 and b >= 240:
            white_count += 1

    ratio = white_count / len(sample_points)
    passed = ratio >= 0.75  # 8箇所中6箇所以上が白ならOK

    if passed:
        detail = f"8箇所中{white_count}箇所が白背景を確認"
        level = "ok"
    else:
        detail = f"8箇所中{white_count}箇所しか白背景ではありません。純白(RGB 255,255,255)が推奨です"
        level = "ng"

    return CheckResult(
        name="白背景",
        passed=passed,
        value=f"{white_count}/8箇所",
        detail=detail,
        level=level,
    )


def check_aspect_ratio(image: Image.Image) -> CheckResult:
    """チェック6: アスペクト比チェック"""
    w, h = image.size
    ratio = w / h if h > 0 else 1

    # Amazon推奨: 1:1 から 1:1.5 くらいまで
    if 0.6 <= ratio <= 1.05:
        passed = True
        level = "ok"
        detail = "Amazon推奨のアスペクト比です"
    elif 0.5 <= ratio <= 1.2:
        passed = True
        level = "warn"
        detail = "使えますが、正方形〜やや縦長が検索結果で最も映えます"
    else:
        passed = False
        level = "ng"
        detail = "アスペクト比が極端です。正方形〜縦長（1:1〜2:3）がAmazon推奨です"

    return CheckResult(
        name="アスペクト比",
        passed=passed,
        value=f"{w}:{h} ({ratio:.2f})",
        detail=detail,
        level=level,
    )


def _create_annotated_image(image: Image.Image, bbox: tuple) -> Image.Image:
    """商品bboxに赤枠を描画した画像を作成"""
    annotated = image.copy().convert("RGB")

    # 大きい画像はプレビュー用にリサイズ
    max_dim = 600
    if max(annotated.size) > max_dim:
        scale = max_dim / max(annotated.size)
        new_size = (int(annotated.width * scale), int(annotated.height * scale))
        annotated = annotated.resize(new_size, Image.LANCZOS)

        # bboxもスケール
        left, top, right, bottom = bbox
        bbox = (
            int(left * scale),
            int(top * scale),
            int(right * scale),
            int(bottom * scale),
        )

    draw = ImageDraw.Draw(annotated)
    left, top, right, bottom = bbox
    for i in range(2):  # 2px幅の赤枠
        draw.rectangle(
            [left - i, top - i, right + i, bottom + i],
            outline=(255, 0, 0),
        )

    return annotated


def check_image(image: Image.Image, filename: str = "image.jpg") -> ImageCheckReport:
    """
    画像の全チェックを実行して結果をまとめる
    """
    results = []

    # 1. 商品面積比
    ratio_result, mask, bbox = check_product_ratio(image)
    results.append(ratio_result)

    # 2. 影の有無
    results.append(check_shadow(image, mask, bbox))

    # 3. 画像サイズ
    results.append(check_image_size(image))

    # 4. 明るさ
    results.append(check_brightness(image, mask))

    # 5. 白背景
    results.append(check_white_background(image))

    # 6. アスペクト比
    results.append(check_aspect_ratio(image))

    # bbox赤枠付き画像
    annotated = _create_annotated_image(image, bbox)

    return ImageCheckReport(
        filename=filename,
        width=image.width,
        height=image.height,
        results=results,
        product_ratio=(bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / (image.width * image.height),
        bbox=bbox,
        annotated_image=annotated,
    )
