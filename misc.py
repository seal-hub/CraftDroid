import traceback
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


def teardown_mail(driver):
    print('misc.py::teardown_mail()')
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located(
            (By.XPATH, '//android.widget.TextView[contains(@text, "You got here")]')))
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@content-desc="Navigate up"]')))
        el1 = driver.find_element_by_accessibility_id("Navigate up")
        el1.click()
        el1 = driver.find_element_by_xpath("//*[@text='uci.seal@gmail.com']")
        el1.click()
        driver.swipe(400, 1600, 400, 600, 400)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//android.widget.TextView[@text="Sign Out"]')))
        el2 = driver.find_element_by_xpath('//android.widget.TextView[@text="Sign Out"]')
        el2.click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//android.widget.Button[@text="OK"]')))
        el3 = driver.find_element_by_xpath('//android.widget.Button[@text="OK"]')
        el3.click()
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//android.widget.TextView[@text="other mail"]')))
    except:
        print('misc.py::something wrong when teardown')
        traceback.print_exc()
        pass