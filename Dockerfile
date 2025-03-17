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
COPY main.py .
COPY conversion_list.json .
COPY mkdocs.yml .
COPY common/ common/
COPY docs/ docs/
COPY routes/ routes/
COPY templates/ templates/
COPY .env* ./

# Expose port 8000 for MkDocs and 8080 for FastAPI
EXPOSE 8000 8080

# Run main.py
CMD ["python", "main.py"]
