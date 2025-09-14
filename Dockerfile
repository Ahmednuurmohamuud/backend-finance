FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN python -m ensurepip --upgrade
RUN python -m pip install --upgrade pip
RUN python -m pip install -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

COPY start.sh /start.sh
RUN chmod +x /start.sh
ENTRYPOINT ["/start.sh"]
