import os
import sqlite3
import shutil
from datetime import datetime
import glob

DB_FILE = 'anaslo_data.db'
BACKUP_DIR = 'backup'
MAX_BACKUPS = 5

def get_connection():
    """SQLiteデータベースへの接続を取得します。排他制御用にタイムアウトを設定。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, DB_FILE)
    return sqlite3.connect(db_path, timeout=20.0)

def backup_database():
    """データベースのバックアップを作成し、最大5世代を維持します。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, DB_FILE)
    
    if not os.path.exists(db_path):
        return  # DBファイルがなければバックアップは不要
        
    backup_path = os.path.join(base_dir, BACKUP_DIR)
    os.makedirs(backup_path, exist_ok=True)
    
    # 新しいバックアップのファイル名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    new_backup_file = os.path.join(backup_path, f'anaslo_data_{timestamp}.db')
    
    try:
        shutil.copy2(db_path, new_backup_file)
        print(f"Backup created: {new_backup_file}")
    except Exception as e:
        print(f"Failed to create backup: {e}")
        return
        
    # 古いバックアップの削除（5世代管理）
    backups = sorted(glob.glob(os.path.join(backup_path, 'anaslo_data_*.db')))
    while len(backups) > MAX_BACKUPS:
        oldest = backups.pop(0)
        try:
            os.remove(oldest)
            print(f"Oldest backup removed: {oldest}")
        except Exception as e:
            print(f"Failed to remove oldest backup {oldest}: {e}")

def init_db():
    """データベースの初期化（テーブル・インデックス作成）を行います。"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Hallsテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS halls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        pref TEXT NOT NULL,
        list_url TEXT NOT NULL
    )
    ''')
    
    # Daily Summariesテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        day_of_week TEXT NOT NULL,
        total_difference INTEGER NOT NULL,
        avg_difference INTEGER NOT NULL,
        avg_games INTEGER NOT NULL,
        win_rate REAL NOT NULL,
        win_units INTEGER NOT NULL,
        total_units INTEGER NOT NULL,
        FOREIGN KEY (hall_id) REFERENCES halls (id),
        UNIQUE(hall_id, date)
    )
    ''')
    
    # Unit Detailsテーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS unit_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        summary_id INTEGER NOT NULL,
        machine_name TEXT NOT NULL,
        unit_number TEXT NOT NULL,
        unit_number_tail INTEGER NOT NULL,
        games INTEGER NOT NULL,
        difference INTEGER NOT NULL,
        bb_count INTEGER NOT NULL,
        rb_count INTEGER NOT NULL,
        composite_probability TEXT,
        bb_probability TEXT,
        rb_probability TEXT,
        FOREIGN KEY (summary_id) REFERENCES daily_summaries (id)
    )
    ''')

    # カラムの追加（既存DB移行用）
    try:
        cursor.execute('ALTER TABLE unit_details ADD COLUMN bb_probability TEXT')
    except sqlite3.OperationalError:
        pass  # 既に存在する場合

    try:
        cursor.execute('ALTER TABLE unit_details ADD COLUMN rb_probability TEXT')
    except sqlite3.OperationalError:
        pass  # 既に存在する場合
    
    # インデックス作成
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_summaries_date ON daily_summaries (date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_unit_details_machine ON unit_details (machine_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_unit_details_tail ON unit_details (unit_number_tail)')
    
    conn.commit()
    conn.close()

def get_or_create_hall(name, pref, list_url):
    """店舗情報を取得するか、なければ新しく登録してIDを返します。"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM halls WHERE name = ?', (name,))
    row = cursor.fetchone()
    if row:
        hall_id = row[0]
    else:
        cursor.execute('INSERT INTO halls (name, pref, list_url) VALUES (?, ?, ?)', (name, pref, list_url))
        hall_id = cursor.lastrowid
        conn.commit()
        
    conn.close()
    return hall_id

def is_date_registered(hall_id, date):
    """指定された日付のデータがすでに登録されているか確認します。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM daily_summaries WHERE hall_id = ? AND date = ?', (hall_id, date))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def delete_daily_data(hall_id, date):
    """指定された日付のサマリーおよび台別詳細データを削除します（リフレッシュ用）。"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # まず日別サマリーのIDを取得
        cursor.execute('SELECT id FROM daily_summaries WHERE hall_id = ? AND date = ?', (hall_id, date))
        row = cursor.fetchone()
        if row:
            summary_id = row[0]
            # 詳細データを削除
            cursor.execute('DELETE FROM unit_details WHERE summary_id = ?', (summary_id,))
            # サマリーデータを削除
            cursor.execute('DELETE FROM daily_summaries WHERE id = ?', (summary_id,))
            conn.commit()
            print(f"Deleted existing data for {date}")
            return True
    except Exception as e:
        conn.rollback()
        print(f"Error deleting daily data for {date}: {e}")
        raise e
    finally:
        conn.close()
    return False

def save_daily_data(hall_id, summary_data, units_data):
    """日別サマリーと台別詳細データの一括保存を行います。"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # サマリーの登録
        cursor.execute('''
        INSERT INTO daily_summaries (
            hall_id, date, day_of_week, total_difference, avg_difference, avg_games, win_rate, win_units, total_units
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            hall_id,
            summary_data['date'],
            summary_data['day_of_week'],
            summary_data['total_difference'],
            summary_data['avg_difference'],
            summary_data['avg_games'],
            summary_data['win_rate'],
            summary_data['win_units'],
            summary_data['total_units']
        ))
        summary_id = cursor.lastrowid
        
        # 台別詳細データのバルクインサート
        insert_data = []
        for unit in units_data:
            insert_data.append((
                summary_id,
                unit['machine_name'],
                unit['unit_number'],
                unit['unit_number_tail'],
                unit['games'],
                unit['difference'],
                unit['bb_count'],
                unit['rb_count'],
                unit.get('composite_probability'),
                unit.get('bb_probability'),
                unit.get('rb_probability')
            ))
            
        cursor.executemany('''
        INSERT INTO unit_details (
            summary_id, machine_name, unit_number, unit_number_tail, games, difference, bb_count, rb_count, composite_probability, bb_probability, rb_probability
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', insert_data)
        
        conn.commit()
        print(f"Successfully saved {len(units_data)} records for {summary_data['date']}")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error saving daily data for {summary_data['date']}: {e}")
        raise e
    finally:
        conn.close()
    return False
