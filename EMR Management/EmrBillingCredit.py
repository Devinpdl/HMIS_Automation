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
screenshot_dir = os.path.join("screenshots", "emr_billing_credit")
report_dir = os.path.join("reports", "emr_billing_credit")
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
        xml_file = os.path.join(self.output, f'TEST-EMRBillingCredit_{timestamp}.xml')
        
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

class EMRBillingCredit(unittest.TestCase):
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

    def __get_latest_emr_patient_id(self):
        """
        Get the latest EMR patient ID from the patient_ids folders.
        Returns the most recent patient ID based on file modification time.
        """
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
            patient_id_dirs = [
                os.path.join(base_dir, 'emr_billing_credit', 'patient_ids'),
                os.path.join(base_dir, 'emr_billing_due', 'patient_ids'),
                os.path.join(base_dir, 'emr_combined', 'patient_ids'),
                os.path.join(base_dir, 'emr_registration', 'patient_ids'),
                os.path.join(base_dir, 'emr_registration_existing', 'patient_ids'),
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
                raise ValueError("No patient ID files found in any patient_ids folder (emr_billing_credit, emr_billing_due, emr_combined, emr_registration, emr_registration_existing, opd_billing, opd_combined, opd_registration)")
            
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

    def test_emr_billing_credit(self):
        """
        Test method: Perform EMR billing with Credit payment using the latest patient ID.
        """
        logging.info("Starting EMR Billing with Credit Payment...")
        self.__perform_emr_billing_credit()

    def __perform_emr_billing_credit(self):
        """
        Perform EMR billing with Credit payment using the latest patient ID.
        """
        try:
            # Navigate directly to EMR Billing
            self.driver.get("http://lunivacare.ddns.net:8080/himsnew/bill/createBill?bt=Emergency")
            self.wait.until(EC.presence_of_element_located((By.ID, "patientId")))
            logging.info("Navigated to EMR Billing page")
            self.__take_screenshot("EMR_BILLING_PAGE")

            # Store the original window handle
            original_window = self.driver.current_window_handle
            logging.info(f"Original window handle: {original_window}")

            # Use the latest EMR patient ID
            patient_id_to_use = self.__get_latest_emr_patient_id()
            self.patient_id = patient_id_to_use

            # Enter Patient ID
            patient_id_field = self.wait.until(EC.presence_of_element_located((By.ID, "patientId")))
            # Additional check to ensure patient ID field is visible
            if not patient_id_field.is_displayed():
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", patient_id_field)
                time.sleep(0.5)
            patient_id_field.clear()
            patient_id_field.send_keys(patient_id_to_use)
            logging.info(f"Entered Patient ID: {patient_id_to_use}")
            self.__take_screenshot("PATIENT_ID_ENTERED")

            # Click Search button
            search_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "bill-searchPatient")))
            # Additional check to ensure search button is visible
            if not search_btn.is_displayed():
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", search_btn)
                time.sleep(0.5)
            search_btn.click()
            logging.info("Clicked Search button")
            self.__take_screenshot("SEARCH_CLICKED")

            # Wait for patient info to load
            self.wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "patientName")))
            logging.info("Patient information loaded")
            self.__take_screenshot("PATIENT_INFO_LOADED")

            # Handle "Recommended Test For Emergency" notification if it appears
            self.__handle_recommended_test_notification()

            # Handle outstanding balance alert if it appears
            self.__handle_outstanding_balance_alert()

            # Select tests (CBC and ABO & Rh Factor)
            self.__select_test()

            # Handle performedByForm modal if it appears
            self.__handle_performed_by_modal()

            # Select Credit payment option
            self.__select_credit_payment()

            # Enter remarks
            try:
                remarks_field = self.wait.until(EC.presence_of_element_located((By.ID, "billRemarks")))
                # Additional check to ensure remarks field is visible
                if not remarks_field.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", remarks_field)
                    time.sleep(0.5)
                remarks_field.clear()
                remarks_field.send_keys("Credit payment test")
                logging.info("Entered remarks: 'Credit payment test'")
                self.__take_screenshot("REMARKS_ENTERED")
            except Exception as e:
                logging.warning(f"Could not enter remarks using ID 'billRemarks': {str(e)}")
                # Try alternative remark field selectors
                try:
                    remarks_field = self.wait.until(EC.presence_of_element_located((By.NAME, "billRemarks")))
                    # Additional check to ensure remarks field is visible
                    if not remarks_field.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", remarks_field)
                        time.sleep(0.5)
                    remarks_field.clear()
                    remarks_field.send_keys("Credit payment test")
                    logging.info("Entered remarks using NAME 'billRemarks'")
                    self.__take_screenshot("REMARKS_ENTERED_BY_NAME")
                except Exception as e2:
                    logging.warning(f"Could not enter remarks using NAME 'billRemarks': {str(e2)}")
                    # Try textarea with placeholder
                    try:
                        remarks_field = self.wait.until(EC.presence_of_element_located((By.XPATH, "//textarea[contains(@placeholder, 'Bill Remarks')]")))
                        # Additional check to ensure remarks field is visible
                        if not remarks_field.is_displayed():
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", remarks_field)
                            time.sleep(0.5)
                        remarks_field.clear()
                        remarks_field.send_keys("Credit payment test")
                        logging.info("Entered remarks using textarea with placeholder")
                        self.__take_screenshot("REMARKS_ENTERED_TEXTAREA")
                    except Exception as e3:
                        logging.warning(f"Could not enter remarks using textarea: {str(e3)}")

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
                    # Wait for any overlays to disappear before clicking dropdown
                    try:
                        self.wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "ui-widget-overlay")))
                    except:
                        pass  # If overlay not found, continue
                    
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
                        f"//div[contains(@class, 'select2-result-label') and contains(text(), 'CBC')]" if test_name == "Complete Blood Cell Count" else f"//div[contains(@class, 'select2-result-label') and contains(text(), 'ABO & Rh Factor')]" if test_name == "ABO & Rh Factor" else f"//div[contains(@class, 'select2-result-label')]"
                    ]

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
                        # Small delay to allow any modals to appear
                        time.sleep(2)
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

    def __handle_performed_by_modal(self):
        """
        Handle the performedByForm modal if it appears after selecting tests.
        """
        try:
            # Wait a moment for modal to potentially appear
            time.sleep(2)
            
            # Check if the performedByForm modal is visible
            modal = self.driver.find_element(By.ID, "performedByForm")
            if modal.is_displayed():
                logging.info("PerformedByForm modal detected")
                self.__take_screenshot("PERFORMED_BY_MODAL_DETECTED")
                
                # Small delay to ensure modal is fully loaded
                time.sleep(1)
                
                # Look for the Select button and click it
                try:
                    select_btn = self.wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[@type='submit' and contains(@class, 'antoclose') and contains(text(), 'Select')]")))
                    # Additional check to ensure select button is visible
                    if not select_btn.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", select_btn)
                        time.sleep(0.5)
                    select_btn.click()
                    logging.info("Clicked Select button in performedByForm modal")
                    self.__take_screenshot("PERFORMED_BY_MODAL_SELECT_CLICKED")
                    
                    # Wait for modal to close
                    self.wait.until(EC.invisibility_of_element_located((By.ID, "performedByForm")))
                    logging.info("PerformedByForm modal closed")
                except TimeoutException:
                    # Try alternative XPath for the Select button
                    try:
                        select_btn = self.wait.until(EC.element_to_be_clickable(
                            (By.XPATH, "//button[contains(@class, 'btn-primary') and contains(text(), 'Select')]")))
                        # Additional check to ensure select button is visible
                        if not select_btn.is_displayed():
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", select_btn)
                            time.sleep(0.5)
                        select_btn.click()
                        logging.info("Clicked Select button (alternative) in performedByForm modal")
                        self.__take_screenshot("PERFORMED_BY_MODAL_SELECT_CLICKED_ALT")
                        
                        # Wait for modal to close
                        self.wait.until(EC.invisibility_of_element_located((By.ID, "performedByForm")))
                        logging.info("PerformedByForm modal closed")
                    except TimeoutException:
                        logging.warning("Could not find Select button in performedByForm modal")
                        self.__take_screenshot("PERFORMED_BY_MODAL_SELECT_NOT_FOUND")
                except Exception as click_e:
                    logging.warning(f"Failed to click Select button normally, trying JavaScript click: {str(click_e)}")
                    try:
                        # Additional check to ensure select button is visible
                        if not select_btn.is_displayed():
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", select_btn)
                            time.sleep(0.5)
                        self.driver.execute_script("arguments[0].click();", select_btn)
                        logging.info("JavaScript clicked Select button in performedByForm modal")
                        self.__take_screenshot("PERFORMED_BY_MODAL_JS_CLICK")
                        
                        # Wait for modal to close
                        self.wait.until(EC.invisibility_of_element_located((By.ID, "performedByForm")))
                        logging.info("PerformedByForm modal closed")
                    except Exception as js_e:
                        logging.error(f"JavaScript click also failed: {str(js_e)}")
                        raise
            else:
                logging.info("No performedByForm modal detected")
        except Exception as e:
            # If modal doesn't exist or isn't visible, that's fine
            logging.info("No performedByForm modal found or not visible")

    def __select_credit_payment(self):
        """
        Select Credit payment option and Cash payment mode, then input 0 as paid amount.
        """
        try:
            # Select Credit as payment type
            payment_type_select = self.wait.until(EC.presence_of_element_located((By.NAME, "paymentType")))
            # Scroll to the element to ensure it's visible
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", payment_type_select)
            time.sleep(0.5)
            Select(payment_type_select).select_by_value("Credit")
            logging.info("Selected 'Credit' as payment type")
            self.__take_screenshot("CREDIT_PAYMENT_TYPE_SELECTED")
            
            # Wait for payment mode container to appear
            payment_mode_container = self.wait.until(EC.visibility_of_element_located((By.ID, "paymentModeContainer")))
            logging.info("Payment mode container appeared")
            
            # Small delay to ensure the container is fully loaded
            time.sleep(1)
            
            # Select Cash as payment mode
            payment_mode_select = self.wait.until(EC.presence_of_element_located((By.NAME, "paymentMode")))
            # Additional check to ensure payment mode select is visible
            if not payment_mode_select.is_displayed():
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", payment_mode_select)
                time.sleep(0.5)
            Select(payment_mode_select).select_by_value("Cash")
            logging.info("Selected 'Cash' as payment mode")
            self.__take_screenshot("CASH_PAYMENT_MODE_SELECTED")
            
            # Get the gross total amount
            grand_total_element = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".grandTotal .rounded_grand_total")))
            grand_total_text = grand_total_element.text
            logging.info(f"Grand total text: {grand_total_text}")
            
            # Extract numeric value from the text (remove Rs. and any other non-numeric characters)
            grand_total_match = re.search(r'(\d+)', grand_total_text)
            if grand_total_match:
                grand_total = int(grand_total_match.group(1))
                logging.info(f"Extracted grand total: {grand_total}")
                
                # For credit billing, we don't pay any amount
                # Enter 0 in paid amount field
                paid_amount_field = self.wait.until(EC.presence_of_element_located((By.ID, "paidamts")))
                # Scroll to the element to ensure it's visible
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", paid_amount_field)
                time.sleep(0.5)
                # Additional check to ensure paid amount field is visible
                if not paid_amount_field.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", paid_amount_field)
                    time.sleep(0.5)
                paid_amount_field.clear()
                paid_amount_field.send_keys("0")
                logging.info("Entered 0 in paid amount field for credit billing")
                self.__take_screenshot("ZERO_AMOUNT_ENTERED")
            else:
                logging.warning("Could not extract grand total amount")
                self.__take_screenshot("GRAND_TOTAL_EXTRACTION_FAILED")
                
        except Exception as e:
            logging.warning(f"Failed to select credit payment: {str(e)}")
            self.__take_screenshot("CREDIT_PAYMENT_ERROR")

    def __handle_outstanding_balance_alert(self):
        """
        Handle the outstanding balance alert dialog if it appears.
        """
        try:
            # Wait a moment for alert to potentially appear
            time.sleep(2)
            
            # Check if the alert dialog is visible
            alert_dialogs = self.driver.find_elements(By.CLASS_NAME, "ui-dialog")
            for alert_dialog in alert_dialogs:
                if alert_dialog.is_displayed():
                    # Check if it's the outstanding balance alert
                    title_elements = alert_dialog.find_elements(By.CLASS_NAME, "ui-dialog-title")
                    if title_elements and "Alert" in title_elements[0].text:
                        message_elements = alert_dialog.find_elements(By.ID, "lblMessage")
                        if message_elements and "outstanding balance" in message_elements[0].text:
                            logging.info("Outstanding balance alert detected")
                            self.__take_screenshot("OUTSTANDING_BALANCE_ALERT_DETECTED")
                            
                            # Look for the Okay button and click it
                            try:
                                okay_btn = alert_dialog.find_element(By.CLASS_NAME, "confirm")
                                okay_btn.click()
                                logging.info("Clicked Okay button in outstanding balance alert")
                                self.__take_screenshot("OUTSTANDING_BALANCE_ALERT_OKAY_CLICKED")
                                
                                # Wait for alert to close
                                self.wait.until(EC.invisibility_of_element(alert_dialog))
                                logging.info("Outstanding balance alert closed")
                                return
                            except Exception as e:
                                logging.warning(f"Could not click Okay button in outstanding balance alert: {str(e)}")
                                self.__take_screenshot("OUTSTANDING_BALANCE_ALERT_OKAY_FAILED")
            
            logging.info("No outstanding balance alert detected")
        except Exception as e:
            # If alert doesn't exist or isn't visible, that's fine
            logging.info("No outstanding balance alert found or not visible")

    def __handle_recommended_test_notification(self):
        """
        Handle the 'Recommended Test For Emergency' notification if it appears.
        Simply detect it and continue without trying to close it to avoid too many errors in console log.
        """
        try:
            # Wait a moment for notification to potentially appear
            time.sleep(2)
            
            # Check if the recommended test notification is visible
            notification_title_elements = self.driver.find_elements(By.XPATH, "//h4[contains(text(), 'Recommended Test For Emergency')]")
            if notification_title_elements:
                logging.info("Recommended Test For Emergency notification detected (continuing without interaction)")
                self.__take_screenshot("RECOMMENDED_TEST_NOTIFICATION_DETECTED")
                # Just wait a bit for it to be visible
                time.sleep(1)
            else:
                logging.info("No Recommended Test For Emergency notification detected")
        except Exception as e:
            # If notification doesn't exist or isn't visible, that's fine
            logging.info("No Recommended Test For Emergency notification found or not visible")

    def __submit_billing_form(self):
        """
        Submit the billing form, ensuring no modals are open.
        """
        try:
            # Click Submit button
            submit_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "sbmtbtn")))
            # Additional check to ensure submit button is visible
            if not submit_btn.is_displayed():
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", submit_btn)
                time.sleep(1)
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                submit_btn
            )
            time.sleep(1)  # Increased from 0.5 to 1 second
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
            except Exception as click_e:
                logging.warning(f"Failed to click Submit button normally, trying JavaScript click: {str(click_e)}")
                try:
                    self.driver.execute_script("arguments[0].click();", submit_btn)
                    logging.info("JavaScript clicked Submit button")
                    self.__take_screenshot("BILLING_FORM_SUBMITTED_JS")
                except Exception as js_e:
                    logging.error(f"JavaScript click also failed: {str(js_e)}")
                    raise
            
        except Exception as e:
            self.__take_screenshot("SUBMIT_BUTTON_ERROR")
            logging.error(f"Failed to submit billing form: {str(e)}")
            raise

    def __handle_billing_success_notification(self):
        """
        Handle success notification for billing.
        """
        try:
            # Small delay to allow notification to appear
            time.sleep(2)
            success_message_locator = (By.XPATH, "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')] | //div[contains(@class, 'ui-pnotify') and contains(@class, 'success')] | //div[contains(@class, 'alert') and contains(@class, 'alert-success')]")
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
                        EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'Success') or contains(text(), 'Bill created') or contains(text(), 'successful')]")))
                    logging.info("Bill creation confirmation detected")
                    self.__take_screenshot("BILL_CONFIRMATION")
                    return True
                except TimeoutException:
                    self.__take_screenshot("BILLING_SUBMISSION_RESULT")
                    logging.warning("No explicit billing success notification found, proceeding with caution")
                    return False

    def __capture_and_handle_bill_info(self, original_window):
        """
        Capture Bill No from new window and Bill ID and Patient ID from main page by hovering over Print Bill button.
        """
        wait_for_windows = WebDriverWait(self.driver, 20)
        try:
            # Wait for new window or tab to open
            wait_for_windows.until(lambda d: len(d.window_handles) > 1)
            logging.info(f"Number of windows: {len(self.driver.window_handles)}")
            
            # Switch to the new window or tab (avoid devtools windows)
            target_window = None
            bill_window_handle = None
            for window_handle in self.driver.window_handles:
                if window_handle != original_window:
                    self.driver.switch_to.window(window_handle)
                    current_url = self.driver.current_url
                    # Skip devtools and chrome://print/ windows which cannot be closed normally
                    if not current_url.startswith("devtools://") and not current_url.startswith("chrome://print/"):
                        target_window = window_handle
                        bill_window_handle = window_handle
                        break
                    elif current_url.startswith("chrome://print/"):
                        # This is a print dialog - we need to handle it differently
                        logging.info(f"Detected print dialog: {current_url}")
                        # Instead of closing, switch back to original window
                        self.driver.switch_to.window(original_window)
                        # Extract bill no from the original window
                        bill_no = self.__extract_bill_no_from_invoice_fallback()
                        if bill_no:
                            self.bill_no = bill_no
                            logging.info(f"Successfully captured Bill No: {self.bill_no}")
                        else:
                            logging.warning("Could not extract Bill No from invoice")
                        return  # Exit early since we've handled the print dialog
            else:
                # If no appropriate window found, try original window
                self.driver.switch_to.window(original_window)
                bill_no = self.__extract_bill_no_from_invoice_fallback()
                if bill_no:
                    self.bill_no = bill_no
                    logging.info(f"Successfully captured Bill No: {self.bill_no}")
                else:
                    logging.warning("Could not extract Bill No from invoice")
                target_window = None
            
            if target_window:
                logging.info(f"Switched to new window: {self.driver.current_url}")
                self.__take_screenshot("BILL_WINDOW")
                
                # Extract the bill No from the new window
                bill_no = self.__extract_bill_no_from_invoice()
                if bill_no:
                    self.bill_no = bill_no
                    logging.info(f"Successfully captured Bill No: {self.bill_no}")
                else:
                    logging.warning("Could not extract Bill No from invoice")
                
                # Close the bill window and switch back to the original window
                self.driver.close()
                self.driver.switch_to.window(original_window)
                logging.info("Closed bill window and switched back to original window")
                
                else:
                logging.warning("No bill window found. Trying to find Bill No in current window")
                # Switch back to original window if we couldn't find a proper bill window
                self.driver.switch_to.window(original_window)
                self.bill_no = self.__capture_bill_no_fallback()
                logging.info(f"Captured Bill No: {self.bill_no}")
            
            # Capture Bill ID and Patient ID by hovering over Print Bill button
            # Small delay to ensure page is loaded
            time.sleep(1)
            try:
                print_bill_btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "printBtn")))
                # Additional check to ensure print button is visible
                if not print_bill_btn.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_bill_btn)
                    time.sleep(0.5)
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_bill_btn)
                time.sleep(0.5)
                actions = ActionChains(self.driver)
                actions.move_to_element(print_bill_btn).perform()
                # Longer delay to ensure tooltip is fully loaded
                time.sleep(3)
                self.__take_screenshot("PRINT_BILL_HOVER")
                title = print_bill_btn.get_attribute("data-original-title")
                logging.info(f"Tooltip content: {title}")
                if title:
                    # Extract Bill ID from tooltip with more robust regex
                    bill_id_match = re.search(r'Bill Id\s*:\s*.*?>\s*(\d+)\s*<', title, re.IGNORECASE | re.DOTALL)
                    if not bill_id_match:
                        bill_id_match = re.search(r'Bill Id\s*:\s*(\d+)', title, re.IGNORECASE)
                    if not bill_id_match:
                        bill_id_match = re.search(r'Bill\s*Id[^\d]*(\d+)', title, re.IGNORECASE)
                    if not bill_id_match:
                        bill_id_match = re.search(r'BILL\s*ID[^\d]*(\d+)', title, re.IGNORECASE)
                    if bill_id_match:
                        self.bill_id = bill_id_match.group(1)
                        logging.info(f"Captured Bill ID from tooltip: {self.bill_id}")
                    else:
                        logging.warning("Could not find Bill ID in tooltip")
                        self.__take_screenshot("BILL_ID_TOOLTIP_NOT_FOUND")
                    
                    # Extract Patient ID from tooltip with more robust regex
                    patient_id_match = re.search(r'Patient Id\s*:\s*.*?>\s*(\d+)\s*<', title, re.IGNORECASE | re.DOTALL)
                    if not patient_id_match:
                        patient_id_match = re.search(r'Patient Id\s*:\s*(\d+)', title, re.IGNORECASE)
                    if not patient_id_match:
                        patient_id_match = re.search(r'Patient\s*Id[^\d]*(\d+)', title, re.IGNORECASE)
                    if not patient_id_match:
                        patient_id_match = re.search(r'PATIENT\s*ID[^\d]*(\d+)', title, re.IGNORECASE)
                    if patient_id_match:
                        self.patient_id = patient_id_match.group(1)
                        logging.info(f"Captured Patient ID from tooltip: {self.patient_id}")
                    else:
                        logging.warning("Could not find Patient ID in tooltip")
                        self.__take_screenshot("PATIENT_ID_TOOLTIP_NOT_FOUND")
                else:
                    logging.warning("No data-original-title in print button")
                    self.__take_screenshot("BILL_ID_NO_TOOLTIP")
                actions.move_by_offset(0, -100).perform()
                
                # Fallback: Try extracting Bill ID and Patient ID from page elements
                if not self.bill_id:
                    bill_id_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Bill Id') or contains(text(), 'Bill ID') or contains(@id, 'billId') or contains(@name, 'billId')]")
                    for elem in bill_id_elements:
                        text = elem.text
                        # Try different regex patterns to extract bill ID
                        match = re.search(r'Bill Id\s*:?\\s*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'Bill ID\s*:?\\s*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'Bill\s*Id[^\d]*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'BILL\s*ID[^\d]*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'(\d+)', text)
                        if match:
                            self.bill_id = match.group(1)
                            logging.info(f"Captured Bill ID from page element: {self.bill_id}")
                            break
                    if not self.bill_id:
                        logging.warning("Could not find Bill ID in page elements")
                        self.__take_screenshot("BILL_ID_PAGE_NOT_FOUND")
                
                if not self.patient_id:
                    patient_id_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Patient Id') or contains(text(), 'Patient ID') or contains(@id, 'patientId') or contains(@name, 'patientId')]")
                    for elem in patient_id_elements:
                        text = elem.text
                        # Try different regex patterns to extract patient ID
                        match = re.search(r'Patient Id\s*:?\\s*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'Patient ID\s*:?\\s*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'Patient\s*Id[^\d]*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'PATIENT\s*ID[^\d]*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'(\d+)', text)
                        if match:
                            self.patient_id = match.group(1)
                            logging.info(f"Captured Patient ID from page element: {self.patient_id}")
                            break
                    if not self.patient_id:
                        logging.warning("Could not find Patient ID in page elements")
                        self.__take_screenshot("PATIENT_ID_PAGE_NOT_FOUND")
            except Exception as e:
                logging.error(f"Error capturing Bill ID and Patient ID: {str(e)}")
                self.__take_screenshot("BILL_PATIENT_ID_CAPTURE_ERROR")
            
        except TimeoutException:
            logging.warning("No new window appeared. Trying to find Bill No in current window")
            # Make sure we're on the original window
            self.driver.switch_to.window(original_window)
            # Small delay to ensure we're on the correct window
            time.sleep(1)
            self.bill_no = self.__capture_bill_no_fallback()
            logging.info(f"Captured Bill No: {self.bill_no}")
            # Also attempt to capture Bill ID and Patient ID
            # Small delay to ensure page is loaded
            time.sleep(1)
            try:
                print_bill_btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "printBtn")))
                # Additional check to ensure print button is visible
                if not print_bill_btn.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_bill_btn)
                    time.sleep(0.5)
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_bill_btn)
                time.sleep(0.5)
                actions = ActionChains(self.driver)
                actions.move_to_element(print_bill_btn).perform()
                # Longer delay to ensure tooltip is fully loaded
                time.sleep(3)
                self.__take_screenshot("PRINT_BILL_HOVER_FALLBACK")
                title = print_bill_btn.get_attribute("data-original-title")
                logging.info(f"Tooltip content (fallback): {title}")
                if title:
                    # Extract Bill ID from tooltip with more robust regex
                    bill_id_match = re.search(r'Bill Id\s*:\s*.*?>\s*(\d+)\s*<', title, re.IGNORECASE | re.DOTALL)
                    if not bill_id_match:
                        bill_id_match = re.search(r'Bill Id\s*:\s*(\d+)', title, re.IGNORECASE)
                    if not bill_id_match:
                        bill_id_match = re.search(r'Bill\s*Id[^\d]*(\d+)', title, re.IGNORECASE)
                    if not bill_id_match:
                        bill_id_match = re.search(r'BILL\s*ID[^\d]*(\d+)', title, re.IGNORECASE)
                    if bill_id_match:
                        self.bill_id = bill_id_match.group(1)
                        logging.info(f"Captured Bill ID from tooltip (fallback): {self.bill_id}")
                    else:
                        logging.warning("Could not find Bill ID in tooltip (fallback)")
                        self.__take_screenshot("BILL_ID_TOOLTIP_NOT_FOUND_FALLBACK")
                    
                    # Extract Patient ID from tooltip with more robust regex
                    patient_id_match = re.search(r'Patient Id\s*:\s*.*?>\s*(\d+)\s*<', title, re.IGNORECASE | re.DOTALL)
                    if not patient_id_match:
                        patient_id_match = re.search(r'Patient Id\s*:\s*(\d+)', title, re.IGNORECASE)
                    if not patient_id_match:
                        patient_id_match = re.search(r'Patient\s*Id[^\d]*(\d+)', title, re.IGNORECASE)
                    if not patient_id_match:
                        patient_id_match = re.search(r'PATIENT\s*ID[^\d]*(\d+)', title, re.IGNORECASE)
                    if patient_id_match:
                        self.patient_id = patient_id_match.group(1)
                        logging.info(f"Captured Patient ID from tooltip (fallback): {self.patient_id}")
                    else:
                        logging.warning("Could not find Patient ID in tooltip (fallback)")
                        self.__take_screenshot("PATIENT_ID_TOOLTIP_NOT_FOUND_FALLBACK")
                else:
                    logging.warning("No data-original-title in print button (fallback)")
                    self.__take_screenshot("BILL_ID_NO_TOOLTIP_FALLBACK")
                actions.move_by_offset(0, -100).perform()
                
                # Fallback: Try extracting Bill ID and Patient ID from page elements
                if not self.bill_id:
                    bill_id_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Bill Id') or contains(text(), 'Bill ID') or contains(@id, 'billId') or contains(@name, 'billId')]")
                    for elem in bill_id_elements:
                        text = elem.text
                        # Try different regex patterns to extract bill ID
                        match = re.search(r'Bill Id\s*:?\\s*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'Bill ID\s*:?\\s*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'Bill\s*Id[^\d]*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'BILL\s*ID[^\d]*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'(\d+)', text)
                        if match:
                            self.bill_id = match.group(1)
                            logging.info(f"Captured Bill ID from page element (fallback): {self.bill_id}")
                            break
                    if not self.bill_id:
                        logging.warning("Could not find Bill ID in page elements (fallback)")
                        self.__take_screenshot("BILL_ID_PAGE_NOT_FOUND_FALLBACK")
                
                if not self.patient_id:
                    patient_id_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Patient Id') or contains(text(), 'Patient ID') or contains(@id, 'patientId') or contains(@name, 'patientId')]")
                    for elem in patient_id_elements:
                        text = elem.text
                        # Try different regex patterns to extract patient ID
                        match = re.search(r'Patient Id\s*:?\\s*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'Patient ID\s*:?\\s*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'Patient\s*Id[^\d]*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'PATIENT\s*ID[^\d]*(\d+)', text, re.IGNORECASE)
                        if not match:
                            match = re.search(r'(\d+)', text)
                        if match:
                            self.patient_id = match.group(1)
                            logging.info(f"Captured Patient ID from page element (fallback): {self.patient_id}")
                            break
                    if not self.patient_id:
                        logging.warning("Could not find Patient ID in page elements (fallback)")
                        self.__take_screenshot("PATIENT_ID_PAGE_NOT_FOUND_FALLBACK")
            except Exception as e:
                logging.error(f"Error capturing Bill ID and Patient ID (fallback): {str(e)}")
                self.__take_screenshot("BILL_PATIENT_ID_CAPTURE_ERROR_FALLBACK")
        
        # Force wait to ensure info is captured
        time.sleep(2)

    def __extract_bill_no_from_invoice_fallback(self):
        """
        Extract bill No from the current page as a fallback method.
        This is used when we can't access the new window (like print dialogs).
        """
        try:
            # Small delay to ensure page is loaded
            time.sleep(1)
            
            # Try to find bill no in page elements
            bill_elements = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Bill No:') or contains(text(), 'Bill No') or contains(text(), 'Bill ID') or contains(text(), 'BillId')]")
            for element in bill_elements:
                text = element.text
                bill_match = re.search(r'Bill\s*No[^\d]*(\d+)', text, re.IGNORECASE)
                if bill_match:
                    bill_no = bill_match.group(1)
                    logging.info(f"Found bill No in page element: {bill_no}")
                    return bill_no
            
            # Try to get bill ID from URL
            url = self.driver.current_url
            bill_id_match = re.search(r'[?&]billId=(\d+)', url)
            if bill_id_match:
                bill_no = bill_id_match.group(1)
                logging.info(f"Found bill No in URL: {bill_no}")
                return bill_no
            
            # Try to find any element that might contain bill ID
            id_elements = self.driver.find_elements(By.XPATH, "//div[contains(@id, 'billNo') or contains(@id, 'billId') or contains(@name, 'billNo') or contains(@name, 'billId')] | //span[contains(@id, 'billNo') or contains(@id, 'billId') or contains(@name, 'billNo') or contains(@name, 'billId')]")
            for elem in id_elements:
                text = elem.text.strip()
                if text and text.isdigit():
                    logging.info(f"Found bill No in ID element: {text}")
                    return text
            
            # Try another fallback approach - look for any digits that could be bill no
            all_text = self.driver.find_element(By.TAG_NAME, "body").text
            bill_number_match = re.search(r'Bill\s*No[^\d]*(\d+)', all_text, re.IGNORECASE)
            if bill_number_match:
                bill_no = bill_number_match.group(1)
                logging.info(f"Found bill No in page text: {bill_no}")
                return bill_no
            
            logging.warning("Could not find bill No in any element using fallback method")
            return None
        except Exception as e:
            logging.error(f"Error extracting bill No from invoice using fallback: {str(e)}")
            self.__take_screenshot("BILL_NO_EXTRACTION_FALLBACK_ERROR")
            return None

    def __extract_bill_no_from_invoice(self):
        """
        Extract bill No from the invoice page.
        """
        try:
            # Small delay to ensure page is loaded
            time.sleep(1)
            
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
            # Small delay to ensure page is loaded
            time.sleep(1)
            
            url = self.driver.current_url
            bill_no_match = re.search(r'[?&]billId=(\d+)', url)
            if bill_no_match:
                return bill_no_match.group(1)
            
            bill_elements = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Bill') and contains(text(), 'ID') or contains(text(), 'No')] | //strong[contains(text(), 'Bill No')] | //div[contains(text(), 'Bill No')]")
            for elem in bill_elements:
                text = elem.text
                # Try different regex patterns
                no_match = re.search(r'Bill\s*(ID|No)?\s*:?\\s*(\d+)', text, re.IGNORECASE)
                if not no_match:
                    no_match = re.search(r'Bill\s*#?\s*(\d+)', text, re.IGNORECASE)
                if not no_match:
                    no_match = re.search(r'(?:I)?(\d+)', text)
                if no_match:
                    return no_match.group(1) if no_match.lastindex == 1 else no_match.group(2)
            
            id_elements = self.driver.find_elements(By.XPATH, "//strong[contains(text(), 'ID')]/following-sibling::span | //*[@id='billNo'] | //*[@name='billNo']")
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
        if self.bill_no and self.bill_no != "unknown" and self.bill_no != "error":
            bill_json_file = os.path.join(bill_nos_dir, f"{self.bill_no}.json")
            bill_data = {
                "bill_no": self.bill_no,
                "bill_id": self.bill_id if hasattr(self, 'bill_id') and self.bill_id and self.bill_id != "unknown" else "unknown",
                "patient_id": self.patient_id if hasattr(self, 'patient_id') and self.patient_id and self.patient_id != "unknown" else "unknown",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                with open(bill_json_file, "w") as f:
                    json.dump(bill_data, f, indent=4)
                logging.info(f"Bill information saved to {bill_json_file}")
            except Exception as e:
                logging.error(f"Error saving bill information to {bill_json_file}: {str(e)}")
                self.__take_screenshot("BILL_JSON_SAVE_ERROR")
        elif self.bill_no:
            logging.warning(f"Bill number is invalid: {self.bill_no}, not saving bill information")

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
                        logging.warning(f"Window {handle} already closed or not accessible: {str(e)}")
            
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
    
    suite = unittest.TestLoader().loadTestsFromTestCase(EMRBillingCredit)
    runner.run(suite)