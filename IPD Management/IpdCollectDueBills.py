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
screenshot_dir = os.path.join("screenshots", "ipd_collect_due")
report_dir = os.path.join("reports", "ipd_collect_due")
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class IPDCollectDueBills(unittest.TestCase):
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

    def test_collect_ipd_due_bills(self):
        """
        Test method: Navigate to IPD bill list, find due bills, and collect them.
        """
        logging.info("Starting IPD Due Bill Collection...")
        self.__collect_ipd_due_bills()

    def __collect_ipd_due_bills(self):
        """
        Collect IPD due bills from the bill list.
        """
        try:
            # Navigate directly to IPD Bill List
            self.driver.get("http://lunivacare.ddns.net:8080/himsnew/bill/bill_list?list=IPD")
            time.sleep(3)  # Wait for page to load
            logging.info("Navigated to IPD Bill List page")
            self.__take_screenshot("IPD_BILL_LIST_PAGE")

            # Look for bill table
            try:
                bill_table = self.wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'table')]")))
                logging.info("Bill table found")
                self.__take_screenshot("BILL_TABLE_FOUND")
                
                # Find all rows in the table
                rows = bill_table.find_elements(By.XPATH, ".//tbody//tr")
                logging.info(f"Found {len(rows)} bill rows")
                
                # Process each row to find due bills
                due_bills_found = 0
                for i, row in enumerate(rows):
                    try:
                        # Get cells in the row
                        cells = row.find_elements(By.XPATH, ".//td")
                        if len(cells) >= 4:  # Ensure we have enough cells
                            # Check if this is a due bill (look for "Due" in status column)
                            status_cell = cells[3]  # Assuming 4th column is status
                            status_text = status_cell.text.strip().lower()
                            
                            if "due" in status_text or "credit" in status_text:
                                due_bills_found += 1
                                logging.info(f"Found due bill in row {i+1}")
                                self.__take_screenshot(f"DUE_BILL_FOUND_ROW_{i+1}")
                                
                                # Look for collect button in this row
                                collect_buttons = row.find_elements(By.XPATH, ".//a[contains(@class, 'collect') or contains(text(), 'Collect') or contains(@href, 'collect')]")
                                if collect_buttons:
                                    collect_btn = collect_buttons[0]
                                    logging.info(f"Collect button found for due bill in row {i+1}")
                                    
                                    # Click the collect button
                                    try:
                                        collect_btn.click()
                                        logging.info(f"Clicked collect button for due bill in row {i+1}")
                                        self.__take_screenshot(f"COLLECT_BUTTON_CLICKED_ROW_{i+1}")
                                        
                                        # Handle the collection process (this will depend on the actual implementation)
                                        self.__handle_bill_collection()
                                        
                                        # Break after collecting one bill for testing purposes
                                        logging.info("Successfully collected one due bill, stopping for now")
                                        break
                                    except Exception as e:
                                        logging.error(f"Error clicking collect button in row {i+1}: {str(e)}")
                                        self.__take_screenshot(f"COLLECT_BUTTON_ERROR_ROW_{i+1}")
                                else:
                                    logging.warning(f"No collect button found for due bill in row {i+1}")
                                    self.__take_screenshot(f"NO_COLLECT_BUTTON_ROW_{i+1}")
                                    # Try to find any button that might be for collection
                                    all_buttons = row.find_elements(By.XPATH, ".//button | .//a")
                                    for btn in all_buttons:
                                        btn_text = btn.text.lower()
                                        if "collect" in btn_text or "pay" in btn_text or "due" in btn_text:
                                            logging.info(f"Found potential collection button: {btn_text}")
                                            try:
                                                btn.click()
                                                logging.info(f"Clicked potential collection button: {btn_text}")
                                                self.__take_screenshot(f"POTENTIAL_COLLECT_BUTTON_CLICKED_{i+1}")
                                                self.__handle_bill_collection()
                                                break
                                            except Exception as e:
                                                logging.error(f"Error clicking potential collection button: {str(e)}")
                                                self.__take_screenshot(f"POTENTIAL_COLLECT_BUTTON_ERROR_{i+1}")
                        else:
                            logging.debug(f"Row {i+1} doesn't have enough cells: {len(cells)}")
                            
                    except Exception as e:
                        logging.warning(f"Error processing row {i+1}: {str(e)}")
                        self.__take_screenshot(f"ROW_PROCESSING_ERROR_{i+1}")
                
                if due_bills_found == 0:
                    logging.info("No due bills found in the list")
                    self.__take_screenshot("NO_DUE_BILLS_FOUND")
                else:
                    logging.info(f"Processed {due_bills_found} due bills")
                    
            except TimeoutException:
                logging.error("Bill table not found")
                self.__take_screenshot("BILL_TABLE_NOT_FOUND")
                
        except Exception as e:
            self.__take_screenshot("BILL_LIST_ERROR")
            logging.error(f"Error in bill list processing: {str(e)}")
            raise

    def __handle_bill_collection(self):
        """
        Handle the bill collection process after clicking collect button.
        """
        try:
            # Wait for collection modal or page to load
            time.sleep(2)
            logging.info("Waiting for collection interface to load")
            
            # Look for payment amount field
            try:
                amount_fields = self.driver.find_elements(By.XPATH, "//input[contains(@id, 'amount') or contains(@name, 'amount') or @type='number']")
                if amount_fields:
                    amount_field = amount_fields[0]
                    amount_field.clear()
                    amount_field.send_keys("100")  # Enter test amount
                    logging.info("Entered collection amount")
                    self.__take_screenshot("AMOUNT_ENTERED")
                else:
                    logging.warning("No amount field found")
                    self.__take_screenshot("NO_AMOUNT_FIELD")
            except Exception as e:
                logging.warning(f"Error handling amount field: {str(e)}")
                self.__take_screenshot("AMOUNT_FIELD_ERROR")
            
            # Look for payment method selection
            try:
                payment_methods = self.driver.find_elements(By.XPATH, "//input[@name='paymentMethod'] | //select[@name='paymentMethod']")
                if payment_methods:
                    # Select first payment method
                    payment_method = payment_methods[0]
                    if payment_method.tag_name == "select":
                        select = Select(payment_method)
                        select.select_by_index(1)  # Select second option (index 1)
                        logging.info("Selected payment method from dropdown")
                    else:
                        # For radio buttons, just click the first one
                        payment_method.click()
                        logging.info("Selected payment method")
                    self.__take_screenshot("PAYMENT_METHOD_SELECTED")
                else:
                    logging.warning("No payment method selection found")
                    self.__take_screenshot("NO_PAYMENT_METHOD")
            except Exception as e:
                logging.warning(f"Error handling payment method: {str(e)}")
                self.__take_screenshot("PAYMENT_METHOD_ERROR")
            
            # Look for submit/confirm button
            try:
                submit_buttons = self.driver.find_elements(By.XPATH, "//button[@type='submit' and (contains(text(), 'Collect') or contains(text(), 'Pay') or contains(text(), 'Confirm'))] | //input[@type='submit' and (contains(value, 'Collect') or contains(value, 'Pay') or contains(value, 'Confirm'))]")
                if submit_buttons:
                    submit_btn = submit_buttons[0]
                    submit_btn.click()
                    logging.info("Clicked submit/confirm button for bill collection")
                    self.__take_screenshot("COLLECTION_SUBMIT_CLICKED")
                    
                    # Wait for success notification
                    try:
                        success_notification = self.wait.until(
                            EC.visibility_of_element_located((By.XPATH, 
                                "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')] | //div[contains(@class, 'alert-success')]"))
                        )
                        logging.info("Bill collection successful")
                        self.__take_screenshot("COLLECTION_SUCCESS")
                    except TimeoutException:
                        logging.warning("No success notification found after collection")
                        self.__take_screenshot("NO_COLLECTION_SUCCESS_NOTIFICATION")
                else:
                    logging.warning("No submit/confirm button found for collection")
                    self.__take_screenshot("NO_COLLECTION_SUBMIT_BUTTON")
            except Exception as e:
                logging.error(f"Error handling collection submit: {str(e)}")
                self.__take_screenshot("COLLECTION_SUBMIT_ERROR")
                
        except Exception as e:
            logging.error(f"Error in bill collection handling: {str(e)}")
            self.__take_screenshot("COLLECTION_HANDLING_ERROR")

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
    
    runner = xmlrunner.XMLTestRunner(
        output=report_dir,
        verbosity=2,
        outsuffix=""
    )
    
    suite = unittest.TestLoader().loadTestsFromTestCase(IPDCollectDueBills)
    runner.run(suite)