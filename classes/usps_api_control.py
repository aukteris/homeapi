from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
import time
import os.path
import requests
from requests.auth import AuthBase
import requests_cache
import datetime
import pickle
import json
import re
from bs4 import BeautifulSoup

class USPSError(Exception):
    """ Error while working with USPS """
    pass

class SFDCError(Exception):
    """ Error while working with USPS """
    pass

### INTERACT WITH USPS SITE (VIA SELENIUM)

class USPSApi():
    LOGUN_URL = 'https://reg.usps.com/entreg/LoginAction_input?app=Phoenix&appURL=https://www.usps.com/'
    DASHBOARD_URL = 'https://informeddelivery.usps.com/box/pages/secure/DashboardAction_input.action'
    INFORMED_DELIVERY_IMAGE_URL = 'https://informeddelivery.usps.com/box/pages/secure/'
    COOKIE_PATH = './usps_cookies.pickle'
    CACHE_NAME = 'usps_cache'
    USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) ' \
                'Chrome/41.0.2228.0 Safari/537.36'

    def _save_cookies(self,requests_cookiejar, filename):
        """Save cookies to a file."""
        print('saved cookies')
        with open(filename, 'wb') as handle:
            pickle.dump(requests_cookiejar, handle)

    def _load_cookies(self,filename):
        """Load cookies from a file."""
        print('loading cookies')
        with open(filename, 'rb') as handle:
            return pickle.load(handle)

    def _login(self,session):
        print('trying to login to usps')
        chromeOptions = webdriver.ChromeOptions()
        chromeOptions.add_argument("--remote-debugging-port=9222")
        chromeOptions.add_argument("--no-sandbox")
        chromeOptions.add_argument("--disable-gpu")
        chromeOptions.add_argument("--disable-extensions")
        chromeOptions.add_argument("--headless")
        chromeOptions.add_argument('--user-agent={}'.format(self.USER_AGENT))
        chromeOptions.add_argument("--log-path=/home/aukteris/chromedriver.log")
        chromeOptions.binary_location = r"/usr/bin/google-chrome"

        service = Service(executable_path=r'/usr/local/bin/chromedriver')

        driver = webdriver.Chrome(service=service, options=chromeOptions)
        driver.get(self.LOGUN_URL)

        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input#username"))).send_keys(session.auth.username)
        driver.find_element(By.CSS_SELECTOR, "input#password").send_keys(session.auth.password)
        driver.find_element(By.CSS_SELECTOR, "button#btn-submit").click()

        try:
            WebDriverWait(driver, 15).until(EC.title_is('Welcome | USPS'))
        except TimeoutException:
            print(driver.title)
            driver.quit()
            raise USPSError('login failed')

        print('logged in to usps')
        for cookie in driver.get_cookies():
            session.cookies.set(name=cookie['name'], value=cookie['value'])
        self._save_cookies(session.cookies, self.COOKIE_PATH)

        driver.quit()

    def authenticated_usps(function):
        """Re-authenticate if session expired."""
        def wrapped(*args):
            """Wrap function."""
            try:
                return function(*args)
            except USPSError:
                print('authentication expired')
                args[0]._login(args[1])
                return function(*args)
        return wrapped

    @authenticated_usps
    def _get_dashboard(self,session, date):
        response = session.get(self.DASHBOARD_URL, params={
            'selectedDate': '{0:%m}/{0:%d}/{0:%Y}'.format(date)
        }, allow_redirects=False)

        if response.status_code == 302:
            raise USPSError('expired session')
        return response

    def _get_mailpiece_image(self,row):
        try:
            return row.find('img', {'class': 'mailpieceIMG'}).get('src')
        except AttributeError:
            return None

    def _get_mailpiece_id(self,image):
        parts = image.split('=')
        if len(parts) != 2:
            return None
        return parts[1]

    def _get_mailpiece_url(self,image):
        """Get mailpiece url."""
        return '{}{}'.format(self.INFORMED_DELIVERY_IMAGE_URL, image)

    @authenticated_usps
    def get_mail(self, session, date=None):
        print('getting mail')
        
        if date is None:
            date = datetime.datetime.now().date()
        
        response = self._get_dashboard(session, date)
        parsed = BeautifulSoup(response.text, 'html.parser')
        mail = []
        for row in parsed.find_all('div', {'class': 'mailpiece'}):
            image = self._get_mailpiece_image(row)
            if not image:
                continue
            mail.append({
                'id': self._get_mailpiece_id(image),
                'image': self._get_mailpiece_url(image),
                'date': date
            })
        
        mail_count = 0
        date_text = date.strftime('%m/%d/%Y')
        
        for row in parsed.find_all('li', {'id': date_text}):
            selected_day_text = row.find('a').get_text()
            mail_count = re.findall('\(([0-9]?)\)', selected_day_text)[0]
        
        mail_check_result = {
            'count': int(mail_count),
            'mail': mail
        }

        return mail_check_result

    def start_session(self, user, password):
        class USPSAuth(AuthBase):
            def __init__(self, username, password):
                self.username = username
                self.password = password
            
            def __call__(self, r):
                return r
            
        #session = requests.Session()
        session = requests_cache.CachedSession(cache_name=self.CACHE_NAME)
        session.auth = USPSAuth(user, password)

        if os.path.exists(self.COOKIE_PATH):
            session.cookies = self._load_cookies(self.COOKIE_PATH)
        else :
            self._login(session)

        return session

    @authenticated_usps
    def download_image(self, session, image):
        response = session.get(image, allow_redirects=False)
        if response.status_code == 302:
            raise USPSError('expired session')
        print("image downloaded")
        return response

### INTERACT WITH SALESFORCE

class SFDCApi():
    ACCESS_TOKEN_PATH = './sfdc_access_token'
    SFDC_CACHE_NAME = 'sfdc_cache'

    REST_BASE_URL = '/services/data/'
    API_VERSION = 'v52.0'
    CONTENT_VERSION_ENDPOINT = '/sobjects/ContentVersion'
    MAIL_ENDPOINT = '/sobjects/Mail__c/'
    REFRESH_TOKEN_ENDPOINT = '/services/oauth2/token'
    FLOW_ENDPOINT = '/actions/custom/flow/'

    def _save_token(self, token, filename):
        """Save cookies to a file."""
        print('saved token')
        with open(filename, 'wb') as handle:
            pickle.dump(token, handle)

    def _load_token(self, filename):
        """Load cookies from a file."""
        print('loading token')
        with open(filename, 'rb') as handle:
            return pickle.load(handle)

    def _refresh_sfdc(self, session):
        print('refreshing access token')
        requestData = {'grant_type':'refresh_token',
                        'client_id':session.auth.client_id,
                        'client_secret':session.auth.client_secret,
                        'refresh_token':session.auth.refresh_token}
        res = requests.post(url=session.auth.domain + self.REFRESH_TOKEN_ENDPOINT,
                            data=requestData)

        if res.status_code == 200:
            resultObj = json.loads(res.content)
            self._save_token(resultObj['access_token'], self.ACCESS_TOKEN_PATH)
            session.auth.access_token = resultObj['access_token']

    def authenticated_sfdc(function):
        """Re-authenticate if session expired."""
        def wrapped(*args):
            """Wrap function."""
            try:
                return function(*args)
            except SFDCError:
                print('sfdc authentication expired')
                args[0]._refresh_sfdc(args[1])
                return function(*args)
        return wrapped

    def get_sfdc_session(self, cid, csec, ref, dom):

        class SFDCAuth(AuthBase): 
            """SFDC authorization storage."""

            def __init__(self, client_id, client_secret, refresh_token, domain):
                """Init."""
                self.access_token = None
                self.client_id = client_id
                self.client_secret = client_secret
                self.refresh_token = refresh_token
                self.domain = domain

            def __call__(self, r):
                """Call is no-op."""
                return r

        session = requests_cache.CachedSession(cache_name=self.SFDC_CACHE_NAME)
        session.auth = SFDCAuth(cid, csec, ref, dom)

        if os.path.exists(self.ACCESS_TOKEN_PATH):
            session.auth.access_token = self._load_token(self.ACCESS_TOKEN_PATH)
        else:
            self._refresh_sfdc(session)

        return session

    @authenticated_sfdc
    def new_mail_item(self, session, mail_item):
        print('inserting mail record')
        headers = {'Authorization':f'Bearer {session.auth.access_token}',
                    'Content-Type':'application/json'}
        requestData = {'Name':mail_item['id'],
                        'Delivery_Date__c':mail_item['date'].strftime("%Y-%m-%d")}
        requestUrl = session.auth.domain + self.REST_BASE_URL + self.API_VERSION + self.MAIL_ENDPOINT

        res = session.post(url = requestUrl,
                            data = json.dumps(requestData),
                            headers = headers)
        
        if res.status_code == 401:
            raise SFDCError('access token expired')

        return json.loads(res.content)['id']

    @authenticated_sfdc
    def upload_mail_image(self, session, mail_item, rec_id, image_data):
        print('attaching mail image')
        head1 = f'--boundary_string\nContent-Disposition: form-data; name="entity_content";\nContent-Type: application/json\n\n{{\n    "PathOnClient" : "uploadedMailPiece.jpg",\n    "FirstPublishLocationId" : "{rec_id}"\n}}\n\n--boundary_string\nContent-Type: application/octet-stream\nContent-Disposition: form-data; name="VersionData"; filename="uploadedMailPiece.jpg"\n\n'
        head2 = '\n\n--boundary_string--'

        headers = {'Content-Type': 'multipart/form-data; boundary=boundary_string',
                    'Authorization':f'Bearer {session.auth.access_token}'}
        requestData = bytes(head1, 'utf-8') + image_data + bytes(head2, 'utf-8')
        requestUrl = session.auth.domain + self.REST_BASE_URL + self.API_VERSION + self.CONTENT_VERSION_ENDPOINT

        res = session.post(url = requestUrl,
                            data = requestData,
                            headers = headers)
        
        if res.status_code == 401:
            raise SFDCError('access token expired')
        
        return res

    @authenticated_sfdc
    def send_notification(self, session, body):
        print('starting flow')
        headers = {'Authorization':f'Bearer {session.auth.access_token}',
                    'Content-Type':'application/json'}
        requestUrl = session.auth.domain + self.REST_BASE_URL + self.API_VERSION + self.FLOW_ENDPOINT + 'Send_Mail_Alert'
        requestData = {
            'inputs' : [{
                'Notification_Body': body
            }]
        }

        res = session.post(url = requestUrl,
                            data = json.dumps(requestData),
                            headers = headers)

        if res.status_code == 401:
            raise SFDCError('access token expired')

        return res