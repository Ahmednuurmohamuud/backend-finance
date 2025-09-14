import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "finance_project.settings")

# Create Celery app
app = Celery("finance_project")

# Load settings from Django settings, using CELERY_ namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()
# celery.py
# app.autodiscover_tasks(["core.utils.notifications"])

