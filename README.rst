===============================
Cryptolio
===============================

Cryptolio is a cryptocurrency portfolio rebalancing tool based on the strategy described in the Crypto20 whitepaper_.
Performances can be seen in real time in Crypto20 portal_.

Crypto20 backtestings showed optimal results with the following parameters:

- 20 crypto currencies with the top market capitalisation
- 10% max capping level
- Weekly rebalancing interval

For those who missed the Crypto20 ICO or want to keep control of their cryptos, this tool can perform portfolio rebalancing automatically in less than one minute! The only thing to do is to run it once a week!

.. _whitepaper: https://cdn.crypto20.com/pdf/c20-whitepaper.pdf
.. _portal: https://crypto20.com/en/portal/performance/

Features
--------

- Supported platforms: all platforms supported by the cctx_ library (tested Bittrex and Binance so far)
- Cold wallet support: indicate the amount of cryptos to keep on the cold wallet
- Rebalancing among multiple platforms at the same time
- Automatically find the top cryptos by market capitalisation
- Include or exclude specific cryptos from the portfolio
- Automatic or manual weighting of each crypto
- Place real orders to do the rebalancing
- Backtesting and charts to find optimal parameters

.. _cctx: https://github.com/ccxt/ccxt


Algorithm
---------

- Get the top cryptos ranked by market capitalisation to include in the ideal portfolio (using coinmarketcap library)
- Compute the total available capital (cold wallet + online platforms cryptos) value in Bitcoin (using ccxt library)
- Compute the weighings (capped and proportionnal to market capitalisation) and quantity of each crypto in the ideal portfolio
- Subtract the cold wallet crypto balances to get the ideal global online portfolio
- Split the ideal global online portfolio to get the specific ideal portfolio for each platform (sometime a crypto in not supported on a platform)
- Compute the delta between the current portfolio and the target portfolio for each platform
- Execute sell orders, then buy orders (using ccxt library)
- Compute the amount of cryptos to send to the cold wallet to keep a good ratio between online and cold wallets

Backtest results
----------------

Backtest output example is in `backtest.log`_.

.. _backtest.log: https://raw.githubusercontent.com/frossigneux/cryptolio/master/output_examples/backtest.log

Backtest profit chart example:

.. image:: https://raw.githubusercontent.com/frossigneux/cryptolio/master/output_examples/profit.png

Backtest winners chart example:

.. image:: https://raw.githubusercontent.com/frossigneux/cryptolio/master/output_examples/winners.png

At the end of the log file there is a summary:

::

  Final capital:
  3189.29 $ with capping_level=0.25 and number_of_cryptos=100
  3158.87 $ with capping_level=0.25 and number_of_cryptos=20
  3133.63 $ with capping_level=0.25 and number_of_cryptos=50
  2933.89 $ with capping_level=0.1 and number_of_cryptos=20
  2917.50 $ with capping_level=0.15 and number_of_cryptos=20
  2829.19 $ with capping_level=0.15 and number_of_cryptos=100
  2804.95 $ with capping_level=0.15 and number_of_cryptos=50
  2691.88 $ with capping_level=0.1 and number_of_cryptos=50
  2686.20 $ with capping_level=0.1 and number_of_cryptos=100
  2579.58 $ with capping_level=0.05 and number_of_cryptos=100
  2550.81 $ with capping_level=0.05 and number_of_cryptos=50
  2512.75 $ with capping_level=0.05 and number_of_cryptos=20

  The parameters with maximum number of wins are capping_level=0.25 and number_of_cryptos=100



Rebalancing output
------------------

For privacy reasons, the capital in example outputs is totally fictive.

Rebalancing output example is in `rebalancing.log`_.

.. _rebalancing.log: https://raw.githubusercontent.com/frossigneux/cryptolio/master/output_examples/rebalancing.log

The results slightly differs from Crypto20 whitepaper results are they are ran only on 2017 year and include newer data.
Crypto20 params are a safe choice though.

Installation
------------

Clone the git repository:

::

  git clone https://github.com/frossigneux/cryptolio.git

Install the package:

::

  cd cryptolio
  pip install .

Set parameters in the configuration file and equitably distribute your funds among the platforms.

Now you can run cryptolio-rebalancing by typing:

::

  cryptolio-rebalancing settings.cfg

And doing backtests by typing:

::

  cryptolio-backtest settings.cfg

The directory *backtest_cache* contains cached data from coinmarketcap (top 1000 cryptos) from 1th January 2019 to 12th February 2023.
New data will be downloaded and inserted into the cache if cached data are not available.

Settings
--------

All settings should be set in the `settings.cfg`_ file.

.. _settings.cfg: https://raw.githubusercontent.com/frossigneux/cryptolio/master/settings.cfg


Default section
^^^^^^^^^^^^^^^

======================  ============================================================================
Parameter               Description
======================  ============================================================================
*platform*\ _api_key    *Platform* api key with read and trading rights (replace platform by binance, bittrex...)
*platform*\ _secret     *Platform* secret
ask_confirmation        Ask confirmation before doing the balancing
capping_level           Maximum capping level per crypto (default 10%)
cold_wallet_ratio     Ratio of cryptos that should be kept on the cold wallet (default 80%)
number_of_cryptos       Number of cryptos included in the portfolio (default 20)
trading_slippage        Slippage used to sell or buy (default 3%)
======================  ============================================================================

Note: multiple platforms can be used at the same time.

Manual weightings section
^^^^^^^^^^^^^^^^^^^^^^^^^

This section allows to set manual weighings for some cryptos.

Allowed values are:

==========================  ============================================================================
Parameter                   Description
==========================  ============================================================================
0                           Exclude the crypto from the portfolio (this crypto will be sold)
0.15 (for example)          Specific weighting (a float between 0 and 1) bypassing the capping_level parameter
auto                        Force the inclusion of a crypto (weighting will be computed automatically)
==========================  ============================================================================

Cold wallet section
^^^^^^^^^^^^^^^^^^^

This section allows to set the amount of each crypto actually stored in the cold wallet.
The amount can be set to 0 to indicate that the crypto is supported by the cold wallet.
All tokens supported by MyEtherWallet are automatically considered as supported.

Backtest section
^^^^^^^^^^^^^^^^

======================  ============================================================================
Parameter               Description
======================  ============================================================================
start_date              Backtest start date (default 2019-01-01)
end_date                Backtest end date (default now)
week_interval           Number of weeks between two rebalancings
initial_capital         Initial capital for starting the backtest (default 1000 $)
capping_level           List of capping levels (comma-separated float values)
number_of_cryptos       List of number of cryptos included in the portfolio (comma-separated integer values)
fees                    Trading platform fees (default 0.25%)
draw_charts             Show charts (default true)
log_scale               Use log scale (default true)
cache_dir               Cache dir to speed up the backtests (default backtest_cache)
======================  ============================================================================

Backtest manual weightings section
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This section allows to set manual weighings for some cryptos for the backtests.

Contributing
------------

Feel free to send me your ideas and bug reports!