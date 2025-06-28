import yaml 
import os

class ConfigManager:
    def __init__(self, config_path):
        """
        Initialize the configuration manager.
        :param config_path: Path to the YAML configuration file.
        """
        self.config_path = config_path
        self.config = {}

    def load_config(self):
        """
        Load configuration from the YAML file.
        """
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as file:
                self.config = yaml.safe_load(file)
                print(f"Configuration loaded from {self.config_path}.")
        else:
            print(f"Configuration file {self.config_path} does not exist. Using default configuration.")

    def save_config(self):
        """
        Save the current configuration to the YAML file.
        """
        with open(self.config_path, 'w') as file:
            yaml.dump(self.config, file, default_flow_style=False)
            print(f"Configuration saved to {self.config_path}.")

    def get(self, key, default=None):
        """
        Get a configuration value.
        :param key: Key of the configuration item.
        :param default: Default value if the key is not found.
        :return: Value of the configuration item.
        """
        return self.config.get(key, default)

    def set(self, key, value):
        """
        Set a configuration value.
        :param key: Key of the configuration item.
        :param value: Value to set.
        """
        self.config[key] = value
        print(f"Set configuration: {key} = {value}")

    # copy the config file to the give destination
    def save_config_to_file(self, destination):
        """
        Copy the configuration file to the destination.
        :param destination: Path to the destination file.
        """
        # os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(self.config_path, 'r') as file:
            with open(destination, 'w') as dest:
                dest.write(file.read())
                print(f"Configuration file copied to {destination}.")