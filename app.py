import os
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import re
import uuid
import threading
import time
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
TEMP_DIR = BASE_DIR / "temp_downloads"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
