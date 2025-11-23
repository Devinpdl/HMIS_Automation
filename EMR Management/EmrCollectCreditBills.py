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
screenshot_dir = os.path.join("screenshots", "emr_collect_credit")
report_dir = os.path.join("reports", "emr_collect_credit")
collected_bills_dir = os.path.join(report_dir, "collected_bills")
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)
os.makedirs(collected_bills_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class EMRCollectCreditBills(unittest.TestCase):
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
        Test-level setup: Navigate to base URL, login.
        """
        self.driver.get(self.base_url)
        self.__login()

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

    def test_collect_emr_credit_bills(self):
        """
        Test method: Navigate to EMR bill list, find credit bills, and collect them.
        """
        logging.info("Starting EMR Credit Bill Collection...")
        self.__collect_emr_credit_bills()

    def __collect_emr_credit_bills(self):
        """
        Collect EMR credit bills from the bill list.
        """
        try:
            # Navigate to the specific EMR bill list URL
            self.driver.get("http://lunivacare.ddns.net:8080/himsnew/bill/bill_list?list=Emergency")
            time.sleep(3)  # Wait for page to load
            logging.info("Navigated to EMR Bill List")
            self.__take_screenshot("EMR_BILL_LIST")
            
            # Click on English date toggle
            try:
                english_toggle = self.wait.until(EC.element_to_be_clickable((By.ID, "show_nepaliCheck")))
                if not english_toggle.is_selected():
                    # Use JavaScript click to avoid interception issues
                    self.driver.execute_script("arguments[0].click();", english_toggle)
                    logging.info("Clicked on English date toggle")
                    self.__take_screenshot("ENGLISH_TOGGLE_CLICKED")
                else:
                    logging.info("English date toggle already selected")
            except Exception as e:
                logging.error(f"Error clicking English date toggle: {str(e)}")
                self.__take_screenshot("ENGLISH_TOGGLE_ERROR")
            
            # Wait for English date fields to appear
            time.sleep(2)
            
            # === DATE FILTERING SECTION ===
            # COMMENT OUT THIS SECTION IF YOU WANT TO USE THE DEFAULT LOADING DATE OF THE SOFTWARE
            # UNCOMMENT THIS SECTION IF YOU WANT TO PASS DATES MANUALLY
            # ------------------------------------------------------------------
            # For manual date entry, uncomment the following lines:
            try:
                # Try different selectors for date fields
                try:
                    from_date_field = self.wait.until(EC.presence_of_element_located((By.ID, "englishFrom")))
                except:
                    try:
                        from_date_field = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#englishFrom")))
                    except:
                        # If ID doesn't work, try by name
                        from_date_field = self.wait.until(EC.presence_of_element_located((By.NAME, "fromDate")))
                
                from_date_field.clear()
                from_date_field.send_keys("2025-09-15")  # From date - modify as needed
                logging.info("Entered From Date: 2025-09-15")
                self.__take_screenshot("FROM_DATE_ENTERED")
                
                # Try different selectors for To date field
                try:
                    to_date_field = self.driver.find_element(By.ID, "englishTo")
                except:
                    try:
                        to_date_field = self.driver.find_element(By.CSS_SELECTOR, "input#englishTo")
                    except:
                        # If ID doesn't work, try by name
                        to_date_field = self.driver.find_element(By.NAME, "toDate")
                
                to_date_field.clear()
                to_date_field.send_keys("2025-09-18")  # To date - modify as needed
                logging.info("Entered To Date: 2025-09-18")
                self.__take_screenshot("TO_DATE_ENTERED")
                
                # Click on Get Bills button
                get_button = self.driver.find_element(By.ID, "btnGetMiscPayment")
                # Use JavaScript click to avoid interception issues
                self.driver.execute_script("arguments[0].click();", get_button)
                logging.info("Clicked on Get Bills button")
                self.__take_screenshot("GET_BILLS_BUTTON_CLICKED")
                
                # Wait for page to reload with filtered data
                time.sleep(5)
            except Exception as e:
                logging.error(f"Error in date filtering: {str(e)}")
                self.__take_screenshot("DATE_FILTERING_ERROR")
            # ------------------------------------------------------------------
            # === END DATE FILTERING SECTION ===
            
            # Process the bill table
            page_number = 1
            total_credit_bills_collected = 0
            
            while True:
                # If we're not on page 1, navigate to the specific page
                if page_number > 1:
                    self.driver.get(f"http://lunivacare.ddns.net:8080/himsnew/bill/bill_list?list=Emergency&page={page_number}")
                    time.sleep(3)  # Wait for page to load
                    logging.info(f"Navigate to page {page_number}")
                    self.__take_screenshot(f"EMR_BILL_LIST_PAGE_{page_number}")
                
                # Look for bill table
                try:
                    bill_table = self.wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'table')]")))
                    logging.info("Bill table found")
                    self.__take_screenshot(f"BILL_TABLE_FOUND_PAGE_{page_number}")
                    
                    # Find all rows in the table body - more inclusive selector
                    rows = bill_table.find_elements(By.XPATH, ".//tbody/tr")
                    logging.info(f"Found {len(rows)} bill rows on page {page_number}")
                    
                    # Process each row to find credit bills
                    credit_bills_found_on_page = 0
                    for i, row in enumerate(rows):
                        try:
                            # Get the row class to differentiate odd/even if available
                            row_class = row.get_attribute("class") or "no-class"
                            logging.info(f"Processing row {i+1} with class '{row_class}' on page {page_number}")
                            
                            # Get cells in the row
                            cells = row.find_elements(By.XPATH, ".//td")
                            if len(cells) >= 8:  # Ensure we have enough cells
                                # Check if this is a credit bill (look for "Credit" in status column - 8th column)
                                status_cell = cells[7]  # 8th column is status
                                status_text = status_cell.text.strip()
                                
                                logging.info(f"Row {i+1} status: '{status_text}'")
                                
                                # Check for "Credit" status (exact match)
                                if status_text == "Credit":
                                    credit_bills_found_on_page += 1
                                    bill_no = cells[0].text.strip()  # 1st column is bill number
                                    credit_amount = cells[6].text.strip()  # 7th column is credit amount
                                    patient_id = cells[1].text.strip()  # 2nd column is patient ID
                                    # Try to get bill ID from the row (9th column or from data attributes)
                                    bill_id = "unknown"
                                    if len(cells) > 8:
                                        bill_id = cells[8].text.strip()  # 9th column is bill ID
                                    
                                    # If we couldn't get bill ID from cells, try to extract from row attributes
                                    if bill_id == "unknown" or not bill_id:
                                        try:
                                            # Try to get data-bill-id attribute from the row
                                            bill_id_attr = row.get_attribute("data-bill-id")
                                            if bill_id_attr:
                                                bill_id = bill_id_attr
                                                logging.info(f"Extracted bill ID {bill_id} from row data attribute")
                                        except Exception as e:
                                            logging.warning(f"Could not extract bill ID from row attributes: {str(e)}")
                                    
                                    logging.info(f"Found credit bill {bill_no} (ID: {bill_id}) with credit amount {credit_amount} for patient {patient_id} in row {i+1} on page {page_number}")
                                    self.__take_screenshot(f"CREDIT_BILL_FOUND_{bill_no}_PAGE_{page_number}")
                                    
                                    # Look for View button in this row
                                    view_buttons = row.find_elements(By.XPATH, ".//a[contains(@class, 'btn') and contains(text(), 'View')]")
                                    if view_buttons:
                                        view_btn = view_buttons[0]
                                        logging.info(f"View button found for credit bill {bill_no}")
                                        
                                        # Extract bill ID from the View button's href attribute if we don't have it
                                        if bill_id == "unknown" or not bill_id:
                                            # Try to get bill ID from the View button's href attribute
                                            try:
                                                view_href = view_btn.get_attribute("href")
                                                # Extract bill ID from URL like "...?billId=12345"
                                                bill_id_match = re.search(r'billId=(\d+)', view_href)
                                                if bill_id_match:
                                                    bill_id = bill_id_match.group(1)
                                                    logging.info(f"Extracted bill ID {bill_id} from View button href")
                                            except Exception as e:
                                                logging.warning(f"Could not extract bill ID from View button: {str(e)}")
                                        
                                        # Store original URL
                                        original_url = self.driver.current_url
                                        
                                        # Click the View button using JavaScript to avoid interception
                                        try:
                                            self.driver.execute_script("arguments[0].click();", view_btn)
                                            logging.info(f"Clicked View button for credit bill {bill_no}")
                                            self.__take_screenshot(f"VIEW_BUTTON_CLICKED_{bill_no}_PAGE_{page_number}")
                                            
                                            # Wait for page to load
                                            time.sleep(3)
                                            
                                            # Handle the bill collection process
                                            self.__handle_bill_collection_in_same_window(original_url, credit_amount, bill_no, bill_id, patient_id)
                                            total_credit_bills_collected += 1
                                            
                                            # After returning to bill list, break to avoid stale element issues
                                            break
                                            
                                        except Exception as e:
                                            logging.error(f"Error clicking View button for bill {bill_no}: {str(e)}")
                                            self.__take_screenshot(f"VIEW_BUTTON_ERROR_{bill_no}_PAGE_{page_number}")
                                    else:
                                        logging.warning(f"No View button found for credit bill {bill_no}")
                                        self.__take_screenshot(f"NO_VIEW_BUTTON_{bill_no}_PAGE_{page_number}")
                            else:
                                logging.debug(f"Row {i+1} doesn't have enough cells: {len(cells)}")
                                
                        except Exception as e:
                            logging.warning(f"Error processing row {i+1} on page {page_number}: {str(e)}")
                            self.__take_screenshot(f"ROW_PROCESSING_ERROR_PAGE_{page_number}_ROW_{i+1}")
                    
                    if credit_bills_found_on_page == 0:
                        logging.info(f"No credit bills found on page {page_number}")
                        self.__take_screenshot(f"NO_CREDIT_BILLS_FOUND_PAGE_{page_number}")
                    
                except TimeoutException:
                    logging.error(f"Bill table not found on page {page_number}")
                    self.__take_screenshot(f"BILL_TABLE_NOT_FOUND_PAGE_{page_number}")
                
                # Check if there's a next page
                try:
                    next_button = self.driver.find_element(By.ID, "tbl-bill-list_next")
                    # Check if the next button is disabled
                    if "disabled" in next_button.get_attribute("class"):
                        logging.info("Reached last page, no more pages to process")
                        break
                    else:
                        logging.info(f"Moving to next page {page_number + 1}")
                        page_number += 1
                        time.sleep(2)  # Wait before loading next page
                except:
                    logging.info("No pagination found or reached last page")
                    break
            
            logging.info(f"Total credit bills collected: {total_credit_bills_collected}")
                    
        except Exception as e:
            self.__take_screenshot("BILL_LIST_ERROR")
            logging.error(f"Error in bill list processing: {str(e)}")
            raise

    def __handle_bill_collection_in_same_window(self, original_url, credit_amount, bill_no, bill_id, patient_id):
        """
        Handle the bill collection process when navigation occurs in the same window.
        """
        try:
            # Wait for page to load
            time.sleep(3)
            logging.info("Navigated to bill details page in same window")
            self.__take_screenshot("NAVIGATED_TO_BILL_DETAILS")
            
            # Get the paid amount (already paid)
            try:
                paid_amount_element = self.wait.until(EC.presence_of_element_located((By.NAME, "paidAmount")))
                paid_amount = paid_amount_element.get_attribute("value")
                logging.info(f"Paid amount: {paid_amount}")
            except Exception as e:
                logging.warning(f"Could not get paid amount: {str(e)}")
                paid_amount = "0"
            
            # Get the grand total
            try:
                grand_total_element = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".rounded_grand_total")))
                grand_total = grand_total_element.text
                logging.info(f"Grand total: {grand_total}")
            except Exception as e:
                logging.warning(f"Could not get grand total: {str(e)}")
                grand_total = "0"
            
            # For credit bills, we collect the full credit amount
            # Extract numeric value from credit amount
            try:
                # Handle different formats like "Rs. 1,215", "1,215.00", "1215", etc.
                credit_amount_clean = re.search(r'[\d,]+\.?\d*', credit_amount).group()
                credit_amount_value = float(credit_amount_clean.replace(',', ''))
                logging.info(f"Credit amount to collect: {credit_amount_value}")
            except Exception as e:
                logging.error(f"Error extracting credit amount from '{credit_amount}': {str(e)}")
                # Fallback: try to get the value from the grand total
                try:
                    grand_total_clean = re.search(r'[\d,]+\.?\d*', grand_total).group()
                    credit_amount_value = float(grand_total_clean.replace(',', ''))
                    logging.info(f"Using grand total as credit amount: {credit_amount_value}")
                except Exception as e2:
                    logging.error(f"Error using grand total as fallback: {str(e2)}")
                    # Last resort: try to extract any number from the credit amount string
                    try:
                        numbers = re.findall(r'\d+', credit_amount)
                        if numbers:
                            credit_amount_value = float(numbers[0])
                            logging.info(f"Using first number {credit_amount_value} from credit amount string")
                        else:
                            credit_amount_value = 0
                    except Exception as e3:
                        logging.error(f"Error extracting any number: {str(e3)}")
                        credit_amount_value = 0
            
            # Enter the full credit amount in the Received Amount field
            try:
                received_amount_field = self.wait.until(EC.presence_of_element_located((By.NAME, "paidAmount")))
                received_amount_field.clear()
                received_amount_field.send_keys(str(credit_amount_value))
                logging.info(f"Entered full credit amount {credit_amount_value} in Received Amount field")
                self.__take_screenshot("CREDIT_AMOUNT_ENTERED")
            except Exception as e:
                logging.error(f"Error entering credit amount: {str(e)}")
                self.__take_screenshot("CREDIT_AMOUNT_ERROR")
            
            # Enter remarks
            try:
                remarks_field = self.driver.find_element(By.NAME, "billRemarks")
                remarks_field.clear()
                remarks_field.send_keys("Credit bill collected")
                logging.info("Entered remarks: 'Credit bill collected'")
                self.__take_screenshot("REMARKS_ENTERED")
            except Exception as e:
                logging.warning(f"Could not enter remarks using NAME 'billRemarks': {str(e)}")
                # Try alternative remark field selectors
                try:
                    remarks_field = self.driver.find_element(By.ID, "billRemarks")
                    remarks_field.clear()
                    remarks_field.send_keys("Credit bill collected")
                    logging.info("Entered remarks using ID 'billRemarks'")
                    self.__take_screenshot("REMARKS_ENTERED_BY_ID")
                except Exception as e2:
                    logging.warning(f"Could not enter remarks using ID 'billRemarks': {str(e2)}")
                    # Try textarea with placeholder
                    try:
                        remarks_field = self.driver.find_element(By.XPATH, "//textarea[contains(@placeholder, 'Bill Remarks')]")
                        remarks_field.clear()
                        remarks_field.send_keys("Credit bill collected")
                        logging.info("Entered remarks using textarea with placeholder")
                        self.__take_screenshot("REMARKS_ENTERED_TEXTAREA")
                    except Exception as e3:
                        logging.warning(f"Could not enter remarks using textarea: {str(e3)}")
            
            # Click Submit button
            try:
                submit_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "sbmtbtn")))
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", submit_btn)
                time.sleep(1)  # Increased from 0.5 to 1 second
                # Use JavaScript click to avoid interception issues
                self.driver.execute_script("arguments[0].click();", submit_btn)
                logging.info("Clicked Submit button")
                self.__take_screenshot("SUBMIT_BUTTON_CLICKED")
                
                # Wait for success notification
                try:
                    # Small delay to allow notification to appear
                    time.sleep(2)
                    success_notification = self.wait.until(
                        EC.visibility_of_element_located((By.XPATH, 
                            "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')] | //div[contains(@class, 'alert-success')] | //div[contains(@class, 'ui-pnotify') and contains(@class, 'success')] | //div[contains(@class, 'toast-success')] | //div[contains(@class, 'success-message')]"))
                    )
                    logging.info("Bill collection successful")
                    self.__take_screenshot("COLLECTION_SUCCESS")
                    
                    # Save collected bill information to JSON file
                    self.__save_collected_bill_info(bill_no, bill_id, patient_id, credit_amount_value)
                except TimeoutException:
                    logging.warning("No success notification found after collection")
                    self.__take_screenshot("NO_COLLECTION_SUCCESS_NOTIFICATION")
                    
                    # Even if we don't see the success notification, still save the bill info
                    # as it might have been collected successfully
                    self.__save_collected_bill_info(bill_no, bill_id, patient_id, credit_amount_value)
                    
            except Exception as e:
                logging.error(f"Error clicking Submit button: {str(e)}")
                self.__take_screenshot("SUBMIT_BUTTON_ERROR")
            
            # Navigate back to the original bill list
            try:
                self.driver.get(original_url)
                logging.info("Navigated back to original bill list")
                self.__take_screenshot("BACK_TO_BILL_LIST")
                
                # Wait for page to load
                time.sleep(3)
            except Exception as e:
                logging.error(f"Error navigating back to bill list: {str(e)}")
                
        except Exception as e:
            logging.error(f"Error in bill collection handling: {str(e)}")
            self.__take_screenshot("COLLECTION_HANDLING_ERROR")

    def __save_collected_bill_info(self, bill_no, bill_id, patient_id, amount_collected):
        """
        Save collected bill information to a JSON file.
        """
        try:
            # Create a dictionary with the bill information
            bill_data = {
                "bill_no": bill_no if bill_no else "unknown",
                "bill_id": bill_id if bill_id and bill_id != "unknown" else "unknown",
                "patient_id": patient_id if patient_id else "unknown",
                "amount_collected": amount_collected if amount_collected else 0,
                "collection_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Create JSON filename with bill number
            json_filename = f"{bill_no if bill_no else 'unknown'}.json"
            json_filepath = os.path.join(collected_bills_dir, json_filename)
            
            # Write data to JSON file
            with open(json_filepath, "w") as json_file:
                json.dump(bill_data, json_file, indent=4)
            
            logging.info(f"Collected bill information saved to {json_filepath}")
        except Exception as e:
            logging.error(f"Error saving collected bill information: {str(e)}")
            self.__take_screenshot("SAVE_BILL_INFO_ERROR")

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
    
    # Generate timestamp for unique report name
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    
    runner = xmlrunner.XMLTestRunner(
        output=report_dir,
        verbosity=2,
        outsuffix=f"_{timestamp}"
    )
    
    suite = unittest.TestLoader().loadTestsFromTestCase(EMRCollectCreditBills)
    runner.run(suite)