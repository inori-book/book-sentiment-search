import streamlit as st
import pandas as pd
from janome.tokenizer import Tokenizer
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go

# 1. ページ設定 (最初に必ず)
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide")

# 2. データ読み込み & 前処理
@st.cache_data
def load_data(path="sample05.csv"):
    df = pd.read_csv(path).fillna("")
    # genre 列をリスト化
    df["genres_list"] = (
        df["genre"].str.split(",").apply(lambda lst: [g.strip() for g in lst if g.strip()])
    )
    # Janome で形容詞抽出
    tokenizer = Tokenizer()
    def extract_adjs(text):
        return [
            t.base_form
            for t in tokenizer.tokenize(text)
            if t.part_of_speech.startswith("形容詞")
        ]
    df["adjectives"] = df["review"].apply(extract_adjs)
    return df

df = load_data()

# 3. ストップワード & 全形容詞リスト
STOPWORDS = {"ない", "っぽい"}
all_adjs = sorted({adj for lst in df["adjectives"] for adj in lst})
suggestions = [w for w in all_adjs if w not in STOPWORDS]

# 4. セッション状態初期化
if "page" not in st.session_state:
    st.session_state.page = "home"
if "results" not in st.session_state:
    st.session_state.results = pd.DataFrame()
if "adj" not in st.session_state:
    st.session_state.adj = ""
if "detail_idx" not in st.session_state:
    st.session_state.detail_idx = None

# 5. サイドバー: ジャンル絞り込み
st.sidebar.header("タグで絞り込み")
unique_genres = sorted({g for lst in df["genres_list"] for g in lst})
genres = st.sidebar.multiselect(
    "ジャンルを選択", options=unique_genres, default=[]
)

# 6. ページ遷移用関数
def to_results():
    adj = st.session_state.raw_input
    st.session_state.adj = adj
    # フィルタリング
    tmp = df.copy()
    if genres:
        tmp = tmp[tmp["genres_list"].apply(lambda gl: any(g in gl for g in genres))]
    # カウント
    tmp["count"] = tmp["adjectives"].apply(lambda lst: lst.count(adj))
    res = tmp[tmp["count"] > 0].sort_values("count", ascending=False)
    st.session_state.results = res.reset_index(drop=True)
    st.session_state.page = "results"


def to_detail(idx):
    st.session_state.detail_idx = idx
    st.session_state.page = "detail"


def to_home():
    st.session_state.page = "home"


def to_results_page():
    st.session_state.page = "results"

# 7. ホーム画面
if st.session_state.page == "home":
    st.title("📚 感想形容詞で探す本アプリ")
    st.write("感想に登場する形容詞から本を検索します。")
    # 入力
    st.text_input(
        "形容詞を入力してください", key="raw_input", placeholder="例：怖い"
    )
    # サジェスト
    filtered = [w for w in suggestions if w.startswith(st.session_state.raw_input)] if st.session_state.raw_input else suggestions
    st.selectbox(
        "候補から選ぶ", filtered, key="raw_select",
        help="Enterキーでも適用できます",
        on_change=lambda: st.session_state.update(raw_input=st.session_state.raw_select)
    )
    st.button("🔍 検索", on_click=to_results)

# 8. 検索結果画面
elif st.session_state.page == "results":
    st.title("🔎 検索結果ランキング")
    res = st.session_state.results
    if res.empty:
        st.warning("該当する本がありませんでした。")
    else:
        for i, row in res.iterrows():
            st.markdown(f"**{i+1}位：『{row['title']}』／{row['author']}（{row['count']}回）**")
            st.button("詳細を見る", key=f"btn_{i}", on_click=to_detail, args=(i,))
        if st.button("← ホームへ戻る"):
            to_home()

# 9. 詳細画面
elif st.session_state.page == "detail":
    res = st.session_state.results
    idx = st.session_state.detail_idx
    if idx is None or idx >= len(res):
        st.error("不正な選択です。")
    else:
        book = res.loc[idx]
        st.header(f"📖 『{book['title']}』 by {book['author']}")
        st.write(book['review'])
        # レーダーチャート
        labels = ["エロ", "グロ", "狂気", "超常", "耽美", "痛み"]
        values = [book[col] for col in ["erotic","grotesque","insane","paranomal","esthetic","painful"]]
        fig_radar = go.Figure(
            data=[go.Scatterpolar(r=values, theta=labels, fill='toself')],
            layout=go.Layout(title="読み味レーダーチャート", polar=dict(radialaxis=dict(visible=True)))
        )
        st.plotly_chart(fig_radar, use_container_width=True)
        # 頻出形容詞TOP5
        cnt = Counter(book['adjectives'])
        for sw in STOPWORDS:
            cnt.pop(sw, None)
        top5 = cnt.most_common(5)
        if top5:
            df5 = pd.DataFrame(top5, columns=["形容詞","回数"] )
            fig_bar = px.bar(df5, x="形容詞", y="回数", title="頻出形容詞TOP5")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("有効な形容詞が見つかりませんでした。")
        # Googleフォーム
        st.markdown("---")
        st.markdown("[✏️ あなたの感想を投稿する](https://forms.gle/Eh3fYtnzSHmN3KMSA)")
        # 戻る
        st.button("← 検索結果に戻る", on_click=to_results_page)
