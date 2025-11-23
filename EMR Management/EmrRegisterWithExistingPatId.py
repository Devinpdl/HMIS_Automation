import os
import sys
# Add the parent directory of 'utilities' to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import time
import logging
import unittest
import json
import glob
import xmlrunner
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from utilities.config_loader import ConfigLoader


# Folder configuration
screenshot_dir = os.path.join("screenshots", "emr_registration_existing")
report_dir = os.path.join("reports", "emr_registration_existing")
patient_json_dir = os.path.join(report_dir, "patient_ids")  # Folder for storing individual patient JSON files
bill_nos_dir = os.path.join(report_dir, "bill_nos")  # Folder for storing individual bill number JSON files
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)
os.makedirs(patient_json_dir, exist_ok=True)
os.makedirs(bill_nos_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class EMRRegistrationWithExistingPatId(unittest.TestCase):
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
        Test-level setup: Navigate to base URL, login, and initialize patient_id and bill_no.
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

    def __get_latest_patient_id(self):
        """
        Get the latest patient ID from the patient_ids folders.
        Returns the most recent patient ID based on file modification time.
        """
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
            patient_id_dirs = [
                os.path.join(base_dir, 'opd_registration', 'patient_ids'),
                os.path.join(base_dir, 'opd_combined', 'patient_ids'),
                os.path.join(base_dir, 'emr_registration', 'patient_ids'),
                os.path.join(base_dir, 'emr_billing', 'patient_ids'),
                os.path.join(base_dir, 'emr_combined', 'patient_ids')
            ]
            
            # Log absolute paths for debugging
            for dir_path in patient_id_dirs:
                logging.info(f"Checking patient ID directory: {os.path.abspath(dir_path)}")
            
            # Check read permissions and directory existence
            json_files = []
            for dir_path in patient_id_dirs:
                if not os.path.exists(dir_path):
                    logging.warning(f"Directory does not exist: {dir_path}")
                    continue
                if not os.access(dir_path, os.R_OK):
                    logging.error(f"No read permission for directory: {dir_path}")
                    continue
                files = glob.glob(os.path.join(dir_path, "*.json"))
                json_files.extend(files)
                logging.info(f"Found {len(files)} JSON files in {dir_path}")
            
            if not json_files:
                logging.error("No patient ID files found in any patient_ids folder")
                raise ValueError("No patient ID files found in any patient_ids folder")
            
            # Find the most recent file
            latest_file = max(json_files, key=os.path.getmtime)
            logging.info(f"Latest patient ID file: {latest_file}")
            
            # Extract patient ID from filename (e.g., "2154.json" -> "2154")
            filename = os.path.basename(latest_file)
            patient_id = os.path.splitext(filename)[0]
            
            logging.info(f"Latest patient ID found: {patient_id}")
            return patient_id
            
        except Exception as e:
            logging.error(f"Error getting latest patient ID: {str(e)}")
            self.__take_screenshot("PATIENT_ID_RETRIEVAL_ERROR")
            raise

    def test_emr_registration_with_existing_pat_id(self):
        """
        Main test method: Navigate to EMR registration, use existing patient ID, 
        and submit to create a new EMR registration.
        """
        # Navigate directly to Emergency registration URL
        self.driver.get("http://lunivacare.ddns.net:8080/himsnew/ipd/register/Emergency")
        self.wait.until(EC.presence_of_element_located((By.ID, "getPatInfoById")))
        logging.info("Navigated to EMR Registration page")
        # self.__take_screenshot("EMR_REGISTER_PAGE")  # Uncomment for debugging

        # Get the latest patient ID from existing files
        self.patient_id = self.__get_latest_patient_id()
        logging.info(f"Using existing Patient ID: {self.patient_id}")

        # Enter Patient ID in the correct field and send Enter key
        patient_id_field = self.wait.until(EC.presence_of_element_located((By.ID, "getPatInfoById")))
        patient_id_field.clear()
        patient_id_field.send_keys(self.patient_id)
        patient_id_field.send_keys(Keys.ENTER)  # Send Enter key to trigger data population
        logging.info("Entered patient ID and sent Enter key")
        # self.__take_screenshot("PATIENT_ID_ENTERED")  # Uncomment for debugging

        # Wait for patient details to populate (give some time for the system to fetch data)
        time.sleep(3)

        # Submit the form directly without filling other details
        submit_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "submitNewButton")))
        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", submit_btn)
        time.sleep(0.5)
        submit_btn.click()
        logging.info("Form submitted with existing patient ID")
        # self.__take_screenshot("FORM_SUBMITTED")  # Uncomment for debugging

        # Handle success notification and capture bill number
        self.__handle_success_notification()
        
        # Capture patient ID and bill number
        self.__capture_patient_and_bill_info()
        logging.info(f"Captured Patient ID: {self.patient_id}")
        logging.info(f"Captured Bill No: {self.bill_no}")

        # Optionally add to test description for better XML reporting (appears in test doc)
        self._testMethodDoc = f"Patient ID: {self.patient_id}, Bill No: {self.bill_no}"

    def __handle_success_notification(self):
        """
        Verify success notification after form submission.
        """
        try:
            notification = self.wait.until(
                EC.visibility_of_element_located((By.XPATH,
                    "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')]"
                ))
            )
            logging.info("EMR registration successful")
            # self.__take_screenshot("REGISTRATION_SUCCESS_NOTIFICATION")  # Uncomment for debugging

            # Attempt to close notification gracefully
            try:
                close_btn = notification.find_element(By.CSS_SELECTOR, ".ui-pnotify-closer")
                self.driver.execute_script("arguments[0].click();", close_btn)
                WebDriverWait(self.driver, 5).until(EC.invisibility_of_element_located(notification))
            except Exception:
                logging.info("Notification auto-closed or close button not needed")
        except TimeoutException:
            # self.__take_screenshot("REGISTRATION_SUBMISSION_ERROR")  # Uncomment for debugging
            logging.error("Success notification not found")
            raise

    def __capture_patient_and_bill_info(self):
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
            
            # Store the patient ID and bill_no for saving to JSON
            if patient_id:
                self.patient_id = patient_id
            self.bill_no = bill_no
            
        except Exception as e:
            logging.error(f"Error capturing patient ID and bill info: {str(e)}")
            self.__take_screenshot("CAPTURE_PATIENT_BILL_ERROR")
            
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