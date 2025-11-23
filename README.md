# HMIS Automation Testing Framework

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Selenium](https://img.shields.io/badge/Selenium-4.0%2B-green.svg)](https://www.selenium.dev/)
[![ChromeDriver](https://img.shields.io/badge/ChromeDriver-Latest-brightgreen.svg)](https://chromedriver.chromium.org/)

## Overview

This repository contains an automated testing framework for the Hospital Management Information System (HMIS). Built with Python and Selenium WebDriver, it provides comprehensive end-to-end testing for critical healthcare workflows including OPD registration, billing, and patient management.
## Features

- 🏥 Automated OPD Registration workflow testing
- 💰 Integrated billing process validation
- 📊 Detailed test reporting and logging
- 📸 Automated screenshot capture for visual validation
- 🔄 Cross-browser compatibility (Chrome-focused)
- 🔒 Secure credential management

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Google Chrome Browser
- Git
- Visual Studio Code (recommended) or any preferred IDE

### System Requirements

| Component    | Minimum Version |
|-------------|----------------|
| Python      | 3.8+           |
| Chrome      | Latest         |
| ChromeDriver| Match Chrome   |
| RAM         | 4GB+           |
| Disk Space  | 1GB free       |



### Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/Devinpdl/HMIS_Automation.git
   cd HMIS_Automation
   ```

2. **Set Up Virtual Environment**
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```



3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

1. Create `utilities/config.json` with your HMIS credentials:
   ```json
   {
       "staging": {
           "base_url": "http://lunivacare.ddns.net:8080/himsnew/",
           "username": "your_username",
           "password": "your_password"
       }
   }
   ```

2. Verify ChromeDriver installation:
   ```bash
   chromedriver --version
   ```

## Project Structure

```
HMIS_Automation/
├── test_scripts/
│   ├── Opdregister.py
│   └── OpdregisterandOpdBilling.py
├── utilities/
│   ├── config_loader.py
│   └── config.json
├── reports/
│   ├── opd_registration/
│   └── opd_combined/
├── screenshots/
│   ├── opd_registration/
│   └── opd_combined/
├── requirements.txt
└── README.md
```
5. Verify ChromeDriver Setup
Ensure chromedriver is in your PATH or in the project directory:

Run chromedriver --version in your terminal to confirm it’s installed and compatible with your Chrome browser version.
If not in PATH, place chromedriver in the HMIS_Automation directory and update the scripts if necessary.

6. Run the Scripts
Execute an automation script (e.g., any .py file in the repository) by running:
python <script_name>.py

The scripts will:

Open Chrome and navigate to the HMIS application.
Log in using the credentials from config.json.
Perform automated workflows as defined in the script.
Save screenshots to screenshots/opd_combined/ (or other directories, depending on the script).
Save test reports and IDs to reports/opd_combined/ (or other directories).

7. View Output

Screenshots: Check the screenshots/ directory for screenshots taken during execution (e.g., LOGIN_SUCCESS_*.png, SUCCESS_NOTIFICATION_*.png).
Reports: XML test reports are saved in reports/ (e.g., TEST-*.xml).
Patient and Bill IDs: JSON files with relevant IDs are saved in reports/patient_ids/ and reports/bill_nos/ (or other directories, depending on the script).

## Troubleshooting Guide

### Common Issues and Solutions

1. **ChromeDriver Version Mismatch**
   ```
   Error: session not created
   Solution: Update ChromeDriver to match Chrome version
   ```

2. **Configuration Issues**
   ```
   Error: FileNotFoundError - config.json
   Solution: Ensure config.json exists in utilities/ directory
   ```

3. **Selenium Timeouts**
   ```
   Error: ElementNotInteractableException
   Solution: Increase wait times in test scripts
   ```

## Best Practices

1. **Code Organization**
   - Follow PEP 8 style guide
   - Maintain modular test structure
   - Use clear, descriptive test names

2. **Test Data Management**
   - Use unique test data for each run
   - Clean up test data after execution
   - Avoid hardcoding test values

3. **Error Handling**
   - Implement robust exception handling
   - Log all errors with context
   - Take screenshots on failures



## Contributing

1. Fork the repository
2. Create your feature branch:
   ```bash
   git checkout -b feature/AmazingFeature
   ```
3. Commit your changes:
   ```bash
   git commit -m 'Add some AmazingFeature'
   ```
4. Push to the branch:
   ```bash
   git push origin feature/AmazingFeature
   ```
5. Open a Pull Request

## Security

- Never commit sensitive credentials
- Keep `config.json` in `.gitignore`
- Regularly update dependencies
- Use environment variables where possible

## Support

For support and queries:
- Create an issue in the repository
- Contact the development team
- Refer to internal documentation

## License

This project is proprietary and confidential. Unauthorized copying or distribution is prohibited.

## Authors

- **Devin Samundra Paudel** - *Initial work* - [Devinpdl](https://github.com/Devinpdl)

---
Last Updated: August 19, 2025