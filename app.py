import streamlit as st
import pandas as pd
from janome.tokenizer import Tokenizer
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go

#── 1. ページ設定は必ず一番上 ───────────────────────────
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide")

#── 2. キャッシュデータ読み込み・前処理 ─────────────────
@st.cache_data
def load_and_prepare_data(path="sample05.csv"):
    df = pd.read_csv(path)
    df = df.fillna("")  # 空セル対策

    # ジャンル文字列をリスト化
    df["genres_list"] = df["genre"].apply(lambda s: [g.strip() for g in s.split(",") if g.strip()])

    # Janome で各レビューから形容詞を抽出
    tokenizer = Tokenizer()
    def extract_adjs(text):
        return [
            t.base_form
            for t in tokenizer.tokenize(text)
            if t.part_of_speech.startswith("形容詞")
        ]
    df["adjectives"] = df["review"].apply(extract_adjs)

    return df

df = load_and_prepare_data()

#── 3. 全候補形容詞＆ストップワード ───────────────────
# 全レビューに出現する形容詞をユニークに
all_adjs = sorted({adj for lst in df["adjectives"] for adj in lst})
STOPWORDS = {"ない", "っぽい"}  # 今まで不要とされたもの
suggestions = [w for w in all_adjs if w not in STOPWORDS]

#── 4. セッションステート初期化 ───────────────────────
if "page" not in st.session_state:
    st.session_state.page = "home"
if "results" not in st.session_state:
    st.session_state.results = pd.DataFrame()
if "selected_adj" not in st.session_state:
    st.session_state.selected_adj = ""
if "selected_title" not in st.session_state:
    st.session_state.selected_title = ""

#── 5. サイドバー：ジャンル絞り込み ────────────────────
st.sidebar.header("タグで絞り込み")
unique_genres = sorted({g for lst in df["genres_list"] for g in lst})
genres = st.sidebar.multiselect(
    "ジャンルを選択",
    options=unique_genres,
    default=[],
)

#── 6. ページ遷移関数 ────────────────────────────────
def do_search():
    st.session_state.selected_adj = st.session_state.raw_input
    adj = st.session_state.selected_adj

    # 絞り込み
    filtered = df.copy()
    if genres:
        filtered = filtered[
            filtered["genres_list"].apply(lambda gl: any(g in gl for g in genres))
        ]

    # カウント＆ソート
    filtered["count"] = filtered["adjectives"].apply(
        lambda lst: lst.count(adj)
    )
    results = filtered[filtered["count"] > 0].sort_values(
        "count", ascending=False
    )
    st.session_state.results = results.reset_index(drop=True)
    st.session_state.page = "results"

def go_detail(idx: int):
    st.session_state.selected_title = st.session_state.results.loc[idx, "title"]
    st.session_state.page = "detail"

def go_back():
    st.session_state.page = "results"

#── 7. ホーム画面 ─────────────────────────────────
if st.session_state.page == "home":
    st.title("📚 感想形容詞で探す本アプリ")
    st.write("感想に登場する形容詞から本を検索します。")

    # 自由入力＋サジェスト
    st.text_input(
        "形容詞を入力してください",
        key="raw_input",
        placeholder="例：怖い",
    )
    # 入力値に応じて候補を絞り込む
    filtered_sugs = [
        w for w in suggestions
        if w.startswith(st.session_state.raw_input)
    ] if st.session_state.raw_input else suggestions

    st.selectbox(
        "候補から選ぶ",
        options=filtered_sugs,
        key="selected_adj_box",
        label_visibility="visible",
        on_change=lambda: st.session_state.update(raw_input=st.session_state.selected_adj_box)
    )

    st.button("🔍 検索", on_click=do_search)

#── 8. 検索結果ランキング画面 ─────────────────────────
elif st.session_state.page == "results":
    st.title("🔎 検索結果ランキング")
    res = st.session_state.results
    if res.empty:
        st.warning("該当する本がありませんでした。")
    else:
        for idx, row in res.iterrows():
            rank = idx + 1
            line = f"{rank}位：『{row['title']}』／{row['author']}（{row['count']}回）"
            st.markdown(f"**{line}**")
            st.button("詳細を見る", key=f"btn_{idx}", on_click=go_detail, args=(idx,))

#── 9. 詳細画面 ───────────────────────────────────
elif st.session_state.page == "detail":
    # 戻るボタン
    if st.button("← 戻る"):
        go_back()
        st.experimental_rerun()

    title = st.session_state.selected_title
    book = df[df["title"] == title].iloc[0]
    st.header(f"📖 『{book['title']}』 by {book['author']}")
    st.write(book["review"])

    # ── レーダーチャート ─────────────────────────
    radar_vals = [
        book["erotic"],
        book["grotesque"],
        book["insane"],
        book["paranomal"],
        book["esthetic"],
        book["painful"],
    ]
    radar_labels = ["エロ", "グロ", "狂気", "超常", "耽美", "痛み"]
    radar = go.Figure(
        data=[
            go.Scatterpolar(
                r=radar_vals,
                theta=radar_labels,
                fill="toself",
                name=book["title"]
            )
        ],
        layout=go.Layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, max(radar_vals)+1])),
            showlegend=False,
            title="読み味レーダーチャート"
        )
    )
    st.plotly_chart(radar, use_container_width=True)

    # ── 頻出形容詞TOP5 棒グラフ ─────────────────
    cnt = Counter(book["adjectives"])
    # ストップワード除外
    for w in STOPWORDS:
        cnt.pop(w, None)
    top5 = cnt.most_common(5)
    if top5:
        df_top5 = pd.DataFrame(top5, columns=["形容詞", "回数"])
        bar = px.bar(
            df_top5,
            x="形容詞",
            y="回数",
            labels={"回数": "回数", "形容詞": "形容詞"},
            title="頻出形容詞TOP5"
        )
        st.plotly_chart(bar, use_container_width=True)
    else:
        st.info("この本には有効な形容詞が見つかりませんでした。")

    # ── Googleフォームへのリンク ───────────────────────
    form_url = "https://forms.gle/Eh3fYtnzSHmN3KMSA"
    st.markdown("---")
    st.markdown(f"[✏️ あなたの感想を投稿する](<{form_url}>)")
