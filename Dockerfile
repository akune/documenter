# Document Processor
# Based on OCRmyPDF image with additional Python packages

ARG VERSION=dev
FROM jbarlow83/ocrmypdf:latest
LABEL org.opencontainers.image.version="${VERSION}"

# Install additional system packages including python3-venv for creating venv with pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libzbar0 \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create a new venv with pip support, copying site-packages from original venv
RUN python3 -m venv --system-site-packages /app/newvenv && \
    /app/newvenv/bin/pip install --upgrade pip

# Use the new venv
ENV PATH="/app/newvenv/bin:$PATH"
ENV VIRTUAL_ENV="/app/newvenv"

# Copy requirements and install Python packages into venv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/

# Create input, output and temp directories
RUN mkdir -p /input /output /tmp/processing

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV INPUT_DIR=/input
ENV TEMP_DIR=/tmp/processing

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.isdir('/input') else 1)"

# Override entrypoint from base image
ENTRYPOINT []

# Run the application
CMD ["python3", "/app/src/main.py"]
