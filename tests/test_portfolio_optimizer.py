
import unittest
import sys
import os
import pandas as pd
import numpy as np

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.portfolio_optimizer import PortfolioOptimizer

class TestPortfolioOptimizer(unittest.TestCase):
    def setUp(self):
        self.optimizer = PortfolioOptimizer()
        # Mocking data for testing without yfinance calls if possible,
        # but for integration test we might want to check fetch too.
        # For now let's just test math with dummy data.
        
        dates = pd.date_range(start='2024-01-01', periods=100)
        self.dummy_prices = pd.DataFrame({
            'A': np.random.normal(100, 1, 100).cumsum(),
            'B': np.random.normal(100, 2, 100).cumsum()
        }, index=dates)

    def test_calculate_metrics(self):
        expected_returns, cov_matrix = self.optimizer.calculate_metrics(self.dummy_prices)
        self.assertEqual(len(expected_returns), 2)
        self.assertEqual(cov_matrix.shape, (2, 2))
        
    def test_optimize_portfolio(self):
        result = self.optimizer.optimize_portfolio(self.dummy_prices, objective="max_sharpe")
        self.assertTrue(result['success'])
        self.assertAlmostEqual(sum(result['weights'].values()), 1.0, places=4)
        print("\nOptimization Result:", result)

    def test_simulate_efficient_frontier(self):
        frontier = self.optimizer.simulate_efficient_frontier(self.dummy_prices, num_portfolios=10)
        self.assertEqual(len(frontier), 10)
        self.assertIn('Returns', frontier.columns)
        self.assertIn('Volatility', frontier.columns)
        self.assertIn('Sharpe', frontier.columns)
        print("\nFrontier Head:\n", frontier.head())

if __name__ == '__main__':
    unittest.main()
