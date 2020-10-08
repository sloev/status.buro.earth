from uuid import uuid4
from base64 import urlsafe_b64encode
from dateutil.parser import parse


def create_uuid():
    return urlsafe_b64encode(uuid4().bytes).decode("ascii").strip("=")


class Redirect(Exception):
    def __init__(self, target_path, message=None):
        message = message or f"redirecting to '{target_path}'"
        super().__init__(message)
        self.target_path = target_path


def parse_date(datestring):
    return parse(datestring)
