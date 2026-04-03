import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="한영외고 야자 대시보드", page_icon="🏫", layout="wide",
                   initial_sidebar_state="collapsed")

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
        font-size: 1.15rem; font-weight: 700; color: #1d3a6e;
        margin: 20px 0 10px; padding-bottom: 6px;
        border-bottom: 2px solid #2d7ef7;
    }
    .top3-card {
        background: linear-gradient(135deg, #eff4ff, #f5f0ff);
        border: 1px solid #dde8ff; border-radius: 16px;
        padding: 14px 18px; margin-bottom: 10px;
    }
    .gold   { border-left: 4px solid #f59e0b; }
    .silver { border-left: 4px solid #94a3b8; }
    .bronze { border-left: 4px solid #b45309; }
    .empty-state {
        text-align: center; padding: 32px 20px;
        color: #9ca3af; background: #f9fafb;
        border-radius: 12px; margin: 8px 0; font-size: 0.9rem;
    }
    #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── 유틸 ─────────────────────────────────────────────
def empty_state(msg="데이터가 없습니다."):
    st.markdown(f'<div class="empty-state">📭 {msg}</div>', unsafe_allow_html=True)

def safe_int(v):
    try: return int(float(v))
    except: return None

def is_valid(v):
    return v is not None and str(v) not in ['미지정', '', 'nan', 'None']

def get_week_range(offset=0):
    today = datetime.now().date()
    mon   = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    return mon, mon + timedelta(days=6)

def make_label(g, k):
    gi, ki = safe_int(g), safe_int(k)
    if gi and ki: return f"{gi}-{ki}반"
    return "미확인"

MEDALS = ['🥇','🥈','🥉']
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly",
          "https://www.googleapis.com/auth/drive.readonly"]

@st.cache_data(ttl=300)
def load_data(key, ws_name):
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        ws    = gspread.authorize(creds).open_by_key(key).worksheet(ws_name)
        data  = ws.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        if '날짜' in df.columns:
            df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
            df = df.dropna(subset=['날짜'])
            df['날짜'] = df['날짜'].dt.normalize()
            df['요일'] = df['날짜'].dt.dayofweek.map({0:'월',1:'화',2:'수',3:'목',4:'금',5:'토',6:'일'})
        for col in ['학년','반','번호']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        # ★ 핵심: '2~3교시' → '3교시' 로 통일
        if '교시' in df.columns:
            df['교시'] = df['교시'].str.strip().replace('2~3교시', '3교시')
        def get_dept(k):
            try:
                n = int(k)
                if n<=2:  return '중국어과'
                if n<=4:  return '일본어과'
                if n<=6:  return '독일어과'
                if n<=8:  return '프랑스어과'
                if n<=10: return '스페인어과'
            except: pass
            return '기타'
        if '반' in df.columns:
            df['어학과'] = df['반'].apply(get_dept)
        return df
    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_student_list(key):
    """학생목록 시트 로드 — 같은 스프레드시트 내 '학생목록' 워크시트"""
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        ws    = gspread.authorize(creds).open_by_key(key).worksheet("학생목록")
        data  = ws.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        for col in ['학년','반','번호']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        st.warning(f"학생목록 시트 로드 실패: {e}")
        return pd.DataFrame()

def filter_valid(df):
    if df.empty: return df
    d = df.copy()
    for col in ['학년','반']:
        if col in d.columns:
            d = d[d[col].notna()]
            d = d[d[col].astype(str).str.strip().isin(['미지정','']) == False]
    return d

def filter_period(df, start, end):
    if df.empty or '날짜' not in df.columns: return df
    return df[(df['날짜']>=pd.Timestamp(start)) & (df['날짜']<=pd.Timestamp(end))].copy()

# ── 기간 필터 컴포넌트 (TAB 2~5 공용) ────────────────
def period_filter_ui(tab_key):
    s_key = f"{tab_key}_start"
    e_key = f"{tab_key}_end"
    today = datetime.now().date()
    if s_key not in st.session_state:
        st.session_state[s_key] = today - timedelta(days=today.weekday())
    if e_key not in st.session_state:
        st.session_state[e_key] = today

    st.markdown("""<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;
    padding:10px 16px;margin-bottom:12px'>
    <span style='font-size:13px;color:#64748b;font-weight:600'>📅 기간 선택</span></div>""",
    unsafe_allow_html=True)

    c1,c2,c3,c4,c5,c6 = st.columns([1,1,1,1,2,1])
    rerun_needed = False
    with c1:
        if st.button("이번 주", key=f"{tab_key}_w0", use_container_width=True):
            s,e = get_week_range(0); st.session_state[s_key]=s; st.session_state[e_key]=e; rerun_needed=True
    with c2:
        if st.button("지난 주", key=f"{tab_key}_w1", use_container_width=True):
            s,e = get_week_range(-1); st.session_state[s_key]=s; st.session_state[e_key]=e; rerun_needed=True
    with c3:
        if st.button("이번 달", key=f"{tab_key}_m0", use_container_width=True):
            st.session_state[s_key]=today.replace(day=1); st.session_state[e_key]=today; rerun_needed=True
    with c4:
        if st.button("전체", key=f"{tab_key}_all", use_container_width=True):
            st.session_state[s_key]=today.replace(year=today.year-1); st.session_state[e_key]=today; rerun_needed=True
    with c5:
        dr = st.date_input("기간", value=(st.session_state[s_key], st.session_state[e_key]),
                           format="YYYY/MM/DD", label_visibility="collapsed", key=f"{tab_key}_dr")
        if isinstance(dr,(list,tuple)) and len(dr)==2:
            st.session_state[s_key]=dr[0]; st.session_state[e_key]=dr[1]
    with c6:
        if st.button("🔄", key=f"{tab_key}_ref", use_container_width=True, help="새로고침"):
            st.cache_data.clear(); rerun_needed=True
    if rerun_needed: st.rerun()
    return st.session_state[s_key], st.session_state[e_key]

# ── 고정값 ────────────────────────────────────────────
sheet_key = "1LH_AI8jvW-vNn9I8wsj8lIot16vuLzqyjbZfDqcNgM8"
ws_name   = "출석기록"
today     = datetime.now().date()

st.markdown("---")

# ── 데이터 로드 ───────────────────────────────────────
with st.spinner("데이터 불러오는 중..."):
    df_all      = load_data(sheet_key, ws_name)
    df_students = load_student_list(sheet_key)

if df_all.empty:
    st.markdown("""<div style='text-align:center;padding:60px 20px;color:#6b7280'>
        <div style='font-size:40px;margin-bottom:12px'>📭</div>
        <h3>데이터가 없습니다</h3></div>""", unsafe_allow_html=True)
    st.stop()

df_valid = filter_valid(df_all)

# ── 대시보드 헤더 ─────────────────────────────────────
st.markdown(f"""
<div style='display:flex;align-items:center;gap:12px;margin-bottom:4px'>
  <span style='font-size:2rem'>🏫</span>
  <div>
    <h1 style='margin:0;font-size:1.7rem;color:#1d3a6e'>야간자율학습 출석 대시보드</h1>
    <p style='margin:0;color:#6b7280;font-size:0.82rem'>한영외국어고등학교 &nbsp;·&nbsp; 전체 {len(df_valid)}건</p>
  </div>
</div>""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🏠 오늘 현황", "🏆 TOP3 시상", "📈 주차별 추이",
    "🏫 학년·반별", "🌍 어학과별", "👩‍🏫 담임용 조회"
])

# ══════════════════════════════════════════════════
# TAB 1: 오늘 현황
# ══════════════════════════════════════════════════
with tab1:
    if "tab1_selected_day" not in st.session_state:
        st.session_state["tab1_selected_day"] = today

    col_title_t1, col_spacer, col_cal = st.columns([3, 3, 2])
    with col_title_t1:
        st.markdown("<div style='margin-top:8px;font-size:1.1rem;font-weight:700;color:#1d3a6e'>📊 출석 현황</div>",
                    unsafe_allow_html=True)
    with col_cal:
        picked = st.date_input("", value=st.session_state["tab1_selected_day"],
                               max_value=today, format="YYYY/MM/DD",
                               label_visibility="collapsed")
        if picked != st.session_state["tab1_selected_day"]:
            st.session_state["tab1_selected_day"] = picked
            st.rerun()

    selected_day = st.session_state["tab1_selected_day"]

    dow_map = {0:'월',1:'화',2:'수',3:'목',4:'금',5:'토',6:'일'}
    dow = dow_map[selected_day.weekday()]
    is_today_flag = selected_day == today
    badge_text = f"📅 {selected_day.year}년 {selected_day.month}월 {selected_day.day}일 ({dow}){' · 오늘' if is_today_flag else ''}"

    col_badge, col_shortcuts = st.columns([3, 2])
    with col_badge:
        st.markdown(f"""<div style='margin-bottom:12px'>
          <span style='background:#eff6ff;border:1.5px solid #3b82f6;border-radius:20px;
            padding:4px 14px;font-size:12px;font-weight:600;color:#3b82f6'>{badge_text}</span>
        </div>""", unsafe_allow_html=True)
    with col_shortcuts:
        sc1, sc2 = st.columns(2)
        with sc1:
            if st.button("어제", use_container_width=True, key="tab1_yesterday"):
                st.session_state["tab1_selected_day"] = today - timedelta(days=1)
                st.rerun()
        with sc2:
            if st.button("오늘", use_container_width=True, key="tab1_today"):
                st.session_state["tab1_selected_day"] = today
                st.rerun()

    st.markdown("<hr style='border:none;border-top:2px solid #3b82f6;margin-bottom:16px'>", unsafe_allow_html=True)

    today_ts   = pd.Timestamp(selected_day)
    df_today   = df_all[df_all['날짜']==today_ts] if '날짜' in df_all.columns else pd.DataFrame()
    df_today_v = filter_valid(df_today)

    def cnt(df_t, grade=None, period=None):
        d = df_t.copy()
        if grade  and '학년' in d.columns: d = d[d['학년']==grade]
        if period and '교시' in d.columns: d = d[d['교시']==period]
        return d['이메일'].nunique() if '이메일' in d.columns and not d.empty else 0

    # ★ 교시 라벨 통일: '3교시'
    p1_label = '1교시'
    p2_label = '3교시'

    data_table = {
        '학년':   ['1학년','2학년','3학년','✅ 전체'],
        '1교시':  [cnt(df_today_v,1,p1_label),cnt(df_today_v,2,p1_label),
                   cnt(df_today_v,3,p1_label),cnt(df_today_v,None,p1_label)],
        '3교시':  [cnt(df_today_v,1,p2_label),cnt(df_today_v,2,p2_label),
                   cnt(df_today_v,3,p2_label),cnt(df_today_v,None,p2_label)],
    }
    data_table['합계'] = [a+b for a,b in zip(data_table['1교시'],data_table['3교시'])]

    tbody = ""
    for label,v1,v2,vt in zip(data_table['학년'],data_table['1교시'],data_table['3교시'],data_table['합계']):
        is_total = (label=='✅ 전체')
        bg = '#f0fdf4' if is_total else 'white'
        fw = '700'    if is_total else '500'
        fs = '1.2rem' if is_total else '1.4rem'
        tbody += f"<tr style='background:{bg}'><td style='padding:16px 24px;font-weight:{fw};font-size:1rem;border-bottom:1px solid #f3f4f6'>{label}</td><td style='padding:16px;text-align:center;font-weight:{fw};font-size:{fs};color:#3b82f6;border-bottom:1px solid #f3f4f6'>{v1}명</td><td style='padding:16px;text-align:center;font-weight:{fw};font-size:{fs};color:#8b5cf6;border-bottom:1px solid #f3f4f6'>{v2}명</td><td style='padding:16px;text-align:center;font-weight:{fw};font-size:{fs};color:#10b981;border-bottom:1px solid #f3f4f6'>{vt}명</td></tr>"

    # ★ 테이블 헤더도 '3교시'로 변경
    st.markdown(f"""<table style='width:100%;border-collapse:collapse;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(26,47,90,0.08);margin-bottom:20px'>
      <thead><tr style='background:#1d3a6e;color:white'>
        <th style='padding:16px 24px;text-align:left;font-size:0.95rem;width:22%'>학년</th>
        <th style='padding:16px;text-align:center;font-size:0.95rem;width:26%'>1교시<br><span style='font-size:0.75rem;opacity:0.8;font-weight:400'>16:10 ~ 17:40</span></th>
        <th style='padding:16px;text-align:center;font-size:0.95rem;width:26%'>3교시<br><span style='font-size:0.75rem;opacity:0.8;font-weight:400'>18:40 ~ 21:50</span></th>
        <th style='padding:16px;text-align:center;font-size:0.95rem;width:26%'>합계</th>
      </tr></thead><tbody>{tbody}</tbody></table>""", unsafe_allow_html=True)

    if df_today_v.empty:
        empty_state("선택한 날짜의 출석 데이터가 없습니다.")
    else:
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("<div class='section-title'>학년별 참여 인원</div>", unsafe_allow_html=True)
            if '학년' in df_today_v.columns and '이메일' in df_today_v.columns:
                gd = df_today_v.groupby('학년')['이메일'].nunique().reset_index().rename(columns={'이메일':'학생수'})
                gd['학년명'] = gd['학년'].apply(lambda x: f"{int(x)}학년")
                fig = px.bar(gd, x='학년명', y='학생수', color='학생수',
                             color_continuous_scale=['#93c5fd','#1d4ed8'], text='학생수')
                fig.update_traces(textposition='outside')
                fig.update_layout(showlegend=False, coloraxis_showscale=False,
                                  plot_bgcolor='white', paper_bgcolor='white',
                                  margin=dict(t=20,b=0), height=260)
                st.plotly_chart(fig, use_container_width=True)
        with col_r:
            st.markdown("<div class='section-title'>반별 참여 인원</div>", unsafe_allow_html=True)
            if '학년' in df_today_v.columns and '반' in df_today_v.columns:
                cd = df_today_v.groupby(['학년','반'])['이메일'].nunique().reset_index().rename(columns={'이메일':'학생수'})
                cd['반명'] = cd.apply(lambda r: make_label(r['학년'],r['반']), axis=1)
                cd = cd[cd['반명']!='미확인']
                if not cd.empty:
                    fig2 = px.bar(cd, x='반명', y='학생수', color='학년',
                                  text='학생수', color_continuous_scale='Blues')
                    fig2.update_traces(textposition='outside')
                    fig2.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                                       margin=dict(t=20,b=0), height=260,
                                       showlegend=False, coloraxis_showscale=False)
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    empty_state("반별 데이터 없음")

        st.markdown("<div class='section-title'>출석 명단</div>", unsafe_allow_html=True)
        show_cols = [c for c in ['학년','반','번호','이름','교시','좌석','시간'] if c in df_today_v.columns]
        if show_cols:
            sort_by = [c for c in ['학년','반','번호'] if c in show_cols]
            st.dataframe(df_today_v[show_cols].sort_values(sort_by) if sort_by else df_today_v[show_cols],
                         use_container_width=True, height=320)

# ══════════════════════════════════════════════════
# TAB 2: TOP3 시상
# ══════════════════════════════════════════════════
with tab2:
    start_date, end_date = period_filter_ui("t2")
    df = filter_period(df_valid, start_date, end_date)
    st.markdown("<div class='section-title'>🏆 기간 내 TOP3 현황</div>", unsafe_allow_html=True)
    st.caption(f"기간: {start_date} ~ {end_date}")

    if df.empty or '이메일' not in df.columns:
        empty_state("선택 기간에 데이터가 없습니다.")
    else:
        grp_cols = [c for c in ['이메일','이름','학년','반'] if c in df.columns]
        stu = df.groupby(grp_cols).agg(체크인수=('날짜','count'), 출석일수=('날짜','nunique')).reset_index()

        def show_top3(data, title, score_col='체크인수'):
            st.markdown(f"**{title}**")
            top = data.nlargest(3, score_col).reset_index(drop=True)
            if top.empty: empty_state("데이터 없음"); return
            for i, row in top.iterrows():
                medal = MEDALS[i] if i<3 else f"{i+1}위"
                cls   = ['gold','silver','bronze'][i] if i<3 else ''
                name  = row.get('이름',''); grade=safe_int(row.get('학년','')); klass=safe_int(row.get('반',''))
                dept  = row['어학과'] if '어학과' in row.index else ''
                info  = f"{grade}학년 {klass}반 {dept}" if grade and klass else ''
                cnt_v = int(row[score_col]); days = int(row.get('출석일수',0))
                st.markdown(f"""<div class="top3-card {cls}">
                  <span style="font-size:1.3rem">{medal}</span>
                  <strong style="font-size:1rem;margin-left:8px">{name}</strong>
                  <span style="color:#6b7280;font-size:0.85rem;margin-left:8px">{info}</span>
                  <span style="float:right;color:#2d7ef7;font-weight:700">{cnt_v}회 · {days}일</span>
                </div>""", unsafe_allow_html=True)

        st.markdown("<div class='section-title'>🌟 전체 학생 TOP3</div>", unsafe_allow_html=True)
        if '어학과' not in stu.columns and '반' in df.columns:
            stu['어학과'] = stu['반'].apply(lambda k: (
                '중국어과' if k<=2 else '일본어과' if k<=4 else '독일어과'
                if k<=6 else '프랑스어과' if k<=8 else '스페인어과') if pd.notna(k) else '')
        show_top3(stu, "🏅 전체 TOP3")
        st.markdown("---")

        st.markdown("<div class='section-title'>📚 학년별 TOP3</div>", unsafe_allow_html=True)
        gc1,gc2,gc3 = st.columns(3)
        for col,grade_n in zip([gc1,gc2,gc3],[1,2,3]):
            with col:
                show_top3(stu[stu['학년']==grade_n] if '학년' in stu.columns else pd.DataFrame(),
                          f"🎓 {grade_n}학년 TOP3")
        st.markdown("---")

        st.markdown("<div class='section-title'>🏫 반별 TOP3</div>", unsafe_allow_html=True)
        if '학년' in df.columns and '반' in df.columns and '이메일' in df.columns:
            cls_sum = df.groupby(['학년','반']).agg(체크인수=('이메일','count'),고유학생수=('이메일','nunique')).reset_index()
            cls_sum['반명'] = cls_sum.apply(lambda r: make_label(r['학년'],r['반']),axis=1)
            cls_top = cls_sum[cls_sum['반명']!='미확인'].nlargest(3,'체크인수').reset_index(drop=True)
            if not cls_top.empty:
                rc1,rc2,rc3 = st.columns(3)
                for col,(i,row) in zip([rc1,rc2,rc3],cls_top.iterrows()):
                    with col:
                        medal = MEDALS[i] if i<3 else f"{i+1}위"
                        st.markdown(f"""<div class="top3-card {'gold silver bronze'.split()[i] if i<3 else ''}">
                          <div style="font-size:1.5rem;text-align:center">{medal}</div>
                          <div style="text-align:center;font-size:1.1rem;font-weight:700">{row['반명']}</div>
                          <div style="text-align:center;color:#2d7ef7">체크인 {int(row['체크인수'])}회</div>
                          <div style="text-align:center;color:#6b7280;font-size:0.85rem">참여 {int(row['고유학생수'])}명</div>
                        </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════
# TAB 3: 주차별 추이
# ══════════════════════════════════════════════════
with tab3:
    start_date, end_date = period_filter_ui("t3")
    df = filter_period(df_valid, start_date, end_date)

    st.markdown("<div class='section-title'>📈 이번 주 vs 지난 주</div>", unsafe_allow_html=True)
    this_s,this_e = get_week_range(0); last_s,last_e = get_week_range(-1)
    df_this = filter_valid(filter_period(df_all,this_s,this_e))
    df_last = filter_valid(filter_period(df_all,last_s,last_e))
    this_cnt = df_this['이메일'].nunique() if not df_this.empty and '이메일' in df_this.columns else 0
    last_cnt = df_last['이메일'].nunique() if not df_last.empty and '이메일' in df_last.columns else 0

    c1,c2,c3,c4 = st.columns(4)
    with c1: st.metric("이번 주 학생",f"{this_cnt}명",delta=f"{this_cnt-last_cnt:+d}명")
    with c2: st.metric("이번 주 체크인",f"{len(df_this)}건")
    with c3: st.metric("지난 주 학생",f"{last_cnt}명")
    with c4: st.metric("지난 주 체크인",f"{len(df_last)}건")

    day_map = {0:'월',1:'화',2:'수',3:'목',4:'금'}
    def daily_cnt(d):
        if d.empty or '이메일' not in d.columns or '날짜' not in d.columns:
            return pd.DataFrame(columns=['요일번호','학생수','요일'])
        r = d.groupby(d['날짜'].dt.dayofweek)['이메일'].nunique().reset_index()
        r.columns = ['요일번호','학생수']; r['요일']=r['요일번호'].map(day_map)
        return r.sort_values('요일번호')

    fig = go.Figure()
    dc_this = daily_cnt(df_this); dc_last = daily_cnt(df_last)
    if not dc_this.empty:
        fig.add_trace(go.Scatter(x=dc_this['요일'],y=dc_this['학생수'],mode='lines+markers+text',
            name='이번 주',line=dict(color='#2d7ef7',width=3),marker=dict(size=10),
            text=dc_this['학생수'],textposition='top center'))
    if not dc_last.empty:
        fig.add_trace(go.Scatter(x=dc_last['요일'],y=dc_last['학생수'],mode='lines+markers+text',
            name='지난 주',line=dict(color='#94a3b8',width=2,dash='dash'),marker=dict(size=8),
            text=dc_last['학생수'],textposition='bottom center'))
    fig.update_layout(title="이번 주 vs 지난 주",plot_bgcolor='white',paper_bgcolor='white',
        legend=dict(orientation='h',y=1.1),height=340,margin=dict(t=50,b=20))
    fig.update_xaxes(gridcolor='#f3f4f6'); fig.update_yaxes(gridcolor='#f3f4f6')
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div class='section-title'>선택 기간 일별 추이</div>", unsafe_allow_html=True)
    if df.empty or '날짜' not in df.columns:
        empty_state("선택 기간에 데이터가 없습니다.")
    else:
        daily = df.groupby('날짜')['이메일'].nunique().reset_index().rename(columns={'이메일':'학생수'}).sort_values('날짜')
        daily['날짜str'] = daily['날짜'].dt.strftime('%m/%d(%a)')
        fig2 = px.area(daily,x='날짜str',y='학생수',title="일별 참여 학생 수",color_discrete_sequence=['#2d7ef7'])
        fig2.update_layout(plot_bgcolor='white',paper_bgcolor='white',height=280,margin=dict(t=40,b=20))
        st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════
# TAB 4: 학년·반별
# ══════════════════════════════════════════════════
with tab4:
    start_date, end_date = period_filter_ui("t4")
    df = filter_period(df_valid, start_date, end_date)
    st.markdown("<div class='section-title'>🏫 학년·반별 출석 현황</div>", unsafe_allow_html=True)

    if df.empty or '학년' not in df.columns:
        empty_state("선택 기간에 데이터가 없습니다.")
    else:
        valid_g = sorted([int(g) for g in df['학년'].dropna().unique()
                          if is_valid(g) and str(g).replace('.0','').isdigit()])
        sel_grade = st.selectbox("학년 선택",["전체"]+[f"{g}학년" for g in valid_g])
        df_g = df if sel_grade=="전체" else df[df['학년']==int(sel_grade.replace('학년',''))]

        if df_g.empty:
            empty_state(f"{sel_grade} 데이터 없음")
        elif '반' in df_g.columns and '이메일' in df_g.columns:
            sm = df_g.groupby(['학년','반']).agg(체크인수=('이메일','count'),고유학생수=('이메일','nunique')).reset_index()
            sm['반명'] = sm.apply(lambda r: make_label(r['학년'],r['반']),axis=1)
            sm = sm[sm['반명']!='미확인'].sort_values(['학년','반'])
            cl,cr = st.columns([3,2])
            with cl:
                fig = px.bar(sm,x='반명',y='고유학생수',color='학년',text='고유학생수',
                             title="반별 참여 학생 수",color_continuous_scale='Blues')
                fig.update_traces(textposition='outside')
                fig.update_layout(plot_bgcolor='white',paper_bgcolor='white',
                                  height=360,margin=dict(t=40,b=20),coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
            with cr:
                st.markdown("**반별 상세**")
                st.dataframe(sm[['반명','체크인수','고유학생수']].rename(
                    columns={'반명':'반','체크인수':'체크인','고유학생수':'학생수'}),
                    use_container_width=True, height=360)

# ══════════════════════════════════════════════════
# TAB 5: 어학과별
# ══════════════════════════════════════════════════
with tab5:
    start_date, end_date = period_filter_ui("t5")
    df = filter_period(df_valid, start_date, end_date)
    st.markdown("<div class='section-title'>🌍 어학과별 출석 현황</div>", unsafe_allow_html=True)

    if df.empty or '어학과' not in df.columns:
        empty_state("선택 기간에 데이터가 없습니다.")
    else:
        ds = df.groupby('어학과').agg(체크인수=('이메일','count'),고유학생수=('이메일','nunique'),
                                      운영일수=('날짜','nunique')).reset_index().sort_values('고유학생수',ascending=False)
        ds['1일평균'] = (ds['체크인수']/ds['운영일수'].replace(0,1)).round(1)
        cl,cr = st.columns(2)
        with cl:
            fig = px.pie(ds,names='어학과',values='고유학생수',title="어학과별 참여 비율",
                         color_discrete_sequence=px.colors.qualitative.Set2,hole=0.4)
            fig.update_traces(textinfo='label+percent',textfont_size=13)
            fig.update_layout(height=360,margin=dict(t=40,b=0),paper_bgcolor='white')
            st.plotly_chart(fig, use_container_width=True)
        with cr:
            fig2 = px.bar(ds,x='어학과',y='고유학생수',color='어학과',text='고유학생수',
                          title="어학과별 참여 학생 수",color_discrete_sequence=px.colors.qualitative.Set2)
            fig2.update_traces(textposition='outside',showlegend=False)
            fig2.update_layout(plot_bgcolor='white',paper_bgcolor='white',height=360,margin=dict(t=40,b=20))
            st.plotly_chart(fig2, use_container_width=True)
        if '날짜' in df.columns:
            dd = df.groupby(['날짜','어학과'])['이메일'].nunique().reset_index().rename(columns={'이메일':'학생수'})
            if not dd.empty:
                fig3 = px.line(dd,x='날짜',y='학생수',color='어학과',title="어학과별 일별 추이",
                               markers=True,color_discrete_sequence=px.colors.qualitative.Set2)
                fig3.update_layout(plot_bgcolor='white',paper_bgcolor='white',height=320,margin=dict(t=40,b=20))
                st.plotly_chart(fig3, use_container_width=True)
        st.dataframe(ds, use_container_width=True)

# ══════════════════════════════════════════════════
# TAB 6: 담임용 조회 — 학생목록 연동 + 요일별 출석표
# ══════════════════════════════════════════════════
with tab6:
    st.markdown("<div class='section-title'>👩‍🏫 담임용 우리 반 출석 조회</div>", unsafe_allow_html=True)

    valid_all_g = sorted([int(g) for g in df_valid['학년'].dropna().unique()
                          if is_valid(g) and str(g).replace('.0','').isdigit()]) \
                  if not df_valid.empty and '학년' in df_valid.columns else []

    if not valid_all_g:
        empty_state("유효한 학년 데이터가 없습니다.")
    else:
        if "t6_week_offset" not in st.session_state:
            st.session_state["t6_week_offset"] = 0

        hc1, hc2, hc3, hc4 = st.columns([1, 1, 2.5, 0.5])

        with hc1:
            sel_hg = st.selectbox("학년", [f"{g}학년" for g in valid_all_g], key='hgrade')
            h_gnum = int(sel_hg.replace('학년',''))

        with hc2:
            valid_hk = sorted([int(k) for k in df_valid[df_valid['학년']==h_gnum]['반'].dropna().unique()
                if is_valid(k) and str(k).replace('.0','').isdigit()]) if '반' in df_valid.columns else []
            if valid_hk:
                sel_hk = st.selectbox("반", [f"{k}반" for k in valid_hk], key='hklass')
                h_knum = int(sel_hk.replace('반',''))
            else:
                sel_hk = None; h_knum = None

        with hc3:
            ws, we = get_week_range(st.session_state["t6_week_offset"])
            week_label = f"{ws.month}/{ws.day}(월) ~ {we.month}/{we.day}(일)"
            st.markdown(f"<div style='font-size:12px;color:#6b7280;margin-bottom:6px'>조회 주간</div>", unsafe_allow_html=True)
            nav1, nav2, nav3 = st.columns([1,2,1])
            with nav1:
                if st.button("◀ 이전 주", use_container_width=True, key="t6_prev"):
                    st.session_state["t6_week_offset"] -= 1; st.rerun()
            with nav2:
                st.markdown(f"<div style='background:#f1f5f9;border-radius:8px;padding:7px 12px;text-align:center;font-size:13px;font-weight:600;color:#1d3a6e'>📅 {week_label}</div>", unsafe_allow_html=True)
            with nav3:
                if st.button("다음 주 ▶", use_container_width=True, key="t6_next"):
                    st.session_state["t6_week_offset"] += 1; st.rerun()

        with hc4:
            st.markdown("<div style='font-size:12px;color:#6b7280;margin-bottom:6px'>&nbsp;</div>", unsafe_allow_html=True)
            if st.button("🔄", use_container_width=True, key="t6_ref", help="새로고침"):
                st.cache_data.clear(); st.rerun()

        if not sel_hk or not h_knum:
            empty_state("반 데이터가 없습니다.")
        else:
            st.markdown("---")

            week_start = ws
            week_end   = we

            if not df_students.empty and '학년' in df_students.columns and '반' in df_students.columns:
                class_students = df_students[
                    (df_students['학년']==h_gnum) & (df_students['반']==h_knum)
                ].copy().sort_values('번호') if '번호' in df_students.columns else \
                df_students[(df_students['학년']==h_gnum) & (df_students['반']==h_knum)].copy()
            else:
                class_students = pd.DataFrame()

            df_week = df_valid[
                (df_valid['학년']==h_gnum) &
                (df_valid['반']==h_knum) &
                (df_valid['날짜'] >= pd.Timestamp(week_start)) &
                (df_valid['날짜'] <= pd.Timestamp(week_end))
            ].copy() if not df_valid.empty else pd.DataFrame()

            total_students    = len(class_students) if not class_students.empty else \
                                (df_week['이름'].nunique() if not df_week.empty and '이름' in df_week.columns else 0)
            attended_students = df_week['이름'].nunique() if not df_week.empty and '이름' in df_week.columns else 0
            not_attended      = max(0, total_students - attended_students)
            total_checkins    = len(df_week)

            m1,m2,m3,m4 = st.columns(4)
            with m1: st.metric("전체 학생", f"{total_students}명")
            with m2: st.metric("이번 주 참여", f"{attended_students}명")
            with m3: st.metric("미참여", f"{not_attended}명",
                               delta=f"-{not_attended}" if not_attended>0 else "0",
                               delta_color="inverse")
            with m4: st.metric("총 체크인", f"{total_checkins}건")

            st.markdown("---")

            dow_kor  = {0:'월',1:'화',2:'수',3:'목',4:'금'}
            week_days = []
            d = week_start
            while d <= week_end:
                if d.weekday() < 5:
                    week_days.append(d)
                d += timedelta(days=1)

            if not class_students.empty and '이름' in class_students.columns:
                if '번호' in class_students.columns:
                    student_rows = class_students[['번호','이름']].drop_duplicates().values.tolist()
                else:
                    student_rows = [[None, n] for n in class_students['이름'].unique()]
            elif not df_week.empty and '이름' in df_week.columns:
                if '번호' in df_week.columns:
                    student_rows = df_week[['번호','이름']].drop_duplicates().sort_values('번호').values.tolist()
                else:
                    student_rows = [[None, n] for n in df_week['이름'].unique()]
            else:
                student_rows = []

            # ★ 범례: '2~3교시' → '3교시'
            st.markdown(f"""
            <div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:10px'>
              <div style='font-size:1.05rem;font-weight:700;color:#1d3a6e'>
                📋 {h_gnum}학년 {h_knum}반 — 학생별 요일·교시 출석 현황
              </div>
              <div style='display:flex;gap:8px;font-size:12px;align-items:center;flex-wrap:wrap'>
                <span style='background:#dbeafe;color:#1e40af;padding:2px 10px;border-radius:4px;font-weight:600'>1교시</span>
                <span style='background:#ede9fe;color:#5b21b6;padding:2px 10px;border-radius:4px;font-weight:600'>3교시</span>
                <span style='background:#d1fae5;color:#065f46;padding:2px 10px;border-radius:4px;font-weight:600'>둘 다</span>
                <span style='color:#9ca3af'>— 미참여</span>
              </div>
            </div>""", unsafe_allow_html=True)

            if not student_rows:
                empty_state("표시할 학생 데이터가 없습니다.")
            else:
                day_headers = ""
                for day in week_days:
                    dow_str  = dow_kor[day.weekday()]
                    date_str = f"{day.month}/{day.day}"
                    day_headers += f"<th style='padding:10px 6px;text-align:center;min-width:76px'>{dow_str}<br><span style='font-size:11px;opacity:0.8;font-weight:400'>{date_str}</span></th>"

                tbody_rows = ""
                for s_info in student_rows:
                    s_num  = s_info[0] if len(s_info) > 0 else None
                    s_name = s_info[1] if len(s_info) > 1 else ""

                    week_total = 0
                    row_cells  = ""

                    for day in week_days:
                        day_ts = pd.Timestamp(day)
                        if not df_week.empty and '날짜' in df_week.columns and '이름' in df_week.columns:
                            day_rec = df_week[(df_week['날짜']==day_ts) & (df_week['이름']==s_name)]
                            periods = set(day_rec['교시'].tolist()) if '교시' in day_rec.columns and not day_rec.empty else set()
                        else:
                            periods = set()

                        has_p1 = '1교시' in periods
                        # ★ '2~3교시' → '3교시' 로 통일
                        has_p2 = '3교시' in periods

                        if has_p1 and has_p2:
                            cell = "<span style='background:#d1fae5;color:#065f46;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600'>둘 다</span>"
                            week_total += 2
                        elif has_p1:
                            cell = "<span style='background:#dbeafe;color:#1e40af;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600'>1교시</span>"
                            week_total += 1
                        elif has_p2:
                            # ★ 셀 표시도 '3교시'
                            cell = "<span style='background:#ede9fe;color:#5b21b6;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600'>3교시</span>"
                            week_total += 1
                        else:
                            cell = "<span style='color:#d1d5db;font-size:14px'>—</span>"

                        row_cells += f"<td style='padding:10px 6px;text-align:center;border-bottom:1px solid #f3f4f6'>{cell}</td>"

                    if week_total == 0:
                        badge = f"<span style='background:#fef2f2;color:#991b1b;border:1px solid #fecaca;border-radius:12px;padding:2px 10px;font-size:11px;font-weight:600'>0회</span>"
                    elif week_total >= 8:
                        badge = f"<span style='background:#d1fae5;color:#065f46;border:1px solid #6ee7b7;border-radius:12px;padding:2px 10px;font-size:11px;font-weight:600'>{week_total}회 ⭐</span>"
                    else:
                        badge = f"<span style='background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;border-radius:12px;padding:2px 10px;font-size:11px;font-weight:600'>{week_total}회</span>"

                    num_str = f"<span style='font-size:10px;color:#9ca3af;display:block'>{int(s_num)}번</span>" if s_num else ""
                    row_bg  = "#fef2f2" if week_total == 0 else "white"

                    tbody_rows += f"""<tr style='background:{row_bg}'>
                      <td style='padding:10px 14px;border-bottom:1px solid #f3f4f6;white-space:nowrap'>
                        {num_str}<span style='font-weight:600'>{s_name}</span>
                      </td>
                      {row_cells}
                      <td style='padding:10px 6px;text-align:center;border-bottom:1px solid #f3f4f6'>{badge}</td>
                    </tr>"""

                st.markdown(f"""
                <div style='overflow-x:auto;border-radius:16px;box-shadow:0 4px 24px rgba(26,47,90,0.08);margin-bottom:12px'>
                <table style='width:100%;border-collapse:collapse;font-size:13px'>
                  <thead>
                    <tr style='background:#1d3a6e;color:white'>
                      <th style='padding:12px 14px;text-align:left;min-width:90px'>학생</th>
                      {day_headers}
                      <th style='padding:10px 6px;text-align:center;min-width:72px'>주간 합계</th>
                    </tr>
                  </thead>
                  <tbody>{tbody_rows}</tbody>
                </table>
                </div>
                <div style='font-size:11px;color:#9ca3af;margin-bottom:16px'>
                  ⭐ 주간 8회 이상(1+3교시 모두) &nbsp;·&nbsp; 🔴 미참여 학생은 행 배경 연빨간색 &nbsp;·&nbsp; 학생목록 시트 기준
                </div>""", unsafe_allow_html=True)

            st.markdown("<div class='section-title'>📈 이번 주 일별 출석 추이</div>", unsafe_allow_html=True)
            if not df_week.empty and '날짜' in df_week.columns and '이메일' in df_week.columns:
                dc = df_week.groupby('날짜')['이메일'].nunique().reset_index().rename(columns={'이메일':'학생수'})
                dc['날짜str'] = dc['날짜'].dt.strftime('%m/%d(%a)')
                figc = px.bar(dc, x='날짜str', y='학생수',
                              title=f"{h_gnum}학년 {h_knum}반 일별 출석",
                              color_discrete_sequence=['#2d7ef7'], text='학생수')
                figc.update_traces(textposition='outside')
                figc.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                                   height=260, margin=dict(t=40,b=20))
                st.plotly_chart(figc, use_container_width=True)
            else:
                empty_state("이번 주 출석 데이터가 없습니다.")

# ── 학생 개인 검색 ────────────────────────────────────
st.markdown("---")
st.markdown("<div class='section-title'>🔍 학생 개인 검색</div>", unsafe_allow_html=True)
search = st.text_input("이름 또는 이메일로 검색", placeholder="예: 홍길동 또는 student@hyfl.hs.kr")
if search and not df_valid.empty:
    mask = pd.Series([False]*len(df_valid), index=df_valid.index)
    if '이름'  in df_valid.columns: mask = mask | df_valid['이름'].astype(str).str.contains(search,na=False)
    if '이메일' in df_valid.columns: mask = mask | df_valid['이메일'].astype(str).str.contains(search,na=False)
    ds = df_valid[mask]
    if ds.empty:
        empty_state(f"'{search}' 검색 결과가 없습니다.")
    else:
        s1,s2,s3 = st.columns(3)
        with s1: st.metric("총 체크인",f"{len(ds)}건")
        with s2: st.metric("출석 일수",f"{ds['날짜'].nunique() if '날짜' in ds.columns else 0}일")
        with s3: st.metric("교시 종류",f"{ds['교시'].nunique() if '교시' in ds.columns else 0}종류")
        sc = [c for c in ['날짜','교시','좌석','학년','반','번호','이름','시간'] if c in ds.columns]
        st.dataframe(ds[sc].sort_values('날짜',ascending=False) if '날짜' in sc else ds[sc],
                     use_container_width=True, height=300)
