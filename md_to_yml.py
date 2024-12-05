#!/usr/bin/env python3

import json
import re
import yaml
import os
from common.helper_functions import (
    add_argparser_arguments,
    strip_markdown_links,
    replace_br_tags,
    slugify,
)


def parse_markdown_to_dict(md_content: str) -> dict | None:
    """Helper function that parses markdown content and returns it in a dictionary.
    This function has been heavily customized to parse the specific markdown content typically found in .md documentation files.
    The markdown is assumed to comply with the standards set out in RFC 7763, with an additional YAML front matter section at the beginning.

    Args:
        md_content: The markdown content to parse.

    Returns:
        data | None: The parsed data as a dictionary, or None if an error occurs.
    """
    # Header mapping for the revision history and document_review_and_approval table to shorten the keys in the jinja template
    header_mapping = {
        "Revision No": "rev_no",
        "Description of Changes": "description_of_changes",
        "Document Submission Date (DD-MMM-YYYY)": "sub_date",
        "Actions": "actions",
        "Designation": "designation",
        "Names": "names",
    }

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

        for i, line in enumerate(lines):
            line = replace_br_tags(line)
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
                "document_review_and_approval",
            ]
            if line.startswith("|"):
                if current_section in table_allowed_sections:
                    # Existing code for allowed sections (lines 129 to 161 remain unchanged)
                    if not parsing_table:
                        parsing_table = True
                        table_headers = [
                            header_mapping.get(header.strip(), header.strip())
                            for header in line.strip("|").split("|")
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
                else:
                    # Modified code to handle tables outside allowed sections
                    if not parsing_table:
                        parsing_table = True
                        table_headers = [
                            header.strip() for header in line.strip("|\n").split("|")
                        ]
                        table_rows = []
                        continue
                    else:
                        table_row = [
                            value.strip() for value in line.strip("|\n").split("|")
                        ]
                        if all(header.startswith("--") for header in table_row):
                            continue  # Skip separator row
                        table_rows.append(table_row)
                        if i + 1 >= len(lines) or not lines[i + 1].startswith("|"):
                            # End of table
                            table_data = []
                            for row in table_rows:
                                row_data = {
                                    header: value
                                    for header, value in zip(table_headers, row)
                                }
                                table_data.append(row_data)
                            if last_item:
                                # Associate the table data with the last list item
                                # Ensure the last item is a dictionary
                                if not isinstance(data[current_section][-1], dict):
                                    item = data[current_section].pop()
                                    item = strip_markdown_links(item)
                                    item = replace_br_tags(item)
                                    data[current_section].append({item: []})
                                # Append the table data to the last list item
                                data[current_section][-1][last_item] = table_data
                                last_item = None  # Reset after associating
                            else:
                                # Handle as an additional table
                                table_key = (
                                    f"additional_table{additional_table_counter}"
                                )
                                data[table_key] = table_data
                                additional_table_counter += 1
                            parsing_table = False
                            table_headers = []
                            table_rows = []
            else:
                # Reset parsing_table if a line doesn't start with '|' and we're not in a table
                parsing_table = False

            # Check for multiline list items and accumulate content
            if line.endswith("  "):
                multiline_accumulating = True
                multiline_content += (
                    line[:-2] + "\n"
                )  # Append a newline instead of a space
                continue
            elif multiline_accumulating:
                multiline_content += line.lstrip()
                line = multiline_content
                multiline_accumulating = False
                multiline_content = ""

            # Adjusted list item handling to use 'line' which may now contain accumulated content
            if line.startswith("- ") and current_section:
                item = line[2:].strip()
                item = strip_markdown_links(item)
                item = replace_br_tags(item)
                data[current_section].append(item)
                last_item = item  # Keep track of the last item for associating tables

            # Adjusted sub-item handling
            elif line.startswith("    - ") and current_section:
                if not isinstance(data[current_section][-1], dict):
                    last_item = data[current_section].pop()
                    data[current_section].append({last_item: []})
                item = strip_markdown_links(line[6:].strip())
                item = replace_br_tags(item)
                data[current_section][-1][last_item].append(item)
                last_sub_item = (
                    item  # Keep track of the last sub-item for sub-sub-items
                )

            # Adjusted sub-sub-item handling
            elif line.startswith("        - ") and current_section:
                if not isinstance(data[current_section][-1][last_item][-1], dict):
                    last_sub_item = data[current_section][-1][last_item].pop()
                    data[current_section][-1][last_item].append({last_sub_item: []})
                item = strip_markdown_links(line[10:].strip())
                item = replace_br_tags(item)
                data[current_section][-1][last_item][-1][last_sub_item].append(item)

            # Only reset 'last_item' if the line is not a table or empty
            elif not line.startswith("|") and line.strip() != "":
                last_item = None

        return data
    except TypeError:
        print("Input must be a string.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return


def convert_md_to_yaml(md_path: str, yaml_path: str) -> bool:
    """Function that converts a markdown file to a YAML file. The markdown file is read line by line, parsed to a dictionary, and then written to a YAML file.

    Args:
        md_path: The path to the markdown file to convert.
        yaml_path: The path to the YAML file to write the converted content to.

    Returns:
        bool: True if the conversion was successful. Does not return False as an error will raise an exception.

    Raises:
        FileNotFoundError: If the markdown file is not found.
        TypeError: If the input or output file path is invalid.
        OSError: If an error occurs during file operations.
        Exception: If an error occurs during the conversion process.
    """
    try:
        # Read the markdown file
        with open(md_path, "r", encoding="utf-8") as md_file:
            md_content = md_file.read()

        # Parse the markdown content to a dictionary
        data = parse_markdown_to_dict(md_content)

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


def conversion_task(config_file: str = "conversion_list.json") -> None:
    """Function to convert markdown files to YAML using a configuration file.

    Args:
        config_file: Path to the JSON configuration file. Defaults to 'conversion_list.json'.

    Returns:
        None

    Raises:
        ValueError: If the configuration file is invalid.
    """
    # Read conversion configuration from user input JSON, or conversion_list.json if not provided
    with open(config_file, "r", encoding="utf-8") as json_file:
        conversion_config = json.load(json_file)

    # Check if the configuration file has the required keys
    if not all(
        key in conversion_config
        for key in [
            "markdown_folder",
            "yml_folder",
            "temp_yml_folder",
            "yml_convert_without_issues",
            "yml_convert_with_issues",
        ]
    ):
        raise ValueError(
            "Invalid configuration file. Please check the keys in the JSON file."
        )
    else:
        # Retrieve folders from the configuration
        markdown_folder = conversion_config["markdown_folder"]
        without_issues_folder = conversion_config["yml_folder"]
        with_issues_folder = conversion_config["temp_yml_folder"]

        # Retrieve file lists from the configuration
        without_issues_files = conversion_config["yml_convert_without_issues"]
        with_issues_files = conversion_config["yml_convert_with_issues"]

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

                yaml_path = os.path.join(yaml_folder, slugify(base_name) + ".yml")
                result = convert_md_to_yaml(md_path, yaml_path)
                if result:
                    print(f"Converted {md_path} to {yaml_path} successfully.")
                else:
                    print(f"Failed to convert {md_path} to {yaml_path}")


def main():
    # Set up argparser with arguments
    args = add_argparser_arguments(config_file=True)

    # Retrieve values from the command line arguments
    input_values_dict = vars(args)

    # Perform the conversion task
    conversion_task(config_file=input_values_dict["config_file"])


if __name__ == "__main__":
    main()
