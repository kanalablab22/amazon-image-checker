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
from amazon_search_sim import create_search_simulation, fetch_amazon_thumbnails
from amazon_html_sim import fetch_amazon_search_html, fetch_amazon_mobile_html
import streamlit.components.v1 as components

# --- ジャンル別アドバイス ---
import os

def _load_genre_tips():
    """genre_tips.jsonを読み込む"""
    path = os.path.join(os.path.dirname(__file__), "genre_tips.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _match_genre(keyword: str, tips_data: list) -> dict | None:
    """キーワードにマッチするジャンルを探す"""
    if not keyword.strip():
        return None
    kw_lower = keyword.lower()
    best_match = None
    best_score = 0
    for genre in tips_data:
        score = 0
        for gk in genre.get("keywords", []):
            if gk.lower() in kw_lower or kw_lower in gk.lower():
                score += 1
        if score > best_score:
            best_score = score
            best_match = genre
    return best_match if best_score > 0 else None

# --- カスタムデータの永続化（GitHub API / 汎用） ---

def _github_headers():
    token = st.secrets.get("github", {}).get("token", "")
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

def _github_repo():
    return st.secrets.get("github", {}).get("repo", "kanalablab22/amazon-image-checker")

def _has_github_secrets() -> bool:
    try:
        return len(st.secrets.get("github", {}).get("token", "")) > 0
    except Exception:
        return False

def _load_data(filename: str):
    """GitHub（data branch）またはローカルからJSONを読み込む"""
    if _has_github_secrets():
        try:
            repo = _github_repo()
            url = f"https://api.github.com/repos/{repo}/contents/{filename}?ref=data"
            resp = requests.get(url, headers=_github_headers(), timeout=5)
            if resp.status_code == 200:
                content = base64.b64decode(resp.json()["content"]).decode("utf-8")
                return json.loads(content)
        except Exception:
            pass
    # ローカルフォールバック
    local_path = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_data(filename: str, data, commit_msg: str = "データ更新"):
    """GitHub（data branch）+ ローカルにJSONを保存"""
    # ローカル保存（常に）
    local_path = os.path.join(os.path.dirname(__file__), filename)
    try:
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    if not _has_github_secrets():
        return
    try:
        repo = _github_repo()
        url = f"https://api.github.com/repos/{repo}/contents/{filename}"
        sha = None
        resp = requests.get(url + "?ref=data", headers=_github_headers(), timeout=5)
        if resp.status_code == 200:
            sha = resp.json()["sha"]
        payload = {
            "message": commit_msg,
            "content": base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii"),
            "branch": "data",
        }
        if sha:
            payload["sha"] = sha
        put_resp = requests.put(url, headers=_github_headers(), json=payload, timeout=5)
        if put_resp.status_code in (200, 201):
            st.toast("✅ 保存しました", icon="✅")
        else:
            st.toast(f"⚠️ GitHub保存失敗（{put_resp.status_code}）", icon="⚠️")
    except Exception:
        st.toast("⚠️ GitHub接続エラー。ローカルには保存済み", icon="⚠️")

# 便利関数（既存コードとの互換性）
def load_custom_guidelines() -> list:
    return _load_data("custom_guidelines.json")

def save_custom_guidelines(guidelines: list):
    _save_data("custom_guidelines.json", guidelines, "ガイドライン更新")

def load_examples(kind: str) -> list:
    """OK例集 or NG例集を読み込む（kind = 'ok' or 'ng'）"""
    return _load_data(f"examples_{kind}.json")

def save_examples(kind: str, examples: list):
    label = "OK例集" if kind == "ok" else "NG例集"
    _save_data(f"examples_{kind}.json", examples, f"{label}更新")

def load_comments() -> dict:
    """画像ごとのコメントを読み込む"""
    return _load_data("comments.json") or {}

def save_comments(comments: dict):
    _save_data("comments.json", comments, "コメント更新")

st.set_page_config(
    page_title="Amazon画像チェッカー",
    page_icon="🔍",
    layout="wide",
)

# --- カスタムCSS ---
st.markdown("""
<style>
/* 削除ボタン（✕）をミニマルに */
button[kind="secondary"]:has(p) {
    all: unset !important;
}
div[data-testid="stColumn"]:last-child button {
    background: none !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    min-height: 0 !important;
    font-size: 0.7em !important;
    color: #aaa !important;
    cursor: pointer !important;
}
div[data-testid="stColumn"]:last-child button:hover {
    color: #e53935 !important;
}
</style>
""", unsafe_allow_html=True)

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
    with st.expander("🏢 **社内ガイドライン**", expanded=False):
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

        custom_guidelines = load_custom_guidelines()

        for title, desc in default_guidelines:
            st.checkbox(f"**{title}**", value=False, key=f"internal_{title}")
            st.markdown(f"<p style='margin-top: -15px; margin-bottom: 8px; padding-left: 32px; font-size: 0.78em; color: #888;'>{desc}</p>", unsafe_allow_html=True)

        for i, g in enumerate(custom_guidelines):
            st.checkbox(f"**{g['title']}**", value=False, key=f"custom_{i}_{g['title']}")
            desc_text = g.get("desc", "")
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

    # ===========================================
    # ブランド一覧（ブランドも追加可能に）
    # ===========================================
    st.markdown("---")
    DEFAULT_BRANDS = [
        "GRAV", "CAMP GREEB", "sopoa",
        "mura", "oeuf_soleil", "hugmotti", "shop_channel",
        "hugmin", "riceking", "pin_eagle", "ponbaby",
        "hacono", "kameto", "qp", "nocor",
        "turfmate", "forest_pellet", "chotplus", "baby_potage",
    ]
    custom_brands = _load_data("custom_brands.json")
    all_brands = DEFAULT_BRANDS + [b for b in custom_brands if b not in DEFAULT_BRANDS]

    # ブランド選択 → すぐ下にOK/NG表示
    st.markdown("### 🏷️ ブランド別 OK / NG例集")
    selected_brand = st.selectbox(
        "ブランドを選択",
        ["（選択してください）"] + all_brands,
        key="brand_filter",
    )

    # ブランド追加
    with st.expander("ブランドを追加"):
        with st.form("add_brand_form", clear_on_submit=True):
            new_brand = st.text_input("ブランド名", placeholder="例: 新ブランド名")
            brand_submitted = st.form_submit_button("➕ 追加")
            if brand_submitted and new_brand.strip() and new_brand.strip() not in all_brands:
                custom_brands.append(new_brand.strip())
                _save_data("custom_brands.json", custom_brands, "ブランド追加")
                st.rerun()

    # --- ブランド選択後にOK/NG表示 ---
    ok_examples = load_examples("ok")
    ng_examples = load_examples("ng")

    if selected_brand != "（選択してください）":
        filtered_ok = [ex for ex in ok_examples if ex.get("brand", "") == selected_brand]
        filtered_ng = [ex for ex in ng_examples if ex.get("brand", "") == selected_brand]

        # ✅ OK例
        st.markdown(f"#### ✅ {selected_brand} の OK例")
        if not filtered_ok:
            st.caption("まだ登録されていません")
        for i, ex in enumerate(filtered_ok):
            orig_idx = ok_examples.index(ex)
            col_txt, col_del = st.columns([8, 1])
            with col_txt:
                desc_part = f' <span style="font-size:0.78em;color:#888;">— {ex["desc"]}</span>' if ex.get("desc") else ""
                st.markdown(f"**・{ex['title']}**{desc_part}", unsafe_allow_html=True)
            with col_del:
                if st.button("✕", key=f"del_ok_{orig_idx}", help="削除"):
                    ok_examples.pop(orig_idx)
                    save_examples("ok", ok_examples)
                    st.rerun()

        st.markdown("---")

        # ❌ NG例
        st.markdown(f"#### ❌ {selected_brand} の NG例")
        if not filtered_ng:
            st.caption("まだ登録されていません")
        for i, ex in enumerate(filtered_ng):
            orig_idx = ng_examples.index(ex)
            col_txt, col_del = st.columns([8, 1])
            with col_txt:
                desc_part = f' <span style="font-size:0.78em;color:#888;">— {ex["desc"]}</span>' if ex.get("desc") else ""
                st.markdown(f"**・{ex['title']}**{desc_part}", unsafe_allow_html=True)
            with col_del:
                if st.button("✕", key=f"del_ng_{orig_idx}", help="削除"):
                    ng_examples.pop(orig_idx)
                    save_examples("ng", ng_examples)
                    st.rerun()
    else:
        st.caption("👆 ブランドを選ぶとOK例・NG例が表示されます")

    # --- ブランド未選択でも追加できるフォーム ---
    st.markdown("---")
    st.markdown("### ➕ 例を追加")
    with st.form("add_example_form", clear_on_submit=True):
        ex_brand = st.selectbox("ブランド", ["（選択してください）"] + all_brands, key="ex_brand",
                                index=(all_brands.index(selected_brand) + 1) if selected_brand in all_brands else 0)
        ex_type = st.radio("種類", ["✅ OK例", "❌ NG例"], horizontal=True)
        ex_title = st.text_input("内容", placeholder="例: 影が自然に入っていて立体的")
        ex_desc = st.text_input("補足（任意）", placeholder="例: 左上からの光で高級感がある", key="ex_desc")
        ex_submitted = st.form_submit_button("➕ 追加", type="primary")
        if ex_submitted and ex_title.strip() and ex_brand != "（選択してください）":
            entry = {"title": ex_title.strip(), "desc": ex_desc.strip() if ex_desc.strip() else "", "brand": ex_brand}
            if "OK" in ex_type:
                ok_examples = load_examples("ok")
                ok_examples.append(entry)
                save_examples("ok", ok_examples)
            else:
                ng_examples = load_examples("ng")
                ng_examples.append(entry)
                save_examples("ng", ng_examples)
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

# --- 画像アップロード＆キーワード入力（並列） ---
up_col, kw_col = st.columns([3, 2])

with up_col:
    st.markdown("**サムネイル画像をドラッグ＆ドロップ（複数OK）**")
    uploaded_files = st.file_uploader(
        "サムネイル画像をドラッグ＆ドロップ（複数OK）",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

with kw_col:
    st.markdown("**🔍 検索キーワード（検索結果プレビュー用）**")
    target_keyword = st.text_input(
        "検索キーワード",
        placeholder="例：財布 レディース 本革",
        key="target_keyword",
        label_visibility="collapsed",
    )
    check_stitching = st.toggle("🪡 縫製チェック（革・布製品向け）", value=False, key="check_stitching")

if not uploaded_files:
    st.info("👆 上のエリアにサムネイル画像をドロップしてください（複数OK）")
    st.stop()

# --- チェック実行 ---
reports: list[ImageCheckReport] = []

for uploaded_file in uploaded_files:
    image = Image.open(uploaded_file)
    report = check_image(image, uploaded_file.name, check_stitching=check_stitching)
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
        st.markdown(f"**`{report.filename}`** → **{report.score}点** {status}")

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

    # 総合判定（一番上に表示）
    all_ok = all(r.level == "ok" for r in report.results)
    has_ng = any(r.level == "ng" for r in report.results)
    score = report.score

    # スコア表示（カラー付き）
    score_color = "#4CAF50" if score >= 80 else "#FF9800" if score >= 60 else "#F44336"
    label = "✅ 合格" if score >= 80 else "⚠️ 要改善"
    bg = "#E8F5E9" if score >= 80 else ("#FFF3E0" if score >= 60 else "#FFEBEE")
    border = "#4CAF50" if score >= 80 else ("#FF9800" if score >= 60 else "#F44336")
    st.markdown(f"""
    <div style="background:{bg}; border-left:5px solid {border}; border-radius:10px; padding:16px 22px; margin-bottom:12px;">
        <span style="font-size:22px; font-weight:bold;">総合スコア:
            <span style="color:{score_color}; font-size:32px;">{score}点</span>
            <span style="font-size:18px; color:#666;"> / 100点</span>
            <span style="font-size:20px; margin-left:8px;">{label}</span>
        </span>
    </div>
    """, unsafe_allow_html=True)

    if all_ok:
        st.success("🎉 すべてのチェックをクリア！")
    elif has_ng:
        ng_items = [r.name for r in report.results if r.level == "ng"]
        st.error(f"❌ 修正が必要: {', '.join(ng_items)}")
    else:
        st.warning("⚠️ 確認したほうがいい項目があります")

    col_img, col_result = st.columns([1, 1])

    # 左: 画像（bbox赤枠付き）
    with col_img:
        st.image(report.annotated_image, caption=f"{report.filename} ({report.width}x{report.height}px)", use_column_width=True)

    # 右: チェック結果（カラーバー付き）
    with col_result:
        for result in report.results:
            if result.level == "ok":
                icon = "✅"
                color = "#4CAF50"
                bar_pct = 100
            elif result.level == "warn":
                icon = "⚠️"
                color = "#FF9800"
                bar_pct = 60
            else:
                icon = "❌"
                color = "#F44336"
                bar_pct = 20

            st.markdown(f"### {icon} {result.name}: {result.value}")
            # カラーバー
            st.markdown(f"""<div style="background:#eee; border-radius:4px; height:6px; margin:-8px 0 4px 0; overflow:hidden;">
                <div style="width:{bar_pct}%; height:100%; background:{color}; border-radius:4px;"></div>
            </div>""", unsafe_allow_html=True)
            st.markdown(f"<p style='color: {color}; margin-top: 0;'>{result.detail}</p>", unsafe_allow_html=True)

    # --- コメント欄 ---
    comments = load_comments()
    if not isinstance(comments, dict):
        comments = {}
    file_key = report.filename
    file_comments = comments.get(file_key, [])

    if file_comments:
        st.markdown("**💬 コメント**")
        for ci, c in enumerate(file_comments):
            col_comment, col_del = st.columns([20, 1])
            with col_comment:
                st.markdown(f"<span style='font-size:0.9em;'>{c.get('text', '')}</span>", unsafe_allow_html=True)
            with col_del:
                if st.button("×", key=f"del_comment_{i}_{ci}",
                             help="削除",
                             type="secondary"):
                    file_comments.pop(ci)
                    comments[file_key] = file_comments
                    save_comments(comments)
                    st.rerun()

    with st.expander("💬 コメントを追加", expanded=False):
        comment_text = st.text_area("コメント", key=f"comment_text_{i}", placeholder="例: 影をもう少し強くしたほうが良さそう", height=80)
        if st.button("💾 保存", key=f"save_comment_{i}"):
            if comment_text.strip():
                file_comments.append({
                    "text": comment_text.strip()
                })
                comments[file_key] = file_comments
                save_comments(comments)
                st.success("コメントを保存しました！")
                st.rerun()
            else:
                st.warning("コメントを入力してください")

    if i < len(reports) - 1:
        st.markdown("---")

# --- ジャンル別サムネイル戦略アドバイス ---
if target_keyword.strip():
    genre_tips = _load_genre_tips()
    matched_genre = _match_genre(target_keyword, genre_tips)
    if matched_genre:
        st.markdown("---")
        icon = matched_genre.get("genre_icon", "💡")
        name = matched_genre.get("genre_name", "")
        refs = matched_genre.get("reference_brands", "")
        st.markdown(f"""
<div style="background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%); border-radius: 16px; padding: 24px; margin-bottom: 20px;">
  <h3 style="margin:0 0 4px 0;">{icon} 「{name}」ジャンルのサムネイル戦略</h3>
  <p style="margin:0; color:#888; font-size:13px;">参考店舗: {refs}</p>
</div>
""", unsafe_allow_html=True)

        tip_cols = st.columns(2)
        for idx, tip in enumerate(matched_genre.get("tips", [])[:4]):
            with tip_cols[idx % 2]:
                st.markdown(f"""
<div style="background: white; border: 1px solid #e8ecf0; border-radius: 12px; padding: 16px; margin-bottom: 12px; min-height: 140px;">
  <p style="margin:0 0 8px 0; font-weight: bold;">💡 {tip['title']}</p>
  <p style="margin:0; font-size: 13px; color: #444; line-height: 1.6;">{tip['body']}</p>
</div>
""", unsafe_allow_html=True)

# --- 検索結果シミュレーション ---
sim_pc = None
if target_keyword.strip():
    st.markdown("---")
    st.markdown("## 🔍 検索結果シミュレーション")
    st.caption(f"「{target_keyword}」でAmazon検索した場合のイメージ")

    with st.spinner("Amazon検索結果を取得中..."):
        try:
            uploaded_files[0].seek(0)
            user_img = Image.open(uploaded_files[0])

            tab_pc, tab_sp = st.tabs(["🖥️ PC版", "📱 スマホ版"])
            with tab_pc:
                amazon_html = fetch_amazon_search_html(target_keyword, user_img, position=5)
                components.html(amazon_html, height=800, scrolling=True)

                competitors = fetch_amazon_thumbnails(target_keyword, count=14)
                sim_pc = create_search_simulation(
                    keyword=target_keyword,
                    user_image=user_img,
                    position=5,
                    competitor_images=competitors,
                )
            with tab_sp:
                amazon_html_sp = amazon_html
                sp_css = """
                <style>
                    html, body { margin:0 !important; padding:0 !important; max-width:375px !important; margin:0 auto !important; overflow-x:hidden !important; }
                    *, *::before, *::after { box-sizing:border-box !important; }
                    /* 検索結果を2列に強制（元のCSS + 追加セレクタ） */
                    .s-main-slot { display:flex !important; flex-wrap:wrap !important; }
                    .s-main-slot > div[data-component-type="s-search-result"] {
                        width:50% !important; flex:0 0 50% !important;
                    }
                    .s-main-slot > div:not([data-component-type="s-search-result"]) {
                        width:100% !important; flex:0 0 100% !important;
                    }
                    /* 追加: Amazon内部グリッドの3列化を防止 */
                    .s-result-item { width:50% !important; }
                    .sg-col-inner { padding:4px !important; }
                </style>
                """
                amazon_html_sp = amazon_html_sp.replace('</head>', sp_css + '</head>')
                components.html(amazon_html_sp, height=700, scrolling=True)
        except Exception as e:
            st.warning(f"検索結果の取得に失敗しました: {e}")
            st.info("Amazon側のアクセス制限の可能性があります。時間をおいて再度お試しください。")
else:
    st.markdown("---")
    st.info("💡 検索キーワードを入力すると、Amazon検索結果のシミュレーションも表示されますよ")

# --- PDFレポート ---
st.markdown("---")
st.markdown("## 📄 PDFレポート")

# PDF自動生成 → ワンクリックでダウンロード
with st.spinner("PDF生成中..."):
    original_images = []
    for uploaded_file in uploaded_files:
        uploaded_file.seek(0)
        original_images.append(Image.open(uploaded_file))

    all_comments = load_comments()
    if not isinstance(all_comments, dict):
        all_comments = {}
    pdf_bytes = generate_pdf_report(reports, original_images, comments=all_comments, sim_image=sim_pc)

st.download_button(
    label="📥 PDFレポートをダウンロード",
    data=pdf_bytes,
    file_name="amazon_image_check_report.pdf",
    mime="application/pdf",
    type="primary",
)
