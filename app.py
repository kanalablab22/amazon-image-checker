"""
Amazon商品画像チェッカー
作成した商品画像がAmazonガイドライン＋社内基準を満たしているかチェック
"""

import streamlit as st
import json
import base64
import requests
from PIL import Image
from io import BytesIO
from image_checker import check_image, ImageCheckReport
from pdf_report import generate_pdf_report

# --- カスタムガイドラインの永続化（GitHub API） ---
GUIDELINES_PATH = "custom_guidelines.json"

def _github_headers():
    """GitHub API用ヘッダー"""
    token = st.secrets.get("github", {}).get("token", "")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

def _github_repo():
    return st.secrets.get("github", {}).get("repo", "kanalablab22/amazon-image-checker")

def _has_github_secrets() -> bool:
    """GitHub secretsが設定されているか確認"""
    try:
        token = st.secrets.get("github", {}).get("token", "")
        return len(token) > 0
    except Exception:
        return False

def load_custom_guidelines() -> list:
    """GitHubリポジトリからカスタムガイドラインを読み込む"""
    if not _has_github_secrets():
        return _load_local_guidelines()
    try:
        repo = _github_repo()
        url = f"https://api.github.com/repos/{repo}/contents/{GUIDELINES_PATH}?ref=data"
        resp = requests.get(url, headers=_github_headers(), timeout=5)
        if resp.status_code == 200:
            content = base64.b64decode(resp.json()["content"]).decode("utf-8")
            return json.loads(content)
        else:
            return _load_local_guidelines()
    except Exception:
        return _load_local_guidelines()

def save_custom_guidelines(guidelines: list):
    """GitHubリポジトリにカスタムガイドラインを保存"""
    # ローカルにも常に保存（フォールバック）
    _save_local_guidelines(guidelines)

    if not _has_github_secrets():
        return

    try:
        repo = _github_repo()
        url = f"https://api.github.com/repos/{repo}/contents/{GUIDELINES_PATH}"

        # 既存ファイルのSHAを取得（更新時に必要）
        sha = None
        resp = requests.get(url + "?ref=data", headers=_github_headers(), timeout=5)
        if resp.status_code == 200:
            sha = resp.json()["sha"]

        # ファイルを作成/更新
        content = json.dumps(guidelines, ensure_ascii=False, indent=2)
        data = {
            "message": "ガイドライン更新",
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": "data",
        }
        if sha:
            data["sha"] = sha

        put_resp = requests.put(url, headers=_github_headers(), json=data, timeout=5)
        if put_resp.status_code in (200, 201):
            st.toast("✅ 保存しました", icon="✅")
        else:
            st.toast(f"⚠️ GitHub保存失敗（{put_resp.status_code}）ローカルには保存済み", icon="⚠️")
    except Exception as e:
        st.toast(f"⚠️ GitHub接続エラー。ローカルには保存済み", icon="⚠️")

# --- ローカルファイルフォールバック ---
import os
_LOCAL_FILE = os.path.join(os.path.dirname(__file__), "custom_guidelines.json")

def _load_local_guidelines() -> list:
    if os.path.exists(_LOCAL_FILE):
        try:
            with open(_LOCAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_local_guidelines(guidelines: list):
    try:
        with open(_LOCAL_FILE, "w", encoding="utf-8") as f:
            json.dump(guidelines, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

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

    # デフォルトのガイドライン
    default_guidelines = [
        ("商品を大きく、白余白を最小限に", "色を濃く商品を大きくするのがCTR改善のコツ"),
        ("陰影・鏡面で少しインパクトを出す", "ドロップシャドウや鏡面反射で高級感"),
        ("暗くてどんよりしないよう明るさに注意", "検索結果のサムネイルで暗く見えないか要チェック"),
        ("商品の一部が暗くなっていないか", "穴の中・隙間・パーツの裏側も明るく見えるように"),
        ("斜めからの光で立体感を出す", "まっすぐなライトだと平面的に。左上からの自然光が理想"),
        ("検索結果の中で相対的に目立つように", "競合の中で埋もれない画像づくり"),
        ("質感と佇まいが伝わる画像にする", "CGをやめて実写の質感を重視"),
        ("細部にこだわる", "光の感じ、立体感、木や布の質感を追求"),
    ]

    # ユーザー追加ガイドラインをファイルから読み込み
    custom_guidelines = load_custom_guidelines()

    # デフォルト（固定）ガイドラインを表示
    for title, desc in default_guidelines:
        st.checkbox(f"**{title}**", value=False, key=f"internal_{title}")
        st.markdown(f"<p style='margin-top: -15px; margin-bottom: 8px; padding-left: 32px; font-size: 0.78em; color: #888;'>{desc}</p>", unsafe_allow_html=True)

    # ユーザー追加ガイドライン（削除ボタン付き）
    for i, g in enumerate(custom_guidelines):
        st.checkbox(f"**{g['title']}**", value=False, key=f"custom_{i}_{g['title']}")
        desc_text = g.get("desc", "")
        # 補足説明 + 削除リンクを1行にまとめる
        desc_part = f'<span style="color: #888;">{desc_text}</span>　' if desc_text else ""
        st.markdown(
            f"<p style='margin-top: -15px; margin-bottom: 8px; padding-left: 32px; font-size: 0.78em;'>"
            f"{desc_part}</p>",
            unsafe_allow_html=True,
        )
        if st.button("削除", key=f"del_{i}", type="secondary"):
            custom_guidelines.pop(i)
            save_custom_guidelines(custom_guidelines)
            st.rerun()

    # --- ガイドライン追加 ---
    st.markdown("---")
    if not _has_github_secrets():
        st.caption("⚠️ GitHub未接続（ローカル保存モード）")
    with st.form("add_guideline_form", clear_on_submit=True):
        new_title = st.text_input("チェック項目を追加", placeholder="例: 背景に余計なものを入れない")
        new_desc = st.text_input("補足説明（任意）", placeholder="例: 商品以外の小道具やテキストはNG")
        submitted = st.form_submit_button("➕ 追加", type="primary")
        if submitted and new_title.strip():
            custom_guidelines.append({
                "title": new_title.strip(),
                "desc": new_desc.strip() if new_desc.strip() else "",
            })
            save_custom_guidelines(custom_guidelines)
            st.rerun()

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

    for report in reports:
        all_passed = all(r.passed for r in report.results)
        ng_count = sum(1 for r in report.results if r.level == "ng")
        warn_count = sum(1 for r in report.results if r.level == "warn")

        status = "✅ 合格" if all_passed else f"❌ NG {ng_count}件" if ng_count else f"⚠️ 注意 {warn_count}件"
        st.markdown(f"**`{report.filename}`** → {status}")

        # コンパクトに各チェック結果を表示
        result_text = " | ".join([
            f"{'✅' if r.level == 'ok' else ('⚠️' if r.level == 'warn' else '❌')}{r.name}"
            for r in report.results
        ])
        st.caption(result_text)

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
        st.image(report.annotated_image, caption=f"{report.filename} ({report.width}x{report.height}px)", width="100%")

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
