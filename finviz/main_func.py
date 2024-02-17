from datetime import datetime

from lxml import etree

from finviz.helper_functions.request_functions import http_request_get
from finviz.helper_functions.scraper_functions import get_table


class Stock:
    '''
    Base class for ticker data fetching.
    '''

    STOCK_URL:str   = 'https://finviz.com/quote.ashx'
    NEWS_URL:str    = 'https://finviz.com/news.ashx'
    CRYPTO_URL:str  = 'https://finviz.com/crypto_performance.ashx'
    STOCK_PAGE:dict = {}


    def __init__(self, session=None):
        '''

        :param session: session type object
        '''
        self.session = session


    def _get_page(self, ticker:str):
        if ticker not in self.STOCK_PAGE:
            self.STOCK_PAGE[ticker], _ = http_request_get(
                url=self.STOCK_URL,
                session=self.session,
                payload={'t': ticker},
                parse=True
            )

        return self.STOCK_PAGE[ticker]


    def get_fund(self, ticker:str) -> dict:
        '''
        Returns a dictionary containing stock fundamental data.

        :param ticker: stock symbol
        :type ticker: str
        :return dict
        '''

        page_parsed = self._get_page(ticker)

        title = page_parsed.cssselect('div[class="fv-container py-2.5"]')[0]
        keys = ["Ticker", "Company", "Sector", "Industry", "Country", "Exchange"]

        data = {}

        data["Ticker"] = title.cssselect('h1[class="js-recent-quote-ticker quote-header_ticker-wrapper_ticker"]')[0].text_content().strip()
        try:
            company_details = title.cssselect('h2[class="quote-header_ticker-wrapper_company text-xl"]')[0]
        except IndexError:
            company_details = title.cssselect('h2[class="quote-header_ticker-wrapper_company"]')[0]
        data["Company"] = company_details.text_content().strip()

        try:
            company_link = company_details.cssselect('a[class="tab-link block truncate"]')[0].attrib["href"]
            data["Website"] = company_link if company_link.startswith("http") else None
        except IndexError:
            pass

        fields = [f.text_content() for f in title.cssselect('a[class="tab-link"]')]

        data.update(dict(zip(keys, fields)))

        td_texts = []

        for tr in page_parsed.cssselect('tr[class="table-dark-row"]'):
            tds = tr.xpath("td//text()")
            for td in tds:
                text = td.strip()
                if text and text != 'Trades':
                    td_texts.append(text)

        for key, value in dict(zip(td_texts[::2], td_texts[1::2])).items():
            if key == "EPS next Y" and "EPS next Y" in data.keys():
                data["EPS growth next Y"] = value
                continue
            elif key == "Volatility":
                vols = value.split()
                data["Volatility (Week)"] = vols[0]
                data["Volatility (Month)"] = vols[1]
                continue

            data[key] = value

        return data


    def get_insider(self, ticker:str) -> list:
        '''
        Returns a list of dictionaries containing all recent insider transactions.

        :param ticker: stock symbol
        :return: list
        '''

        page_parsed = self._get_page(ticker)
        outer_table = page_parsed.cssselect('table[class="body-table insider-trading-table"]')

        if len(outer_table) == 0:
            return []

        table = outer_table[0]
        headers = table[0].xpath("td//text()")

        data = [dict(zip(
            headers,
            [etree.tostring(elem, method="text", encoding="unicode") for elem in row]
        )) for row in table[1:]]

        return data


    def get_news(self, ticker:str) -> list:
        '''
        Returns a list of sets containing news headline and url

        :param ticker: stock symbol
        :return: list
        '''

        page_parsed = self._get_page(ticker)
        news_table = page_parsed.cssselect('table[id="news-table"]')

        if len(news_table) == 0:
            return []

        rows = news_table[0].xpath("./tr[not(@id)]")

        results = []
        date = None
        for row in rows:
            raw_timestamp = row.xpath("./td")[0].xpath("text()")[0][0:-2]

            if len(raw_timestamp) > 8:
                parsed_timestamp = datetime.strptime(raw_timestamp, "%b-%d-%y %I:%M%p")
                date = parsed_timestamp.date()
            else:
                parsed_timestamp = datetime.strptime(raw_timestamp, "%I:%M%p").replace(
                    year=date.year, month=date.month, day=date.day)

            results.append((
                parsed_timestamp.strftime("%Y-%m-%d %H:%M"),
                row.xpath("./td")[1].cssselect('a[class="tab-link-news"]')[0].xpath("text()")[0],
                row.xpath("./td")[1].cssselect('a[class="tab-link-news"]')[0].get("href"),
                row.xpath("./td")[1].cssselect('div[class="news-link-right"] span')[0].xpath("text()")[0][1:]
            ))

        return results


    def get_all_news(self) -> list:
        '''
        Returns a list of sets containing time, headline and url
        :return: list
        '''

        page_parsed, _ = http_request_get(url=self.NEWS_URL, parse=True)
        all_dates = [
            row.text_content() for row in page_parsed.cssselect('td[class="nn-date"]')
        ]
        all_headlines = [
            row.text_content() for row in page_parsed.cssselect('a[class="nn-tab-link"]')
        ]
        all_links = [
            row.get("href") for row in page_parsed.cssselect('a[class="nn-tab-link"]')
        ]

        return list(zip(all_dates, all_headlines, all_links))


    def get_crypto(self, pair:str) -> dict:
        '''
        Get crypto pair information.

        :param pair: crypto pair
        :return: dictionary
        '''

        page_parsed, _ = http_request_get(url=self.CRYPTO_URL, session=self.session, parse=True)
        page_html, _ = http_request_get(url=self.CRYPTO_URL, session=self.session, parse=False)

        crypto_headers = page_parsed.cssselect('tr[valign="middle"]')[0].xpath("td//text()")
        crypto_table_data = get_table(page_html, crypto_headers)

        return crypto_table_data[pair]


    def get_analyst_price_targets(self, ticker:str, last_ratings:int=5) -> list:
        '''
        Returns a list of dictionaries containing all analyst ratings and Price targets
        - if any of 'price_from' or 'price_to' are not available in the DATA, then those values are set to default 0
        :param ticker: stock symbol
        :param last_ratings: most recent ratings to pull
        :return: list
        '''

        analyst_price_targets = []

        try:
            page_parsed = self._get_page(ticker)

            table = page_parsed.cssselect(
                'table[class="js-table-ratings fullview-ratings-outer"]'
            )[0]

            for row in table:
                rating = row.xpath("td//text()")
                rating = [val.replace("→", "->").replace("$", "") for val in rating if val != "\n"]
                rating[0] = datetime.strptime(rating[0], "%b-%d-%y").strftime("%Y-%m-%d")

                data = {
                    "date": rating[0],
                    "category": rating[1],
                    "analyst": rating[2],
                    "rating": rating[3],
                }
                if len(rating) == 5:
                    if "->" in rating[4]:
                        rating.extend(rating[4].replace(" ", "").split("->"))
                        del rating[4]
                        data["target_from"] = float(rating[4])
                        data["target_to"] = float(rating[5])
                    else:
                        data["target"] = float(rating[4])

                analyst_price_targets.append(data)
        except Exception as e:
            pass

        return analyst_price_targets[:last_ratings]