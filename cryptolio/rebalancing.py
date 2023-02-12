#!/usr/bin/env python3

import configparser
import copy
import json
import sys
import time
import urllib.request

import ccxt
import click
from coinmarketcapapi import CoinMarketCapAPI


class PortfolioManager:
    def __init__(
        self,
        coinmarketcap_api_key,
        api_keys,
        manual_weightings={},
        cold_wallet={},
        cold_wallet_ratio=0.8,
        capping_level=0.1,
        number_of_cryptos=20,
        trading_slippage=0.03,
    ):
        self.coinmarketcap_api_key = coinmarketcap_api_key
        self.manual_weightings = manual_weightings
        self.cold_wallet = cold_wallet
        self.cold_wallet_ratio = cold_wallet_ratio
        self.capping_level = capping_level
        self.number_of_cryptos = number_of_cryptos
        self.trading_slippage = trading_slippage
        self.platforms = {}
        for platform in api_keys:
            class_name = getattr(ccxt, platform)
            args = {"apiKey": api_keys[platform]["api_key"], "secret": api_keys[platform]["secret"]}
            if platform == "kucoin":
                args["password"] = api_keys[platform]["password"]
            self.platforms[platform] = class_name(args)
        self.balances = {}
        self.tickers = {}
        self.markets = {}
        for platform in self.platforms:
            self.balances[platform] = self.platforms[platform].fetch_balance()
            self.tickers[platform] = self.platforms[platform].fetch_tickers()
            self.markets[platform] = self.platforms[platform].load_markets()

    def get_current_top_cryptos(self, limit=20, forced_cryptos=[], excluded_cryptos=[]):
        coinmarketcap = CoinMarketCapAPI(self.coinmarketcap_api_key, sandbox=False)
        crypto_list = coinmarketcap.cryptocurrency_listings_latest(limit=1000).data
        top_cryptos = {}
        selected_cryptos = []
        for crypto in crypto_list:
            if crypto["symbol"] in forced_cryptos:
                selected_cryptos.append(crypto)
            if len(selected_cryptos) == len(forced_cryptos):
                break
        for crypto in crypto_list:
            if crypto["symbol"] not in forced_cryptos and crypto["symbol"] not in excluded_cryptos:
                selected_cryptos.append(crypto)
            if len(selected_cryptos) >= limit:
                break
        for crypto in selected_cryptos:
            top_cryptos[crypto["symbol"]] = {
                "rank": int(crypto["cmc_rank"]),
                "name": crypto["name"],
                "symbol": crypto["symbol"],
                "marketcap": float(crypto["quote"]["USD"]["market_cap"]),
                "supply": float(crypto["circulating_supply"]),
                "percent_change_1h": float(crypto["quote"]["USD"]["percent_change_1h"]),
                "percent_change_24h": float(crypto["quote"]["USD"]["percent_change_24h"]),
                "percent_change_7d": float(crypto["quote"]["USD"]["percent_change_7d"]),
                "percent_change_30d": float(crypto["quote"]["USD"]["percent_change_30d"]),
                "percent_change_60d": float(crypto["quote"]["USD"]["percent_change_60d"]),
                "percent_change_90d": float(crypto["quote"]["USD"]["percent_change_90d"]),
            }
        for crypto, support in self.get_crypto_platform_support(list(top_cryptos.keys())).items():
            if not support:
                print(crypto, "not supported. Ban it in config file or use another platform")
                exit(-1)
        for crypto in selected_cryptos:
            top_cryptos[crypto["symbol"]]["btc_price"] = float(
                self.get_crypto_price(crypto["symbol"])
            )
        for crypto in forced_cryptos:
            if crypto not in top_cryptos:
                print(crypto, "does not exist")
                exit(-1)
        return top_cryptos

    def get_balance(self, portfolio):
        return sum(
            [portfolio[crypto]["btc_price"] * portfolio[crypto]["quantity"] for crypto in portfolio]
        )

    def get_platform_balance(self, platform):
        balances = self.balances[platform]["total"]
        tickers = self.tickers[platform]
        balance = 0
        for crypto in balances:
            if not balances[crypto]:
                continue
            if crypto + "/BTC" in tickers or crypto == "BTC":
                price = tickers[crypto + "/BTC"]["last"] if crypto != "BTC" else 1
                balance += balances[crypto] * price
            else:
                print(
                    "Ignoring",
                    balances[crypto],
                    crypto,
                    "on",
                    platform,
                    "(not available in BTC market)",
                )
        return balance

    def get_crypto_price(self, crypto, platform=None, currency="BTC"):
        platforms = [platform] if platform else list(self.platforms.keys())
        prices = []
        supported_platforms = 0
        for platform in platforms:
            if crypto == "BTC":
                prices.append(1)
                supported_platforms += 1
            elif crypto + "/BTC" in self.tickers[platform]:
                prices.append(self.tickers[platform][crypto + "/BTC"]["last"])
                supported_platforms += 1
        if currency == "USD":
            btc_prices = [
                self.tickers[platform]["BTC/USDT"]["last"]
                for platform in platforms
                if "BTC/USDT" in self.tickers[platform]
            ]
            btc_price = sum(btc_prices) / len(btc_prices)
            return sum(prices) / supported_platforms * btc_price
        elif currency == "BTC":
            return sum(prices) / supported_platforms
        else:
            raise NotImplementedError

    def get_total_market_cap(self, portfolio, cryptos=None):
        if not cryptos:
            cryptos = portfolio.keys()
        return sum([portfolio[crypto]["marketcap"] for crypto in cryptos])

    def get_uncapped_cryptos(self, portfolio):
        precision_error = 0.001
        uncapped_cryptos = []
        fixed_manual_weightings = {}
        for crypto, weighting in self.manual_weightings.items():
            if weighting not in ["auto", 0]:
                fixed_manual_weightings[crypto] = weighting
        for crypto, value in portfolio.items():
            if (
                crypto not in fixed_manual_weightings
                and value["weighting"] > self.capping_level + precision_error
            ) or (
                crypto in fixed_manual_weightings
                and abs(value["weighting"] - fixed_manual_weightings[crypto]) > precision_error
            ):
                uncapped_cryptos.append(crypto)
        return sorted(uncapped_cryptos)

    def get_ideal_portfolio(self, btc_capital):
        forced_cryptos = [crypto for crypto, quantity in self.manual_weightings.items() if quantity]
        excluded_cryptos = [
            crypto for crypto, quantity in self.manual_weightings.items() if not quantity
        ]
        portfolio = self.get_current_top_cryptos(
            self.number_of_cryptos, forced_cryptos, excluded_cryptos
        )
        total_market_cap = self.get_total_market_cap(portfolio)
        for crypto, values in portfolio.items():
            weighting = values["marketcap"] / total_market_cap
            portfolio[crypto]["weighting"] = weighting
            portfolio[crypto]["quantity"] = btc_capital * weighting / values["btc_price"]
        capped_cryptos = []
        uncapped_cryptos = True
        while uncapped_cryptos:
            uncapped_cryptos = self.get_uncapped_cryptos(portfolio)
            for crypto in uncapped_cryptos:
                old_weighting = portfolio[crypto]["weighting"]
                if crypto in self.manual_weightings and self.manual_weightings[crypto] not in [
                    "auto",
                    0,
                ]:
                    capping_level = self.manual_weightings[crypto]
                else:
                    capping_level = self.capping_level
                portfolio[crypto]["weighting"] = capping_level
                portfolio[crypto]["quantity"] *= capping_level / old_weighting
                capped_cryptos.append(crypto)
            weightings_sum_not_capped = sum(
                [portfolio[key]["weighting"] for key in portfolio if key not in capped_cryptos]
            )
            weightings_sum_capped = sum(
                [portfolio[key]["weighting"] for key in portfolio if key in capped_cryptos]
            )
            for crypto in portfolio:
                if crypto not in capped_cryptos:
                    old_weighting = portfolio[crypto]["weighting"]
                    new_weighting = (
                        old_weighting * (1 - weightings_sum_capped) / weightings_sum_not_capped
                    )
                    portfolio[crypto]["weighting"] = new_weighting
                    portfolio[crypto]["quantity"] *= new_weighting / old_weighting
        assert abs(sum([values["weighting"] for crypto, values in portfolio.items()]) - 1) < 0.01
        assert abs(self.get_balance(portfolio) / btc_capital - 1) < 0.01
        return portfolio

    def get_crypto_platform_support(self, cryptos):
        platform_support = {}
        for crypto in cryptos:
            support = []
            for platform in self.platforms:
                tickers = self.tickers[platform]
                if crypto + "/BTC" in tickers:
                    support.append(platform)
            platform_support[crypto] = support
        platform_support["BTC"] = list(self.platforms.keys())
        return platform_support

    def get_portfolio_excluding_cold_wallet(self, portfolio):
        portfolio = copy.deepcopy(portfolio)
        for crypto, balance in self.cold_wallet.items():
            if not balance:
                continue
            portfolio[crypto]["weighting"] *= (portfolio[crypto]["quantity"] - balance) / portfolio[
                crypto
            ]["quantity"]
            portfolio[crypto]["quantity"] -= balance
        total_weightings = sum([portfolio[crypto]["weighting"] for crypto in portfolio])
        for crypto in portfolio:
            portfolio[crypto]["weighting"] /= total_weightings
        assert abs(sum([portfolio[crypto]["weighting"] for crypto in portfolio]) - 1) < 0.01
        return portfolio

    def download_to_cold_wallet(self, ideal_portfolio):
        with urllib.request.urlopen(
            "https://raw.githubusercontent.com/kvhnuke/etherwallet/mercury/app/scripts/tokens/ethTokens.json"
        ) as url:
            for token in json.loads(url.read().decode()):
                if token["symbol"] not in self.cold_wallet:
                    self.cold_wallet[token["symbol"]] = 0
        for crypto in ideal_portfolio:
            if crypto not in self.cold_wallet:
                continue
            actual_ratio = self.cold_wallet[crypto] / ideal_portfolio[crypto]["quantity"]
            if actual_ratio < self.cold_wallet_ratio:
                ideal_cold_quantity = ideal_portfolio[crypto]["quantity"] * self.cold_wallet_ratio
                print(
                    "Transfer",
                    ideal_cold_quantity - self.cold_wallet[crypto],
                    crypto,
                    "to cold wallet ("
                    + str(round(actual_ratio * 100, 2))
                    + "% => "
                    + str(round(self.cold_wallet_ratio * 100, 2))
                    + "%)",
                )

    def get_ideal_portfolio_per_platform(self, portfolio, platform_balances):
        portfolios = {}
        for platform in self.platforms:
            splitted_portfolio = copy.deepcopy(portfolio)
            for crypto in splitted_portfolio:
                splitted_portfolio[crypto]["quantity"] *= platform_balances[platform] / sum(
                    platform_balances.values()
                )
            portfolios[platform] = splitted_portfolio
        platform_support = self.get_crypto_platform_support(list(portfolio.keys()))
        capped_cryptos = []
        for crypto in sorted(platform_support, key=lambda crypto: len(platform_support[crypto])):
            removed_quantity = 0
            for platform in self.platforms:
                if platform not in platform_support[crypto]:
                    removed_quantity += portfolios[platform][crypto]["quantity"]
                    del portfolios[platform][crypto]
                    if crypto not in capped_cryptos:
                        capped_cryptos.append(crypto)
            for platform in self.platforms:
                if platform in platform_support[crypto]:
                    old_quantity = portfolios[platform][crypto]["quantity"]
                    portfolios[platform][crypto]["quantity"] += removed_quantity / len(
                        platform_support[crypto]
                    )
                    portfolios[platform][crypto]["weighting"] *= (
                        portfolios[platform][crypto]["quantity"] / old_quantity
                    )
        for platform, platform_portfolio in portfolios.items():
            old_weightings_sum_capped = sum(
                [portfolio[crypto]["weighting"] for crypto in portfolio if crypto in capped_cryptos]
            )
            weightings_sum_capped = sum(
                [
                    platform_portfolio[crypto]["weighting"]
                    for crypto in platform_portfolio
                    if crypto in capped_cryptos
                ]
            )
            if weightings_sum_capped > 1:
                print(
                    "Transfert",
                    (weightings_sum_capped - 1) * platform_balances[platform],
                    "BTC from another platform or cold wallet to",
                    platform,
                )
                exit(-1)
            assert weightings_sum_capped <= 1
            for crypto in platform_portfolio:
                if crypto not in capped_cryptos:
                    old_weighting = portfolio[crypto]["weighting"]
                    new_weighting = (
                        old_weighting
                        * (1 - weightings_sum_capped)
                        / (1 - old_weightings_sum_capped)
                    )
                    platform_portfolio[crypto]["weighting"] = new_weighting
                    platform_portfolio[crypto]["quantity"] *= new_weighting / old_weighting
        for platform_portfolio in portfolios.values():
            total_weightings = sum(
                [platform_portfolio[crypto]["weighting"] for crypto in platform_portfolio]
            )
            for crypto in platform_portfolio:
                platform_portfolio[crypto]["weighting"] /= total_weightings
            assert (
                abs(
                    sum([platform_portfolio[crypto]["weighting"] for crypto in platform_portfolio])
                    - 1
                )
                < 0.01
            )
        for crypto in portfolio:
            quantity = 0
            for platform_portfolio in portfolios.values():
                if crypto in platform_portfolio:
                    quantity += platform_portfolio[crypto]["quantity"]
            assert (quantity - portfolio[crypto]["quantity"]) < 0.01
        return portfolios

    def get_delta(self, platform, new_balances):
        original_balances = self.balances[platform]["total"]
        original_balances = dict(
            (crypto, balance) for crypto, balance in original_balances.items() if balance
        )
        buy = {}
        sell = {}
        added_cryptos = [crypto for crypto in new_balances if crypto not in list(original_balances)]
        common_cryptos = [
            crypto for crypto in list(new_balances) if crypto not in added_cryptos and crypto
        ]
        removed_cryptos = [
            crypto for crypto in original_balances if crypto not in list(new_balances)
        ]
        for crypto in sorted(added_cryptos):
            buy[crypto] = new_balances[crypto]
        for crypto in sorted(common_cryptos):
            quantity_delta = new_balances[crypto] - original_balances[crypto]
            if quantity_delta > 0:
                buy[crypto] = quantity_delta
            elif quantity_delta < 0:
                sell[crypto] = abs(quantity_delta)
        for crypto in sorted(removed_cryptos):
            sell[crypto] = original_balances[crypto]
        platform_support = self.get_crypto_platform_support(
            list(original_balances) + list(new_balances)
        )
        ignored = []
        delete = []
        for item in [buy, sell]:
            for crypto, quantity in item.items():
                if crypto == "BTT":
                    continue
                if platform not in platform_support[crypto]:
                    delete.append(crypto)
                    continue
                elif crypto == "BTC":
                    limits = {"cost": {"min": 0.001, "max": None}}
                else:
                    limits = self.markets[platform][crypto + "/BTC"]["limits"]
                if (
                    "amount" in limits
                    and quantity < limits["amount"]["min"]
                    or "cost" in limits
                    and quantity * self.get_crypto_price(crypto, platform) < limits["cost"]["min"]
                ):
                    delete.append(crypto)
            for crypto in delete:
                del item[crypto]
                if crypto in added_cryptos:
                    added_cryptos.remove(crypto)
                if crypto in removed_cryptos:
                    removed_cryptos.remove(crypto)
            ignored += delete
            delete = []
        return {
            "buy": buy,
            "sell": sell,
            "added": sorted(added_cryptos),
            "removed": sorted(removed_cryptos),
            "ignored": ignored,
        }

    def apply_delta(self, platform, delta):
        for operation in ["sell", "buy"]:
            if operation == "sell":
                trade_function = self.platforms[platform].create_limit_sell_order
                factor = 1 - self.trading_slippage
            else:
                trade_function = self.platforms[platform].create_limit_buy_order
                factor = 1 + self.trading_slippage
            for crypto, quantity in delta[operation].items():
                if crypto == "BTC":
                    continue
                price = self.tickers[platform][crypto + "/BTC"]["last"] * factor
                print(operation.capitalize(), quantity, crypto, "at", price, "BTC")
                print("Processing", end="", flush=True)
                try:
                    trade = trade_function(crypto + "/BTC", quantity, price)
                except Exception as exc:
                    print(" FAILED:", str(exc))
                    continue
                while True:
                    time.sleep(0.5)
                    try:
                        order = self.platforms[platform].fetch_order(
                            trade["id"], symbol=crypto + "/BTC"
                        )
                    except Exception:
                        print(
                            "... order monitoring not supported. Waiting 5 seconds for completion.",
                            end="",
                            flush=True,
                        )
                        time.sleep(5)
                        break
                    else:
                        if order["status"] in ["closed", "FILLED"]:
                            break
                        else:
                            print(".", end="", flush=True)
                print(" DONE!")

    def rebalance(self, ask_confirmation=True):
        print("########## Balances ##########")
        platform_balances = {}
        for platform in self.platforms:
            balance = self.get_platform_balance(platform)
            platform_balances[platform] = balance
            print(
                platform.capitalize(),
                balance,
                "BTC",
                balance * self.get_crypto_price("BTC", currency="USD"),
                "USD",
            )
        capital = sum(platform_balances.values())
        for crypto, support in self.get_crypto_platform_support(
            list(self.cold_wallet.keys())
        ).items():
            if crypto != "BTC" and self.cold_wallet[crypto] and not support:
                print(crypto, "not supported. Remove it from cold wallet")
                exit(-1)
        for crypto, quantity in self.cold_wallet.items():
            if not quantity:
                continue
            capital += quantity * self.get_crypto_price(crypto)
        print(
            "Cold",
            capital - sum(platform_balances.values()),
            "BTC",
            (capital - sum(platform_balances.values()))
            * self.get_crypto_price("BTC", currency="USD"),
            "USD",
        )
        print()
        print(
            "Total capital",
            capital,
            "BTC",
            capital * self.get_crypto_price("BTC", currency="USD"),
            "USD",
        )
        print()
        print("########## Ideal portfolio ##########")
        ideal_portfolio = self.get_ideal_portfolio(capital)
        for crypto in sorted(
            ideal_portfolio, key=lambda crypto: ideal_portfolio[crypto]["weighting"], reverse=True
        ):
            current_balance = sum(
                [
                    self.balances[platform]["total"][crypto]
                    for platform in self.platforms
                    if crypto in self.balances[platform]["total"]
                ]
            )
            if crypto in self.cold_wallet:
                current_balance += self.cold_wallet[crypto]
            price = self.get_crypto_price(crypto)
            current_ratio = current_balance * price / capital * 100
            print(
                crypto,
                str(round(current_ratio, 2)) + "%",
                current_balance,
                "=>",
                str(round(ideal_portfolio[crypto]["weighting"] * 100, 2)) + "%",
                ideal_portfolio[crypto]["quantity"],
                "[",
                str(round(ideal_portfolio[crypto]["percent_change_24h"], 2)) + "% 1d |",
                str(round(ideal_portfolio[crypto]["percent_change_7d"], 2)) + "% 7d |",
                str(round(ideal_portfolio[crypto]["percent_change_30d"], 2)) + "% 30d |",
                str(round(ideal_portfolio[crypto]["percent_change_60d"], 2)) + "% 60d |",
                str(round(ideal_portfolio[crypto]["percent_change_90d"], 2)) + "% 90d",
                "]",
            )
        print()
        percent_change_24h = sum(
            [
                crypto["weighting"] * crypto["percent_change_24h"]
                for crypto in ideal_portfolio.values()
            ]
        )
        percent_change_7d = sum(
            [
                crypto["weighting"] * crypto["percent_change_7d"]
                for crypto in ideal_portfolio.values()
            ]
        )
        percent_change_30d = sum(
            [
                crypto["weighting"] * crypto["percent_change_30d"]
                for crypto in ideal_portfolio.values()
            ]
        )
        percent_change_60d = sum(
            [
                crypto["weighting"] * crypto["percent_change_60d"]
                for crypto in ideal_portfolio.values()
            ]
        )
        percent_change_90d = sum(
            [
                crypto["weighting"] * crypto["percent_change_90d"]
                for crypto in ideal_portfolio.values()
            ]
        )
        print(
            "Portfolio change:",
            "[",
            str(round(percent_change_24h, 2)) + "% 1d |",
            str(round(percent_change_7d, 2)) + "% 7d |",
            str(round(percent_change_30d, 2)) + "% 30d |",
            str(round(percent_change_60d, 2)) + "% 60d |",
            str(round(percent_change_90d, 2)) + "% 90d",
            "]",
        )
        coinmarketcap = CoinMarketCapAPI(self.coinmarketcap_api_key, sandbox=False)
        bitcoin_data = coinmarketcap.cryptocurrency_listings_latest(start=1, limit=1).data[0]
        print(
            "Bitcoin change:",
            "[",
            str(round(bitcoin_data["quote"]["USD"]["percent_change_24h"], 2)) + "% 1d |",
            str(round(bitcoin_data["quote"]["USD"]["percent_change_7d"], 2)) + "% 7d |",
            str(round(bitcoin_data["quote"]["USD"]["percent_change_30d"], 2)) + "% 30d |",
            str(round(bitcoin_data["quote"]["USD"]["percent_change_60d"], 2)) + "% 60d |",
            str(round(bitcoin_data["quote"]["USD"]["percent_change_90d"], 2)) + "% 90d",
            "]",
        )

        transfers_required = False
        for crypto, cold_balance in self.cold_wallet.items():
            if crypto not in ideal_portfolio and cold_balance:
                if not transfers_required:
                    print()
                print("Remove", crypto, "from cold wallet")
                transfers_required = True
        if transfers_required:
            exit(-1)
        online_ideal_portfolio = self.get_portfolio_excluding_cold_wallet(ideal_portfolio)
        ideal_portfolio_per_platform = self.get_ideal_portfolio_per_platform(
            online_ideal_portfolio, platform_balances
        )
        transfers_required = False
        for platform, portfolio in ideal_portfolio_per_platform.items():
            for crypto in portfolio:
                if portfolio[crypto]["quantity"] < 0:
                    if not transfers_required:
                        print()
                    print(
                        "Transfer",
                        abs(portfolio[crypto]["quantity"]),
                        crypto,
                        "from cold wallet to",
                        platform,
                    )
                    transfers_required = True
        if transfers_required:
            exit(-1)
        deltas = {}
        for platform, portfolio in ideal_portfolio_per_platform.items():
            print()
            print("##########", platform.capitalize(), "##########")
            new_balances = {}
            for crypto in sorted(
                portfolio, key=lambda crypto: portfolio[crypto]["weighting"], reverse=True
            ):
                print(
                    crypto,
                    str(round(ideal_portfolio[crypto]["weighting"] * 100, 2)) + "%",
                    portfolio[crypto]["quantity"],
                )
                new_balances[crypto] = portfolio[crypto]["quantity"]
            print()
            deltas[platform] = self.get_delta(platform, new_balances)
            print("Added:", ", ".join(deltas[platform]["added"]))
            print("Removed:", ", ".join(deltas[platform]["removed"]))
            print("Ignored:", ", ".join(deltas[platform]["ignored"]))
            print()
            for operation in ["sell", "buy"]:
                for crypto, quantity in deltas[platform][operation].items():
                    if crypto == "BTC":
                        continue
                    print(operation.capitalize(), crypto, quantity)
        print()
        self.download_to_cold_wallet(ideal_portfolio)
        print()
        if not ask_confirmation or click.confirm(
            "Do you want to perform the rebalancing now?", default=False
        ):
            print()
            print("########## Live rebalancing ##########")
            for platform, portfolio in ideal_portfolio_per_platform.items():
                print()
                print("Apply delta on", platform.capitalize())
                self.apply_delta(platform, deltas[platform])


def main():
    if len(sys.argv) < 2:
        print("Usage: cryptolio settings.cfg")
        exit(-1)

    config = configparser.ConfigParser()
    config.read(sys.argv[1])
    coinmarketcap_api_key = config["DEFAULT"]["coinmarketcap_api_key"]
    manual_weightings = {}
    for crypto, weighting in config.items("MANUAL_WEIGHTINGS"):
        weighting = weighting.split("#")[0].strip()
        if crypto not in [option for option, _ in config.items("DEFAULT")]:
            try:
                weighting = float(weighting)
                if weighting < 0 or weighting > 1:
                    print("Ponderation must be between 0 and 1")
                    exit(-1)
            except ValueError:
                weighting = weighting.lower()
                if weighting != "auto":
                    print(
                        'Ponderation "'
                        + weighting
                        + '" is not a valid weighting. Only a number or "auto" are allowed'
                    )
                    exit(-1)
            manual_weightings[crypto.upper()] = weighting
    cold_wallet = {}
    for crypto, quantity in config.items("COLD_WALLET"):
        quantity = quantity.split("#")[0].strip()
        if crypto not in [option for option, _ in config.items("DEFAULT")]:
            cold_wallet[crypto.upper()] = float(quantity)
    api_keys = {}
    for platform in [
        key.split("_api_key")[0] for key in config["DEFAULT"] if key.endswith("_api_key")
    ]:
        try:
            api_key = config["DEFAULT"][platform + "_api_key"]
            secret = config["DEFAULT"][platform + "_secret"]
            try:
                password = config["DEFAULT"][platform + "_password"]
            except KeyError:
                password = None
            api_keys[platform] = {"api_key": api_key, "secret": secret}
            if password:
                api_keys[platform]["password"] = password
        except KeyError:
            pass
    if not api_keys:
        print("API keys for at least one platform are required")
        exit(-1)
    try:
        ask_confirmation = config.getboolean("DEFAULT", "ask_confirmation")
    except KeyError as e:
        print("Missing", e.args[0], "parameter in config file")
        exit(-1)
    capping_level = float(config["DEFAULT"]["capping_level"])
    if capping_level < 0 or capping_level > 1:
        print("Capping level must be between 0 and 1")
        exit(-1)
    cold_wallet_ratio = float(config["DEFAULT"]["cold_wallet_ratio"])
    number_of_cryptos = int(config["DEFAULT"]["number_of_cryptos"])
    if number_of_cryptos < 1 or number_of_cryptos < len(
        [crypto for crypto, weighting in manual_weightings.items() if weighting]
    ):
        print("Increase number of cryptos or remove some manual weightings")
        exit(-1)
    trading_slippage = float(config["DEFAULT"]["trading_slippage"])
    if trading_slippage < 0 or trading_slippage > 1:
        print("Trading slippage must be between 0 and 1")
        exit(-1)
    portfolio = PortfolioManager(
        coinmarketcap_api_key,
        api_keys,
        manual_weightings,
        cold_wallet,
        cold_wallet_ratio,
        capping_level,
        number_of_cryptos,
        trading_slippage,
    )
    portfolio.rebalance(ask_confirmation)


if __name__ == "__main__":
    main()
