import streamlit as st
import pandas as pd
from janome.tokenizer import Tokenizer
import matplotlib.pyplot as plt

# ─── ページ設定 (必ず最初) ────────────────────────────────────
st.set_page_config(
    page_title="感想で本が探せるアプリ",
    layout="wide",
)

# ─── データ読み込み & 前処理 ─────────────────────────────────
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # genre列をカンマ区切りでリスト化
    df["genre_list"] = df["genre"].str.split(",")
    return df

df = load_data("sample05.csv")

tokenizer = Tokenizer()
# 価値の低い形容詞をストップワードとして除外
STOP_ADJS = {
    "ない", "っぽい", "良い", "おいしい", "すごい", "すごく","多い","少ない"
}

@st.cache_data
def extract_adjs(text: str) -> list[str]:
    toks = tokenizer.tokenize(text)
    adjs = [
        t.surface
        for t in toks
        if t.part_of_speech.startswith("形容詞")
    ]
    # ストップワードを除外
    return [w for w in adjs if w not in STOP_ADJS]

df["adjs"] = df["review"].map(extract_adjs)

# 全形容詞リスト（サジェスト用）
all_adjs = sorted({adj for adjs in df["adjs"] for adj in adjs})

# ─── サイドバー：ジャンル絞り込み ─────────────────────────────
st.sidebar.header("🔖 ジャンルで絞り込み")
genres = sorted({g for gl in df["genre_list"] for g in gl})
selected_genre = st.sidebar.selectbox("ジャンルを選択", ["All"] + genres)

# ─── メイン画面 ─────────────────────────────────────────────
st.title("📚感想で本が探せるアプリ")
st.write("感想に登場する形容詞から本を検索します。")

# 形容詞入力 + サジェスト
raw = st.text_input("形容詞を入力してください", "")
search_adj = None
if raw:
    candidates = [w for w in all_adjs if w.startswith(raw)]
    if candidates:
        search_adj = st.selectbox("候補", candidates, key="suggestion")
    else:
        st.warning("お探しの形容詞は登録されている感想リストの中に登場しません。別の形容詞で検索してみてください。")

# 検索ボタン
if st.button("🔍 検索"):
    if not search_adj:
        st.error("検索する形容詞を選んでください。")
    else:
        # ジャンルでフィルター
        if selected_genre != "All":
            df_filtered = df[df["genre_list"].apply(lambda gl: selected_genre in gl)]
        else:
            df_filtered = df

        # キーワード出現回数
        counts = (
            pd.Series(sum(df_filtered["adjs"].tolist(), []))
            .value_counts()
        )

        # 結果がなければ通知
        if search_adj not in counts:
            st.info(f"「{search_adj}」は該当する感想に登場しません。")
        else:
            # ── 検索結果ランキング画面 ─────────────────────
            st.header("🔎 検索結果ランキング")
            top_books = (
                df_filtered.assign(count=df_filtered["adjs"].map(lambda al: al.count(search_adj)))
                .query("count>0")
                .sort_values("count", ascending=False)
                .head(10)
                .reset_index(drop=True)
            )

            # ランキング文言リスト
            options = [
                f"{i+1}位：『{row['title']}』／{row['author']} （{row['count']}回）"
                for i, row in top_books.iterrows()
            ]
            selected_label = st.selectbox("本を選択して詳細を見る", options)

            # 詳細表示
            idx = options.index(selected_label)
            book = top_books.iloc[idx]

            st.subheader(f"📖 『{book['title']}』 by {book['author']}")
            st.write(book["review"])

            # ── 棒グラフ：Top5 形容詞頻度 ─────────────────
            freq = pd.Series(book["adjs"]).value_counts().head(5)
            fig, ax = plt.subplots()
            freq.plot.bar(ax=ax)
            ax.set_xlabel("形容詞")
            ax.set_ylabel("回数")
            ax.set_title("頻出形容詞TOP5")
            st.pyplot(fig)

            # ── レーダーチャート：6軸 ──────────────────────
            categories = ["erotic", "grotesque", "insane", "paranormal", "esthetic", "painful"]
            values = [book.get(cat, 0) for cat in categories]
            angles = [n / float(len(categories)) * 2 * 3.1415926535 for n in range(len(categories))]
            values += values[:1]
            angles += angles[:1]

            fig2, ax2 = plt.subplots(subplot_kw=dict(polar=True))
            ax2.plot(angles, values, marker="o")
            ax2.fill(angles, values, alpha=0.25)
            ax2.set_thetagrids([a * 180/3.1415926535 for a in angles[:-1]], categories)
            ax2.set_title("レーダーチャート(6軸)")
            st.pyplot(fig2)
