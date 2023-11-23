from appium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from appium.webdriver.common.appiumby import AppiumBy as MobileBy
from appium.webdriver.common.touch_action import TouchAction
from appium.options.android import UiAutomator2Options
from selenium.common.exceptions import NoSuchElementException
import time
import re
import subprocess
# local import
from Databank import Databank
from misc import teardown_mail
from StrUtil import StrUtil


class Runner:
    def __init__(self, pkg, act, no_reset=False, appium_port='4723', udid=None):
        desired_caps = Runner.set_caps(pkg, act, no_reset, udid)
        capabilities_options = UiAutomator2Options().load_capabilities(desired_caps)
        self.driver = webdriver.Remote(command_executor='http://localhost:' + appium_port, options=capabilities_options)
        self.databank = Databank()
        self.act_interval = 2

    @staticmethod
    def set_caps(app_name, app_activity, no_reset=False, udid=None):
        caps = {
            'platformName': 'Android',
            'automationName': 'uiautomator2',
            'platformVersion': '6.0',
            'deviceName': 'Android',
            'appPackage': app_name,
            'appActivity': app_activity,
            'autoGrantPermissions': True,
            'noReset': no_reset
        }
        if udid:
            caps['udid'] = udid
        return caps

    def perform_actions(self, action_list, require_wait=False, reset=True, cgp=None):
        if reset:
            if self.driver.desired_capabilities['desired']['noReset']:
                # self.driver.launch_app() is deprecated
                self.driver.activate_app(app_id=self.driver.desired_capabilities['appPackage'])  # don't clear app data
            else:
                # self.driver.reset() is deprecated
                self.driver.terminate_app(app_id=self.driver.desired_capabilities['appPackage'])
                subprocess.run(f"adb shell pm clear {self.driver.desired_capabilities['appPackage']}".split(),
                                stdout=subprocess.DEVNULL)
                self.driver.activate_app(app_id=self.driver.desired_capabilities['appPackage'])
        #time.sleep(self.act_interval)

        # specific for Ru email apps: a43-a45
        # if len(action_list) > 1:
        #     for a in action_list:
        #         if a['resource-id'].split('/')[-1] in ['sign_in', 'accept_button', 'welcome_done', 'subject']:
        #             teardown_mail(self.driver)
        #             break

        '''
        # specific for Etsy app (w/ two different staring screens)
        found = False
        while not found:
            try:
                driver.find_element_by_xpath('//android.widget.Button[@text="Get Started"]')
                found = True
            except:
                print('Exception: required btn not found')
                driver.reset()
                time.sleep(act_interval)
        '''

        is_for_confirm = False
        # specific for Yelp app. Cancel the pop-up dialog
        # try:
        #     ele = self.driver.find_element_by_id('com.yelp.android:id/toolbar')
        #     ele.click()
        # except:
        #     pass
        for i, action in enumerate(action_list):
            time.sleep(self.act_interval)
            # print(f'doing action: {action}')
            # print(driver.page_source)
            # if the action is SYS_EVENT, no need to get the element
            if action['class'] == 'SYS_EVENT':
                if action['action'][0] == 'sleep':
                    time.sleep(action['action'][1])
                elif action['action'][0] == 'KEY_BACK':
                    self.driver.press_keycode(4)  # AndroidKeyCode for 'Back'
                elif action['action'][0] == 'restart_app':
                    self.driver.activate_app(self.driver.desired_capabilities['appPackage'])
                else:
                    assert False, 'Unknown SYS_EVENT'
                continue

            if action['class'] == 'EMPTY_EVENT':
                continue

            self.hide_keyboard()
            # if the action is WAIT_UNTIL, no need to get the element
            if action['action'][0].startswith('wait_until'):
                # e.g., ["wait_until_element_presence", 10, "xpath", "//android.widget.TextView[@text='Sample Todo']"]
                # e.g., ["wait_until_element_invisible", 10, "xpath", "//android.widget.TextView[@text='Sample Todo']"]
                # e.g., ["wait_until_text_presence", 10, "text", "65.09"]
                # e.g., ["wait_until_text_invisible", 10, "text", "Sample Todo"]
                wait_time, selector_type, selector = action['action'][1:]
                locator = None
                if selector_type == 'xpath':
                    locator = (MobileBy.XPATH, selector)
                elif selector_type == 'content-desc':
                    locator = (MobileBy.ACCESSIBILITY_ID, selector)
                elif selector_type == 'id':
                    locator = (MobileBy.ID, selector)
                elif selector_type == 'text':
                    locator = (MobileBy.XPATH, f'//*[contains(@text, "{selector}")]')
                else:
                    assert locator, "Unknown selector type"
                try:
                    if action['action'][0].endswith('presence'):
                        WebDriverWait(self.driver, wait_time).until(EC.presence_of_element_located(locator))
                    elif action['action'][0].endswith('invisible'):
                        WebDriverWait(self.driver, wait_time).until(EC.invisibility_of_element_located(locator))
                    else:
                        assert False, "Unknown WAIT_UNTIL action"
                except Exception as excep:
                    print('Exception in wait_until')
                    print(excep)
                    print(action)
                    print(locator)
                    print(self.driver.page_source)
                    assert False, "Failed WAIT_UNTIL action"
                continue

            # action performed on the selected element
            ele = self.get_web_element(action)
            act_from = self.get_current_package() + self.get_current_activity()
            if ele:
                if action['action'][0] == 'click':
                    # specific corner case for Yelp: click the right part
                    if 'activity_login_create_account_question' in action['resource-id']\
                            and action['text'] == "Don't have a Yelp account yet? Sign up.":
                        rect = ele.rect
                        x = rect['x'] + (0.8 * rect['width'])
                        y = rect['y'] + (0.5 * rect['height'])
                        self.driver.tap([(x, y)])
                    else:
                        ele.click()
                elif 'send_keys' in action['action'][0]:
                    value_for_input = action['action'][1]
                    # if sending email (for registration), get a new one
                    if StrUtil.is_contain_email(value_for_input) and value_for_input != self.databank.get_login_email():
                        if is_for_confirm:
                            value_for_input = self.databank.get_temp_email(renew=False)
                        else:
                            value_for_input = self.databank.get_temp_email()
                            is_for_confirm = True
                    # all possible cases: 'clear_and_send_keys', 'clear_and_send_keys_and_hide_keyboard',
                    # 'send_keys_and_hide_keyboard', 'send_keys_and_enter', 'send_keys'
                    if action['action'][0].startswith('clear'):
                        ele.clear()
                    ele.send_keys(value_for_input)
                    if action['action'][0].endswith('hide_keyboard'):
                        ele.click()
                        time.sleep(self.act_interval/2)
                        self.hide_keyboard()
                    elif action['action'][0].endswith('enter'):
                        self.driver.press_keycode(66)  # AndroidKeyCode for 'Enter'
                # elif action['action'][0] == 'clear_and_send_keys':
                #     ele.clear()
                #     ele.send_keys(action['action'][1])
                # elif action['action'][0] == 'clear_and_send_keys_and_hide_keyboard':
                #     ele.clear()
                #     ele.send_keys(action['action'][1])
                #     ele.click()
                #     self.hide_keyboard()
                # elif action['action'][0] == 'send_keys_and_hide_keyboard':
                #     ele.send_keys(action['action'][1])
                #     ele.click()
                #     self.hide_keyboard()
                # elif action['action'][0] == 'send_keys_and_enter':
                #     ele.send_keys(action['action'][1])
                #     self.driver.press_keycode(66)  # AndroidKeyCode for 'Enter'
                # elif 'send_keys' in action['action'][0]:  # 'send_keys', 'clear_and_send_keys'
                #     # if sending email (for registration), get a new one
                #     if StrUtil.is_contain_email(action['action'][1]) \
                #             and action['action'][1] != self.databank.get_login_email():
                #         if is_for_confirm:
                #             ele.send_keys(self.databank.get_temp_email(renew=False))
                #         else:
                #             ele.send_keys(self.databank.get_temp_email())
                #             is_for_confirm = True
                #     else:
                #         ele.send_keys(action['action'][1])
                elif action['action'][0] == 'swipe_right':
                    rect = ele.rect  # e.g., {'x': 202, 'y': 265, 'width': 878, 'height': 57}
                    start_x, start_y, end_x, end_y = rect['x'] + rect['width'] / 4, rect['y'] + rect['height'] / 2, \
                                                     rect['x'] + rect['width'] * 3 / 4, rect['y'] + rect['height'] / 2
                    self.driver.swipe(start_x, start_y, end_x, end_y, 500)
                elif action['action'][0] == 'long_press':
                    ta = TouchAction(self.driver)
                    ta.long_press(ele).perform()
                else:
                    assert False, "Unknown action to be performed"
                act_to = self.get_current_package() + self.get_current_activity()
                if action['action'][0] in ['click', 'long_press'] and cgp:
                    cgp.add_edge(act_from, act_to, action)

        if require_wait:
            time.sleep(self.act_interval*2)
        else:
            # time.sleep(self.act_interval/2)
            time.sleep(self.act_interval)

    def get_web_element(self, action):
        ele = None
        try:
            xpath = None
            if action['resource-id']:
                if 'id-prefix' in action and '/' not in action['resource-id']:  # for running actions when exploring
                    rid = action['id-prefix'] + action['resource-id']
                else:
                    rid = action['resource-id']  # for running actions load from test file
                elements = self.driver.find_elements(MobileBy.ID, rid)
                if elements:
                    ele = elements[0]
                    if len(elements) > 1:
                        if action['text'] or action['content-desc']:
                            attr = 'text' if action['text'] else 'content-desc'
                            xpath = f'//{action["class"]}[contains(@{attr}, "{action[attr]}") ' \
                                f'and @resource-id="{rid}"]'
                            ele = self.driver.find_element(MobileBy.XPATH, xpath)
            elif action['content-desc']:
                xpath = '//' + action['class'] + '[@content-desc="' + action['content-desc'] + '"]'
                WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((MobileBy.XPATH, xpath)))
                ele = self.driver.find_element(MobileBy.XPATH, xpath)
            elif action['text']:
                xpath = '//' + action['class'] + '[@text="' + action['text'] + '"]'
                ele = self.driver.find_element(MobileBy.XPATH, xpath)
            elif action['naf']:  # "naf" is either "true" or ""; a32-a33-b31
                xpath = '//' + action['class'] + '[@NAF="true"]'
                ele = self.driver.find_element(MobileBy.XPATH, xpath)
            # elif action['password'] == 'true':  # corner case for the password field in Target app registration
            #     xpath = '//' + action['class'] + '[@password="true"]'
            #     ele = self.driver.find_element(MobileBy.XPATH, xpath)
            else:
                assert False, "No attribute to locate widgets"
        except Exception as excep:
            print('Exception in get_web_element')
            print(excep)
            print(action)
            if xpath:
                print(xpath)
            print(self.driver.page_source)
        return ele

    # def check_invisible(self, act):
    #     # e.g., 'action': ['wait_until_element_invisible', 10, 'xpath', '//android.widget.TextView[@text=\"Sample Todo\"]'
    #     wait_time, selector_type, selector = act['action'][1:]
    #     assert selector_type == 'xpath'
    #     try:
    #         WebDriverWait(self.driver, wait_time).until(EC.invisibility_of_element_located((MobileBy.XPATH, selector)))
    #         return True
    #     except:
    #         return False

    # def check_text_presence(self, act):
    #     # e.g., ["wait_until_text_presence", 10, "text", "65.09"]
    #     wait_time, selector_type, selector = act['action'][1:]
    #     assert selector_type == 'text'
    #     try:
    #         WebDriverWait(self.driver, wait_time).until(
    #             EC.presence_of_element_located((MobileBy.XPATH, f'//*[contains(@text, "{selector}")]')))
    #         return True
    #     except:
    #         return False

    def check_text_invisible(self, act):
        # e.g., ["wait_until_text_invisible", 10, "text", "Sample Todo"]
        wait_time, selector_type, selector = act['action'][1:]
        assert selector_type == 'text'
        try:
            WebDriverWait(self.driver, wait_time).until(
                EC.invisibility_of_element_located((MobileBy.XPATH, f'//*[contains(@text, "{selector}")]')))
            return True
        except:
            return False

    def get_current_activity(self):
        return self.driver.current_activity

    def get_page_source(self):
        self.hide_keyboard()
        return self.driver.page_source

    def get_current_package(self):
        return self.driver.current_package

    def hide_keyboard(self):
        if self.driver.is_keyboard_shown:
            try:
                self.driver.hide_keyboard()
            except WebDriverException:
                pass

    # def is_waited_element_present(self, event):
    #     wait_time, selector_type, selector = event['action'][1:]
    #     locator = None
    #     if selector_type == 'xpath':
    #         locator = (MobileBy.XPATH, selector)
    #     elif selector_type == 'content-desc':
    #         locator = (MobileBy.ACCESSIBILITY_ID, selector)
    #     elif selector_type == 'id':
    #         locator = (MobileBy.ID, selector)
    #     else:
    #         assert locator, "Unknown selector type"
    #     try:
    #         WebDriverWait(self.driver, wait_time).until(EC.presence_of_element_located(locator))
    #         return True
    #     except:
    #         return False

    # @staticmethod
    # def clear_browser_data(self):
    #     # specific for Target app (register through website;
    #     # need to clear registered data when restarting app)
    #     subprocess.call(['adb', 'shell', 'pm', 'clear', 'com.android.browser'])
    #     print('Cleared browser data')
