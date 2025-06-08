import streamlit as st
import pandas as pd
from janome.tokenizer import Tokenizer
import plotly.express as px

# ————— Page config (must be first Streamlit command) —————
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide")

# ————— Constants & Stopwords —————
STOPWORDS = {"ない", "っぽい", "よい", "いい", "すごい", "おもしろい", "わかり", "ある"}
ADJ_POS = "形容詞"

# ————— Load data —————
@st.cache_data
def load_data():
    df = pd.read_csv("sample05.csv")
    # split comma-separated genres into list
    df["genre_list"] = df["genre"].str.split(",")
    return df

df = load_data()

# all possible genres
all_genres = sorted({g for sub in df["genre_list"] for g in sub})
genre_options = ["All"] + all_genres

# precompute all adjectives in dataset for suggestions
tokenizer = Tokenizer()
def extract_adjs(text):
    return [t.surface for t in tokenizer.tokenize(text) if t.part_of_speech.startswith(ADJ_POS)]

@st.cache_data
def all_adjectives():
    adjs = set()
    for text in df["review"]:
        adjs.update(extract_adjs(str(text)))
    return sorted(adjs)

ADJ_CANDIDATES = all_adjectives()

# ————— Session state initialization —————
if "page" not in st.session_state:
    st.session_state.page = "search"
if "results" not in st.session_state:
    st.session_state.results = []
if "selected_idx" not in st.session_state:
    st.session_state.selected_idx = None

# ————— Search UI —————
def show_search():
    st.title("📚 感想形容詞で探す本アプリ")
    st.write("感想に登場する形容詞から本を検索します。")
    col1, col2 = st.columns([2, 1])
    with col1:
        query = st.text_input("形容詞を入力してください", "")
    with col2:
        # suggestion dropdown
        suggestion = st.selectbox(
            "候補から選ぶ",
            options=[x for x in ADJ_CANDIDATES if x.startswith(query)] or ["（該当なし）"]
        )
    genre_sel = st.selectbox("ジャンルを選択", genre_options)
    if st.button("検索"):
        # final adjective choice
        adj = suggestion if suggestion in ADJ_CANDIDATES else query
        # filter by genre if needed
        d = df.copy()
        if genre_sel != "All":
            d = d[d["genre_list"].apply(lambda lst: genre_sel in lst)]
        # count occurrences per title
        counts = []
        for i, row in d.iterrows():
            cnt = extract_adjs(str(row["review"])).count(adj)
            if cnt > 0:
                counts.append((i, row["title"], row["author"], cnt))
        # sort
        counts.sort(key=lambda x: x[3], reverse=True)
        st.session_state.results = counts
        st.session_state.page = "results"
        st.session_state.adj = adj

# ————— Results UI —————
def show_results():
    st.title("🔍 検索結果ランキング")
    if not st.session_state.results:
        st.warning(f"「{st.session_state.adj}」を含む感想の本が見つかりませんでした。")
        if st.button("検索に戻る"):
            st.session_state.page = "search"
        return

    for rank, (idx, title, author, cnt) in enumerate(st.session_state.results, start=1):
        st.markdown(f"**{rank}位:** 『{title}』／{author} （{cnt}回）")
        if st.button(f"詳細を見る", key=f"detail_{rank}"):
            st.session_state.selected_idx = idx
            st.session_state.page = "detail"

    if st.button("検索に戻る"):
        st.session_state.page = "search"

# ————— Detail UI —————
def show_detail():
    idx = st.session_state.selected_idx
    row = df.loc[idx]
    st.title(f"📖 『{row['title']}』 by {row['author']}")
    st.write(str(row["review"]))

    # radar chart data
    radar_categories = ["erotic", "grotesque", "insane", "paranormal", "esthetic", "painful"]
    radar_values = [row.get(cat, 0) for cat in radar_categories]
    radar_df = pd.DataFrame({
        "value": radar_values,
        "category": radar_categories
    })
    fig_radar = px.line_polar(radar_df, r="value", theta="category", line_close=True)
    fig_radar.update_traces(fill="toself")
    fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True)))
    st.plotly_chart(fig_radar, use_container_width=True)

    # top adjectives for this book
    adjs = extract_adjs(str(row["review"]))
    freqs = pd.Series([a for a in adjs if a not in STOPWORDS]).value_counts().nlargest(5)
    bar_df = freqs.rename_axis("形容詞").reset_index(name="回数")
    fig_bar = px.bar(bar_df, x="形容詞", y="回数")
    fig_bar.update_layout(yaxis_title="回数")
    st.plotly_chart(fig_bar, use_container_width=True)

    if st.button("検索結果に戻る"):
        st.session_state.page = "results"

# ————— Page routing —————
if st.session_state.page == "search":
    show_search()
elif st.session_state.page == "results":
    show_results()
elif st.session_state.page == "detail":
    show_detail()
