import os
import sys
import re
import argparse
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import json
import db
import scraper

# ディレクトリ設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# ログディレクトリの作成
os.makedirs(LOG_DIR, exist_ok=True)

# ログ設定（10MBローテーション、最大5世代、UTF-8）
log_file = os.path.join(LOG_DIR, 'anaslo.log')
log_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

logger = logging.getLogger('anaslo-scraper')
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# コンソール出力用の設定（標準出力にも出す）
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(console_handler)

def load_config():
    """設定ファイルを読み込みます。"""
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Configuration file not found: {CONFIG_FILE}")
        sys.exit(1)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to parse config.json: {e}")
        sys.exit(1)

def run_collect():
    """最新データのクローリングを実行します。"""
    logger.info("Starting latest data collection...")
    config = load_config()
    db.backup_database()  # バックアップ実行
    db.init_db()
    
    for hall in config.get('halls', []):
        name = hall['name']
        pref = hall['pref']
        url = hall['list_url']
        
        hall_id = db.get_or_create_hall(name, pref, url)
        try:
            scraper.crawl_latest(hall_id, name, pref, url)
        except Exception as e:
            logger.error(f"Error during collection for {name}: {e}", exc_info=True)
            # 1店舗でエラーが発生しても続行
            
    logger.info("Latest data collection completed.")

def run_backfill(days):
    """過去データの一括取得を実行します。"""
    logger.info(f"Starting backfill collection for past {days} days...")
    config = load_config()
    db.backup_database()
    db.init_db()
    
    for hall in config.get('halls', []):
        name = hall['name']
        pref = hall['pref']
        url = hall['list_url']
        
        hall_id = db.get_or_create_hall(name, pref, url)
        try:
            scraper.crawl_backfill(hall_id, name, pref, url, days)
        except Exception as e:
            logger.error(f"Error during backfill for {name}: {e}", exc_info=True)
            
    logger.info("Backfill collection completed.")

def run_refresh(date_str):
    """指定日のデータ上書きをリフレッシュ実行します。"""
    logger.info(f"Starting data refresh for date {date_str}...")
    config = load_config()
    db.backup_database()
    db.init_db()
    
    for hall in config.get('halls', []):
        name = hall['name']
        pref = hall['pref']
        url = hall['list_url']
        
        hall_id = db.get_or_create_hall(name, pref, url)
        try:
            scraper.crawl_refresh(hall_id, name, pref, url, date_str)
        except Exception as e:
            logger.error(f"Error during refresh for {name} on {date_str}: {e}", exc_info=True)
            
    logger.info("Data refresh completed.")

def run_dashboard():
    """Streamlitダッシュボードを起動します。"""
    logger.info("Launching analysis dashboard...")
    db.backup_database()  # 起動前にバックアップを実行
    app_path = os.path.join(BASE_DIR, 'app.py')
    
    # 仮想環境やWindowsの環境依存を避けるため、sys.executable (現在動いているPython) の -m streamlit を使用
    cmd = [sys.executable, "-m", "streamlit", "run", app_path]
    try:
        # Popenで非同期起動させ、制御を即座に戻す
        subprocess.Popen(cmd)
        logger.info("Dashboard launched in browser. Press Ctrl+C in this terminal to exit.")
    except Exception as e:
        logger.error(f"Failed to launch dashboard: {e}")

def show_interactive_menu():
    """対話式メニューを表示します。"""
    db.init_db()
    while True:
        print("\n=========================================")
        print("   🎰 アナスロ出玉データ収集・分析システム")
        print("=========================================")
        print(" 1. 最新データの自動収集 (未登録分のみ)")
        print(" 2. 過去データの一括収集 (バックフィル)")
        print(" 3. 指定日のデータ上書き (リフレッシュ)")
        print(" 4. 分析ダッシュボードの起動 (Streamlit)")
        print(" 5. 終了")
        print("=========================================")
        
        choice = input("メニュー番号を選択してください [1-5]: ").strip()
        
        if choice == '1':
            run_collect()
        elif choice == '2':
            days_input = input("何日分の過去データを取得しますか？ (例: 30): ").strip()
            try:
                days = int(days_input)
                if days <= 0:
                    raise ValueError
                run_backfill(days)
            except ValueError:
                print("⚠️ 正しい日数を入力してください（1以上の整数）。")
        elif choice == '3':
            date_input = input("上書き更新したい日付を入力してください [YYYY-MM-DD] (例: 2026-06-15): ").strip()
            # 日付フォーマットの簡易チェック
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_input):
                run_refresh(date_input)
            else:
                print("⚠️ 正しい日付フォーマット（YYYY-MM-DD）で入力してください。")
        elif choice == '4':
            run_dashboard()
        elif choice == '5':
            print("システムを終了します。")
            break
        else:
            print("⚠️ 無効な入力です。1〜5の数字を入力してください。")

def main():
    parser = argparse.ArgumentParser(description="アナスロ データ収集・分析システム")
    parser.add_argument('--collect', action='store_true', help='最新の未登録データをクローリング')
    parser.add_argument('--backfill', type=int, help='指定した過去日数分のデータを一括クローリング')
    parser.add_argument('--refresh', type=str, help='指定した日付（YYYY-MM-DD）のデータを上書きクローリング')
    parser.add_argument('--dashboard', action='store_true', help='Streamlitダッシュボードを起動')
    
    args = parser.parse_args()
    
    # 引数がある場合はそれぞれの処理を実行、なければ対話式メニューを表示
    if args.collect:
        run_collect()
    elif args.backfill is not None:
        if args.backfill <= 0:
            logger.error("Backfill days must be a positive integer.")
            sys.exit(1)
        run_backfill(args.backfill)
    elif args.refresh is not None:
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', args.refresh):
            logger.error("Refresh date must be in YYYY-MM-DD format.")
            sys.exit(1)
        run_refresh(args.refresh)
    elif args.dashboard:
        run_dashboard()
    else:
        show_interactive_menu()

if __name__ == '__main__':
    main()
