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
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoAlertPresentException
from utilities.config_loader import ConfigLoader
import xml.etree.ElementTree as ET

# Folder configuration
screenshot_dir = os.path.join("screenshots", "opd_combined")
report_dir = os.path.join("reports", "opd_combined")
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
        xml_file = os.path.join(self.output, 'TEST-ServiceRegistration.xml')
        
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

class ServiceRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load credentials FIRST
        cls.config = ConfigLoader.load_credentials("staging")

        # THEN initialize browser components
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--enable-javascript")
        chrome_options.add_experimental_option("detach", True)
        chrome_options.add_experimental_option("excludeSwitches", ["disable-popup-blocking"])
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-site-isolation-trials")
        chrome_options.add_argument("--kiosk-printing")  # Handle print dialogs
        cls.driver = webdriver.Chrome(options=chrome_options)
        cls.driver.maximize_window()
        # Initialize wait AFTER driver creation
        cls.wait = WebDriverWait(cls.driver, 20)
        cls.short_wait = WebDriverWait(cls.driver, 5)
        
        # Set credentials from config
        cls.base_url = cls.config["base_url"]
        cls.valid_username = cls.config["username"]
        cls.valid_password = cls.config["password"]

    def setUp(self):
        self.driver.get(self.base_url)
        self.__login()
        self.patient_id = None
        self.bill_no = None
        self.bill_id = None

    def __take_screenshot(self, name):
        filename = f"{screenshot_dir}/{name}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        try:
            self.driver.save_screenshot(filename)
            logging.info(f"Screenshot saved: {filename}")
        except Exception as e:
            logging.error(f"Error taking screenshot: {str(e)}")

    def __login(self):
        try:
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
        except Exception as e:
            self.__take_screenshot("LOGIN_FAILURE")
            logging.error(f"Login failed: {str(e)}")
            raise

    def test_service_registration(self):
        try:
            # Intercept print function to prevent dialog
            self.driver.execute_script("window.print = function() { console.log('Print function intercepted'); };")
            logging.info("Intercepted window.print function")

            # Navigate to Service Registration
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@id='patient_menu']/a"))).click()
            service_register_link = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//a[@href='http://lunivacare.ddns.net:8080/himsnew/patient/register']")))
            service_register_link.click()
            logging.info("Navigated to SERVICE Registration page")
            self.__take_screenshot("SERVICE_REGISTER_PAGE")

            # Fill mobile number and handle immediate modal
            mobile_field = self.wait.until(EC.presence_of_element_located((By.ID, "mobile-number")))
            mobile_field.send_keys("9800000000")
            logging.info("Entered mobile number")
            self.__take_screenshot("MOBILE_ENTERED")

            # Handle potential immediate modal after number entry
            time.sleep(2)
            self.__handle_duplicate_patient_modal()
            
            # Continue with rest of form
            designation = Select(self.driver.find_element(By.ID, "designation"))
            designation.select_by_value("Mr.")
            logging.info("Selected designation")

            self.driver.find_element(By.ID, "first-name").send_keys("John")
            self.driver.find_element(By.ID, "last-name").send_keys("Doe")
            self.driver.find_element(By.ID, "age").send_keys("30")
            ethnicity = Select(self.driver.find_element(By.ID, "ethnicity"))
            ethnicity.select_by_value("5")
            logging.info("Selected Ethnicity")
            logging.info("Entered personal details")

            # Handle address selection
            self.driver.find_element(By.XPATH, "//span[@id='select2-current-address-container']").click()
            search_field = self.wait.until(EC.presence_of_element_located(
                (By.XPATH, "//input[@class='select2-search__field']")))
            search_field.send_keys("Kathmandu")
            
            address_option = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//li[contains(@class, 'select2-results__option') and contains(text(), 'Kathmandu')]")))
            address_option.click()
            logging.info("Selected address")
            self.__take_screenshot("FORM_FILLED")

            # Submit form
            submit_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and contains(@class, 'btn-primary')]")))
            self.driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
            time.sleep(0.5)
            submit_btn.click()
            logging.info("Form submitted")
            self.__take_screenshot("FORM_SUBMITTED")

            # Wait before handling doctor selection modal
            time.sleep(2)
            
            # Handle doctor selection modal
            try:
                self.__handle_doctor_selection_modal()
                logging.info("Doctor selection modal handled successfully")
            except Exception as e:
                logging.error(f"Doctor selection failed: {str(e)}")
                self.__take_screenshot("DOCTOR_SELECTION_FAILED")
                raise
            
            # Store original window handle before billing
            original_window = self.driver.current_window_handle
            
            # Handle billing page
            self.__handle_billing_page()
            logging.info("Billing page handled successfully")
            self.__take_screenshot("BILLING_PAGE_HANDLED")
            
            # Handle success notification
            self.__handle_success_notification()
            
            # Capture Bill No and Bill ID
            self.__capture_and_handle_bill_info(original_window)
            
            # Add to XML report description
            self._testMethodDoc = f"Patient ID: {self.patient_id}, Bill No: {self.bill_no}, Bill ID: {self.bill_id}"

        except Exception as e:
            self.__take_screenshot("TEST_FAILURE")
            logging.error(f"Test failed: {str(e)}")
            raise

    def __handle_duplicate_patient_modal(self):
        """Handle modal appearing immediately after mobile number entry"""
        try:
            modal_locator = (By.XPATH, "//h4[contains(.,'Patient Info')]")
            proceed_btn_locator = (By.ID, "proceedToRegister")
        
            if len(self.driver.find_elements(*modal_locator)) > 0:
                logging.info("Duplicate patient modal detected")
                self.__take_screenshot("DUPLICATE_MODAL_PRESENT")
            
                proceed_btn = self.short_wait.until(EC.element_to_be_clickable(proceed_btn_locator))
                self.driver.execute_script("arguments[0].click();", proceed_btn)
                logging.info("Clicked proceed button")
                self.__take_screenshot("MODAL_HANDLED")
            
                self.short_wait.until(EC.invisibility_of_element_located(modal_locator))
            
        except TimeoutException:
            logging.info("No duplicate modal present or it disappeared quickly")
        except Exception as e:
            logging.info(f"Handling duplicate modal: {str(e)}")

    def __handle_doctor_selection_modal(self):
        """Handle the doctor selection modal with robust error handling"""
        try:
            modal = self.wait.until(
                EC.visibility_of_element_located(
                (By.XPATH, "//h4[@id='doctorModalLabel' and contains(text(),'Select Patient Doctor')]")
                )
            )
            logging.info("Doctor selection modal detected")
            self.__take_screenshot("DOCTOR_SELECTION_MODAL")

            select2_container = self.short_wait.until(
                EC.element_to_be_clickable((By.ID, "select2-docLists-container"))
            )

            aria_expanded = select2_container.get_attribute("aria-expanded")
            if aria_expanded == "false":
                logging.info("Opening the doctor selection dropdown")
                select2_container.click()

            dropdown_visible = self.short_wait.until(
                EC.visibility_of_element_located((By.CLASS_NAME, "select2-results__options"))
            )
            logging.info("Dropdown is open, proceeding to search for the doctor")

            search_field = self.short_wait.until(
                EC.element_to_be_clickable((By.CLASS_NAME, "select2-search__field"))
            )
            search_field.clear()
            doctor_name = "Dr. Usha Karki"
            search_field.send_keys(doctor_name)
            time.sleep(1)

            doctor_option = self.short_wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, f"//li[contains(@class, 'select2-results__option') and contains(text(), '{doctor_name}')]")
                )
            )
            logging.info(f"Selecting doctor: {doctor_name}")
            doctor_option.click()

            self.short_wait.until(
                EC.text_to_be_present_in_element((By.ID, "select2-docLists-container"), doctor_name)
            )
            logging.info("Doctor selection verified")
            self.__take_screenshot("DOCTOR_SELECTED")

            submit_btn = self.short_wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and contains(text(),'Submit')]"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", submit_btn)
            logging.info("Clicked Submit button on doctor selection modal")

            self.short_wait.until(
                EC.invisibility_of_element_located((By.ID, "doctorModal"))
            )
            logging.info("Doctor selection modal closed successfully")

        except Exception as e:
            error_message = f"Doctor selection error: {str(e)}"
            logging.error(error_message)
            self.__take_screenshot("DOCTOR_SELECTION_ERROR")
            raise

    def __handle_billing_page(self):
        """Handles test selection and submission on the billing page with robust error handling"""
        try:
            self.wait.until(EC.url_contains("/bill/createBill"))
            logging.info("Billing page loaded successfully")
            self.__take_screenshot("BILLING_PAGE_LOADED")

            # Capture Patient ID from input field or fallback to span
            try:
                patient_id_field = self.wait.until(EC.presence_of_element_located((By.ID, "patientId")))
                self.patient_id = patient_id_field.get_attribute("value").strip()
                if self.patient_id:
                    logging.info(f"Captured Patient ID from input: {self.patient_id}")
                else:
                    try:
                        pat_id_span = self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "ipd-patId")))
                        self.patient_id = pat_id_span.text.strip()
                        logging.info(f"Captured Patient ID from span: {self.patient_id}")
                    except TimeoutException:
                        logging.warning("Could not capture Patient ID from span")
            except TimeoutException:
                logging.warning("Could not find patient ID field")

            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
            
            try:
                dropdown = self.short_wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//span[@id='select2-chosen-26']"))
                )
            except TimeoutException:
                dropdown = self.short_wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//span[starts-with(@id, 'select2-chosen-')]"))
                )
            dropdown.click()
            logging.info("Test dropdown clicked")
            time.sleep(0.2)

            try:
                search_input = self.short_wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class, 'select2-drop-active')]//input[contains(@id, 'search')]"))
                )
            except TimeoutException:
                search_input = self.short_wait.until(EC.presence_of_element_located(
                    (By.ID, "s2id_autogen26_search"))
                )
            search_input.clear()
            search_input.send_keys("Complete Blood Cell Count")
            logging.info("Searching for 'Complete Blood Cell Count'")
            time.sleep(0.2)

            try:
                cbc_option = self.short_wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(@class, 'select2-result-label') and contains(text(), 'Complete Blood Cell Count')]"))
                )
            except TimeoutException:
                cbc_option = self.short_wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//div[contains(text(), 'Complete Blood Cell Count')]"))
                )
            cbc_option.click()
            logging.info("Complete Blood Cell Count selected")
            self.__take_screenshot("CBC_SELECTED")

            # Select Patient Type
            try:
                patient_type_select = Select(self.wait.until(EC.presence_of_element_located((By.NAME, "clientType"))))
                patient_type_select.select_by_value("2")
                logging.info("Selected Patient Type: General Client")
                self.__take_screenshot("PATIENT_TYPE_SELECTED")
            except Exception as e:
                logging.warning(f"Could not select patient type: {str(e)}")
                self.__take_screenshot("PATIENT_TYPE_SELECTION_ERROR")

            try:
                final_submit_button = self.short_wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[@id='sbmtbtn' and @type='submit']"))
                )
            except TimeoutException:
                final_submit_button = self.short_wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[@type='submit' and contains(text(), 'Submit')]"))
                )

            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                final_submit_button
            )
            time.sleep(0.5)
            final_submit_button.click()
            logging.info("Clicked final Submit button to complete the billing process")

            logging.info("Waiting for success notification or page transition")
            success_message_locator = (By.XPATH, "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')]")
            self.wait.until(EC.visibility_of_element_located(success_message_locator))
            logging.info("Success notification detected.")
            self.__take_screenshot("BILLING_COMPLETED_SUCCESS")

            try:
                create_new_bill_button = self.wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@class, 'create_biller')]"))
                )
                create_new_bill_url = create_new_bill_button.get_attribute("href")
                if "bt=OPD" in create_new_bill_url and "ins=y" not in create_new_bill_url:
                    logging.info("Create New Bill button URL is correct.")
                else:
                    logging.warning("Create New Bill button URL is incorrect. It is going to Insurance billing instead of OPD Billing.")
                    self.__take_screenshot("CREATE_NEW_BILL_URL_ERROR")
            except Exception as e:
                logging.error(f"Error checking Create New Bill button URL: {str(e)}")
                self.__take_screenshot("CREATE_NEW_BILL_URL_CHECK_ERROR")

        except Exception as e:
            self.__take_screenshot("BILLING_PAGE_ERROR")
            logging.error(f"Billing page handling failed: {str(e)}")
            raise

    def __handle_success_notification(self):
        """Verify the success notification appears after submission"""
        try:
            notification = self.wait.until(
                EC.visibility_of_element_located((
                    By.XPATH, 
                    "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')]"
                ))
            )
            
            try:
                ui_text = notification.find_element(By.CSS_SELECTOR, ".ui-pnotify-text").text
                logging.info(f"Success notification text: '{ui_text}'")
                
                if "Bill created successfully" in ui_text or "Successfully registered" in ui_text:
                    logging.info("Registration/Billing success confirmed")
                else:
                    logging.warning(f"Unknown success message: '{ui_text}'")
            except Exception as text_error:
                logging.warning(f"Could not extract notification text: {str(text_error)}")
            
            self.__take_screenshot("SUCCESS_NOTIFICATION")
            
            try:
                close_btn = self.short_wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".ui-pnotify-closer"))
                )
                self.driver.execute_script("arguments[0].scrollIntoView(true);", close_btn)
                self.driver.execute_script("arguments[0].click();", close_btn)
            
                self.short_wait.until(
                    EC.invisibility_of_element_located((By.XPATH, "//div[contains(@class, 'ui-pnotify-container')]"))
                )
                
            except Exception as close_error:
                logging.info("Notification close button not required for test success")
                self.__take_screenshot("NOTIFICATION_CLOSE_IGNORED")

        except TimeoutException:
            self.__take_screenshot("SUBMISSION_ERROR")
            logging.error("Success notification not found within timeout period")
            raise
        except Exception as e:
            self.__take_screenshot("NOTIFICATION_ERROR")
            logging.error(f"Error verifying success notification: {str(e)}")
            raise

    def __capture_and_handle_bill_info(self, original_window):
        """Capture Bill No from new window and Bill ID from main page by hovering over Print Bill button"""
        try:
            # Check for new windows
            self.short_wait.until(lambda d: len(d.window_handles) > 1)
            logging.info(f"Number of windows: {len(self.driver.window_handles)}")
            
            invoice_window = None
            for window_handle in self.driver.window_handles:
                if window_handle != original_window:
                    self.driver.switch_to.window(window_handle)
                    current_url = self.driver.current_url
                    if "chrome://print" not in current_url and "print_bill" in current_url:
                        invoice_window = window_handle
                        break
            
            if invoice_window:
                logging.info(f"Switched to invoice window: {self.driver.current_url}")
                self.__take_screenshot("BILL_WINDOW")
                
                # Wait for page to load
                self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                bill_no = self.__extract_bill_no_from_invoice()
                if bill_no:
                    self.bill_no = bill_no
                    logging.info(f"Successfully captured Bill No: {self.bill_no}")
                else:
                    logging.warning("Could not extract Bill No from invoice")
                
                try:
                    self.driver.close()
                    logging.info("Closed invoice window")
                except Exception as e:
                    logging.warning(f"Could not close invoice window: {str(e)}")
            
            self.driver.switch_to.window(original_window)
            logging.info("Switched back to original window")
            
            # Try extracting Bill No from main window if not captured
            if not self.bill_no:
                self.bill_no = self.__extract_bill_no_from_main_page()
                if self.bill_no:
                    logging.info(f"Captured Bill No from main page: {self.bill_no}")
                else:
                    logging.warning("Could not capture Bill No from main page")
            
            # Capture Bill ID
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

                    # Capture Patient ID from tooltip if not already captured
                    match_pat = re.search(r'Pat Id : (\d+)', title)
                    if match_pat and not self.patient_id:
                        self.patient_id = match_pat.group(1)
                        logging.info(f"Captured Patient ID from tooltip: {self.patient_id}")
                else:
                    logging.warning("No data-original-title in print button")
                    self.__take_screenshot("BILL_ID_NO_TOOLTIP")
                actions.move_by_offset(0, -100).perform()
                
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
            
            # Fallback to capture Bill No if still not captured
            if not self.bill_no:
                self.bill_no = self.__capture_bill_no_fallback()
                logging.info(f"Captured Bill No (fallback): {self.bill_no}")
        
        except TimeoutException:
            logging.warning("No new window appeared. Trying to find Bill No in current window")
            self.bill_no = self.__extract_bill_no_from_main_page()
            if not self.bill_no:
                self.bill_no = self.__capture_bill_no_fallback()
            logging.info(f"Captured Bill No: {self.bill_no}")
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

                    # Capture Patient ID from tooltip if not already captured
                    match_pat = re.search(r'Pat Id : (\d+)', title)
                    if match_pat and not self.patient_id:
                        self.patient_id = match_pat.group(1)
                        logging.info(f"Captured Patient ID from tooltip: {self.patient_id}")
                else:
                    logging.warning("No data-original-title in print button (fallback)")
                    self.__take_screenshot("BILL_ID_NO_TOOLTIP_FALLBACK")
                actions.move_by_offset(0, -100).perform()
                
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
        
        time.sleep(2)

    def __extract_id_from_url(self, url):
        """Extract patient ID from create_stiker URL"""
        match = re.search(r'/create_stiker/(\d+)', url)
        if match:
            return match.group(1)
        logging.warning(f"Patient ID not found in URL: {url}")
        return None

    def __extract_patient_id_fallback(self):
        """Fallback method to extract patient ID from page elements"""
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            match = re.search(r'Pat Id\.:\s*(\d+)', page_text)
            if match:
                return match.group(1)
            logging.warning("Patient ID not found via fallback method")
            return "EXTRACTION_FAILED_SEE_SCREENSHOT"
        except Exception as e:
            logging.error(f"Patient ID fallback extraction failed: {str(e)}")
            return "EXTRACTION_FAILED_SEE_SCREENSHOT"

    def __extract_bill_no_from_invoice(self):
        """Extract bill No from the invoice page"""
        try:
            # Wait for page to stabilize
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(1)  # Allow dynamic content to load
            
            # Try the billIdInfo div first
            bill_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'billIdInfo') and contains(., 'Bill No:')]")
            for element in bill_elements:
                bill_text = element.text
                bill_match = re.search(r'Bill No:\s*(?:I)?(\d+)', bill_text, re.IGNORECASE)
                if bill_match:
                    bill_no = bill_match.group(1)
                    logging.info(f"Found bill No in billIdInfo div: {bill_no}")
                    return bill_no
            
            # Fallback: Broader search for Bill No
            bill_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Bill No:') or contains(text(), 'Bill No.')]")
            for element in bill_elements:
                text = element.text
                bill_match = re.search(r'Bill No\.?:\s*(?:I)?(\d+)', text, re.IGNORECASE)
                if bill_match:
                    bill_no = bill_match.group(1)
                    logging.info(f"Found bill No via alternative method: {bill_no}")
                    return bill_no
            
            # Fallback: Search for I0000 pattern
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

    def __extract_bill_no_from_main_page(self):
        """Extract Bill No from the main page after billing submission"""
        try:
            # Try the billIdInfo div first
            bill_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'billIdInfo') and contains(., 'Bill No:')]")
            for element in bill_elements:
                text = element.text
                bill_match = re.search(r'Bill No:\s*(?:I)?(\d+)', text, re.IGNORECASE)
                if bill_match:
                    bill_no = bill_match.group(1)
                    logging.info(f"Found bill No in billIdInfo div (main page): {bill_no}")
                    return bill_no
            
            # Fallback: Check tooltip of print button
            try:
                print_bill_btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "printBtn")))
                title = print_bill_btn.get_attribute("data-original-title")
                if title:
                    bill_match = re.search(r'Bill No\.?:\s*(?:I)?(\d+)', title, re.IGNORECASE)
                    if bill_match:
                        bill_no = bill_match.group(1)
                        logging.info(f"Found bill No in print button tooltip: {bill_no}")
                        return bill_no
            except Exception:
                logging.info("No print button tooltip found for Bill No")
            
            # Fallback: Broader search for Bill No
            bill_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Bill No:') or contains(text(), 'Bill No.')]")
            for element in bill_elements:
                text = element.text
                bill_match = re.search(r'Bill No\.?:\s*(?:I)?(\d+)', text, re.IGNORECASE)
                if bill_match:
                    bill_no = bill_match.group(1)
                    logging.info(f"Found bill No in page element (main page): {bill_no}")
                    return bill_no
            
            return None
        except Exception as e:
            logging.error(f"Error extracting Bill No from main page: {str(e)}")
            self.__take_screenshot("BILL_NO_MAIN_PAGE_ERROR")
            return None

    def __capture_bill_no_fallback(self):
        """Fallback method to capture bill No from current page"""
        try:
            # Try URL first
            url = self.driver.current_url
            bill_no_match = re.search(r'[?&]billId=(\d+)', url)
            if bill_no_match:
                bill_no = bill_no_match.group(1)
                logging.info(f"Found bill No in URL: {bill_no}")
                return bill_no
            
            # Try page elements
            bill_elements = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Bill') and (contains(text(), 'ID') or contains(text(), 'No'))]")
            for elem in bill_elements:
                text = elem.text
                no_match = re.search(r'Bill\s*(ID|No)?\s*:?\s*(?:I)?(\d+)', text, re.IGNORECASE)
                if no_match:
                    bill_no = no_match.group(2)
                    logging.info(f"Found bill No in page element (fallback): {bill_no}")
                    return bill_no
            
            # Try any numeric span after Bill-related text
            id_elements = self.driver.find_elements(By.XPATH, "//strong[contains(text(), 'Bill')]/following-sibling::span")
            for elem in id_elements:
                text = elem.text.strip()
                if text.isdigit():
                    logging.info(f"Found bill No in following span (fallback): {text}")
                    return text
            
            return "unknown"
        except Exception as e:
            logging.error(f"Bill No capture failed: {str(e)}")
            return "error"

    def tearDown(self):
        """Handle patient ID and bill info in reports"""
        if self.patient_id:
            json_file = os.path.join(patient_json_dir, f"{self.patient_id}.json")
            data = {
                "patient_id": self.patient_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                with open(json_file, "w", encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                logging.info(f"Patient ID {self.patient_id} saved to {json_file}")
            except Exception as e:
                logging.error(f"Error saving patient ID to {json_file}: {str(e)}")
                self.__take_screenshot("PATIENT_ID_SAVE_ERROR")

        if self.bill_no and self.bill_no != "unknown" and self.bill_no != "error":
            bill_json_file = os.path.join(bill_nos_dir, f"{self.bill_no.zfill(8)}.json")
            bill_data = {
                "bill_no": self.bill_no.zfill(8),
                "bill_id": self.bill_id if hasattr(self, 'bill_id') and self.bill_id else "unknown",
                "patient_id": self.patient_id if self.patient_id else "unknown",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                with open(bill_json_file, "w", encoding='utf-8') as f:
                    json.dump(bill_data, f, indent=4)
                logging.info(f"Bill information saved to {bill_json_file}")
            except Exception as e:
                logging.error(f"Error saving bill info to {bill_json_file}: {str(e)}")
                self.__take_screenshot("BILL_INFO_SAVE_ERROR")

    @classmethod
    def tearDownClass(cls):
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
    unittest.main(
        testRunner=XMLTestRunnerWithBillInfo(output=report_dir, verbosity=2),
        failfast=False, buffer=False, catchbreak=False
    )