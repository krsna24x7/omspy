import pyotp
from omspy.base import Broker, pre, post

from kiteconnect import KiteConnect
from kiteconnect import KiteTicker
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from kiteconnect.exceptions import (
    TokenException,
    NetworkException,
    GeneralException,
    KiteException,
    InputException,
)


def get_key(url, key="request_token"):
    """
    Get the required key from the query parameter
    """
    from urllib.parse import parse_qs, urlparse

    req = urlparse(url)
    key = parse_qs(req.query).get(key)
    if key is None:
        return None
    else:
        return key[0]


class Zerodha(Broker):
    """
    Automated Trading class
    """

    def __init__(
        self,
        api_key,
        secret,
        user_id,
        password,
        PIN,
        exchange="NSE",
        product="MIS",
        totp=None,
        is_pin=False,
    ):
        self._api_key = api_key
        self._secret = secret
        self._user_id = user_id
        self._password = password
        self._pin = PIN
        self._totp = totp
        self.is_pin = is_pin
        self.exchange = exchange
        self.product = product
        self._store_access_token = True
        super(Zerodha, self).__init__()

    def _shortcuts(self):
        """
        Provides shortcuts to kite functions by mapping functions.
        Instead of calling at.kite.quote, you would directly call
        at.quote
        Note
        -----
        1) Kite functions are initialized only after authentication
        1) Not all functions are supported
        """
        self.margins = self.kite.margins
        self.profile = self.kite.profile
        self.ltp = self.kite.ltp
        self.quote = self.kite.quote
        self.ohlc = self.kite.ohlc
        self.holdings = self.kite.holdings

    def authenticate(self):
        """
        Authenticates a kite session if access token is already available
        Looks up token in token.tok file
        Useful for reconnecting instead of logging in again
        """
        try:
            self.kite = KiteConnect(api_key=self._api_key)
            with open("token.tok") as f:
                access_token = f.read()
            self.kite.set_access_token(access_token)
            self.kite.profile()
            self.ticker = KiteTicker(
                api_key=self._api_key, access_token=self.kite.access_token
            )
            self._shortcuts()
        except TokenException:
            print("Into Exception")
            self._login()
            self._shortcuts()
            self.ticker = KiteTicker(
                api_key=self._api_key, access_token=self.kite.access_token
            )
        except:
            print("Unknown Exception")
            self._login()
            self._shortcuts()
            self.ticker = KiteTicker(
                api_key=self._api_key, access_token=self.kite.access_token
            )

    def _login(self):
        import time

        self.kite = KiteConnect(api_key=self._api_key)
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        driver = webdriver.Chrome(options=options)
        driver.get(self.kite.login_url())
        login_form = WebDriverWait(driver, 45).until(
            EC.presence_of_element_located((By.CLASS_NAME, "login-form"))
        )
        login_form.find_elements_by_tag_name("input")[0].send_keys(self._user_id)
        login_form.find_elements_by_tag_name("input")[1].send_keys(self._password)
        WebDriverWait(driver, 45).until(
            EC.presence_of_element_located((By.CLASS_NAME, "button-orange"))
        )
        driver.find_element_by_xpath('//button[@type="submit"]').click()
        totp_pass = pyotp.TOTP(self._totp).now()
        twofa_pass = self._pin if self.is_pin is True else totp_pass
        twofa_form = WebDriverWait(driver, 45).until(
            EC.presence_of_element_located((By.CLASS_NAME, "twofa-form"))
        )
        twofa_form.find_elements_by_tag_name("input")[0].send_keys(twofa_pass)
        WebDriverWait(driver, 45).until(
            EC.presence_of_element_located((By.CLASS_NAME, "button-orange"))
        )
        driver.find_element_by_xpath('//button[@type="submit"]').click()
        time.sleep(2)
        token = get_key(driver.current_url)
        access = self.kite.generate_session(
            request_token=token, api_secret=self._secret
        )
        self.kite.set_access_token(access["access_token"])
        with open("token.tok", "w") as f:
            f.write(access["access_token"])
        driver.close()

    @property
    @post
    def orders(self):
        status_map = {
            "OPEN": "PENDING",
            "COMPLETE": "COMPLETE",
            "CANCELLED": "CANCELED",
            "CANCELLED AMO": "CANCELED",
            "REJECTED": "REJECTED",
            "MODIFY_PENDING": "PENDING",
            "OPEN_PENDING": "PENDING",
            "CANCEL_PENDING": "PENDING",
            "AMO_REQ_RECEIVED": "PENDING",
            "TRIGGER_PENDING": "PENDING",
        }
        ords = self.kite.orders()
        # Update status
        for o in ords:
            o["status"] = status_map.get(o["status"], "PENDING")
        return ords

    @property
    @post
    def positions(self):
        """
        Return only the positions for the day
        """
        pos = self.kite.positions()["day"]
        for p in pos:
            if p["quantity"] > 0:
                p["side"] = "BUY"
            else:
                p["side"] = "SELL"
        return pos

    @property
    @post
    def trades(self):
        """
        Return all the trades
        """
        return self.kite.trades()

    @pre
    def order_place(self, **kwargs):
        """
        Place an order
        """
        return self.kite.place_order(**kwargs)

    def order_cancel(self, order_id):
        """
        Cancel an existing order
        """
        return self.kite.cancel_order(order_id=order_id)

    def order_modify(self, order_id, **kwargs):
        """
        Modify an existing order
        Note
        ----
        This is just a basic implementation
        So, all changes must be passed as keyword arguments
        """
        return self.kite.modify_order(order_id=order_id, **kwargs)
