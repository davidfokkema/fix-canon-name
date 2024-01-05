import re

from selenium import webdriver
from selenium.webdriver.common.by import By

PASSWORD = "1234"

RE_NAME = "(?P<name>.*?) \([0-9a-f:]{8}\)"

options = webdriver.FirefoxOptions()
# options.add_argument("--headless")
options.accept_insecure_certs = True
with webdriver.Firefox(options=options) as driver:
    driver.get("https://canoncfcad9.local./login.html")
    driver.find_element(By.ID, "i0012A").click()
    driver.find_element(By.ID, "i2101").send_keys(PASSWORD)
    driver.find_element(By.ID, "submitButton").click()

    driver.get("https://canoncfcad9.local./m_network_airprint_edit.html")
    name_element = driver.find_element(By.ID, "i2072")
    current_name = name_element.get_attribute("value")
    printer_name = re.match(RE_NAME, current_name).group("name")
    name_element.clear()
    name_element.send_keys(printer_name)
    driver.find_element(By.ID, "submitButton").click()
