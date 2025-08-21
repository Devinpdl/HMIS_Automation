import os
import json

class ConfigLoader:
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