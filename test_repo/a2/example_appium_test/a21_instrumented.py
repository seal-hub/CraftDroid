from appium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import os
import sys

# local import
from Util import Util
from WidgetUtil import WidgetUtil

desired_caps = {
    'platformName': 'Android',
    'platformVersion': '6.0',
    'deviceName': 'Android Emulator',
    'appPackage': "com.rubenroy.minimaltodo",
    'appActivity': "com.rubenroy.minimaltodo.MainActivity",
    'autoGrantPermissions': True,
    'noReset': False
}
driver = webdriver.Remote('http://localhost:4723/wd/hub', desired_caps)
driver.implicitly_wait(5)

tid = os.path.basename(__file__).split('.')[0]
actions = []

el1 = driver.find_element_by_id("com.rubenroy.minimaltodo:id/addToDoItemFAB")
attrs = WidgetUtil.get_attrs(driver.page_source, 'resource-id', 'com.rubenroy.minimaltodo:id/addToDoItemFAB')
actions.append(Util.compose(attrs, tid, ['click'], driver.current_package, driver.current_activity, 'gui'))
el1.click()

el2 = driver.find_element_by_id("com.rubenroy.minimaltodo:id/userToDoEditText")
attrs = WidgetUtil.get_attrs(driver.page_source, 'resource-id', 'com.rubenroy.minimaltodo:id/userToDoEditText')
actions.append(Util.compose(attrs, tid, ['send_keys_and_hide_keyboard', 'Sample Todo'],
                            driver.current_package, driver.current_activity, 'gui'))
el2.send_keys("Sample Todo")
driver.press_keycode(4)  # AndroidKeyCode for 'Back'

el3 = driver.find_element_by_id("com.rubenroy.minimaltodo:id/makeToDoFloatingActionButton")
attrs = WidgetUtil.get_attrs(driver.page_source, 'resource-id', 'com.rubenroy.minimaltodo:id/makeToDoFloatingActionButton')
actions.append(Util.compose(attrs, tid, ['click'], driver.current_package, driver.current_activity, 'gui'))
el3.click()

WebDriverWait(driver, 10).until(EC.presence_of_element_located(
    (By.XPATH, '//android.widget.TextView[@text="Sample Todo"]')))
attrs = WidgetUtil.get_attrs(driver.page_source, 'text', 'Sample Todo', 'android.widget.TextView')
actions.append(Util.compose(attrs, tid,
                            ['wait_until_element_presence', 10, 'xpath', '//android.widget.TextView[@text="Sample Todo"]'],
                            driver.current_package, driver.current_activity, 'oracle'))

Util.save_aug_events(actions, f'{tid}.json')
