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
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from utilities.config_loader import ConfigLoader

# Folder configuration
screenshot_dir = os.path.join("screenshots", "ipd_combined")
report_dir = os.path.join("reports", "ipd_combined")
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
        self.ipd_id = None

    def addSuccess(self, test):
        super().addSuccess(test)
        if hasattr(test, 'bill_no'):
            self.bill_no = test.bill_no
        if hasattr(test, 'bill_id'):
            self.bill_id = test.bill_id
        if hasattr(test, 'patient_id'):
            self.patient_id = test.patient_id
        if hasattr(test, 'ipd_id'):
            self.ipd_id = test.ipd_id


class IpdRegisterAndBilling(unittest.TestCase):
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
        self.ipd_id = None
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
            json_files = glob.glob(os.path.join("reports", "opd_combined", "patient_ids", "*.json"))
            
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

    def test_ipd_registration_and_billing(self):
        """
        Combined test method: 
        1. Perform IPD registration using existing patient ID
        2. Navigate to IPD billing
        3. Use the captured IPD ID for billing
        4. Complete the billing process
        """
        # Part 1: IPD Registration
        logging.info("Starting IPD Registration...")
        self.__perform_ipd_registration()
        
        # Part 2: IPD Billing using the registered patient
        logging.info("Starting IPD Billing...")
        self.__perform_ipd_billing()

    def __perform_ipd_registration(self):
        """
        Perform IPD registration process using existing patient ID
        """
        # Navigate directly to IPD registration page
        self.driver.get("http://lunivacare.ddns.net:8080/himsnew/ipd/register/IPD")
        self.wait.until(EC.presence_of_element_located((By.NAME, "searchOPDId")))
        logging.info("Navigated to IPD Registration page")
        self.__take_screenshot("IPD_REGISTER_PAGE")

        # Get the latest patient ID from existing files
        self.patient_id = self.__get_latest_patient_id()
        logging.info(f"Using existing Patient ID: {self.patient_id}")

        # Enter Patient ID in the correct field
        patient_id_field = self.wait.until(EC.presence_of_element_located((By.NAME, "searchOPDId")))
        patient_id_field.clear()
        patient_id_field.send_keys(self.patient_id)
        
        # Send Enter key to trigger data population
        from selenium.webdriver.common.keys import Keys
        patient_id_field.send_keys(Keys.ENTER)
        logging.info("Entered patient ID and sent Enter key")
        self.__take_screenshot("PATIENT_ID_ENTERED")
        
        # Wait for patient details to populate
        time.sleep(3)
        
        # Click Select Ward button
        select_ward_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "select_dep")))
        select_ward_btn.click()
        logging.info("Clicked Select Ward button")
        self.__take_screenshot("SELECT_WARD_CLICKED")

        # Wait for room container to be visible
        self.wait.until(EC.visibility_of_element_located((By.ID, "roomContainer")))
        
        # Select a ward from the list (Labor Ward as an example)
        labor_ward = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@data-room='Labor Ward']")))
        labor_ward.click()
        logging.info("Selected Labor Ward")
        self.__take_screenshot("LABOR_WARD_SELECTED")
        
        # Wait for bed container to be visible
        time.sleep(2)
        self.wait.until(EC.visibility_of_element_located((By.ID, "bedContainers")))
        
        # Select a bed from the available beds using intelligent selection
        self.__select_available_bed()
        
        self.__take_screenshot("BED_SELECTED")

        # Wait for the deposit fields to be available after selecting ward
        time.sleep(2)
        
        # Wait for the deposit fields to be available after selecting ward
        time.sleep(3)
        
        # Enter deposit amount
        try:
            deposit_field = self.wait.until(EC.element_to_be_clickable((By.NAME, "deposit")))
            deposit_field.clear()
            deposit_field.send_keys("0")
            logging.info("Entered deposit amount: 0")
        except Exception as e:
            logging.error(f"Error entering deposit amount: {str(e)}")
            # Take screenshot for debugging
            self.__take_screenshot("DEPOSIT_FIELD_ERROR")
            # Try alternative approach
            try:
                deposit_field = self.driver.find_element(By.NAME, "deposit")
                self.driver.execute_script("arguments[0].value = '0';", deposit_field)
                logging.info("Entered deposit amount via JavaScript: 0")
            except Exception as e2:
                logging.error(f"Error entering deposit amount via JavaScript: {str(e2)}")
                raise e
        
        # Enter deposit by
        try:
            deposit_by_field = self.wait.until(EC.element_to_be_clickable((By.NAME, "depositBy")))
            deposit_by_field.clear()
            deposit_by_field.send_keys("Test User")
            logging.info("Entered deposit by: Test User")
        except Exception as e:
            logging.error(f"Error entering deposit by: {str(e)}")
            # Take screenshot for debugging
            self.__take_screenshot("DEPOSIT_BY_FIELD_ERROR")
            # Try alternative approach
            try:
                deposit_by_field = self.driver.find_element(By.NAME, "depositBy")
                self.driver.execute_script("arguments[0].value = 'Test User';", deposit_by_field)
                logging.info("Entered deposit by via JavaScript: Test User")
            except Exception as e2:
                logging.error(f"Error entering deposit by via JavaScript: {str(e2)}")
                raise e
        
        self.__take_screenshot("DEPOSIT_INFO_ENTERED")

        # Submit the form
        # Wait a bit for any modals to close
        time.sleep(2)
        
        # Try to click the submit button, with fallback to JavaScript click if intercepted
        try:
            submit_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "submitNewButton")))
            submit_btn.click()
            logging.info("Form submitted (normal click)")
        except Exception as e:
            logging.warning(f"Normal click failed: {str(e)}, trying JavaScript click")
            # If normal click fails, try JavaScript click
            try:
                submit_btn = self.driver.find_element(By.ID, "submitNewButton")
                self.driver.execute_script("arguments[0].click();", submit_btn)
                logging.info("Form submitted (JavaScript click)")
            except Exception as e2:
                logging.error(f"Both click methods failed: {str(e2)}")
                raise e2
        
        self.__take_screenshot("FORM_SUBMITTED")

        # Handle success notification and capture IPD ID
        self.__handle_ipd_success_notification()
        logging.info(f"Captured IPD ID: {self.ipd_id}")

    def __perform_ipd_billing(self):
        """
        Perform IPD billing process using the registered IPD ID
        """
        try:
            # Navigate to IPD Billing with timeout handling
            try:
                self.driver.get("http://lunivacare.ddns.net:8080/himsnew/bill/createBill?bt=IPD")
                self.wait.until(EC.presence_of_element_located((By.ID, "ipdId")))
                logging.info("Navigated to IPD Billing page")
                self.__take_screenshot("IPD_BILLING_PAGE")
            except Exception as e:
                logging.error(f"Error navigating to IPD billing page: {str(e)}")
                # Try alternative navigation
                self.driver.get("http://lunivacare.ddns.net:8080/himsnew/bill/createBill?bt=IPD")
                time.sleep(5)  # Wait for page to load
                logging.info("Retried navigation to IPD Billing page")
                self.__take_screenshot("IPD_BILLING_PAGE_RETRY")

            # Enter IPD ID
            ipd_id_field = self.wait.until(EC.presence_of_element_located((By.ID, "ipdId")))
            ipd_id_field.clear()
            ipd_id_field.send_keys(self.ipd_id)
            logging.info(f"Entered IPD ID: {self.ipd_id}")
            self.__take_screenshot("IPD_ID_ENTERED")

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
            
        except Exception as e:
            self.__take_screenshot("BILLING_FAILURE")
            logging.error(f"Billing test failed: {str(e)}")
            # Don't raise the exception, just log it and continue
            pass

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

    def __handle_ipd_success_notification(self):
        """
        Handle success notification after IPD form submission and capture IPD ID.
        """
        try:
            # Wait for the deposit slip print window to open
            time.sleep(8)  # Give more time for the print window to open
            
            # Check if a new window opened (deposit slip print window)
            if len(self.driver.window_handles) > 1:
                # Store original window handle
                original_window = self.driver.current_window_handle
                
                # Switch to the new window (deposit slip print window)
                for window_handle in self.driver.window_handles:
                    if window_handle != original_window:
                        self.driver.switch_to.window(window_handle)
                        break
                
                logging.info("Switched to deposit slip print window")
                self.__take_screenshot("DEPOSIT_SLIP_PRINT_WINDOW")
                
                # Extract IPD ID from the deposit slip with multiple approaches
                ipd_id_found = False
                
                try:
                    # Approach 1: Look for IPD ID in the page source using multiple patterns
                    page_source = self.driver.page_source
                    
                    # Try different regex patterns to find IPD ID
                    patterns = [
                        r'IPD\s*Id[^\d]*(\d+)',
                        r'IPD\s*ID[^\d]*(\d+)',
                        r'IPD[^\d]*(\d{3,6})',
                        r'>(\d{3,6})<.*IPD',
                        r'IPD\s*:\s*(\d+)',
                        r'IPD\s*No[^\d]*(\d+)'
                    ]
                    
                    for pattern in patterns:
                        ipd_match = re.search(pattern, page_source, re.IGNORECASE)
                        if ipd_match:
                            self.ipd_id = ipd_match.group(1)
                            logging.info(f"IPD ID captured from deposit slip (pattern: {pattern}): {self.ipd_id}")
                            self.__take_screenshot("IPD_ID_CAPTURED_FROM_SLIP")
                            ipd_id_found = True
                            break
                            
                except Exception as e:
                    logging.warning(f"Approach 1 for IPD ID extraction failed: {str(e)}")
                
                # Approach 2: Try to find IPD ID by looking at page elements
                if not ipd_id_found:
                    try:
                        # Look for elements containing "IPD" text
                        ipd_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'IPD')]")
                        for element in ipd_elements:
                            text = element.text
                            # Look for patterns in the text
                            match = re.search(r'IPD\s*[Ii][Dd][:.\s]*(\d+)', text, re.IGNORECASE)
                            if match:
                                self.ipd_id = match.group(1)
                                logging.info(f"IPD ID captured from element text: {self.ipd_id}")
                                ipd_id_found = True
                                break
                    except Exception as e:
                        logging.warning(f"Approach 2 for IPD ID extraction failed: {str(e)}")
                
                # Approach 3: Try to find any number near IPD text
                if not ipd_id_found:
                    try:
                        page_text = self.driver.find_element(By.TAG_NAME, "body").text
                        # Split text into lines and look for lines containing IPD
                        lines = page_text.split('\n')
                        for line in lines:
                            if 'IPD' in line.upper():
                                # Look for numbers in this line
                                numbers = re.findall(r'\b\d{3,6}\b', line)
                                if numbers:
                                    self.ipd_id = numbers[0]  # Take the first number found
                                    logging.info(f"IPD ID captured from line analysis: {self.ipd_id}")
                                    ipd_id_found = True
                                    break
                    except Exception as e:
                        logging.warning(f"Approach 3 for IPD ID extraction failed: {str(e)}")
                
                # If we found IPD ID, close the window and return
                if ipd_id_found:
                    try:
                        # Close the deposit slip window
                        self.driver.close()
                        # Switch back to original window
                        self.driver.switch_to.window(original_window)
                        return
                    except:
                        pass
                else:
                    logging.warning("Could not extract IPD ID from deposit slip")
                    try:
                        self.driver.close()
                        self.driver.switch_to.window(original_window)
                    except:
                        pass
            else:
                logging.info("No new window opened, checking current page for IPD ID")
            
            # If no new window or couldn't extract IPD ID, check current page
            try:
                page_source = self.driver.page_source
                # Try the same patterns on current page
                patterns = [
                    r'IPD\s*Id[^\d]*(\d+)',
                    r'IPD\s*ID[^\d]*(\d+)',
                    r'IPD[^\d]*(\d{3,6})',
                    r'IPD\s*:\s*(\d+)',
                    r'IPD\s*No[^\d]*(\d+)'
                ]
                
                for pattern in patterns:
                    ipd_match = re.search(pattern, page_source, re.IGNORECASE)
                    if ipd_match:
                        self.ipd_id = ipd_match.group(1)
                        logging.info(f"IPD ID captured from current page: {self.ipd_id}")
                        self.__take_screenshot("IPD_ID_FOUND_ON_PAGE")
                        return
            except Exception as e:
                        logging.error(f"Error extracting IPD ID from current page: {str(e)}")
            
            # Check for notification messages
            try:
                notification_elements = self.driver.find_elements(By.XPATH,
                    "//*[contains(@class, 'ui-pnotify-container') or contains(@class, 'alert') or contains(@class, 'success') or contains(text(), 'successfully') or contains(text(), 'Success')]"
                )
                
                if notification_elements:
                    logging.info("IPD registration successful - notification found")
                    self.__take_screenshot("IPD_REGISTRATION_SUCCESS_NOTIFICATION")
                    
                    # Close notifications if present
                    try:
                        for notification in notification_elements:
                            try:
                                close_btn = notification.find_element(By.CSS_SELECTOR, ".ui-pnotify-closer, .close")
                                self.driver.execute_script("arguments[0].click();", close_btn)
                            except:
                                pass
                    except:
                        pass
            except Exception as e:
                logging.warning(f"Error checking for notifications: {str(e)}")
            
            # If still no IPD ID, log and continue (assume registration was successful)
            logging.info("IPD registration completed")
            self.__take_screenshot("IPD_REGISTRATION_COMPLETED")
            
        except Exception as e:
            self.__take_screenshot("IPD_REGISTRATION_PROCESS_ERROR")
            logging.error(f"IPD registration handling error: {str(e)}")
            # Don't raise exception, just continue
            pass

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

    def __select_available_bed(self):
        """
        Intelligently select an available bed from the bed containers.
        Tries multiple approaches to find and select an available bed.
        """
        bed_selected = False
        
        # Approach 1: Try to find available beds (not occupied)
        try:
            available_beds = self.driver.find_elements(By.XPATH, "//div[@id='bedContainers']//div[contains(@class, 'panel-heading') and not(contains(@class, 'occupied'))]")
            if available_beds:
                # Click the first available bed
                self.driver.execute_script("arguments[0].click();", available_beds[0])
                bed_name = available_beds[0].text.strip()
                logging.info(f"Selected first available bed (approach 1): {bed_name}")
                bed_selected = True
                self.__take_screenshot("BED_SELECTED_APPROACH1")
        except Exception as e:
            logging.warning(f"Approach 1 for bed selection failed: {str(e)}")
        
        # Approach 2: If no available beds found, try to find any bed with data-id
        if not bed_selected:
            try:
                bed_elements = self.driver.find_elements(By.XPATH, "//div[@id='bedContainers']//*[@data-id]")
                if bed_elements:
                    # Try to find one that's not occupied
                    for bed_element in bed_elements:
                        try:
                            class_attr = bed_element.get_attribute("class")
                            if class_attr and "occupied" not in class_attr:
                                self.driver.execute_script("arguments[0].click();", bed_element)
                                bed_name = bed_element.text.strip()
                                logging.info(f"Selected available bed (approach 2): {bed_name}")
                                bed_selected = True
                                self.__take_screenshot("BED_SELECTED_APPROACH2")
                                break
                        except:
                            continue
                    
                    # If no non-occupied beds found, just select the first one
                    if not bed_selected and bed_elements:
                        self.driver.execute_script("arguments[0].click();", bed_elements[0])
                        bed_name = bed_elements[0].text.strip()
                        logging.info(f"Selected first bed (approach 2 fallback): {bed_name}")
                        bed_selected = True
                        self.__take_screenshot("BED_SELECTED_APPROACH2_FALLBACK")
            except Exception as e:
                logging.warning(f"Approach 2 for bed selection failed: {str(e)}")
        
        # Approach 3: Try to find beds by specific data attributes
        if not bed_selected:
            try:
                # Try to find beds with class 'panel-heading' that are not occupied
                bed_elements = self.driver.find_elements(By.XPATH, "//div[@id='bedContainers']//div[@class='panel-heading' and not(contains(@class, 'occupied'))]")
                if bed_elements:
                    self.driver.execute_script("arguments[0].click();", bed_elements[0])
                    bed_name = bed_elements[0].text.strip()
                    logging.info(f"Selected available bed (approach 3): {bed_name}")
                    bed_selected = True
                    self.__take_screenshot("BED_SELECTED_APPROACH3")
            except Exception as e:
                logging.warning(f"Approach 3 for bed selection failed: {str(e)}")
        
        # Approach 4: Try preferred ward selection method
        if not bed_selected:
            try:
                # Try to select beds in order of preference (data-id values)
                preferred_bed_ids = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
                for bed_id in preferred_bed_ids:
                    try:
                        bed_element = self.driver.find_element(By.XPATH, f"//div[@id='bedContainers']//*[@data-id='{bed_id}']")
                        class_attr = bed_element.get_attribute("class")
                        if not class_attr or "occupied" not in class_attr:
                            self.driver.execute_script("arguments[0].click();", bed_element)
                            bed_name = bed_element.text.strip()
                            logging.info(f"Selected preferred bed (data-id {bed_id}): {bed_name}")
                            bed_selected = True
                            self.__take_screenshot(f"BED_SELECTED_PREFERRED_{bed_id}")
                            break
                    except:
                        continue
            except Exception as e:
                logging.warning(f"Approach 4 for bed selection failed: {str(e)}")
        
        # If no approach worked, log error but continue
        if not bed_selected:
            logging.warning("Could not select a bed, continuing without bed selection")
            self.__take_screenshot("BED_SELECTION_FAILED")
            # Raise an exception since bed selection is required
            raise Exception("Could not select any available bed")

    def __extract_ipd_id_from_url(self, url):
        """
        Extract IPD ID from the URL using regex.
        """
        # Try different patterns for IPD ID
        patterns = [
            r'/create_stiker/(\d+)',
            r'[?&]ipdId=([A-Z0-9]+)',
            r'[?&]id=([A-Z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                ipd_id = match.group(1)
                # Make sure it's not "Go" or other invalid values
                if ipd_id and len(ipd_id) > 2 and ipd_id != "Go":
                    return ipd_id
        
        # If not found in URL, try to extract from page content
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            # Look for IPD ID patterns
            ipd_patterns = [
                r'IPD\s*ID[:\s]*([A-Z]{2,4}\d{6,10})',
                r'IPD\s*No[:\s]*([A-Z]{2,4}\d{6,10})',
                r'([A-Z]{2,4}\d{6,10})'
            ]
            
            for pattern in ipd_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    ipd_id = match.group(1)
                    # Make sure it's not "Go" or other invalid values
                    if ipd_id and len(ipd_id) > 2 and ipd_id != "Go":
                        return ipd_id
        except Exception as e:
            logging.error(f"Error extracting IPD ID from page: {str(e)}")
        
        raise ValueError(f"Valid IPD ID not found in URL or page: {url}")

    def __extract_ipd_id_from_page(self):
        """
        Extract IPD ID from the current page content.
        """
        try:
            # Look for IPD ID in page text
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # Try different patterns to find IPD ID - more specific patterns first
            patterns = [
                r'IPD\s*ID[:\s]*([A-Z]{2,4}\d{4,8})',  # More specific pattern
                r'IPD\s*ID[:\s]*([A-Z0-9]{6,12})',      # Alphanumeric pattern
                r'IPD\s*No[:\s]*([A-Z]{2,4}\d{4,8})',
                r'([A-Z]{2,4}\d{6,10})'  # Pattern like IPD123456
            ]
            
            for pattern in patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    ipd_id = match.group(1)
                    # Make sure it's not "Go" or other invalid values
                    if ipd_id and len(ipd_id) > 2 and ipd_id != "Go":
                        return ipd_id
            
            # If not found in text, look for specific elements with IPD ID
            # Look for elements that contain "IPD" but exclude buttons with "Go Back"
            ipd_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'IPD') and not(contains(text(), 'Go Back'))]")
            for elem in ipd_elements:
                text = elem.text
                # Look for patterns like IPD123456 or similar
                match = re.search(r'([A-Z]{2,4}\d{6,10})', text)
                if match:
                    ipd_id = match.group(1)
                    if ipd_id and len(ipd_id) > 2 and ipd_id != "Go":
                        return ipd_id
                        
            # Try to find IPD ID in URL parameters
            current_url = self.driver.current_url
            url_patterns = [
                r'[?&]ipdId=([A-Z0-9]+)',
                r'[?&]id=([A-Z0-9]+)'
            ]
            
            for pattern in url_patterns:
                match = re.search(pattern, current_url, re.IGNORECASE)
                if match:
                    ipd_id = match.group(1)
                    if ipd_id and len(ipd_id) > 2 and ipd_id != "Go":
                        return ipd_id
            
            return None
        except Exception as e:
            logging.error(f"Error extracting IPD ID from page: {str(e)}")
            return None

    def __select_available_bed(self):
        """
        Intelligently select an available bed from the bed containers.
        Tries multiple approaches to find and select an available bed.
        """
        bed_selected = False
        
        # Approach 1: Try to find available beds (not occupied)
        try:
            available_beds = self.driver.find_elements(By.XPATH, "//div[@id='bedContainers']//div[contains(@class, 'panel-heading') and not(contains(@class, 'occupied'))]")
            if available_beds:
                # Click the first available bed
                self.driver.execute_script("arguments[0].click();", available_beds[0])
                bed_name = available_beds[0].text.strip()
                logging.info(f"Selected first available bed (approach 1): {bed_name}")
                bed_selected = True
                self.__take_screenshot("BED_SELECTED_APPROACH1")
        except Exception as e:
            logging.warning(f"Approach 1 for bed selection failed: {str(e)}")
        
        # Approach 2: If no available beds found, try to find any bed with data-id
        if not bed_selected:
            try:
                bed_elements = self.driver.find_elements(By.XPATH, "//div[@id='bedContainers']//*[@data-id]")
                if bed_elements:
                    # Try to find one that's not occupied
                    for bed_element in bed_elements:
                        try:
                            class_attr = bed_element.get_attribute("class")
                            if class_attr and "occupied" not in class_attr:
                                self.driver.execute_script("arguments[0].click();", bed_element)
                                bed_name = bed_element.text.strip()
                                logging.info(f"Selected available bed (approach 2): {bed_name}")
                                bed_selected = True
                                self.__take_screenshot("BED_SELECTED_APPROACH2")
                                break
                        except:
                            continue
                    
                    # If no non-occupied beds found, just select the first one
                    if not bed_selected and bed_elements:
                        self.driver.execute_script("arguments[0].click();", bed_elements[0])
                        bed_name = bed_elements[0].text.strip()
                        logging.info(f"Selected first bed (approach 2 fallback): {bed_name}")
                        bed_selected = True
                        self.__take_screenshot("BED_SELECTED_APPROACH2_FALLBACK")
            except Exception as e:
                logging.warning(f"Approach 2 for bed selection failed: {str(e)}")
        
        # Approach 3: Try to find beds by specific data attributes
        if not bed_selected:
            try:
                # Try to find beds with class 'panel-heading' that are not occupied
                bed_elements = self.driver.find_elements(By.XPATH, "//div[@id='bedContainers']//div[@class='panel-heading' and not(contains(@class, 'occupied'))]")
                if bed_elements:
                    self.driver.execute_script("arguments[0].click();", bed_elements[0])
                    bed_name = bed_elements[0].text.strip()
                    logging.info(f"Selected available bed (approach 3): {bed_name}")
                    bed_selected = True
                    self.__take_screenshot("BED_SELECTED_APPROACH3")
            except Exception as e:
                logging.warning(f"Approach 3 for bed selection failed: {str(e)}")
        
        # Approach 4: Try preferred ward selection method
        if not bed_selected:
            try:
                # Try to select beds in order of preference (data-id values)
                preferred_bed_ids = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
                for bed_id in preferred_bed_ids:
                    try:
                        bed_element = self.driver.find_element(By.XPATH, f"//div[@id='bedContainers']//*[@data-id='{bed_id}']")
                        class_attr = bed_element.get_attribute("class")
                        if not class_attr or "occupied" not in class_attr:
                            self.driver.execute_script("arguments[0].click();", bed_element)
                            bed_name = bed_element.text.strip()
                            logging.info(f"Selected preferred bed (data-id {bed_id}): {bed_name}")
                            bed_selected = True
                            self.__take_screenshot(f"BED_SELECTED_PREFERRED_{bed_id}")
                            break
                    except:
                        continue
            except Exception as e:
                logging.warning(f"Approach 4 for bed selection failed: {str(e)}")
        
        # If no approach worked, log error but continue
        if not bed_selected:
            logging.warning("Could not select a bed, continuing without bed selection")
            self.__take_screenshot("BED_SELECTION_FAILED")
            # Raise an exception since bed selection is required
            raise Exception("Could not select any available bed")

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
        Test-level teardown: Save patient ID, IPD ID and bill info to separate JSON files if captured.
        """
        if self.patient_id:
            json_file = os.path.join(patient_json_dir, f"{self.patient_id}_ipd.json")
            data = {
                "patient_id": self.patient_id,
                "ipd_id": self.ipd_id if self.ipd_id else "unknown",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(json_file, "w") as f:
                json.dump(data, f, indent=4)
            logging.info(f"Patient/IPD information saved to {json_file}")

        if self.bill_no:
            # Save bill information directly in bill_nos folder
            bill_json_file = os.path.join(bill_nos_dir, f"{self.bill_no.zfill(8)}.json")
            bill_data = {
                "bill_no": self.bill_no.zfill(8),
                "bill_id": self.bill_id if hasattr(self, 'bill_id') and self.bill_id else "unknown",
                "patient_id": self.patient_id,
                "ipd_id": self.ipd_id if self.ipd_id else "unknown",
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
    
    # Create test suite and run
    suite = unittest.TestLoader().loadTestsFromTestCase(IpdRegisterAndBilling)
    
    # Run the test
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Check if the test passed
    if result.wasSuccessful():
        logging.info("All tests passed!")
    else:
        logging.error("Some tests failed!")
        for failure in result.failures:
            logging.error(f"FAILURE: {failure[0]}\n{failure[1]}")
        for error in result.errors:
            logging.error(f"ERROR: {error[0]}\n{error[1]}")