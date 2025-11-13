# 🏔️ Yukiguni Factory - チラシ収集・分析システム

スーパーマーケットのチラシを自動収集し、AI（Gemini）を使って商品情報を抽出・分析するWebアプリケーションです。

## ✨ 機能

- **🕸️ 自動チラシ収集**: Seleniumを使用してスーパーのWebサイトからチラシを収集
- **🤖 AI画像解析**: Google Gemini AIでチラシ画像から商品情報を抽出
- **📊 リアルタイム表示**: 処理状況をリアルタイムで表示
- **🖼️ 画像プレビュー**: 収集したチラシ画像を即座に確認
- **💾 増分保存**: 処理中断時も部分的なデータを保持
- **🎯 インテリジェント補完**: 画像から不足情報（タイトル・期間）を自動抽出

## 🚀 デプロイ

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://yukiguni-factory.streamlit.app/)

## 🛠️ ローカル環境での実行

### 前提条件
- Python 3.8+
- Google Gemini API Key

### セットアップ

1. リポジトリをクローン
```bash
git clone https://github.com/momokauenoethosai/yukiguni-factory.git
cd yukiguni-factory
```

2. 依存関係をインストール
```bash
pip install -r requirements.txt
```

3. 環境変数を設定
`.env`ファイルを作成し、以下を追加：
```
GOOGLE_GEMINI_API_KEY=your_gemini_api_key_here
MAX_FLYERS=5
```

4. アプリを起動
```bash
streamlit run app.py
```

## ☁️ Streamlit Cloudでのデプロイ

1. GitHubリポジトリをStreamlit Cloudに接続
2. **Secrets**設定で以下を追加：
   ```
   GOOGLE_GEMINI_API_KEY = "your_gemini_api_key_here"
   MAX_FLYERS = "5"
   ```

## 使い方

1. サイドバーでスーパーリストを確認
2. 処理タイプを選択（収集のみ/分析のみ/両方）
3. 「処理を実行」ボタンをクリック
4. リアルタイムでログを確認
5. 結果をタブで表示（商品データ/チラシ画像/統計）

## ファイル構成

```
yukiguni/
├── app.py                          # Streamlit UI
├── src/
│   ├── scrape_chirashi_selenium.py # チラシ収集
│   ├── analyze_chirashi_products.py # AI分析
│   └── filter_period_data.py       # データフィルタリング
├── input/
│   └── super_list.csv              # スーパーリスト
├── output/
│   └── chirashi_data_with_products.csv # 分析結果
└── cache/
    └── images/                      # チラシ画像キャッシュ
```