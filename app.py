import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from janome.tokenizer import Tokenizer

# ─── 定数 ───────────────────────────────────────────────────────────────
DATA_PATH = "sample05.csv"
FORM_URL  = "https://forms.gle/Eh3fYtnzSHmN3KMSA"  # GoogleフォームURL

STOPWORDS = {
    "ない", "っぽい", "良い", "いい", "すごい", "多い","少ない",
    # もし追加したい語があればここに入れてください
}

# ─── ヘルパー関数 ────────────────────────────────────────────────────────
@st.cache_data
def load_data(path):
    df = pd.read_csv(path)
    # ジャンルをカンマで分割してリスト化
    df["genre_list"] = df["genre"].str.split(",")
    return df

def extract_adjectives(text, tokenizer):
    tokens = tokenizer.tokenize(text)
    return [t.surface for t in tokens if t.part_of_speech.startswith("形容詞")]

def count_adjectives(reviews, tokenizer):
    counter = {}
    for rev in reviews:
        for adj in extract_adjectives(str(rev), tokenizer):
            if adj in STOPWORDS:
                continue
            counter[adj] = counter.get(adj, 0) + 1
    return counter

def plot_radar(ax, labels, values):
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False)
    values = np.concatenate((values, [values[0]]))
    angles = np.concatenate((angles, [angles[0]]))
    ax.plot(angles, values, 'o-', linewidth=2)
    ax.fill(angles, values, alpha=0.25)
    ax.set_thetagrids(angles[:-1] * 180/np.pi, labels)
    ax.set_ylim(0, max(values) * 1.1)

def show_detail(book):
    """
    選択された本の詳細画面を描画する関数
    """
    st.header(f"📖 『{book['title']}』  by {book['author']}")
    st.write(book["review"])

    # レーダーチャート用データ
    radar_labels = ["erotic","grotesque","insane","paranormal","esthetic","painful"]
    radar_values = [book.get(col, 0) for col in radar_labels]

    fig1, ax1 = plt.subplots(subplot_kw={"polar": True}, figsize=(5,5))
    plot_radar(ax1, radar_labels, np.array(radar_values))
    st.pyplot(fig1)

    # 感想から形容詞を再カウントしてTop5を棒グラフ表示
    tokenizer = Tokenizer()
    counter = count_adjectives([book["review"]], tokenizer)
    top5 = sorted(counter.items(), key=lambda x: x[1], reverse=True)[:5]
    if top5:
        labels, counts = zip(*top5)
        fig2, ax2 = plt.subplots(figsize=(6,4))
        ax2.bar(labels, counts)
        ax2.set_xlabel("形容詞")
        ax2.set_ylabel("回数")
        ax2.set_title("頻出形容詞TOP5")
        st.pyplot(fig2)
    else:
        st.info("形容詞が見つかりませんでした。")

    # ─── ここからGoogleフォームへのリンクボタン ─────────────────────────
    st.markdown("---")
    st.markdown(
        f"""
        <div style="text-align:center; margin-top:1em;">
          <a href="{FORM_URL}" target="_blank">
            <button style="
               background-color:#f63366;
               color:white;
               padding:0.5em 1em;
               border:none;
               border-radius:4px;
               font-size:1em;
               cursor:pointer;
            ">
              感想を投稿する（Googleフォーム）
            </button>
          </a>
        </div>
        """,
        unsafe_allow_html=True
    )

# ─── アプリ本体 ────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="感想で本が探せるアプリ", layout="wide")
    st.title("📚 感想で本が探せるアプリ")
    st.write("感想に登場する形容詞から本を検索します。")

    df = load_data(DATA_PATH)
    genres = ["All"] + sorted({g for sub in df["genre_list"] for g in sub})
    genre_sel = st.sidebar.selectbox("ジャンルを選択", genres)

    # 形容詞のサジェストリスト
    tokenizer = Tokenizer()
    all_adj = []
    for rev in df["review"]:
        all_adj += extract_adjectives(str(rev), tokenizer)
    all_adj = sorted(set([a for a in all_adj if a not in STOPWORDS]))

    adjective_input = st.text_input("形容詞を入力してください")
    adj_choice = st.selectbox("候補から選ぶ", [""] + all_adj)

    if st.button("検索"):
        target_adj = adj_choice or adjective_input.strip()
        if not target_adj:
            st.warning("形容詞を入力または選択してください。")
            return

        # フィルタリング
        dff = df.copy()
        if genre_sel != "All":
            dff = dff[dff["genre_list"].apply(lambda gl: genre_sel in gl)]

        # 出現回数をカウント
        dff["count"] = dff["review"].apply(lambda txt: extract_adjectives(str(txt), tokenizer).count(target_adj))
        dff = dff[dff["count"] > 0].sort_values("count", ascending=False)

        if dff.empty:
            st.info(f"「{target_adj}」を含む感想が見つかりませんでした。")
            return

        st.subheader("🔎 検索結果ランキング")
        for idx, row in dff.iterrows():
            st.write(f"**{row['count']}回**: 『{row['title']}』／{row['author']}")
            if st.button(f"詳細を見る", key=f"detail_{idx}"):
                show_detail(row)
                st.stop()

if __name__ == "__main__":
    main()
