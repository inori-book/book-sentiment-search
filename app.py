import streamlit as st
import pandas as pd
import MeCab
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import plotly.express as px

# ── ページ設定（必ず最初に記述） ───────────────────────
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide")

# ── 日本語フォント設定 ─────────────────────────────────
plt.rcParams['font.family'] = [
    "Yu Gothic",       # Windows
    "Hiragino Sans",   # macOS
    "MS Gothic",       # 古いWindows
    "IPAPGothic",      # Linux
    "Noto Sans CJK JP" # 共通
]
plt.rcParams['axes.unicode_minus'] = False

# ── 定数 ───────────────────────────────────────────────
STOPWORDS = {"ない", "ぬるい", "っぽい", "よかった", "良かった"}

# ── データ読み込み ────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv("sample05.csv")
    df["genres"] = df["genre"].str.split(",")
    return df

@st.cache_data
def extract_unique_adjectives(df):
    tagger = MeCab.Tagger()
    adj_set = set()
    for text in df["review"]:
        node = tagger.parseToNode(text)
        while node:
            feats = node.feature.split(",")
            if feats[0] == "形容詞":
                base = feats[6] if feats[6] != "*" else node.surface
                if base not in STOPWORDS:
                    adj_set.add(base)
            node = node.next
    return sorted(adj_set)

df = load_data()
all_adjs = extract_unique_adjectives(df)

# ── サイドバー：ジャンル選択 ─────────────────────────────
unique_genres = sorted({g for sub in df["genres"] for g in sub})
genre_options = ["All"] + unique_genres

# ── セッション初期化 ───────────────────────────────────
if 'page' not in st.session_state:
    st.session_state.page = 'search'
if 'search_term' not in st.session_state:
    st.session_state.search_term = ""
if 'genre_sel' not in st.session_state:
    st.session_state.genre_sel = "All"
if 'selected_idx' not in st.session_state:
    st.session_state.selected_idx = None

# ── ページ切替コールバック ─────────────────────────────
def go_to_search():
    st.session_state.page = 'search'

def go_to_ranking():
    st.session_state.page = 'ranking'

def go_to_detail(idx):
    st.session_state.selected_idx = idx
    st.session_state.page = 'detail'

# ── 検索ページ ─────────────────────────────────────────
if st.session_state.page == 'search':
    st.sidebar.title("🔎 条件で絞り込み")
    st.session_state.genre_sel = st.sidebar.selectbox("ジャンルを選択", genre_options)

    st.title("📚 感想形容詞で探す本アプリ")
    st.write("感想に登場する形容詞から本を検索します。")

    term_input = st.text_input("形容詞を入力してください")
    # サジェスト候補
    suggestions = [a for a in all_adjs if term_input in a] if term_input else []
    sel_adj = st.selectbox("候補から選ぶ", suggestions, key="adj_select")

    if st.button("検索"):
        st.session_state.search_term = sel_adj
        go_to_ranking()

# ── ランキングページ ───────────────────────────────────
elif st.session_state.page == 'ranking':
    term = st.session_state.search_term
    genre_sel = st.session_state.genre_sel

    st.title("🔍 検索結果ランキング")

    # ジャンルフィルタ
    if genre_sel != "All":
        df_filtered = df[df["genres"].apply(lambda gl: genre_sel in gl)]
    else:
        df_filtered = df

    # カウント集計
    results = []
    for idx, row in df_filtered.iterrows():
        cnt = row["review"].count(term)
        if cnt > 0:
            results.append((idx, row["title"], row["author"], cnt))
    results.sort(key=lambda x: x[3], reverse=True)

    if not results:
        st.write("該当する本はありませんでした。")
        st.button("← 戻る", on_click=go_to_search)
    else:
        for rank, (idx, title, author, cnt) in enumerate(results, start=1):
            st.write(f"{rank}位: 『{title}』／{author} （{cnt}回）")
            if st.button("詳細を見る", key=f"dtl_{idx}"):
                go_to_detail(idx)

# ── 詳細ページ ─────────────────────────────────────────
elif st.session_state.page == 'detail':
    idx = st.session_state.selected_idx
    row = df.loc[idx]

    st.header(f"📖 『{row['title']}』 by {row['author']}")
    st.write(row["review"])

    # レーダーチャート
    cats = ["erotic","grotesque","insane","paranormal","esthetic","painful"]
    labels_jp = ["エロ","グロ","狂気","超常","美的","痛々しい"]
    vals = [row[c] for c in cats]
    angles = np.linspace(0, 2*np.pi, len(labels_jp), endpoint=False).tolist()
    vals += vals[:1]
    angles += angles[:1]

    fig = plt.figure(figsize=(4,4))
    ax = fig.add_subplot(111, polar=True)
    ax.plot(angles, vals, marker='o')
    ax.fill(angles, vals, alpha=0.3)
    ax.set_thetagrids([a*180/np.pi for a in angles[:-1]], labels_jp)
    st.pyplot(fig)

    # 棒グラフTOP5
    tagger = MeCab.Tagger()
    cnts = {}
    node = tagger.parseToNode(row["review"])
    while node:
        feats = node.feature.split(",")
        if feats[0] == "形容詞":
            base = feats[6] if feats[6] != "*" else node.surface
            if base not in STOPWORDS:
                cnts[base] = cnts.get(base,0) + 1
        node = node.next
    top5 = sorted(cnts.items(), key=lambda x: x[1], reverse=True)[:5]
    df_top5 = pd.DataFrame(top5, columns=["形容詞","回数"])

    fig_bar = px.bar(df_top5, x="形容詞", y="回数")
    fig_bar.update_layout(
        title_text="頻出形容詞TOP5",
        font_family="Noto Sans CJK JP",
        xaxis_title="形容詞",
        yaxis_title="回数"
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # 戻るボタン
    st.button("← 検索に戻る", on_click=go_to_search)
