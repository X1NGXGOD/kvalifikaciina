
import random
import re
import string
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from mntu_app.config import (
    AUTH_PATH,
    DEFAULT_SCHEDULE_PATH,
    LIB_BASE_URL,
    LIB_BASE_URL_HTTP,
    REQUEST_TIMEOUT,
    USER_AGENT,
)


class File:
    def __init__(self, name: str, url: str, is_file: bool):
        self.name = name
        self.url = url
        self.is_file = is_file
        self.is_folder = not is_file

    def __str__(self):
        return f"{'Folder' if self.is_folder else 'File'} {self.name} ({self.url})"


class IstuParser:
    def __init__(self):
        PHPSESSID = "".join(random.choices(string.ascii_lowercase, k=26))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.session.cookies.update({"PHPSESSID": PHPSESSID})

        self.base_url = LIB_BASE_URL_HTTP
        try:
            self.auth()
        except Exception:
            try:
                self.base_url = LIB_BASE_URL
                self.auth()
            except Exception as e:
                print(
                    f"[WARN] lib.istu.edu.ua: авторизація при старті не вдалася ({type(e).__name__}). "
                    "Розклад можна оновити пізніше, коли з’явиться мережа."
                )

    def auth(self):
        auth_url = self.base_url + AUTH_PATH
        post_data = "password_lib=powerpower&enter_lib=%D0%A3%D0%B2%D1%96%D0%B9%D1%82%D0%B8"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            r = self.session.post(auth_url, headers=headers, data=post_data, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if self.base_url.startswith("https"):
                self.base_url = LIB_BASE_URL_HTTP
                auth_url = self.base_url + AUTH_PATH
                try:
                    r = self.session.post(auth_url, headers=headers, data=post_data, timeout=REQUEST_TIMEOUT)
                    r.raise_for_status()
                except Exception:
                    raise e
            else:
                raise
        except Exception as e:
            print(f"[WARN] Не вдалося авторизуватися: {type(e).__name__}")

    def _make_url(self, current_page: str, href: str) -> str:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return urljoin(current_page, href)

    def parse_files(self, url: str = None):
        if not url:
            url = self.base_url + DEFAULT_SCHEDULE_PATH

        try:
            r = self.session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, features="lxml")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"[ERROR] Не вдалося підключитися до {url}: {type(e).__name__}")
            raise
        except Exception as e:
            print(f"[ERROR] Помилка при отриманні сторінки {url}: {type(e).__name__}")
            raise

        all_forms = soup.find_all("form", {"method": re.compile(r"post", re.I)})
        password_form = None
        for form in all_forms:
            password_input = form.find("input", {"name": "password_lib"})
            if password_input:
                password_form = form
                break

        if password_form:
            form_action = password_form.get("action", "")
            if not form_action or form_action.strip() == "":
                form_action = url

            post_data = {"password_lib": "powerpower"}

            submit_btn = password_form.find("input", {"name": "enter_lib"}) or password_form.find(
                "input", {"type": "submit"}
            )
            if submit_btn:
                submit_name = submit_btn.get("name", "")
                submit_value = submit_btn.get("value", "")
                if submit_name:
                    post_data[submit_name] = submit_value

            if not form_action.startswith("http"):
                form_action = self._make_url(url, form_action)

            r = self.session.post(form_action, data=post_data, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, features="lxml")

            soup.find(string=re.compile(r"правильний пароль|успішно", re.I))

            r = self.session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, features="lxml")

        result = []

        tables = soup.select(".forumline")
        if not tables:
            tables = soup.find_all("table")

        for tbl in tables:
            tbl_result = []
            for el in tbl.find_all("tr"):
                els = el.select("a[href]")
                if not els:
                    continue
                link = els[0]
                href = link.get("href") or ""
                name = (link.get_text() or "").strip()
                if not name and not href:
                    continue

                if name.lower() in [
                    "дізнатись пароль",
                    "дiзнатись пароль",
                    "увійти",
                    "вхід",
                    "оновіть сторінку",
                    "оновити сторінку",
                ]:
                    continue

                if not name or not href or href == "#" or href.startswith("javascript:"):
                    continue
                full_url = self._make_url(url, href)

                els_img = el.select("img")
                is_file = False
                if els_img:
                    img_src = (els_img[0].get("src") or "").lower()
                    is_file = "folder" not in img_src and "dir" not in img_src
                else:
                    is_file = name.lower().endswith((".pdf", ".docx")) or href.lower().endswith((".pdf", ".docx"))

                if is_file and (name.lower().endswith((".pdf", ".docx")) or href.lower().endswith((".pdf", ".docx"))):
                    tbl_result.append(File(name, full_url, True))
                elif not is_file and href and "id_f=" in href:
                    tbl_result.append(File(name, full_url, False))
                elif not is_file and name:
                    tbl_result.append(File(name, full_url, False))

            if tbl_result:
                result = tbl_result
                break

        return result


_parser: Optional[IstuParser] = None
_parser_warned = False


def reset_parser():
    global _parser, _parser_warned
    _parser = None
    _parser_warned = False


def get_parser() -> Optional[IstuParser]:
    global _parser, _parser_warned
    if _parser is not None:
        return _parser
    try:
        _parser = IstuParser()
        return _parser
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, OSError) as e:
        if not _parser_warned:
            _parser_warned = True
            print("[WARN] lib.istu.edu.ua недоступний (перевірте інтернет або VPN):", e)
        return None
