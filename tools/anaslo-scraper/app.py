import streamlit as st
import pandas as pd
import altair as alt
import db

# ページ基本設定
st.set_page_config(
    page_title="パチスロ出玉データ分析ダッシュボード",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSSでデザイン調整
st.markdown("""
<style>
    .reportview-container {
        background: #f0f2f6;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        border: 1px solid #e1e4e8;
    }
</style>
""", unsafe_allow_html=True)

# データベース接続
db.init_db()

# キャッシュしてデータ取得の負荷を下げる
@st.cache_data(ttl=600)
def load_halls():
    conn = db.get_connection()
    df = pd.read_sql_query("SELECT id, name, pref FROM halls", conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_daily_summaries(hall_id, start_date, end_date):
    conn = db.get_connection()
    query = """
        SELECT date, day_of_week, total_difference, avg_difference, avg_games, win_rate, win_units, total_units
        FROM daily_summaries
        WHERE hall_id = ? AND date BETWEEN ? AND ?
        ORDER BY date DESC
    """
    df = pd.read_sql_query(query, conn, params=(int(hall_id), start_date, end_date))
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_unit_details(hall_id, start_date, end_date):
    conn = db.get_connection()
    query = """
        SELECT ud.machine_name, ud.unit_number, ud.unit_number_tail, ud.games, ud.difference, ud.bb_count, ud.rb_count, ud.composite_probability, ds.date, ds.day_of_week
        FROM unit_details ud
        JOIN daily_summaries ds ON ud.summary_id = ds.id
        WHERE ds.hall_id = ? AND ds.date BETWEEN ? AND ?
    """
    df = pd.read_sql_query(query, conn, params=(int(hall_id), start_date, end_date))
    conn.close()
    return df

# タイトル
st.title("🎰 パチスロ出玉データ分析ダッシュボード")
st.caption("アナスロから自動収集した実績データを多角的に分析します。")

# 店舗情報の読み込み
halls_df = load_halls()

if halls_df.empty:
    st.warning("⚠️ データベースに店舗情報が存在しません。まずクローラーを実行してデータを取得してください。")
    st.stop()

# ----------------- サイドバーUI -----------------
st.sidebar.header("🔍 フィルター設定")

# 1. 店舗選択
hall_names = halls_df["name"].tolist()
selected_hall_name = st.sidebar.selectbox("店舗を選択", hall_names)
selected_hall_id = halls_df[halls_df["name"] == selected_hall_name]["id"].values[0]

# 2. 期間選択
period_option = st.sidebar.selectbox(
    "分析期間を選択",
    ["直近30日間", "直近60日間", "直近90日間", "全期間", "カスタム範囲"]
)

# 最小・最大日付の取得
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute("SELECT MIN(date), MAX(date) FROM daily_summaries WHERE hall_id = ?", (int(selected_hall_id),))
min_date_val, max_date_val = cursor.fetchone()
conn.close()

if not min_date_val or not max_date_val:
    st.info("💡 選択した店舗の営業データがありません。クローラーを実行してデータを取得してください。")
    st.stop()

max_date = pd.to_datetime(max_date_val)
min_date = pd.to_datetime(min_date_val)

if period_option == "直近30日間":
    start_date = max_date - pd.Timedelta(days=30)
    end_date = max_date
elif period_option == "直近60日間":
    start_date = max_date - pd.Timedelta(days=60)
    end_date = max_date
elif period_option == "直近90日間":
    start_date = max_date - pd.Timedelta(days=90)
    end_date = max_date
elif period_option == "全期間":
    start_date = min_date
    end_date = max_date
else:  # カスタム範囲
    start_date_input = st.sidebar.date_input("開始日", min_date.date(), min_value=min_date.date(), max_value=max_date.date())
    end_date_input = st.sidebar.date_input("終了日", max_date.date(), min_value=min_date.date(), max_value=max_date.date())
    start_date = pd.to_datetime(start_date_input)
    end_date = pd.to_datetime(end_date_input)

start_date_str = start_date.strftime('%Y-%m-%d')
end_date_str = end_date.strftime('%Y-%m-%d')

# 3. 分析対象設定
analysis_target = st.sidebar.radio("分析対象", ["店舗全体", "特定機種に絞る"])

# データロード
summaries_df = load_daily_summaries(selected_hall_id, start_date_str, end_date_str)
units_df = load_unit_details(selected_hall_id, start_date_str, end_date_str)

if summaries_df.empty or units_df.empty:
    st.warning("指定された期間のデータが存在しません。期間を変更するかデータを取得してください。")
    st.stop()

# 機種リストの取得（部分一致検索対応用の機種選択UI）
all_machines = sorted(units_df["machine_name"].unique())

selected_machine = None
if analysis_target == "特定機種に絞る":
    machine_search = st.sidebar.text_input("機種名検索（キーワード入力）", "")
    filtered_machines = [m for m in all_machines if machine_search.lower() in m.lower()]
    
    if filtered_machines:
        selected_machine = st.sidebar.selectbox("対象機種を選択", filtered_machines)
        # 台データを該当機種のみにフィルタリング
        units_df = units_df[units_df["machine_name"] == selected_machine]
    else:
        st.sidebar.error("該当する機種がありません。")
        st.stop()

# ----------------- メインコンテンツ -----------------

# KPI表示用の集計
if analysis_target == "店舗全体":
    avg_total_diff = summaries_df["total_difference"].mean()
    avg_unit_diff = summaries_df["avg_difference"].mean()
    avg_games = summaries_df["avg_games"].mean()
    avg_win_rate = summaries_df["win_rate"].mean()
    total_days = len(summaries_df)
    
    st.subheader(f"📊 {selected_hall_name} の全体成績 (期間内: {total_days}日分)")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("平均総差枚", f"{avg_total_diff:+.0f} 枚")
    col2.metric("台平均差枚", f"{avg_unit_diff:+.0f} 枚")
    col3.metric("台平均回転数", f"{avg_games:.0f} G")
    col4.metric("平均勝率", f"{avg_win_rate * 100:.1f} %")
else:
    # 機種別集計
    total_units_run = len(units_df)
    avg_unit_diff = units_df["difference"].mean()
    avg_games = units_df["games"].mean()
    win_units_count = len(units_df[units_df["difference"] > 0])
    win_rate = win_units_count / total_units_run if total_units_run > 0 else 0.0
    
    st.subheader(f"🎰 {selected_machine} の詳細データ")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("総稼働台数 (延べ)", f"{total_units_run} 台")
    col2.metric("台平均差枚", f"{avg_unit_diff:+.0f} 枚")
    col3.metric("台平均回転数", f"{avg_games:.0f} G")
    col4.metric("平均勝率", f"{win_rate * 100:.1f} % ({win_units_count}/{total_units_run})")

st.markdown("---")

# 1. 曜日別・日付末尾別の分析
tab1, tab2, tab3 = st.tabs(["📅 曜日・末尾日分析", "🔢 台番号末尾分析", "🏆 機種別ランキング"])

with tab1:
    st.write("### 曜日別・日付末尾別の傾向")
    
    # データの集計先定義
    if analysis_target == "店舗全体":
        # 店舗全体は daily_summaries から算出
        df_for_days = summaries_df.copy()
        df_for_days["day_tail"] = df_for_days["date"].apply(lambda x: x.split("-")[-1][-1])
        
        # 曜日別
        dow_summary = df_for_days.groupby("day_of_week").agg(
            avg_diff=("avg_difference", "mean"),
            win_rate=("win_rate", "mean")
        ).reindex(['月', '火', '水', '木', '金', '土', '日'])
        
        # 日付末尾別
        tail_summary = df_for_days.groupby("day_tail").agg(
            avg_diff=("avg_difference", "mean"),
            win_rate=("win_rate", "mean")
        )
    else:
        # 機種別は台別詳細データから算出
        df_for_days = units_df.copy()
        df_for_days["day_tail"] = df_for_days["date"].apply(lambda x: x.split("-")[-1][-1])
        
        # 曜日別
        dow_summary = df_for_days.groupby("day_of_week").apply(
            lambda x: pd.Series({
                'avg_diff': x['difference'].mean(),
                'win_rate': len(x[x['difference'] > 0]) / len(x) if len(x) > 0 else 0
            })
        ).reindex(['月', '火', '水', '木', '金', '土', '日'])
        
        # 日付末尾別
        tail_summary = df_for_days.groupby("day_tail").apply(
            lambda x: pd.Series({
                'avg_diff': x['difference'].mean(),
                'win_rate': len(x[x['difference'] > 0]) / len(x) if len(x) > 0 else 0
            })
        )

    # 曜日別グラフ
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.write("#### 曜日ごとの平均差枚数")
        dow_summary = dow_summary.reset_index()
        chart_dow = alt.Chart(dow_summary).mark_bar().encode(
            x=alt.X('day_of_week:N', sort=['月', '火', '水', '木', '金', '土', '日'], title="曜日"),
            y=alt.Y('avg_diff:Q', title="平均差枚"),
            color=alt.condition(
                alt.datum.avg_diff > 0,
                alt.value("#ff5c70"),  # 赤系（プラス）
                alt.value("#4f86f7")   # 青系（マイナス）
            ),
            tooltip=['day_of_week', 'avg_diff']
        ).properties(height=300)
        st.altair_chart(chart_dow, use_container_width=True)
        
    with col_right:
        st.write("#### 日付の末尾（1の位）ごとの平均差枚数")
        tail_summary = tail_summary.reset_index()
        chart_tail = alt.Chart(tail_summary).mark_bar().encode(
            x=alt.X('day_tail:N', title="日付の末尾"),
            y=alt.Y('avg_diff:Q', title="平均差枚"),
            color=alt.condition(
                alt.datum.avg_diff > 0,
                alt.value("#ff5c70"),
                alt.value("#4f86f7")
            ),
            tooltip=['day_tail', 'avg_diff']
        ).properties(height=300)
        st.altair_chart(chart_tail, use_container_width=True)

    # 特定日のイベント日分析（5のつく日、ゾロ目の日、通常日）
    st.write("#### イベント日 vs 通常日（比較分析）")
    
    # イベント判定関数の適用
    def classify_event_day(date_str):
        day = int(date_str.split("-")[-1])
        month = int(date_str.split("-")[1])
        # 5のつく日
        if day in [5, 15, 25]:
            return "5のつく日"
        # ゾロ目の日
        elif day in [11, 22] or month == day:
            return "ゾロ目の日"
        else:
            return "通常日"
            
    df_for_days["event_class"] = df_for_days["date"].apply(classify_event_day)
    
    if analysis_target == "店舗全体":
        event_summary = df_for_days.groupby("event_class").agg(
            avg_diff=("avg_difference", "mean"),
            win_rate=("win_rate", "mean")
        ).reset_index()
    else:
        event_summary = df_for_days.groupby("event_class").apply(
            lambda x: pd.Series({
                'avg_diff': x['difference'].mean(),
                'win_rate': len(x[x['difference'] > 0]) / len(x) if len(x) > 0 else 0
            })
        ).reset_index()
        
    chart_event = alt.Chart(event_summary).mark_bar().encode(
        x=alt.X('event_class:N', sort=["通常日", "5のつく日", "ゾロ目の日"], title="営業区分"),
        y=alt.Y('avg_diff:Q', title="平均差枚"),
        color=alt.Color('event_class:N', legend=None),
        tooltip=['event_class', 'avg_diff']
    ).properties(height=250)
    st.altair_chart(chart_event, use_container_width=True)


with tab2:
    st.write("### 台番号の末尾（0〜9）分析")
    st.caption("台番号の末尾1桁ごとの差枚数を分析し、高設定が投入されやすい末尾傾向を視覚化します。")
    
    # 常に台別詳細(units_df)から算出
    tail_units_summary = units_df.groupby("unit_number_tail").apply(
        lambda x: pd.Series({
            'avg_diff': x['difference'].mean(),
            'win_rate': (len(x[x['difference'] > 0]) / len(x) * 100) if len(x) > 0 else 0,
            'total_units': len(x)
        })
    ).reset_index()
    
    col_l2, col_r2 = st.columns(2)
    
    with col_l2:
        st.write("#### 台末尾ごとの平均差枚")
        chart_unit_tail_diff = alt.Chart(tail_units_summary).mark_bar().encode(
            x=alt.X('unit_number_tail:N', title="台番号の末尾"),
            y=alt.Y('avg_diff:Q', title="平均差枚"),
            color=alt.condition(
                alt.datum.avg_diff > 0,
                alt.value("#ff5c70"),
                alt.value("#4f86f7")
            ),
            tooltip=['unit_number_tail', 'avg_diff']
        ).properties(height=300)
        st.altair_chart(chart_unit_tail_diff, use_container_width=True)
        
    with col_r2:
        st.write("#### 台末尾ごとの勝率 (%)")
        chart_unit_tail_win = alt.Chart(tail_units_summary).mark_bar().encode(
            x=alt.X('unit_number_tail:N', title="台番号の末尾"),
            y=alt.Y('win_rate:Q', scale=alt.Scale(domain=[0, 100]), title="勝率 (%)"),
            color=alt.value("#fcb900"),
            tooltip=['unit_number_tail', 'win_rate']
        ).properties(height=300)
        st.altair_chart(chart_unit_tail_win, use_container_width=True)
        
    st.write("#### 台番号末尾データテーブル")
    st.dataframe(
        tail_units_summary.rename(columns={
            'unit_number_tail': '台番号末尾',
            'avg_diff': '平均差枚 (枚)',
            'win_rate': '勝率 (%)',
            'total_units': '稼働台数'
        }).style.format({
            '平均差枚 (枚)': '{:+.0f}',
            '勝率 (%)': '{:.1f}%'
        }),
        use_container_width=True
    )


with tab3:
    st.write("### 機種別ランキング")
    st.caption("指定された期間で稼働した全スロット機種の集計ランキングです。")
    
    # 常に元の units_df から集計（もし特定機種に絞っている場合は全体ランキングが見れないため、全データから再集計）
    raw_units_df = load_unit_details(selected_hall_id, start_date_str, end_date_str)
    
    machine_summary = raw_units_df.groupby("machine_name").apply(
        lambda x: pd.Series({
            'total_diff': x['difference'].sum(),
            'avg_diff': x['difference'].mean(),
            'avg_games': x['games'].mean(),
            'win_rate': (len(x[x['difference'] > 0]) / len(x) * 100) if len(x) > 0 else 0,
            'total_units': len(x)
        })
    ).reset_index()
    
    machine_summary = machine_summary.sort_values(by="avg_diff", ascending=False).reset_index(drop=True)
    
    # カラム名見直し
    ranking_display_df = machine_summary.rename(columns={
        'machine_name': '機種名',
        'total_diff': '総差枚数 (枚)',
        'avg_diff': '台平均差枚 (枚)',
        'avg_games': '平均ゲーム数',
        'win_rate': '勝率 (%)',
        'total_units': '総稼働台数'
    })
    
    st.dataframe(
        ranking_display_df.style.format({
            '総差枚数 (枚)': '{:+.0f}',
            '台平均差枚 (枚)': '{:+.0f}',
            '平均ゲーム数': '{:.0f}',
            '勝率 (%)': '{:.1f}%'
        }),
        use_container_width=True
    )
