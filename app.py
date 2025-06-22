import streamlit as st
import pandas as pd
from janome.tokenizer import Tokenizer
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go

# ─── 1. ページ設定（最初に） ─────────────────────────────────
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide")

# ─── 2. データ読み込み & 前処理 ─────────────────────────────────
@st.cache_data
def load_data(path: str = "sample06.csv") -> pd.DataFrame:
    df = pd.read_csv(path).fillna("")
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

# ─── 5. サイドバー: ジャンル絞り込み ─────────────────────────────
st.sidebar.header("タグで絞り込み")
unique_genres = sorted({g for lst in df["genres_list"] for g in lst})
genres = st.sidebar.multiselect("ジャンルを選択", options=unique_genres, default=[])

# ─── 6. ページ遷移用関数 ─────────────────────────────────────
def to_results():
    adj = st.session_state.raw_select or st.session_state.raw_input.strip()
    st.session_state.adj = adj
    tmp = df.copy()
    if genres:
        tmp = tmp[tmp["genres_list"].apply(lambda gl: any(g in gl for g in genres))]
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
            st.markdown(f"**{row['rank']}位：『{row['title']}』／{row['author']}（{row['count']}回）**")
            if st.button("詳細を見る", key=f"btn_{i}", on_click=to_detail, args=(i,)):
                pass

# ─── 9. 詳細画面 ───────────────────────────────────────
elif st.session_state.page == "detail":
    if st.button("戻る", on_click=to_results_page):
        pass
    res = st.session_state.results
    idx = st.session_state.detail_idx
    if idx is None or idx >= len(res):
        st.error("不正な選択です。")
    else:
        book = res.loc[idx]
        st.header(f"{book['rank']}位：『{book['title']}』／{book['author']}")
        # レーダーチャート
        radar_vals = [book[c] for c in ["erotic","grotesque","insane","paranomal","esthetic","painful"]]
        radar_labels = ["エロ","グロ","狂気","超常","耽美","痛み"]
        fig_radar = go.Figure(
            data=[go.Scatterpolar(r=radar_vals, theta=radar_labels, fill='toself')],
            layout=go.Layout(
                title="読み味レーダーチャート",
                polar=dict(radialaxis=dict(visible=True, range=[0, 5], tickfont=dict(color="#000000"))),
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
        # Googleフォームリンク
        st.markdown("---")
        st.markdown("[✏️ あなたの感想を投稿する](https://forms.gle/Eh3fYtnzSHmN3KMSA)")
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
