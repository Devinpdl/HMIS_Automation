import os
import sys
# Add the parent directory of 'utilities' to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import re
import time
import logging
import unittest
import json
import xmlrunner
import glob
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
from utilities.config_loader import ConfigLoader
import xml.etree.ElementTree as ET

# Folder configuration
screenshot_dir = os.path.join("screenshots", "emr_billing")
report_dir = os.path.join("reports", "emr_billing")
patient_json_dir = os.path.join(report_dir, "patient_ids")
bill_nos_dir = os.path.join(report_dir, "bill_nos")
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)
os.makedirs(patient_json_dir, exist_ok=True)
os.makedirs(bill_nos_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TestResultWithBillInfo(unittest.TestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.bill_no = None
        self.bill_id = None
        self.patient_id = None

    def addSuccess(self, test):
        super().addSuccess(test)
        if hasattr(test, 'bill_no'):
            self.bill_no = test.bill_no
        if hasattr(test, 'bill_id'):
            self.bill_id = test.bill_id
        if hasattr(test, 'patient_id'):
            self.patient_id = test.patient_id

class XMLTestRunnerWithBillInfo(xmlrunner.XMLTestRunner):
    def run(self, test):
        result = super().run(test)
        
        # Extract bill_no, bill_id, and patient_id from the test case
        bill_no = None
        bill_id = None
        patient_id = None
        for test_case in test._tests:
            if hasattr(test_case, 'bill_no'):
                bill_no = test_case.bill_no
            if hasattr(test_case, 'bill_id'):
                bill_id = test_case.bill_id
            if hasattr(test_case, 'patient_id'):
                patient_id = test_case.patient_id
                break
        
        # Generate XML filename with timestamp
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        xml_file = os.path.join(self.output, f'TEST-EMRBilling_{timestamp}.xml')
        
        # Wait for file creation
        time.sleep(2)
        
        if os.path.exists(xml_file) and (bill_no is not None or bill_id is not None or patient_id is not None):
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
                    
                    # Add bill_no, bill_id, and patient_id as attributes
                    if bill_no is not None:
                        testcase.set('bill_no', str(bill_no))
                        property_elem = ET.SubElement(properties, 'property')
                        property_elem.set('name', 'bill_no')
                        property_elem.set('value', str(bill_no))
                    
                    if bill_id is not None:
                        testcase.set('bill_id', str(bill_id))
                        property_elem = ET.SubElement(properties, 'property')
                        property_elem.set('name', 'bill_id')
                        property_elem.set('value', str(bill_id))
                    
                    if patient_id is not None:
                        testcase.set('patient_id', str(patient_id))
                        property_elem = ET.SubElement(properties, 'property')
                        property_elem.set('name', 'patient_id')
                        property_elem.set('value', str(patient_id))
                    
                    # Save changes
                    tree.write(xml_file, encoding='utf-8', xml_declaration=True)
                    logging.info(f"Added Bill No {bill_no}, Bill ID {bill_id}, Patient ID {patient_id} to XML report: {xml_file}")
            except Exception as e:
                logging.error(f"Error updating XML report: {str(e)}")
        
        return result

class EMRBilling(unittest.TestCase):
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
        chrome_options.add_argument("--disable-logging")
        cls.driver = webdriver.Chrome(options=chrome_options)
        cls.driver.maximize_window()
        cls.wait = WebDriverWait(cls.driver, 20)
        cls.short_wait = WebDriverWait(cls.driver, 10)  # Increased for modal handling
        cls.base_url = cls.config["base_url"]
        cls.valid_username = cls.config["username"]
        cls.valid_password = cls.config["password"]

    def setUp(self):
        """
        Test-level setup: Navigate to base URL, login, and initialize bill_no, bill_id, and patient_id.
        """
        self.driver.get(self.base_url)
        self.__login()
        self.bill_no = None
        self.bill_id = None
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

    def __get_latest_patient_id(self):
        """
        Get the latest patient ID from the patient_ids folders.
        Returns the most recent patient ID based on file modification time.
        """
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
            patient_id_dirs = [
                os.path.join(base_dir, 'emr_billing', 'patient_ids'),
                os.path.join(base_dir, 'emr_combined', 'patient_ids'),
                os.path.join(base_dir, 'emr_registration', 'patient_ids'),
                os.path.join(base_dir, 'opd_billing', 'patient_ids'),
                os.path.join(base_dir, 'opd_combined', 'patient_ids'),
                os.path.join(base_dir, 'opd_registration', 'patient_ids')
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
                raise ValueError("No patient ID files found in any patient_ids folder (emr_billing, emr_combined, emr_registration, opd_billing, opd_combined, opd_registration)")
            
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

    def test_emr_billing(self):
        """
        Test method: Perform EMR billing using the latest patient ID and select both CBC and ABO & Rh Factor tests.
        """
        logging.info("Starting EMR Billing...")
        self.__perform_emr_billing()

    def __perform_emr_billing(self):
        """
        Perform EMR billing process using the latest patient ID.
        """
        try:
            # Navigate to EMR Billing
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@id='patient_menu']/a"))).click()
            billing_link = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//a[@href='http://lunivacare.ddns.net:8080/himsnew/bill/createBill?bt=Emergency']")))
            billing_link.click()
            logging.info("Navigated to EMR Billing page")
            self.__take_screenshot("EMR_BILLING_PAGE")

            # Store the original window handle
            original_window = self.driver.current_window_handle
            logging.info(f"Original window handle: {original_window}")

            # Use the latest patient ID
            patient_id_to_use = self.__get_latest_patient_id()
            self.patient_id = patient_id_to_use

            # Enter Patient ID
            patient_id_field = self.wait.until(EC.presence_of_element_located((By.ID, "patientId")))
            patient_id_field.clear()
            patient_id_field.send_keys(patient_id_to_use)
            logging.info(f"Entered Patient ID: {patient_id_to_use}")
            self.__take_screenshot("PATIENT_ID_ENTERED")

            # Click Search button
            search_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "bill-searchPatient")))
            search_btn.click()
            logging.info("Clicked Search button")
            self.__take_screenshot("SEARCH_CLICKED")

            # Wait for patient info to load
            self.wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "patientName")))
            logging.info("Patient information loaded")
            self.__take_screenshot("PATIENT_INFO_LOADED")

            # Select tests (CBC and ABO & Rh Factor)
            self.__select_test()

            # Enter remarks
            remarks_field = self.wait.until(EC.presence_of_element_located((By.ID, "billRemarks")))
            remarks_field.clear()
            remarks_field.send_keys("paid")
            logging.info("Entered remarks: 'paid'")
            self.__take_screenshot("REMARKS_ENTERED")

            # Submit the form
            self.__submit_billing_form()

            # Handle success notification
            self.__handle_billing_success_notification()
            
            # Capture Bill No and Bill ID
            self.__capture_and_handle_bill_info(original_window)
            
        except Exception as e:
            self.__take_screenshot("BILLING_FAILURE")
            logging.error(f"Billing test failed: {str(e)}")
            raise

    def __select_test(self):
        """
        Select CBC and ABO & Rh Factor tests from dropdown and handle performedByModal.
        """
        tests = ["Complete Blood Cell Count", "ABO & Rh Factor"]
        
        for test_name in tests:
            max_attempts = 3
            attempt = 1
            while attempt <= max_attempts:
                try:
                    # Locate and open the test dropdown
                    dropdown = self.short_wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//span[starts-with(@id, 'select2-chosen-')]")))
                    dropdown.click()
                    logging.info(f"Test dropdown clicked for {test_name} (attempt {attempt})")
                    self.__take_screenshot(f"TEST_DROPDOWN_CLICKED_{test_name.replace(' ', '_')}_{attempt}")

                    # Locate search input
                    search_input = self.short_wait.until(EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@class, 'select2-drop-active')]//input")))
                    search_input.clear()
                    search_input.send_keys(test_name)
                    logging.info(f"Entered {test_name} in search (attempt {attempt})")
                    time.sleep(2)
                    self.__take_screenshot(f"TEST_SEARCH_ENTERED_{test_name.replace(' ', '_')}_{attempt}")

                    # Log available dropdown options for debugging
                    try:
                        options = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'select2-result-label')]")
                        option_texts = [opt.text.strip() for opt in options]
                        logging.info(f"Available dropdown options for {test_name}: {option_texts}")
                    except Exception as e:
                        logging.warning(f"Could not retrieve dropdown options: {str(e)}")

                    # Try multiple XPaths to locate the test option
                    xpaths = [
                        f"//div[contains(@class, 'select2-result-label') and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{test_name.lower()}')]",
                        f"//div[contains(text(), '{test_name}')]",
                        f"//div[contains(@class, 'select2-result-label') and contains(text(), 'CBC')]" if test_name == "Complete Blood Cell Count" else None,
                        f"//div[contains(@class, 'select2-result-label')]"
                    ]
                    xpaths = [x for x in xpaths if x]

                    test_option = None
                    for xpath in xpaths:
                        try:
                            test_option = self.short_wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                            logging.info(f"Found test option using XPath: {xpath}")
                            break
                        except TimeoutException:
                            logging.debug(f"XPath failed: {xpath}")
                            continue

                    if test_option:
                        test_option.click()
                        logging.info(f"{test_name} selected (attempt {attempt})")
                        self.__take_screenshot(f"{test_name.replace(' ', '_')}_SELECTED_{attempt}")
                        break
                    else:
                        logging.warning(f"Test option '{test_name}' not found after trying all XPaths (attempt {attempt})")
                        self.__take_screenshot(f"{test_name.replace(' ', '_')}_NOT_FOUND_{attempt}")
                        attempt += 1
                        continue

                except Exception as e:
                    logging.warning(f"Failed to select {test_name} on attempt {attempt}: {str(e)}")
                    self.__take_screenshot(f"{test_name.replace(' ', '_')}_SELECTION_ERROR_{attempt}")
                    attempt += 1
                    if attempt > max_attempts:
                        logging.error(f"Failed to select {test_name} after {max_attempts} attempts")
                        raise TimeoutException(f"Failed to select {test_name} after {max_attempts} attempts")

                # Handle performedByModal for non-pathology tests
                if test_name == "ABO & Rh Factor" and attempt <= max_attempts:
                    max_modal_attempts = 3
                    modal_attempt = 1
                    while modal_attempt <= max_modal_attempts:
                        try:
                            modal = self.short_wait.until(EC.visibility_of_element_located(
                                (By.ID, "performedByModal")))
                            logging.info(f"Performed By modal detected (modal attempt {modal_attempt})")
                            self.__take_screenshot(f"PERFORMED_BY_MODAL_{modal_attempt}")

                            # Log modal HTML for debugging
                            modal_html = modal.get_attribute('outerHTML')
                            logging.debug(f"Modal HTML: {modal_html[:500]}...")  # Truncate for brevity

                            # Verify default selection is SELF
                            select_element = self.short_wait.until(EC.presence_of_element_located(
                                (By.XPATH, "//span[@class='select2-chosen' and contains(text(), 'SELF')]")))
                            logging.info("Default selection 'SELF' confirmed")

                            # Try multiple selectors for the Select button
                            select_button_xpaths = [
                                "//button[@type='submit' and contains(@class, 'antoclose')]",
                                "//button[@type='submit' and contains(text(), 'Select')]",
                                "//button[contains(@class, 'btn-primary') and contains(text(), 'Select')]"
                            ]
                            select_btn = None
                            for xpath in select_button_xpaths:
                                try:
                                    select_btn = self.short_wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                                    logging.info(f"Found Select button using XPath: {xpath}")
                                    break
                                except TimeoutException:
                                    logging.debug(f"Select button XPath failed: {xpath}")
                                    continue

                            if select_btn:
                                try:
                                    select_btn.click()
                                    logging.info(f"Clicked Select button in performedByModal (modal attempt {modal_attempt})")
                                    self.__take_screenshot(f"PERFORMED_BY_MODAL_SUBMITTED_{modal_attempt}")
                                except ElementClickInterceptedException:
                                    logging.warning("Select button click intercepted, trying JavaScript click")
                                    self.driver.execute_script("arguments[0].click();", select_btn)
                                    logging.info(f"JavaScript clicked Select button (modal attempt {modal_attempt})")
                                    self.__take_screenshot(f"PERFORMED_BY_MODAL_JS_CLICK_{modal_attempt}")
                            else:
                                logging.warning(f"Select button not found after trying all XPaths (modal attempt {modal_attempt})")
                                self.__take_screenshot(f"SELECT_BUTTON_NOT_FOUND_{modal_attempt}")

                            # Wait for modal to close
                            self.short_wait.until(EC.invisibility_of_element_located((By.ID, "performedByModal")))
                            logging.info("Performed By modal closed")
                            break


                        except TimeoutException as e:
                            logging.warning(f"Performed By modal handling failed on modal attempt {modal_attempt}: {str(e)}")
                            self.__take_screenshot(f"NO_PERFORMED_BY_MODAL_{modal_attempt}")

                            # Try to find and click a Cancel/Close button as fallback
                            close_button_xpaths = [
                                "//button[contains(@class, 'close')]",
                                "//button[contains(text(), 'Close') or contains(text(), 'Cancel')]"
                            ]
                            close_btn = None
                            for xpath in close_button_xpaths:
                                try:
                                    close_btn = self.short_wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                                    logging.info(f"Found Close button using XPath: {xpath}")
                                    break
                                except TimeoutException:
                                    logging.debug(f"Close button XPath failed: {xpath}")
                                    continue

                            if close_btn:
                                try:
                                    close_btn.click()
                                    logging.info(f"Clicked Close button in performedByModal (modal attempt {modal_attempt})")
                                    self.__take_screenshot(f"PERFORMED_BY_MODAL_CLOSED_{modal_attempt}")
                                    self.short_wait.until(EC.invisibility_of_element_located((By.ID, "performedByModal")))
                                    logging.info("Performed By modal closed via Close button")
                                    break
                                except Exception as e:
                                    logging.warning(f"Failed to click Close button: {str(e)}")
                                    self.__take_screenshot(f"PERFORMED_BY_MODAL_CLOSE_ERROR_{modal_attempt}")

                            modal_attempt += 1
                            if modal_attempt > max_modal_attempts:
                                logging.error(f"Failed to handle performedByModal after {max_modal_attempts} attempts")
                                raise TimeoutException(f"Failed to handle performedByModal after {max_modal_attempts} attempts")

    def __submit_billing_form(self):
        """
        Submit the billing form, ensuring no modals are open.
        """
        try:
            # Check for performedByModal and close it if present
            max_modal_attempts = 3
            modal_attempt = 1
            while modal_attempt <= max_modal_attempts:
                try:
                    modal = self.driver.find_element(By.ID, "performedByModal")
                    if modal.is_displayed():
                        logging.warning(f"Performed By modal still open before submitting form (attempt {modal_attempt})")
                        self.__take_screenshot(f"UNEXPECTED_MODAL_BEFORE_SUBMIT_{modal_attempt}")

                        # Try to find and click the Select or Close button
                        button_xpaths = [
                            "//button[@type='submit' and contains(@class, 'antoclose')]",
                            "//button[@type='submit' and contains(text(), 'Select')]",
                            "//button[contains(@class, 'btn-primary') and contains(text(), 'Select')]",
                            "//button[contains(@class, 'close')]",
                            "//button[contains(text(), 'Close') or contains(text(), 'Cancel')]"
                        ]
                        button = None
                        for xpath in button_xpaths:
                            try:
                                button = self.short_wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                                logging.info(f"Found button to close modal using XPath: {xpath}")
                                break
                            except TimeoutException:
                                logging.debug(f"Button XPath failed: {xpath}")
                                continue

                        if button:
                            try:
                                button.click()
                                logging.info(f"Clicked button to close modal (attempt {modal_attempt})")
                                self.__take_screenshot(f"UNEXPECTED_MODAL_CLOSED_{modal_attempt}")
                            except ElementClickInterceptedException:
                                logging.warning("Button click intercepted, trying JavaScript click")
                                self.driver.execute_script("arguments[0].click();", button)
                                logging.info(f"JavaScript clicked button to close modal (attempt {modal_attempt})")
                                self.__take_screenshot(f"UNEXPECTED_MODAL_JS_CLOSED_{modal_attempt}")

                            self.short_wait.until(EC.invisibility_of_element_located((By.ID, "performedByModal")))
                            logging.info("Performed By modal closed before submitting form")
                            break
                        else:
                            logging.warning(f"No button found to close modal (attempt {modal_attempt})")
                            self.__take_screenshot(f"NO_BUTTON_TO_CLOSE_MODAL_{modal_attempt}")

                        modal_attempt += 1
                        if modal_attempt > max_modal_attempts:
                            logging.error(f"Failed to close performedByModal after {max_modal_attempts} attempts")
                            raise TimeoutException(f"Failed to close performedByModal after {max_modal_attempts} attempts")
                    else:
                        logging.info("No performedByModal detected before submitting form")
                        break
                except Exception:
                    logging.info("No performedByModal detected before submitting form")
                    break

            # Click Submit button
            submit_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "sbmtbtn")))
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                submit_btn
            )
            time.sleep(0.5)
            try:
                submit_btn.click()
                logging.info("Clicked Submit button to complete the billing process")
                self.__take_screenshot("BILLING_FORM_SUBMITTED")
            except ElementClickInterceptedException as e:
                logging.warning(f"Submit button click intercepted: {str(e)}")
                self.__take_screenshot("SUBMIT_BUTTON_INTERCEPTED")
                # Try JavaScript click as fallback
                self.driver.execute_script("arguments[0].click();", submit_btn)
                logging.info("JavaScript clicked Submit button")
                self.__take_screenshot("BILLING_FORM_SUBMITTED_JS")
            
        except Exception as e:
            self.__take_screenshot("SUBMIT_BUTTON_ERROR")
            logging.error(f"Failed to submit billing form: {str(e)}")
            raise

    def __handle_billing_success_notification(self):
        """
        Handle success notification for billing.
        """
        try:
            success_message_locator = (By.XPATH, "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')]")
            notification = self.wait.until(EC.visibility_of_element_located(success_message_locator))
            logging.info("Billing success notification detected")
            self.__take_screenshot("BILLING_SUCCESS_NOTIFICATION")
            return True
        except TimeoutException:
            try:
                notification = self.short_wait.until(
                    EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'ui-pnotify-container') or contains(@class, 'alert-success')]")))
                logging.info("Generic billing success notification detected")
                self.__take_screenshot("GENERIC_BILLING_SUCCESS_NOTIFICATION")
                return True
            except TimeoutException:
                try:
                    confirmation = self.short_wait.until(
                        EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'Success') or contains(text(), 'Bill created')]")))
                    logging.info("Bill creation confirmation detected")
                    self.__take_screenshot("BILL_CONFIRMATION")
                    return True
                except TimeoutException:
                    self.__take_screenshot("BILLING_SUBMISSION_RESULT")
                    logging.warning("No explicit billing success notification found, proceeding with caution")
                    return False

    def __capture_and_handle_bill_info(self, original_window):
        """
        Capture Bill No from new window and Bill ID from main page by hovering over Print Bill button.
        """
        wait_for_windows = WebDriverWait(self.driver, 20)
        try:
            # Wait for new window or tab to open
            wait_for_windows.until(lambda d: len(d.window_handles) > 1)
            logging.info(f"Number of windows: {len(self.driver.window_handles)}")
            
            # Switch to the new window or tab
            for window_handle in self.driver.window_handles:
                if window_handle != original_window:
                    self.driver.switch_to.window(window_handle)
                    break
            
            logging.info(f"Switched to new window: {self.driver.current_url}")
            self.__take_screenshot("BILL_WINDOW")
            
            # Extract the bill No from the new window
            bill_no = self.__extract_bill_no_from_invoice()
            if bill_no:
                self.bill_no = bill_no
                logging.info(f"Successfully captured Bill No: {self.bill_no}")
            else:
                logging.warning("Could not extract Bill No from invoice")
            
            # Switch back to the original window
            self.driver.switch_to.window(original_window)
            logging.info("Switched back to original window")
            
            # Capture Bill ID by hovering over Print Bill button
            try:
                print_bill_btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "printBtn")))
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_bill_btn)
                time.sleep(0.5)
                actions = ActionChains(self.driver)
                actions.move_to_element(print_bill_btn).perform()
                time.sleep(2)
                self.__take_screenshot("PRINT_BILL_HOVER")
                title = print_bill_btn.get_attribute("data-original-title")
                logging.info(f"Tooltip content: {title}")
                if title:
                    match = re.search(r'Bill Id\s*:\s*.*?>\s*(\d+)\s*<', title, re.IGNORECASE | re.DOTALL)
                    if match:
                        self.bill_id = match.group(1)
                        logging.info(f"Captured Bill ID from tooltip: {self.bill_id}")
                    else:
                        logging.warning("Could not find Bill ID in tooltip")
                        self.__take_screenshot("BILL_ID_TOOLTIP_NOT_FOUND")
                else:
                    logging.warning("No data-original-title in print button")
                    self.__take_screenshot("BILL_ID_NO_TOOLTIP")
                actions.move_by_offset(0, -100).perform()
                
                # Fallback: Try extracting Bill ID from page elements
                if not self.bill_id:
                    bill_id_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Bill Id') or contains(text(), 'Bill ID')]")
                    for elem in bill_id_elements:
                        text = elem.text
                        match = re.search(r'Bill Id\s*:?\s*(\d+)', text, re.IGNORECASE)
                        if match:
                            self.bill_id = match.group(1)
                            logging.info(f"Captured Bill ID from page element: {self.bill_id}")
                            break
                    if not self.bill_id:
                        logging.warning("Could not find Bill ID in page elements")
                        self.__take_screenshot("BILL_ID_PAGE_NOT_FOUND")
            
            except Exception as e:
                logging.error(f"Error capturing Bill ID: {str(e)}")
                self.__take_screenshot("BILL_ID_CAPTURE_ERROR")
            
        except TimeoutException:
            logging.warning("No new window appeared. Trying to find Bill No in current window")
            self.bill_no = self.__capture_bill_no_fallback()
            logging.info(f"Captured Bill No: {self.bill_no}")
            # Also attempt to capture Bill ID
            try:
                print_bill_btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "printBtn")))
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_bill_btn)
                time.sleep(0.5)
                actions = ActionChains(self.driver)
                actions.move_to_element(print_bill_btn).perform()
                time.sleep(2)
                self.__take_screenshot("PRINT_BILL_HOVER_FALLBACK")
                title = print_bill_btn.get_attribute("data-original-title")
                logging.info(f"Tooltip content (fallback): {title}")
                if title:
                    match = re.search(r'Bill Id\s*:\s*.*?>\s*(\d+)\s*<', title, re.IGNORECASE | re.DOTALL)
                    if match:
                        self.bill_id = match.group(1)
                        logging.info(f"Captured Bill ID from tooltip (fallback): {self.bill_id}")
                    else:
                        logging.warning("Could not find Bill ID in tooltip (fallback)")
                        self.__take_screenshot("BILL_ID_TOOLTIP_NOT_FOUND_FALLBACK")
                else:
                    logging.warning("No data-original-title in print button (fallback)")
                    self.__take_screenshot("BILL_ID_NO_TOOLTIP_FALLBACK")
                actions.move_by_offset(0, -100).perform()
                
                # Fallback: Try extracting Bill ID from page elements
                if not self.bill_id:
                    bill_id_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Bill Id') or contains(text(), 'Bill ID')]")
                    for elem in bill_id_elements:
                        text = elem.text
                        match = re.search(r'Bill Id\s*:?\s*(\d+)', text, re.IGNORECASE)
                        if match:
                            self.bill_id = match.group(1)
                            logging.info(f"Captured Bill ID from page element (fallback): {self.bill_id}")
                            break
                    if not self.bill_id:
                        logging.warning("Could not find Bill ID in page elements (fallback)")
                        self.__take_screenshot("BILL_ID_PAGE_NOT_FOUND_FALLBACK")
            
            except Exception as e:
                logging.error(f"Error capturing Bill ID (fallback): {str(e)}")
                self.__take_screenshot("BILL_ID_CAPTURE_ERROR_FALLBACK")
        
        # Force wait to ensure info is captured
        time.sleep(2)

    def __extract_bill_no_from_invoice(self):
        """
        Extract bill No from the invoice page.
        """
        try:
            bill_element = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'Bill No:') or contains(strong/text(), 'Bill No:')]")))
            bill_text = bill_element.text
            bill_match = re.search(r'Bill No:\s*(?:I)?(\d+)', bill_text)
            
            if bill_match:
                bill_no = bill_match.group(1)
                logging.info(f"Found bill No in invoice: {bill_no}")
                return bill_no
            
            bill_elements = self.driver.find_elements(By.XPATH, "//strong[contains(text(), 'Bill No:')]")
            for element in bill_elements:
                text = element.text
                if 'Bill No:' in text:
                    bill_no = text.split('Bill No:')[1].strip()
                    if bill_no.startswith('I'):
                        bill_no = bill_no[1:]
                    logging.info(f"Found bill No via alternative method: {bill_no}")
                    return bill_no
            
            bill_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'I0000')]")
            for element in bill_elements:
                text = element.text
                bill_match = re.search(r'(I\d+)', text)
                if bill_match:
                    bill_no = bill_match.group(1)[1:]
                    logging.info(f"Found bill No with prefix: {bill_no}")
                    return bill_no
            
            logging.warning("Could not find bill No in any element")
            return None
        except Exception as e:
            logging.error(f"Error extracting bill No from invoice: {str(e)}")
            self.__take_screenshot("BILL_NO_EXTRACTION_ERROR")
            return None

    def __capture_bill_no_fallback(self):
        """
        Fallback method to capture bill No from current page.
        """
        try:
            url = self.driver.current_url
            bill_no_match = re.search(r'[?&]billId=(\d+)', url)
            if bill_no_match:
                return bill_no_match.group(1)
            
            bill_elements = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Bill') and contains(text(), 'ID') or contains(text(), 'No')]")
            for elem in bill_elements:
                text = elem.text
                no_match = re.search(r'Bill\s*(ID|No)?\s*:?\s*(\d+)', text, re.IGNORECASE)
                if no_match:
                    return no_match.group(2)
            
            id_elements = self.driver.find_elements(By.XPATH, "//strong[contains(text(), 'ID')]/following-sibling::span")
            if id_elements:
                for elem in id_elements:
                    text = elem.text.strip()
                    if text.isdigit():
                        return text
            
            return "unknown"
            
        except Exception as e:
            logging.error(f"Bill No capture failed: {str(e)}")
            return "error"

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
        Test-level teardown: Save bill info to JSON file if captured.
        """
        if self.bill_no:
            bill_json_file = os.path.join(bill_nos_dir, f"{self.bill_no.zfill(8)}.json")
            bill_data = {
                "bill_no": self.bill_no.zfill(8),
                "patient_id": self.patient_id if hasattr(self, 'patient_id') and self.patient_id else "unknown",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                with open(bill_json_file, "w") as f:
                    json.dump(bill_data, f, indent=4)
                logging.info(f"Bill information saved to {bill_json_file}")
            except Exception as e:
                logging.error(f"Error saving bill information to {bill_json_file}: {str(e)}")
                self.__take_screenshot("BILL_JSON_SAVE_ERROR")

    @classmethod
    def tearDownClass(cls):
        """
        Class-level teardown: Clean up extra browser windows, keeping the main one open.
        """
        logging.info("Cleaning up browser windows...")
        try:
            time.sleep(2)
            window_handles = cls.driver.window_handles
            main_window = window_handles[0]
            
            if len(window_handles) > 1:
                for handle in window_handles[1:]:
                    try:
                        cls.driver.switch_to.window(handle)
                        logging.info(f"Closing window: {handle}")
                        cls.driver.close()
                        time.sleep(0.5)
                    except Exception as e:
                        logging.warning(f"Window {handle} already closed or not accessible")
            
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
    
    runner = XMLTestRunnerWithBillInfo(
        output=report_dir,
        verbosity=2,
        outsuffix=""
    )
    
    suite = unittest.TestLoader().loadTestsFromTestCase(EMRBilling)
    runner.run(suite)