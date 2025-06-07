import streamlit as st
import pandas as pd
import plotly.express as px
from janome.tokenizer import Tokenizer

# --- ページ設定はスクリプト冒頭で ---
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide")

@st.cache_data
def load_data(path):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    return df

df = load_data("sample05.csv")

# --- サイドバー：ジャンル絞り込み ---
st.sidebar.title("ジャンルを選択")
all_genres = sorted({g for subs in df["genre"] for g in subs.split(",")})
all_genres.insert(0, "全て")
selected_genre = st.sidebar.selectbox("", all_genres)

# --- ヘッダー ---
st.title("📚 感想形容詞で探す本アプリ")
st.subheader("🔍 感想によく出る形容詞で本を探す")

# --- 検索フォーム ---
adj_input = st.text_input("形容詞を入力してください")
if st.button("検索"):
    # 押されたら前回の選択をクリアして検索ワードを保存
    st.session_state.pop("selected", None)
    st.session_state["search"] = adj_input

# --- ランキング画面 ---
if st.session_state.get("search"):
    adj = st.session_state["search"]

    # ジャンルフィルタ
    df_f = df.copy()
    if selected_genre != "全て":
        df_f = df_f[df_f["genre"].apply(lambda s: selected_genre in s.split(","))]

    # 形容詞抽出＋カウント
    tokenizer = Tokenizer()
    def extract_adjs(text):
        return [t.surface for t in tokenizer.tokenize(text) if t.part_of_speech.startswith("形容詞")]
    df_f["adjs"] = df_f["review"].map(extract_adjs)
    df_f["count"] = df_f["adjs"].map(lambda lst: lst.count(adj))

    hits = df_f[df_f["count"]>0].sort_values("count", ascending=False).reset_index(drop=True)

    st.subheader("🔢 検索結果ランキング")
    for idx, row in hits.iterrows():
        st.write(f"{idx+1}位: 『{row['title']}』／{row['author']} （{row['count']}回）")
        # on_click で selected をセットするだけ
        st.button(
            "詳細を見る",
            key=f"detail_{idx}",
            on_click=lambda i=idx: st.session_state.__setitem__("selected", i),
        )

# --- 詳細画面 ---
if "selected" in st.session_state:
    sel = st.session_state["selected"]
    rec = hits.loc[sel]

    st.markdown("---")
    st.header(f"📖 詳細：『{rec['title']}』 by {rec['author']}")
    st.write(rec["review"])

    # レーダーチャート
    axes = ["erotic","grotesque","insane","paranomal","esthetic","painful"]
    vals = [rec[a] for a in axes]
    rad_df = pd.DataFrame({"axis": axes, "value": vals})
    fig1 = px.line_polar(
        rad_df,
        r="value",
        theta="axis",
        line_close=True,
        title="レーダーチャート(6軸)"
    )
    st.plotly_chart(fig1, use_container_width=True)

    # 棒グラフ Top5
    vc = pd.Series(rec["adjs"]).value_counts().head(5).reset_index()
    vc.columns = ["形容詞", "回数"]
    fig2 = px.bar(vc, x="形容詞", y="回数", title="頻出形容詞TOP5")
    st.plotly_chart(fig2, use_container_width=True)
