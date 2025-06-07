import streamlit as st
import pandas as pd
import plotly.express as px
from janome.tokenizer import Tokenizer

# キャッシュ設定（st.cache_data に移行）
@st.cache_data
def load_data(path):
    df = pd.read_csv(path)
    # 列名の前後空白を除去
    df.columns = [col.strip() for col in df.columns]
    return df

# データ読み込み
DATA_PATH = "sample05.csv"
df = load_data(DATA_PATH)

# ページ設定
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide")
st.title("📚 感想形容詞で探す本アプリ")

# サイドバー：ジャンル選択
genres = sorted({g for subs in df["genre"] for g in subs.split(",")})
genres.insert(0, "全て")
selected_genre = st.sidebar.selectbox("ジャンルを選択", genres)

# メイン：検索フォーム
st.subheader("🔍 感想によく出る形容詞で本を探す")
adj_input = st.text_input("形容詞を入力してください")
if st.button("検索"):
    # ジャンル絞り込み
    if selected_genre != "全て":
        df = df[df["genre"].apply(lambda s: selected_genre in s.split(","))]

    # 形容詞抽出
    tokenizer = Tokenizer()
    def extract_adjs(text):
        return [
            tok.surface for tok in tokenizer.tokenize(text)
            if tok.part_of_speech.startswith("形容詞")
        ]
    df["adjectives"] = df["review"].apply(extract_adjs)

    # 指定形容詞の出現回数をカウント
    df["count"] = df["adjectives"].apply(lambda lst: lst.count(adj_input))
    hits = df[df["count"] > 0].copy()

    # ランキング
    ranking = hits.sort_values("count", ascending=False)[["title", "author", "count"]]
    st.subheader("🔢 検索結果ランキング")
    for i, row in ranking.iterrows():
        st.write(f"{i+1}位: {row['title']} / {row['author']} ({row['count']}回)")
        if st.button(f"詳細を見る: {row['title']}", key=i):
            st.session_state.selected = i

    # 詳細画面
    if "selected" in st.session_state:
        sel_idx = st.session_state.selected
        sel_book = ranking.iloc[sel_idx]
        orig_idx = sel_book.name
        rec = hits.loc[orig_idx]

        st.markdown("---")
        st.header(f"📖 詳細ページ：『{sel_book['title']}』 by {sel_book['author']}")
        st.write(rec["review"])

        # レーダーチャート
        axes = ["erotic", "grotesque", "insane", "paranomal", "esthetic", "painful"]
        values = [rec[a] for a in axes]
        radar_df = pd.DataFrame({"axis": axes, "value": values})
        fig_rad = px.line_polar(
            radar_df, r="value", theta="axis", line_close=True,
            title="レーダーチャート（6軸）"
        )
        st.plotly_chart(fig_rad, use_container_width=True)

        # 頻出形容詞トップ5
        adj_counts = pd.Series(rec["adjectives"]).value_counts().head(5).reset_index()
        adj_counts.columns = ["形容詞", "出現回数"]
        fig_bar = px.bar(
            adj_counts, x="形容詞", y="出現回数",
            labels={"出現回数": "回数"},
            title="頻出形容詞Top5"
        )
        st.plotly_chart(fig_bar, use_container_width=True)
