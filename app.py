import streamlit as st
import pandas as pd
from janome.tokenizer import Tokenizer
import plotly.express as px

# ——————————————————
# １）データ読み込み＆前処理
# ——————————————————
@st.cache(allow_output_mutation=True)
def load_data(path="sample05.csv"):
    df = pd.read_csv(path)
    # ジャンルをカンマ区切りでリスト化
    df["genre_list"] = (
        df["genre"]
        .fillna("")
        .apply(lambda s: [g.strip() for g in s.split(",") if g.strip()])
    )
    return df

df = load_data()

# プルダウン用ジャンル一覧
all_genres = sorted({g for genres in df["genre_list"] for g in genres})
all_genres.insert(0, "All")  # 先頭に「All」を追加

# セッションステート初期化
if "ranking" not in st.session_state:
    st.session_state.ranking = None
if "selected" not in st.session_state:
    st.session_state.selected = None

# ——————————————————
# ２）トップ画面（検索フォーム）
# ——————————————————
st.title("📚 感想形容詞で探す本アプリ")
with st.form("search_form"):
    genre_filter = st.selectbox("ジャンルを選択", all_genres)
    adj_input = st.text_input("形容詞を入力してください")
    submitted = st.form_submit_button("検索")

if submitted:
    # ジャンルフィルタ
    if genre_filter != "All":
        df_f = df[df["genre_list"].apply(lambda lst: genre_filter in lst)]
    else:
        df_f = df.copy()
    # マッチスコア計算（感想中の形容詞出現回数）
    df_f["match_score"] = df_f["review"].apply(lambda txt: txt.count(adj_input))
    df_f = df_f[df_f["match_score"] > 0].sort_values("match_score", ascending=False)
    st.session_state.ranking = df_f.reset_index(drop=True)
    st.session_state.selected = None

# ——————————————————
# ３）ランキング一覧画面
# ——————————————————
if st.session_state.ranking is not None and st.session_state.selected is None:
    st.subheader("🔢 検索結果ランキング")
    for idx, row in st.session_state.ranking.head(10).iterrows():
        label = f"{idx+1}位: {row['title']} / {row['author']} （{row['match_score']}回）"
        if st.button(label, key=idx):
            st.session_state.selected = row

# ——————————————————
# ４）詳細画面
# ——————————————————
if st.session_state.selected is not None:
    book = st.session_state.selected
    if st.button("◀ 戻る"):
        st.session_state.selected = None
        st.experimental_rerun()

    st.markdown(f"## 📖 『{book['title']}』 by {book['author']}")
    st.markdown(book["review"])

    # 形容詞Top5を抽出
    tokenizer = Tokenizer()
    tokens = [
        t.surface
        for t in tokenizer.tokenize(book["review"])
        if t.part_of_speech.startswith("形容詞,自立")
    ]
    top5 = (
        pd.Series(tokens)
        .value_counts()
        .head(5)
        .reset_index()
        .rename(columns={"index": "形容詞", 0: "出現回数"})
    )

    # — 棒グラフ —
    fig_bar = px.bar(
        top5,
        x="形容詞",
        y="出現回数",
        title="📊 感想でよく使われた形容詞 (Top 5)",
        labels={"出現回数": "回数"},
    )
    fig_bar.update_layout(
        font_family="sans-serif",
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # — レーダーチャート —
    radar_labels = ["エロ", "グロ", "狂気", "超常", "美的", "痛み"]
    radar_values = [
        book["erotic"],
        book["grotesque"],
        book["insane"],
        book["paranormal"],
        book["esthetic"],
        book["painful"],
    ]
    # 最後に最初の値を追記して閉ループさせる
    df_radar = pd.DataFrame({
        "カテゴリ": radar_labels + [radar_labels[0]],
        "値": radar_values + [radar_values[0]],
    })
    fig_radar = px.line_polar(
        df_radar,
        r="値",
        theta="カテゴリ",
        line_close=True,
        title="🏷️ レーダーチャート (6軸)",
    )
    fig_radar.update_traces(fill="toself")
    fig_radar.update_layout(
        font_family="sans-serif",
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig_radar, use_container_width=True)
