import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from janome.tokenizer import Tokenizer
from collections import Counter
import numpy as np

# --- 日本語フォント設定 ---
matplotlib.rcParams['font.family'] = 'IPAexGothic'  # macOS/共通フォント

# --- データ読み込み ---
df = pd.read_csv("sample05.csv")

# --- Streamlit レイアウト ---
st.set_page_config(layout="wide")
st.title("📚 感想形容詞で探す本アプリ")

# --- サイドバー: ジャンル絞り込み ---
genres = ["All"] + sorted(df['genre'].dropna().unique().tolist())
selected_genre = st.sidebar.selectbox("ジャンルを選択", genres)

# --- サイドバー: タグ絞り込み（必要に応じて） ---
tag_cols = [c for c in ['tags_fear_type','tags_motif','tags_style','tags_aftertaste'] if c in df.columns]
selected_tags = {}
for col in tag_cols:
    options = sorted({t for tags in df[col].dropna() for t in str(tags).split(",")})
    selected = st.sidebar.multiselect(col.replace('tags_','').capitalize(), options)
    selected_tags[col] = selected

# --- データフィルタリング ---
filtered = df.copy()
if selected_genre != "All":
    filtered = filtered[filtered['genre'] == selected_genre]
if tag_cols:
    def match_tags(r):
        for col, sel in selected_tags.items():
            if sel:
                vals = [t.strip() for t in str(r[col]).split(",")]
                if not any(t in vals for t in sel):
                    return False
        return True
    filtered = filtered[filtered.apply(match_tags, axis=1)]

# --- 感想から形容詞を抽出する関数 ---
def extract_adjs(text):
    t = Tokenizer()
    return [tok.surface for tok in t.tokenize(str(text)) if '形容詞' in tok.part_of_speech]

# --- メイン: 形容詞検索 ---
st.markdown("## 🔍 感想によく出る形容詞で本を探す")
search_adj = st.text_input("形容詞を入力してください", "")
search_btn = st.button("検索")

if search_btn and search_adj:
    # 入力語が辞書にあるかチェック
    all_adjs = []
    for rev in filtered['review'].dropna():
        all_adjs.extend(extract_adjs(rev))
    if search_adj not in set(all_adjs):
        st.warning(f"「{search_adj}」は感想に登場していない形容詞です。別のワードを試してください。")
    else:
        # 本ごとの出現回数をカウント
        counts = []
        for idx, r in filtered.iterrows():
            cnt = extract_adjs(r['review']).count(search_adj)
            if cnt > 0:
                counts.append((idx, cnt))
        if not counts:
            st.info("該当する本がありませんでした。")
        else:
            counts.sort(key=lambda x: x[1], reverse=True)
            titles = [f"{i+1}位: {filtered.loc[i,'title']} / {filtered.loc[i,'author']} ({c}回)" \
                      for i, (i,c) in enumerate(counts)]
            sel = st.selectbox("本を選択してください", titles)
            sel_idx = counts[[i for i,(idx,_) in enumerate(counts) 
                              if f"{filtered.loc[idx,'title']} / {filtered.loc[idx,'author']}" in sel][0]][0]
            book = filtered.loc[sel_idx]

            # --- 詳細ページ表示 ---
            st.markdown(f"### 📖 『{book['title']}』 by {book['author']}")
            st.write(book['review'])

            # レーダーチャート用データ
            st.markdown("#### レーダーチャート(6軸)")
            labels = ['erotic','grotesque','insane','paranomal','esthetic','painful']
            values = [book.get(l, 0) for l in labels]
            angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
            values += values[:1]; angles += angles[:1]
            fig, ax = plt.subplots(subplot_kw=dict(polar=True))
            ax.plot(angles, values, 'o-', linewidth=2)
            ax.fill(angles, values, alpha=0.3)
            ax.set_thetagrids(np.degrees(angles[:-1]), ['エロ','グロ','狂気','超常','美的','痛み'])
            st.pyplot(fig)

            # 形容詞Top5
            st.markdown("#### 感想によく使われた形容詞 Top5")
            adjs = extract_adjs(book['review'])
            top5 = Counter(adjs).most_common(5)
            if top5:
                w, v = zip(*top5)
                fig2, ax2 = plt.subplots()
                ax2.bar(w, v)
                ax2.set_ylabel('出現回数')
                ax2.set_title('形容詞頻出Top5')
                st.pyplot(fig2)
            else:
                st.info('形容詞が見つかりませんでした。')

else:
    st.info("検索ワードを入力して「検索」ボタンを押してください。")
