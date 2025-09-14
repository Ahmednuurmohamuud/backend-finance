# finance_project/_init_.py
from .celery import app as celery_app


__all__ = ["celery_app"]
