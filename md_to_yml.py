# md_to_yml.py

"""Module to convert Markdown files to YAML.

This module provides functionality to convert Markdown files, which follow a
standard documentation format, into YAML files. The conversion process is
configurable via a JSON file. The target Markdown files are expected to have
a YAML front matter section at the beginning, followed by sections with
headings and content. The output YAML files are suitable for further processing,
such as conversion to .docx format or for making API calls.

The expected standard documentation format can be found in the '.foam/templates'
folder of the repository.

Functions:
    main(): The main function of the script.
    parse_markdown_file(file_path): Parses a Markdown file and returns a YAML string.
    write_yaml_file(yaml_content, output_path): Writes a YAML string to a file.

Example:
    To convert a Markdown file to YAML, run either of the following commands. You can 
    also specify a custom configuration file if it is in the right format.
    
    ```bash
    python md_to_yml.py
    python md_to_yml.py --config conversion_list.json
    ```

Note:
    This module is the first part of a larger application for documentation processing.
"""

import json
import yaml
import os
import re
import unicodedata
import argparse


def slugify(text: str) -> str:
    """Helper function to convert text to a slugified version.
    Slugs are text that is safe to use in URLs, filenames, and identifiers.
    Slugs are lowercase, alphanumeric, and replace special characters with underscores.

    Examples:
        >>> slugify("Hello, World!")
        'hello_world'
        >>> slugify("hello_world")
        'hello_world'
        >>> slugify(123)
        Traceback (most recent call last):
        TypeError: Input must be a string.

    Args:
        text: The text to slugify

    Returns:
        text: The slugified text
    """
    try:
        # Normalize the unicode data
        text = unicodedata.normalize("NFKD", text)
        # Convert to lowercase
        text = text.lower()
        # Replace spaces and special characters with underscores
        text = re.sub(r"[\s\-]+", "_", text)
        # Remove any non-alphanumeric characters except underscores
        text = re.sub(r"[^\w_]", "", text)
        return text
    except TypeError:
        raise TypeError("Input must be a string.")
    except Exception as e:
        raise Exception(f"An error occurred: {e}")


def parse_markdown_to_dict(md_content: str) -> dict:
    """Helper function that parses markdown content and returns it in a dictionary.
    This function has been heavily customized to parse the specific markdown content typically found in .md documentation files.
    The markdown is assumed to comply with the standards set out in RFC 7763, with an additional YAML front matter section at the beginning.

    Args:
        md_content: The markdown content to parse

    Returns:
        data: A dictionary containing the parsed markdown content
    """
    try:
        # Split the content by lines
        lines = md_content.strip().split("\n")

        # Initialize variables to hold the parsed data
        data = {}
        current_section = None
        parsing_table = False
        table_headers = []
        table_rows = []
        additional_table_counter = 0  # Initialize a counter to handle additional tables outside the normal sections
        multiline_accumulating = False
        multiline_content = ""
        last_item = None
        last_sub_item = None
        last_sub_sub_item = None

        for i, line in enumerate(lines):
            # Skip all empty lines
            if line.strip() == "":
                continue

            # Handle YAML front matter
            if line.strip() == "---":
                if i == 0:  # Starting YAML front matter
                    j = i + 1
                    while lines[j].strip() != "---":
                        key, value = lines[j].strip().split(":", 1)
                        data[key.strip()] = value.strip()
                        j += 1
                    continue  # Move to next part after front matter

            # Check for markdown section headers denoted by 2 to 6 # characters followed by a space. Skip 1 # character for the section level as that is the title
            heading_match = re.match(r"^(#{2,6}) ", line)
            if heading_match:
                num_hashes = len(heading_match.group(1))
                current_section = slugify(line[num_hashes + 1 :].strip())
                data[current_section] = []
                parsing_table = False
                continue

            # Handle table parsing only for specified sections
            table_allowed_sections = [
                "revision_history",
                "prepared_by",
                "reviewed_and_approved_by",
            ]
            if line.startswith("|"):
                if current_section in table_allowed_sections:
                    if not parsing_table:
                        parsing_table = True
                        table_headers = [
                            header.strip() for header in line.strip("|").split("|")
                        ]
                        continue
                    else:
                        table_row = [
                            value.strip() for value in line.strip("|").split("|")
                        ]
                        if all(header.startswith("--") for header in table_row):
                            continue  # Skip separator row
                        table_rows.append(table_row)
                        if i + 1 >= len(lines) or not lines[i + 1].startswith("|"):
                            # End of table
                            if current_section in data:
                                for row in table_rows:
                                    row_data = {
                                        header: value
                                        for header, value in zip(table_headers, row)
                                    }
                                    data[current_section].append(row_data)
                            parsing_table = False
                            table_headers = []
                            table_rows = []
                else:  # Handle tables outside allowed sections
                    if not parsing_table:
                        parsing_table = True
                        table_headers = [
                            header.strip() for header in line.strip("|").split("|")
                        ]
                        continue
                    else:
                        table_row = [
                            value.strip() for value in line.strip("|").split("|")
                        ]
                        if all(header.startswith("--") for header in table_row):
                            continue  # Skip separator row
                        table_rows.append(table_row)
                        if i + 1 >= len(lines) or not lines[i + 1].startswith("|"):
                            # End of table
                            table_key = f"additional_table{additional_table_counter}"
                            data[table_key] = []
                            for row in table_rows:
                                row_data = {
                                    header: value
                                    for header, value in zip(table_headers, row)
                                }
                                data[table_key].append(row_data)
                            additional_table_counter += 1
                            parsing_table = False
                            table_headers = []
                            table_rows = []

            # Check for multiline list items and accumulate content
            if line.endswith("  "):
                multiline_accumulating = True
                multiline_content += line[:-2] + "\n"  # Append a newline instead of a space
                continue
            elif multiline_accumulating:
                multiline_content += line
                line = multiline_content
                multiline_accumulating = False
                multiline_content = ""

            # Adjusted list item handling to use 'line' which may now contain accumulated content
            if line.startswith("- ") and current_section:
                item = line[2:].strip()
                data[current_section].append(item)
                last_item = item  # Keep track of the last item for sub-items

            # Adjusted sub-item handling
            elif line.startswith("    - ") and current_section:
                if not isinstance(data[current_section][-1], dict):
                    last_item = data[current_section].pop()
                    data[current_section].append({last_item: []})
                data[current_section][-1][last_item].append(line[6:].strip())
                last_sub_item = line[6:].strip()  # Keep track of the last sub-item for sub-sub-items

            # Adjusted sub-sub-item handling
            elif line.startswith("        - ") and current_section:
                if not isinstance(data[current_section][-1][last_item][-1], dict):
                    last_sub_item = data[current_section][-1][last_item].pop()
                    data[current_section][-1][last_item].append({last_sub_item: []})
                data[current_section][-1][last_item][-1][last_sub_item].append(line[10:].strip())
                last_sub_sub_item = line[10:].strip()  # Keep track of the last sub-sub-item for sub-sub-sub-items

            # Adjusted sub-sub-sub-item handling
            elif line.startswith("            - ") and current_section:
                if not isinstance(data[current_section][-1][last_item][-1][last_sub_item][-1], dict):
                    last_sub_sub_item = data[current_section][-1][last_item][-1][last_sub_item].pop()
                    data[current_section][-1][last_item][-1][last_sub_item].append({last_sub_sub_item: []})
                data[current_section][-1][last_item][-1][last_sub_item][-1][last_sub_sub_item].append(line[14:].strip())

            # Reset multiline content after processing
            if not multiline_accumulating:
                multiline_content = ""

        return data
    except TypeError:
        print("Input must be a string.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return

def post_process_slugify(data: dict) -> dict:
    """Helper function to post-process the dictionary to slugify first-level keys in specific sections.

    Args:
        data: The dictionary to post-process

    Returns:
        data: The post-processed dictionary
    """
    sections_to_slugify = ['revision_history', 'prepared_by', 'reviewed_and_approved_by', 'procedure']

    for section in sections_to_slugify:
        if section in data:
            # This section contains a list of dictionaries
            for entry in data[section]:
                for key in list(entry.keys()):  # Use list to avoid RuntimeError
                    entry[slugify(key)] = entry.pop(key)

    return data


def convert_md_to_yaml(md_path: str, yaml_path: str) -> bool:
    """Function that converts a markdown file to a YAML file. The markdown file is read line by line, parsed to a dictionary, and then written to a YAML file.

    Examples:
        >>> convert_md_to_yaml(os.path.join("docs", "Example", "example.md"), os.path.join("docs", "Example", "example.yml"))
        True
        >>> convert_md_to_yaml("non_existent.md", "readme.yml")
        Traceback (most recent call last):
        FileNotFoundError: File not found: non_existent.md
        >>> convert_md_to_yaml("readme.md", 123)
        Traceback (most recent call last):
        OSError: Invalid input or output file path.

    Args:
        md_path: The path to the markdown file to convert
        yaml_path: The path to the YAML file to write the converted content to

    Returns:
        bool: True if the conversion was successful, error otherwise
    """
    try:
        # Read the markdown file
        with open(md_path, "r", encoding="utf-8") as md_file:
            md_content = md_file.read()

        # Parse the markdown content to a dictionary
        data = parse_markdown_to_dict(md_content)

        # Post-process the dictionary to slugify first-level keys in specific sections
        data = post_process_slugify(data)

        # Write the dictionary to a YAML file
        with open(yaml_path, "w", encoding="utf-8") as yaml_file:
            yaml.safe_dump(
                data, yaml_file, allow_unicode=True, sort_keys=False, width=float("inf")
            )
        return True
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {md_path}")
    except TypeError:
        raise TypeError(f"Invalid input or output file path.")
    except OSError:
        raise OSError(f"Invalid input or output file path.")
    except Exception as e:
        raise Exception(f"An error occurred: {e}")


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Convert Markdown files to YAML using a configuration file."
    )
    parser.add_argument(
        "--config",
        help="Path to the JSON configuration file.",
        default="conversion_list.json",
    )
    args = parser.parse_args()

    # Read conversion configuration from user input JSON, or conversion_list.json if not provided
    config_file = args.config
    with open(config_file, "r", encoding="utf-8") as json_file:
        conversion_config = json.load(json_file)

    # Check if the configuration file is valid
    if not all(
        key in conversion_config
        for key in [
            "markdown_folder",
            "convert_without_issues_folder",
            "convert_with_issues_folder",
            "convert_without_issues",
            "convert_with_issues",
        ]
    ):
        print("Invalid configuration file. Please check the keys in the JSON file.")
        return
    else:
        # Retrieve folders from the configuration
        markdown_folder = conversion_config["markdown_folder"]
        without_issues_folder = conversion_config["convert_without_issues_folder"]
        with_issues_folder = conversion_config["convert_with_issues_folder"]

        # Retrieve file lists from the configuration
        without_issues_files = conversion_config["convert_without_issues"]
        with_issues_files = conversion_config["convert_with_issues"]

        # Convert markdown files based on the configuration
        for markdown_file in os.listdir(markdown_folder):
            if markdown_file.endswith(".md"):
                base_name = markdown_file.replace(".md", "")
                md_path = os.path.join(markdown_folder, markdown_file)

                # Determine the output folder based on the file's presence in the lists
                if base_name in without_issues_files:
                    yaml_folder = without_issues_folder
                elif base_name in with_issues_files:
                    yaml_folder = with_issues_folder
                else:
                    print(
                        f"Skipping {markdown_file}: Not listed in conversion configuration."
                    )
                    continue  # Skip files not listed in the configuration

                yaml_path = os.path.join(yaml_folder, base_name + ".yml")
                result = convert_md_to_yaml(md_path, yaml_path)
                if result:
                    print(f"Converted {md_path} to {yaml_path} successfully.")
                else:
                    print(f"Failed to convert {md_path} to {yaml_path}")


if __name__ == "__main__":
    main()
