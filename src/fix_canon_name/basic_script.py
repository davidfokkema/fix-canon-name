import re
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

PASSWORD = "1234"

OLD_NAME = "Canon LBP622C/623C Printer (a0:1b:23)"
NUM_CHARS = 15
RE_NAME = "(?P<name>.*?) \([0-9a-f:]{8}\)"

options = webdriver.FirefoxOptions()
options.add_argument("--headless")
options.accept_insecure_certs = True
t0 = time.monotonic()
with webdriver.Firefox(options=options) as driver:
    driver.get("http://Canoncfcad9.local:80/airprint.html")
    driver.find_element(By.XPATH, "//input[@type='password']").send_keys(PASSWORD)
    driver.find_element(By.ID, "submitButton").click()

    element = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, "//input[contains(@value, 'Edit')]"))
    )
    element.click()

    name_element = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located(
            (By.XPATH, f"//input[starts-with(@value, '{OLD_NAME[:NUM_CHARS]}')]")
        )
    )
    current_name = name_element.get_attribute("value")
    if match := re.match(RE_NAME, current_name):
        printer_name = match.group("name")
        print(f"Changing name from {current_name} to {printer_name}...")
        name_element.clear()
        name_element.send_keys(printer_name)
        driver.find_element(By.ID, "submitButton").click()

    print(f"Changing name took {time.monotonic() - t0:.1f} s.")
