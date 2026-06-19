FROM python:3.12-slim

WORKDIR /app

# Install system dependencies needed for parsing
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    ffmpeg \
    inotify-tools \
    && rm -rf /var/lib/apt/lists/*

# Install markitdown
RUN pip install --no-cache-dir "markitdown[all]"
RUN pip install sentence-transformers scikit-learn

# Create working dirs
RUN mkdir -p /input /output

CMD ["bash"]
