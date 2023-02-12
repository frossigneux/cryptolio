#!/usr/bin/env python3

import configparser
import datetime
import json
import sys
import time
from zipfile import ZipFile

import matplotlib.pyplot as plt
import semidbm
import undetected_chromedriver as uc
from lxml import html


class Portfolio:
    def __init__(
        self,
        manual_weightings={},
        capping_level=0.1,
        number_of_cryptos=20,
        fees=0.0025,
        cache_dir="backtest_cache",
    ):
        self.manual_weightings = manual_weightings
        self.fees = fees
        self.capping_level = capping_level
        self.number_of_cryptos = number_of_cryptos
        self.db = semidbm.open(cache_dir, "c")
        self.driver = None

    def auto_scroll(self, driver, sleep):
        old_position = 0
        new_position = 1
        distance = 600
        while new_position != old_position:
            old_position = new_position
            driver.execute_script(f"window.scrollBy(0, {distance})")
            time.sleep(sleep)
            new_position = driver.execute_script("return window.pageYOffset")

    def get_crypto_list(self, date):
        # Snapshots are done every sundays
        if not self.driver:
            options = uc.ChromeOptions()
            options.add_argument("--incognito")
            with ZipFile("extensions/i_dont_care_about_cookies.crx", mode="r") as extension_zip:
                extension_zip.extractall("extensions/i_dont_care_about_cookies")
            options.add_argument("--load-extension=extensions/i_dont_care_about_cookies")
            self.driver = uc.Chrome(options=options)
            self.driver.get("chrome://extensions/?id=hopckdfffhkbakcggpmgoingfjfahbjn")
            self.driver.execute_script(
                "return document.querySelector('extensions-manager').shadowRoot.querySelector('extensions-item-list').shadowRoot.querySelector('extensions-item').shadowRoot.querySelector('#detailsButton').click()"
            )
            self.driver.execute_script(
                "return document.querySelector('extensions-manager').shadowRoot.querySelector('#viewManager > extensions-detail-view').shadowRoot.querySelector('#allow-incognito').shadowRoot.querySelector('#crToggle').click()"
            )
            time.sleep(1)
        crypto_list = []
        self.driver.get("https://coinmarketcap.com/historical/" + date.strftime("%Y%m%d"))
        for more in range(0, 4):
            self.auto_scroll(self.driver, 0.2)
            self.driver.execute_script(
                "return document.getElementsByClassName('cmc-table-listing__loadmore')"
            )[0].click()
        self.driver.execute_script("window.scrollTo(0, 0)")
        self.auto_scroll(self.driver, 0.2)
        tree = html.fromstring(self.driver.page_source)
        rows = tree.xpath("//table/tbody")[0]
        for i in range(1, len(rows)):
            node = rows[i]
            items = [text for text in node.itertext()]
            symbol = items[1]
            marketcap = float(items[4].replace(",", "").replace("$", ""))
            if items[5] == "--":
                continue
            price = float(items[5].replace(",", "").replace("$", ""))
            crypto = {
                "name": items[1],
                "symbol": symbol,
                "marketcap": marketcap,
                "usd_price": price,
            }
            print(crypto)
            crypto_list.append(crypto)
        return crypto_list

    def get_historical_top_cryptos(self, date, limit=20, forced_cryptos=[], excluded_cryptos=[]):
        try:
            crypto_list = json.loads(self.db[str(date)].decode())
        except KeyError:
            print("Cache miss, fetching historical data from coinmarketcap...")
            crypto_list = self.get_crypto_list(date)
            if crypto_list:
                self.db[str(date)] = json.dumps(crypto_list)
        top_cryptos = {}
        selected_cryptos = []
        appended = []
        for crypto in crypto_list:
            if crypto["symbol"] in forced_cryptos and crypto["symbol"] not in appended:
                selected_cryptos.append(crypto)
                appended.append(crypto["symbol"])
            if len(selected_cryptos) == len(forced_cryptos):
                break
        for crypto in crypto_list:
            if len(selected_cryptos) == limit:
                break
            if (
                crypto["symbol"] not in forced_cryptos
                and crypto["symbol"] not in excluded_cryptos
                and crypto["symbol"] not in appended
            ):
                selected_cryptos.append(crypto)
                appended.append(crypto["symbol"])
        for crypto in selected_cryptos:
            top_cryptos[crypto["symbol"]] = {
                "name": crypto["name"],
                "symbol": crypto["symbol"],
                "marketcap": crypto["marketcap"],
                "usd_price": crypto["usd_price"],
            }
        return top_cryptos

    def update_portfolio_values(self, portfolio, top_cryptos):
        for crypto in portfolio:
            if crypto not in top_cryptos:
                print("Warning, crypto", crypto, "not found, reuse old values")
                continue
            if top_cryptos[crypto]["marketcap"]:
                portfolio[crypto]["marketcap"] = top_cryptos[crypto]["marketcap"]
            else:
                print("Warning, new marketcap not found, reuse old", crypto, "marketcap value")
                portfolio[crypto]["marketcap"]
            if top_cryptos[crypto]["usd_price"]:
                portfolio[crypto]["usd_price"] = top_cryptos[crypto]["usd_price"]
            else:
                print("Warning, new price not found, reuse old", crypto, "price")
                portfolio[crypto]["usd_price"]

    def get_balance(self, portfolio):
        return sum(
            [portfolio[crypto]["usd_price"] * portfolio[crypto]["quantity"] for crypto in portfolio]
        )

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

    def get_historical_ideal_portfolio(self, date, capital):
        forced_cryptos = [crypto for crypto, quantity in self.manual_weightings.items() if quantity]
        excluded_cryptos = [
            crypto for crypto, quantity in self.manual_weightings.items() if not quantity
        ]
        portfolio = self.get_historical_top_cryptos(
            date, self.number_of_cryptos, forced_cryptos, excluded_cryptos
        )
        total_market_cap = self.get_total_market_cap(portfolio)
        for crypto, values in portfolio.items():
            weighting = values["marketcap"] / total_market_cap
            portfolio[crypto]["weighting"] = weighting
            portfolio[crypto]["quantity"] = capital * weighting / values["usd_price"]
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
        assert abs(self.get_balance(portfolio) / capital - 1) < 0.01
        return portfolio

    def compare(self, original_portfolio, new_portfolio):
        added_cryptos = [
            crypto for crypto in new_portfolio if crypto not in list(original_portfolio)
        ]
        removed_cryptos = [
            crypto for crypto in original_portfolio if crypto not in list(new_portfolio)
        ]
        common_cryptos = [
            crypto for crypto in list(new_portfolio) if crypto not in added_cryptos and crypto
        ]
        for crypto, values in sorted(
            new_portfolio.items(), key=lambda p: p[1]["weighting"], reverse=True
        ):
            print(crypto, values["weighting"] * 100, "%")
        print()
        for crypto in sorted(removed_cryptos):
            print("Sell", original_portfolio[crypto]["quantity"], crypto, "removed from index")
        for crypto in sorted(common_cryptos):
            if new_portfolio[crypto]["quantity"] < original_portfolio[crypto]["quantity"]:
                delta = original_portfolio[crypto]["quantity"] - new_portfolio[crypto]["quantity"]
                delta_percent = delta / original_portfolio[crypto]["quantity"] * 100
                if delta_percent > 0.1:
                    print(
                        "Sell",
                        delta,
                        crypto,
                        "(" + str(original_portfolio[crypto]["quantity"]),
                        "=>",
                        new_portfolio[crypto]["quantity"],
                        "-%.2f" % delta_percent,
                        "%)",
                    )
        for crypto in sorted(common_cryptos):
            if new_portfolio[crypto]["quantity"] > original_portfolio[crypto]["quantity"]:
                delta = new_portfolio[crypto]["quantity"] - original_portfolio[crypto]["quantity"]
                delta_percent = delta / original_portfolio[crypto]["quantity"] * 100
                if delta_percent > 0.1:
                    print(
                        "Buy",
                        delta,
                        crypto,
                        "(" + str(original_portfolio[crypto]["quantity"]),
                        "=>",
                        new_portfolio[crypto]["quantity"],
                        "+%.2f" % delta_percent,
                        "%)",
                    )
        for crypto in sorted(added_cryptos):
            print("Buy", new_portfolio[crypto]["quantity"], crypto, "(added in index)")

    def backtest(self, capital, start_date, end_date, week_interval=1):
        results = []
        idx = (start_date.weekday() + 1) % 7
        last_sunday = start_date - datetime.timedelta(idx)
        original_portfolio = self.get_historical_ideal_portfolio(last_sunday, capital)
        results.append((last_sunday, capital))
        next_sunday = last_sunday + datetime.timedelta(weeks=week_interval)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        while next_sunday <= end_date and next_sunday != today:
            print("Date: " + str(next_sunday))
            old_balance = self.get_balance(original_portfolio)
            top_cryptos = self.get_historical_top_cryptos(
                next_sunday, forced_cryptos=list(original_portfolio.keys())
            )
            self.update_portfolio_values(original_portfolio, top_cryptos)
            new_balance = self.get_balance(original_portfolio)
            print("Old balance: %.2f" % old_balance, "$")
            next_portfolio = self.get_historical_ideal_portfolio(next_sunday, new_balance)
            for crypto in next_portfolio:
                if crypto in original_portfolio:
                    next_portfolio[crypto]["quantity"] -= (
                        abs(
                            original_portfolio[crypto]["quantity"]
                            - next_portfolio[crypto]["quantity"]
                        )
                        * 2
                        * self.fees
                    )
                else:
                    next_portfolio[crypto]["quantity"] *= 1 - 2 * self.fees
            new_balance = self.get_balance(next_portfolio)
            variation = "+" if new_balance >= old_balance else ""
            results.append((next_sunday, new_balance))
            print(
                "New balance:",
                "%.2f" % new_balance,
                "$",
                variation + "%.2f" % (((new_balance / old_balance) - 1) * 100),
                "%",
            )
            print()
            self.compare(original_portfolio, next_portfolio)
            next_sunday += datetime.timedelta(weeks=week_interval)
            original_portfolio = next_portfolio
            print()
            if next_sunday <= end_date and next_sunday != today:
                print(
                    "###############################################################################"
                )
                print()
        if self.driver:
            self.driver.quit()
        self.db.close()
        return results


def main():
    if len(sys.argv) < 2:
        print("Usage: cryptolio-backtest settings.cfg")
        exit(-1)
    config = configparser.ConfigParser()
    config.read(sys.argv[1])
    manual_weightings = {}
    for crypto, weighting in config.items("BACKTEST_MANUAL_WEIGHTINGS"):
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
    start_date = config["BACKTEST"]["start_date"]
    try:
        start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        print("Wrong date format")
        exit(-1)
    end_date = config["BACKTEST"]["end_date"]
    try:
        end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        if end_date == "now":
            end_date = datetime.datetime.now()
        else:
            print("Wrong date format")
            exit(-1)
    if start_date >= end_date:
        print("End date must be greater than start date")
        exit(-1)
    if end_date != "now" and end_date > datetime.datetime.now():
        print("End date must be lower than today's date or set to now")
        exit(-1)
    week_interval = int(config["BACKTEST"]["week_interval"])
    if week_interval <= 0:
        print("Week interval must be a positive integer")
        exit(-1)
    capital = int(config["BACKTEST"]["initial_capital"])
    if capital < 0:
        print("Initial capital must be a positive integer")
        exit(-1)
    capping_level_list = [float(n) for n in config["BACKTEST"]["capping_level"].split(",")]
    number_of_cryptos_list = [int(n) for n in config["BACKTEST"]["number_of_cryptos"].split(",")]
    fees = float(config["BACKTEST"]["fees"])
    draw_charts = config["BACKTEST"]["draw_charts"]
    if draw_charts.lower() not in ["true", "false"]:
        print("Charts must be true or false")
        exit(-1)
    draw_charts = True if draw_charts.lower() == "true" else False
    log_scale = config["BACKTEST"]["log_scale"]
    if log_scale.lower() not in ["true", "false"]:
        print("Log scale must be true or false")
        exit(-1)
    log_scale = True if log_scale.lower() == "true" else False
    cache_dir = config["BACKTEST"]["cache_dir"]
    if fees < 0:
        print("Fees must be a positive float")
        exit(-1)
    backtests = {}
    for capping_level in capping_level_list:
        for number_of_cryptos in number_of_cryptos_list:
            if capping_level * number_of_cryptos < 1:
                print(
                    "Skipping backtest",
                    capping_level,
                    "capping level with",
                    number_of_cryptos,
                    "cryptos",
                )
                continue
            print("###############################################################################")
            print(
                "Run backtest with",
                capping_level,
                "capping level and",
                number_of_cryptos,
                "cryptos",
            )
            print("###############################################################################")
            portfolio = Portfolio(
                manual_weightings, capping_level, number_of_cryptos, fees, cache_dir
            )
            backtests[(capping_level, number_of_cryptos)] = portfolio.backtest(
                capital, start_date, end_date, week_interval
            )
    print("Final capital:")
    final_capital = []
    for params, backtest in backtests.items():
        final_capital.append((backtest[-1][1], params))
    for capital, params in sorted(final_capital, reverse=True):
        print(
            "%.2f" % capital,
            "$ with capping_level=" + str(params[0]),
            "and number_of_cryptos=" + str(params[1]),
        )
    print()
    wins = {}
    first_serie = backtests[list(backtests.keys())[0]]
    for i in range(0, len(first_serie)):
        winner_value = 0
        winner_params = None
        for params, backtest in backtests.items():
            if backtest[i][1] > winner_value:
                winner_value = backtest[i][1]
                winner_params = params
        if winner_params not in wins:
            wins[winner_params] = 1
        else:
            wins[winner_params] += 1
    assert sum(wins.values()) == len(first_serie)
    best_params = max(wins, key=wins.get)
    print(
        "The parameters with the maximum number of wins are capping_level=" + str(best_params[0]),
        "and number_of_cryptos=" + str(best_params[1]),
    )
    print()
    if not draw_charts:
        return
    x = [str(c) + " - " + str(s) for c, s in sorted(list(wins.keys()))]
    y = [wins[params] for params in sorted(list(wins.keys()))]
    plt.figure(0, figsize=(15, 8))
    plt.title("Winners")
    plt.xlabel("Parameters")
    plt.bar(x, y)
    plt.ylabel("Number of wins")
    plt.figure(1, figsize=(15, 8))
    plt.title("Profit")
    if log_scale:
        plt.yscale("log")
    plt.ylabel("Capital")
    legend = []
    for capping_level in capping_level_list:
        for number_of_cryptos in number_of_cryptos_list:
            if capping_level * number_of_cryptos < 1:
                continue
            legend.append(str(capping_level) + " - " + str(number_of_cryptos))
            results = backtests[(capping_level, number_of_cryptos)]
            x = [tup[0] for tup in results]
            y = [tup[1] for tup in results]
            plt.plot(x, y)
    plt.legend(legend, loc="upper left")
    plt.show()


if __name__ == "__main__":
    main()
