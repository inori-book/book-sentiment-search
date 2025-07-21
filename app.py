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
def load_data(path: str = "sample07.csv") -> pd.DataFrame:
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

# ─── 5. サイドバー: ジャンル・スペック絞り込み ─────────────────────────────
# st.sidebar.header("絞り込み")
# st.sidebar.subheader("ジャンル")
# unique_genres = sorted({g for lst in df["genres_list"] for g in lst})
# genres = st.sidebar.multiselect("ジャンル", options=unique_genres, default=[])
#
# st.sidebar.subheader("スペック")
# spec_keys = ["erotic", "grotesque", "insane", "paranomal", "esthetic", "painful"]
# spec_labels = ["エロ", "グロ", "狂気", "超常", "耽美", "痛み"]
# if "spec_ranges" not in st.session_state:
#     st.session_state.spec_ranges = {k: (0, 5) for k in spec_keys}
# for k, label in zip(spec_keys, spec_labels):
#     st.session_state.spec_ranges[k] = st.sidebar.slider(label, 0, 5, (0, 5), key=f"slider_{k}")

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
def to_results():
    adj = st.session_state.raw_select or st.session_state.raw_input.strip()
    st.session_state.adj = adj
    tmp = df.copy()
    # ジャンル・スペック絞り込みはサイドバー削除のためスキップ
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
    st.markdown('<div class="custom-title">YOMIAJI <span class="colon">:</span> Horror</div>', unsafe_allow_html=True)
    # リード文
    st.markdown('<div class="custom-lead">読み味から本が検索できるサービスです。<br>怖くて耽美でインモラルな本が探せます。</div>', unsafe_allow_html=True)

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
    # Googleフォームボタン（<a>＋CSSで実装）
    st.markdown('<a href="https://forms.gle/Eh3fYtnzSHmN3KMSA" target="_blank" class="custom-btn">Googleフォーム</a>', unsafe_allow_html=True)

# ─── 8. 検索結果画面 ───────────────────────────────────
elif st.session_state.page == "results":
    # 検索バー（flexレイアウト）
    adj = st.session_state.get('adj', '')
    st.markdown(f'''
    <div style="width:375px; padding:10px; display:flex; align-items:center; gap:8px; margin:0 auto;">
      <button onclick="window.parent.postMessage({{func: 'to_home'}}, '*');" style="background:none;border:none;font-size:24px;cursor:pointer;padding:0 8px 0 0;">←</button>
      <input type="text" value="{adj}" readonly style="flex:1; font-size:16px; padding:8px; border-radius:6px; border:1px solid #ccc; background:#222; color:#fff;" />
    </div>
    ''', unsafe_allow_html=True)
    # 絞り込みボタン（カスタムHTML+CSSで実装）
    st.markdown('''
    <style>
      .custom-filter-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        position: absolute;
        left: 42px;
        top: 103px;
        width: 98px;
        height: 32px;
        background: #FF9500;
        border-radius: 8px;
        padding: 2px 4px 2px 10px;
        border: none;
        cursor: pointer;
        box-shadow: none;
        outline: none;
        z-index: 10;
      }
      .custom-filter-btn:hover {
        opacity: 0.9;
      }
      .custom-filter-btn .icon {
        width: 20px;
        height: 20px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        margin-right: 4px;
      }
      .custom-filter-btn .icon svg {
        width: 20px;
        height: 20px;
        fill: #17182A;
        display: block;
      }
      .custom-filter-btn .label {
        font-family: Inter, sans-serif;
        font-size: 12px;
        line-height: 20px;
        color: #17182A;
        font-weight: 400;
        display: inline-block;
        vertical-align: middle;
      }
    </style>
    <button class="custom-filter-btn" onclick="window.parent.postMessage({func: 'show_filter_modal'}, '*');">
      <span class="icon">
        <svg viewBox="0 0 24 24"><path d="M3 5h18v2H3V5zm4 7h10v2H7v-2zm4 7h2v2h-2v-2z"/></svg>
      </span>
      <span class="label">絞り込み</span>
    </button>
    ''', unsafe_allow_html=True)
    # --- ここから下、再検索や入力欄・検索ボタンなどを削除 ---
    # if st.button("戻る", on_click=to_home):
    #     pass
    # st.markdown("## 🔍 再検索")
    # st.session_state.raw_input = st.text_input(
    #     "形容詞を入力してください", value=st.session_state.raw_input, key="raw_input_results"
    # )
    # filtered = [w for w in suggestions if w.startswith(st.session_state.raw_input)] if st.session_state.raw_input else suggestions
    # st.session_state.raw_select = st.selectbox(
    #     "候補から選ぶ", options=[""] + filtered, index=0, key="raw_select_results"
    # )
    # if st.button("🔍 検索", on_click=to_results, key="search_btn_results"):
    #     pass
    # パンくずリストをタイトルの「前」に移動
    st.markdown(f'''
    <style>
      .custom-breadcrumb {{
        width: 355px;
        height: 28px;
        font-family: Inter, sans-serif;
        font-size: 12px;
        line-height: 28px;
        color: #17182A;
        display: flex;
        align-items: center;
        margin: 16px auto 0 auto;
        z-index: 10;
      }}
      .custom-breadcrumb .home-link {{
        color: #17182A;
        text-decoration: underline;
        cursor: pointer;
      }}
      .custom-breadcrumb .sep {{
        margin: 0 4px;
      }}
      .custom-breadcrumb .kwd {{
        color: #17182A;
      }}
    </style>
    <div class="custom-breadcrumb">
      <span class="home-link" onclick="window.parent.postMessage({{func: 'to_home'}}, '*');">ホーム</span>
      <span class="sep">＞</span>
      検索キーワード「<span class="kwd">{adj}</span>」
    </div>
    ''', unsafe_allow_html=True)
    st.title("検索結果ランキング")
    res = st.session_state.results
    if res.empty:
        st.warning("該当する本がありませんでした。")
    else:
        for i, row in res.iterrows():
            if st.button(f"{row['rank']}位：『{row['title']}』／{row['author']}（{row['count']}回）", key=f"title_btn_{i}"):
                to_detail(i)
                st.rerun()
            rakuten = fetch_rakuten_book(row.get("isbn", ""))
            if rakuten.get("cover"):
                st.image(rakuten["cover"], width=120)
            with st.expander("▼作品紹介"):
                st.write(rakuten.get("description", "—"))

# ─── 9. 詳細画面 ───────────────────────────────────────
elif st.session_state.page == "detail":
    # ページトップに強制スクロール
    st.markdown('<script>window.scrollTo(0,0);</script>', unsafe_allow_html=True)
    if st.button("戻る", on_click=to_results_page):
        pass
    res = st.session_state.results
    idx = st.session_state.detail_idx
    if idx is None or idx >= len(res):
        st.error("不正な選択です。")
    else:
        book = res.loc[idx]
        st.header(f"{book['rank']}位：『{book['title']}』／{book['author']}")
        rakuten = fetch_rakuten_book(book.get("isbn", ""))
        # 書影とボタンを横並びで表示
        col1, col2 = st.columns([1,2])
        with col1:
            cover_url = rakuten.get("cover")
            if cover_url:
                st.image(cover_url, width=100)
        with col2:
            btn1 = f'<a href="{rakuten.get("affiliateUrl") or rakuten.get("itemUrl")}" target="_blank" style="display:inline-block;padding:16px 32px;background:#FFC107;color:#222;font-weight:bold;border-radius:8px;text-decoration:none;margin-bottom:12px;">商品ページを開く（楽天ブックス）<span style="margin-left:8px;">&#x1F517;</span></a>'
            btn2 = '<a href="https://forms.gle/Eh3fYtnzSHmN3KMSA" target="_blank" style="display:inline-block;padding:16px 32px;background:#FFC107;color:#222;font-weight:bold;border-radius:8px;text-decoration:none;">感想を投稿する（Googleフォーム）<span style="margin-left:8px;">&#x1F517;</span></a>'
            st.markdown(btn1, unsafe_allow_html=True)
            st.markdown(btn2, unsafe_allow_html=True)
        # 書誌情報
        st.write(f"**出版社**: {rakuten.get('publisher','—')}")
        st.write(f"**発行日**: {rakuten.get('pubdate','—')}")
        st.write(f"**定価**: {rakuten.get('price','—')} 円")
        st.write(f"**紹介文**: {rakuten.get('description','—')}")

        # レーダーチャート
        radar_vals = [book[c] for c in ["erotic","grotesque","insane","paranomal","esthetic","painful"]]
        radar_labels = ["エロ","グロ","狂気","超常","耽美","痛み"]
        fig_radar = go.Figure(
            data=[go.Scatterpolar(r=radar_vals, theta=radar_labels, fill='toself')],
            layout=go.Layout(
                title="読み味レーダーチャート",
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
            st.markdown("### 感想ワードクラウド")
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
