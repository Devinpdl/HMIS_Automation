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
from selenium.common.exceptions import TimeoutException, NoAlertPresentException
from utilities.config_loader import ConfigLoader
import xml.etree.ElementTree as ET

# Folder configuration
screenshot_dir = os.path.join("screenshots", "opd_registration")
report_dir = os.path.join("reports", "opd_registration")
patient_json_dir = os.path.join(report_dir, "patient_ids")
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)
os.makedirs(patient_json_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TestResultWithPatientInfo(unittest.TestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.patient_id = None

    def addSuccess(self, test):
        super().addSuccess(test)
        if hasattr(test, 'patient_id'):
            self.patient_id = test.patient_id

class XMLTestRunnerWithPatientInfo(xmlrunner.XMLTestRunner):
    def run(self, test):
        result = super().run(test)
        
        # Extract patient_id from the test case
        patient_id = None
        for test_case in test._tests:
            if hasattr(test_case, 'patient_id'):
                patient_id = test_case.patient_id
                break
        
        # Get the XML report file
        xml_file = os.path.join(self.output, 'TEST-OPDRegistration.xml')
        
        # Wait for file creation
        time.sleep(2)
        
        if os.path.exists(xml_file) and patient_id is not None:
            try:
                # Parse and modify XML
                tree = ET.parse(xml_file)
                root = tree.getroot()
                testcase = root.find('.//testcase')
                
                if testcase is not None:
                    # Add properties element if it doesn't exist
                    properties = testcase.find('properties')
                    if properties is None:
                        properties = ET.SubElement(testcase, 'properties')
                    
                    # Add patient_id as attribute
                    testcase.set('patient_id', str(patient_id))
                    property_elem = ET.SubElement(properties, 'property')
                    property_elem.set('name', 'patient_id')
                    property_elem.set('value', str(patient_id))
                    
                    # Save changes
                    tree.write(xml_file, encoding='utf-8', xml_declaration=True)
                    logging.info(f"Added Patient ID {patient_id} to XML report")
            except Exception as e:
                logging.error(f"Error updating XML report: {str(e)}")
        
        return result

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
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-site-isolation-trials")
        # Disable print dialog
        chrome_options.add_argument("--kiosk-printing")
        cls.driver = webdriver.Chrome(options=chrome_options)
        cls.driver.maximize_window()
        cls.wait = WebDriverWait(cls.driver, 20)
        cls.short_wait = WebDriverWait(cls.driver, 5)
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

    def test_opd_registration(self):
        """
        Test method: Perform OPD registration.
        """
        logging.info("Starting OPD Registration...")
        self.__perform_opd_registration()

    def __perform_opd_registration(self):
        """
        Perform OPD registration process.
        """
        try:
            # Navigate to OPD Registration
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@id='patient_menu']/a"))).click()
            self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//a[@href='http://lunivacare.ddns.net:8080/himsnew/ipd/register/OPD']"))).click()
            logging.info("Navigated to OPD Registration page")
            self.__take_screenshot("OPD_REGISTER_PAGE")

            # Enter mobile number
            mobile_field = self.wait.until(EC.presence_of_element_located((By.ID, "mobile-number")))
            mobile_field.send_keys("9800000001")
            logging.info("Entered mobile number")
            self.__take_screenshot("MOBILE_ENTERED")
            time.sleep(2)  # Brief pause to allow modal to appear if needed
            self.__handle_duplicate_patient_modal()

            # Enter patient details
            Select(self.driver.find_element(By.ID, "designation")).select_by_value("Mr.")
            self.driver.find_element(By.ID, "first-name").send_keys("John")
            self.driver.find_element(By.ID, "last-name").send_keys("Doe")
            self.driver.find_element(By.ID, "age").send_keys("30")
            logging.info("Entered personal details")

            # Select address
            self.driver.find_element(By.XPATH, "//span[@id='select2-current-address-container']").click()
            search_field = self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@class='select2-search__field']")))
            search_field.send_keys("Kathmandu")
            self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//li[contains(@class, 'select2-results__option') and contains(text(), 'Kathmandu')]"))).click()
            logging.info("Selected address")
            self.__take_screenshot("FORM_FILLED")

            # Submit the form
            submit_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "submitNewButton")))
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", submit_btn)
            time.sleep(0.5)
            # Capture URL before submission
            pre_submit_url = self.driver.current_url
            logging.info(f"Pre-submit URL: {pre_submit_url}")
            submit_btn.click()
            logging.info("Form submitted")
            self.__take_screenshot("FORM_SUBMITTED")

            # Handle success notification
            self.__handle_success_notification()

            # Capture patient ID
            self.patient_id = self.__capture_patient_id(pre_submit_url)
            logging.info(f"Captured Patient ID: {self.patient_id}")

            # Wait for Print Sticker button and take screenshot
            try:
                print_sticker_btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "printStikerBtn")))
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_sticker_btn)
                time.sleep(1)
                sticker_screenshot_path = os.path.join(screenshot_dir, f"PRINT_STICKER_BTN_{self.patient_id}_{time.strftime('%Y%m%d_%H%M%S')}.png")
                print_sticker_btn.screenshot(sticker_screenshot_path)
                logging.info(f"Print Sticker button screenshot saved: {sticker_screenshot_path}")
            except Exception as e:
                logging.warning(f"Could not take screenshot of Print Sticker button: {str(e)}")
                self.__take_screenshot("PRINT_STICKER_ERROR")

        except Exception as e:
            self.__take_screenshot("REGISTRATION_FAILURE")
            logging.error(f"Registration test failed: {str(e)}")
            raise

    def __handle_duplicate_patient_modal(self):
        """
        Handle potential duplicate patient modal after entering mobile number.
        """
        modal_locator = (By.XPATH, "//h4[contains(.,'Patient Info')]")
        try:
            if self.driver.find_elements(*modal_locator):
                logging.info("Duplicate patient modal detected")
                self.__take_screenshot("DUPLICATE_MODAL_PRESENT")
                proceed_btn = self.short_wait.until(
                    EC.element_to_be_clickable((By.ID, "proceedToRegister")))
                self.driver.execute_script("arguments[0].click();", proceed_btn)
                logging.info("Clicked proceed button")
                self.__take_screenshot("MODAL_HANDLED")
                self.short_wait.until(EC.invisibility_of_element_located(modal_locator))
        except TimeoutException:
            logging.info("No duplicate modal present")

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
            logging.info("OPD registration successful")
            self.__take_screenshot("REGISTRATION_SUCCESS_NOTIFICATION")

            # Attempt to close notification gracefully
            try:
                close_btn = notification.find_element(By.CSS_SELECTOR, ".ui-pnotify-closer")
                self.driver.execute_script("arguments[0].click();", close_btn)
                self.short_wait.until(EC.invisibility_of_element_located(notification))
            except Exception:
                logging.info("Notification auto-closed or close button not needed")
        except TimeoutException:
            self.__take_screenshot("REGISTRATION_SUBMISSION_ERROR")
            logging.error("Success notification not found")
            raise

    def __capture_patient_id(self, pre_submit_url):
        """
        Capture patient ID from URL, new window, or page elements after submission.
        Handles unexpected navigation to chrome://print/.
        """
        main_window = self.driver.current_window_handle
        current_url = self.driver.current_url
        logging.info(f"Current URL after submission: {current_url}")

        # Intercept print function to prevent dialog
        try:
            self.driver.execute_script("window.print = function() { console.log('Print function intercepted'); };")
            logging.info("Intercepted window.print function")
        except Exception as e:
            logging.warning(f"Error intercepting window.print: {str(e)}")

        # Check for print dialog and attempt to close it
        if "chrome://print/" in current_url:
            logging.warning("Print dialog detected (chrome://print/). Attempting to handle.")
            self.__take_screenshot("PRINT_DIALOG_DETECTED")
            try:
                self.driver.switch_to.alert.dismiss()
                logging.info("Print dialog dismissed via alert")
            except NoAlertPresentException:
                logging.info("No alert present, attempting to close window")
                try:
                    self.driver.execute_script("window.close();")
                except Exception:
                    logging.warning("Could not close print window")
            self.driver.switch_to.window(main_window)
            current_url = self.driver.current_url
            logging.info(f"Switched back to main window, URL: {current_url}")
            self.__take_screenshot("AFTER_PRINT_DIALOG_HANDLED")

        # Check new window
        try:
            self.short_wait.until(lambda d: len(d.window_handles) > 1)
            logging.info(f"New window detected, handles: {self.driver.window_handles}")
            for window_handle in self.driver.window_handles:
                if window_handle != main_window:
                    self.driver.switch_to.window(window_handle)
                    current_url = self.driver.current_url
                    logging.info(f"Switched to new window, URL: {current_url}")
                    self.__take_screenshot("NEW_WINDOW")
                    patient_id = self.__extract_id_from_url(current_url)
                    self.driver.close()
                    self.driver.switch_to.window(main_window)
                    if patient_id:
                        return patient_id
        except TimeoutException:
            logging.info("No new window detected")

        # Try extracting from current URL
        patient_id = self.__extract_id_from_url(current_url)
        if patient_id:
            return patient_id

        # Try extracting from pre-submit URL (in case of redirect)
        patient_id = self.__extract_id_from_url(pre_submit_url)
        if patient_id:
            return patient_id

        # Fallback: Extract from page elements
        patient_id = self.__extract_id_from_page()
        if patient_id:
            return patient_id

        # Fallback: Check for patient ID in success notification or other elements
        patient_id = self.__extract_id_from_notification()
        if patient_id:
            return patient_id

        raise ValueError("Patient ID not captured from URL, page elements, or notification")

    def __extract_id_from_url(self, url):
        """
        Extract patient ID from the 'create_stiker' URL using regex.
        """
        try:
            match = re.search(r'/create_stiker/(\d+)', url)
            if match:
                patient_id = match.group(1)
                logging.info(f"Extracted Patient ID from URL: {patient_id}")
                return patient_id
            logging.warning(f"Patient ID not found in URL: {url}")
            return None
        except Exception as e:
            logging.error(f"Error extracting Patient ID from URL: {str(e)}")
            return None

    def __extract_id_from_page(self):
        """
        Fallback method to extract patient ID from page elements.
        """
        try:
            # Look for elements containing 'Patient ID' or similar
            id_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Patient ID') or contains(text(), 'Patient Id') or contains(text(), 'ID')]")
            for elem in id_elements:
                text = elem.text
                match = re.search(r'(?:Patient ID|Patient Id|ID)\s*:?\s*(\d+)', text, re.IGNORECASE)
                if match:
                    patient_id = match.group(1)
                    logging.info(f"Extracted Patient ID from page element: {patient_id}")
                    self.__take_screenshot("PATIENT_ID_FROM_PAGE")
                    return patient_id
            
            # Check for elements with classes like patient-id
            elements = self.driver.find_elements(By.XPATH, "//span[contains(@class, 'patient-id')] | //div[contains(@class, 'patient-id')]")
            for elem in elements:
                text = elem.text.strip()
                if text.isdigit():
                    logging.info(f"Extracted Patient ID from page element (numeric): {text}")
                    self.__take_screenshot("PATIENT_ID_FROM_PAGE_NUMERIC")
                    return text
            
            # Check printStikerBtn attributes
            try:
                print_sticker_btn = self.driver.find_element(By.CLASS_NAME, "printStikerBtn")
                for attr in ['title', 'data-original-title', 'data-patient-id']:
                    attr_value = print_sticker_btn.get_attribute(attr)
                    if attr_value:
                        match = re.search(r'\d+', attr_value)
                        if match:
                            patient_id = match.group(0)
                            logging.info(f"Extracted Patient ID from printStikerBtn {attr}: {patient_id}")
                            self.__take_screenshot("PATIENT_ID_FROM_STICKER_BTN")
                            return patient_id
            except Exception:
                logging.info("No printStikerBtn found for ID extraction")

            logging.warning("No Patient ID found in page elements")
            self.__take_screenshot("NO_PATIENT_ID_ON_PAGE")
            return None
        except Exception as e:
            logging.error(f"Error extracting Patient ID from page: {str(e)}")
            self.__take_screenshot("PATIENT_ID_PAGE_ERROR")
            return None

    def __extract_id_from_notification(self):
        """
        Fallback method to extract patient ID from success notification or related elements.
        """
        try:
            notification_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'ui-pnotify-container')]")
            for elem in notification_elements:
                text = elem.text
                match = re.search(r'(?:Patient ID|ID)\s*:?\s*(\d+)', text, re.IGNORECASE)
                if match:
                    patient_id = match.group(1)
                    logging.info(f"Extracted Patient ID from notification: {patient_id}")
                    self.__take_screenshot("PATIENT_ID_FROM_NOTIFICATION")
                    return patient_id
            logging.warning("No Patient ID found in notification")
            self.__take_screenshot("NO_PATIENT_ID_IN_NOTIFICATION")
            return None
        except Exception as e:
            logging.error(f"Error extracting Patient ID from notification: {str(e)}")
            self.__take_screenshot("PATIENT_ID_NOTIFICATION_ERROR")
            return None

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
        Test-level teardown: Save patient ID to JSON file if captured.
        """
        if self.patient_id:
            json_file = os.path.join(patient_json_dir, f"{self.patient_id}.json")
            data = {
                "patient_id": self.patient_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                # Verify directory exists and is writable
                if not os.path.exists(patient_json_dir):
                    os.makedirs(patient_json_dir, exist_ok=True)
                    logging.info(f"Created directory: {patient_json_dir}")
                
                # Check write permissions
                if not os.access(patient_json_dir, os.W_OK):
                    logging.error(f"No write permission for directory: {patient_json_dir}")
                    raise PermissionError(f"No write permission for directory: {patient_json_dir}")
                
                # Write JSON file
                with open(json_file, "w", encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                
                # Verify file was created
                if os.path.exists(json_file):
                    logging.info(f"Patient ID {self.patient_id} saved to {json_file}")
                    # Read back to confirm content
                    with open(json_file, "r", encoding='utf-8') as f:
                        saved_data = json.load(f)
                        if saved_data["patient_id"] == self.patient_id:
                            logging.info(f"Verified Patient ID {self.patient_id} in {json_file}")
                        else:
                            logging.error(f"Patient ID mismatch in {json_file}. Expected {self.patient_id}, found {saved_data['patient_id']}")
                else:
                    logging.error(f"Failed to create JSON file: {json_file}")
                    raise IOError(f"Failed to create JSON file: {json_file}")
                
            except PermissionError as e:
                logging.error(f"Permission error saving patient ID to {json_file}: {str(e)}")
                self.__take_screenshot("JSON_SAVE_PERMISSION_ERROR")
                raise
            except IOError as e:
                logging.error(f"IO error saving patient ID to {json_file}: {str(e)}")
                self.__take_screenshot("JSON_SAVE_IO_ERROR")
                raise
            except Exception as e:
                logging.error(f"Unexpected error saving patient ID to {json_file}: {str(e)}")
                self.__take_screenshot("JSON_SAVE_ERROR")
                raise

    @classmethod
    def tearDownClass(cls):
        """
        Class-level teardown: Clean up extra browser windows, keeping the main one open.
        """
        logging.info("Cleaning up browser windows...")
        try:
            # Ensure we have time to write XML and JSON before cleanup
            time.sleep(2)
            
            # Get current window handles
            window_handles = cls.driver.window_handles
            main_window = window_handles[0]
            
            if len(window_handles) > 1:
                # Close additional windows one by one
                for handle in window_handles[1:]:
                    try:
                        cls.driver.switch_to.window(handle)
                        logging.info(f"Closing window: {handle}")
                        cls.driver.close()
                        time.sleep(0.5)
                    except Exception as e:
                        logging.warning(f"Window {handle} already closed or not accessible")
            
            # Switch back to main window
            try:
                cls.driver.switch_to.window(main_window)
                logging.info("Back to main window")
            except Exception as e:
                logging.error(f"Error switching to main window: {str(e)}")
        except Exception as e:
            logging.error(f"Error during cleanup: {str(e)}")
        finally:
            try:
                current_handle = cls.driver.current_window_handle
                if current_handle != main_window:
                    cls.driver.switch_to.window(main_window)
            except Exception:
                pass
            logging.info("Cleanup completed. Main window remains open.")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Use the custom test runner
    runner = XMLTestRunnerWithPatientInfo(
        output=report_dir,
        verbosity=2,
        outsuffix=""
    )
    
    # Run the test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(OPDRegistration)
    runner.run(suite)