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

load_dotenv()

# ─── 1. ページ設定（最初に） ─────────────────────────────────
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide")

# ─── 2. データ読み込み & 前処理 ─────────────────────────────────
@st.cache_data
def load_data(path: str = "sample07.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ISBN": str}).fillna("")
    df.columns = [col.lower() for col in df.columns]  # 列名を小文字に統一
    # ジャンルをリスト化
    df["genres_list"] = df["genre"].str.split(",").apply(lambda lst: [g.strip() for g in lst if g.strip()])
    # Janome で形容詞抽出
    tokenizer = Tokenizer()
    def extract_adjs(text: str) -> list[str]:
        return [t.base_form for t in tokenizer.tokenize(text) if t.part_of_speech.startswith("形容詞")]
    df["adjectives"] = df["review"].apply(extract_adjs)
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
all_adjs = sorted({adj for lst in df["adjectives"] for adj in lst})
suggestions = [w for w in all_adjs if w not in STOPWORDS]

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
st.sidebar.header("絞り込み")
st.sidebar.subheader("ジャンル")
unique_genres = sorted({g for lst in df["genres_list"] for g in lst})
genres = st.sidebar.multiselect("ジャンル", options=unique_genres, default=[])

st.sidebar.subheader("スペック")
spec_keys = ["erotic", "grotesque", "insane", "paranomal", "esthetic", "painful"]
spec_labels = ["エロ", "グロ", "狂気", "超常", "耽美", "痛み"]
if "spec_ranges" not in st.session_state:
    st.session_state.spec_ranges = {k: (0, 5) for k in spec_keys}
for k, label in zip(spec_keys, spec_labels):
    st.session_state.spec_ranges[k] = st.sidebar.slider(label, 0, 5, (0, 5), key=f"slider_{k}")

# スマホでサイドバーをデフォルトで格納し、スライダーに余白を追加するカスタムCSS
st.markdown('''
    <style>
    /* スマホでサイドバーをデフォルトで閉じる */
    @media (max-width: 900px) {
        section[data-testid="stSidebar"] {
            transform: translateX(-100%);
        }
        /* サイドバー開閉ボタンを表示 */
        button[aria-label="Open sidebar"] {
            display: block;
        }
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
    # ジャンル絞り込み
    if genres:
        tmp = tmp[tmp["genres_list"].apply(lambda gl: any(g in gl for g in genres))]
    # スペック範囲絞り込み
    for k in spec_keys:
        min_v, max_v = st.session_state.spec_ranges[k]
        tmp = tmp[(tmp[k] >= min_v) & (tmp[k] <= max_v)]
    # 形容詞絞り込み
    tmp["count"] = tmp["adjectives"].apply(lambda lst: lst.count(adj))
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
    st.title("📚 感想形容詞で探す本アプリ")
    st.write("感想に登場する形容詞から本を検索します。")
    st.session_state.raw_input = st.text_input(
        "形容詞を入力してください", value=st.session_state.raw_input, key="raw_input_input"
    )
    filtered = [w for w in suggestions if w.startswith(st.session_state.raw_input)] if st.session_state.raw_input else suggestions
    st.session_state.raw_select = st.selectbox(
        "候補から選ぶ", options=[""] + filtered, index=0, key="raw_select_box"
    )
    if st.button("🔍 検索", on_click=to_results):
        pass

# ─── 8. 検索結果画面 ───────────────────────────────────
elif st.session_state.page == "results":
    if st.button("戻る", on_click=to_home):
        pass
    st.title("🔎 検索結果ランキング")
    res = st.session_state.results
    if res.empty:
        st.warning("該当する本がありませんでした。")
    else:
        for i, row in res.iterrows():
            # タイトルをボタンで表示し、クリックで詳細遷移（シングルクリックで動作）
            if st.button(f"{row['rank']}位：『{row['title']}』／{row['author']}（{row['count']}回）", key=f"title_btn_{i}"):
                to_detail(i)
                st.experimental_rerun()
            # 書影も表示
            rakuten = fetch_rakuten_book(row.get("isbn", ""))
            if rakuten.get("cover"):
                st.image(rakuten["cover"], width=120)
            # 紹介文をトグル展開
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
        st.plotly_chart(fig_radar, use_container_width=True)
        # 棒グラフ TOP5
        cnt = Counter(book['adjectives'])
        for sw in STOPWORDS:
            cnt.pop(sw, None)
        top5 = cnt.most_common(5)
        if top5:
            df5 = pd.DataFrame(top5, columns=["形容詞","回数"])
            fig_bar = go.Figure(
                data=[go.Bar(x=df5["形容詞"], y=df5["回数"])],
                layout=go.Layout(
                    title="頻出形容詞TOP5",
                    yaxis=dict(tickmode='linear', dtick=1)
                )
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("有効な形容詞が見つかりませんでした。")
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
