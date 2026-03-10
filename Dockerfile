FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create .streamlit directory and config
RUN mkdir -p .streamlit

# Expose port (Railway.app requires this)
EXPOSE 8501

# Run the app
CMD ["streamlit", "run", "bom_automation/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
