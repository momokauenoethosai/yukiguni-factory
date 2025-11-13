import streamlit as st
import pandas as pd
import os
from datetime import datetime

# ページ設定は削除（メインアプリで設定済み）

# プロジェクトルートからの動的パス設定
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV = os.path.join(PROJECT_ROOT, "input", "super_list.csv")

def load_supermarket_data():
    """スーパーマーケットデータを読み込み"""
    if os.path.exists(INPUT_CSV):
        df = pd.read_csv(INPUT_CSV)
        # ステータス列がない場合は追加
        if 'status' not in df.columns:
            df['status'] = '未適用'
        if 'created_at' not in df.columns:
            df['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return df
    else:
        return pd.DataFrame(columns=['super_name', 'shop_name', 'url', 'status', 'created_at'])

def save_supermarket_data(df):
    """スーパーマーケットデータを保存"""
    os.makedirs(os.path.dirname(INPUT_CSV), exist_ok=True)
    df.to_csv(INPUT_CSV, index=False, encoding='utf-8')

st.title("🏪 スーパーマーケット管理システム")

# ナビゲーション機能は selectbox で実現

# データ読み込み
if 'supermarket_df' not in st.session_state:
    st.session_state.supermarket_df = load_supermarket_data()

df = st.session_state.supermarket_df

# サイドバー - 新規登録
with st.sidebar:
    st.header("📝 新規スーパー登録")

    with st.form("add_supermarket"):
        super_name = st.text_input("スーパー名", placeholder="例: イオン")
        shop_name = st.text_input("店舗名", placeholder="例: 市川妙典店")
        url = st.text_input("URL", placeholder="https://...")

        submitted = st.form_submit_button("➕ 登録", use_container_width=True)

        if submitted:
            if super_name and shop_name and url:
                new_row = {
                    'super_name': super_name,
                    'shop_name': shop_name,
                    'url': url,
                    'status': '未適用',
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                # 重複チェック
                duplicate = df[
                    (df['super_name'] == super_name) &
                    (df['shop_name'] == shop_name) &
                    (df['url'] == url)
                ]

                if duplicate.empty:
                    st.session_state.supermarket_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    save_supermarket_data(st.session_state.supermarket_df)
                    st.success("✅ 登録完了!")
                    st.rerun()
                else:
                    st.error("❌ 同じ店舗が既に登録されています")
            else:
                st.error("❌ すべての項目を入力してください")

    st.divider()

    # 一括操作
    st.header("🔧 一括操作")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📤 CSVエクスポート", use_container_width=True):
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 ダウンロード",
                data=csv,
                file_name=f"supermarket_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

    with col2:
        if st.button("🗑️ 全削除", use_container_width=True):
            if st.session_state.get('confirm_delete', False):
                st.session_state.supermarket_df = pd.DataFrame(columns=['super_name', 'shop_name', 'url', 'status', 'created_at'])
                save_supermarket_data(st.session_state.supermarket_df)
                st.session_state.confirm_delete = False
                st.success("削除完了")
                st.rerun()
            else:
                st.session_state.confirm_delete = True
                st.warning("もう一度クリックで削除実行")

# メインコンテンツ
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    st.subheader("📋 登録済みスーパーマーケット一覧")

with col2:
    # ステータスフィルター
    status_filter = st.selectbox(
        "ステータスフィルター",
        ["すべて", "適用済み", "未適用"],
        index=0
    )

with col3:
    # 検索
    search_term = st.text_input("🔍 検索", placeholder="スーパー名・店舗名で検索")

# データフィルタリング
filtered_df = df.copy()

if status_filter != "すべて":
    filtered_df = filtered_df[filtered_df['status'] == status_filter]

if search_term:
    mask = (
        filtered_df['super_name'].str.contains(search_term, case=False, na=False) |
        filtered_df['shop_name'].str.contains(search_term, case=False, na=False)
    )
    filtered_df = filtered_df[mask]

# 統計情報
col1, col2, col3, col4 = st.columns(4)
col1.metric("総店舗数", len(df))
col2.metric("適用済み", len(df[df['status'] == '適用済み']))
col3.metric("未適用", len(df[df['status'] == '未適用']))
col4.metric("スーパー数", df['super_name'].nunique() if not df.empty else 0)

st.divider()

# データテーブル表示
if not filtered_df.empty:
    # 編集可能なデータエディタ
    edited_df = st.data_editor(
        filtered_df,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "super_name": st.column_config.TextColumn("スーパー名", width="medium"),
            "shop_name": st.column_config.TextColumn("店舗名", width="medium"),
            "url": st.column_config.LinkColumn("URL", width="large"),
            "status": st.column_config.SelectboxColumn(
                "ステータス",
                options=["適用済み", "未適用"],
                width="small"
            ),
            "created_at": st.column_config.TextColumn("登録日時", width="medium")
        },
        column_order=["super_name", "shop_name", "url", "status", "created_at"]
    )

    # 変更を保存
    if not edited_df.equals(filtered_df):
        # 元のDataFrameを更新
        for index, row in edited_df.iterrows():
            original_index = df[
                (df['super_name'] == row['super_name']) &
                (df['shop_name'] == row['shop_name']) &
                (df['url'] == row['url'])
            ].index

            if not original_index.empty:
                df.loc[original_index[0]] = row

        st.session_state.supermarket_df = df
        save_supermarket_data(df)
        st.success("✅ 変更を保存しました")
        st.rerun()

else:
    st.info("📭 条件に合致するデータがありません")

# フッター
st.divider()
with st.container():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.caption("💡 ヒント: ステータスを「適用済み」にするとチラシ収集の対象になります")
        st.caption("🔄 データは自動保存されます")