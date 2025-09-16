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
screenshot_dir = os.path.join("screenshots", "emr_collect_due")
report_dir = os.path.join("reports", "emr_collect_due")
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class EMRCollectDueBills(unittest.TestCase):
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

    def test_collect_emr_due_bills(self):
        """
        Test method: Navigate to EMR bill list, find due bills, and collect them.
        """
        logging.info("Starting EMR Due Bill Collection...")
        self.__collect_emr_due_bills()

    def __collect_emr_due_bills(self):
        """
        Collect EMR due bills from the bill list.
        """
        try:
            page_number = 1
            total_due_bills_collected = 0
            
            while True:
                # Navigate directly to EMR Bill List for current page
                self.driver.get(f"http://lunivacare.ddns.net:8080/himsnew/bill/bill_list?list=Emergency&page={page_number}")
                time.sleep(3)  # Wait for page to load
                logging.info(f"Navigated to EMR Bill List page {page_number}")
                self.__take_screenshot(f"EMR_BILL_LIST_PAGE_{page_number}")
                
                # Look for bill table
                try:
                    bill_table = self.wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'table')]")))
                    logging.info("Bill table found")
                    self.__take_screenshot(f"BILL_TABLE_FOUND_PAGE_{page_number}")
                    
                    # Find all rows in the table
                    rows = bill_table.find_elements(By.XPATH, ".//tbody//tr")
                    logging.info(f"Found {len(rows)} bill rows on page {page_number}")
                    
                    # Process each row to find due bills
                    due_bills_found_on_page = 0
                    for i, row in enumerate(rows):
                        try:
                            # Get cells in the row
                            cells = row.find_elements(By.XPATH, ".//td")
                            if len(cells) >= 8:  # Ensure we have enough cells
                                # Check if this is a due bill (look for "Due" in status column - 8th column)
                                status_cell = cells[7]  # 8th column is status
                                status_text = status_cell.text.strip()
                                
                                if "Due" in status_text:
                                    due_bills_found_on_page += 1
                                    bill_no = cells[0].text.strip()  # 1st column is bill number
                                    due_amount = cells[6].text.strip()  # 7th column is due amount
                                    logging.info(f"Found due bill {bill_no} with due amount {due_amount} in row {i+1} on page {page_number}")
                                    self.__take_screenshot(f"DUE_BILL_FOUND_{bill_no}_PAGE_{page_number}")
                                    
                                    # Look for View button in this row
                                    view_buttons = row.find_elements(By.XPATH, ".//a[contains(@class, 'btn') and contains(text(), 'View')]")
                                    if view_buttons:
                                        view_btn = view_buttons[0]
                                        logging.info(f"View button found for due bill {bill_no}")
                                        
                                        # Store original URL
                                        original_url = self.driver.current_url
                                        
                                        # Click the View button using JavaScript to avoid interception
                                        try:
                                            self.driver.execute_script("arguments[0].click();", view_btn)
                                            logging.info(f"Clicked View button for due bill {bill_no}")
                                            self.__take_screenshot(f"VIEW_BUTTON_CLICKED_{bill_no}_PAGE_{page_number}")
                                            
                                            # Wait for page to load
                                            time.sleep(3)
                                            
                                            # Handle the bill collection process
                                            self.__handle_bill_collection_in_same_window(original_url, due_amount)
                                            total_due_bills_collected += 1
                                            
                                            # After returning to bill list, break to avoid stale element issues
                                            break
                                            
                                        except Exception as e:
                                            logging.error(f"Error clicking View button for bill {bill_no}: {str(e)}")
                                            self.__take_screenshot(f"VIEW_BUTTON_ERROR_{bill_no}_PAGE_{page_number}")
                                    else:
                                        logging.warning(f"No View button found for due bill {bill_no}")
                                        self.__take_screenshot(f"NO_VIEW_BUTTON_{bill_no}_PAGE_{page_number}")
                            else:
                                logging.debug(f"Row {i+1} doesn't have enough cells: {len(cells)}")
                                
                        except Exception as e:
                            logging.warning(f"Error processing row {i+1} on page {page_number}: {str(e)}")
                            self.__take_screenshot(f"ROW_PROCESSING_ERROR_PAGE_{page_number}_ROW_{i+1}")
                    
                    if due_bills_found_on_page == 0:
                        logging.info(f"No due bills found on page {page_number}")
                        self.__take_screenshot(f"NO_DUE_BILLS_FOUND_PAGE_{page_number}")
                    
                except TimeoutException:
                    logging.error(f"Bill table not found on page {page_number}")
                    self.__take_screenshot(f"BILL_TABLE_NOT_FOUND_PAGE_{page_number}")
                
                # Check if there's a next page
                try:
                    next_button = self.driver.find_element(By.ID, "tbl-bill-list_next")
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
            
            logging.info(f"Total due bills collected: {total_due_bills_collected}")
                    
        except Exception as e:
            self.__take_screenshot("BILL_LIST_ERROR")
            logging.error(f"Error in bill list processing: {str(e)}")
            raise

    def __handle_bill_collection_in_same_window(self, original_url, due_amount):
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
                paid_amount_element = self.wait.until(EC.presence_of_element_located((By.NAME, "receivedAmount")))
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
            
            # Calculate remaining amount to be paid
            try:
                grand_total_value = int(grand_total)
                paid_amount_value = int(paid_amount)
                remaining_amount = grand_total_value - paid_amount_value
                logging.info(f"Remaining amount to pay: {remaining_amount}")
            except Exception as e:
                logging.error(f"Error calculating remaining amount: {str(e)}")
                remaining_amount = due_amount  # Use the due amount from the table
            
            # Enter the remaining amount in the Received Amount field
            try:
                received_amount_field = self.wait.until(EC.presence_of_element_located((By.NAME, "paidAmount")))
                received_amount_field.clear()
                received_amount_field.send_keys(str(remaining_amount))
                logging.info(f"Entered remaining amount {remaining_amount} in Received Amount field")
                self.__take_screenshot("REMAINING_AMOUNT_ENTERED")
            except Exception as e:
                logging.error(f"Error entering remaining amount: {str(e)}")
                self.__take_screenshot("REMAINING_AMOUNT_ERROR")
            
            # Enter remarks
            try:
                remarks_field = self.driver.find_element(By.NAME, "remarks")
                remarks_field.clear()
                remarks_field.send_keys("Due payment test paid")
                logging.info("Entered remarks: 'Due payment test paid'")
                self.__take_screenshot("REMARKS_ENTERED")
            except Exception as e:
                logging.warning(f"Could not enter remarks: {str(e)}")
                # Try alternative remark field names
                try:
                    remarks_fields = self.driver.find_elements(By.XPATH, "//input[contains(@name, 'remark') or contains(@id, 'remark') or contains(@placeholder, 'remark')]")
                    if remarks_fields:
                        remarks_fields[0].clear()
                        remarks_fields[0].send_keys("Due payment test paid")
                        logging.info("Entered remarks in alternative field")
                        self.__take_screenshot("REMARKS_ENTERED_ALTERNATIVE")
                except Exception as e2:
                    logging.warning(f"Could not enter remarks in alternative field: {str(e2)}")
            
            # Click Submit button
            try:
                submit_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "sbmtbtn")))
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", submit_btn)
                time.sleep(0.5)
                submit_btn.click()
                logging.info("Clicked Submit button")
                self.__take_screenshot("SUBMIT_BUTTON_CLICKED")
                
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
    
    suite = unittest.TestLoader().loadTestsFromTestCase(EMRCollectDueBills)
    runner.run(suite)