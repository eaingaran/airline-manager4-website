FROM python:slim-bullseye

ENV PYTHONUNBUFFERED True

WORKDIR /app

COPY . ./
RUN pip install --no-cache-dir -r requirements.txt

CMD exec gunicorn --bind :$PORT --workers 1 --threads 2 --timeout 0 main:app