import csv
import os
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
import pytz

load_dotenv()

def parse_flyer_info(text: str) -> tuple[str, str]:
    """チラシ情報を期間とタイトルに分離
    Returns: (flyer_title, period)
    """
    if not text or not text.strip():
        return text, ""

    # 期間パターンを検出（例: 11/10～11/16, 11/1～11/30, 10/1～10/31）
    period_patterns = [
        r'(\d{1,2}/\d{1,2}\s*～\s*\d{1,2}/\d{1,2})',  # 11/10～11/16
        r'(\d{1,2}/\d{1,2}\s*～\s*\d{1,2}/\d{1,2})',  # 11/1～11/30 (スペース付き)
        r'(\d{1,2}/\d{1,2}\s*-\s*\d{1,2}/\d{1,2})',   # ハイフン区切り
        r'(\d{4}/\d{1,2}/\d{1,2}\s*～\s*\d{4}/\d{1,2}/\d{1,2})',  # 年付き
    ]

    for pattern in period_patterns:
        match = re.search(pattern, text)
        if match:
            period = match.group(1).strip()
            # 残りの部分をタイトルとする
            flyer_title = text.replace(match.group(0), "").strip()

            # 期間のみの場合はタイトルを空にする
            if not flyer_title or flyer_title == period:
                return "", period
            else:
                return flyer_title, period

    # 期間パターンが見つからない場合は全てタイトルとする
    return text, ""

def quick_keyword_filter(title: str) -> str:
    """キーワードベースで素早い判定を行う
    Returns: 'FOOD', 'NON_FOOD', 'UNKNOWN'
    """
    if not title or not title.strip():
        return 'UNKNOWN'

    title_lower = title.lower()

    # 明確に食品関連のキーワード
    food_keywords = [
        'パン', 'ごちそう', 'グルメ', '夜市', '食', '肉', '魚', '野菜', '果物',
        '惣菜', '生鮮', 'タイムセール', 'おせち', 'ケーキ', '刺身', '弁当',
        'デリカ', 'ベーカリー', '酒', 'ビール', '定期便', '予約承り'
    ]

    # 明確に非食品のキーワード
    non_food_keywords = [
        'コスメ', '化粧品', '衣料', 'ファッション', '家電', '雑貨', '文具',
        'インテリア', 'サイクル', '自転車', 'おもちゃ', '玩具', '本', '書籍',
        'CD', 'DVD', 'ゲーム', 'スポーツ', '靴', 'バッグ', '時計', 'アクセサリー'
    ]

    # 非食品キーワードチェック
    for keyword in non_food_keywords:
        if keyword in title:
            return 'NON_FOOD'

    # 食品キーワードチェック
    for keyword in food_keywords:
        if keyword in title:
            return 'FOOD'

    # 期間表記のみの場合は食品扱い（一般的なタイムセールなど）
    if '/' in title and '～' in title:
        return 'FOOD'

    return 'UNKNOWN'

def is_food_flyer_by_title(title: str) -> bool:
    """2段階判定でチラシタイトルから食品チラシかどうかを判定"""
    if not title or not title.strip():
        return True  # タイトルが空の場合はデフォルトで含める

    # 第1段階: キーワードベースの高速判定
    keyword_result = quick_keyword_filter(title)

    if keyword_result == 'FOOD':
        print(f"Keyword filtering: '{title}' -> FOOD (confirmed)")
        return True
    elif keyword_result == 'NON_FOOD':
        print(f"Keyword filtering: '{title}' -> NON-FOOD (confirmed)")
        return False

    # 第2段階: 判定が曖昧な場合のみGemini APIを使用
    print(f"Keyword filtering: '{title}' -> UNKNOWN, using Gemini...")

    try:
        # Streamlit Secrets または環境変数からAPIキーを取得
        try:
            import streamlit as st
            api_key = st.secrets.get("GOOGLE_GEMINI_API_KEY") or os.getenv('GOOGLE_GEMINI_API_KEY')
        except:
            api_key = os.getenv('GOOGLE_GEMINI_API_KEY')

        if not api_key:
            print("Warning: GOOGLE_GEMINI_API_KEY not found, defaulting to FOOD")
            return True

        # API制限対策: 6秒待機
        time.sleep(6)

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""
        以下のチラシのタイトルを見て、主に食品・飲料・食材を扱っているチラシかどうか判定してください。

        タイトル: "{title}"

        判定基準:
        - 食品チラシ: 野菜、肉、魚、果物、惣菜、パン、飲料、食材、夜市、ごちそう、グルメなど食品関連
        - 非食品チラシ: 化粧品、コスメ、衣料品、ファッション、家電、雑貨、文具、インテリアなど

        回答は「YES」（食品チラシ）または「NO」（非食品チラシ）のみでお答えください。
        期間のみの表記（例：10/1～10/31）の場合は「YES」と回答してください。
        """

        response = model.generate_content(prompt)
        result = "YES" in response.text.upper()
        print(f"Gemini filtering: '{title}' -> {'FOOD' if result else 'NON-FOOD'}")
        return result

    except Exception as e:
        print(f"Error in Gemini filtering for '{title}': {e}")
        return True  # エラーの場合はデフォルトで含める

def scrape_chirashi_data_selenium(input_csv, output_csv):
    results = []
    total_items = 0
    filtered_items = 0
    # 日本時間でタイムスタンプを生成
    jst = pytz.timezone('Asia/Tokyo')
    scraped_at = datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')

    # Chrome options for headless mode
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    driver = webdriver.Chrome(options=options)

    try:
        with open(input_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row['url']
                super_name = row['super_name']
                shop_name = row['shop_name']

                try:
                    print(f"Fetching URL: {url}")
                    driver.get(url)

                    # Wait for the flier_list to be populated
                    print("Waiting for content to load...")
                    wait = WebDriverWait(driver, 10)
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "info-item")))

                    # Additional wait for all dynamic content
                    time.sleep(3)

                    # Get page source after JavaScript execution
                    page_source = driver.page_source

                    # Save HTML for inspection
                    html_filename = f"../output/{shop_name}_selenium_response.html"
                    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), html_filename)
                    with open(html_path, 'w', encoding='utf-8') as html_file:
                        html_file.write(page_source)
                    print(f"HTML saved to: {html_path}")

                    # Parse with BeautifulSoup
                    soup = BeautifulSoup(page_source, 'html.parser')

                    flier_list = soup.find('div', id='flier_list', class_='info-list')

                    if flier_list:
                        info_items = flier_list.find_all('div', class_='info-item')

                        for item in info_items:
                            link = item.find('a', class_='info-link')
                            if link:
                                href = link.get('href', '')
                                if href:
                                    full_url = urljoin(url, href)

                                    img = link.find('img', class_='info-item__img')
                                    img_src = ''
                                    if img:
                                        img_src = img.get('src', '')
                                        if img_src:
                                            img_src = urljoin(url, img_src)

                                    title_elem = link.find('h4', class_='info-item__title')
                                    raw_text = title_elem.text.strip() if title_elem else ''

                                    # タイトルと期間を分離
                                    flyer_title, period = parse_flyer_info(raw_text)

                                    total_items += 1

                                    # 2段階判定でタイトルから食品チラシかどうかを判定
                                    print(f"チラシURL取得: {raw_text} -> タイトル:'{flyer_title}' 期間:'{period}'")
                                    if is_food_flyer_by_title(raw_text):
                                        results.append({
                                            'url': full_url,
                                            'super_name': super_name,
                                            'shop_name': shop_name,
                                            'chirashi_png_path': img_src,
                                            'flyer_title': flyer_title,
                                            'period': period,
                                            'scraped_at': scraped_at
                                        })
                                        filtered_items += 1
                                        print(f"✅ 食品チラシとして追加: {period}")
                                    else:
                                        print(f"❌ 非食品チラシとしてスキップ: {period}")

                        print(f"Successfully scraped {len(info_items)} items from {shop_name}")
                    else:
                        print(f"No flier_list found for {shop_name}")

                except TimeoutException:
                    print(f"Timeout waiting for content to load for {shop_name}")
                except Exception as e:
                    print(f"Error processing {shop_name}: {e}")

    finally:
        driver.quit()

    # Save results to CSV
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['url', 'super_name', 'shop_name', 'chirashi_png_path', 'flyer_title', 'period', 'scraped_at']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n=== Scraping Summary ===")
    print(f"Total items found: {total_items}")
    print(f"Food flyers (after filtering): {filtered_items}")
    print(f"Non-food flyers (filtered out): {total_items - filtered_items}")
    print(f"Results saved to: {output_csv}")

if __name__ == "__main__":
    input_file = "../input/super_list.csv"
    output_file = "../output/chirashi_data_selenium.csv"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, input_file)
    output_path = os.path.join(script_dir, output_file)

    scrape_chirashi_data_selenium(input_path, output_path)