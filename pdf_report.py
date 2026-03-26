"""
Amazon商品画像チェッカー - PDFレポート生成
横型A4・日本語対応（HeiseiKakuGo-W5 CIDフォント）
"""

from io import BytesIO
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# 日本語フォント登録
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

FONT_NAME = "HeiseiKakuGo-W5"
PAGE_SIZE = landscape(A4)


def _create_styles():
    """PDF用スタイルを作成"""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="JP_Title",
        fontName=FONT_NAME,
        fontSize=18,
        leading=24,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="JP_Subtitle",
        fontName=FONT_NAME,
        fontSize=12,
        leading=16,
        spaceAfter=6,
        textColor=colors.HexColor("#555555"),
    ))
    styles.add(ParagraphStyle(
        name="JP_Normal",
        fontName=FONT_NAME,
        fontSize=9,
        leading=13,
    ))
    styles.add(ParagraphStyle(
        name="JP_Small",
        fontName=FONT_NAME,
        fontSize=7,
        leading=10,
        textColor=colors.HexColor("#666666"),
    ))
    styles.add(ParagraphStyle(
        name="JP_Header",
        fontName=FONT_NAME,
        fontSize=10,
        leading=14,
        textColor=colors.white,
    ))

    return styles


def _pil_to_rl_image(pil_image: Image.Image, max_width: float = 80 * mm, max_height: float = 60 * mm) -> RLImage:
    """PIL ImageをReportLab Imageに変換"""
    buf = BytesIO()
    rgb_image = pil_image.convert("RGB")
    rgb_image.save(buf, format="JPEG", quality=85)
    buf.seek(0)

    # アスペクト比を保ってリサイズ
    w, h = pil_image.size
    scale = min(max_width / w, max_height / h)
    display_w = w * scale
    display_h = h * scale

    return RLImage(buf, width=display_w, height=display_h)


def generate_pdf_report(reports, original_images=None) -> bytes:
    """
    チェック結果のPDFレポートを生成
    Args:
        reports: ImageCheckReport のリスト
        original_images: PIL Image のリスト（元画像）
    Returns: PDF bytes
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=PAGE_SIZE,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = _create_styles()
    elements = []

    # タイトル
    elements.append(Paragraph("Amazon商品画像 チェックレポート", styles["JP_Title"]))
    elements.append(Paragraph(
        f"チェック画像数: {len(reports)}枚　|　基準: Amazon公式ガイドライン",
        styles["JP_Subtitle"],
    ))
    elements.append(Spacer(1, 5 * mm))

    # サマリーテーブル（Paragraphで折り返し対応）
    header_labels = ["ファイル名", "サイズ", "面積比", "影", "画像サイズ", "明るさ", "白背景", "比率", "総合"]
    header = [Paragraph(h, styles["JP_Header"]) for h in header_labels]
    table_data = [header]

    for report in reports:
        row = [
            Paragraph(report.filename, styles["JP_Small"]),
            Paragraph(f"{report.width}x{report.height}", styles["JP_Small"]),
        ]
        all_passed = True
        for result in report.results:
            if result.level == "ok":
                cell = f"OK {result.value}"
            elif result.level == "warn":
                cell = f"注意 {result.value}"
                all_passed = False
            else:
                cell = f"NG {result.value}"
                all_passed = False
            row.append(Paragraph(cell, styles["JP_Small"]))
        row.append(Paragraph("合格" if all_passed else "要修正", styles["JP_Small"]))
        table_data.append(row)

    col_widths = [45 * mm, 22 * mm, 35 * mm, 18 * mm, 28 * mm, 28 * mm, 20 * mm, 28 * mm, 18 * mm]
    table = Table(table_data, colWidths=col_widths)

    # テーブルスタイル
    style_commands = [
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        # ヘッダ行
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#232F3E")),  # Amazon Dark Blue
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
    ]

    # 行ごとの色分け
    for row_idx in range(1, len(table_data)):
        row = table_data[row_idx]
        if row[-1] == "合格":
            style_commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#E8F5E9")))
        else:
            style_commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#FFF3E0")))

        # 個別セルの色
        for col_idx in range(2, len(row) - 1):
            cell_text = row[col_idx]
            if cell_text.startswith("NG"):
                style_commands.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.red))
            elif cell_text.startswith("注意"):
                style_commands.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), colors.HexColor("#FF8F00")))

    table.setStyle(TableStyle(style_commands))
    elements.append(table)
    elements.append(Spacer(1, 8 * mm))

    # 画像ごとの詳細
    for i, report in enumerate(reports):
        elements.append(Paragraph(f"■ {report.filename}", styles["JP_Normal"]))
        elements.append(Spacer(1, 3 * mm))

        # 画像 + 詳細テーブルを横並び
        detail_data = []
        for result in report.results:
            icon = "OK" if result.level == "ok" else ("注意" if result.level == "warn" else "NG")
            detail_data.append([
                Paragraph(f"{result.name}", styles["JP_Small"]),
                Paragraph(f"{icon}: {result.value}", styles["JP_Small"]),
                Paragraph(f"{result.detail}", styles["JP_Small"]),
            ])

        detail_table = Table(detail_data, colWidths=[25 * mm, 30 * mm, 90 * mm])
        detail_style = [
            ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]

        # NG行を赤背景
        for row_idx, result in enumerate(report.results):
            if result.level == "ng":
                detail_style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#FFEBEE")))

        detail_table.setStyle(TableStyle(detail_style))

        # 画像と詳細を横に並べる
        img_rl = _pil_to_rl_image(report.annotated_image, max_width=60 * mm, max_height=50 * mm)
        layout_table = Table(
            [[img_rl, detail_table]],
            colWidths=[65 * mm, 150 * mm],
        )
        layout_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))

        elements.append(layout_table)
        elements.append(Spacer(1, 6 * mm))

    # フッター: ガイドライン参照
    elements.append(Spacer(1, 5 * mm))
    elements.append(Paragraph(
        "参照: Amazon Seller Central 商品画像のガイド",
        styles["JP_Small"],
    ))

    doc.build(elements)
    return buf.getvalue()
