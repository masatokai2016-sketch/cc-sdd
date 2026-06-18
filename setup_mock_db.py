import sqlite3
import os

DB_FILE = 'tools/anaslo-scraper/anaslo_data.db'

def setup_mock_db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Halls
    cursor.execute('CREATE TABLE halls (id INTEGER PRIMARY KEY, name TEXT, pref TEXT, list_url TEXT)')
    cursor.execute('INSERT INTO halls (name, pref, list_url) VALUES (?, ?, ?)',
                   ("大盛空港通り店", "愛媛県", "http://example.com"))
    hall_id = cursor.lastrowid

    # Daily Summaries
    cursor.execute('''
    CREATE TABLE daily_summaries (
        id INTEGER PRIMARY KEY, hall_id INTEGER, date TEXT, day_of_week TEXT,
        total_difference INTEGER, avg_difference INTEGER, avg_games INTEGER,
        win_rate REAL, win_units INTEGER, total_units INTEGER
    )''')

    # 7のつく日 (2026-06-07)
    cursor.execute('''
    INSERT INTO daily_summaries VALUES (1, ?, '2026-06-07', '日', 5000, 200, 5000, 0.6, 15, 25)
    ''', (hall_id,))
    # 通常日 (2026-06-08)
    cursor.execute('''
    INSERT INTO daily_summaries VALUES (2, ?, '2026-06-08', '月', -1000, -50, 4000, 0.4, 10, 25)
    ''', (hall_id,))

    # Unit Details
    cursor.execute('''
    CREATE TABLE unit_details (
        id INTEGER PRIMARY KEY, summary_id INTEGER, machine_name TEXT, unit_number TEXT,
        unit_number_tail INTEGER, games INTEGER, difference INTEGER, bb_count INTEGER,
        rb_count INTEGER, composite_probability TEXT, bb_probability TEXT, rb_probability TEXT
    )''')

    cursor.execute('''
    INSERT INTO unit_details VALUES
    (1, 1, 'スマスロ北斗の拳', '101', 1, 6000, 2000, 30, 20, '1/120', '1/200', '1/300'),
    (2, 2, 'スマスロ北斗の拳', '101', 1, 4000, -500, 15, 10, '1/160', '1/260', '1/400')
    ''')

    conn.commit()
    conn.close()
    print("Mock DB setup complete.")

if __name__ == '__main__':
    setup_mock_db()
