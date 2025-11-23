import os
import sys
# Add the parent directory (Hims_Automation) to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
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
screenshot_dir = os.path.join("screenshots", "emr_registration")
report_dir = os.path.join("reports", "emr_registration")
patient_json_dir = os.path.join(report_dir, "patient_ids")  # Folder for storing individual patient JSON files
bill_nos_dir = os.path.join(report_dir, "bill_nos")  # Folder for storing individual bill number JSON files
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)
os.makedirs(patient_json_dir, exist_ok=True)
os.makedirs(bill_nos_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class EMRRegistration(unittest.TestCase):
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
        self.bill_no = None

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

    def test_emr_registration(self):
        """
        Main test method: Navigate to EMR registration, fill form, handle modals, submit, and capture patient ID.
        """
        # Navigate directly to Emergency registration URL
        self.driver.get("http://lunivacare.ddns.net:8080/himsnew/ipd/register/Emergency")
        self.wait.until(EC.presence_of_element_located((By.ID, "mobile-number")))
        logging.info("Navigated to EMR Registration page")
        # self.__take_screenshot("EMR_REGISTER_PAGE")  # Uncomment for debugging

        mobile_field = self.wait.until(EC.presence_of_element_located((By.ID, "mobile-number")))
        mobile_field.send_keys("9800000002")
        logging.info("Entered mobile number")
        # self.__take_screenshot("MOBILE_ENTERED")  # Uncomment for debugging
        time.sleep(2)  # Brief pause to allow modal to appear if needed
        self.__handle_duplicate_patient_modal()

        Select(self.driver.find_element(By.ID, "designation")).select_by_value("Mr.")
        self.driver.find_element(By.ID, "first-name").send_keys("Jane")
        self.driver.find_element(By.ID, "last-name").send_keys("Smith")
        self.driver.find_element(By.ID, "age").send_keys("25")
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
            logging.info("EMR registration successful")
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
        Capture patient ID and bill number by clicking the Print Bill button and extracting from the print window.
        """
        try:
            # Wait for the page to load and try multiple approaches to find the Print Bill button
            time.sleep(3)  # Give the page some time to fully load
            
            # Try multiple XPaths to find the Print Bill button
            print_bill_btn = None
            xpaths_to_try = [
                "//*[text()='Print Bill']",
                "//button[contains(text(), 'Print Bill')]",
                "//button[text()='Print Bill']",
                "//*[contains(text(), 'Print Bill')]",
                "//*[contains(@class, 'btn') and contains(text(), 'Print Bill')]"
            ]
            
            for xpath in xpaths_to_try:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    if elements:
                        for element in elements:
                            if element.is_displayed() and element.is_enabled():
                                print_bill_btn = element
                                logging.info(f"Found Print Bill button using XPath: {xpath}")
                                break
                        if print_bill_btn:
                            break
                except Exception as e:
                    logging.debug(f"XPath {xpath} failed: {str(e)}")
                    continue
            
            if not print_bill_btn:
                # Try to find any button and check its text
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for button in buttons:
                    try:
                        text = button.text.strip()
                        if text == "Print Bill":
                            print_bill_btn = button
                            logging.info("Found Print Bill button by iterating through all buttons")
                            break
                    except:
                        continue
            
            if not print_bill_btn:
                raise TimeoutException("Print Bill button not found")
                
            logging.info("Found Print Bill button")
            self.__take_screenshot("PRINT_BILL_BUTTON_FOUND")
            
            # Scroll to the button and click it
            self.driver.execute_script("arguments[0].scrollIntoView(true);", print_bill_btn)
            time.sleep(1)
            print_bill_btn.click()
            logging.info("Clicked Print Bill button")
            
            # Wait for new window to open
            main_window = self.driver.current_window_handle
            WebDriverWait(self.driver, 20).until(lambda d: len(d.window_handles) > 1)
            logging.info("Print window opened")
            
            # Switch to the print window
            for window_handle in self.driver.window_handles:
                if window_handle != main_window:
                    self.driver.switch_to.window(window_handle)
                    break
            
            # Wait for print page to load
            time.sleep(3)
            logging.info("Switched to print window")
            self.__take_screenshot("PRINT_WINDOW")
            
            # Extract patient ID and bill number from the print page
            patient_id = None
            bill_no = None
            
            try:
                # Extract patient ID from the patient info section
                patient_id_element = self.driver.find_element(By.XPATH, "//strong[contains(text(), 'Patient Id:')]")
                patient_id_text = patient_id_element.text
                patient_id_match = re.search(r'Patient Id:\s*(\d+)', patient_id_text)
                if patient_id_match:
                    patient_id = patient_id_match.group(1)
                    logging.info(f"Extracted Patient ID: {patient_id}")
                else:
                    logging.warning("Could not extract Patient ID from text: " + patient_id_text)
            except Exception as e:
                logging.warning(f"Could not extract Patient ID: {str(e)}")
            
            try:
                # Extract bill number from the bill info section
                bill_no_element = self.driver.find_element(By.XPATH, "//strong[contains(text(), 'Bill No:')]")
                bill_no_text = bill_no_element.text
                bill_no_match = re.search(r'Bill No:\s*I?0*(\d+)', bill_no_text)
                if bill_no_match:
                    bill_no = bill_no_match.group(1)
                    logging.info(f"Extracted Bill No: {bill_no}")
                else:
                    logging.warning("Could not extract Bill No from text: " + bill_no_text)
            except Exception as e:
                logging.warning(f"Could not extract Bill No: {str(e)}")
            
            # Close the print window
            self.driver.close()
            self.driver.switch_to.window(main_window)
            logging.info("Closed print window and switched back to main window")
            
            # Store the patient ID for saving to JSON
            if patient_id:
                self.patient_id = patient_id
            
            # For EMR registration, we're primarily interested in the patient ID
            if not patient_id:
                raise ValueError("Patient ID not captured")
                
            # Store the bill_no for saving to JSON
            self.bill_no = bill_no
            
            return patient_id
            
        except Exception as e:
            logging.error(f"Error capturing patient ID and bill info: {str(e)}")
            self.__take_screenshot("CAPTURE_PATIENT_ID_ERROR")
            
            # Fallback to URL extraction method
            logging.info("Trying fallback URL extraction method")
            main_window = self.driver.current_window_handle
            if len(self.driver.window_handles) > 1:
                # Switch to the last window if it exists
                self.driver.switch_to.window(self.driver.window_handles[-1])
                url = self.driver.current_url
                self.driver.close()
                self.driver.switch_to.window(main_window)
            else:
                url = self.driver.current_url
                
            match = re.search(r'/create_stiker/(\d+)', url)
            if match:
                patient_id = match.group(1)
                self.patient_id = patient_id
                logging.info(f"Fallback - Extracted Patient ID from URL: {patient_id}")
                return patient_id
            else:
                raise ValueError(f"Patient ID not captured using fallback method. URL: {url}")

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
        Test-level teardown: Save patient ID and bill number to separate JSON files if captured.
        Each patient ID is stored in a file named as ID.json
        Each bill number is stored in a file named as BILLNO.json
        """
        # Save patient ID to JSON file
        if self.patient_id:
            json_file = os.path.join(patient_json_dir, f"{self.patient_id}.json")
            data = {
                "patient_id": self.patient_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(json_file, "w") as f:
                json.dump(data, f, indent=4)
            logging.info(f"Patient ID {self.patient_id} saved to {json_file}")
        
        # Save bill number to JSON file
        if self.bill_no:
            bill_json_file = os.path.join(bill_nos_dir, f"{self.bill_no}.json")
            bill_data = {
                "bill_no": self.bill_no,
                "patient_id": self.patient_id if hasattr(self, 'patient_id') and self.patient_id else "unknown",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(bill_json_file, "w") as f:
                json.dump(bill_data, f, indent=4)
            logging.info(f"Bill No {self.bill_no} saved to {bill_json_file}")

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