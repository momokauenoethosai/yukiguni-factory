import os
import csv
import json
import time
import requests
from datetime import datetime
import pytz
from typing import List, Dict, Tuple
from dotenv import load_dotenv
import google.generativeai as genai
import PIL.Image
from io import BytesIO

load_dotenv()

# Streamlit Secrets または環境変数からAPIキーを取得
try:
    import streamlit as st
    GEMINI_API_KEY = st.secrets.get("GOOGLE_GEMINI_API_KEY") or os.getenv('GOOGLE_GEMINI_API_KEY')
except:
    GEMINI_API_KEY = os.getenv('GOOGLE_GEMINI_API_KEY')

# プロジェクトルートからの動的パス設定
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV_PATH = os.path.join(PROJECT_ROOT, 'output', 'chirashi_data_selenium.csv')
OUTPUT_CSV_PATH = os.path.join(PROJECT_ROOT, 'output', 'chirashi_data_with_products.csv')
IMAGE_CACHE_DIR = os.path.join(PROJECT_ROOT, 'cache', 'images')

os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

def download_image(url: str, base_filename: str, timestamp: str) -> str:
    """画像をダウンロードしてローカルパスを返す"""
    # タイムスタンプ付きファイル名を生成
    name_parts = base_filename.split('.')
    if len(name_parts) > 1:
        filename = f"{name_parts[0]}_{timestamp}.{name_parts[-1]}"
    else:
        filename = f"{base_filename}_{timestamp}.jpg"

    filepath = os.path.join(IMAGE_CACHE_DIR, filename)

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(response.content)
        print(f"Downloaded image: {filename}")
        return filepath
    except Exception as e:
        print(f"Error downloading image {url}: {e}")
        return None

def extract_flyer_metadata(image_path: str) -> dict:
    """画像からチラシのメタデータ（タイトル、期間、食品チラシかどうか）を抽出"""
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        image = PIL.Image.open(image_path)

        prompt = """
        このチラシ画像から以下の情報を抽出してください。JSON形式で返してください：

        {
          "is_food_flyer": "YES"または"NO"（主に食品・飲料・食材を扱っているチラシかどうか）,
          "flyer_title": "チラシのタイトル（例：夜市、パンdeナイト、年末年始ごちそうご予約承り）",
          "period": "期間（例：11/10～11/16、11/1～11/30）"
        }

        注意事項：
        - 食品チラシの判定：野菜、肉、魚、果物、惣菜、パン、飲料、食材などが主体なら"YES"、衣料品・家電・雑貨などなら"NO"
        - チラシタイトル：画像上部やメインに表示されているキャッチコピーやイベント名
        - 期間：有効期間や開催期間（mm/dd～mm/dd形式が理想）
        - 情報が読み取れない場合は空文字""を返してください
        """

        response = model.generate_content([prompt, image])

        try:
            import json
            response_text = response.text.strip()
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            metadata = json.loads(response_text)

            return {
                'is_food_flyer': metadata.get('is_food_flyer', '').upper() == 'YES',
                'flyer_title': metadata.get('flyer_title', ''),
                'period': metadata.get('period', '')
            }
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}")
            print(f"Response text: {response_text[:200]}...")
            # フォールバック: 従来の食品判定のみ
            is_food = "YES" in response.text.upper()
            return {'is_food_flyer': is_food, 'flyer_title': '', 'period': ''}

    except Exception as e:
        print(f"Error extracting flyer metadata: {e}")
        return {'is_food_flyer': False, 'flyer_title': '', 'period': ''}

def is_food_flyer(image_path: str) -> bool:
    """画像が食品チラシかどうかを判定（後方互換性のため残す）"""
    metadata = extract_flyer_metadata(image_path)
    return metadata['is_food_flyer']

def analyze_chirashi_with_gemini(image_path: str, super_name: str, shop_name: str) -> List[Dict]:
    """Gemini APIを使用してチラシ画像から商品情報を抽出"""
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return []

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        image = PIL.Image.open(image_path)

        prompt = f"""
        このスーパーマーケットのチラシ画像から商品情報を抽出してください。
        スーパー名: {super_name}
        店舗名: {shop_name}

        以下の形式で、すべての商品情報をJSON配列として返してください：
        [
          {{
            "product_name": "商品名（ブランド名、商品の詳細な名称、容量、個数なども含めて）",
            "price_without_tax": "税抜価格（数値のみ、円は不要）",
            "price_with_tax": "税込価格（数値のみ、円は不要）",
            "discount": "割引情報（あれば）",
            "category": "カテゴリー（野菜、肉、魚、惣菜、飲料など）"
          }}
        ]

        商品名の記載例：
        - 悪い例：「カレー」「牛乳」「パン」
        - 良い例：「ハウス バーモントカレー 甘口 230g」「明治おいしい牛乳 1000ml」「ヤマザキ 超芳醇 6枚切」

        注意事項：
        - 商品名は画像に記載されているブランド名、詳細な商品名、容量、個数などをすべて含めて記載
        - メーカー名やブランド名が読み取れる場合は必ず含める
        - 容量（g、ml、個など）が記載されている場合は必ず含める
        - 価格が読み取れない場合は "不明" と記載
        - 税抜価格が明記されていない場合は、税込価格から計算（税率10%として）
        - できるだけ多くの商品を抽出してください
        """

        response = model.generate_content([prompt, image])

        response_text = response.text.strip()
        response_text = response_text.replace('```json', '').replace('```', '').strip()

        try:
            products = json.loads(response_text)
            return products if isinstance(products, list) else []
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}")
            print(f"Response text: {response_text[:500]}...")
            return []

    except Exception as e:
        print(f"Error analyzing image with Gemini: {e}")
        return []

def process_chirashi_data():
    """CSVファイルを読み込み、各チラシ画像を分析して結果を保存"""
    with open(INPUT_CSV_PATH, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        rows = list(reader)

    results = []

    # MAX_FLYERSの設定
    try:
        import streamlit as st
        max_flyers_setting = st.secrets.get("MAX_FLYERS") or os.getenv('MAX_FLYERS', str(len(rows)))
    except:
        max_flyers_setting = os.getenv('MAX_FLYERS', str(len(rows)))

    max_flyers = int(max_flyers_setting)
    rows_to_process = rows[:max_flyers]

    # 日本時間で実行時刻をタイムスタンプとして使用
    jst = pytz.timezone('Asia/Tokyo')
    timestamp = datetime.now(jst).strftime("%Y%m%d_%H%M%S")

    # CSVファイルの初期化（ヘッダー書き込み）
    fieldnames = ['url', 'super_name', 'shop_name', 'chirashi_png_path', 'flyer_title', 'period', 'scraped_at',
                  'product_name', 'price_without_tax', 'price_with_tax', 'discount', 'category']

    # 出力ファイルを初期化
    with open(OUTPUT_CSV_PATH, 'w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

    for idx, row in enumerate(rows_to_process):
        # 停止フラグをチェック
        stop_flag_file = os.path.join(PROJECT_ROOT, "temp_stop_flag.txt")
        if os.path.exists(stop_flag_file):
            print("⏹️ 停止要求を受信しました。処理を中断します。")
            break

        print(f"\n📋 Processing {idx + 1}/{len(rows_to_process)}: {row['super_name']} - {row['shop_name']}")
        flyer_title = row.get('flyer_title', '')
        period = row.get('period', '')
        display_title = flyer_title if flyer_title else period
        print(f"🖼️ チラシタイトル: {display_title}")

        image_url = row['chirashi_png_path']
        base_image_filename = f"{row['super_name']}_{row['shop_name']}_{idx}.jpg"
        base_image_filename = base_image_filename.replace('/', '_').replace(' ', '_')

        print(f"📥 画像ダウンロード開始: {base_image_filename}")
        image_path = download_image(image_url, base_image_filename, timestamp)
        if not image_path:
            print(f"❌ 画像ダウンロード失敗")
            continue

        print(f"✅ 画像ダウンロード完了: {base_image_filename}")

        # チラシメタデータを抽出
        print(f"🔍 チラシ情報抽出中...")
        image_metadata = extract_flyer_metadata(image_path)

        if not image_metadata['is_food_flyer']:
            print(f"❌ 非食品チラシのためスキップ")
            continue

        print(f"✅ 食品チラシと判定")

        # メタデータから得られた情報で空白を補完
        extracted_title = image_metadata.get('flyer_title', '')
        extracted_period = image_metadata.get('period', '')

        # 元のCSVデータと画像から抽出したデータをマージ
        final_flyer_title = flyer_title if flyer_title else extracted_title
        final_period = period if period else extracted_period

        print(f"📋 補完後 - タイトル: '{final_flyer_title}' 期間: '{final_period}'")
        print(f"🤖 AI OCR分析開始...")
        products = analyze_chirashi_with_gemini(image_path, row['super_name'], row['shop_name'])

        if products:
            print(f"✅ AI OCR完了: {len(products)}個の商品を検出")
        else:
            print(f"⚠️ AI OCR完了: 商品検出なし")

        # 結果を準備
        rows_to_save = []
        if products:
            for product in products:
                result_row = {
                    'url': row['url'],
                    'super_name': row['super_name'],
                    'shop_name': row['shop_name'],
                    'chirashi_png_path': row['chirashi_png_path'],
                    'flyer_title': final_flyer_title,
                    'period': final_period,
                    'scraped_at': row['scraped_at'],
                    'product_name': product.get('product_name', ''),
                    'price_without_tax': product.get('price_without_tax', ''),
                    'price_with_tax': product.get('price_with_tax', ''),
                    'discount': product.get('discount', ''),
                    'category': product.get('category', '')
                }
                rows_to_save.append(result_row)
                results.append(result_row)
        else:
            result_row = {
                'url': row['url'],
                'super_name': row['super_name'],
                'shop_name': row['shop_name'],
                'chirashi_png_path': row['chirashi_png_path'],
                'flyer_title': final_flyer_title,
                'period': final_period,
                'scraped_at': row['scraped_at'],
                'product_name': '取得失敗',
                'price_without_tax': '',
                'price_with_tax': '',
                'discount': '',
                'category': ''
            }
            rows_to_save.append(result_row)
            results.append(result_row)

        # 逐次保存（追記）
        with open(OUTPUT_CSV_PATH, 'a', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writerows(rows_to_save)

        time.sleep(2)

    print(f"\n分析完了！結果を {OUTPUT_CSV_PATH} に保存しました。")
    print(f"合計 {len(results)} 件の商品情報を抽出しました。")

if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("エラー: GOOGLE_GEMINI_API_KEY が .env ファイルに設定されていません。")
        print(".env ファイルに以下の形式で設定してください：")
        print("GOOGLE_GEMINI_API_KEY=your_actual_api_key")
    else:
        process_chirashi_data()