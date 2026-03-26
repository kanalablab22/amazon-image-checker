"""
Amazon商品画像チェッカー
作成した商品画像がAmazonガイドライン＋社内基準を満たしているかチェック
"""

import streamlit as st
from PIL import Image
from io import BytesIO
from image_checker import check_image, ImageCheckReport
from pdf_report import generate_pdf_report

st.set_page_config(
    page_title="Amazon画像チェッカー",
    page_icon="🔍",
    layout="wide",
)

# --- サイドバー: Amazon公式ガイドライン ---
with st.sidebar:
    st.markdown("## 📋 商品のメイン画像 要件")
    st.caption("Amazon Seller Central 公式ガイドラインより")

    guidelines = [
        "実際の商品を正確に表し、プロフェッショナルな品質の画像であること",
        "プレースホルダーがないこと",
        "純粋な白の背景（RGB: 255,255,255）を使用すること",
        "画像の85%が商品で占められていること",
        "商品または背景にテキスト、ロゴ、縁取り、カラーブロック、透かし等を配置しないこと",
        "画像の枠内に商品全体を表示し、どの部分も切り取られていないこと",
        "商品に含まれていない付属品や小道具を表示しないこと",
        "画像には商品を1回のみ表示すること（正面のみなど）",
    ]

    for g in guidelines:
        st.checkbox(g, value=False, key=g)

    st.divider()
    st.markdown("## 🏢 社内ガイドライン")

    internal_guidelines = [
        ("商品を大きく、白余白を最小限に", "色を濃く商品を大きくするのがCTR改善のコツ"),
        ("陰影・鏡面で少しインパクトを出す", "ドロップシャドウや鏡面反射で高級感"),
        ("暗くてどんよりしないよう明るさに注意", "検索結果のサムネイルで暗く見えないか要チェック"),
        ("検索結果の中で相対的に目立つように", "競合の中で埋もれない画像づくり"),
        ("質感と佇まいが伝わる画像にする", "CGをやめて実写の質感を重視"),
        ("細部にこだわる", "光の感じ、立体感、木や布の質感を追求"),
    ]

    for title, desc in internal_guidelines:
        st.checkbox(f"**{title}**", value=False, help=desc, key=f"internal_{title}")

# --- メインエリア ---
st.markdown("# 🔍 Amazon商品画像チェッカー")
st.markdown("作成した商品画像をアップロードすると、Amazonガイドラインに基づいて自動チェックします")

with st.expander("📌 **画像の技術的要件（Amazon公式）**", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
- **形式**: JPEG（推奨）/ TIFF / PNG / GIF
- **サイズ**: 長辺500px以上〜10,000px以下
- **解像度**: 鮮明、画素化されていないこと
        """)
    with col2:
        st.markdown("""
- **背景**: 純粋な白（RGB: 255,255,255）
- **面積比**: 画像の85%を商品が占める
- **禁止**: テキスト、ロゴ、透かし等なし
        """)

# ファイルアップロード
uploaded_files = st.file_uploader(
    "画像をドラッグ＆ドロップ（複数枚OK）",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("👆 チェックしたい商品画像をアップロードしてください")
    st.stop()

# --- チェック実行 ---
reports: list[ImageCheckReport] = []

for uploaded_file in uploaded_files:
    image = Image.open(uploaded_file)
    report = check_image(image, uploaded_file.name)
    reports.append(report)

# --- 複数枚サマリー（2枚以上の場合） ---
if len(reports) > 1:
    st.markdown("---")
    st.markdown("## 📊 一括チェック結果")

    summary_cols = st.columns([2, 1, 1, 1, 1])
    summary_cols[0].markdown("**ファイル名**")
    summary_cols[1].markdown("**面積比**")
    summary_cols[2].markdown("**影**")
    summary_cols[3].markdown("**サイズ**")
    summary_cols[4].markdown("**総合**")

    for report in reports:
        cols = st.columns([2, 1, 1, 1, 1])
        cols[0].markdown(f"`{report.filename}`")

        # 面積比
        ratio_result = report.results[0]
        icon = "✅" if ratio_result.level == "ok" else ("⚠️" if ratio_result.level == "warn" else "❌")
        cols[1].markdown(f"{icon} {ratio_result.value}")

        # 影
        shadow_result = report.results[1]
        icon = "✅" if shadow_result.passed else "❌"
        cols[2].markdown(f"{icon} {shadow_result.value}")

        # サイズ
        size_result = report.results[2]
        icon = "✅" if size_result.passed else "❌"
        cols[3].markdown(f"{icon}")

        # 総合
        all_passed = all(r.passed for r in report.results)
        cols[4].markdown("✅ 合格" if all_passed else "❌ 要修正")

    st.markdown("---")

# --- 画像ごとの詳細結果 ---
for i, report in enumerate(reports):
    if len(reports) > 1:
        st.markdown(f"## 📸 {report.filename}")
    else:
        st.markdown("## 📸 チェック結果")

    col_img, col_result = st.columns([1, 1])

    # 左: 画像（bbox赤枠付き）
    with col_img:
        st.image(report.annotated_image, caption=f"{report.filename} ({report.width}x{report.height}px)", use_container_width=True)

    # 右: チェック結果
    with col_result:
        for result in report.results:
            if result.level == "ok":
                icon = "✅"
                color = "green"
            elif result.level == "warn":
                icon = "⚠️"
                color = "orange"
            else:
                icon = "❌"
                color = "red"

            st.markdown(f"### {icon} {result.name}: {result.value}")
            st.markdown(f"<p style='color: {color}; margin-top: -10px;'>{result.detail}</p>", unsafe_allow_html=True)

        # 総合判定
        st.divider()
        all_ok = all(r.level == "ok" for r in report.results)
        has_ng = any(r.level == "ng" for r in report.results)

        if all_ok:
            st.success("🎉 すべてのチェックをクリア！この画像はAmazon基準OKです")
        elif has_ng:
            ng_items = [r.name for r in report.results if r.level == "ng"]
            st.error(f"❌ 修正が必要な項目: {', '.join(ng_items)}")
        else:
            st.warning("⚠️ 確認したほうがいい項目があります")

    if i < len(reports) - 1:
        st.markdown("---")

# --- PDFレポート ---
st.markdown("---")
st.markdown("## 📄 PDFレポート")

# PDF自動生成 → ワンクリックでダウンロード
with st.spinner("PDF生成中..."):
    original_images = []
    for uploaded_file in uploaded_files:
        uploaded_file.seek(0)
        original_images.append(Image.open(uploaded_file))

    pdf_bytes = generate_pdf_report(reports, original_images)

st.download_button(
    label="📥 PDFレポートをダウンロード",
    data=pdf_bytes,
    file_name="amazon_image_check_report.pdf",
    mime="application/pdf",
    type="primary",
)
