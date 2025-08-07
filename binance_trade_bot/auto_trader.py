from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from .binance_api_manager import BinanceAPIManager
from .config import Config
from .database import Database
from .logger import Logger
from .models import Coin, CoinValue, Pair
from .technical_analysis import WmaEngine


class AutoTrader:
    def __init__(
        self,
        binance_manager: BinanceAPIManager,
        database: Database,
        logger: Logger,
        config: Config,
    ):
        self.manager = binance_manager
        self.db = database
        self.logger = logger
        self.config = config
        
        # Initialize WMA engine for technical analysis
        self.wma_engine = self._initialize_wma_engine()

    def initialize(self):
        self.initialize_trade_thresholds()
    
    def _initialize_wma_engine(self) -> Optional[WmaEngine]:
        """
        Initialize the WMA engine with configuration settings.
        
        @description Create and configure WMA engine for technical analysis
        @returns {WmaEngine|null} Initialized WMA engine or None if configuration fails
        """
        try:
            wma_config = {
                'wma_short_period': self.config.get('wma_short_period', 7),
                'wma_long_period': self.config.get('wma_long_period', 21),
                'price_column': 'close'
            }
            
            # Validate WMA configuration
            if wma_config['wma_short_period'] <= 0 or wma_config['wma_long_period'] <= 0:
                self.logger.warning("Invalid WMA configuration detected, using defaults")
                wma_config = {'wma_short_period': 7, 'wma_long_period': 21, 'price_column': 'close'}
            
            if wma_config['wma_short_period'] >= wma_config['wma_long_period']:
                self.logger.warning("WMA short period must be less than long period, using defaults")
                wma_config = {'wma_short_period': 7, 'wma_long_period': 21, 'price_column': 'close'}
            
            return WmaEngine(wma_config)
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WMA engine: {e}")
            return None
    
    def _get_historical_data(self, symbol: str, periods: int = 50) -> Optional[pd.DataFrame]:
        """
        Get historical price data for WMA analysis.
        
        @description Fetch historical market data for technical analysis
        @param {str} symbol - Trading symbol (e.g., 'BTCUSDT')
        @param {int} periods - Number of periods to fetch
        @returns {DataFrame|null} Historical data or None if fetch fails
        """
        try:
            # Get klines/candlestick data
            klines = self.manager.get_klines(symbol, limit=periods)
            
            if not klines or len(klines) < periods:
                self.logger.warning(f"Insufficient historical data for {symbol}")
                return None
            
            # Convert to DataFrame
            df_data = {
                'open': [float(k[1]) for k in klines],
                'high': [float(k[2]) for k in klines],
                'low': [float(k[3]) for k in klines],
                'close': [float(k[4]) for k in klines],
                'volume': [float(k[5]) for k in klines]
            }
            
            return pd.DataFrame(df_data)
            
        except Exception as e:
            self.logger.error(f"Failed to get historical data for {symbol}: {e}")
            return None
    
    def _calculate_wma_signal_score(self, pair: Pair, coin_price: float) -> float:
        """
        Calculate WMA-based signal score for trade opportunity.
        
        @description Analyze WMA indicators and generate trade opportunity score
        @param {Pair} pair - Trading pair
        @param {float} coin_price - Current coin price
        @returns {float} Signal score between -1.0 (bearish) and 1.0 (bullish)
        """
        if not self.wma_engine:
            return 0.0
        
        try:
            # Get historical data for the pair
            symbol = pair.to_coin + self.config.BRIDGE
            historical_data = self._get_historical_data(symbol, self.wma_engine.long_period + 10)
            
            if historical_data is None or len(historical_data) < self.wma_engine.long_period:
                self.logger.warning(f"Insufficient data for WMA analysis on {symbol}")
                return 0.0
            
            # Perform WMA analysis
            trend_analysis = self.wma_engine.detect_trend(historical_data)
            
            if trend_analysis['trend'] == 'insufficient_data':
                return 0.0
            
            # Calculate signal score based on trend strength and direction
            signal_score = 0.0
            
            if trend_analysis['trend'] == 'bullish':
                # Positive score for bullish trend
                signal_score = trend_analysis['trend_strength']
                
                # Bonus for golden cross
                if trend_analysis['crossover_signal'] == 'golden_cross':
                    signal_score += 0.3
                    
            elif trend_analysis['trend'] == 'bearish':
                # Negative score for bearish trend
                signal_score = -trend_analysis['trend_strength']
                
                # Penalty for death cross
                if trend_analysis['crossover_signal'] == 'death_cross':
                    signal_score -= 0.3
            
            # Ensure score is within valid range
            return max(-1.0, min(1.0, signal_score))
            
        except Exception as e:
            self.logger.error(f"Failed to calculate WMA signal score for {pair.to_coin}: {e}")
            return 0.0

    def transaction_through_bridge(self, pair: Pair):
        """
        Jump from the source coin to the destination coin through bridge coin
        """
        can_sell = False
        balance = self.manager.get_currency_balance(pair.from_coin.symbol)
        from_coin_price = self.manager.get_ticker_price(pair.from_coin + self.config.BRIDGE)

        if balance and balance * from_coin_price > self.manager.get_min_notional(
            pair.from_coin.symbol, self.config.BRIDGE.symbol
        ):
            can_sell = True
        else:
            self.logger.info("Skipping sell")

        if can_sell and self.manager.sell_alt(pair.from_coin, self.config.BRIDGE) is None:
            self.logger.info("Couldn't sell, going back to scouting mode...")
            return None

        result = self.manager.buy_alt(pair.to_coin, self.config.BRIDGE)
        if result is not None:
            self.db.set_current_coin(pair.to_coin)
            self.update_trade_threshold(pair.to_coin, result.price)
            return result

        self.logger.info("Couldn't buy, going back to scouting mode...")
        return None

    def update_trade_threshold(self, coin: Coin, coin_price: float):
        """
        Update all the coins with the threshold of buying the current held coin
        """

        if coin_price is None:
            self.logger.info(f"Skipping update... current coin {coin + self.config.BRIDGE} not found")
            return

        session: Session
        with self.db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.to_coin == coin):
                from_coin_price = self.manager.get_ticker_price(pair.from_coin + self.config.BRIDGE)

                if from_coin_price is None:
                    self.logger.info(f"Skipping update for coin {pair.from_coin + self.config.BRIDGE} not found")
                    continue

                pair.ratio = from_coin_price / coin_price

    def initialize_trade_thresholds(self):
        """
        Initialize the buying threshold of all the coins for trading between them
        """
        session: Session
        with self.db.db_session() as session:
            for pair in session.query(Pair).filter(Pair.ratio.is_(None)).all():
                if not pair.from_coin.enabled or not pair.to_coin.enabled:
                    continue
                self.logger.info(f"Initializing {pair.from_coin} vs {pair.to_coin}")

                from_coin_price = self.manager.get_ticker_price(pair.from_coin + self.config.BRIDGE)
                if from_coin_price is None:
                    self.logger.info(f"Skipping initializing {pair.from_coin + self.config.BRIDGE}, symbol not found")
                    continue

                to_coin_price = self.manager.get_ticker_price(pair.to_coin + self.config.BRIDGE)
                if to_coin_price is None:
                    self.logger.info(f"Skipping initializing {pair.to_coin + self.config.BRIDGE}, symbol not found")
                    continue

                pair.ratio = from_coin_price / to_coin_price

    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        raise NotImplementedError()

    def _get_ratios(self, coin: Coin, coin_price):
        """
        Given a coin, get the current price ratio for every other enabled coin
        incorporating WMA trend signals for enhanced trading decisions.
        """
        ratio_dict: Dict[Pair, float] = {}

        for pair in self.db.get_pairs_from(coin):
            optional_coin_price = self.manager.get_ticker_price(pair.to_coin + self.config.BRIDGE)

            if optional_coin_price is None:
                self.logger.info(f"Skipping scouting... optional coin {pair.to_coin + self.config.BRIDGE} not found")
                continue

            self.db.log_scout(pair, pair.ratio, coin_price, optional_coin_price)

            # Obtain (current coin)/(optional coin)
            coin_opt_coin_ratio = coin_price / optional_coin_price

            # Fees
            from_fee = self.manager.get_fee(pair.from_coin, self.config.BRIDGE, True)
            to_fee = self.manager.get_fee(pair.to_coin, self.config.BRIDGE, False)
            transaction_fee = from_fee + to_fee - from_fee * to_fee

            # Calculate base ratio using existing logic
            if self.config.USE_MARGIN == "yes":
                base_ratio = (
                    (1 - transaction_fee) * coin_opt_coin_ratio / pair.ratio - 1 - self.config.SCOUT_MARGIN / 100
                )
            else:
                base_ratio = (
                    coin_opt_coin_ratio - transaction_fee * self.config.SCOUT_MULTIPLIER * coin_opt_coin_ratio
                ) - pair.ratio

            # Apply WMA-based signal enhancement if WMA engine is available
            enhanced_ratio = self._apply_wma_signal_enhancement(pair, base_ratio)

            ratio_dict[pair] = enhanced_ratio
        return ratio_dict
    
    def _apply_wma_signal_enhancement(self, pair: Pair, base_ratio: float) -> float:
        """
        Apply WMA signal enhancement to trading ratio calculation.
        
        @description Enhance base ratio with WMA trend signals for better trading decisions
        @param {Pair} pair - Trading pair being analyzed
        @param {float} base_ratio - Base calculated ratio
        @returns {float} Enhanced ratio incorporating WMA signals
        """
        # Fallback to base ratio if WMA engine is not available
        if not self.wma_engine:
            self.logger.debug("WMA engine not available, using base ratio")
            return base_ratio
        
        try:
            # Calculate WMA signal score
            wma_signal_score = self._calculate_wma_signal_score(pair, base_ratio)
            
            # Apply signal enhancement with configurable weight
            wma_weight = self.config.get('wma_signal_weight', 0.3)  # Default 30% weight
            enhanced_ratio = base_ratio * (1 + wma_signal_score * wma_weight)
            
            # Log the enhancement for debugging
            if abs(wma_signal_score) > 0.1:  # Log significant signals
                self.logger.info(
                    f"WMA enhancement for {pair.from_coin}->{pair.to_coin}: "
                    f"base_ratio={base_ratio:.4f}, wma_score={wma_signal_score:.3f}, "
                    f"enhanced_ratio={enhanced_ratio:.4f}"
                )
            
            return enhanced_ratio
            
        except Exception as e:
            self.logger.error(f"Failed to apply WMA enhancement for {pair}: {e}")
            # Fallback to base ratio on error
            return base_ratio

    def _jump_to_best_coin(self, coin: Coin, coin_price: float):
        """
        Given a coin, search for a coin to jump to
        """
        ratio_dict = self._get_ratios(coin, coin_price)

        # keep only ratios bigger than zero
        ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}

        # if we have any viable options, pick the one with the biggest ratio
        if ratio_dict:
            best_pair = max(ratio_dict, key=ratio_dict.get)
            self.logger.info(f"Will be jumping from {coin} to {best_pair.to_coin_id}")
            self.transaction_through_bridge(best_pair)

    def bridge_scout(self):
        """
        If we have any bridge coin leftover, buy a coin with it that we won't immediately trade out of
        """
        bridge_balance = self.manager.get_currency_balance(self.config.BRIDGE.symbol)

        for coin in self.db.get_coins():
            current_coin_price = self.manager.get_ticker_price(coin + self.config.BRIDGE)

            if current_coin_price is None:
                continue

            ratio_dict = self._get_ratios(coin, current_coin_price)
            if not any(v > 0 for v in ratio_dict.values()):
                # There will only be one coin where all the ratios are negative. When we find it, buy it if we can
                if bridge_balance > self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol):
                    self.logger.info(f"Will be purchasing {coin} using bridge coin")
                    self.manager.buy_alt(coin, self.config.BRIDGE)
                    return coin
        return None

    def update_values(self):
        """
        Log current value state of all altcoin balances against BTC and USDT in DB.
        """
        now = datetime.now()

        session: Session
        with self.db.db_session() as session:
            coins: List[Coin] = session.query(Coin).all()
            for coin in coins:
                balance = self.manager.get_currency_balance(coin.symbol)
                if balance == 0:
                    continue
                usd_value = self.manager.get_ticker_price(coin + "USDT")
                btc_value = self.manager.get_ticker_price(coin + "BTC")
                cv = CoinValue(coin, balance, usd_value, btc_value, datetime=now)
                session.add(cv)
                self.db.send_update(cv)
