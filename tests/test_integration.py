import unittest
import sys
import os
import sqlite3
from unittest.mock import patch, MagicMock

# Add the tools directory to the path
sys.path.append(os.path.join(os.getcwd(), 'tools/anaslo-scraper'))
import db
import scraper

class TestIntegration(unittest.TestCase):
    def setUp(self):
        # Use an in-memory database for testing
        db.DB_FILE = 'test_anaslo.db'
        db.init_db()

    def tearDown(self):
        if os.path.exists('test_anaslo.db'):
            os.remove('test_anaslo.db')

    @patch('scraper.fetch_html')
    def test_crawl_latest_pagination(self, mock_fetch):
        # Mocking list page 1
        html_list1 = """
        <div class="date-table">
            <div class="table-row"><a href="url_2026-06-15">2026/06/15(月)</a></div>
        </div>
        <a class="next" href="url_list2">Next</a>
        """
        # Mocking list page 2
        html_list2 = """
        <div class="date-table">
            <div class="table-row"><a href="url_2026-06-14">2026/06/14(日)</a></div>
        </div>
        """
        # Mocking detail pages
        html_detail_template = """
        <h1 class="entry-title">{date_slash} 大盛空港通り店 データまとめ</h1>
        <table class="total_get_medals_table">
            <tr><th>総差枚</th><td>0</td></tr><tr><th>平均差枚</th><td>0</td></tr><tr><th>平均G数</th><td>0</td></tr><tr><th>勝率</th><td>0%</td></tr>
        </table>
        <table id="all_data_table">
            <thead><tr><th>機種名</th><th>台番号</th><th>G数</th><th>差枚</th><th>BB</th><th>RB</th></tr></thead>
            <tbody><tr><td>Test</td><td>101</td><td>100</td><td>100</td><td>1</td><td>1</td></tr></tbody>
        </table>
        """

        # Define mock side effects
        def mock_side_effect(url):
            if 'url_list2' in url: return html_list2
            if 'url_2026-06-15' in url:
                return html_detail_template.format(date_slash='2026/06/15')
            if 'url_2026-06-14' in url:
                return html_detail_template.format(date_slash='2026/06/14')
            return html_list1

        mock_fetch.side_effect = mock_side_effect

        hall_id = db.get_or_create_hall("Test Hall", "Pref", "http://list_url")

        # Run crawl_latest
        with patch('time.sleep'):
            scraper.crawl_latest(hall_id, "Test Hall", "Pref", "http://list_url")

        # Verify both dates are in DB
        self.assertTrue(db.is_date_registered(hall_id, '2026-06-15'))
        self.assertTrue(db.is_date_registered(hall_id, '2026-06-14'))

if __name__ == '__main__':
    unittest.main()
