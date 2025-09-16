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
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from utilities.config_loader import ConfigLoader
import xml.etree.ElementTree as ET


# Folder configuration
screenshot_dir = os.path.join("screenshots", "emr_combined")
report_dir = os.path.join("reports", "emr_combined")
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
        
        # Extract bill_no, bill_id and patient_id from the test case
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
        
        # Get the XML report file
        xml_file = os.path.join(self.output, 'TEST-CombinedEMRRegistrationBilling.xml')
        
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
                    
                    # Add bill_no, bill_id and patient_id as attributes
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
                    logging.info(f"Added Bill No {bill_no}, Bill ID {bill_id} and Patient ID {patient_id} to XML report")
            except Exception as e:
                logging.error(f"Error updating XML report: {str(e)}")
        
        return result


class CombinedEMRRegistrationBilling(unittest.TestCase):
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
        cls.driver = webdriver.Chrome(options=chrome_options)
        cls.driver.maximize_window()
        cls.wait = WebDriverWait(cls.driver, 20)
        cls.base_url = cls.config["base_url"]
        cls.valid_username = cls.config["username"]
        cls.valid_password = cls.config["password"]

    def setUp(self):
        """
        Test-level setup: Navigate to base URL, login, and initialize patient_id, bill_no and bill_id.
        """
        self.driver.get(self.base_url)
        self.__login()
        self.patient_id = None
        self.bill_no = None
        self.bill_id = None

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
        Get the latest patient ID from the patient_ids folder.
        Returns the most recent patient ID based on file modification time.
        """
        try:
            # Get all JSON files from patient_ids folder
            json_files = glob.glob(os.path.join(patient_json_dir, "*.json"))
            
            if not json_files:
                raise ValueError("No patient ID files found in patient_ids folder")
            
            # Find the most recent file
            latest_file = max(json_files, key=os.path.getmtime)
            
            # Extract patient ID from filename (e.g., "2134.json" -> "2134")
            filename = os.path.basename(latest_file)
            patient_id = os.path.splitext(filename)[0]
            
            logging.info(f"Latest patient ID found: {patient_id}")
            return patient_id
            
        except Exception as e:
            logging.error(f"Error getting latest patient ID: {str(e)}")
            raise

    def test_combined_emr_registration_and_billing(self):
        """
        Combined test method: 
        1. Perform EMR registration
        2. Navigate to EMR billing
        3. Use the captured patient ID for billing
        4. Complete the billing process
        """
        # Part 1: EMR Registration
        logging.info("Starting EMR Registration...")
        self.__perform_emr_registration()
        
        # Part 2: EMR Billing using the registered patient
        logging.info("Starting EMR Billing...")
        self.__perform_emr_billing()

    def __perform_emr_registration(self):
        """
        Perform EMR registration process
        """
        self.wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@id='patient_menu']/a"))).click()
        self.wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[@href='http://lunivacare.ddns.net:8080/himsnew/ipd/register/Emergency']"))).click()
        logging.info("Navigated to EMR Registration page")
        self.__take_screenshot("EMR_REGISTER_PAGE")

        mobile_field = self.wait.until(EC.presence_of_element_located((By.ID, "mobile-number")))
        mobile_field.send_keys("9800000002")
        logging.info("Entered mobile number")
        self.__take_screenshot("MOBILE_ENTERED")
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
        self.__take_screenshot("FORM_FILLED")

        self.wait.until(EC.element_to_be_clickable((By.ID, "submitNewButton"))).click()
        logging.info("Form submitted")
        self.__take_screenshot("FORM_SUBMITTED")

        self.__handle_success_notification()
        self.patient_id = self.__capture_patient_id()
        logging.info(f"Captured Patient ID: {self.patient_id}")

        # Wait for Print Sticker button to be clickable and take screenshot
        try:
            print_sticker_btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "printStikerBtn")))
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_sticker_btn)
            time.sleep(1)  # Extended pause to ensure visibility
            sticker_screenshot_path = os.path.join(screenshot_dir, f"PRINT_STICKER_BTN_{self.patient_id}_{time.strftime('%Y%m%d_%H%M%S')}.png")
            print_sticker_btn.screenshot(sticker_screenshot_path)
            logging.info(f"Print Sticker button screenshot saved: {sticker_screenshot_path}")
        except Exception as e:
            logging.warning(f"Could not take screenshot of Print Sticker button: {str(e)}")
            self.__take_screenshot("PRINT_STICKER_ERROR")

    def __perform_emr_billing(self):
        """
        Perform EMR billing process using the registered patient ID
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

            # Use the patient ID from registration (or get latest from folder as fallback)
            patient_id_to_use = self.patient_id if self.patient_id else self.__get_latest_patient_id()

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
        Select CBC and ABO & Rh Factor tests from dropdown and handle performedByModal
        """
        short_wait = WebDriverWait(self.driver, 5)
        tests = ["Complete Blood Cell Count", "ABO & Rh Factor"]
        
        for test_name in tests:
            try:
                # Locate and open the test dropdown
                try:
                    dropdown = short_wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//span[starts-with(@id, 'select2-chosen-')]"))
                    )
                except TimeoutException:
                    dropdown = short_wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//span[starts-with(@id, 'select2-chosen-')]"))
                    )
                dropdown.click()
                logging.info(f"Test dropdown clicked for {test_name}")
                self.__take_screenshot(f"TEST_DROPDOWN_CLICKED_{test_name.replace(' ', '_')}")
                time.sleep(0.5)

                # Locate search input
                try:
                    search_input = short_wait.until(EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@class, 'select2-drop-active')]//input"))
                    )
                except TimeoutException:
                    search_input = short_wait.until(EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@class, 'select2-drop-active')]//input"))
                    )
                
                search_input.clear()
                search_input.send_keys(test_name)
                logging.info(f"Entered {test_name} in search")
                time.sleep(1)

                # Select the test
                try:
                    test_option = short_wait.until(EC.element_to_be_clickable(
                        (By.XPATH, f"//div[contains(@class, 'select2-result-label') and contains(text(), '{test_name}')]"))
                    )
                except TimeoutException:
                    test_option = short_wait.until(EC.element_to_be_clickable(
                        (By.XPATH, f"//div[contains(text(), '{test_name}')]"))
                    )
                test_option.click()
                logging.info(f"{test_name} selected")
                self.__take_screenshot(f"{test_name.replace(' ', '_')}_SELECTED")

                # Handle performedByModal for non-pathology tests
                if test_name == "ABO & Rh Factor":
                    try:
                        modal = short_wait.until(EC.visibility_of_element_located(
                            (By.ID, "performedByModal")))
                        logging.info("Performed By modal detected")
                        self.__take_screenshot("PERFORMED_BY_MODAL")

                        # Verify default selection is SELF
                        select_element = short_wait.until(EC.presence_of_element_located(
                            (By.XPATH, "//span[@class='select2-chosen' and text()='SELF']")))
                        logging.info("Default selection 'SELF' confirmed")

                        # Click Select button
                        select_btn = short_wait.until(EC.element_to_be_clickable(
                            (By.XPATH, "//button[@type='submit' and contains(@class, 'antoclose')]")))
                        select_btn.click()
                        logging.info("Clicked Select button in performedByModal")
                        self.__take_screenshot("PERFORMED_BY_MODAL_SUBMITTED")

                        # Wait for modal to close
                        short_wait.until(EC.invisibility_of_element_located((By.ID, "performedByModal")))
                        logging.info("Performed By modal closed")

                    except TimeoutException:
                        logging.warning("Performed By modal did not appear or already closed")
                        self.__take_screenshot("NO_PERFORMED_BY_MODAL")

            except Exception as e:
                self.__take_screenshot(f"{test_name.replace(' ', '_')}_SELECTION_ERROR")
                logging.error(f"Failed to select {test_name}: {str(e)}")
                raise

    def __submit_billing_form(self):
        """
        Submit the billing form
        """
        try:
            submit_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "sbmtbtn")))
            if not submit_btn:
                submit_btn = self.wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[@type='submit' and contains(text(), 'Submit')]"))
                )
            
            # Scroll to submit button
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                submit_btn
            )
            time.sleep(0.5)
            
            submit_btn.click()
            logging.info("Clicked Submit button to complete the billing process")
            self.__take_screenshot("BILLING_FORM_SUBMITTED")
            
        except Exception as e:
            self.__take_screenshot("SUBMIT_BUTTON_ERROR")
            logging.error(f"Failed to submit billing form: {str(e)}")
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
                proceed_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.ID, "proceedToRegister")))
                self.driver.execute_script("arguments[0].click();", proceed_btn)
                logging.info("Clicked proceed button")
                self.__take_screenshot("MODAL_HANDLED")
                WebDriverWait(self.driver, 3).until(EC.invisibility_of_element_located(modal_locator))
        except TimeoutException:
            logging.info("No duplicate modal present")

    def __handle_success_notification(self):
        """
        Verify success notification after form submission.
        """
        try:
            notification = WebDriverWait(self.driver, 20).until(
                EC.visibility_of_element_located((By.XPATH,
                    "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')]"
                ))
            )
            logging.info("EMR registration successful")
            self.__take_screenshot("REGISTRATION_SUCCESS_NOTIFICATION")

            # Attempt to close notification gracefully
            try:
                close_btn = notification.find_element(By.CSS_SELECTOR, ".ui-pnotify-closer")
                self.driver.execute_script("arguments[0].click();", close_btn)
                WebDriverWait(self.driver, 5).until(EC.invisibility_of_element_located(notification))
            except Exception:
                logging.info("Notification auto-closed or close button not needed")
        except TimeoutException:
            self.__take_screenshot("REGISTRATION_SUBMISSION_ERROR")
            logging.error("Success notification not found")
            raise

    def __handle_billing_success_notification(self):
        """
        Handle success notification for billing
        """
        try:
            success_message_locator = (By.XPATH, "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')]")
            notification = WebDriverWait(self.driver, 20).until(
                EC.visibility_of_element_located(success_message_locator))
            logging.info("Billing success notification detected.")
            self.__take_screenshot("BILLING_SUCCESS_NOTIFICATION")
            return True
        except TimeoutException:
            try:
                notification = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'ui-pnotify-container') or contains(@class, 'alert-success')]")))
                logging.info("Generic billing success notification detected.")
                self.__take_screenshot("GENERIC_BILLING_SUCCESS_NOTIFICATION")
                return True
            except TimeoutException:
                try:
                    confirmation = WebDriverWait(self.driver, 5).until(
                        EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'Success') or contains(text(), 'Bill created')]")))
                    logging.info("Bill creation confirmation detected.")
                    self.__take_screenshot("BILL_CONFIRMATION")
                    return True
                except TimeoutException:
                    self.__take_screenshot("BILLING_SUBMISSION_RESULT")
                    logging.warning("No explicit billing success notification found, proceeding with caution")
                    return False

    def __capture_patient_id(self):
        """
        Capture patient ID from either a new window or URL change after submission.
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
        self.__take_screenshot("PATIENT_ID_CAPTURED")
        return patient_id

    def __capture_and_handle_bill_info(self, original_window):
        """
        Capture Bill No from new window and Bill ID from main page by hovering over Print Bill button
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
                time.sleep(0.5)  # Ensure button is in view
                # Hover over the button to trigger tooltip
                actions = ActionChains(self.driver)
                actions.move_to_element(print_bill_btn).perform()
                time.sleep(2)  # Extended wait for tooltip to appear
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
                # Move mouse away to avoid interference
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
                time.sleep(0.5)  # Ensure button is in view
                # Hover over the button to trigger tooltip
                actions = ActionChains(self.driver)
                actions.move_to_element(print_bill_btn).perform()
                time.sleep(2)  # Extended wait for tooltip to appear
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
                # Move mouse away to avoid interference
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

    def __extract_id_from_url(self, url):
        """
        Extract patient ID from the 'create_stiker' URL using regex.
        """
        match = re.search(r'/create_stiker/(\d+)', url)
        if match:
            return match.group(1)
        raise ValueError(f"Patient ID not found in URL: {url}")

    def __extract_bill_no_from_invoice(self):
        """Extract bill No from the invoice page."""
        try:
            # Wait for the bill information to load
            bill_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'Bill No:') or contains(strong/text(), 'Bill No:')]"))
            )
            
            bill_text = bill_element.text
            bill_match = re.search(r'Bill No:\s*(?:I)?(\d+)', bill_text)
            
            if bill_match:
                bill_no = bill_match.group(1)
                logging.info(f"Found bill No in invoice: {bill_no}")
                return bill_no
            
            # Try alternative approaches
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
        """Fallback method to capture bill No from current page"""
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

    def __extract_bill_id_from_tooltip(self):
        """
        Extract Bill ID from Print Bill button tooltip
        """
        try:
            print_bill_btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "printBtn")))
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_bill_btn)
            time.sleep(0.5)  # Ensure button is in view
            
            # Hover over the button to trigger tooltip
            actions = ActionChains(self.driver)
            actions.move_to_element(print_bill_btn).perform()
            time.sleep(2)  # Extended wait for tooltip to appear
            self.__take_screenshot("PRINT_BILL_HOVER")
            
            # Get tooltip content from data-original-title attribute
            title = print_bill_btn.get_attribute("data-original-title")
            logging.info(f"Tooltip content: {title}")
            
            if title:
                patterns = [
                    r'Bill Id\s*:\s*.*?>\s*(\d+)\s*<',  # Updated pattern to capture Bill ID
                    r'Bill Id.*?(\d+)',  # Simple pattern
                    r'(\d+)'  # Any number in the element
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, title, re.IGNORECASE | re.DOTALL)
                    if match:
                        self.bill_id = match.group(1)
                        logging.info(f"Captured Bill ID from tooltip: {self.bill_id}")
                        break
                
                if not self.bill_id:
                    logging.warning("Could not find Bill ID in tooltip using regex patterns")
                    self.__take_screenshot("BILL_ID_TOOLTIP_NOT_FOUND")
                    
                    numbers = re.findall(r'\d+', title)
                    if numbers:
                        for num in numbers:
                            if int(num) > 100:  # Bill IDs are usually larger numbers
                                self.bill_id = num
                                logging.info(f"Captured Bill ID (fallback number): {self.bill_id}")
                                break
            else:
                logging.warning("No data-original-title in print button")
                self.__take_screenshot("BILL_ID_NO_TOOLTIP")
            
            # Move mouse away to avoid interference
            actions.move_by_offset(0, -100).perform()
            
            # Fallback: Try extracting Bill ID from page elements
            if not self.bill_id:
                self.__extract_bill_id_from_page_elements()
                
        except Exception as e:
            logging.error(f"Error capturing Bill ID: {str(e)}")
            self.__take_screenshot("BILL_ID_CAPTURE_ERROR")
            # Try fallback method
            self.__extract_bill_id_from_page_elements()

    def __extract_bill_id_from_page_elements(self):
        """
        Fallback method to extract Bill ID from page elements
        """
        try:
            # Look for elements containing Bill ID text
            bill_id_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Bill Id') or contains(text(), 'Bill ID')]")
            
            for elem in bill_id_elements:
                text = elem.text
                logging.info(f"Found element with Bill ID text: {text}")
                
                patterns = [
                    r'Bill Id\s*:?\s*(\d+)',
                    r'Bill ID\s*:?\s*(\d+)',
                    r'(\d+)'  # Any number in the element
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        self.bill_id = match.group(1)
                        logging.info(f"Captured Bill ID from page element: {self.bill_id}")
                        return
            
            # If still not found, look in all printBtn elements for title or data attributes
            print_buttons = self.driver.find_elements(By.CLASS_NAME, "printBtn")
            for btn in print_buttons:
                for attr in ['title', 'data-original-title', 'data-title']:
                    attr_value = btn.get_attribute(attr)
                    if attr_value:
                        logging.info(f"Checking {attr}: {attr_value}")
                        numbers = re.findall(r'\d+', attr_value)
                        if numbers:
                            for num in numbers:
                                if int(num) > 100:  # Assuming Bill IDs are larger numbers
                                    self.bill_id = num
                                    logging.info(f"Captured Bill ID from {attr}: {self.bill_id}")
                                    return
            
            if not self.bill_id:
                logging.warning("Could not find Bill ID in page elements")
                self.__take_screenshot("BILL_ID_PAGE_NOT_FOUND")
                
        except Exception as e:
            logging.error(f"Error in fallback Bill ID extraction: {str(e)}")
            self.__take_screenshot("BILL_ID_FALLBACK_ERROR")

    def tearDown(self):
        """
        Test-level teardown: Save patient ID and bill info to separate JSON files if captured.
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

        if self.bill_no:
            # Save bill information directly in bill_nos folder
            bill_json_file = os.path.join(bill_nos_dir, f"{self.bill_no.zfill(8)}.json")
            bill_data = {
                "bill_no": self.bill_no.zfill(8),
                "bill_id": self.bill_id if hasattr(self, 'bill_id') and self.bill_id else "unknown",
                "patient_id": self.patient_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(bill_json_file, "w") as f:
                json.dump(bill_data, f, indent=4)
            logging.info(f"Bill information saved to {bill_json_file}")

    @classmethod
    def tearDownClass(cls):
        """
        Class-level teardown: Clean up extra browser windows, keeping the main one open.
        """
        logging.info("Cleaning up browser windows...")
        try:
            # Ensure we have time to write XML before cleanup
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
    runner = XMLTestRunnerWithBillInfo(
        output=report_dir,
        verbosity=2,
        outsuffix=""
    )
    
    # Run the test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(CombinedEMRRegistrationBilling)
    runner.run(suite)