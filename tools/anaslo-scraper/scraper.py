import re
import time
import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import db

# 一般的なブラウザのUser-Agentリスト
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
]

def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

def fetch_html(url, retries=3, delay=10):
    """HTMLを取得します。通信エラー時の自動リトライ機能付き。"""
    for attempt in range(1, retries + 1):
        try:
            print(f"Fetching: {url} (Attempt {attempt}/{retries})")
            response = requests.get(url, headers=get_headers(), timeout=15.0)
            
            # ステータスコードチェック
            if response.status_code == 503:
                print("HTTP 503: Site is under maintenance or blocking requests.")
                raise requests.exceptions.RequestException("Site maintenance / HTTP 503")
                
            response.raise_for_status()
            # 文字コード設定
            response.encoding = 'utf-8'
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"Network error on attempt {attempt}: {e}")
            if attempt < retries:
                print(f"Waiting {delay} seconds before retry...")
                time.sleep(delay)
            else:
                raise e
    return None

def clean_int(value_str):
    """数値文字列から記号やカンマを除去してintに変換します。変換不能な場合は0を返します。"""
    if not value_str:
        return 0
    # 全角マイナスなどを半角に
    value_str = value_str.replace('–', '-').replace('−', '-').replace('+', '')
    cleaned = re.sub(r'[^\d-]', '', value_str)
    try:
        return int(cleaned)
    except ValueError:
        return 0

def parse_date_list(html_content):
    """店舗データ一覧ページから日付リンクと日付のリストを取得します。"""
    soup = BeautifulSoup(html_content, 'html.parser')

    # 次のページURLの取得
    next_page_tag = soup.find('a', class_='next')
    next_page_url = next_page_tag.get('href') if next_page_tag else None

    date_table = soup.find('div', class_='date-table')
    if not date_table:
        date_table = soup.find('table', id='table')
        
    if not date_table:
        print("Date table not found on list page.")
        return [], next_page_url
        
    date_links = []
    # 各行を走査
    rows = date_table.find_all('div', class_='table-row')
    if not rows:
        rows = date_table.find_all('tr')
        
    for row in rows:
        # aタグを探す
        a_tag = row.find('a')
        if not a_tag:
            continue
            
        href = a_tag.get('href')
        text = a_tag.text.strip()
        
        # 日付フォーマットのパース (例: 2026/06/15(月) -> 2026-06-15)
        match = re.match(r'(\d{4})/(\d{2})/(\d{2})', text)
        if match:
            date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            date_links.append({
                'date': date_str,
                'url': href
            })
            
    return date_links, next_page_url

def parse_detail_page(html_content):
    """詳細ページからサマリー情報と台別詳細情報をパースします。"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. 記事タイトルから日付を抽出 (例:「2026/06/06 大盛空港通り店 データまとめ」)
    title_tag = soup.find('h1', class_='entry-title')
    title_text = title_tag.text.strip() if title_tag else ""
    date_match = re.search(r'(\d{4})[/\-](\d{2})[/\-](\d{2})', title_text)
    if not date_match:
        raise ValueError(f"Could not parse date from page title: {title_text}")
    
    date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
    
    # 曜日の取得
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    weeks = ['月', '火', '水', '木', '金', '土', '日']
    day_of_week = weeks[dt.weekday()]
    
    # 2. サマリーの取得
    summary_table = soup.find('table', class_='total_get_medals_table')
    if not summary_table:
        raise ValueError(f"Summary table (total_get_medals_table) not found for date {date_str}")
        
    summary_headers = [th.text.strip() for th in summary_table.find_all('th')]
    summary_cells = [td.text.strip() for td in summary_table.find_all('td')]
    
    summary_map = dict(zip(summary_headers, summary_cells))
    
    total_diff = clean_int(summary_map.get('総差枚', '0'))
    avg_diff = clean_int(summary_map.get('平均差枚', '0'))
    avg_games = clean_int(summary_map.get('平均G数', '0'))
    
    # 勝率のパース (例: "43.1%(56/130)" または "–")
    win_rate_str = summary_map.get('勝率', '0')
    win_units = 0
    total_units = 0
    win_rate = 0.0
    
    rate_match = re.search(r'([\d\.]+)%\((\d+)/(\d+)\)', win_rate_str)
    if rate_match:
        win_rate = float(rate_match.group(1)) / 100.0
        win_units = int(rate_match.group(2))
        total_units = int(rate_match.group(3))
    else:
        # データがない、あるいは%表記のみなどのフォールバック
        rate_only_match = re.search(r'([\d\.]+)%', win_rate_str)
        if rate_only_match:
            win_rate = float(rate_only_match.group(1)) / 100.0
            
    summary_data = {
        'date': date_str,
        'day_of_week': day_of_week,
        'total_difference': total_diff,
        'avg_difference': avg_diff,
        'avg_games': avg_games,
        'win_rate': win_rate,
        'win_units': win_units,
        'total_units': total_units
    }
    
    # 3. 台番号別詳細データの取得
    detail_table = soup.find('table', id='all_data_table')
    if not detail_table:
        raise ValueError(f"Detail table (all_data_table) not found for date {date_str}")
        
    # ヘッダー行から列マッピングを動的取得
    thead = detail_table.find('thead')
    if not thead:
        raise ValueError("Detail table thead not found.")
        
    headers = [th.text.strip() for th in thead.find_all('th')]
    
    # 列名の対応マッピング
    col_mapping = {
        '機種名': 'machine_name',
        '台番号': 'unit_number',
        'G数': 'games',
        '差枚': 'difference',
        'BB': 'bb_count',
        'RB': 'rb_count',
        '合成確率': 'composite_probability',
        'BB確率': 'bb_probability',
        'RB確率': 'rb_probability'
    }
    
    index_map = {}
    for col_name, key in col_mapping.items():
        if col_name in headers:
            index_map[key] = headers.index(col_name)
            
    # 必須列が存在するかチェック
    required_keys = ['machine_name', 'unit_number', 'games', 'difference', 'bb_count', 'rb_count']
    for req in required_keys:
        if req not in index_map:
            raise ValueError(f"Required column '{req}' could not be mapped from headers: {headers}")
            
    # 各行のパース
    tbody = detail_table.find('tbody')
    if not tbody:
        raise ValueError("Detail table tbody not found.")
        
    units_data = []
    rows = tbody.find_all('tr')
    for row in rows:
        cells = [td.text.strip() for td in row.find_all(['td', 'th'])]
        if len(cells) < len(headers):
            continue
            
        machine_name = cells[index_map['machine_name']]
        
        # パチンコデータの除外（念のため）
        if 'パチンコ' in machine_name or 'P' == machine_name[0] or 'e' == machine_name[0]:
            continue
            
        unit_num_str = cells[index_map['unit_number']]
        if not unit_num_str:
            continue
            
        # 末尾1桁を算出
        try:
            unit_num_tail = int(unit_num_str[-1])
        except ValueError:
            unit_num_tail = 0
            
        games = clean_int(cells[index_map['games']])
        difference = clean_int(cells[index_map['difference']])
        bb_count = clean_int(cells[index_map['bb_count']])
        rb_count = clean_int(cells[index_map['rb_count']])
        
        composite_probability = None
        if 'composite_probability' in index_map:
            composite_probability = cells[index_map['composite_probability']]
            
        bb_probability = None
        if 'bb_probability' in index_map:
            bb_probability = cells[index_map['bb_probability']]

        rb_probability = None
        if 'rb_probability' in index_map:
            rb_probability = cells[index_map['rb_probability']]

        units_data.append({
            'machine_name': machine_name,
            'unit_number': unit_num_str,
            'unit_number_tail': unit_num_tail,
            'games': games,
            'difference': difference,
            'bb_count': bb_count,
            'rb_count': rb_count,
            'composite_probability': composite_probability,
            'bb_probability': bb_probability,
            'rb_probability': rb_probability
        })
        
    return summary_data, units_data

def crawl_page(hall_id, url):
    """指定された詳細URLをスクレイピングしてDBに保存します。"""
    html = fetch_html(url)
    if not html:
        return False
        
    summary_data, units_data = parse_detail_page(html)
    
    # DBへの保存
    db.save_daily_data(hall_id, summary_data, units_data)
    return True

def crawl_latest(hall_id, name, pref, list_url):
    """最新の未登録データをクローリングします（ページネーション対応）。"""
    print(f"Crawl latest started for {name}")

    current_url = list_url
    all_new_dates = []

    # 未登録の日付が見つかる限り、またはページがなくなるまでリストを辿る
    while current_url:
        html_list = fetch_html(current_url)
        if not html_list:
            break

        date_links, next_page_url = parse_date_list(html_list)
        
        page_has_new_date = False
        for item in date_links:
            if not db.is_date_registered(hall_id, item['date']):
                all_new_dates.append(item)
                page_has_new_date = True

        # このページに未登録が1つもなければ、それ以上遡る必要はないと判断（最新順のため）
        if not page_has_new_date:
            break

        current_url = next_page_url
        if current_url:
            time.sleep(random.uniform(1, 2))

    print(f"Found {len(all_new_dates)} new dates to register.")
    
    # 古い日付から順に登録するために、逆順で処理
    registered_count = 0
    for item in reversed(all_new_dates):
        date_str = item['date']
        url = item['url']
        
        print(f"Crawling: {date_str}...")
        try:
            success = crawl_page(hall_id, url)
            if success:
                registered_count += 1
            time.sleep(random.uniform(3, 5))
        except Exception as e:
            print(f"Failed to crawl {date_str}: {e}")
            
    print(f"Crawl latest completed for {name}. Registered {registered_count} new dates.")

def crawl_backfill(hall_id, name, pref, list_url, days):
    """過去の営業日数（days）分のデータを遡って一括収集します（ページネーション対応）。"""
    print(f"Crawl backfill started for {name} (Limit: {days} days)")

    current_url = list_url
    all_target_links = []

    while current_url and len(all_target_links) < days:
        html_list = fetch_html(current_url)
        if not html_list:
            break

        date_links, next_page_url = parse_date_list(html_list)
        all_target_links.extend(date_links)
        
        if len(all_target_links) >= days:
            break

        current_url = next_page_url
        if current_url:
            time.sleep(random.uniform(1, 2))
    
    # 指定件数分に切り出し
    target_links = all_target_links[:days]
    print(f"Backfill targets: {len(target_links)} dates found across pages.")
    
    registered_count = 0
    # 古いものから順にインポートするため、逆順にする
    for item in reversed(target_links):
        date_str = item['date']
        url = item['url']
        
        if db.is_date_registered(hall_id, date_str):
            print(f"{date_str} is already registered. Skipping.")
            continue
            
        try:
            success = crawl_page(hall_id, url)
            if success:
                registered_count += 1
            time.sleep(random.uniform(3, 5))
        except Exception as e:
            print(f"Failed to crawl {date_str}: {e}")
            
    print(f"Backfill completed. Registered {registered_count} dates.")

def crawl_refresh(hall_id, name, pref, list_url, date_str):
    """指定された日付のデータを上書き（リフレッシュ）します。"""
    print(f"Refresh started for {name} on {date_str}")
    
    # 記事URLの一覧を取得して対象日付のURLを探す
    html_list = fetch_html(list_url)
    if not html_list:
        return
        
    date_links, _ = parse_date_list(html_list)
    target_url = None
    for item in date_links:
        if item['date'] == date_str:
            target_url = item['url']
            break
            
    if not target_url:
        # URLを直接組み立てる (例: https://ana-slo.com/YYYY-MM-DD-店舗名-data/)
        # ただし、店舗名はURLエンコードなどの表記揺れがあるため、直接推測
        # ここではconfigのlist_urlから店舗名部分を抜き出してURLを作る
        # (通常は一覧にある日付をリフレッシュするので、ここに来ることは稀です)
        print(f"Date {date_str} not found in the recent list page. Attempting url prediction...")
        # configの list_url の最後にある「-データ一覧/」を「-data/」にして日付を付与する
        clean_list_url = list_url.rstrip('/')
        if clean_list_url.endswith('%e3%83%87%e3%83%bc%e3%82%bf%e4%b8%80%e8%a6%a7'):
            base_url = clean_list_url[:-len('%e3%83%87%e3%83%bc%e3%82%bf%e4%b8%80%e8%a6%a7')]
            target_url = f"https://ana-slo.com/{date_str}-{base_url.split('/')[-1]}-data/"
            
    if not target_url:
        print(f"Could not determine URL for date {date_str}")
        return
        
    # 既存データの削除
    db.delete_daily_data(hall_id, date_str)
    
    # 新規取得
    try:
        success = crawl_page(hall_id, target_url)
        if success:
            print(f"Successfully refreshed data for {date_str}")
        else:
            print(f"Failed to refresh data for {date_str}")
    except Exception as e:
        print(f"Error during refresh for {date_str}: {e}")
