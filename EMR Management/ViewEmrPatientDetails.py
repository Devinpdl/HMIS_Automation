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
screenshot_dir = os.path.join("screenshots", "emr_view")
report_dir = os.path.join("reports", "emr_view")
patient_json_dir = os.path.join(report_dir, "patient_ids")
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)
os.makedirs(patient_json_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class ViewEMRPatientDetails(unittest.TestCase):
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
        self.__take_screenshot("LOGIN_SUCCESS")

    def test_view_emr_patient_details(self):
        """
        Main test method: Navigate to EMR patient view, select a patient, and perform automation on patient details page.
        """
        # Navigate to View Emergency Patients page
        self.wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@id='patient_menu']/a"))).click()
        self.wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[@href='http://lunivacare.ddns.net:8080/himsnew/patient/view_emergency']"))).click()
        logging.info("Navigated to View Emergency Patients page")
        self.__take_screenshot("VIEW_EMERGENCY_PATIENTS_PAGE")

        # Wait for patient table to load
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//table[@id='patientTable']")))
        logging.info("Patient table loaded")

        # Click on the first patient's View button
        try:
            view_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//table[@id='patientTable']//tbody//tr[1]//a[contains(@class, 'btn-info') and contains(@href, 'emergency_patient_details')]")))
            patient_href = view_btn.get_attribute("href")
            logging.info(f"Found patient details link: {patient_href}")
            view_btn.click()
            logging.info("Clicked on View button for first patient")
            self.__take_screenshot("CLICKED_VIEW_BUTTON")
        except TimeoutException:
            logging.error("Could not find or click the View button for the first patient")
            self.__take_screenshot("VIEW_BUTTON_ERROR")
            raise

        # Wait for patient details page to load
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'ibox-title') and contains(., 'Patient Detail')]")))
        logging.info("Patient details page loaded")
        self.__take_screenshot("PATIENT_DETAILS_PAGE")

        # Extract patient ID from URL
        current_url = self.driver.current_url
        logging.info(f"Current URL: {current_url}")
        patient_id_match = re.search(r'/emergency_patient_details/\?q=.*?(\d+)', current_url)
        if patient_id_match:
            self.patient_id = patient_id_match.group(1)
            logging.info(f"Extracted Patient ID: {self.patient_id}")
        else:
            logging.warning("Could not extract patient ID from URL")

        # Click on the collapse link to expand patient details
        try:
            collapse_link = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@class='collapse-link']//i[@class='fa fa-chevron-down']")))
            collapse_link.click()
            logging.info("Clicked on collapse link to expand patient details")
            self.__take_screenshot("COLLAPSE_LINK_CLICKED")
        except TimeoutException:
            logging.warning("Could not find or click the collapse link")
            self.__take_screenshot("COLLAPSE_LINK_ERROR")

        # Perform additional automation as needed
        # For example, filling in some form fields if they exist
        try:
            # Example: Fill in a diagnosis field if it exists
            diagnosis_field = self.driver.find_element(By.ID, "diagnosis")
            diagnosis_field.clear()
            diagnosis_field.send_keys("Emergency case - observation")
            logging.info("Filled in diagnosis field")
            self.__take_screenshot("DIAGNOSIS_FIELD_FILLED")
        except Exception:
            logging.info("Diagnosis field not found, continuing...")

        # Example: Click on a save or update button if it exists
        try:
            save_btn = self.driver.find_element(By.XPATH, "//button[@type='submit' and contains(text(), 'Save')]")
            save_btn.click()
            logging.info("Clicked Save button")
            self.__take_screenshot("SAVE_BUTTON_CLICKED")
            
            # Handle success notification if it appears
            try:
                notification = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH,
                        "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')]"
                    ))
                )
                logging.info("Save operation successful")
                self.__take_screenshot("SAVE_SUCCESS")
            except TimeoutException:
                logging.info("No success notification appeared after save")
        except Exception:
            logging.info("Save button not found, continuing...")

        # Optionally add to test description for better XML reporting (appears in test doc)
        if self.patient_id:
            self._testMethodDoc = f"Patient ID: {self.patient_id}"

    def __take_screenshot(self, name):
        """
        Take a screenshot for debugging purposes.
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
    unittest.main(
        testRunner=xmlrunner.XMLTestRunner(output=report_dir, verbosity=2),
        failfast=False, buffer=False, catchbreak=False
    )