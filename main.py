import argparse
import difflib
import json
import logging
import os
import subprocess
import sys
import tempfile
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ConfigBaselineComparator:
    """
    Compares a configuration file against a known good baseline, flagging deviations.
    """

    def __init__(self, current_config_path, baseline_config_path, output_format="diff"):
        """
        Initializes the ConfigBaselineComparator.

        Args:
            current_config_path (str): Path to the current configuration file.
            baseline_config_path (str): Path to the baseline configuration file.
            output_format (str): The format of the output (e.g., "diff", "json").  Defaults to "diff".
        """
        self.current_config_path = current_config_path
        self.baseline_config_path = baseline_config_path
        self.output_format = output_format
        self.logger = logging.getLogger(__name__)


    def _load_config(self, config_path):
        """
        Loads a configuration file, attempting to automatically detect the format (YAML or JSON).

        Args:
            config_path (str): Path to the configuration file.

        Returns:
            dict: The configuration data as a dictionary.

        Raises:
            ValueError: If the file format cannot be determined or if loading fails.
        """
        try:
            with open(config_path, 'r') as f:
                # Attempt to automatically detect format based on file extension
                if config_path.lower().endswith(('.yaml', '.yml')):
                    return yaml.safe_load(f)
                elif config_path.lower().endswith('.json'):
                    return json.load(f)
                else:
                    # Attempt to load as YAML first, then JSON if that fails
                    try:
                        return yaml.safe_load(f)
                    except yaml.YAMLError:
                        try:
                            return json.load(f)
                        except json.JSONDecodeError:
                            raise ValueError("Could not determine file format (YAML or JSON) or loading failed.")
        except FileNotFoundError:
            self.logger.error(f"File not found: {config_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading config file {config_path}: {e}")
            raise ValueError(f"Error loading config file: {e}")

    def _validate_file_exists(self, file_path):
        """
        Validates that the given file path exists.

        Args:
            file_path (str): The path to the file.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        if not os.path.exists(file_path):
            self.logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
        if not os.path.isfile(file_path):
            self.logger.error(f"Not a file: {file_path}")
            raise ValueError(f"Not a file: {file_path}")

    def _run_linter(self, file_path, linter_type):
        """
        Runs yamllint or jsonlint to validate config file syntax

        Args:
            file_path (str): Path to the configuration file
            linter_type (str): The type of linter ("yaml" or "json")

        Returns:
            bool: True if linter passes, False otherwise.
        """
        try:
            if linter_type == "yaml":
                result = subprocess.run(['yamllint', file_path], capture_output=True, text=True, check=True)
                return True
            elif linter_type == "json":
                result = subprocess.run(['jsonlint', '-q', file_path], capture_output=True, text=True, check=True)  # -q for quiet mode
                return True
            else:
                self.logger.warning(f"Unknown linter type: {linter_type}. Skipping linting.")
                return True
        except FileNotFoundError as e:
            self.logger.warning(f"{linter_type} not found. Skipping linting.  Ensure {linter_type} is installed and in your PATH.")
            return True # Non-critical, so continue execution
        except subprocess.CalledProcessError as e:
            self.logger.error(f"{linter_type} found errors in {file_path}:\n{e.stderr}")
            return False
        except Exception as e:
            self.logger.error(f"Error running {linter_type} on {file_path}: {e}")
            return False



    def compare_configs(self):
        """
        Compares the current configuration against the baseline.

        Returns:
            str: The comparison output, formatted according to `self.output_format`.
            None: If there are no differences.
        """
        try:
            # Input validation
            self._validate_file_exists(self.current_config_path)
            self._validate_file_exists(self.baseline_config_path)

            # Lint current config
            if self.current_config_path.lower().endswith(('.yaml', '.yml')):
                if not self._run_linter(self.current_config_path, "yaml"):
                    raise ValueError(f"YAML linting failed for {self.current_config_path}")
            elif self.current_config_path.lower().endswith('.json'):
                if not self._run_linter(self.current_config_path, "json"):
                    raise ValueError(f"JSON linting failed for {self.current_config_path}")

            # Lint baseline config
            if self.baseline_config_path.lower().endswith(('.yaml', '.yml')):
                if not self._run_linter(self.baseline_config_path, "yaml"):
                    raise ValueError(f"YAML linting failed for {self.baseline_config_path}")
            elif self.baseline_config_path.lower().endswith('.json'):
                if not self._run_linter(self.baseline_config_path, "json"):
                    raise ValueError(f"JSON linting failed for {self.baseline_config_path}")

            current_config = self._load_config(self.current_config_path)
            baseline_config = self._load_config(self.baseline_config_path)

            if self.output_format == "diff":
                # Create temporary files for generating diff
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as current_temp, tempfile.NamedTemporaryFile(mode='w', delete=False) as baseline_temp:
                    json.dump(current_config, current_temp, indent=4, sort_keys=True)
                    json.dump(baseline_config, baseline_temp, indent=4, sort_keys=True)
                    current_temp_path = current_temp.name
                    baseline_temp_path = baseline_temp.name

                try:
                     # Generate diff using difflib
                    with open(current_temp_path, 'r') as current_file, open(baseline_temp_path, 'r') as baseline_file:
                        current_lines = current_file.readlines()
                        baseline_lines = baseline_file.readlines()

                    diff = difflib.unified_diff(baseline_lines, current_lines, fromfile=self.baseline_config_path, tofile=self.current_config_path)
                    diff_string = ''.join(diff)
                finally:
                    # Clean up temporary files
                    os.remove(current_temp_path)
                    os.remove(baseline_temp_path)
                if diff_string:
                    return diff_string
                else:
                    return None  # No differences
            elif self.output_format == "json":
                #  Return the configurations as JSON
                return json.dumps({"current": current_config, "baseline": baseline_config}, indent=4, sort_keys=True)
            else:
                raise ValueError(f"Unsupported output format: {self.output_format}")

        except FileNotFoundError as e:
            self.logger.error(f"File not found: {e}")
            print(f"Error: {e}", file=sys.stderr) # Print to stderr for user feedback
            return None
        except ValueError as e:
            self.logger.error(f"ValueError: {e}")
            print(f"Error: {e}", file=sys.stderr)
            return None
        except Exception as e:
            self.logger.exception("An unexpected error occurred.")
            print(f"An unexpected error occurred: {e}", file=sys.stderr)
            return None


def setup_argparse():
    """
    Sets up the argument parser for the command line interface.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """
    parser = argparse.ArgumentParser(description="Compares a configuration file against a known good baseline.")
    parser.add_argument("current_config", help="Path to the current configuration file.")
    parser.add_argument("baseline_config", help="Path to the baseline configuration file.")
    parser.add_argument("-o", "--output_format", default="diff", choices=["diff", "json"],
                        help="The format of the output (diff or json). Defaults to diff.")
    return parser


def main():
    """
    Main function to execute the configuration comparison.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    comparator = ConfigBaselineComparator(args.current_config, args.baseline_config, args.output_format)

    try:
        comparison_result = comparator.compare_configs()

        if comparison_result:
            print(comparison_result)
        else:
            print("No differences found between the configurations.")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

# Usage examples:
#
# 1.  Compare current_config.yaml against baseline.yaml and display the diff:
#     python main.py current_config.yaml baseline.yaml
#
# 2.  Compare current_config.json against baseline.json and output the full JSON configurations:
#     python main.py current_config.json baseline.json -o json
#
# 3.  If yamllint or jsonlint is not installed or a YAML/JSON file contains errors, the script provides informative messages.
#
# Security Considerations:
# - Ensure file paths provided as arguments are validated to prevent path traversal vulnerabilities.
# - Avoid using `eval()` or `exec()` to prevent code injection.
# - Sanitize user inputs.
# - Minimize the privileges of the user running the script.
# - Regularly update dependencies to patch security vulnerabilities.