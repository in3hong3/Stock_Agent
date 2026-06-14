"""
로딩 UI 컴포넌트
무거운 작업(평가서 생성, 신문 발행 등) 중 사용자에게
"진행 중이다 / 어디까지 왔다" 시각적 피드백을 제공한다.
"""
import time
import streamlit as st

# CSS 한 번만 주입 (펄스 애니메이션 + 아이콘 회전)
_CSS_INJECTED = "_loading_css_injected"
_CSS = """
<style>
@keyframes progress-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
@keyframes progress-shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
@keyframes progress-spin {
  to { transform: rotate(360deg); }
}
.progress-banner {
  background: linear-gradient(135deg, #1A2340 0%, #16181F 100%);
  border: 1px solid rgba(0, 255, 163, 0.35);
  border-radius: 14px;
  padding: 18px 22px;
  margin: 12px 0;
  box-shadow: 0 4px 20px rgba(0, 255, 163, 0.08);
  animation: progress-pulse 2s ease-in-out infinite;
}
.progress-banner .banner-title {
  font-weight: 700;
  font-size: 1.0rem;
  color: #FFFFFF;
  margin-bottom: 4px;
}
.progress-banner .banner-step {
  color: #94A3B8;
  font-size: 0.85rem;
}
.progress-banner .icon-spin {
  display: inline-block;
  font-size: 22px;
  margin-right: 12px;
  animation: progress-spin 1.2s linear infinite;
}
.progress-track {
  margin-top: 12px;
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 4px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #00FFA3, #00D9F5, #00FFA3);
  background-size: 200% 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
  animation: progress-shimmer 1.5s linear infinite;
}
.progress-banner.success {
  border-color: rgba(0, 255, 163, 0.6);
  animation: none;
}
.progress-banner.error {
  border-color: rgba(255, 75, 75, 0.6);
  animation: none;
}
</style>
"""


def _inject_css():
    if not st.session_state.get(_CSS_INJECTED):
        st.markdown(_CSS, unsafe_allow_html=True)
        st.session_state[_CSS_INJECTED] = True


class ProgressBanner:
    """
    단계별 진행 배너. with 구문으로 사용:

    with ProgressBanner("AI 평가서 생성 중", total=3, icon="🤖") as banner:
        banner.step("뉴스 검색 중...")
        ... 작업 1
        banner.step("밸류에이션 수집 중...")
        ... 작업 2
        banner.step("AI가 평가서 작성 중...")
        ... 작업 3
        banner.done("✅ 평가서 생성 완료!")
    """

    def __init__(self, title: str, total: int = 1, icon: str = "⚙️"):
        self.title = title
        self.total = total
        self.icon = icon
        self.current = 0
        self.placeholder = None

    def __enter__(self):
        _inject_css()
        self.placeholder = st.empty()
        self._render(message="시작하는 중...", state="running")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._render(message=str(exc_val)[:80], state="error")
            time.sleep(1.5)
        self.placeholder.empty()
        return False  # 예외는 그대로 던짐

    def step(self, message: str):
        """다음 단계로 진행"""
        self.current = min(self.current + 1, self.total)
        self._render(message=message, state="running")

    def done(self, message: str = "완료!"):
        """성공 종료 — 짧게 표시 후 사라짐"""
        self.current = self.total
        self._render(message=message, state="success")
        time.sleep(0.8)

    def fail(self, message: str = "실패"):
        """실패 표시"""
        self._render(message=message, state="error")
        time.sleep(1.2)

    def _render(self, message: str, state: str = "running"):
        if state == "success":
            cls, icon, border = "progress-banner success", "✅", ""
        elif state == "error":
            cls, icon, border = "progress-banner error", "❌", ""
        else:
            cls, icon = "progress-banner", f"<span class='icon-spin'>{self.icon}</span>"
            border = ""

        pct = int(self.current / self.total * 100) if self.total else 0
        step_label = f"[{self.current}/{self.total}] " if self.total > 1 else ""

        self.placeholder.markdown(f"""
        <div class="{cls}">
            <div style="display:flex; align-items:center;">
                <div style="font-size:22px; margin-right:12px;">{icon}</div>
                <div style="flex:1;">
                    <div class="banner-title">{self.title}</div>
                    <div class="banner-step">{step_label}{message}</div>
                </div>
            </div>
            <div class="progress-track">
                <div class="progress-fill" style="width: {pct}%;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
