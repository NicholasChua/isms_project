import argparse
import re
import unicodedata
import yaml
from typing import TypedDict, Any


# Class definitions for the YAML content


class HeaderFooterItems(TypedDict):
    """Represents the structure of the header and footer items in a document.

    Fields:
    - document_type (str): The type of the document.
    - document_no (str): The document number.
    - document_rev (str): The revision number of the document.
    - title (str): The title of the document.
    """

    document_type: str
    document_no: str
    document_rev: str
    title: str


class RevisionHistoryItem(TypedDict):
    """Represents the structure of a revision history item in a document.

    Fields:
    - revision (str): The revision number.
    - description (str): The description of the changes made in the revision.
    - sub_date (str): The date of the document submission.
    """

    revision: str
    description: str
    sub_date: str


class ReviewedApprovedItem(TypedDict, total=False):
    """Represents the structure of the Document Review and Approval section in a document.

    Fields:
    - action (str): The action taken by the individual (e.g., Originator, Reviewed and approved by)
    - designation (str): The designation of the individual.
    - name (str): The name of the individual.
    """

    action: str
    designation: str
    name: str


class ProcedureSection(TypedDict, total=False):
    """Represents the structure of the Procedure section (5.0) in a document.
    This is the part of the document that is most likely to vary significantly between documents,
    thus it is left flexible with optional fields, and custom handling may be required.
    Minimally, it can be expected to be a mixed list of lists and dictionaries.

    Fields:
    - title (str): The title of the procedure section.
    - content (dict[str, list[dict[str, list[str]] | str]] | Any): The content of the procedure section.
    """

    title: str
    content: dict[str, list[dict[str, list[str]] | str]] | Any


class DocumentType(TypedDict):
    """Represents the structure of a standard document, including header/footer, document control items and content sections.

    Fields:
    - document_type (str): The type of the document.
    - document_no (str): The document number.
    - document_rev (str): The revision number of the document.
    - title (str): The title of the document.
    - revision_history (list[RevisionHistoryItem]): A list of revision history items.
    - prepared_by (list[PreparedByItem]): A list of individuals who prepared the document.
    - reviewed_approved (list[ReviewedApprovedByItem]): A list of individuals who originated, and reviewed and approved the document.
    - purpose (list[str]): The purpose of the document.
    - scope (list[str]): The scope of the document.
    - responsibility (list[str]): The responsibilities outlined in the document.
    - definition (list[str]): Definitions of terms used in the document.
    - reference (list[str]): References to other documents.
    - attachment (list[str]): Attachments to the document.
    - procedure (list[ProcedureSection]): The procedural content of the document.
    """

    document_type: str
    document_no: str
    document_rev: str
    title: str
    revision_history: list[RevisionHistoryItem]
    reviewed_approved: list[ReviewedApprovedItem]
    purpose: list[str]
    scope: list[str]
    responsibility: list[str]
    definition: list[str]
    reference: list[str]
    attachment: list[str]
    procedure: list[ProcedureSection]


# Utility functions for data transformation and processing


def strip_markdown_links(text: str) -> str:
    """Remove markdown link syntax and return the link text.

    Args:
        text: The text containing markdown link syntax

    Returns:
        str: The link text without markdown syntax
    """
    return re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)


def replace_br_tags(text: str) -> str:
    """Replace HTML br tags and normalize newlines.

    Args:
        text: Input text containing br tags and newlines

    Returns:
        str: Text with normalized line endings
    """
    # Replace <br> tags with \n
    text = re.sub(r"<br>|<br/>", r"\n", text)
    return text


def transform_data(
    data: DocumentType | dict[str, Any] | list[Any]
) -> DocumentType | dict[str, Any] | list[Any]:
    """Helper function that recursively enters an unknown-amount nested dictionary or list and applies transformations to all string elements.
    This function can be flexibly edited to apply other transformations to the data structure as needed.
    In this example, we remove trailing newline characters from all string elements.

    Args:
        data: The input data structure which can be a dictionary, list, string, or any other type.

    Returns:
        data: The transformed data structure with modifications applied to all string elements.
    """
    if isinstance(data, dict):
        return {
            transform_data(key): transform_data(value) for key, value in data.items()
        }
    elif isinstance(data, list):
        return [transform_data(element) for element in data]
    elif isinstance(data, str):
        # Edit the transformation here as needed
        return data.rstrip("\n")
    else:
        print("There are no string elements in the data structure to transform.")
        return data


def read_yaml_file(input_file: str) -> DocumentType | dict | None:
    """Used to read a YAML file and return the content as a dictionary

    Usage: content = read_yaml_file('text.yml')

    Args:
        input_file: The file path of the YAML file to be read

    Returns:
        example_content: The content of the YAML file as a dictionary
    """
    try:
        with open(input_file, "r", encoding="utf-8") as file:
            example_content = yaml.safe_load(file)
    except yaml.YAMLError:
        print(f"Error reading the YAML file {input_file}.")
        return None

    # Transform the data structure to remove trailing newline characters from all string elements
    example_content = transform_data(example_content)

    return example_content


def slugify(text: str) -> str:
    """Helper function to convert text to a slugified version.
    Slugs are text that is safe to use in URLs, filenames, and identifiers.
    Slugs are lowercase, alphanumeric, and replace special characters with underscores.

    Args:
        text: The text to slugify

    Returns:
        str: The slugified text
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


def un_slugify(slug: str) -> str:
    """Convert a slugified string to a more readable format.

    Args:
        slug: The slugified string to convert to a readable format

    Returns:
        str: The converted string with spaces and capitalization
    """
    # Replace underscores with spaces
    slug = slug.replace("_", " ")
    # Capitalize the first letter of each word
    readable = " ".join(word.capitalize() for word in slug.split())
    # Add an underscore after the first two digits
    readable = re.sub(r"^(\d{2}) ", r"\1_", readable)
    return readable


def unescape_newlines(
    input: dict[str, str] | list[str] | str
) -> dict[str, str] | list[str] | str:
    """Helper function to recursively unescape newline characters in a dictionary or list of dictionaries with actual newlines. This only modifies strings in the input data structure.

    Inputs:
        input: The input data structure to unescape newline characters in

    Returns:
        output: The input data structure with escaped newline characters replaced by unescaped newlines
    """
    if isinstance(input, dict):
        return {unescape_newlines(k): unescape_newlines(v) for k, v in input.items()}
    elif isinstance(input, list):
        return [unescape_newlines(elem) for elem in input]
    elif isinstance(input, str):
        return input.replace("\\n", "\n")
    else:
        return input


def add_argparser_arguments(config_file: bool = False) -> argparse.ArgumentParser:
    """Add arguments to the ArgumentParser object for scripts to take in user inputs.
    This function takes in boolean arguments to determine which arguments should be provided.

    Args:
        config_file: If True, add the argument for config file. Defaults to False.

    Returns:
        argparse.ArgumentParser: ArgumentParser object with added arguments.
    """
    # Initialize the ArgumentParser object
    parser = argparse.ArgumentParser()

    # Add arguments to the ArgumentParser object based on the provided booleans
    if config_file:
        parser.add_argument(
            "--config_file",
            type=str,
            default="conversion_list.json",
            help="Path to the JSON configuration file.",
        )

    args = parser.parse_args()
    return args


def transform_dict_keys(data_list: list[dict[str, str]]) -> list[dict[str, str]]:
    """Transform dictionary keys by slugifying them. This is useful for creating context dictionaries for DocxTemplate. This does not modify the values, only the keys.

    Args:
        data_list: A list of dictionaries to transform the keys of

    Returns:
        transformed_list: A list of dictionaries with slugified keys
    """
    transformed_list = []

    for item in data_list:
        # Create new dict with slugified keys but same values
        new_dict = {slugify(key): value for key, value in item.items()}
        transformed_list.append(new_dict)

    return transformed_list


def process_tables(
    list_of_tables: list[dict[str, str]], table_names: list[str]
) -> dict[str, str]:
    """Process multiple tables dynamically based on provided names. This function is used to dynamically process an unspecified number of tables based on their names. It extracts the header and values for each table and adds them into a dictionary that can be used to update the context in a DocxTemplate.

    Args:
        list_of_tables: A list of dictionaries containing table data
        table_names: A list of names for the tables

    Returns:
        context_updates: A dictionary containing the extracted table data with dynamic names
    """
    context_updates = {}

    for i, (table_data, table_name) in enumerate(zip(list_of_tables, table_names)):
        # Extract header and values for each table
        table_header = next(iter(table_data))
        table_values = transform_dict_keys(table_data[table_header])

        # Add to context with dynamic names
        context_updates[f"{table_name}_table_header"] = table_header
        context_updates[f"{table_name}_table"] = table_values

    return context_updates
