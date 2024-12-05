#!/usr/bin/env python3

import json
import os
from docxtpl import DocxTemplate
from common.helper_functions import (
    add_argparser_arguments,
    DocumentType,
    read_yaml_file,
    slugify,
    unescape_newlines,
    process_tables,
)

# Document Filler Classes


class DocumentFillerWithoutProcedure:
    """Base class to fill a Word document template with the extracted information from a YAML file.

    This is the assumed structure of the document template:
        - Document Header and Footer Items
            - Header
                - Document Type
                - Document Number
                - Document Revision Number
                - Document Title
        - Document Control Items
            - Revision History
            - Document Review and Approval
        - Document Body Items
            - Purpose           (1.0)
            - Scope             (2.0)
            - Responsibility    (3.0)
            - Definition        (4.0)
            - Procedure         (5.0) (filled in by extended functions)
            - Reference         (6.0)
            - Attachment        (7.0)
    """

    @staticmethod
    def fill_common_items(yaml_content: DocumentType) -> dict:
        """Base function to read YAML data and return common items in a document template as a context dictionary.

        Extended functions will add on to the context dictionary and fill the document template.

        Inputs:
            yaml_content: The extracted information from the YAML file from read_yaml_file()

        Returns:
            context: The context dictionary with the common items filled in
        """
        context = {
            # Document Header and Footer Items
            "document_type": yaml_content["document_type"],
            "document_no": yaml_content["document_no"],
            "document_rev": str(yaml_content["document_rev"]),
            "title": yaml_content["title"],
            # Document Control Items
            "revision_history": yaml_content["revision_history"],
            "reviewed_approved": yaml_content["document_review_and_approval"],
            # Document Body Items
            "purpose": yaml_content["purpose"],
            "scope": yaml_content["scope"],
            "responsibility": yaml_content["responsibility"],
            "definition": yaml_content["definition"],
            # Procedure (5.0) goes here, filled in by extended functions
            "reference": yaml_content["reference"],
            "attachment": yaml_content["attachment"],
        }

        return context


class DocumentFiller(DocumentFillerWithoutProcedure):
    """Extended class to fill a Word document template with the extracted information from a YAML file. This class extends the DocumentFiller class to fill in the Procedure section of the document template, assuming no customization is needed.

    As different documents tend to differ in the structure of the Procedure section, this class should be extended and customized as needed. This can act as a base function assuming no customization is needed. This is sufficient for the example document.
    """

    @staticmethod
    def fill_common_items(yaml_content: DocumentType) -> dict:
        """Extended function to read YAML data and return common items in a document template as a context dictionary.

        Can be further extended with even more extended functions to add to the context dictionary and fill the document template.

        Inputs:
            yaml_content: The extracted information from the YAML file from read_yaml_file()

        Returns:
            context: The context dictionary with the common items filled in
        """
        # Get base context from parent class
        context = DocumentFillerWithoutProcedure.fill_common_items(yaml_content)

        # Add or modify additional items
        context.update(
            {
                "procedure": yaml_content["procedure"],
            }
        )
        return context


# Redacted extended DocumentFiller classes were here


# Document Generation Function


def generate_document(
    yaml_content: DocumentType,
    output_file: str,
) -> None:
    """Used to fill a Word document template with the extracted information.

    Inputs:
        yaml_content: The extracted information from the YAML file from read_yaml_file()
        output_file: The file path to save the filled Word document

    Returns:
        None
    """
    # Instantiate a template file and context dictionary
    template_file = None
    context = None

    # Use the generic DocumentFiller class for standard documents
    context = DocumentFiller.fill_common_items(yaml_content)
    template_file = os.path.join("templates", "template_general.docx")

    # Open the Word document
    doc = DocxTemplate(template_file)

    # Replace template jinja tags with corresponding extracted information
    doc.render(context)

    # Export the modified Word document
    doc.save(output_file)


def docx_fill_task(config_file: str = "conversion_list.json") -> None:
    """Fill the Word document templates with the extracted information from the YAML files based on the configuration file.

    Args:
        config_file: The file path of the configuration file to use for document generation. Defaults to 'conversion_list.json'.

    Returns:
        None
    """
    # Read conversion configuration from user input JSON, or conversion_list.json if not provided
    with open(config_file, "r", encoding="utf-8") as json_file:
        conversion_config = json.load(json_file)

        # Check if the configuration file has the required keys
        if not all(
            key in conversion_config
            for key in [
                "yml_folder",
                "docx_folder",
                "docx_standard_convert",
            ]
        ):
            raise ValueError(
                "Invalid configuration file. Please check the keys in the JSON file."
            )
        else:
            # Retrieve folders from the configuration
            yml_folder = conversion_config["yml_folder"]
            docx_folder = conversion_config["docx_folder"]

            # Retrieve file lists from the configuration
            standard_files = conversion_config["docx_standard_convert"]

            # Fill documents for standard files
            for file in standard_files:
                # Read the YAML file
                yaml_content = unescape_newlines(
                    read_yaml_file(os.path.join(yml_folder, slugify(file) + ".yml"))
                )

                # Generate the filled document
                generate_document(
                    yaml_content=yaml_content,
                    output_file=os.path.join(docx_folder, file + ".docx"),
                )


def main():
    # Set up argparser with arguments
    args = add_argparser_arguments(config_file=True)

    # Retrieve values from the command line arguments
    input_values_dict = vars(args)

    # Fill the Word document templates with the extracted information from the YAML files based on the configuration file
    docx_fill_task(config_file=input_values_dict["config_file"])


if __name__ == "__main__":
    main()
