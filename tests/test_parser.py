import unittest
from bs4 import BeautifulSoup
import sys
import os

# Add the tools directory to the path
sys.path.append(os.path.join(os.getcwd(), 'tools/anaslo-scraper'))
import scraper

class TestAnasloParser(unittest.TestCase):
    def test_parse_date_list(self):
        html = """
        <div class="date-table">
            <div class="table-row"><a href="url1">2026/06/15(月)</a></div>
            <div class="table-row"><a href="url2">2026/06/14(日)</a></div>
        </div>
        <a class="next" href="next_url">Next</a>
        """
        links, next_url = scraper.parse_date_list(html)
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0]['date'], '2026-06-15')
        self.assertEqual(next_url, 'next_url')

    def test_parse_detail_page(self):
        html = """
        <h1 class="entry-title">2026/06/07 大盛空港通り店 データまとめ</h1>
        <table class="total_get_medals_table">
            <tr><th>総差枚</th><td>+10,000</td></tr>
            <tr><th>平均差枚</th><td>+100</td></tr>
            <tr><th>平均G数</th><td>5,000</td></tr>
            <tr><th>勝率</th><td>50.0%(50/100)</td></tr>
        </table>
        <table id="all_data_table">
            <thead>
                <tr><th>機種名</th><th>台番号</th><th>G数</th><th>差枚</th><th>BB</th><th>RB</th><th>BB確率</th><th>RB確率</th></tr>
            </thead>
            <tbody>
                <tr><td>スマスロ北斗の拳</td><td>101</td><td>6000</td><td>2000</td><td>30</td><td>20</td><td>1/200</td><td>1/300</td></tr>
            </tbody>
        </table>
        """
        summary, units = scraper.parse_detail_page(html)
        self.assertEqual(summary['date'], '2026-06-07')
        self.assertEqual(summary['total_difference'], 10000)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]['machine_name'], 'スマスロ北斗の拳')
        self.assertEqual(units[0]['bb_probability'], '1/200')
        self.assertEqual(units[0]['rb_probability'], '1/300')

if __name__ == '__main__':
    unittest.main()
