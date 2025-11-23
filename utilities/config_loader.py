import json
import os

class ConfigLoader:
    """
    A class to load configuration from JSON files
    """
    @staticmethod
    def load_credentials(environment: str = "staging"):
        """Handle path resolution properly"""
        current_dir = os.path.dirname(os.path.abspath(__file__))  # utilities/
        project_root = os.path.dirname(current_dir)               # project root
        config_path = os.path.join(project_root, "config", "credentials.json")
        
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                return config[environment]
        except FileNotFoundError:
            raise RuntimeError(f"Missing config file at: {config_path}")
        except KeyError:
            raise RuntimeError(f"Environment '{environment}' not found in config")
    def __init__(self, config_file=None):
        """
        Initialize the ConfigLoader with a config file path
        If no path is provided, it will use the default credentials.json in the config directory
        """
        if config_file is None:
            # Get the root directory of the project
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_file = os.path.join(root_dir, 'config', 'credentials.json')
        
        self.config_file = config_file
        self.config_data = self._load_config()
    
    def _load_config(self):
        """
        Load the configuration from the JSON file
        """
        try:
            with open(self.config_file, 'r') as file:
                return json.load(file)
        except Exception as e:
            raise Exception(f"Error loading configuration file: {str(e)}")
    
    def get_credentials(self, environment='staging'):
        """
        Get credentials for the specified environment
        """
        if environment in self.config_data:
            return self.config_data[environment]
        else:
            raise ValueError(f"Environment '{environment}' not found in configuration")
    
    def get_url(self, environment='staging'):
        """
        Get the base URL for the specified environment
        """
        return self.get_credentials(environment)['base_url']
    
    def get_username(self, environment='staging'):
        """
        Get the username for the specified environment
        """
        return self.get_credentials(environment)['username']
    
    def get_password(self, environment='staging'):
        """
        Get the password for the specified environment
        """
        return self.get_credentials(environment)['password']