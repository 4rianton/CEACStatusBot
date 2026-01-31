import os
import requests
from bs4 import BeautifulSoup
import time

from CEACStatusBot.captcha import CaptchaHandle, OnnxCaptchaHandle

def query_status(location, application_num, passport_number, surname, captchaHandle: CaptchaHandle = OnnxCaptchaHandle("captcha.onnx")):
    failCount = 0
    result = {
        "success": False,
    }
    backupTime = 5
    debug_html = os.getenv("CEAC_DEBUG_HTML", "").strip().lower() in {"1", "true", "yes", "y", "on"}

    def dump_debug(label: str, html_text: str) -> None:
        if not debug_html:
            return
        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        path = f"ceac_debug_{label}_{ts}.html"
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(html_text)
            print(f"Saved debug HTML to {path}")
        except Exception as exc:
            print(f"Failed to save debug HTML: {exc}")

    while failCount < 5:
        if failCount > 0:
            print(f"Retrying... Attempt {failCount + 1} / 5 in {backupTime} seconds")
            time.sleep(backupTime)
        failCount += 1
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en,zh-CN;q=0.9,zh;q=0.8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Host": "ceac.state.gov",
        }

        session = requests.Session()
        ROOT = "https://ceac.state.gov"

        try:
            r = session.get(url=f"{ROOT}/ceacstattracker/status.aspx?App=NIV", headers=headers)
        except Exception as e:
            print(e)
            continue

        soup = BeautifulSoup(r.text, features="lxml")

        # Find captcha image
        captcha = soup.find(name="img", id="c_status_ctl00_contentplaceholder1_defaultcaptcha_CaptchaImage")
        image_url = ROOT + captcha["src"]
        img_resp = session.get(image_url)

        # Resolve captcha
        captcha_num = captchaHandle.solve(img_resp.content)
        print(f"Captcha solved: {captcha_num}")

        # Find the correct value for the location dropdown
        location_dropdown = soup.find("select", id="Location_Dropdown")
        location_value = None
        for option in location_dropdown.find_all("option"):
            if location in option.text:
                location_value = option["value"]
                break

        if not location_value:
            print("Location not found in dropdown options.")
            return {"success": False}

        # Fill form
        def update_from_current_page(cur_page, name, data):
            ele = cur_page.find(name="input", attrs={"name": name})
            if ele:
                data[name] = ele["value"]

        data = {
            "ctl00$ToolkitScriptManager1": "ctl00$ContentPlaceHolder1$UpdatePanel1|ctl00$ContentPlaceHolder1$btnSubmit",
            "ctl00_ToolkitScriptManager1_HiddenField": ";;AjaxControlToolkit, Version=4.1.40412.0, Culture=neutral, PublicKeyToken=28f01b0e84b6d53e:en-US:acfc7575-cdee-46af-964f-5d85d9cdcf92:de1feab2:f9cec9bc:a67c2700:f2c8e708:8613aea7:3202a5a2:ab09e3fe:87104b7c:be6fb298",
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnSubmit",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": "8GJOG5GAuT1ex7KX3jakWssS08FPVm5hTO2feqUpJk8w5ukH4LG/o39O4OFGzy/f2XLN8uMeXUQBDwcO9rnn5hdlGUfb2IOmzeTofHrRNmB/hwsFyI4mEx0mf7YZo19g",
            "__VIEWSTATEGENERATOR": "DBF1011F",
            "__VIEWSTATEENCRYPTED": "",
            "ctl00$ContentPlaceHolder1$Visa_Application_Type": "NIV",
            "ctl00$ContentPlaceHolder1$Location_Dropdown": location_value,  # Use the correct value
            "ctl00$ContentPlaceHolder1$Visa_Case_Number": application_num,
            "ctl00$ContentPlaceHolder1$Captcha": captcha_num,
            "ctl00$ContentPlaceHolder1$Passport_Number": passport_number,
            "ctl00$ContentPlaceHolder1$Surname": surname,
            "LBD_VCID_c_status_ctl00_contentplaceholder1_defaultcaptcha": "a81747f3a56d4877bf16e1a5450fb944",
            "LBD_BackWorkaround_c_status_ctl00_contentplaceholder1_defaultcaptcha": "1",
            "__ASYNCPOST": "true",
        }

        fields_need_update = [
            "__VIEWSTATE",
            "__VIEWSTATEGENERATOR",
            "LBD_VCID_c_status_ctl00_contentplaceholder1_defaultcaptcha",
        ]
        for field in fields_need_update:
            update_from_current_page(soup, field, data)

        try:
            r = session.post(url=f"{ROOT}/ceacstattracker/status.aspx", headers=headers, data=data)
        except Exception as e:
            print(e)
            continue

        soup = BeautifulSoup(r.text, features="lxml")
        def _text(tag):
            return tag.get_text(strip=True) if tag else ""

        status_tag = soup.find("span", id="ctl00_ContentPlaceHolder1_ucApplicationStatusView_lblStatus")
        status = _text(status_tag)
        if not status:
            print("Status not found in response, retrying.")
            dump_debug("missing_status", r.text)
            continue

        app_num_tag = soup.find("span", id="ctl00_ContentPlaceHolder1_ucApplicationStatusView_lblCaseNo")
        application_num_returned = _text(app_num_tag)
        if not application_num_returned:
            print("Case number not found in response, retrying.")
            dump_debug("missing_case_number", r.text)
            continue
        if application_num_returned != application_num:
            print("Case number mismatch, retrying.")
            dump_debug("case_number_mismatch", r.text)
            continue

        visa_type_tag = soup.find("span", id="ctl00_ContentPlaceHolder1_ucApplicationStatusView_lblAppName")
        case_created_tag = soup.find("span", id="ctl00_ContentPlaceHolder1_ucApplicationStatusView_lblSubmitDate")
        case_last_updated_tag = soup.find("span", id="ctl00_ContentPlaceHolder1_ucApplicationStatusView_lblStatusDate")
        description_tag = soup.find("span", id="ctl00_ContentPlaceHolder1_ucApplicationStatusView_lblMessage")

        visa_type = _text(visa_type_tag)
        case_created = _text(case_created_tag)
        case_last_updated = _text(case_last_updated_tag)
        description = _text(description_tag)

        result.update({
            "success": True,
            "time": str(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())),
            "visa_type": visa_type,
            "status": status,
            "case_created": case_created,
            "case_last_updated": case_last_updated,
            "description": description,
            "application_num": application_num_returned,
            "application_num_origin": application_num
        })
        break

    return result
