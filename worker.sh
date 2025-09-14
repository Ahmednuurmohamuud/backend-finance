#!/bin/bash
set -e

echo "Starting Celery worker..."
celery -A finance_project beat --loglevel=info
celery -A finance_project worker --loglevel=info --pool=solo

