import csv
import re
import os

def is_valid_period(period_text):
    """
    期間を表す文字列かどうかを判定
    例: "10/3～10/7", "10/1～10/31", "10/3 ～ 10/5" など
    """
    # 日付パターン: 月/日～月/日 または 月/日 ～ 月/日
    date_pattern = r'\d{1,2}/\d{1,2}\s*[～~－-]\s*\d{1,2}/\d{1,2}'

    # パターンにマッチするかチェック
    if re.search(date_pattern, period_text):
        return True

    # 単一日付の場合も期間として扱う（例: "10/1～" や "～10/31"）
    single_date_pattern = r'(\d{1,2}/\d{1,2}\s*[～~－-])|([～~－-]\s*\d{1,2}/\d{1,2})'
    if re.search(single_date_pattern, period_text):
        return True

    return False

def filter_period_data(input_csv, output_csv):
    """
    期間が正しく設定されているデータのみをフィルタリング
    """
    filtered_results = []
    excluded_results = []

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            period = row.get('period', '')

            if is_valid_period(period):
                filtered_results.append(row)
            else:
                excluded_results.append(row)

    # フィルタリングされたデータを保存
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        if filtered_results:
            fieldnames = filtered_results[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filtered_results)

    # 除外されたデータも別ファイルに保存（確認用）
    excluded_file = output_csv.replace('.csv', '_excluded.csv')
    with open(excluded_file, 'w', newline='', encoding='utf-8') as f:
        if excluded_results:
            fieldnames = excluded_results[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(excluded_results)

    print(f"フィルタリング完了:")
    print(f"  - 期間データあり: {len(filtered_results)}件 -> {output_csv}")
    print(f"  - 期間データなし: {len(excluded_results)}件 -> {excluded_file}")

    # 除外されたデータの内容を表示
    if excluded_results:
        print("\n除外されたデータのperiod値:")
        for row in excluded_results:
            print(f"  - '{row['period']}'")

    return filtered_results, excluded_results

if __name__ == "__main__":
    input_file = "../output/chirashi_data_selenium.csv"
    output_file = "../output/chirashi_data_filtered.csv"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, input_file)
    output_path = os.path.join(script_dir, output_file)

    filter_period_data(input_path, output_path)