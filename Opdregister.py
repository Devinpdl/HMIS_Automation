import os
import re
import time
import logging
import unittest
import json
import xmlrunner
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utilities.config_loader import ConfigLoader


# Folder configuration
screenshot_dir = os.path.join("screenshots", "opd_registration")
report_dir = os.path.join("reports", "opd_registration")
patient_json_dir = os.path.join(report_dir, "patient_ids")  # Folder for storing individual patient JSON files
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)
os.makedirs(patient_json_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class OPDRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Class-level setup: Load config, initialize WebDriver with options, and set up wait and credentials.
        """
        cls.config = ConfigLoader.load_credentials("staging")
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--enable-javascript")
        chrome_options.add_experimental_option("detach", True)
        chrome_options.add_experimental_option("excludeSwitches", ["disable-popup-blocking"])
        cls.driver = webdriver.Chrome(options=chrome_options)
        cls.driver.maximize_window()
        cls.wait = WebDriverWait(cls.driver, 20)
        cls.base_url = cls.config["base_url"]
        cls.valid_username = cls.config["username"]
        cls.valid_password = cls.config["password"]

    def setUp(self):
        """
        Test-level setup: Navigate to base URL, login, and initialize patient_id.
        """
        self.driver.get(self.base_url)
        self.__login()
        self.patient_id = None

    def __login(self):
        """
        Private method to handle login with explicit waits and logging.
        """
        username_field = self.wait.until(EC.presence_of_element_located((By.NAME, "Username")))
        password_field = self.driver.find_element(By.NAME, "Password")
        login_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        username_field.clear()
        password_field.clear()
        username_field.send_keys(self.valid_username)
        password_field.send_keys(self.valid_password)
        login_btn.click()
        self.wait.until(EC.url_contains("/dashboard"))
        logging.info("Login successful")
        # self.__take_screenshot("LOGIN_SUCCESS")  # Uncomment for debugging screenshots

    def test_opd_registration(self):
        """
        Main test method: Navigate to OPD registration, fill form, handle modals, submit, and capture patient ID.
        """
        self.wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@id='patient_menu']/a"))).click()
        self.wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[@href='http://lunivacare.ddns.net:8080/himsnew/ipd/register/OPD']"))).click()
        logging.info("Navigated to OPD Registration page")
        # self.__take_screenshot("OPD_REGISTER_PAGE")  # Uncomment for debugging

        mobile_field = self.wait.until(EC.presence_of_element_located((By.ID, "mobile-number")))
        mobile_field.send_keys("9800000001")
        logging.info("Entered mobile number")
        # self.__take_screenshot("MOBILE_ENTERED")  # Uncomment for debugging
        time.sleep(2)  # Brief pause to allow modal to appear if needed
        self.__handle_duplicate_patient_modal()

        Select(self.driver.find_element(By.ID, "designation")).select_by_value("Mr.")
        self.driver.find_element(By.ID, "first-name").send_keys("John")
        self.driver.find_element(By.ID, "last-name").send_keys("Doe")
        self.driver.find_element(By.ID, "age").send_keys("30")
        logging.info("Entered personal details")

        self.driver.find_element(By.XPATH, "//span[@id='select2-current-address-container']").click()
        search_field = self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@class='select2-search__field']")))
        search_field.send_keys("Kathmandu")
        self.wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//li[contains(@class, 'select2-results__option') and contains(text(), 'Kathmandu')]"))).click()
        logging.info("Selected address")
        # self.__take_screenshot("FORM_FILLED")  # Uncomment for debugging

        self.wait.until(EC.element_to_be_clickable((By.ID, "submitNewButton"))).click()
        logging.info("Form submitted")
        # self.__take_screenshot("FORM_SUBMITTED")  # Uncomment for debugging

        self.__handle_success_notification()
        self.patient_id = self.__capture_patient_id()
        logging.info(f"Captured Patient ID: {self.patient_id}")

        # Optionally add to test description for better XML reporting (appears in test doc)
        self._testMethodDoc = f"Patient ID: {self.patient_id}"

    def __handle_duplicate_patient_modal(self):
        """
        Handle potential duplicate patient modal after entering mobile number.
        Uses short timeout to avoid unnecessary waits.
        """
        modal_locator = (By.XPATH, "//h4[contains(.,'Patient Info')]")
        try:
            if self.driver.find_elements(*modal_locator):
                logging.info("Duplicate patient modal detected")
                # self.__take_screenshot("DUPLICATE_MODAL_PRESENT")  # Uncomment for debugging
                proceed_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.ID, "proceedToRegister")))
                self.driver.execute_script("arguments[0].click();", proceed_btn)
                logging.info("Clicked proceed button")
                # self.__take_screenshot("MODAL_HANDLED")  # Uncomment for debugging
                WebDriverWait(self.driver, 3).until(EC.invisibility_of_element_located(modal_locator))
        except TimeoutException:
            logging.info("No duplicate modal present")

    def __handle_success_notification(self):
        """
        Verify success notification after form submission and attempt to close it if possible.
        """
        try:
            notification = WebDriverWait(self.driver, 20).until(
                EC.visibility_of_element_located((By.XPATH,
                    "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')]"
                ))
            )
            logging.info("OPD registration successful")
            # self.__take_screenshot("SUCCESS_NOTIFICATION")  # Uncomment for debugging

            # Attempt to close notification gracefully
            try:
                close_btn = notification.find_element(By.CSS_SELECTOR, ".ui-pnotify-closer")
                self.driver.execute_script("arguments[0].click();", close_btn)
                WebDriverWait(self.driver, 5).until(EC.invisibility_of_element_located(notification))
            except Exception:
                logging.info("Notification auto-closed or close button not needed")
        except TimeoutException:
            # self.__take_screenshot("SUBMISSION_ERROR")  # Uncomment for debugging
            logging.error("Success notification not found")
            raise

    def __capture_patient_id(self):
        """
        Capture patient ID from either a new window or URL change after submission.
        Handles both scenarios robustly.
        """
        main_window = self.driver.current_window_handle
        WebDriverWait(self.driver, 20).until(
            lambda d: "create_stiker" in d.current_url or len(d.window_handles) > 1
        )
        if len(self.driver.window_handles) > 1:
            self.driver.switch_to.window(self.driver.window_handles[-1])
            patient_id = self.__extract_id_from_url(self.driver.current_url)
            self.driver.close()
            self.driver.switch_to.window(main_window)
        else:
            patient_id = self.__extract_id_from_url(self.driver.current_url)
        if not patient_id:
            raise ValueError("Patient ID not captured")
        # self.__take_screenshot("PATIENT_ID_CAPTURED")  # Uncomment for debugging
        return patient_id

    def __extract_id_from_url(self, url):
        """
        Extract patient ID from the 'create_stiker' URL using regex.
        """
        match = re.search(r'/create_stiker/(\d+)', url)
        if match:
            return match.group(1)
        raise ValueError(f"Patient ID not found in URL: {url}")

    def __take_screenshot(self, name):
        """
        Take a screenshot for debugging purposes. Commented out by default to avoid overhead.
        """
        filename = f"{screenshot_dir}/{name}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        try:
            self.driver.save_screenshot(filename)
            logging.info(f"Screenshot saved: {filename}")
        except Exception as e:
            logging.error(f"Error taking screenshot: {str(e)}")

    def tearDown(self):
        """
        Test-level teardown: Save patient ID to a separate JSON file if captured.
        Each patient ID is stored in a file named as ID.json
        """
        if self.patient_id:
            json_file = os.path.join(patient_json_dir, f"{self.patient_id}.json")
            data = {
                "patient_id": self.patient_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(json_file, "w") as f:
                json.dump(data, f, indent=4)
            logging.info(f"Patient ID {self.patient_id} saved to {json_file}")

    @classmethod
    def tearDownClass(cls):
        """
        Class-level teardown: Clean up extra browser windows, keeping the main one open.
        """
        logging.info("Cleaning up browser windows...")
        try:
            while len(cls.driver.window_handles) > 1:
                cls.driver.switch_to.window(cls.driver.window_handles[-1])
                cls.driver.close()
            cls.driver.switch_to.window(cls.driver.window_handles[0])
        finally:
            logging.info("Cleanup completed. Main window remains open.")


if __name__ == "__main__":
    unittest.main(0
        testRunner=xmlrunner.XMLTestRunner(output=report_dir, verbosity=2),
        failfast=False, buffer=False, catchbreak=False
    )