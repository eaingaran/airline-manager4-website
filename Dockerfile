FROM python:slim-bullseye

ENV PYTHONUNBUFFERED True

WORKDIR /app

COPY . ./
RUN pip install --no-cache-dir -r requirements.txt

CMD exec gunicorn --preload --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 0 main:app