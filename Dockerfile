FROM python:slim-bullseye

ENV PYTHONUNBUFFERED True

WORKDIR /app

COPY . ./
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "main.py"]