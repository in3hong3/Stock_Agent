"""
포트폴리오 시각화 모듈
Plotly를 사용한 인터랙티브 차트 생성
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PortfolioVisualizer:
    """포트폴리오 시각화 클래스"""
    
    def __init__(self):
        """초기화"""
        self.color_scheme = {
            'positive': '#00C853',  # 녹색 (수익)
            'negative': '#FF1744',  # 빨간색 (손실)
            'neutral': '#2196F3',   # 파란색 (중립)
            'background': '#1E1E1E',  # 다크 배경
            'text': '#FFFFFF'  # 흰색 텍스트
        }
    
    def create_sector_pie_chart(self, portfolio_df: pd.DataFrame, 
                                sector_summary: Dict) -> go.Figure:
        """
        섹터별 비중 파이 차트
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            sector_summary: 섹터별 요약 정보
            
        Returns:
            go.Figure: Plotly 파이 차트
        """
        try:
            # 데이터 준비
            sectors = list(sector_summary['sector_weights'].keys())
            weights = list(sector_summary['sector_weights'].values())
            values = list(sector_summary['sector_values'].values())
            
            # 파이 차트 생성
            fig = go.Figure(data=[go.Pie(
                labels=sectors,
                values=weights,
                hole=0.4,  # 도넛 차트
                textinfo='label+percent',
                textposition='auto',
                hovertemplate='<b>%{label}</b><br>' +
                             '비중: %{percent}<br>' +
                             '평가금액: $%{customdata:,.0f}<extra></extra>',
                customdata=values,
                marker=dict(
                    line=dict(color='#FFFFFF', width=2)
                )
            )])
            
            fig.update_layout(
                title={
                    'text': '섹터별 포트폴리오 비중',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 20, 'color': self.color_scheme['text']}
                },
                showlegend=True,
                height=500,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=self.color_scheme['text'])
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"섹터 파이 차트 생성 오류: {str(e)}")
            return go.Figure()
    
    def create_profit_bar_chart(self, portfolio_df: pd.DataFrame) -> go.Figure:
        """
        종목별 수익률 막대 차트
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            
        Returns:
            go.Figure: Plotly 막대 차트
        """
        try:
            # 수익률 순으로 정렬
            df_sorted = portfolio_df.sort_values('profit_rate', ascending=True)
            
            # 색상 결정 (수익/손실)
            colors = [
                self.color_scheme['positive'] if rate > 0 else self.color_scheme['negative']
                for rate in df_sorted['profit_rate']
            ]
            
            # 막대 차트 생성
            fig = go.Figure(data=[go.Bar(
                x=df_sorted['profit_rate'],
                y=df_sorted['name'],
                orientation='h',
                marker=dict(color=colors),
                text=df_sorted['profit_rate'].apply(lambda x: f'{x:+.1f}%'),
                textposition='outside',
                hovertemplate='<b>%{y}</b><br>' +
                             '수익률: %{x:+.2f}%<br>' +
                             '<extra></extra>'
            )])
            
            fig.update_layout(
                title={
                    'text': '종목별 수익률',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 20, 'color': self.color_scheme['text']}
                },
                xaxis_title='수익률 (%)',
                yaxis_title='',
                height=max(400, len(df_sorted) * 30),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=self.color_scheme['text']),
                xaxis=dict(
                    gridcolor='rgba(255,255,255,0.1)',
                    zeroline=True,
                    zerolinecolor='rgba(255,255,255,0.3)',
                    zerolinewidth=2
                ),
                yaxis=dict(gridcolor='rgba(255,255,255,0.1)')
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"수익률 막대 차트 생성 오류: {str(e)}")
            return go.Figure()
    
    def create_treemap(self, portfolio_df: pd.DataFrame) -> go.Figure:
        """
        포트폴리오 트리맵 (평가금액 기준)
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임 (섹터 정보 포함)
            
        Returns:
            go.Figure: Plotly 트리맵
        """
        try:
            # 섹터 정보가 없으면 추가
            if 'sector' not in portfolio_df.columns:
                portfolio_df['sector'] = 'Unknown'
            
            # 트리맵 데이터 준비
            df = portfolio_df.copy()
            df['label'] = df['name'] + '<br>' + df['profit_rate'].apply(lambda x: f'{x:+.1f}%')
            
            # 색상 스케일 (수익률 기준)
            fig = go.Figure(go.Treemap(
                labels=df['label'],
                parents=df['sector'],
                values=df['eval_amount'],
                marker=dict(
                    colorscale=[
                        [0, self.color_scheme['negative']],
                        [0.5, '#FFEB3B'],  # 노란색 (중립)
                        [1, self.color_scheme['positive']]
                    ],
                    cmid=0,
                    cmin=df['profit_rate'].min(),
                    cmax=df['profit_rate'].max(),
                    colorbar=dict(
                        title='수익률 (%)',
                        titleside='right',
                        tickmode='linear',
                        tick0=df['profit_rate'].min(),
                        dtick=(df['profit_rate'].max() - df['profit_rate'].min()) / 5
                    ),
                    line=dict(color='#FFFFFF', width=2)
                ),
                text=df['ticker'],
                hovertemplate='<b>%{text}</b><br>' +
                             '평가금액: $%{value:,.0f}<br>' +
                             '<extra></extra>',
                textposition='middle center'
            ))
            
            fig.update_layout(
                title={
                    'text': '포트폴리오 구성 (평가금액 기준)',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 20, 'color': self.color_scheme['text']}
                },
                height=600,
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=self.color_scheme['text'], size=12)
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"트리맵 생성 오류: {str(e)}")
            return go.Figure()
    
    def create_sector_performance_chart(self, portfolio_df: pd.DataFrame,
                                       sector_summary: Dict) -> go.Figure:
        """
        섹터별 성과 차트 (비중 vs 수익률)
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임
            sector_summary: 섹터별 요약 정보
            
        Returns:
            go.Figure: Plotly 산점도
        """
        try:
            # 데이터 준비
            sectors = list(sector_summary['sector_weights'].keys())
            weights = [sector_summary['sector_weights'][s] for s in sectors]
            profit_rates = [sector_summary['sector_profit_rates'][s] for s in sectors]
            counts = [sector_summary['sector_counts'][s] for s in sectors]
            
            # 색상 결정
            colors = [
                self.color_scheme['positive'] if rate > 0 else self.color_scheme['negative']
                for rate in profit_rates
            ]
            
            # 산점도 생성
            fig = go.Figure(data=[go.Scatter(
                x=weights,
                y=profit_rates,
                mode='markers+text',
                marker=dict(
                    size=[c * 20 for c in counts],  # 종목 수에 비례
                    color=colors,
                    line=dict(color='#FFFFFF', width=2)
                ),
                text=sectors,
                textposition='top center',
                hovertemplate='<b>%{text}</b><br>' +
                             '비중: %{x:.1f}%<br>' +
                             '평균 수익률: %{y:+.2f}%<br>' +
                             '<extra></extra>'
            )])
            
            fig.update_layout(
                title={
                    'text': '섹터별 성과 (비중 vs 수익률)',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 20, 'color': self.color_scheme['text']}
                },
                xaxis_title='포트폴리오 비중 (%)',
                yaxis_title='평균 수익률 (%)',
                height=500,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color=self.color_scheme['text']),
                xaxis=dict(
                    gridcolor='rgba(255,255,255,0.1)',
                    zeroline=True,
                    zerolinecolor='rgba(255,255,255,0.3)'
                ),
                yaxis=dict(
                    gridcolor='rgba(255,255,255,0.1)',
                    zeroline=True,
                    zerolinecolor='rgba(255,255,255,0.3)',
                    zerolinewidth=2
                )
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"섹터 성과 차트 생성 오류: {str(e)}")
            return go.Figure()
    
    def create_allocation_sunburst(self, portfolio_df: pd.DataFrame) -> go.Figure:
        """
        포트폴리오 할당 선버스트 차트 (섹터 → 종목)
        
        Args:
            portfolio_df: 포트폴리오 데이터프레임 (섹터 정보 포함)
            
        Returns:
            go.Figure: Plotly 선버스트 차트
        """
        try:
            if 'sector' not in portfolio_df.columns:
                portfolio_df['sector'] = 'Unknown'
            
            # 선버스트 데이터 준비
            df = portfolio_df.copy()
            
            # 루트 노드 추가
            root_data = pd.DataFrame([{
                'name': 'Portfolio',
                'parent': '',
                'value': df['eval_amount'].sum(),
                'profit_rate': (df['profit_loss'].sum() / (df['quantity'] * df['avg_price']).sum()) * 100
            }])
            
            # 섹터 노드
            sector_data = df.groupby('sector').agg({
                'eval_amount': 'sum',
                'profit_rate': 'mean'
            }).reset_index()
            sector_data['parent'] = 'Portfolio'
            sector_data = sector_data.rename(columns={'sector': 'name', 'eval_amount': 'value'})
            
            # 종목 노드
            stock_data = df[['name', 'sector', 'eval_amount', 'profit_rate']].copy()
            stock_data = stock_data.rename(columns={'sector': 'parent', 'eval_amount': 'value'})
            
            # 통합
            sunburst_df = pd.concat([root_data, sector_data, stock_data], ignore_index=True)
            
            # 선버스트 차트 생성
            fig = go.Figure(go.Sunburst(
                labels=sunburst_df['name'],
                parents=sunburst_df['parent'],
                values=sunburst_df['value'],
                marker=dict(
                    colorscale=[
                        [0, self.color_scheme['negative']],
                        [0.5, '#FFEB3B'],
                        [1, self.color_scheme['positive']]
                    ],
                    cmid=0,
                    line=dict(color='#FFFFFF', width=2)
                ),
                hovertemplate='<b>%{label}</b><br>' +
                             '평가금액: $%{value:,.0f}<br>' +
                             '<extra></extra>',
                branchvalues='total'
            ))
            
            fig.update_layout(
                title={
                    'text': '포트폴리오 할당 구조',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 20, 'color': self.color_scheme['text']}
                },
                height=600,
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=self.color_scheme['text'])
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"선버스트 차트 생성 오류: {str(e)}")
            return go.Figure()


# 사용 예시
if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from utils.sector_classifier import SectorClassifier
    
    logging.basicConfig(level=logging.INFO)
    
    # 포트폴리오 로드
    portfolio_path = "data/portfolio.csv"
    
    if not os.path.exists(portfolio_path):
        print(f"❌ 파일을 찾을 수 없습니다: {portfolio_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("포트폴리오 시각화 테스트")
    print("=" * 60)
    
    # 데이터 로드 및 전처리
    df = pd.read_csv(portfolio_path)
    df['eval_amount'] = df['quantity'] * df['current_price']
    df['profit_loss'] = df['eval_amount'] - (df['quantity'] * df['avg_price'])
    df['profit_rate'] = (df['profit_loss'] / (df['quantity'] * df['avg_price'])) * 100
    
    # 섹터 분류
    classifier = SectorClassifier()
    df = classifier.classify_portfolio(df, delay_seconds=0.3)
    sector_summary = classifier.get_sector_summary(df)
    
    # 시각화
    visualizer = PortfolioVisualizer()
    
    print("\n📊 차트 생성 중...")
    
    # 1. 섹터 파이 차트
    fig1 = visualizer.create_sector_pie_chart(df, sector_summary)
    fig1.write_html("portfolio_sector_pie.html")
    print("✅ 섹터 파이 차트: portfolio_sector_pie.html")
    
    # 2. 수익률 막대 차트
    fig2 = visualizer.create_profit_bar_chart(df)
    fig2.write_html("portfolio_profit_bar.html")
    print("✅ 수익률 막대 차트: portfolio_profit_bar.html")
    
    # 3. 트리맵
    fig3 = visualizer.create_treemap(df)
    fig3.write_html("portfolio_treemap.html")
    print("✅ 트리맵: portfolio_treemap.html")
    
    # 4. 섹터 성과 차트
    fig4 = visualizer.create_sector_performance_chart(df, sector_summary)
    fig4.write_html("portfolio_sector_performance.html")
    print("✅ 섹터 성과 차트: portfolio_sector_performance.html")
    
    # 5. 선버스트 차트
    fig5 = visualizer.create_allocation_sunburst(df)
    fig5.write_html("portfolio_sunburst.html")
    print("✅ 선버스트 차트: portfolio_sunburst.html")
    
    print("\n✅ 모든 차트 생성 완료!")
