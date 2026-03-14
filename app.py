import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

# ── 페이지 설정 ──────────────────────────────────────
st.set_page_config(
    page_title="한영외고 야자 대시보드",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; }
    [data-testid="metric-container"] {
        background: white; border: 1px solid #e5e7eb;
        border-radius: 16px; padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    [data-testid="metric-container"] label { color: #6b7280; font-size: 13px; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 2rem; font-weight: 700; color: #1d3a6e;
    }
    .section-title {
        font-size: 1.2rem; font-weight: 700; color: #1d3a6e;
        margin: 24px 0 12px; padding-bottom: 8px;
        border-bottom: 2px solid #2d7ef7;
    }
    .empty-state {
        text-align: center; padding: 40px 20px;
        color: #9ca3af; background: #f9fafb;
        border-radius: 12px; margin: 12px 0;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 6px 16px; font-weight: 600; }
    [data-testid="stSidebar"] { background: #f8faff; }
    #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── 유틸 함수 ────────────────────────────────────────
def empty_state(msg="해당 기간에 데이터가 없습니다."):
    st.markdown(f"""
    <div class="empty-state">
        <div style="font-size:2rem; margin-bottom:8px">📭</div>
        <p style="margin:0; font-size:0.95rem">{msg}</p>
    </div>""", unsafe_allow_html=True)

def safe_nunique(series):
    try: return series.nunique()
    except: return 0

def get_week_range(offset=0):
    today  = datetime.now().date()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    return monday, monday + timedelta(days=6)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

@st.cache_data(ttl=300)
def load_data(sheet_key: str, worksheet_name: str) -> pd.DataFrame:
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SCOPES)
        gc   = gspread.authorize(creds)
        ws   = gc.open_by_key(sheet_key).worksheet(worksheet_name)
        data = ws.get_all_records()
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()

        if '날짜' in df.columns:
            df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
            df = df.dropna(subset=['날짜'])
            df['날짜'] = df['날짜'].dt.normalize()
            day_map = {0:'월',1:'화',2:'수',3:'목',4:'금',5:'토',6:'일'}
            df['요일'] = df['날짜'].dt.dayofweek.map(day_map)

        for col in ['학년','반','번호']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        def get_dept(k):
            try:
                n = int(k)
                if n <= 2:  return '중국어과'
                if n <= 4:  return '일본어과'
                if n <= 6:  return '독일어과'
                if n <= 8:  return '프랑스어과'
                if n <= 10: return '스페인어과'
            except: pass
            return '기타'

        if '반' in df.columns:
            df['어학과'] = df['반'].apply(get_dept)

        return df

    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")
        return pd.DataFrame()

def filter_df(df, start, end):
    if df.empty or '날짜' not in df.columns:
        return df
    try:
        mask = (df['날짜'] >= pd.Timestamp(start)) & (df['날짜'] <= pd.Timestamp(end))
        return df[mask].copy()
    except:
        return df.copy()

# ── 사이드바 ─────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏫 한영외고 야자 대시보드")
    st.markdown("---")

    st.markdown("#### 📊 데이터 연결")
    sheet_key = st.text_input(
        "Google Sheet Key",
        value=st.session_state.get("sheet_key", ""),
        placeholder="스프레드시트 ID 입력",
    )
    worksheet_name = st.text_input(
        "워크시트 이름",
        value=st.session_state.get("worksheet_name", "출석기록"),
    )
    if sheet_key:
        st.session_state["sheet_key"]      = sheet_key
        st.session_state["worksheet_name"] = worksheet_name

    st.markdown("---")
    st.markdown("#### 📅 기간 설정")

    today = datetime.now().date()

    # ── 빠른 기간 버튼 (session_state로 날짜 제어) ──
    if "date_start" not in st.session_state:
        st.session_state.date_start = today - timedelta(days=today.weekday())
    if "date_end" not in st.session_state:
        st.session_state.date_end = today

    col1, col2 = st.columns(2)
    with col1:
        if st.button("이번 주", use_container_width=True):
            s, e = get_week_range(0)
            st.session_state.date_start = s
            st.session_state.date_end   = e
        if st.button("지난 주", use_container_width=True):
            s, e = get_week_range(-1)
            st.session_state.date_start = s
            st.session_state.date_end   = e
    with col2:
        if st.button("이번 달", use_container_width=True):
            st.session_state.date_start = today.replace(day=1)
            st.session_state.date_end   = today
        if st.button("전체 기간", use_container_width=True):
            st.session_state.date_start = today.replace(year=today.year-1)
            st.session_state.date_end   = today

    # 날짜 직접 입력 (버튼 클릭 시 자동 반영)
    date_range = st.date_input(
        "직접 설정",
        value=(st.session_state.date_start, st.session_state.date_end),
        format="YYYY/MM/DD",
        key="date_picker",
    )

    # date_input 직접 변경 시 session_state 동기화
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
        st.session_state.date_start = start_date
        st.session_state.date_end   = end_date
    elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
        # 시작일만 선택된 상태 (아직 종료일 미선택)
        start_date = date_range[0]
        end_date   = date_range[0]
    else:
        start_date = st.session_state.date_start
        end_date   = st.session_state.date_end

    st.markdown(f"<small style='color:#6b7280'>📌 {start_date} ~ {end_date}</small>",
                unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown(f"<small style='color:#9ca3af'>업데이트: {datetime.now().strftime('%H:%M:%S')}</small>",
                unsafe_allow_html=True)

# ── 데이터 로드 ──────────────────────────────────────
if not sheet_key:
    st.markdown("""
    <div style='text-align:center; padding:80px 20px; color:#6b7280;'>
        <div style='font-size:48px; margin-bottom:16px'>📊</div>
        <h2>야간자율학습 출석 대시보드</h2>
        <p>좌측 사이드바에서 Google Sheet Key를 입력해 주세요.</p>
    </div>""", unsafe_allow_html=True)
    st.stop()

with st.spinner("데이터 불러오는 중..."):
    df_all = load_data(sheet_key, worksheet_name)

if df_all.empty:
    st.markdown("""
    <div style='text-align:center; padding:60px 20px; color:#6b7280;'>
        <div style='font-size:40px; margin-bottom:12px'>📭</div>
        <h3>데이터가 없습니다</h3>
        <p>Sheet Key와 워크시트 이름을 확인해 주세요.</p>
    </div>""", unsafe_allow_html=True)
    st.stop()

df = filter_df(df_all, start_date, end_date)

# ── 헤더 ─────────────────────────────────────────────
st.markdown(f"""
<div style='display:flex; align-items:center; gap:12px; margin-bottom:4px'>
    <span style='font-size:2rem'>🏫</span>
    <div>
        <h1 style='margin:0; font-size:1.8rem; color:#1d3a6e'>야간자율학습 출석 대시보드</h1>
        <p style='margin:0; color:#6b7280; font-size:0.85rem'>
            한영외국어고등학교 &nbsp;·&nbsp; 📅 {start_date} ~ {end_date}
            &nbsp;·&nbsp; 전체 {len(df_all)}건 중 기간 내 {len(df)}건
        </p>
    </div>
</div>
""", unsafe_allow_html=True)

# ── 탭 ───────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🏠 오늘 현황", "📈 주차별 추이", "🏫 학년·반별", "🌍 어학과별", "📅 요일별 분석", "👩‍🏫 담임용 조회"
])

# ══════════════════════════════════════════════════
# TAB 1: 오늘 현황
# ══════════════════════════════════════════════════
with tab1:
    today_ts = pd.Timestamp(today)
    df_today = df_all[df_all['날짜'] == today_ts] if '날짜' in df_all.columns else pd.DataFrame()

    st.markdown("<div class='section-title'>📊 오늘 출석 요약</div>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("총 체크인", f"{len(df_today)}건")
    with c2: st.metric("고유 학생 수", f"{safe_nunique(df_today.get('이메일', pd.Series()))}명")
    with c3:
        p1 = 0
        if not df_today.empty and '교시' in df_today.columns and '이메일' in df_today.columns:
            p1 = df_today[df_today['교시'] == '1교시']['이메일'].nunique()
        st.metric("1교시 참여", f"{p1}명")
    with c4:
        p2 = 0
        if not df_today.empty and '교시' in df_today.columns and '이메일' in df_today.columns:
            p2 = df_today[df_today['교시'] == '2~3교시']['이메일'].nunique()
        st.metric("2~3교시 참여", f"{p2}명")

    if df_today.empty:
        empty_state("오늘 출석 데이터가 없습니다.")
    else:
        col_l, col_r = st.columns(2)
        with col_l:
            if '학년' in df_today.columns and '이메일' in df_today.columns:
                gd = (df_today.groupby('학년')['이메일'].nunique()
                      .reset_index().rename(columns={'이메일':'학생수'}).sort_values('학년'))
                gd['학년명'] = gd['학년'].apply(lambda x: f"{int(x)}학년")
                fig = px.bar(gd, x='학년명', y='학생수', color='학생수',
                             color_continuous_scale=['#93c5fd','#1d4ed8'],
                             text='학생수', title="학년별 참여 인원")
                fig.update_traces(textposition='outside')
                fig.update_layout(showlegend=False, coloraxis_showscale=False,
                    plot_bgcolor='white', paper_bgcolor='white',
                    margin=dict(t=40,b=0,l=0,r=0), height=280)
                st.plotly_chart(fig, use_container_width=True)
            else:
                empty_state("학년별 데이터 없음")

        with col_r:
            if '학년' in df_today.columns and '반' in df_today.columns and '이메일' in df_today.columns:
                cd = (df_today.groupby(['학년','반'])['이메일'].nunique()
                      .reset_index().rename(columns={'이메일':'학생수'}))
                cd = cd.dropna(subset=['학년','반'])
                cd = cd[~cd['학년'].astype(str).isin(['미지정',''])]
                cd = cd[~cd['반'].astype(str).isin(['미지정',''])]
                def safe_label_cd(r):
                    try: return f"{int(r['학년'])}-{int(r['반'])}반"
                    except: return "미확인"
                cd['반명'] = cd.apply(safe_label_cd, axis=1)
                fig2 = px.bar(cd, x='반명', y='학생수', color='학년',
                              text='학생수', title="반별 참여 인원",
                              color_continuous_scale='Blues')
                fig2.update_traces(textposition='outside')
                fig2.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                    margin=dict(t=40,b=0,l=0,r=0), height=280,
                    showlegend=False, coloraxis_showscale=False)
                st.plotly_chart(fig2, use_container_width=True)
            else:
                empty_state("반별 데이터 없음")

        st.markdown("<div class='section-title'>오늘 출석 명단</div>", unsafe_allow_html=True)
        cols_show = [c for c in ['학년','반','번호','이름','좌석','교시','시간'] if c in df_today.columns]
        if cols_show:
            st.dataframe(df_today[cols_show].sort_values(
                [c for c in ['학년','반','번호'] if c in cols_show]), use_container_width=True, height=300)
        else:
            empty_state("표시할 컬럼이 없습니다.")

# ══════════════════════════════════════════════════
# TAB 2: 주차별 추이
# ══════════════════════════════════════════════════
with tab2:
    st.markdown("<div class='section-title'>📈 이번 주 vs 지난 주</div>", unsafe_allow_html=True)

    this_s, this_e = get_week_range(0)
    last_s, last_e = get_week_range(-1)
    df_this = filter_df(df_all, this_s, this_e)
    df_last = filter_df(df_all, last_s, last_e)

    this_cnt = safe_nunique(df_this.get('이메일', pd.Series()))
    last_cnt = safe_nunique(df_last.get('이메일', pd.Series()))
    diff     = this_cnt - last_cnt

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("이번 주 참여 학생", f"{this_cnt}명", delta=f"{diff:+d}명")
    with c2: st.metric("이번 주 체크인", f"{len(df_this)}건")
    with c3: st.metric("지난 주 참여 학생", f"{last_cnt}명")
    with c4: st.metric("지난 주 체크인", f"{len(df_last)}건")

    day_order_num = [0,1,2,3,4]
    day_map_ko    = {0:'월',1:'화',2:'수',3:'목',4:'금'}

    def daily_uniq(df_w):
        if df_w.empty or '이메일' not in df_w.columns or '날짜' not in df_w.columns:
            return pd.DataFrame(columns=['요일번호','학생수','요일'])
        d = (df_w.groupby(df_w['날짜'].dt.dayofweek)['이메일']
             .nunique().reset_index())
        d.columns = ['요일번호','학생수']
        d['요일'] = d['요일번호'].map(day_map_ko)
        return d.sort_values('요일번호')

    dc_this = daily_uniq(df_this)
    dc_last = daily_uniq(df_last)

    if dc_this.empty and dc_last.empty:
        empty_state("주차 데이터가 없습니다.")
    else:
        fig = go.Figure()
        if not dc_this.empty:
            fig.add_trace(go.Scatter(x=dc_this['요일'], y=dc_this['학생수'],
                mode='lines+markers+text', name='이번 주',
                line=dict(color='#2d7ef7', width=3), marker=dict(size=10),
                text=dc_this['학생수'], textposition='top center'))
        if not dc_last.empty:
            fig.add_trace(go.Scatter(x=dc_last['요일'], y=dc_last['학생수'],
                mode='lines+markers+text', name='지난 주',
                line=dict(color='#94a3b8', width=2, dash='dash'), marker=dict(size=8),
                text=dc_last['학생수'], textposition='bottom center'))
        fig.update_layout(title="이번 주 vs 지난 주 일별 참여 학생 수",
            xaxis_title="요일", yaxis_title="참여 학생 수",
            plot_bgcolor='white', paper_bgcolor='white',
            legend=dict(orientation='h', y=1.1), height=360,
            margin=dict(t=60,b=20))
        fig.update_xaxes(gridcolor='#f3f4f6')
        fig.update_yaxes(gridcolor='#f3f4f6')
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div class='section-title'>선택 기간 일별 추이</div>", unsafe_allow_html=True)
    if df.empty or '날짜' not in df.columns or '이메일' not in df.columns:
        empty_state("선택 기간에 데이터가 없습니다.")
    else:
        daily = (df.groupby('날짜')['이메일'].nunique()
                 .reset_index().rename(columns={'이메일':'학생수'}).sort_values('날짜'))
        daily['날짜str'] = daily['날짜'].dt.strftime('%m/%d(%a)')
        fig2 = px.area(daily, x='날짜str', y='학생수',
                       title="일별 참여 학생 수", color_discrete_sequence=['#2d7ef7'])
        fig2.update_layout(plot_bgcolor='white', paper_bgcolor='white',
            height=300, margin=dict(t=40,b=20),
            xaxis_title="날짜", yaxis_title="학생 수")
        fig2.update_xaxes(gridcolor='#f3f4f6')
        fig2.update_yaxes(gridcolor='#f3f4f6')
        st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════
# TAB 3: 학년·반별
# ══════════════════════════════════════════════════
with tab3:
    st.markdown("<div class='section-title'>🏫 학년·반별 출석 현황</div>", unsafe_allow_html=True)

    if df.empty or '학년' not in df.columns:
        empty_state("선택 기간에 데이터가 없습니다.")
    else:
        grades = sorted(df['학년'].dropna().unique().astype(int).tolist())
        sel_grade = st.selectbox("학년 선택", ["전체"] + [f"{g}학년" for g in grades])
        df_g = df if sel_grade == "전체" else df[df['학년'] == int(sel_grade.replace('학년',''))]

        if df_g.empty:
            empty_state(f"{sel_grade} 데이터가 없습니다.")
        elif '반' in df_g.columns and '이메일' in df_g.columns:
            summary = (df_g.groupby(['학년','반'])
                       .agg(체크인수=('이메일','count'), 고유학생수=('이메일','nunique'))
                       .reset_index().sort_values(['학년','반']))
            summary = summary.dropna(subset=['학년','반'])
            summary = summary[summary['학년'].astype(str) != '미지정']
            summary = summary[summary['반'].astype(str) != '미지정']
            def make_label(r):
                try:
                    return f"{int(r['학년'])}-{int(r['반'])}반"
                except:
                    return "미확인"
            summary = summary.dropna(subset=['학년','반'])
            summary = summary[~summary['학년'].astype(str).isin(['미지정',''])]
            summary = summary[~summary['반'].astype(str).isin(['미지정',''])]
            def safe_label(r):
                try: return f"{int(r['학년'])}-{int(r['반'])}반"
                except: return "미확인"
            summary['반명'] = summary.apply(safe_label, axis=1)

            col_l, col_r = st.columns([3,2])
            with col_l:
                fig = px.bar(summary, x='반명', y='고유학생수', color='학년',
                             text='고유학생수', title="반별 참여 학생 수",
                             color_continuous_scale='Blues')
                fig.update_traces(textposition='outside')
                fig.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                    height=380, margin=dict(t=40,b=20),
                    showlegend=True, coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
            with col_r:
                st.markdown("**반별 상세 데이터**")
                st.dataframe(summary[['반명','체크인수','고유학생수']]
                    .rename(columns={'반명':'반','체크인수':'체크인','고유학생수':'학생수'}),
                    use_container_width=True, height=380)

        st.markdown("<div class='section-title'>반 상세 보기</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            sel_g2 = st.selectbox("학년", [f"{g}학년" for g in grades], key='drill_g')
        with c2:
            g_num2  = int(sel_g2.replace('학년',''))
            klasses = sorted(df[df['학년']==g_num2]['반'].dropna().unique().astype(int).tolist()) if '반' in df.columns else []
            if klasses:
                sel_k = st.selectbox("반", [f"{k}반" for k in klasses], key='drill_k')
            else:
                sel_k = None
                empty_state("반 데이터가 없습니다.")

        if sel_k:
            k_num  = int(sel_k.replace('반',''))
            df_cls = df[(df['학년']==g_num2) & (df['반']==k_num)]
            if df_cls.empty:
                empty_state(f"{g_num2}학년 {k_num}반 데이터가 없습니다.")
            else:
                mc1, mc2, mc3 = st.columns(3)
                with mc1: st.metric("총 체크인", f"{len(df_cls)}건")
                with mc2: st.metric("참여 학생", f"{safe_nunique(df_cls.get('이메일', pd.Series()))}명")
                with mc3: st.metric("운영 일수", f"{safe_nunique(df_cls.get('날짜', pd.Series()))}일")

                if '이름' in df_cls.columns:
                    group_cols = [c for c in ['번호','이름'] if c in df_cls.columns]
                    stu = (df_cls.groupby(group_cols)
                           .agg(체크인수=('날짜','count'), 출석일수=('날짜','nunique'))
                           .reset_index()
                           .sort_values(group_cols[0]))
                    st.dataframe(stu, use_container_width=True, height=300)
                else:
                    empty_state("이름 컬럼이 없습니다.")

# ══════════════════════════════════════════════════
# TAB 4: 어학과별
# ══════════════════════════════════════════════════
with tab4:
    st.markdown("<div class='section-title'>🌍 어학과별 출석 현황</div>", unsafe_allow_html=True)

    if df.empty or '어학과' not in df.columns or '이메일' not in df.columns:
        empty_state("선택 기간에 데이터가 없습니다.")
    else:
        dept_s = (df.groupby('어학과')
                  .agg(체크인수=('이메일','count'), 고유학생수=('이메일','nunique'),
                       운영일수=('날짜','nunique'))
                  .reset_index().sort_values('고유학생수', ascending=False))
        dept_s['1일평균'] = (dept_s['체크인수'] / dept_s['운영일수'].replace(0,1)).round(1)

        col_l, col_r = st.columns(2)
        with col_l:
            fig = px.pie(dept_s, names='어학과', values='고유학생수',
                         title="어학과별 참여 학생 비율",
                         color_discrete_sequence=px.colors.qualitative.Set2, hole=0.4)
            fig.update_traces(textinfo='label+percent', textfont_size=13)
            fig.update_layout(height=380, margin=dict(t=40,b=0),
                paper_bgcolor='white', legend=dict(orientation='v',y=0.5))
            st.plotly_chart(fig, use_container_width=True)
        with col_r:
            fig2 = px.bar(dept_s, x='어학과', y='고유학생수', color='어학과',
                          text='고유학생수', title="어학과별 참여 학생 수",
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig2.update_traces(textposition='outside', showlegend=False)
            fig2.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                height=380, margin=dict(t=40,b=20), showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("<div class='section-title'>어학과별 일별 추이</div>", unsafe_allow_html=True)
        if '날짜' in df.columns:
            dept_d = (df.groupby(['날짜','어학과'])['이메일']
                      .nunique().reset_index().rename(columns={'이메일':'학생수'}))
            if dept_d.empty:
                empty_state("일별 추이 데이터가 없습니다.")
            else:
                fig3 = px.line(dept_d, x='날짜', y='학생수', color='어학과',
                               title="어학과별 일별 참여 학생 수", markers=True,
                               color_discrete_sequence=px.colors.qualitative.Set2)
                fig3.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                    height=340, margin=dict(t=40,b=20))
                fig3.update_xaxes(gridcolor='#f3f4f6')
                fig3.update_yaxes(gridcolor='#f3f4f6')
                st.plotly_chart(fig3, use_container_width=True)

        st.markdown("**어학과별 상세 데이터**")
        st.dataframe(dept_s, use_container_width=True)

# ══════════════════════════════════════════════════
# TAB 5: 요일별 분석
# ══════════════════════════════════════════════════
with tab5:
    st.markdown("<div class='section-title'>📅 요일별 출석 분석</div>", unsafe_allow_html=True)

    if df.empty or '요일' not in df.columns or '이메일' not in df.columns:
        empty_state("선택 기간에 데이터가 없습니다.")
    else:
        day_order = ['월','화','수','목','금']
        day_s = (df.groupby('요일')
                 .agg(총체크인=('이메일','count'), 학생수=('이메일','nunique'))
                 .reset_index())
        day_s['요일'] = pd.Categorical(day_s['요일'], categories=day_order, ordered=True)
        day_s = day_s.sort_values('요일')

        col_l, col_r = st.columns(2)
        with col_l:
            if day_s.empty:
                empty_state("요일별 데이터가 없습니다.")
            else:
                fig = px.bar(day_s, x='요일', y='총체크인', color='총체크인',
                             color_continuous_scale=['#bfdbfe','#1d4ed8'],
                             text='총체크인', title="요일별 총 체크인 수")
                fig.update_traces(textposition='outside')
                fig.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                    height=340, margin=dict(t=40,b=20), coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)

        with col_r:
            if '교시' in df.columns:
                hm = (df.groupby(['요일','교시'])['이메일']
                      .nunique().reset_index().rename(columns={'이메일':'학생수'}))
                if hm.empty:
                    empty_state("교시×요일 데이터가 없습니다.")
                else:
                    pivot = hm.pivot(index='교시', columns='요일', values='학생수').fillna(0)
                    pivot = pivot[[d for d in day_order if d in pivot.columns]]
                    fig2  = px.imshow(pivot, color_continuous_scale='Blues',
                                      title="요일×교시 히트맵 (학생 수)",
                                      text_auto=True, aspect='auto')
                    fig2.update_layout(height=340, margin=dict(t=40,b=20), paper_bgcolor='white')
                    st.plotly_chart(fig2, use_container_width=True)
            else:
                empty_state("교시 컬럼이 없습니다.")

        st.markdown("<div class='section-title'>어학과 × 요일 비교</div>", unsafe_allow_html=True)
        if '어학과' in df.columns:
            dd = (df.groupby(['요일','어학과'])['이메일']
                  .nunique().reset_index().rename(columns={'이메일':'학생수'}))
            if dd.empty:
                empty_state("어학과×요일 데이터가 없습니다.")
            else:
                dd['요일'] = pd.Categorical(dd['요일'], categories=day_order, ordered=True)
                dd = dd.sort_values('요일')
                fig3 = px.bar(dd, x='요일', y='학생수', color='어학과', barmode='group',
                              title="요일별 어학과 참여 학생 수",
                              color_discrete_sequence=px.colors.qualitative.Set2)
                fig3.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                    height=360, margin=dict(t=40,b=20))
                st.plotly_chart(fig3, use_container_width=True)
        else:
            empty_state("어학과 데이터가 없습니다.")

# ══════════════════════════════════════════════════
# TAB 6: 담임용 조회
# ══════════════════════════════════════════════════
with tab6:
    st.markdown("<div class='section-title'>👩‍🏫 담임용 우리 반 출석 조회</div>", unsafe_allow_html=True)

    if df_all.empty:
        empty_state("데이터가 없습니다.")
    else:
        # 학년/반 선택
        hc1, hc2, hc3 = st.columns(3)
        with hc1:
            valid_grades = sorted([int(g) for g in df_all['학년'].dropna().unique()
                                   if str(g) not in ['미지정',''] and str(g).replace('.0','').isdigit()])
            sel_hgrade = st.selectbox("학년", [f"{g}학년" for g in valid_grades], key='hgrade')
        with hc2:
            h_gnum = int(sel_hgrade.replace('학년',''))
            valid_klasses = sorted([int(k) for k in df_all[df_all['학년']==h_gnum]['반'].dropna().unique()
                                    if str(k) not in ['미지정',''] and str(k).replace('.0','').isdigit()])
            if valid_klasses:
                sel_hklass = st.selectbox("반", [f"{k}반" for k in valid_klasses], key='hklass')
            else:
                st.info("반 데이터가 없습니다.")
                sel_hklass = None
        with hc3:
            view_date = st.date_input("조회 날짜", value=today, key='hdate')

        if sel_hklass:
            h_knum   = int(sel_hklass.replace('반',''))
            view_ts  = pd.Timestamp(view_date)

            # 해당 날짜 해당 반 출석 데이터
            df_homeroom = df_all[
                (df_all['날짜'] == view_ts) &
                (df_all['학년'] == h_gnum) &
                (df_all['반'] == h_knum)
            ]

            # 요약 메트릭
            hm1, hm2, hm3 = st.columns(3)
            with hm1: st.metric("출석 학생 수", f"{df_homeroom['이메일'].nunique() if not df_homeroom.empty else 0}명")
            with hm2:
                p1_cnt = 0
                if not df_homeroom.empty and '교시' in df_homeroom.columns:
                    p1_cnt = df_homeroom[df_homeroom['교시']=='1교시']['이메일'].nunique()
                st.metric("1교시", f"{p1_cnt}명")
            with hm3:
                p2_cnt = 0
                if not df_homeroom.empty and '교시' in df_homeroom.columns:
                    p2_cnt = df_homeroom[df_homeroom['교시']=='2~3교시']['이메일'].nunique()
                st.metric("2~3교시", f"{p2_cnt}명")

            st.markdown("<div class='section-title'>출석 명단</div>", unsafe_allow_html=True)

            if df_homeroom.empty:
                empty_state(f"{view_date} {h_gnum}학년 {h_knum}반 출석 데이터가 없습니다.")
            else:
                show_cols = [c for c in ['번호','이름','교시','좌석','시간','이메일'] if c in df_homeroom.columns]
                sort_cols = [c for c in ['번호','교시'] if c in show_cols]
                st.dataframe(
                    df_homeroom[show_cols].sort_values(sort_cols) if sort_cols else df_homeroom[show_cols],
                    use_container_width=True, height=400
                )

            # 기간별 우리반 현황
            st.markdown("<div class='section-title'>기간 내 우리 반 출석 현황</div>", unsafe_allow_html=True)
            df_cls_period = df[
                (df['학년'] == h_gnum) &
                (df['반'] == h_knum)
            ] if not df.empty and '학년' in df.columns and '반' in df.columns else pd.DataFrame()

            if df_cls_period.empty:
                empty_state("선택 기간에 우리 반 데이터가 없습니다.")
            else:
                # 학생별 출석 횟수
                if '이름' in df_cls_period.columns and '이메일' in df_cls_period.columns:
                    grp_cols = [c for c in ['번호','이름'] if c in df_cls_period.columns]
                    stu_att = (df_cls_period.groupby(grp_cols)
                               .agg(총체크인=('날짜','count'), 출석일수=('날짜','nunique'))
                               .reset_index()
                               .sort_values(grp_cols[0] if grp_cols else '이름'))
                    st.markdown(f"**{h_gnum}학년 {h_knum}반 학생별 출석 현황** ({start_date} ~ {end_date})")
                    st.dataframe(stu_att, use_container_width=True, height=350)

                # 일별 출석 추이
                if '날짜' in df_cls_period.columns and '이메일' in df_cls_period.columns:
                    daily_cls = (df_cls_period.groupby('날짜')['이메일']
                                 .nunique().reset_index().rename(columns={'이메일':'학생수'}))
                    fig_cls = px.bar(daily_cls, x='날짜', y='학생수',
                                     title=f"{h_gnum}학년 {h_knum}반 일별 출석 학생 수",
                                     color_discrete_sequence=['#2d7ef7'])
                    fig_cls.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                        height=280, margin=dict(t=40,b=20))
                    st.plotly_chart(fig_cls, use_container_width=True)

# ── 학생 개인 검색 ────────────────────────────────────
st.markdown("---")
st.markdown("<div class='section-title'>🔍 학생 개인 검색</div>", unsafe_allow_html=True)

search = st.text_input("이름 또는 이메일로 검색",
                       placeholder="예: 홍길동 또는 student@hyfl.hs.kr")
if search:
    if df.empty:
        empty_state("검색할 데이터가 없습니다.")
    else:
        mask = pd.Series([False] * len(df), index=df.index)
        if '이름'  in df.columns: mask = mask | df['이름'].astype(str).str.contains(search, na=False)
        if '이메일' in df.columns: mask = mask | df['이메일'].astype(str).str.contains(search, na=False)

        df_s = df[mask]
        if df_s.empty:
            empty_state(f"'{search}' 검색 결과가 없습니다.")
        else:
            s1, s2, s3 = st.columns(3)
            with s1: st.metric("총 체크인", f"{len(df_s)}건")
            with s2: st.metric("출석 일수", f"{safe_nunique(df_s.get('날짜', pd.Series()))}일")
            with s3: st.metric("참여 교시 수", f"{safe_nunique(df_s.get('교시', pd.Series()))}종류")

            show_cols = [c for c in ['날짜','교시','좌석','학년','반','번호','이름','이메일','시간']
                         if c in df_s.columns]
            st.dataframe(df_s[show_cols].sort_values('날짜', ascending=False),
                         use_container_width=True, height=300)
