import os
import json
import time
import random
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# ---------- Requirements for Selenium Login -------------
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --------------------------------------------------------
# Configuration
# --------------------------------------------------------
COOKIE_FILE = "cookies.json"
HOST = "0.0.0.0"
PORT = 8080
user_name = ""
password = ""

# Bearer token for server authentication
DEFAULT_TOKEN = "MY_SUPER_SECRET_TOKEN"

# Retrieve LinkedIn credentials from env or set them here
LINKEDIN_USERNAME = os.getenv("LINKEDIN_USERNAME", user_name)
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", password)


# --------------------------------------------------------
def load_cookies():
    """Load cookies from COOKIE_FILE. Returns list of dicts or empty if not found."""
    try:
        with open(COOKIE_FILE, "r") as f:
            data = json.load(f)
            return data.get("cookies", [])
    except FileNotFoundError:
        return []

def save_cookies(cookie_list):
    """Save list of dict cookies to COOKIE_FILE with timestamp."""
    data = {"timestamp": time.time(), "cookies": cookie_list}
    with open(COOKIE_FILE, "w") as f:
        json.dump(data, f)

def cookies_to_dict(cookie_list):
    """Convert Selenium-style cookies (list of dicts) to {name: value} for requests."""
    return {c["name"]: c["value"] for c in cookie_list}

def login_linkedin():
    """
    Logs into LinkedIn via Selenium, stores cookies in COOKIE_FILE.
    Returns True if successful, False otherwise.
    """
    if not LINKEDIN_USERNAME or not LINKEDIN_PASSWORD:
        print("ERROR: LinkedIn username/password not provided.")
        return False

    options = webdriver.ChromeOptions()
    # Uncomment to run Chrome in headless mode:
    # options.add_argument("--headless")

    driver = webdriver.Chrome(options=options)
    driver.get("https://www.linkedin.com/login")

    try:
        # Wait for username input
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "username"))
        ).send_keys(LINKEDIN_USERNAME)

        # Enter password
        driver.find_element(By.ID, "password").send_keys(LINKEDIN_PASSWORD)

        # Submit form
        driver.find_element(By.XPATH, '//button[@type="submit"]').click()

        # Wait for an element that indicates we are logged in
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "global-nav-search"))
        )

        # Retrieve cookies
        cookies = driver.get_cookies()
        save_cookies(cookies)
        print("Successfully logged in. Cookies saved.")
        return True

    except Exception as e:
        print("Login failed:", e)
        return False

    finally:
        driver.quit()


def voyager_get_connections(cookies, start=0, count=10):
    """
    Fetch user's connections from My Network (private voyager endpoint).
    """
    url = ""
    params = {
        "count": count,
        "start": start,
        "q": "recent"
    }
    # random small delay
    time.sleep(random.uniform(1, 3))

    headers = {
        "Accept": "application/vnd.linkedin.normalized+json+2.1",
        "X-RestLi-Protocol-Version": "2.0.0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    cookie_dict = cookies_to_dict(cookies)

    resp = requests.get(url, headers=headers, params=params, cookies=cookie_dict)
    if resp.status_code == 200:
        return resp.json()
    return {
        "error": True,
        "status_code": resp.status_code,
        "body": resp.text
    }

def parse_connections(raw_json):
    """
    Extract minimal details from the voyager connections JSON.
    Typically in: raw_json["data"]["elements"][...]["handle~"]...
    """
    data_section = raw_json.get("data", {})
    elements = data_section.get("elements", [])
    results = []
    for el in elements:
        handle = el.get("handle~", {})
        first_name = handle.get("firstName", "")
        last_name = handle.get("lastName", "")
        occupation = handle.get("occupation", "")
        # Email is rarely present in direct connections data
        email = handle.get("emailAddress", None)
        results.append({
            "firstName": first_name,
            "lastName": last_name,
            "occupation": occupation,
            "email": email
        })
    return results


# --------------------------------------------------------
class LinkedInRequestHandler(BaseHTTPRequestHandler):

    def _check_auth(self):
        """Check Bearer token in Authorization header."""
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            self._send_json({"error": "Unauthorized"}, 401)
            return False
        token = auth_header.split(" ", 1)[1]
        valid_token = os.getenv("API_BEARER_TOKEN", DEFAULT_TOKEN)
        if token != valid_token:
            self._send_json({"error": "Forbidden"}, 403)
            return False
        return True

    def _send_json(self, data, status=200):
        """Utility to send JSON response."""
        response = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(response)

    def do_POST(self):
        """
        Handles POST requests. We only expect /login-linkedin here.
        """
        parsed = urlparse(self.path)
        if parsed.path == "/login-linkedin":
            # Check Bearer token
            if not self._check_auth():
                return

            success = login_linkedin()
            if success:
                self._send_json({"status": "success", "message": "Logged in and cookies saved."}, 200)
            else:
                self._send_json({"status": "fail", "message": "Login failed."}, 500)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_GET(self):
        """
        Handles GET requests.
        - /my-profile
        - /connections?page=x&size=y
        """
        parsed = urlparse(self.path)

        if parsed.path == "/connections":
            if not self._check_auth():
                return
            cookies = load_cookies()
            if not cookies:
                self._send_json({"error": "No cookies found, please POST /login-linkedin first."}, 401)
                return

            qs = parse_qs(parsed.query)
            page = int(qs.get("page", [1])[0])
            size = int(qs.get("size", [10])[0])
            start = (page - 1) * size

            raw_json = voyager_get_connections(cookies, start=start, count=size)
            if "error" in raw_json:
                self._send_json(raw_json, raw_json.get("status_code", 500))
            else:
                parsed_data = parse_connections(raw_json)
                result = {
                    "page": page,
                    "size": size,
                    "connections": parsed_data
                }
                self._send_json(result, 200)
        else:
            self._send_json({"error": "Not found"}, 404)


def run_server(host=HOST, port=PORT):
    httpd = HTTPServer((host, port), LinkedInRequestHandler)
    print(f"Server running on http://{host}:{port}")
    print("Endpoints:")
    print("  POST /login-linkedin  => logs into LinkedIn via Selenium")
    print("  GET  /my-profile      => fetch user’s own profile from voyager")
    print("  GET  /connections?page=1&size=10 => fetch user's connections (paginated)")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
