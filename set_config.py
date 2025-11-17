import toml
import sys
import os

def set_config_value(file_path, section, key, value):
    """
    Sets a value in a TOML configuration file.
    Creates the file and section if they don't exist.
    """
    if not os.path.exists(file_path):
        # Create an empty file with a default comment if it doesn't exist
        with open(file_path, 'w') as f:
            f.write("# Hud35 Configuration File\n")

    try:
        # Read existing config
        config = toml.load(file_path)
    except toml.TomlDecodeError:
        # Handle empty or invalid TOML file
        config = {}

    # Navigate or create nested sections
    parts = section.split('.')
    current_level = config
    for part in parts:
        current_level = current_level.setdefault(part, {})

    # Set the value, attempting to convert to int if possible
    try:
        current_level[key] = int(value)
    except (ValueError, TypeError):
        current_level[key] = value

    # Write the updated config back to the file
    with open(file_path, 'w') as f:
        toml.dump(config, f)

if __name__ == "__main__":
    if len(sys.argv) == 5:
        set_config_value(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])