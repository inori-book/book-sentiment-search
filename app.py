import streamlit as st
import pandas as pd
import requests
from janome.tokenizer import Tokenizer
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go
import re
import unicodedata
from dotenv import load_dotenv
import os
from wordcloud import WordCloud
import matplotlib.pyplot as plt

load_dotenv()

st.markdown('''
<style>
  /* Streamlit 標準の背景色をクリア */
  .stApp, .css-1d391kg, .css-k1vhr4 {
    background: none !important;
  }
  /* Base64 埋め込みした背景画像を全体に敷く */
  .stApp {
    background-image: url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAABAAAAAYACAIAAABn4K39AADUTGNhQlgAANRManVtYgAAAB5qdW1kYzJwYQARABCAAACqADibcQNjMnBhAAAA...（省略）...kTTLmo%") !important;
    background-size: cover !important;
    background-position: center !important;
  }
  .custom-btn {
    display: block;
    width: 355px;
    max-width: 100%;
    margin: 20px auto;
    background: #FFA500;
    color: #000;
    font-weight: bold;
    font-size: 16px;
    border-radius: 8px;
    text-align: center;
    padding: 16px 0;
    text-decoration: none;
    border: none;
  }
  .custom-btn:hover {
    opacity: 0.9;
  }
  div.stButton > button {
    width: 355px !important;
    max-width: 100% !important;
    margin: 20px auto !important;
    background: #FFA500 !important;
    color: #000 !important;
    font-weight: bold !important;
    font-size: 16px !important;
    border-radius: 8px !important;
    text-align: center !important;
    padding: 16px 0 !important;
    border: none !important;
  }
  /* タイトル・リード文・下部テキストの親divも中央揃え */
  div[data-testid="stMarkdownContainer"] > div,
  .custom-title, .custom-lead, .custom-bottom1, .custom-bottom2 {
    text-align: center !important;
  }
</style>
''', unsafe_allow_html=True)

# ─── 1. ページ設定（最初に） ─────────────────────────────────
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide", initial_sidebar_state="collapsed")

# ─── 2. データ読み込み & 前処理 ─────────────────────────────────
# 抽出対象の品詞をリスト化（将来的に増やしやすい形）
POS_TARGETS = ["形容詞", "形容動詞"]

@st.cache_data
def load_abstractwords(path: str = "abstractwords.txt") -> set[str]:
    try:
        with open(path, encoding="utf-8") as f:
            words = {line.strip() for line in f if line.strip() and not line.startswith("#")}
    except FileNotFoundError:
        words = set()
    return words

ABSTRACTWORDS = load_abstractwords()

def extract_target_words(text: str) -> list[str]:
    tokens = tokenizer.tokenize(text)
    results = []
    for t in tokens:
        pos = t.part_of_speech.split(",")[0]
        if pos in POS_TARGETS:
            results.append(t.base_form)
    # 文中に抽出ワードリストがあれば必ず抽出
    for word in ABSTRACTWORDS:
        if word in text:
            results.append(word)
    return results

@st.cache_data
def load_data(path: str = "database.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ISBN": str}).fillna("")
    df.columns = [col.lower() for col in df.columns]  # 列名を小文字に統一
    # ジャンルをリスト化
    df["genres_list"] = df["genre"].str.split(",").apply(lambda lst: [g.strip() for g in lst if g.strip()])
    # Janome で形容詞・形容動詞抽出
    global tokenizer
    tokenizer = Tokenizer()
    df["keywords"] = df["review"].apply(extract_target_words)
    return df

df = load_data()

# ─── 3. ストップワード外部化 & 候補形容詞 ─────────────────────────────
@st.cache_data
def load_stopwords(path: str = "stopwords.txt") -> set[str]:
    try:
        with open(path, encoding="utf-8") as f:
            words = {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        words = {"ない", "っぽい"}
    return words

def get_rakuten_app_id():
    return st.secrets.get("RAKUTEN_APP_ID") or os.getenv("RAKUTEN_APP_ID")

def normalize_isbn(isbn_str: str) -> str:
    """ISBNを正規化する（ハイフンや空白を除去）"""
    if not isbn_str:
        return ""
    # 全角英数字を半角に、数字以外を除去
    s = unicodedata.normalize("NFKC", isbn_str)
    return re.sub(r"[^0-9Xx]", "", s)

# 楽天ブックスAPIで書誌情報を取得
@st.cache_resource(show_spinner=False)
def fetch_rakuten_book(isbn: str) -> dict:
    if not isbn:
        return {}
    normalized_isbn = normalize_isbn(isbn)
    if not normalized_isbn:
        return {}
    url = "https://app.rakuten.co.jp/services/api/BooksBook/Search/20170404"
    params = {
        "isbn": normalized_isbn,
        "applicationId": get_rakuten_app_id(),
        "format": "json"
    }
    try:
        res = requests.get(url, params=params)
        res.raise_for_status()
        data = res.json()
        if data.get("Items"):
            item = data["Items"][0]["Item"]
            # 書影はlarge→medium→smallの順で最初に見つかったもの
            cover_url = item.get("largeImageUrl") or item.get("mediumImageUrl") or item.get("smallImageUrl") or ""
            return {
                "title": item.get("title"),
                "author": item.get("author"),
                "publisher": item.get("publisherName"),
                "pubdate": item.get("salesDate"),
                "price": item.get("itemPrice") if item.get("itemPrice") is not None else "—",
                "description": item.get("itemCaption") or "—",
                "cover": cover_url,
                "affiliateUrl": item.get("affiliateUrl"),
                "itemUrl": item.get("itemUrl")
            }
    except Exception as e:
        print(e)
    return {}

STOPWORDS = load_stopwords()
all_keywords = sorted({kw for lst in df["keywords"] for kw in lst})
suggestions = [w for w in all_keywords if w not in STOPWORDS]

# ─── 4. セッションステート初期化 ─────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "home"
if "results" not in st.session_state:
    st.session_state.results = pd.DataFrame()
if "adj" not in st.session_state:
    st.session_state.adj = ""
if "detail_idx" not in st.session_state:
    st.session_state.detail_idx = None
if "raw_input" not in st.session_state:
    st.session_state.raw_input = ""
if "raw_select" not in st.session_state:
    st.session_state.raw_select = ""
if "show_filter_expander" not in st.session_state:
    st.session_state.show_filter_expander = False

# ─── 5. サイドバー: ジャンル・スペック絞り込み ─────────────────────────────
# 絞り込み機能の初期化
spec_keys = ["erotic", "grotesque", "insane", "paranomal", "esthetic", "painful", "action", "mystery"]
spec_labels = ["エロ", "グロ", "人怖", "霊怖", "耽美", "感動", "アクション", "謎"]

if "spec_ranges" not in st.session_state:
    st.session_state.spec_ranges = {k: (0, 5) for k in spec_keys}
if "selected_genres" not in st.session_state:
    st.session_state.selected_genres = []

# サイドバー開閉ボタンを常時表示するCSSのみ適用
st.markdown('''
    <style>
    button[aria-label="Open sidebar"] {
        display: block !important;
        opacity: 1 !important;
        z-index: 1001 !important;
    }
    /* スペックスライダーの余白調整 */
    div[data-baseweb="slider"] {
        margin-left: 8px !important;
        margin-right: 8px !important;
    }
    </style>
''', unsafe_allow_html=True)

# ─── 6. ページ遷移用関数 ─────────────────────────────────────
def to_results(adj=None):
    if adj is None:
        adj = st.session_state.raw_select or st.session_state.raw_input.strip()
    st.session_state.adj = adj
    st.session_state.raw_input = adj  # 検索に使ったワードを入力欄にも反映
    tmp = df.copy()
    # ジャンル絞り込み
    selected_genres = st.session_state.get('selected_genres', [])
    if selected_genres:
        tmp = tmp[tmp["genres_list"].apply(lambda genres: any(g in genres for g in selected_genres))]

    # スペック絞り込み
    spec_ranges = st.session_state.get('spec_ranges', {})
    spec_keys = ["erotic", "grotesque", "insane", "paranomal", "esthetic", "painful", "action", "mystery"]
    for k in spec_keys:
        if k in spec_ranges:
            min_val, max_val = spec_ranges[k]
            tmp = tmp[(tmp[k] >= min_val) & (tmp[k] <= max_val)]

    # 形容詞絞り込み
    tmp["count"] = tmp["keywords"].apply(lambda lst: lst.count(adj))
    res = tmp[tmp["count"] > 0].sort_values("count", ascending=False)
    if not res.empty:
        res["rank"] = res["count"].rank(method="min", ascending=False).astype(int)
    st.session_state.results = res.reset_index(drop=True)
    st.session_state.page = "results"

def to_detail(idx: int):
    st.session_state.detail_idx = idx
    st.session_state.page = "detail"

def to_home():
    st.session_state.page = "home"

def to_results_page():
    st.session_state.page = "results"

# ─── 7. ホーム画面 ───────────────────────────────────────
if st.session_state.page == "home":
    # カスタムCSSで背景・フォント・色・余白などを調整
    st.markdown(f'''
        <style>
        /* 背景画像＋黒レイヤー */
        .stApp {{
            position: relative !important;
            min-height: 100vh !important;
            background: url('/background.png'), url('background.png') !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            background-attachment: fixed !important;
        }}
        .stApp::before, body::before {{
            content: "";
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.2);
            z-index: 0;
            pointer-events: none;
        }}
        /* メインコンテンツを前面に */
        .main, .block-container, .css-18e3th9, .css-1d391kg {{
            position: relative;
            z-index: 1;
        }}
        /* 全体幅375px中央寄せ */
        div[data-testid="stVerticalBlock"] > div:first-child {{
            max-width: 375px;
            margin: 0 auto;
            background: transparent;
        }}
        /* タイトル */
        .custom-title {{
            font-size: 30px !important;
            font-weight: bold !important;
            color: #FFFFFF !important;
            padding: 84px 10px 10px 10px !important;
            letter-spacing: 0.02em;
            text-align: center !important;
        }}
        .custom-title span.colon {{
            color: #FF9500 !important;
        }}
        /* リード文・下部テキスト */
        .custom-lead, .custom-bottom1, .custom-bottom2 {{
            font-size: 16px !important;
            color: #FFFFFF !important;
            padding: 10px !important;
            text-align: center !important;
        }}
        .custom-bottom1 {{
            padding-top: 0 !important;
        }}
        .custom-bottom2 {{
            padding-top: 0 !important;
        }}
        /* 検索フォームラベル */
        .custom-label {{
            font-size: 14px !important;
            color: #FFFFFF !important;
            padding: 10px 10px 0 10px !important;
        }}
        /* テキストエリア・プルダウン */
        .custom-input, .custom-select {{
            width: 167px !important;
            height: 88px !important;
            padding: 10px !important;
            font-size: 14px !important;
            color: #FFFFFF !important;
            background: rgba(0,0,0,0.4) !important;
            border-radius: 8px !important;
            border: 1px solid #94A3B8 !important;
            margin: 0 5px 0 0 !important;
        }}
        /* プレースホルダー色 */
        input::placeholder, textarea::placeholder, .custom-select option:disabled {{
            color: #94A3B8 !important;
            opacity: 1 !important;
        }}
        /* 共通ボタンデザインをstButtonに強制適用 */
        div.stButton > button {{
            width: 100% !important;
            text-align: center !important;
            font-size: 16px !important;
            font-weight: bold !important;
            color: #000000 !important;
            background: #FF9500 !important;
            border-radius: 8px !important;
            text-decoration: none !important;
            padding: 16px 0 !important;
            margin: 20px 10px 20px 10px !important;
            border: none !important;
            cursor: pointer !important;
        }}
        /* 区切り線 */
        .custom-divider {{
            width: 355px;
            height: 1px;
            background: #FFFFFF;
            opacity: 0.3;
            margin: 116px 10px 10px 10px !important;
        }}
        </style>
    ''', unsafe_allow_html=True)

    # タイトル
    st.markdown('<div class="custom-title">YOMIAJI <span class="colon">:</span> βテスト版</div>', unsafe_allow_html=True)
    # リード文
    st.markdown('<div class="custom-lead">感想・読み味から本が検索できるサービスです。<br>入力したキーワードが感想に含まれている本を検索できます。</div>', unsafe_allow_html=True)

    # 検索フォーム（横並び）
    col1, col2 = st.columns(2, gap="small")
    with col1:
        st.markdown('<div class="custom-label">フリーテキストで検索</div>', unsafe_allow_html=True)
        st.session_state.raw_input = st.text_area(
            "形容詞を入力してください", value=st.session_state.raw_input, key="raw_input_input",
            placeholder="例：美しい、切ない…",
            height=70,
            label_visibility="collapsed"
        )
    with col2:
        st.markdown('<div class="custom-label">候補から検索</div>', unsafe_allow_html=True)
        filtered = [w for w in suggestions if w.startswith(st.session_state.raw_input)] if st.session_state.raw_input else suggestions
        st.session_state.raw_select = st.selectbox(
            "候補から選ぶ", options=[""] + filtered, index=0, key="raw_select_box",
            placeholder="形容詞を選択",
            label_visibility="collapsed"
        )
    # 検索ボタン（st.button＋CSSで実装）
    st.button("検索", on_click=to_results, key="search_btn_home")
    # 区切り線
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    # 下部テキスト
    st.markdown('<div class="custom-bottom1"><b>あなたが読んだ本の感想を投稿してください</b></div>', unsafe_allow_html=True)
    st.markdown('<div class="custom-bottom2">あなたの感想がサービスを育てます。</div>', unsafe_allow_html=True)
    # Googleフォームボタン（st.button＋CSSで実装）
    st.link_button("Googleフォーム", "https://forms.gle/Eh3fYtnzSHmN3KMSA", type="primary")

# ─── 8. 検索結果画面 ───────────────────────────────────
elif st.session_state.page == "results":
    # 0. 戻るボタン
    if st.button("戻る", key="back_to_home"):
        to_home()
        st.rerun()
    # 1. 検索ワード入力欄
    if not st.session_state.raw_input:
        st.session_state.raw_input = st.session_state.get('adj', '')
    st.session_state.raw_input = st.text_input(
        "", value=st.session_state.raw_input, key="raw_input_results", placeholder=""
    )
    # 2. 検索ボタン
    new_input = st.session_state.raw_input
    if st.button("再検索", key="search_btn_results"):
        to_results(new_input)
#   if st.button("絞り込み", key="filter_btn2"):
#       st.session_state['show_filter_expander'] = not st.session_state.get('show_filter_expander', False)
#       st.rerun()
#
#   # 絞り込みエクスパンダー
#   if st.session_state.get('show_filter_expander', False):
#       with st.expander("絞り込み条件", expanded=True):
#           st.markdown('''
#           <style>
#           h3 {
#               text-align: left !important;
#           }
#           /* 数値入力フィールドのスタイル */
#           div[data-testid="stNumberInput"] {
#               margin-bottom: 10px !important;
#           }
#           /* 数値入力フィールドのラベル */
#           div[data-testid="stNumberInput"] label {
#               font-size: 12px !important;
#               color: #FFFFFF !important;
#           }
#           /* エクスパンダー内のパディング */
#           div[data-testid="stExpander"] > div {
#               padding: 20px !important;
#           }
#           </style>
#           ''', unsafe_allow_html=True)
#           # スペック絞り込み
#           st.subheader("スペック")
#           for k, label in zip(spec_keys, spec_labels):
#               col1, col2 = st.columns(2)
#               with col1:
#                   min_val = st.number_input(f"{label} 最小", 0, 5, st.session_state.spec_ranges[k][0], key=f"min_{k}")
#               with col2:
#                   max_val = st.number_input(f"{label} 最大", 0, 5, st.session_state.spec_ranges[k][1], key=f"max_{k}")
#               st.session_state.spec_ranges[k] = (min_val, max_val)
#
#           # ジャンル絞り込み
#           st.subheader("ジャンル")
#           unique_genres = sorted({g for lst in df["genres_list"] for g in lst})
#           st.session_state.selected_genres = st.multiselect("ジャンル", options=unique_genres, default=st.session_state.selected_genres)
#
#           # 適用・キャンセルボタン
#           col1, col2 = st.columns(2)
#           with col1:
#               if st.button("適用", key="apply_filter"):
#                   # 現在の検索ワードで絞り込み条件を適用して再検索
#                   if st.session_state.get('adj'):
#                       to_results(st.session_state.adj)
#                       st.rerun()
#           with col2:
#               if st.button("キャンセル", key="cancel_filter"):
#                   # 絞り込み条件をリセット
#                   st.session_state.spec_ranges = {k: (0, 5) for k in spec_keys}
#                   st.session_state.selected_genres = []
#                   st.session_state.show_filter_expander = False
#                   st.rerun()

    # 4. 検索結果タイトル
    adj = st.session_state.get('adj', '')
    st.markdown(f'<div style="width:355px;margin:12px auto 0 auto;font-family:Inter,sans-serif;font-size:20px;color:#FFFFFF;line-height:28px;font-weight:bold;">検索結果「{adj}」</div>', unsafe_allow_html=True)
    # 5. 注意書き
    st.markdown('<div class="custom-note">※楽天ブックスに登録がない書籍に関しては、書影その他情報が表示されない場合があります。</div>', unsafe_allow_html=True)
    # 6. 検索結果カード
    st.markdown('''
    <style>
      div.stButton > button {
        margin-bottom: 0 !important;
        margin-top: 0 !important;
        padding-top: 12px !important;
        padding-bottom: 12px !important;
      }
      .result-card {
        margin-top: 0 !important;
        padding-top: 0 !important;
        min-height: 126px !important;
        margin-bottom: 8px !important;
      }
      .card-content-row {
        display: flex;
        flex-direction: row;
        gap: 16px;
        align-items: center;
      }
      .card-thumbnail {
        width: 116px !important;
        height: 105px !important;
        flex-shrink: 0 !important;
      }
      .card-thumbnail img {
        width: 100% !important;
        height: 100% !important;
        object-fit: cover !important;
        border-radius: 8px !important;
      }
      .card-meta {
        font-family: 'Inter', sans-serif;
        color: #FFFFFF;
        font-size: 12px;
        display: flex;
        flex-direction: column;
        gap: 4px;
        text-align: left !important;
        align-items: flex-start;
      }
      .genre-tags-container {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-top: 2px;
      }
      .genre-tag {
        display: inline-flex;
        padding: 4px 6px;
        justify-content: center;
        align-items: center;
        gap: 10px;
        border-radius: 8px;
        background: #FFD293;
        color: #000000;
        font-size: 10px;
        font-weight: 500;
        white-space: nowrap;
      }
      .custom-note {
        font-family: 'Inter', sans-serif;
        color: #FFFFFF;
        font-size: 12px;
        line-height: 16px;
        margin: 8px 10px 0 10px;
        text-align: left !important;
      }
      /* 注意書きの左揃えを強制適用 */
      div[data-testid="stMarkdownContainer"] .custom-note,
      div[data-testid="stMarkdownContainer"] .custom-note * {
        text-align: left !important;
      }
    </style>
    ''', unsafe_allow_html=True)
    res = st.session_state.results
    if res.empty:
        st.warning("該当する本がありませんでした。")
    else:
        for i, row in res.iterrows():
            rakuten = fetch_rakuten_book(row.get("isbn", ""))
            placeholder_cover = "https://via.placeholder.com/116x105/D9D9D9/FFFFFF?text=No+Image"
            cover_url = rakuten.get("cover") or placeholder_cover
            genres = row.get('genres_list', [])
            genre_tags_html = "".join([f'<span class=\"genre-tag\">{g}</span>' for g in genres])
            # タイトル行のみクリッカブル
            if st.button(f"{row['rank']}位：『{row['title']}』／{row['author']}", key=f"title_btn_{i}"):
                to_detail(i)
                st.rerun()
            card_html = f'''
            <div class="result-card">
                <div class="card-content-row">
                    <div class="card-thumbnail">
                        <img src="{cover_url}" alt="{row['title']}" />
                    </div>
                    <div class="card-meta">
                        <div>キーワード登場回数：{row['count']}回</div>
                        <div>ジャンル</div>
                        <div class="genre-tags-container">
                            {genre_tags_html}
                        </div>
                        <div>出版社：{rakuten.get('publisher', '—')}</div>
                        <div>発行日：{rakuten.get('pubdate', '—')}</div>
                        <div>定価：{rakuten.get('price', '—')}円</div>
                    </div>
                </div>
            </div>
            '''
            st.markdown(card_html, unsafe_allow_html=True)

# ─── 9. 詳細画面 ───────────────────────────────────────
elif st.session_state.page == "detail":
    # ページトップに強制スクロール
    st.markdown('<script>window.scrollTo(0,0);</script>', unsafe_allow_html=True)
    if st.button("戻る", on_click=to_results_page, key="back_to_results"):
        pass
    res = st.session_state.results
    idx = st.session_state.detail_idx
    if idx is None or idx >= len(res):
        st.error("不正な選択です。")
    else:
        book = res.loc[idx]
        st.markdown(f'<div style="width:355px;margin:12px auto 0 auto;font-family:Inter,sans-serif;font-size:20px;color:#FFFFFF;line-height:28px;font-weight:bold;">{book["rank"]}位：『{book["title"]}』／{book["author"]}</div>', unsafe_allow_html=True)
        rakuten = fetch_rakuten_book(book.get("isbn", ""))
        # 書影とボタンを横並びで表示
        col1, col2 = st.columns([1,2])
        with col1:
            cover_url = rakuten.get("cover")
            if cover_url:
                st.image(cover_url, width=100)
        with col2:
            url = rakuten.get("affiliateUrl") or rakuten.get("itemUrl")
            if url:
                st.link_button("商品ページを開く（楽天ブックス）", url, type="primary")
            st.link_button("感想を投稿する（Googleフォーム）", "https://forms.gle/Eh3fYtnzSHmN3KMSA", type="primary")
        # 書誌情報
        st.write(f"**出版社**: {rakuten.get('publisher','—')}")
        st.write(f"**発行日**: {rakuten.get('pubdate','—')}")
        st.write(f"**定価**: {rakuten.get('price','—')} 円")
        st.write(f"**紹介文**: {rakuten.get('description','—')}")

        # レーダーチャート
        # 「エロ」を上として時計回りに配置
        # 「エロ」を上として時計回りに配置
        # 配列の順序で「エロ」を上に配置（Plotlyは最初の項目を上から開始）
        radar_vals = [book[c] for c in ["erotic","action","mystery","painful","esthetic","paranomal","insane","grotesque"]]
        radar_labels = ["エロ","アクション","謎","感動","耽美","霊怖","人怖","グロ"]
        # レーダーチャートタイトル
        st.markdown('''
        <style>
        div[data-testid="stMarkdownContainer"] > div {
            text-align: left !important;
        }
        </style>
        <div style="font-family:Inter,sans-serif;font-size:20px;color:#FFFFFF;line-height:28px;font-weight:bold;margin:20px 0 10px 0;">読み味レーダーチャート</div>
        ''', unsafe_allow_html=True)
        fig_radar = go.Figure(
            data=[go.Scatterpolar(r=radar_vals, theta=radar_labels, fill='toself')],
            layout=go.Layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 5],
                        showticklabels=False,  # 数字を非表示
                        showline=False,        # 軸線を非表示
                        ticks=''               # 目盛り線も非表示
                    )
                ),
                showlegend=False
            )
        )
        st.plotly_chart(fig_radar, use_container_width=True, config={"staticPlot": True})
        # ワードクラウド表示
        cnt = Counter(book['keywords'])
        for sw in STOPWORDS:
            cnt.pop(sw, None)
        if cnt:
            # ワードクラウド生成
            st.markdown('''
            <style>
            div[data-testid="stMarkdownContainer"] > div {
                text-align: left !important;
            }
            /* ワードクラウド画像の全画面拡大ボタンを非表示 */
            div[data-testid="stImage"] button {
                display: none !important;
            }
            </style>
            <div style="font-family:Inter,sans-serif;font-size:20px;color:#FFFFFF;line-height:28px;font-weight:bold;margin:20px 0 10px 0;">感想ワードクラウド</div>
            ''', unsafe_allow_html=True)
            wc = WordCloud(font_path='ipag.ttf', width=600, height=400, background_color='white', colormap='tab20').generate_from_frequencies(dict(cnt))
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.imshow(wc, interpolation='bilinear')
            ax.axis('off')
            st.pyplot(fig)
        else:
            st.info("有効なワードが見つかりませんでした。")
        # Twitter API連携部分は初期スコープ外のためコメントアウト
        # st.markdown("## 🐦 読了ツイート（最新5件）")
        # tweets = fetch_read_tweets(book['title'])
        # if tweets:
        #     for tw in tweets:
        #         tweet_md = (
        #             f"> {tw['text']}\n"
        #             f"— {tw['author_name']} (@{tw['author']}) {tw['created_at'].date()}, ❤️{tw['likes']}"
        #         )
        #         st.markdown(tweet_md)
        #         st.markdown("---")
        # else:
        #     st.info("該当する読了ツイートが見つかりませんでした。")
        # 戻る
