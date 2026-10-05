"""
app.py - MoviesHub main Flask application entry point.
"""

import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")

# Register blueprints
from routes.public import public_bp
from routes.admin import admin_bp

app.register_blueprint(public_bp)
app.register_blueprint(admin_bp, url_prefix="/admin")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
