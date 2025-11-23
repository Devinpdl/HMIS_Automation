import os
import re
import time
import logging
import unittest
import xmlrunner
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import sys
import os

# Add the parent directory to sys.path to allow imports from sibling packages
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utilities.config_loader import ConfigLoader
import xml.etree.ElementTree as ET  # To store Patient Id in XML report


# Folder configuration
screenshot_dir = os.path.join("screenshots", "opd_registration")
report_dir = os.path.join("reports", "opd_registration")
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(report_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


class OPDRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load credentials FIRST
        cls.config = ConfigLoader.load_credentials("staging")

        # THEN initialize browser components
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--enable-javascript")

        # Corrected experimental options:
        chrome_options.add_experimental_option("detach", True)
        chrome_options.add_experimental_option(
            "excludeSwitches",
            ["disable-popup-blocking"]
        )

        cls.driver = webdriver.Chrome(options=chrome_options)
        cls.driver.maximize_window()
        # Initialize wait AFTER driver creation
        cls.wait = WebDriverWait(cls.driver, 20)  # <--- THIS WAS MISSING

        # Set credentials from config
        cls.base_url = cls.config["base_url"]
        cls.valid_username = cls.config["username"]
        cls.valid_password = cls.config["password"]

    def setUp(self):
        self.driver.get(self.base_url)
        self.__login()
        self.patient_id = None

    def __take_screenshot(self, name):
        filename = f"{screenshot_dir}/{name}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        try:
            self.driver.save_screenshot(filename)
            logging.info(f"Screenshot saved: {filename}")
        except Exception as e:
            logging.error(f"Error taking screenshot: {str(e)}")

    def __login(self):
        try:
            self.driver.find_element(By.NAME, "Username").clear()
            self.driver.find_element(By.NAME, "Password").clear()

            username_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "Username")))
            password_field = self.driver.find_element(By.NAME, "Password")
            login_btn = self.driver.find_element(
                By.CSS_SELECTOR, "button[type='submit']")

            username_field.send_keys(self.valid_username)
            password_field.send_keys(self.valid_password)
            login_btn.click()

            self.wait.until(EC.url_contains("/dashboard"))
            logging.info("Login successful")
            # self.__take_screenshot("LOGIN_SUCCESS")
        except Exception as e:
            # self.__take_screenshot("LOGIN_FAILURE")
            logging.error(f"Login failed: {str(e)}")
            raise

    def test_opd_registration(self):
        try:
            # Navigate to OPD Registration
            self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//li[@id='patient_menu']/a"))).click()

            opd_register_link = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//a[@href='http://lunivacare.ddns.net:8080/himsnew/ipd/register/OPD']")))
            opd_register_link.click()
            logging.info("Navigated to OPD Registration page")
            # self.__take_screenshot("OPD_REGISTER_PAGE")

            # Fill mobile number and handle immediate modal
            mobile_field = self.wait.until(
                EC.presence_of_element_located((By.ID, "mobile-number")))
            mobile_field.send_keys("9800000000")
            logging.info("Entered mobile number")
            # self.__take_screenshot("MOBILE_ENTERED")

            # Handle potential immediate modal after number entry
            time.sleep(2)
            self.__handle_duplicate_patient_modal()

            # Continue with rest of form
            designation = Select(
                self.driver.find_element(By.ID, "designation"))
            designation.select_by_value("Mr.")
            logging.info("Selected designation")

            self.driver.find_element(By.ID, "first-name").send_keys("John")
            self.driver.find_element(By.ID, "last-name").send_keys("Doe")
            self.driver.find_element(By.ID, "age").send_keys("30")
            logging.info("Entered personal details")

            # Handle address selection
            self.driver.find_element(
                By.XPATH, "//span[@id='select2-current-address-container']").click()
            search_field = self.wait.until(EC.presence_of_element_located(
                (By.XPATH, "//input[@class='select2-search__field']")))
            search_field.send_keys("Kathmandu")

            address_option = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//li[contains(@class, 'select2-results__option') and contains(text(), 'Kathmandu')]")))
            address_option.click()
            logging.info("Selected address")
            # self.__take_screenshot("FORM_FILLED")

            # Submit form
            submit_btn = self.wait.until(
                EC.element_to_be_clickable((By.ID, "submitNewButton")))
            submit_btn.click()
            logging.info("Form submitted")
            # self.__take_screenshot("FORM_SUBMITTED")

            # Handle success notification
            self.__handle_success_notification()

            # Handle Print Bill and capture Patient ID
            # self.patient_id = self.__handle_print_bill_window()
            # logging.info(f"Captured Patient ID: {self.patient_id}")

            # Capture Patient ID directly from URL or new window
            self.patient_id = self.__capture_patient_id()
            logging.info(f"Captured Patient ID: {self.patient_id}")

            # Add to XML report description - PUT THIS RIGHT AFTER CAPTURING PATIENT ID
            # Add Patient ID to test description for XML report
            # This ensures the Patient ID appears in the XML report
            # <--- ADD THIS LINE
            self._testMethodDoc = f"Patient ID: {self.patient_id}"

        except Exception as e:
            # self.__take_screenshot("TEST_FAILURE")
            logging.error(f"Test failed: {str(e)}")
            raise

    def __handle_duplicate_patient_modal(self):
        """Handle modal appearing immediately after mobile number entry"""
        try:
            modal_locator = (By.XPATH, "//h4[contains(.,'Patient Info')]")
            proceed_btn_locator = (By.ID, "proceedToRegister")

            if len(self.driver.find_elements(*modal_locator)) > 0:
                logging.info("Duplicate patient modal detected")
                # self.__take_screenshot("DUPLICATE_MODAL_PRESENT")

                proceed_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable(proceed_btn_locator))
                self.driver.execute_script(
                    "arguments[0].click();", proceed_btn)
                logging.info("Clicked proceed button")
                # self.__take_screenshot("MODAL_HANDLED")

                WebDriverWait(self.driver, 3).until(
                    EC.invisibility_of_element_located(modal_locator))

        except Exception as e:
            logging.info(f"No duplicate modal present: {str(e)}")

    def __handle_success_notification(self):
        """Verify the success notification appears after submission"""
        try:
            notification = WebDriverWait(self.driver, 20).until(
                EC.visibility_of_element_located((
                    By.XPATH,
                    "//div[contains(@class, 'ui-pnotify-container') and contains(@class, 'brighttheme-success')]"
                ))
            )

            notification_text = notification.find_element(
                By.XPATH, ".//div[contains(@class, 'ui-pnotify-text') and contains(., 'Successfully registered')]"
            )

            logging.info("OPD registration successful")
            # self.__take_screenshot("SUCCESS_NOTIFICATION")

            try:
                close_btn = WebDriverWait(notification, 5).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, ".ui-pnotify-closer"))
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView(true);", close_btn)
                self.driver.execute_script("arguments[0].click();", close_btn)

                WebDriverWait(self.driver, 5).until(
                    EC.invisibility_of_element(notification)
                )

            except Exception as close_error:
                logging.info(
                    "Notification close button not required for test success")
                # self.__take_screenshot("NOTIFICATION_CLOSE_IGNORED")

        except TimeoutException:
            # self.__take_screenshot("SUBMISSION_ERROR")
            logging.error(
                "Success notification not found within timeout period")
            raise
        except Exception as e:
            # self.__take_screenshot("NOTIFICATION_ERROR")
            logging.error(f"Error verifying success notification: {str(e)}")
            raise

    # def __handle_print_bill_window(self):
    #     """Handle print bill window and return patient ID with multiple fallbacks"""
    #     try:
    #         main_window = self.driver.current_window_handle
    #         original_url = self.driver.current_url

    #         # 1. Attempt to click print button with multiple strategies
    #         try:
    #             print_btn = WebDriverWait(self.driver, 20).until(
    #                 EC.element_to_be_clickable((By.XPATH, "//button[@name='sticker_print']"))
    #             )
    #             self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", print_btn)
    #             print_btn.click()
    #         except Exception as e:
    #             logging.warning(f"Standard click failed: {str(e)}, trying JavaScript click")
    #             self.driver.execute_script("arguments[0].click();", print_btn)

    #         logging.info("Clicked Print Bill button")
    #         self.__take_screenshot("PRINT_BILL_CLICKED")

    #         # 2. Flexible waiting for either new window or URL change
    #         patient_id = None
    #         start_time = time.time()
    #         timeout = 10  # Total timeout in seconds

    #         while time.time() - start_time < timeout:
    #             # Check current window first
    #             if "create_stiker" in self.driver.current_url:
    #                 patient_id = self.__extract_patient_id(self.driver.current_url)
    #                 break

    #             # Check new windows
    #             new_windows = [w for w in self.driver.window_handles if w != main_window]
    #             if new_windows:
    #                 self.driver.switch_to.window(new_windows[0])
    #                 WebDriverWait(self.driver, 10).until(
    #                     EC.url_contains("create_stiker")
    #                 )
    #                 patient_id = self.__extract_patient_id(self.driver.current_url)
    #                 break

    #             time.sleep(1)  # Polling interval

    #         if not patient_id:
    #             raise TimeoutException("Failed to detect print window or URL change")

    #         # 3. Window cleanup
    #         if len(self.driver.window_handles) > 1:
    #             self.driver.close()  # Close print window if exists
    #             self.driver.switch_to.window(main_window)

    #         # 4. Final verification
    #         logging.info(f"Validated Patient ID: {patient_id}")
    #         return patient_id

    #     except Exception as e:
    #         self.__take_screenshot("PRINT_WINDOW_ERROR")
    #         logging.error(f"Final print window failure: {str(e)}")
    #         raise

    def __capture_patient_id(self):
        """Capture patient ID from URL after form submission"""
        try:
            main_window = self.driver.current_window_handle
            patient_id = None

            # Wait for either URL change or new window
            WebDriverWait(self.driver, 20).until(
                lambda d: "create_stiker" in d.current_url or len(
                    d.window_handles) > 1
            )

            # Handle different scenarios
            if len(self.driver.window_handles) > 1:
                # New window opened
                self.driver.switch_to.window(self.driver.window_handles[-1])
                patient_id = self.__extract_id_from_url(
                    self.driver.current_url)
                self.driver.close()
                self.driver.switch_to.window(main_window)
            else:
                # URL changed in same window
                patient_id = self.__extract_id_from_url(
                    self.driver.current_url)

            if not patient_id:
                raise ValueError("Patient ID not found in URL")

            return patient_id

        except Exception as e:
            # self.__take_screenshot("PATIENT_ID_ERROR")
            logging.error(f"Patient ID capture failed: {str(e)}")
            raise

    def __extract_id_from_url(self, url):
        """Extract patient ID from create_stiker URL"""
        match = re.search(r'/create_stiker/(\d+)', url)
        if match:
            return match.group(1)
        raise ValueError(f"Patient ID not found in URL: {url}")

    def __extract_patient_id(self, url):
        """Multi-layered patient ID extraction"""
        try:
            # Strategy 1: URL extraction
            match = re.search(r'create_stiker/(\d+)', url)
            if match:
                return match.group(1)

        # Strategy 2: DOM element extraction
            try:
                return WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//td[contains(., 'Pat Id.:')]/b")
                    )
                ).text.split("Pat Id.:")[1].strip()

            except:
                # Strategy 3: Full page text search
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                match = re.search(r'Pat Id\.:\s*(\d+)', page_text)
                if match:
                    return match.group(1)

            # Final fallback: Screenshot analysis warning
            logging.warning(
                "Patient ID not found via standard methods - check screenshots")
            return "EXTRACTION_FAILED_SEE_SCREENSHOT"

        except Exception as e:
            logging.error(f"Patient ID extraction failed: {str(e)}")
            raise

    @classmethod
    def tearDownClass(cls):
        logging.info("Cleaning up browser windows...")
        try:
            # Close all windows except the main one
            while len(cls.driver.window_handles) > 1:
                cls.driver.switch_to.window(cls.driver.window_handles[-1])
                cls.driver.close()
            # Switch back to main window
            cls.driver.switch_to.window(cls.driver.window_handles[0])
        except Exception as e:
            logging.error(f"Error during cleanup: {str(e)}")
        finally:
            logging.info("Cleanup completed. Main window remains open.")

    def tearDown(self):
        """Handle patient ID in reports safely"""
        if hasattr(self, 'patient_id'):
            # Include Patient ID in XML test report
            if hasattr(self, "_outcome"):
                result = self._outcome.result
                if result and hasattr(result, "addAttribute"):
                    result.addAttribute("PatientID", str(self.patient_id))

            else:
                logging.warning(
                    "Patient ID not captured during test execution")


if __name__ == "__main__":
    unittest.main(
        testRunner=xmlrunner.XMLTestRunner(output=report_dir, verbosity=2),
        failfast=False, buffer=False, catchbreak=False
    )

    # Set verbosity=2 to include more test details.
