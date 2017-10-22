import logging

from app import create_app
from app.database import import_any_model
from config import config

log = logging.getLogger(__name__)

import_any_model('file')
app = create_app(config)