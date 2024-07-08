# ISMS Project

This is the documentation for the ISMS project, built upon four smaller projects:
- `mkdocs_site`
- `md_to_yml.py`
- `api_endpoint`
- `yaml_docx_filler`

## Projects

### mkdocs_site

This project is built upon a static site generator called `mkdocs`. It is used to generate the documentation for the ISMS project using markdown files, a file format that is easy to read and write. `mkdocs` is extended with the `mkdocs-material` theme, which provides a clean and modern look for the documentation.

### md_to_yml.py

This is a Python script that converts markdown files to yaml files. It is used to convert the markdown files in the `mkdocs_site` project to yaml files, which are used by the `api_endpoint` project to provide RESTful API responses, as well as for the `yaml_docx_filler` project to fill in docx templates. This is supported by `conversion_list.json`, which acts as a configuration file for the script.

### api_endpoint

This project is built upon a RESTful API framework called `FastAPI`. It is used to provide an endpoint for the ISMS project to interact with the `yaml_docx_filler` project. The endpoint allows programmatic access to the data in the yaml files, providing a way to retrieve the data and potentially being extended towards updating or deleting data.

### yaml_docx_filler

This project is built upon a Python library called `docxtpl`. It is used to fill in docx templates with data from yaml files. It is used to provide a service for the ISMS project to fill in docx templates with data from yaml files, standardizing the process for generating documents.

## Requirements

Note: The following requirements are for all four projects here. Based on the my knowledge on the requirements, Python 3.10 or higher is required. This project was tested on Python 3.12 on a Windows 11 machine.

- Python 3.10 or higher

## Installation

```bash
pip install -r requirements.txt
```

## File and Folder Structure

```plaintext
.
├───.foam
│   └───templates
|       └───doc-template.md
├───api_endpoint
│   ├───routes
|   |   └───user_document.py
|   |   └───user_root.py
│   └───endpoint.py
├───common
│   ├───__init__.py
│   └───documentHandler.py
├───docx
│   ├───filled
|   |   └───filled_example.docx
│   └───templates
|       └───template_example.docx
├───md
│   ├───example.md
│   └───index.md
├───mkdocs_site
│   └───mkdocs.yml
├───temp_yml_issues
├───yaml_docx_filler
│   └───filler.py
├───yml
│   └───example.py
├───.gitignore
├───conversion_list.json
├───md_to_yml.py
├───README.md
└───requirements.txt
```

## Usage

At the current time, this project is not yet fully integrated to run as a whole. However, the individual projects can be run separately.

### mkdocs_site

```bash
mkdocs serve -f mkdocs_site/mkdocs.yml
```

### md_to_yml.py

```bash
python md_to_yml.py
```

### api_endpoint

```bash
fastapi run api_endpoint/endpoint.py
```

### yaml_docx_filler

```bash
python yaml_docx_filler/filler.py
```

## Future Improvements

- Complete TODO in all projects
- Document the code in all projects
- Integrate all projects to run as a whole