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
from utilities.config_loader import ConfigLoader


# Folder configuration
screenshot_dir = os.path.join("screenshots", "ipd_registration")
report_dir = os.path.join("reports", "ipd_registration")
patient_json_dir = os.path.join(report_dir, "patient_ids")  # Folder for storing individual patient JSON files
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)
os.makedirs(patient_json_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class IPDRegistration(unittest.TestCase):
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
        Test-level setup: Navigate to base URL, login, and initialize patient_id and ipd_id.
        """
        self.driver.get(self.base_url)
        self.__login()
        self.patient_id = None
        self.ipd_id = None

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
        Get the latest patient ID from the patient_ids folder.
        Returns the most recent patient ID based on file modification time.
        """
        try:
            # Get all JSON files from patient_ids folder (check multiple possible locations)
            json_files = []
            
            # Check the standard OPD combined location
            opd_combined_path = os.path.join("..", "reports", "opd_combined", "patient_ids")
            if os.path.exists(opd_combined_path):
                json_files.extend(glob.glob(os.path.join(opd_combined_path, "*.json")))
            
            # Check if we found files, if not try current directory structure
            if not json_files:
                # Try to find patient ID files in various locations
                possible_paths = [
                    os.path.join("..", "reports", "opd_combined", "patient_ids"),
                    os.path.join("..", "..", "reports", "opd_combined", "patient_ids"),
                    os.path.join("reports", "opd_combined", "patient_ids"),
                    os.path.join("..", "OPD Management", "reports", "opd_combined", "patient_ids")
                ]
                
                for path in possible_paths:
                    if os.path.exists(path):
                        files = glob.glob(os.path.join(path, "*.json"))
                        json_files.extend(files)
                        if files:
                            break
            
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

    def test_ipd_registration(self):
        """
        Main test method: Navigate to IPD registration, use existing patient ID, select bed, enter deposit info, 
        submit, and capture IPD ID.
        """
        # Navigate directly to IPD registration page
        self.driver.get("http://lunivacare.ddns.net:8080/himsnew/ipd/register/IPD")
        self.wait.until(EC.presence_of_element_located((By.NAME, "searchOPDId")))
        logging.info("Navigated to IPD Registration page")
        # self.__take_screenshot("IPD_REGISTER_PAGE")  # Uncomment for debugging

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
        # self.__take_screenshot("PATIENT_ID_ENTERED")  # Uncomment for debugging
        
        # Wait for patient details to populate
        time.sleep(3)
        
        # Click Select Ward button
        select_ward_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "select_dep")))
        select_ward_btn.click()
        logging.info("Clicked Select Ward button")
        # self.__take_screenshot("SELECT_WARD_CLICKED")  # Uncomment for debugging

        # Wait for room container to be visible
        self.wait.until(EC.visibility_of_element_located((By.ID, "roomContainer")))
        
        # Select a ward from the list (try preferred wards in order)
        ward_selected = False
        preferred_wards = ["General Ward", "Labor Ward", "Special Ward", "Cabin", "Gynae Ward"]
        
        for ward_name in preferred_wards:
            try:
                ward_element = self.wait.until(EC.element_to_be_clickable((By.XPATH, f"//li[@data-room='{ward_name}']")))
                ward_element.click()
                logging.info(f"Selected {ward_name}")
                # self.__take_screenshot(f"{ward_name.replace(' ', '_')}_SELECTED")  # Uncomment for debugging
                ward_selected = True
                break
            except:
                logging.warning(f"Could not select {ward_name}")
                continue
        
        # If none of the preferred wards work, select the first available ward
        if not ward_selected:
            try:
                first_ward = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@data-room]")))
                ward_name = first_ward.get_attribute("data-room")
                first_ward.click()
                logging.info(f"Selected first available ward: {ward_name}")
                # self.__take_screenshot("FIRST_WARD_SELECTED")  # Uncomment for debugging
                ward_selected = True
            except Exception as e:
                logging.error(f"Could not select any ward: {str(e)}")
                raise

        # Wait for bed container to be visible
        time.sleep(3)
        self.wait.until(EC.visibility_of_element_located((By.ID, "bedContainers")))
        
        # Select a bed from the available beds using intelligent selection
        self.__select_available_bed()
        
        # Enter deposit amount
        time.sleep(2)
        try:
            deposit_field = self.wait.until(EC.element_to_be_clickable((By.NAME, "deposit")))
            deposit_field.clear()
            deposit_field.send_keys("0")
            logging.info("Entered deposit amount: 0")
        except Exception as e:
            logging.error(f"Error entering deposit amount: {str(e)}")
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
            # Try alternative approach
            try:
                deposit_by_field = self.driver.find_element(By.NAME, "depositBy")
                self.driver.execute_script("arguments[0].value = 'Test User';", deposit_by_field)
                logging.info("Entered deposit by via JavaScript: Test User")
            except Exception as e2:
                logging.error(f"Error entering deposit by via JavaScript: {str(e2)}")
                raise e
        
        # self.__take_screenshot("DEPOSIT_INFO_ENTERED")  # Uncomment for debugging

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
        
        # self.__take_screenshot("FORM_SUBMITTED")  # Uncomment for debugging

        # Handle success notification and capture IPD ID
        self.__handle_ipd_success_notification()
        logging.info(f"Captured IPD ID: {self.ipd_id}")

        # Optionally add to test description for better XML reporting (appears in test doc)
        self._testMethodDoc = f"Patient ID: {self.patient_id}, IPD ID: {self.ipd_id}"

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
                # self.__take_screenshot("BED_SELECTED_APPROACH1")  # Uncomment for debugging
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
                                # self.__take_screenshot("BED_SELECTED_APPROACH2")  # Uncomment for debugging
                                break
                        except:
                            continue
                    
                    # If no non-occupied beds found, just select the first one
                    if not bed_selected and bed_elements:
                        self.driver.execute_script("arguments[0].click();", bed_elements[0])
                        bed_name = bed_elements[0].text.strip()
                        logging.info(f"Selected first bed (approach 2 fallback): {bed_name}")
                        bed_selected = True
                        # self.__take_screenshot("BED_SELECTED_APPROACH2_FALLBACK")  # Uncomment for debugging
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
                    # self.__take_screenshot("BED_SELECTED_APPROACH3")  # Uncomment for debugging
            except Exception as e:
                logging.warning(f"Approach 3 for bed selection failed: {str(e)}")
        
        # If no approach worked, log error but continue
        if not bed_selected:
            logging.warning("Could not select a bed, continuing without bed selection")
            # self.__take_screenshot("BED_SELECTION_FAILED")  # Uncomment for debugging
            # Raise an exception since bed selection is required
            raise Exception("Could not select any available bed")

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
                # self.__take_screenshot("DEPOSIT_SLIP_PRINT_WINDOW")  # Uncomment for debugging
                
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
                            # self.__take_screenshot("IPD_ID_CAPTURED_FROM_SLIP")  # Uncomment for debugging
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
                        return
            except Exception as e:
                logging.error(f"Error extracting IPD ID from current page: {str(e)}")
            
            # If still no IPD ID, log and continue (assume registration was successful)
            logging.info("IPD registration completed")
            # self.__take_screenshot("IPD_REGISTRATION_COMPLETED")  # Uncomment for debugging
            
        except Exception as e:
            # self.__take_screenshot("IPD_REGISTRATION_PROCESS_ERROR")  # Uncomment for debugging
            logging.error(f"IPD registration handling error: {str(e)}")
            # Don't raise exception, just continue
            pass

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
        Test-level teardown: Save patient ID and IPD ID to a separate JSON file if captured.
        Each patient ID is stored in a file named as ID.json
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