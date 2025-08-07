import streamlit as st
import pandas as pd
import requests
import json
from janome.tokenizer import Tokenizer
from collections import Counter
import plotly.graph_objects as go
import re
import unicodedata
import os
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import html

# HTMLエスケープ関数
def escape_html(text):
    """HTMLエスケープを行う"""
    if text is None:
        return ""
    return html.escape(str(text))

# フォントファイルの存在確認とフォールバック処理
def get_font_path():
    """利用可能なフォントパスを取得する"""
    # 優先順位1: プロジェクト内のipag.ttf
    font_paths = [
        "ipag.ttf",
        "/mnt/data/ipag.ttf",  # Streamlit Cloud用
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux標準
        "/System/Library/Fonts/Arial.ttf",  # macOS標準
        "C:/Windows/Fonts/arial.ttf"  # Windows標準
    ]
    
    for path in font_paths:
        if os.path.exists(path):
            return path
    
    # どのフォントも見つからない場合はNoneを返す（WordCloudがデフォルトフォントを使用）
    return None

# ─── 1. ページ設定（最初に） ─────────────────────────────────
st.set_page_config(page_title="YOMIAJI : βテスト版", layout="wide", initial_sidebar_state="collapsed")

# 共通CSSを毎回読み込む（安定性を優先）
st.markdown('''
    <style>
    .stApp {
        background: #1E1E1E !important;
    }
    /* 全体幅375px中央寄せ */
    .main .block-container {
        max-width: 375px !important;
        padding: 0 !important;
        margin: 0 auto !important;
    }
    /* st.buttonのみに強制適用 */
    div[data-testid="stButton"] > button,
    div.stButton > button,
    button[data-testid="baseButton-secondary"] {
        width: 100% !important;
        max-width: none !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
        text-align: center !important;
        font-size: 16px !important;
        font-weight: bold !important;
        color: #000000 !important;
        background: #FF9500 !important;
        border-radius: 8px !important;
        text-decoration: none !important;
        padding: 16px 0 !important;
        margin: 20px 10px 20px 10px !important;
        border: none !important;
        cursor: pointer !important;
        box-sizing: border-box !important;
    }
    
    /* st.buttonの親要素のみ制御 */
    div[data-testid="stButton"] {
        width: 100% !important;
        max-width: none !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }
    /* 注意書きのスタイル */
    .custom-note {
        font-family: 'Inter', sans-serif;
        color: #FFFFFF;
        font-size: 12px;
        line-height: 16px;
        padding: 10px;
        text-align: left !important;
    }
    div[data-testid="stMarkdownContainer"] .custom-note, div[data-testid="stMarkdownContainer"] .custom-note * {
        text-align: left !important;
    }
    </style>
''', unsafe_allow_html=True)

# ─── 2. データ読み込み & 前処理 ─────────────────────────────────
# 抽出対象の品詞をリスト化（将来的に増やしやすい形）
POS_TARGETS = ["形容詞", "形容動詞"]

@st.cache_data(ttl=3600)  # 1時間でキャッシュを無効化
def load_abstractwords(path: str = "abstractwords.txt") -> set[str]:
    try:
        with open(path, encoding="utf-8") as f:
            words = {line.strip() for line in f if line.strip() and not line.startswith("#")}
    except FileNotFoundError:
        words = set()
    return words

ABSTRACTWORDS = load_abstractwords()

def extract_target_words(text: str) -> list[str]:
    tokens = tokenizer.tokenize(text)
    results = []
    for t in tokens:
        pos = t.part_of_speech.split(",")[0]
        if pos in POS_TARGETS:
            results.append(t.base_form)
    # 文中に抽出ワードリストがあれば必ず抽出
    for word in ABSTRACTWORDS:
        if word in text:
            results.append(word)
    return results

def get_file_hash(path: str) -> str:
    """ファイルの更新日時とサイズからハッシュを生成"""
    try:
        stat = os.stat(path)
        return f"{stat.st_mtime}_{stat.st_size}"
    except OSError:
        return "file_not_found"

@st.cache_data(ttl=3600)  # 1時間でキャッシュを無効化
def load_data(path: str = "database.csv") -> pd.DataFrame:
    # ファイルの更新日時をチェック
    file_hash = get_file_hash(path)
    
    df = pd.read_csv(path, dtype={"ISBN": str}).fillna("")
    df.columns = [col.lower() for col in df.columns]  # 列名を小文字に統一
    # ジャンルをリスト化
    df["genres_list"] = df["genre"].str.split(",").apply(lambda lst: [g.strip() for g in lst if g.strip()])
    # Janome で形容詞・形容動詞抽出
    global tokenizer
    tokenizer = Tokenizer()
    df["keywords"] = df["review"].apply(extract_target_words)
    return df, file_hash

df, _ = load_data()

# ─── 3. ストップワード外部化 & 候補形容詞 ─────────────────────────────
@st.cache_data(ttl=3600)  # 1時間でキャッシュを無効化
def load_stopwords(path: str = "stopwords.txt") -> set[str]:
    try:
        with open(path, encoding="utf-8") as f:
            words = {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        words = {"ない", "っぽい"}
    return words

def get_rakuten_app_id():
    return st.secrets.get("RAKUTEN_APP_ID")

def normalize_isbn(isbn_str: str) -> str:
    """ISBNを正規化する（ハイフンや空白を除去）"""
    if not isbn_str:
        return ""
    # 全角英数字を半角に、数字以外を除去
    s = unicodedata.normalize("NFKC", isbn_str)
    return re.sub(r"[^0-9Xx]", "", s)

# 楽天ブックスAPIで書誌情報を取得
@st.cache_data(ttl=86400, show_spinner=False)  # 24時間でキャッシュを無効化
def fetch_rakuten_book(isbn: str) -> dict:
    if not isbn:
        return {}
    normalized_isbn = normalize_isbn(isbn)
    if not normalized_isbn:
        return {}
    
    # APIキーの確認
    app_id = get_rakuten_app_id()
    if not app_id:
        st.error("楽天APIキーが設定されていません。管理者にお問い合わせください。")
        return {}
    
    url = "https://app.rakuten.co.jp/services/api/BooksBook/Search/20170404"
    params = {
        "isbn": normalized_isbn,
        "applicationId": app_id,
        "format": "json"
    }
    
    try:
        res = requests.get(url, params=params, timeout=10)  # タイムアウトを設定
        
        # HTTPステータスコードの確認
        if res.status_code == 401:
            st.error("楽天APIの認証エラーが発生しました。APIキーを確認してください。")
            return {}
        elif res.status_code == 429:
            st.warning("楽天APIの利用制限に達しました。しばらく時間をおいてから再試行してください。")
            return {}
        elif res.status_code == 404:
            # 404は正常なケース（本が見つからない）
            return {}
        elif res.status_code != 200:
            st.error(f"楽天APIでエラーが発生しました（ステータスコード: {res.status_code}）")
            return {}
        
        data = res.json()
        
        # APIレスポンスの確認
        if not data.get("Items"):
            # 本が見つからない場合は正常なケース
            return {}
        
        item = data["Items"][0]["Item"]
        # 書影はlarge→medium→smallの順で最初に見つかったもの
        cover_url = item.get("largeImageUrl") or item.get("mediumImageUrl") or item.get("smallImageUrl") or ""
        
        return {
            "title": item.get("title"),
            "author": item.get("author"),
            "publisher": item.get("publisherName"),
            "pubdate": item.get("salesDate"),
            "price": item.get("itemPrice") if item.get("itemPrice") is not None else "—",
            "description": item.get("itemCaption") or "—",
            "cover": cover_url,
            "affiliateUrl": item.get("affiliateUrl"),
            "itemUrl": item.get("itemUrl")
        }
        
    except requests.exceptions.Timeout:
        st.warning("楽天APIへのリクエストがタイムアウトしました。しばらく時間をおいてから再試行してください。")
        return {}
    except requests.exceptions.ConnectionError:
        st.error("楽天APIへの接続に失敗しました。インターネット接続を確認してください。")
        return {}
    except requests.exceptions.RequestException as e:
        st.error(f"楽天APIへのリクエストでエラーが発生しました: {str(e)}")
        return {}
    except json.JSONDecodeError:
        st.error("楽天APIからのレスポンスの形式が不正です。")
        return {}
    except Exception as e:
        st.error(f"予期しないエラーが発生しました: {str(e)}")
        return {}

STOPWORDS = load_stopwords()
all_keywords = sorted({kw for lst in df["keywords"] for kw in lst})
suggestions = [w for w in all_keywords if w not in STOPWORDS]

# ─── 4. セッションステート初期化 ─────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "home"
if "results" not in st.session_state:
    st.session_state.results = pd.DataFrame()
if "adj" not in st.session_state:
    st.session_state.adj = ""
if "detail_idx" not in st.session_state:
    st.session_state.detail_idx = None
if "raw_input" not in st.session_state:
    st.session_state.raw_input = ""
if "raw_select" not in st.session_state:
    st.session_state.raw_select = ""

# ─── 6. ページ遷移用関数 ─────────────────────────────────────
def to_results(adj=None):
    if adj is None:
        adj = st.session_state.raw_select or st.session_state.raw_input.strip()
    st.session_state.adj = adj
    st.session_state.raw_input = adj  # 検索に使ったワードを入力欄にも反映
    tmp = df.copy()
    # 形容詞絞り込み
    tmp["count"] = tmp["keywords"].apply(lambda lst: lst.count(adj))
    res = tmp[tmp["count"] > 0].sort_values("count", ascending=False)
    if not res.empty:
        res["rank"] = res["count"].rank(method="min", ascending=False).astype(int)
    st.session_state.results = res.reset_index(drop=True)
    st.session_state.page = "results"

def to_detail(idx: int):
    st.session_state.detail_idx = idx
    st.session_state.page = "detail"

def to_home():
    st.session_state.page = "home"
    # TOPに戻った時に検索ワードをクリア
    st.session_state.raw_input = ""
    st.session_state.raw_select = ""



# ─── 7. メインページ分岐 ─────────────────────────────────────
if st.session_state.page == "home":
    # ─── TOP画面 ───────────────────────────────────────
    # TOP画面専用CSS
    st.markdown('''
        <style>
        /* タイトル・リード文・下部テキストの親divも中央揃え */
        div[data-testid="stMarkdownContainer"] > div,
        .custom-title, .custom-lead, .custom-bottom1, .custom-bottom2 {
            text-align: center !important;
        }
        /* タイトル */
        .custom-title {
            font-size: 30px !important;
            font-weight: bold !important;
            color: #FFFFFF !important;
            padding: 64px 10px 10px 10px !important;
            letter-spacing: 0.02em;
            text-align: center !important;
        }
        /* リード文 */
        .custom-lead {
            font-size: 16px !important;
            color: #FFFFFF !important;
            padding: 10px !important;
            line-height: 24px !important;
            text-align: center !important;
        }
        /* ラベル */
        .custom-label {
            font-size: 14px !important;
            color: #FFFFFF !important;
            padding: 10px 10px 0 10px !important;
        }
        /* テキストエリア・プルダウン */
        .custom-input, .custom-select {
            width: 167px !important;
            height: 88px !important;
            padding: 10px !important;
            font-size: 14px !important;
            color: #FFFFFF !important;
            background: rgba(0,0,0,0.4) !important;
            border-radius: 8px !important;
            border: 1px solid #94A3B8 !important;
            margin: 0 5px 0 0 !important;
        }
        /* プレースホルダー色 */
        input::placeholder, textarea::placeholder, .custom-select option:disabled {
            color: #94A3B8 !important;
            opacity: 1 !important;
        }
        /* 区切り線 */
        .custom-divider {
            width: 355px;
            height: 1px;
            background: #FFFFFF;
            opacity: 0.3;
            margin: 116px 10px 10px 10px !important;
        }
        </style>
    ''', unsafe_allow_html=True)

    # タイトル
    st.markdown('<div class="custom-title">YOMIAJI <span class="colon">:</span> βテスト版</div>', unsafe_allow_html=True)
    # リード文
    st.markdown('<div class="custom-lead">感想・読み味から本が検索できるサービスです。<br>入力したキーワードが感想に含まれている本を検索できます。</div>', unsafe_allow_html=True)

    # 検索フォーム（横並び）
    col1, col2 = st.columns(2, gap="small")
    with col1:
        st.markdown('<div class="custom-label">候補から検索</div>', unsafe_allow_html=True)
        filtered = [w for w in suggestions if w.startswith(st.session_state.raw_input)] if st.session_state.raw_input else suggestions
        st.session_state.raw_select = st.selectbox(
            "候補から選ぶ", options=[""] + filtered, index=0, key="raw_select_box",
            placeholder="形容詞を選択",
            label_visibility="collapsed"
        )
    with col2:
        st.markdown('<div class="custom-label">フリーテキストで検索</div>', unsafe_allow_html=True)
        st.session_state.raw_input = st.text_area(
            "形容詞を入力してください", value=st.session_state.raw_input, key="raw_input_input",
            placeholder="例：美しい、切ない…",
            height=70,
            label_visibility="collapsed"
        )
    # 検索ボタン（st.button＋CSSで実装）
    st.button("検索", on_click=to_results, key="search_btn_home")
    # 区切り線
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    # 下部テキスト
    st.markdown('<div class="custom-bottom1"><b>あなたが読んだ本の感想を投稿してください</b></div>', unsafe_allow_html=True)
    st.markdown('<div class="custom-bottom2">あなたの感想がサービスを育てます。</div>', unsafe_allow_html=True)
    # Googleフォームボタン（st.button＋CSSで実装）
    st.link_button("Googleフォーム", "https://forms.gle/Eh3fYtnzSHmN3KMSA", type="primary")

elif st.session_state.page == "results":
    # ─── 検索結果画面 ───────────────────────────────────
    # 検索結果画面専用CSS
    st.markdown('''
        <style>
        /* 注意書きのスタイル */
        .custom-note {
            font-family: 'Inter', sans-serif;
            color: #FFFFFF;
            font-size: 12px;
            line-height: 16px;
            padding: 10px;
            text-align: left !important;
        }
        div[data-testid="stMarkdownContainer"] .custom-note, div[data-testid="stMarkdownContainer"] .custom-note * {
            text-align: left !important;
        }
        </style>
    ''', unsafe_allow_html=True)
    
    # 0. 戻るボタン
    if st.button("戻る", key="back_to_home"):
        to_home()
        st.rerun()
    # 1. 検索ワード入力欄
    if not st.session_state.raw_input:
        st.session_state.raw_input = st.session_state.get('adj', '')
    st.session_state.raw_input = st.text_input(
        "", value=st.session_state.raw_input, key="raw_input_results", placeholder=""
    )
    # 2. 検索ボタン
    new_input = st.session_state.raw_input
    if st.button("再検索", key="search_btn_results"):
        to_results(new_input)

    # 4. 検索結果タイトル
    adj = st.session_state.get('adj', '')
    escaped_adj = escape_html(adj)
    st.markdown(f'<div style="width:355px;margin:12px auto 0 auto;font-family:Inter,sans-serif;font-size:20px;color:#FFFFFF;line-height:28px;font-weight:bold;">検索結果「{escaped_adj}」</div>', unsafe_allow_html=True)
    # 5. 注意書き
    st.markdown('<div class="custom-note">※楽天ブックスに登録がない書籍に関しては、書影その他情報が表示されない場合があります。</div>', unsafe_allow_html=True)
    # 6. 検索結果カード
    st.markdown('''
    <style>
      div.stButton > button {
        margin-bottom: 0 !important;
        margin-top: 0 !important;
        padding-top: 12px !important;
        padding-bottom: 12px !important;
      }
      .result-card {
        margin-top: 0 !important;
        padding-top: 0 !important;
        min-height: 126px !important;
        margin-bottom: 8px !important;
      }
      .card-content-row {
        display: flex;
        flex-direction: row;
        gap: 16px;
        align-items: center;
      }
      .card-thumbnail {
        width: 116px !important;
        height: 105px !important;
        flex-shrink: 0 !important;
      }
      .card-thumbnail img {
        width: 100% !important;
        height: 100% !important;
        object-fit: cover !important;
        border-radius: 8px !important;
      }
      .card-meta {
        font-family: 'Inter', sans-serif;
        color: #FFFFFF;
        font-size: 12px;
        display: flex;
        flex-direction: column;
        gap: 4px;
        text-align: left !important;
        align-items: flex-start;
      }
      .genre-tags-container {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-top: 2px;
      }
      .genre-tag {
        display: inline-flex;
        padding: 4px 6px;
        justify-content: center;
        align-items: center;
        gap: 10px;
        border-radius: 8px;
        background: #FFD293;
        color: #000000;
        font-size: 10px;
        font-weight: 500;
        white-space: nowrap;
      }
      .custom-note {
        font-family: 'Inter', sans-serif;
        color: #FFFFFF;
        font-size: 12px;
        line-height: 16px;
        padding: 10px;
        text-align: left !important;
      }
      div[data-testid="stMarkdownContainer"] .custom-note, div[data-testid="stMarkdownContainer"] .custom-note * {
        text-align: left !important;
      }
    </style>
    ''', unsafe_allow_html=True)
    
    res = st.session_state.results
    if res.empty:
        st.markdown('<div style="text-align:center;color:#FFFFFF;font-size:16px;margin:50px 0;">該当する本がありませんでした。</div>', unsafe_allow_html=True)
    else:
        for i, (_, row) in enumerate(res.iterrows()):
            rakuten = fetch_rakuten_book(row.get("isbn", ""))
            placeholder_cover = "https://via.placeholder.com/116x105/666666/FFFFFF?text=No+Image"
            cover_url = rakuten.get("cover") or placeholder_cover
            genres = row.get('genres_list', [])
            # ジャンルタグのHTMLエスケープ
            escaped_genres = [escape_html(g) for g in genres]
            genre_tags_html = "".join([f'<span class=\"genre-tag\">{g}</span>' for g in escaped_genres])
            # タイトル行のみクリッカブル
            escaped_title = escape_html(row['title'])
            escaped_author = escape_html(row['author'])
            if st.button(f"『{escaped_title}』／{escaped_author}：{row['count']}回", key=f"title_btn_{i}"):
                to_detail(i)
                st.rerun()
            card_html = f'''
            <div class="result-card">
                <div class="card-content-row">
                    <div class="card-thumbnail">
                        <img src="{cover_url}" alt="{escaped_title}" />
                    </div>
                    <div class="card-meta" style="display: flex; flex-direction: column; justify-content: center;">
                        <div>ジャンル</div>
                        <div class="genre-tags-container">
                            {genre_tags_html}
                        </div>
                        <div>出版社：{escape_html(rakuten.get('publisher', '—'))}</div>
                        <div>発行日：{escape_html(rakuten.get('pubdate', '—'))}</div>
                        <div>定価：{escape_html(rakuten.get('price', '—'))}円</div>
                    </div>
                </div>
            </div>
            '''
            st.markdown(card_html, unsafe_allow_html=True)

elif st.session_state.page == "detail":
    # ─── 詳細画面 ─────────────────────────────────────
    # ページトップに強制スクロール
    st.markdown('<script>window.scrollTo(0,0);</script>', unsafe_allow_html=True)
    if st.button("戻る", key="back_to_results"):
        st.session_state.page = "results"
        st.rerun()
    res = st.session_state.results
    idx = st.session_state.detail_idx
    if idx is None or idx >= len(res):
        st.error("不正な選択です。")
    else:
        book = res.loc[idx]
        escaped_title = escape_html(book["title"])
        escaped_author = escape_html(book["author"])
        st.markdown(f'<div style="width:355px;margin:12px auto 0 auto;font-family:Inter,sans-serif;font-size:20px;color:#FFFFFF;line-height:28px;font-weight:bold;">『{escaped_title}』／{escaped_author}：{book["count"]}回</div>', unsafe_allow_html=True)
        rakuten = fetch_rakuten_book(book.get("isbn", ""))
        # 書影とボタンを横並びで表示
        col1, col2 = st.columns([1,2])
        with col1:
            cover_url = rakuten.get("cover")
            if cover_url:
                st.image(cover_url, width=100)
        with col2:
            url = rakuten.get("affiliateUrl") or rakuten.get("itemUrl")
            if url:
                st.link_button("商品ページを開く（楽天ブックス）", url, type="primary")
            st.link_button("感想を投稿する（Googleフォーム）", "https://forms.gle/Eh3fYtnzSHmN3KMSA", type="primary")
        # 書誌情報
        st.markdown(f'<div style="color:#FFFFFF;font-family:Inter,sans-serif;font-size:16px;line-height:24px;margin:10px 0;">出版社: {escape_html(rakuten.get("publisher","—"))}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="color:#FFFFFF;font-family:Inter,sans-serif;font-size:16px;line-height:24px;margin:10px 0;">発行日: {escape_html(rakuten.get("pubdate","—"))}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="color:#FFFFFF;font-family:Inter,sans-serif;font-size:16px;line-height:24px;margin:10px 0;">定価: {escape_html(rakuten.get("price","—"))} 円</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="color:#FFFFFF;font-family:Inter,sans-serif;font-size:16px;line-height:24px;margin:10px 0;">紹介文: {escape_html(rakuten.get("description","—"))}</div>', unsafe_allow_html=True)

        # レーダーチャート
        # 「エロ」を上として時計回りに配置
        # 「エロ」を上として時計回りに配置
        # 配列の順序で「エロ」を上に配置（Plotlyは最初の項目を上から開始）
        radar_vals = [book[c] for c in ["erotic","action","mystery","painful","esthetic","paranomal","insane","grotesque"]]
        radar_labels = ["エロ","アクション","謎","感動","耽美","霊怖","人怖","グロ"]
        # レーダーチャートタイトル
        st.markdown('''
        <style>
        div[data-testid="stMarkdownContainer"] > div {
            text-align: left !important;
        }
        </style>
        <div style="font-family:Inter,sans-serif;font-size:20px;color:#FFFFFF;line-height:28px;font-weight:bold;margin:20px 0 10px 0;">読み味レーダーチャート</div>
        ''', unsafe_allow_html=True)
        fig_radar = go.Figure(
            data=[go.Scatterpolar(r=radar_vals, theta=radar_labels, fill='toself')],
            layout=go.Layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 5],
                        showticklabels=False,  # 数字を非表示
                        showline=False,        # 軸線を非表示
                        ticks=''               # 目盛り線も非表示
                    )
                ),
                showlegend=False
            )
        )
        st.plotly_chart(fig_radar, use_container_width=True, config={"staticPlot": True})
        # ワードクラウド表示
        cnt = Counter(book['keywords'])
        for sw in STOPWORDS:
            cnt.pop(sw, None)
        if cnt:
            # ワードクラウド生成
            st.markdown('''
            <style>
            div[data-testid="stMarkdownContainer"] > div {
                text-align: left !important;
            }
            /* ワードクラウド画像の全画面拡大ボタンを非表示 */
            div[data-testid="stImage"] button {
                display: none !important;
            }
            </style>
            <div style="font-family:Inter,sans-serif;font-size:20px;color:#FFFFFF;line-height:28px;font-weight:bold;margin:20px 0 10px 0;">感想ワードクラウド</div>
            ''', unsafe_allow_html=True)
            wc = WordCloud(font_path=get_font_path(), width=600, height=400, background_color='white', colormap='tab20').generate_from_frequencies(dict(cnt))
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.imshow(wc, interpolation='bilinear')
            ax.axis('off')
            st.pyplot(fig)
        else:
            st.info("有効なワードが見つかりませんでした。")
