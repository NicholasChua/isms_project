# Use Python 3.12 image
FROM python:3.12-slim

# Preconfigure frontend to avoid the interactive prompt
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY conversion_list.json .
COPY md_to_yml.py .
COPY yaml_docx_filler.py .
COPY endpoint.py .
COPY mkdocs.yml .
COPY common/ common/
COPY docs/ docs/
COPY routes/ routes/
COPY templates/ templates/

# Make empty directory for generated yml and docx files
RUN mkdir -p /app/yml
RUN mkdir -p /app/docx_docs

# Expose port 8000 for MkDocs and 8080 for FastAPI
EXPOSE 8000 8080

# Run markdown to yaml conversion
RUN python md_to_yml.py

# Run yaml docx filler
RUN python yaml_docx_filler.py

# Start MkDocs server in background and FastAPI server in foreground
CMD mkdocs serve -a 0.0.0.0:8000 & uvicorn endpoint:app --host 0.0.0.0 --port 8080
