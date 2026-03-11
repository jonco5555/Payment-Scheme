FROM python:3.12-slim

WORKDIR /app

# Copy only the pyproject.toml files for dependency installation
COPY chatbot-app/pyproject.toml ./chatbot-app/
COPY pyproject.toml ./

# Install dependencies from app/pyproject.toml
RUN pip install --no-cache-dir -e ./chatbot-app

# Copy the rest of the project
COPY chatbot-app/ ./chatbot-app/
COPY docs/ ./docs/

# Expose Streamlit's default port
EXPOSE 8501

# Run the Streamlit app
CMD ["streamlit", "run", "chatbot-app/main.py"]
