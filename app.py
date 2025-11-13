import streamlit as st
import pandas as pd
import os
import subprocess
import threading
import queue
import time
from datetime import datetime
import pytz
import json
from PIL import Image

st.set_page_config(
    page_title="チラシ収集・分析システム",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ページ選択
page = st.sidebar.selectbox(
    "ページを選択",
    ["🛒 チラシ収集・分析", "🏪 スーパー管理"],
    index=0
)

if page == "🏪 スーパー管理":
    # スーパー管理ページの内容を直接表示
    exec(open("pages/supermarket_manager.py").read())
    st.stop()

st.title("🛒 チラシ収集・分析システム")

# プロジェクトルートからの動的パス設定
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(PROJECT_ROOT, "input", "super_list.csv")
SCRAPED_CSV = os.path.join(PROJECT_ROOT, "output", "chirashi_data_selenium.csv")
OUTPUT_CSV = os.path.join(PROJECT_ROOT, "output", "chirashi_data_with_products.csv")
IMAGE_CACHE_DIR = os.path.join(PROJECT_ROOT, "cache", "images")

# 必要なディレクトリを作成
os.makedirs(os.path.join(PROJECT_ROOT, "output"), exist_ok=True)
os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'log_messages' not in st.session_state:
    st.session_state.log_messages = []
if 'process_thread' not in st.session_state:
    st.session_state.process_thread = None
if 'current_execution_timestamp' not in st.session_state:
    st.session_state.current_execution_timestamp = None
if 'stop_requested' not in st.session_state:
    st.session_state.stop_requested = False

with st.sidebar:
    st.header("📋 スーパーマーケットリスト")

    if os.path.exists(INPUT_CSV):
        super_df = pd.read_csv(INPUT_CSV)

        with st.expander("登録スーパー一覧", expanded=False):
            for idx, row in super_df.iterrows():
                st.write(f"• {row['super_name']} - {row['shop_name']}")
                st.caption(f"  {row['url']}")

        st.metric("登録店舗数", len(super_df))
    else:
        st.warning("super_list.csv が見つかりません")


def run_integrated_process():
    """チラシ収集→AI分析の統合処理を実行"""
    # ログファイルに出力
    log_file = os.path.join(PROJECT_ROOT, "temp_process_log.txt")

    def write_log(message):
        # 日本時間でログタイムスタンプを生成
        jst = pytz.timezone('Asia/Tokyo')
        timestamp = datetime.now(jst).strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}\n"
        print(f"LOG: {message}")  # コンソール出力
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_msg)

    def check_stop_requested():
        """停止リクエストをチェック（ファイルベース）"""
        stop_flag_file = os.path.join(PROJECT_ROOT, "temp_stop_flag.txt")
        if os.path.exists(stop_flag_file):
            write_log("🛑 ユーザーから停止リクエストを受信しました")
            return True
        return False

    # ログファイルを初期化
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("")

    try:
        # 既存データをクリア
        write_log("🧹 既存データをクリアします...")
        if os.path.exists(OUTPUT_CSV):
            os.remove(OUTPUT_CSV)
        if os.path.exists(SCRAPED_CSV):
            os.remove(SCRAPED_CSV)

        # 画像キャッシュもクリア
        if os.path.exists(IMAGE_CACHE_DIR):
            import shutil
            shutil.rmtree(IMAGE_CACHE_DIR)
            os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
            write_log("🗑️ 画像キャッシュをクリアしました")

        # ステップ1: チラシ収集
        write_log("🚀 ステップ1: チラシ収集を開始します...")

        process = subprocess.Popen(
            ["python", "-u", "src/scrape_chirashi_selenium.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,
            universal_newlines=True
        )

        for line in iter(process.stdout.readline, ''):
            if line.strip():
                write_log(f"📄 {line.strip()}")

            # 停止チェック
            if check_stop_requested():
                process.terminate()
                write_log("⏹️ チラシ収集を停止しました")
                # 途中までのデータがあるかチェック
                if os.path.exists(SCRAPED_CSV):
                    write_log("📊 途中まで収集されたデータを保持します")
                # 停止フラグファイルをクリア
                stop_flag_file = os.path.join(PROJECT_ROOT, "temp_stop_flag.txt")
                if os.path.exists(stop_flag_file):
                    os.remove(stop_flag_file)
                return

        process.wait()

        if process.returncode != 0:
            write_log(f"❌ チラシ収集でエラーが発生しました (コード: {process.returncode})")
            # エラーでも途中までのデータがあれば保持
            if os.path.exists(SCRAPED_CSV):
                write_log("📊 エラー前まで収集されたデータを保持します")
            return

        write_log("✅ ステップ1完了: チラシ収集が完了しました")

        # ステップ2に進む前に停止チェック
        if check_stop_requested():
            write_log("⏹️ ステップ2開始前に停止しました")
            # 停止フラグファイルをクリア
            stop_flag_file = os.path.join(PROJECT_ROOT, "temp_stop_flag.txt")
            if os.path.exists(stop_flag_file):
                os.remove(stop_flag_file)
            return

        # ステップ2: AI分析処理
        write_log("🤖 ステップ2: AI商品分析を開始します...")

        # スクレイピング結果をAI分析の入力ファイルとしてコピー
        import shutil
        if os.path.exists(SCRAPED_CSV):
            filtered_csv = os.path.join(PROJECT_ROOT, "output", "chirashi_data_filtered.csv")
            shutil.copy(SCRAPED_CSV, filtered_csv)
            write_log("📋 スクレイピング結果をAI分析用に準備しました")

        process = subprocess.Popen(
            ["python", "-u", "src/analyze_chirashi_products.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,
            universal_newlines=True
        )

        for line in iter(process.stdout.readline, ''):
            if line.strip():
                write_log(f"🤖 {line.strip()}")

            # AI分析中も停止チェック
            if check_stop_requested():
                process.terminate()
                write_log("⏹️ AI分析を停止しました")
                # 途中までの分析結果があるかチェック
                if os.path.exists(OUTPUT_CSV):
                    write_log("📊 途中まで分析されたデータを保持します")
                # 停止フラグファイルをクリア
                stop_flag_file = os.path.join(PROJECT_ROOT, "temp_stop_flag.txt")
                if os.path.exists(stop_flag_file):
                    os.remove(stop_flag_file)
                return

        process.wait()

        if process.returncode == 0:
            write_log("✅ ステップ2完了: AI分析が完了しました")
        else:
            write_log(f"❌ AI分析でエラーが発生しました (コード: {process.returncode})")
            # エラーでも途中までの分析結果があれば保持
            if os.path.exists(OUTPUT_CSV):
                write_log("📊 エラー前まで分析されたデータを保持します")

        write_log("✅ 全処理完了")

    except Exception as e:
        write_log(f"❌ エラー: {str(e)}")

def process_worker():
    """バックグラウンド処理ワーカー（統合処理）"""
    run_integrated_process()

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    if st.button("🚀 チラシ収集+AI分析を実行",
                 type="primary",
                 disabled=st.session_state.processing,
                 use_container_width=True):
        st.session_state.processing = True
        st.session_state.log_messages = []
        st.session_state.stop_requested = False

        # 停止フラグファイルを削除
        stop_flag_file = os.path.join(PROJECT_ROOT, "temp_stop_flag.txt")
        if os.path.exists(stop_flag_file):
            os.remove(stop_flag_file)

        # 日本時間で新しい実行のタイムスタンプを記録
        jst = pytz.timezone('Asia/Tokyo')
        st.session_state.current_execution_timestamp = datetime.now(jst).strftime("%Y%m%d_%H%M%S")

        thread = threading.Thread(target=process_worker)
        thread.start()
        st.session_state.process_thread = thread
        st.rerun()

with col2:
    if st.button("🔄 ログをクリア"):
        st.session_state.log_messages = []
        st.rerun()

with col3:
    if st.button("⏹️ 処理を停止", disabled=not st.session_state.processing):
        st.session_state.stop_requested = True
        # 停止フラグファイルを作成
        stop_flag_file = os.path.join(PROJECT_ROOT, "temp_stop_flag.txt")
        with open(stop_flag_file, "w") as f:
            f.write("stop_requested")
        st.warning("⚠️ 停止リクエストを送信しました。処理が安全に停止されるまでお待ちください...")

if st.session_state.processing:
    st.subheader("📊 リアルタイム処理状況")

    progress_placeholder = st.empty()
    log_placeholder = st.empty()

    # ログファイルからログを読み込み
    log_file = os.path.join(PROJECT_ROOT, "temp_process_log.txt")
    recent_logs = []

    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                all_logs = f.readlines()
                recent_logs = [log.strip() for log in all_logs[-15:] if log.strip()]
        except:
            recent_logs = []

    # スレッドが生きているかチェック
    if st.session_state.process_thread and st.session_state.process_thread.is_alive():
        with progress_placeholder.container():
            # 最新ログから進捗を判定
            if recent_logs:
                latest_log = recent_logs[-1]
                if "ステップ1" in latest_log:
                    st.progress(25)
                    st.info("📄 チラシ収集中...")
                elif "ステップ2" in latest_log:
                    st.progress(50)
                    st.info("🤖 AI分析中...")
                elif "Processing" in latest_log or "AI OCR" in latest_log:
                    st.progress(75)
                    st.info("🤖 商品データ分析中...")
                elif "全処理完了" in latest_log:
                    st.progress(100)
                    st.success("✅ 全処理完了")
                    st.session_state.processing = False
                else:
                    st.progress(15)
                    st.info("🚀 処理中...")
            else:
                st.progress(10)
                st.info("🚀 処理開始中...")

        # ログ表示
        with log_placeholder.container():
            for log_msg in recent_logs:
                if "✅" in log_msg:
                    st.success(log_msg)
                elif "❌" in log_msg:
                    st.error(log_msg)
                elif "🚀" in log_msg or "🤖" in log_msg or "📄" in log_msg or "🧹" in log_msg or "📋" in log_msg or "📥" in log_msg or "🔍" in log_msg:
                    st.info(log_msg)
                else:
                    st.text(log_msg)

        # 1秒ごとにリフレッシュ（画像とデータも更新される）
        time.sleep(1)
        st.rerun()
    else:
        # スレッドが終了している場合
        st.session_state.processing = False
        with progress_placeholder.container():
            if st.session_state.stop_requested:
                st.progress(50)
                st.warning("⏹️ 処理が停止されました")
                st.info("💡 途中まで収集されたデータは下記タブで確認できます")
            else:
                st.progress(100)
                st.success("✅ 処理が完了しました")

        # 最終ログ表示
        with log_placeholder.container():
            for log_msg in recent_logs:
                if "✅" in log_msg:
                    st.success(log_msg)
                elif "❌" in log_msg:
                    st.error(log_msg)
                elif "🚀" in log_msg or "🤖" in log_msg or "📄" in log_msg or "🧹" in log_msg or "📋" in log_msg:
                    st.info(log_msg)
                else:
                    st.text(log_msg)

        # 処理完了後、停止フラグをリセット
        st.session_state.stop_requested = False
        st.rerun()

st.divider()

tab1, tab2, tab3 = st.tabs(["📊 商品データ", "📄 チラシデータ", "🖼️ チラシ画像"])

with tab1:
    st.subheader("📊 収集した商品データ")

    # 処理中でも利用可能なデータを表示
    data_file = None
    data_status = ""

    if os.path.exists(OUTPUT_CSV):
        data_file = OUTPUT_CSV
        data_status = "🎯 AI分析済みデータ"
    elif os.path.exists(SCRAPED_CSV):
        data_file = SCRAPED_CSV
        data_status = "📄 収集済みデータ（AI分析前）"

    if st.session_state.processing:
        if data_file:
            st.info("🔄 データ更新中です... 現在利用可能な部分データを表示しています")
            st.caption(data_status)
        else:
            st.info("🔄 データ収集中です...")
            st.empty()

    if data_file:
        df = pd.read_csv(data_file)

        # 最終更新時刻を表示
        if 'scraped_at' in df.columns and not df.empty:
            last_update = df['scraped_at'].iloc[0]
            st.caption(f"最終更新: {last_update}")

        # データタイプに応じた表示
        col1, col2, col3, col4 = st.columns(4)

        if data_file == OUTPUT_CSV:
            # AI分析済みデータ
            col1.metric("総商品数", len(df))
            col2.metric("店舗数", df['shop_name'].nunique())
            col3.metric("期間数", df['period'].nunique() if 'period' in df.columns else 0)
            col4.metric("カテゴリ数", df['category'].nunique() if 'category' in df.columns else 0)

            # 商品検索（AI分析済みの場合のみ）
            search = st.text_input("🔍 商品検索", placeholder="商品名で検索...")
            if search and 'product_name' in df.columns:
                df = df[df['product_name'].str.contains(search, case=False, na=False)]

            # カテゴリフィルター（AI分析済みの場合のみ）
            if 'category' in df.columns:
                category_filter = st.multiselect(
                    "カテゴリフィルター",
                    options=df['category'].unique(),
                    default=[]
                )
                if category_filter:
                    df = df[df['category'].isin(category_filter)]
        else:
            # 収集データのみ
            col1.metric("総チラシ数", len(df))
            col2.metric("店舗数", df['shop_name'].nunique())
            col3.metric("期間数", df['period'].nunique() if 'period' in df.columns else 0)
            col4.metric("画像数", df['chirashi_png_path'].count())

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=600
        )

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 CSVダウンロード",
            data=csv,
            file_name=f"chirashi_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    elif not st.session_state.processing:
        st.info("データがありません。処理を実行してください。")

with tab2:
    st.subheader("📄 収集したチラシデータ")

    # チラシ収集データを表示（chirashi_data_selenium.csv）
    if os.path.exists(SCRAPED_CSV):
        chirashi_df = pd.read_csv(SCRAPED_CSV)

        if not chirashi_df.empty:
            # 統計情報
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("総チラシ数", len(chirashi_df))
            col2.metric("店舗数", chirashi_df['shop_name'].nunique())
            col3.metric("期間数", chirashi_df['period'].nunique() if 'period' in chirashi_df.columns and chirashi_df['period'].notna().any() else 0)
            col4.metric("タイトル数", chirashi_df['flyer_title'].nunique() if 'flyer_title' in chirashi_df.columns and chirashi_df['flyer_title'].notna().any() else 0)

            # 最終更新時刻を表示
            if 'scraped_at' in chirashi_df.columns and not chirashi_df.empty:
                last_update = chirashi_df['scraped_at'].iloc[0]
                st.caption(f"最終更新: {last_update}")

            # フィルタ機能
            if 'flyer_title' in chirashi_df.columns:
                titles = chirashi_df['flyer_title'].dropna().unique()
                if len(titles) > 0:
                    title_filter = st.multiselect(
                        "🏷️ チラシタイトルでフィルタ",
                        options=titles,
                        default=[]
                    )
                    if title_filter:
                        chirashi_df = chirashi_df[chirashi_df['flyer_title'].isin(title_filter)]

            # データテーブル表示
            st.dataframe(
                chirashi_df,
                use_container_width=True,
                hide_index=True,
                height=600
            )

            # ダウンロードボタン
            csv_data = chirashi_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 チラシデータCSVダウンロード",
                data=csv_data,
                file_name=f"chirashi_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.info("チラシデータがありません。")
    elif st.session_state.processing:
        st.info("🔄 チラシ収集中です...")
    else:
        st.info("チラシデータがありません。処理を実行してください。")

with tab3:
    st.subheader("🖼️ 収集したチラシ画像")

    if st.session_state.processing:
        st.info("🔄 画像収集中です...")
        # 処理中でも現在までにダウンロードされた画像を表示
        if os.path.exists(IMAGE_CACHE_DIR) and st.session_state.current_execution_timestamp:
            current_images = [f for f in os.listdir(IMAGE_CACHE_DIR)
                             if f.endswith(('.jpg', '.jpeg', '.png')) and
                             st.session_state.current_execution_timestamp in f]

            if current_images:
                cols = st.columns(4)
                for idx, img_file in enumerate(current_images[:20]):
                    with cols[idx % 4]:
                        img_path = os.path.join(IMAGE_CACHE_DIR, img_file)
                        try:
                            img = Image.open(img_path)
                            st.image(img, caption=img_file, use_container_width=True)
                        except:
                            pass  # 画像読み込み中の場合はスキップ

                if len(current_images) > 20:
                    st.info(f"他 {len(current_images) - 20} 枚の画像があります")
            else:
                st.info("画像ダウンロード待機中...")

    elif os.path.exists(IMAGE_CACHE_DIR):
        # 全画像を取得して最新順に表示
        all_files = os.listdir(IMAGE_CACHE_DIR)
        image_files = [f for f in all_files if f.endswith(('.jpg', '.jpeg', '.png'))]

        if image_files:
            # ファイルの更新時間でソートして最新を表示
            image_files_with_time = []
            for img_file in image_files:
                img_path = os.path.join(IMAGE_CACHE_DIR, img_file)
                try:
                    mtime = os.path.getmtime(img_path)
                    image_files_with_time.append((img_file, mtime))
                except:
                    continue

            # 最新順にソート
            image_files_with_time.sort(key=lambda x: x[1], reverse=True)
            current_images = [item[0] for item in image_files_with_time]

            # 最新ファイルの更新時刻を表示
            if current_images:
                latest_file_path = os.path.join(IMAGE_CACHE_DIR, current_images[0])
                try:
                    latest_time = datetime.fromtimestamp(os.path.getmtime(latest_file_path))
                    jst = pytz.timezone('Asia/Tokyo')
                    latest_time_jst = latest_time.replace(tzinfo=pytz.UTC).astimezone(jst)
                    st.caption(f"最新画像: {latest_time_jst.strftime('%Y-%m-%d %H:%M:%S')} JST")
                except:
                    pass

            cols = st.columns(4)
            for idx, img_file in enumerate(current_images[:20]):
                with cols[idx % 4]:
                    img_path = os.path.join(IMAGE_CACHE_DIR, img_file)
                    try:
                        img = Image.open(img_path)
                        st.image(img, caption=img_file, use_container_width=True)
                    except:
                        st.error(f"画像読み込みエラー: {img_file}")

            if len(current_images) > 20:
                st.info(f"他 {len(current_images) - 20} 枚の画像があります")
        else:
            st.info("収集された画像がありません")
    else:
        st.info("画像キャッシュディレクトリが見つかりません")


st.divider()
st.caption("© 2024 チラシ収集・分析システム | Powered by Gemini AI")