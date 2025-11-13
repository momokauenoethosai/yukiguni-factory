import csv
import os
import requests
import time
from google import genai
from google.genai import types
import json

def download_image(url, save_path):
    """画像をダウンロード"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"画像ダウンロードエラー: {e}")
        return False

def analyze_chirashi_with_gemini(image_path):
    """Gemini APIでチラシ画像を分析"""
    try:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()

        client = genai.Client()

        prompt = """
        このチラシ画像から商品情報を抽出してください。
        各商品について以下の情報をJSON形式で返してください：
        - product_name: 商品名
        - price_excluding_tax: 税抜価格（数値のみ、円マークや税抜表記は除く）

        注意点：
        1. 価格は税抜価格を抽出してください
        2. 税抜価格が明記されていない場合は、税込価格から計算してください（税率10%として）
        3. 価格が読み取れない場合は null としてください
        4. 最大10商品まで抽出してください

        以下のJSON形式で返してください：
        {
            "products": [
                {"product_name": "商品名1", "price_excluding_tax": 100},
                {"product_name": "商品名2", "price_excluding_tax": 200}
            ]
        }
        """

        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type='image/jpeg',
                ),
                prompt
            ]
        )

        # レスポンスからJSON部分を抽出
        response_text = response.text

        # JSON部分を抽出（```json ... ``` の形式に対応）
        if '```json' in response_text:
            start = response_text.find('```json') + 7
            end = response_text.find('```', start)
            json_text = response_text[start:end].strip()
        else:
            # JSONオブジェクトを直接探す
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            json_text = response_text[start:end]

        # JSONをパース
        data = json.loads(json_text)
        return data.get('products', [])

    except json.JSONDecodeError as e:
        print(f"JSON解析エラー: {e}")
        print(f"レスポンス: {response_text}")
        return []
    except Exception as e:
        print(f"Gemini API エラー: {e}")
        return []

def process_chirashi_data(input_csv, output_csv):
    """チラシデータを処理してGeminiで分析"""
    results = []

    # 画像保存用ディレクトリ作成
    image_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../temp_images')
    os.makedirs(image_dir, exist_ok=True)

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        for idx, row in enumerate(rows):
            print(f"\n処理中 [{idx+1}/{len(rows)}]: {row['shop_name']} - {row['period']}")

            # 画像をダウンロード
            image_url = row['chirashi_png_path']
            image_filename = f"chirashi_{idx+1}.jpg"
            image_path = os.path.join(image_dir, image_filename)

            if download_image(image_url, image_path):
                print(f"画像ダウンロード完了: {image_filename}")

                # Geminiで分析
                print("Geminiで画像分析中...")
                products = analyze_chirashi_with_gemini(image_path)

                if products:
                    # 各商品ごとに行を作成
                    for product in products:
                        result_row = row.copy()
                        result_row['product_name'] = product.get('product_name', '')
                        result_row['price_excluding_tax'] = product.get('price_excluding_tax', '')
                        results.append(result_row)

                    print(f"  {len(products)}個の商品を抽出しました")
                else:
                    # 商品が見つからない場合も元データは保持
                    result_row = row.copy()
                    result_row['product_name'] = ''
                    result_row['price_excluding_tax'] = ''
                    results.append(result_row)
                    print("  商品情報が抽出できませんでした")

                # API制限対策のための待機
                time.sleep(2)
            else:
                print(f"画像ダウンロード失敗: {image_url}")
                # ダウンロード失敗時も元データは保持
                result_row = row.copy()
                result_row['product_name'] = ''
                result_row['price_excluding_tax'] = ''
                results.append(result_row)

    # 結果をCSVに保存
    if results:
        fieldnames = ['url', 'super_name', 'shop_name', 'chirashi_png_path', 'period',
                      'product_name', 'price_excluding_tax']

        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        print(f"\n処理完了: 合計 {len(results)} 件のデータを保存しました")
        print(f"結果ファイル: {output_csv}")
    else:
        print("処理するデータがありません")

if __name__ == "__main__":
    input_file = "../output/chirashi_data_filtered.csv"
    output_file = "../output/chirashi_data_with_products.csv"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, input_file)
    output_path = os.path.join(script_dir, output_file)

    print("Gemini APIキーが環境変数に設定されていることを確認してください")
    print("環境変数: GOOGLE_GENAI_API_KEY または GOOGLE_API_KEY")

    process_chirashi_data(input_path, output_path)