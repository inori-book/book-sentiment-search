import streamlit as st
import pandas as pd
import numpy as np
from janome.tokenizer import Tokenizer
import plotly.express as px
import matplotlib.pyplot as plt

# ─── ページ設定（Must be first Streamlit command） ─────────────────
st.set_page_config(page_title="感想形容詞で探す本アプリ", layout="wide")

# ─── 日本語フォント設定 ───────────────────────────────────────────
plt.rcParams['font.family'] = [
    "Yu Gothic", "Hiragino Sans", "MS Gothic",
    "IPAPGothic", "Noto Sans CJK JP"
]
plt.rcParams['axes.unicode_minus'] = False

# ─── 定数 ─────────────────────────────────────────────────────────
DATA_PATH = "sample05.csv"
FORM_URL  = "https://forms.gle/Eh3fYtnzSHmN3KMSA"
STOPWORDS = {"ない", "っぽい", "良い", "いい", "すごい", "おもしろい"}

# ─── データ読み込み ───────────────────────────────────────────────
@st.cache_data
def load_data(path):
    df = pd.read_csv(path)
    df["genre_list"] = df["genre"].str.split(",")
    return df

df = load_data(DATA_PATH)

# ─── Janome で形容詞抽出 ───────────────────────────────────────────
tokenizer = Tokenizer()

def extract_adjs(text):
    return [
        t.surface for t in tokenizer.tokenize(str(text))
        if t.part_of_speech.startswith("形容詞") and t.surface not in STOPWORDS
    ]

@st.cache_data
def get_candidates(data):
    c = set()
    for rev in data["review"]:
        c.update(extract_adjs(rev))
    return sorted(c)

ADJ_CANDIDATES = get_candidates(df)

# ─── セッション初期化 ─────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "selected_idx" not in st.session_state:
    st.session_state.selected_idx = None
if "adj" not in st.session_state:
    st.session_state.adj = ""

# ─── サイドバー：ジャンル選択 ─────────────────────────────────────
genres = ["All"] + sorted({g for lst in df["genre_list"] for g in lst})
selected_genre = st.sidebar.selectbox("ジャンルを選択", genres)

# ─── メイン画面 ─────────────────────────────────────────────────
st.title("📚 感想形容詞で探す本アプリ")
st.write("感想に登場する形容詞から本を検索します。")

# ─── フロー制御 ─────────────────────────────────────────────────
# 1) 検索前
if st.session_state.results is None:
    query = st.text_input("形容詞を入力してください", key="query")
    suggestions = [w for w in ADJ_CANDIDATES if w.startswith(query)] if query else []
    adj_choice = st.selectbox("候補から選ぶ", [""] + suggestions, key="choice")
    if st.button("🔍 検索"):
        target = adj_choice or query.strip()
        if not target:
            st.warning("形容詞を入力または選択してください。")
        else:
            # フィルタリング
            dff = df.copy()
            if selected_genre != "All":
                dff = dff[dff["genre_list"].apply(lambda lst: selected_genre in lst)]
            # 出現回数集計
            hits = []
            for i, row in dff.iterrows():
                cnt = extract_adjs(row["review"]).count(target)
                if cnt > 0:
                    hits.append((i, row["title"], row["author"], cnt))
            hits.sort(key=lambda x: x[3], reverse=True)
            st.session_state.results = hits
            st.session_state.adj = target
            st.experimental_rerun()

# 2) ランキング表示
elif st.session_state.selected_idx is None:
    adj = st.session_state.adj
    st.subheader(f"🔎 「{adj}」がよく登場する本ランキング")
    if not st.session_state.results:
        st.info(f"「{adj}」を含む本は見つかりませんでした。")
        if st.button("検索に戻る"):
            st.session_state.results = None
            st.experimental_rerun()
    else:
        for rank, (idx, title, author, cnt) in enumerate(st.session_state.results, start=1):
            st.write(f"**{rank}位**: 『{title}』／{author} （{cnt}回）")
            if st.button("詳細を見る", key=f"btn_{idx}"):
                st.session_state.selected_idx = idx
                st.experimental_rerun()
        if st.button("検索に戻る", key="back1"):
            st.session_state.results = None
            st.experimental_rerun()

# 3) 詳細画面
else:
    idx = st.session_state.selected_idx
    row = df.loc[idx]
    st.header(f"📖 『{row['title']}』 by {row['author']}")
    st.write(row["review"])

    # レーダーチャート
    cats = ["erotic","grotesque","insane","paranormal","esthetic","painful"]
    labels_jp = ["エロ","グロ","狂気","超常","美的","痛み"]
    vals = [row.get(c, 0) for c in cats]
    angles = np.linspace(0, 2*np.pi, len(cats), endpoint=False).tolist()
    vals += vals[:1]; angles += angles[:1]
    fig1, ax1 = plt.subplots(subplot_kw={"polar": True}, figsize=(4,4))
    ax1.plot(angles, vals, marker="o")
    ax1.fill(angles, vals, alpha=0.25)
    ax1.set_thetagrids([a*180/np.pi for a in angles[:-1]], labels_jp)
    st.pyplot(fig1)

    # 棒グラフ Top5
    adjs = extract_adjs(row["review"])
    freqs = pd.Series(adjs).value_counts().head(5)
    fig2 = px.bar(x=freqs.index, y=freqs.values, labels={"x":"形容詞","y":"回数"})
    st.plotly_chart(fig2, use_container_width=True)

    # フォームリンク
    st.markdown("---")
    st.markdown(
        f"""<div style="text-align:center; margin-top:1em;">
             <a href="{FORM_URL}" target="_blank">
               <button style="background-color:#f63366; color:white; padding:0.5em 1em; border:none; border-radius:4px; font-size:1em; cursor:pointer;">
                 感想を投稿する（Googleフォーム）
               </button>
             </a>
           </div>""",
        unsafe_allow_html=True
    )

    if st.button("検索に戻る", key="back2"):
        st.session_state.results = None
        st.session_state.selected_idx = None
        st.experimental_rerun()
