"""관리자 탭 — admin 전용."""
import os
import datetime
from pathlib import Path
import streamlit as st


def render_tab_admin():
    """🔧 관리자 전용 탭 — admin 계정에서만 보임"""
    st.header("🔧 관리자 — 시스템 운영")
    st.caption("admin 전용 — 시스템 상태 확인, 영상 수집, 강제 작업, 공용 데이터 편집")

    # ──────────────── 1. 시스템 상태 ────────────────
    with st.expander("📊 시스템 상태 (cron · Pinecone · 서버)", expanded=True):
        st.markdown("**🌲 Pinecone 인덱스**")
        try:
            from utils.pinecone_store import PineconeStore
            store = PineconeStore()
            stats = store.index.describe_index_stats()
            pc1, pc2, pc3 = st.columns(3)
            pc1.metric("총 벡터", f"{stats.total_vector_count:,}")
            ns = stats.namespaces or {}
            pc2.metric("요약본", f"{ns.get('stock-summaries').vector_count if ns.get('stock-summaries') else 0:,}")
            pc3.metric("원문", f"{ns.get('stock-raw-chunks').vector_count if ns.get('stock-raw-chunks') else 0:,}")
        except Exception as e:
            st.warning(f"Pinecone 조회 실패: {e}")

        st.markdown("**⏰ cron 작업 상태**")
        log_dir = Path(__file__).resolve().parents[2] / "logs"
        cron_jobs = [
            ("🗞️ 데일리 신문 자동 발행", "auto_paper.log", "매일 KST 07:00"),
            ("🎤 유튜버 알림 갱신", "video_alerts.log", "이틀에 1회 (KST 06:00)"),
            ("🔔 가격 알림 체크", "alerts.log", "장중 30분마다"),
        ]
        for name, fname, schedule in cron_jobs:
            log = log_dir / fname
            if log.exists():
                lines = log.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
                last_line = lines[-1][:120] if lines else "(빈 로그)"
                mtime = datetime.datetime.fromtimestamp(log.stat().st_mtime)
                st.markdown(
                    f"- **{name}** · {schedule}  \n"
                    f"  마지막 실행: <span style='color:#94A3B8'>{mtime.strftime('%Y-%m-%d %H:%M')}</span>  \n"
                    f"  <span style='color:#64748B; font-size:0.8rem;'>└ {last_line}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"- **{name}** · {schedule} — <span style='color:#FF4B4B;'>로그 없음</span>",
                            unsafe_allow_html=True)

        st.markdown("**🖥️ 서버 / 디스크**")
        try:
            import shutil
            total, used, free = shutil.disk_usage("/")
            sv1, sv2, sv3 = st.columns(3)
            sv1.metric("디스크 사용", f"{used / 1e9:.1f} GB")
            sv2.metric("디스크 여유", f"{free / 1e9:.1f} GB")
            data_size = sum(f.stat().st_size for f in Path("data").rglob("*") if f.is_file()) if Path("data").exists() else 0
            sv3.metric("data/ 폴더", f"{data_size / 1e6:.2f} MB")
        except Exception as e:
            st.caption(f"서버 상태 조회 실패: {e}")

    # ──────────────── 2. API 비용 모니터 ────────────────
    with st.expander("💸 API 비용 모니터", expanded=False):
        st.markdown("""
        실시간 정확한 사용량은 각 서비스 대시보드에서 확인:
        - [OpenAI Usage](https://platform.openai.com/usage)
        - [Perplexity API](https://www.perplexity.ai/settings/api)

        **자동 작업 추정 비용 (현재 설정 기준)**
        """)
        cost_data = [
            ("🗞️ 데일리 신문 (Perplexity)", "매일 1회", "$0.05", "$1.5"),
            ("🎤 유튜버 알림 (gpt-4o)", "이틀 1회", "$0.07", "$1.0"),
            ("🔔 가격 알림 체크", "30분", "$0", "$0"),
            ("🤖 AI 평가서 (수동)", "필요 시", "$0.10", "변동"),
            ("💬 RAG 챗봇 (수동)", "질문당", "$0.03", "변동"),
        ]
        import pandas as pd
        df_cost = pd.DataFrame(cost_data, columns=["작업", "주기", "1회 비용", "월 예상"])
        st.dataframe(df_cost, hide_index=True, use_container_width=True)
        st.caption("**자동 작업만 합산: 월 약 $2.5** (사용자 수동 작업은 추가)")

    # ──────────────── 3. 영상 수집 ────────────────
    with st.expander("🎥 YouTube 영상 수집 → Pinecone 인덱싱", expanded=False):
        from utils.sheet_loader import SheetDataLoader

        if "pipeline_status" not in st.session_state:
            try:
                with st.spinner("수집 현황 조회 중..."):
                    loader = SheetDataLoader()
                    st.session_state.pipeline_status = loader.get_last_data_info()
            except Exception as e:
                st.session_state.pipeline_status = {"youtube_date": "N/A", "market_date": "N/A"}
                print(f"Status loading error: {e}")

        status = st.session_state.pipeline_status
        sc1, sc2 = st.columns(2)
        sc1.metric("🎥 최신 영상", status["youtube_date"])
        sc2.metric("📈 시장 지표", status["market_date"])
        st.caption("YouTube → Pinecone 자동화 (Google Sheets 기준)")

        dc1, dc2 = st.columns(2)
        today = datetime.date.today()
        with dc1:
            start_date = st.date_input("시작일", value=today, key="admin_yt_start")
        with dc2:
            end_date = st.date_input("종료일", value=today, key="admin_yt_end")

        if st.button("🎬 영상 수집 실행", icon=":material/movie:", use_container_width=True):
            progress_container = st.empty()
            status_container = st.empty()
            with st.spinner("파이프라인 실행 중..."):
                try:
                    from core.services.data_pipeline import DataPipeline
                    channels = os.getenv("TARGET_CHANNEL_ID_LIST", "").split(",")
                    channel = channels[0].strip() if channels else ""
                    pipeline = DataPipeline()
                    result = pipeline.run_youtube_pipeline(
                        channel_id=channel,
                        start_date_str=start_date.strftime("%Y-%m-%d"),
                        end_date_str=end_date.strftime("%Y-%m-%d"),
                        progress_callback=lambda r, m: progress_container.progress(r, text=m),
                        status_callback=lambda m: status_container.info(m),
                    )
                    st.success(f"✅ 수집 완료: {result.get('success_count', 0)}개")
                    try:
                        loader = SheetDataLoader()
                        st.session_state.pipeline_status = loader.get_last_data_info()
                        st.rerun()
                    except Exception:
                        pass
                except Exception as e:
                    st.error(f"오류: {e}")

    # ──────────────── 4. 공용 데이터 편집 ────────────────
    with st.expander("📅 공용 데이터 편집 — 커스텀 일정 / 시점 키워드", expanded=False):
        st.markdown("**📅 커스텀 일정 (모든 사용자에게 보임)**")
        from modules.event_calendar import load_custom_events, add_custom_event, remove_custom_event
        with st.form("admin_add_event", clear_on_submit=True):
            ec1, ec2, ec3 = st.columns([2, 4, 1])
            with ec1:
                ev_date = st.date_input("날짜", value=datetime.date.today(), key="admin_ev_date")
            with ec2:
                ev_title = st.text_input("내용", placeholder="예: 한미 정상회담, 휴장 등")
            with ec3:
                st.write("")
                if st.form_submit_button("➕ 추가", use_container_width=True):
                    if ev_title.strip():
                        add_custom_event(ev_date.strftime("%Y-%m-%d"), ev_title.strip())
                        st.rerun()

        customs = load_custom_events()
        if customs:
            for i, ev in enumerate(customs):
                ec1, ec2 = st.columns([5, 1])
                ec1.markdown(f"<span style='font-size:0.9rem;'>{ev['date']} — {ev['title']}</span>",
                             unsafe_allow_html=True)
                if ec2.button("🗑️", key=f"admin_del_ev_{i}"):
                    remove_custom_event(i)
                    st.rerun()
        else:
            st.caption("등록된 커스텀 일정 없음")

        st.markdown("---")
        st.markdown("**🔑 시점 키워드 (유튜버 알림 필터링용 — 읽기 전용)**")
        from modules.video_timing import _TIME_KEYWORDS
        st.code(", ".join(_TIME_KEYWORDS[:15]) + f"\n...(총 {len(_TIME_KEYWORDS)}개)",
                language="text")
        st.caption("수정하려면 `modules/video_timing.py`의 `_TIME_KEYWORDS` 리스트를 직접 편집하세요.")

    # ──────────────── 5. 강제 작업 ────────────────
    with st.expander("⚙️ 강제 작업 — 캐시 무시 재실행", expanded=False):
        st.warning("⚠️ 캐시를 무시하고 즉시 실행합니다. LLM 비용이 발생합니다.")

        ac1, ac2 = st.columns(2)
        with ac1:
            if st.button("🗞️ 데일리 신문 강제 재발행", use_container_width=True):
                from modules.daily_paper import _save_paper_store
                _save_paper_store({})
                st.success("✅ 신문 캐시 삭제. 데일리 탭에서 발행하세요.")

        with ac2:
            if st.button("🎤 유튜버 알림 강제 갱신", use_container_width=True):
                from modules.video_timing import refresh_alerts
                with st.spinner("영상 분석 중... (15~30초)"):
                    try:
                        result = refresh_alerts(days=90)
                        st.success(f"✅ 갱신 완료: 영상 {result['video_count']}개 → 알림 {result['alert_count']}개")
                    except Exception as e:
                        st.error(f"❌ {e}")

        st.markdown("---")
        st.markdown("**🧹 캐시 삭제 (모든 사용자)**")
        cd1, cd2, cd3 = st.columns(3)
        with cd1:
            if st.button("AI 평가서 캐시", use_container_width=True):
                base = Path(__file__).resolve().parents[2] / "data" / "users"
                removed = 0
                if base.exists():
                    for f in base.glob("*/portfolio_eval.json"):
                        f.unlink()
                        removed += 1
                st.success(f"✅ {removed}명 평가서 캐시 삭제")
        with cd2:
            if st.button("매크로 지표 캐시", use_container_width=True):
                st.cache_data.clear()
                st.success("✅ Streamlit 캐시 전체 삭제")
        with cd3:
            if st.button("시그널 캐시", use_container_width=True):
                st.cache_data.clear()
                st.success("✅ Streamlit 캐시 전체 삭제 (시그널 포함)")
