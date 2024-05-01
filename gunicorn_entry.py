# gunicorn_entry.py
from main import app
from waitress import serve  # Import the Waitress server

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8000)
