import csv
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse

def scrape_chirashi_data(input_csv, output_csv):
    results = []

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row['url']
            super_name = row['super_name']
            shop_name = row['shop_name']

            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()

                # Save HTML to file for inspection
                html_filename = f"../output/{shop_name}_response.html"
                html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), html_filename)
                with open(html_path, 'w', encoding='utf-8') as html_file:
                    html_file.write(response.text)
                print(f"HTML saved to: {html_path}")

                soup = BeautifulSoup(response.content, 'html.parser')

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
                                period = title_elem.text.strip() if title_elem else ''

                                results.append({
                                    'url': full_url,
                                    'super_name': super_name,
                                    'shop_name': shop_name,
                                    'chirashi_png_path': img_src,
                                    'period': period
                                })

                    print(f"Successfully scraped {len(info_items)} items from {shop_name}")
                else:
                    print(f"No flier_list found for {shop_name}")

            except requests.RequestException as e:
                print(f"Error fetching {url}: {e}")
            except Exception as e:
                print(f"Error parsing data for {shop_name}: {e}")

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['url', 'super_name', 'shop_name', 'chirashi_png_path', 'period']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nTotal items scraped: {len(results)}")
    print(f"Results saved to: {output_csv}")

if __name__ == "__main__":
    input_file = "../input/super_list.csv"
    output_file = "../output/chirashi_data.csv"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, input_file)
    output_path = os.path.join(script_dir, output_file)

    scrape_chirashi_data(input_path, output_path)