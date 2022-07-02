import os
import re
import json
from datetime import datetime, timezone

from flask import Flask, render_template, request

from google.cloud import storage
from google.cloud.exceptions import NotFound

import logging
from logging.config import fileConfig


fileConfig('logger.cfg')
LOGGER = logging.getLogger()

if 'LOG_LEVEL' in os.environ:
    log_levels = {'NOTSET': 0, 'DEBUG': 10, 'INFO': 20,
                  'WARN': 30, 'ERROR': 40, 'CRITICAL': 50}
    if os.environ.get('LOG_LEVEL') in log_levels:
        LOGGER.setLevel(log_levels[os.environ.get('LOG_LEVEL')])
    else:
        LOGGER.error(
            f'LOG_LEVEL {os.environ.get("LOG_LEVEL")} is not a valid level. using {LOGGER.level}')
else:
    LOGGER.warning(f'LOG_LEVEL not set. current log level is {LOGGER.level}')


app_name = 'Airline Manager Website'

app = Flask(app_name, template_folder='templates')

bucket_name = os.environ.get('BUCKET_NAME', 'cloud-run-am4')
fuel_log_file = os.environ.get('FUEL_LOG_FILE', 'fuel_log.json')


class FuelStats():
    time: str
    fuel_price: int
    co2_price: int
    fuel_low: bool
    co2_low: bool

    def __init__(self, time, fuel_price, co2_price):
        self.time = time
        self.fuel_price = fuel_price
        self.co2_price = co2_price
        self.fuel_low = fuel_price < 500
        self.co2_low = co2_price < 120


def get_fuel_stats():
    client = storage.Client()
    bucket = client.get_bucket(bucket_name)
    new_blob = bucket.blob(fuel_log_file)
    try:
        return json.loads(new_blob.download_as_text())
    except NotFound as e:
        LOGGER.exception('Fuel stats file not found in the bucket', e)
        return None


@app.route("/")
def get_status():
    time = request.args.get("time")
    LOGGER.info(f'client time is {time}')
    fuel_stats_json = get_fuel_stats()
    if fuel_stats_json is None:
        return render_template('error.html', title='Error', heading='Ooops!', message='Fuel stats file not found. <br> Please contact me at <a href="mailto:me@aingaran.dev')
    dates = fuel_stats_json.keys()
    if datetime.now().strftime('%Y-%m-%d') in dates:
        fuel_stats = [FuelStats(time, stat['fuel_price'], stat['co2_price'])
                      for time, stat in fuel_stats_json[datetime.now().strftime('%Y-%m-%d')].items()]
    else:
        return render_template('error.html', title='Error', heading='Ooops!', message='Unable to find fuel stats for today. <br> You can check stats based on date by using the url endpoint "/yyyy-mm-dd" <br> If you need assistance, please contact me at <a href="mailto:me@aingaran.dev')
    return render_template('basic_table.html', title='Fuel Statistics',
                           fuel_stats=fuel_stats)


@app.route("/<date>")
def get_status_date(date):
    if not re.match(r'\d{4}-\d{2}-\d{2}', date):
        return render_template('error.html', title='Error', heading='Ooops!', message=f'Date supplied "{date}" is not of the format yyyy-mm-dd. Please check the date again. <br> if you still need assistance, please contact me at <a href="mailto:me@aingaran.dev')
    fuel_stats_json = get_fuel_stats()
    if fuel_stats_json is None:
        return render_template('error.html', title='Error', heading='Ooops!', message='Fuel stats file not found. <br> please contact me at <a href="mailto:me@aingaran.dev')
    dates = fuel_stats_json.keys()
    if date in dates:
        fuel_stats = [FuelStats(time, stat['fuel_price'], stat['co2_price'])
                      for time, stat in fuel_stats_json[date].items()]
    else:
        return render_template('error.html', title='Error', heading='Ooops!', message=f'Unable to find fuel stats for the day {date}. <br> You can check stats based on date by using the url endpoint "/yyyy-mm-dd" <br> If you need assistance, please contact me at <a href="mailto:me@aingaran.dev')
    return render_template('basic_table.html', title='Fuel Statistics',
                           fuel_stats=fuel_stats)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
