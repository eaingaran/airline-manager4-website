import os
import re
import json
import secrets
from datetime import datetime, timedelta

from flask import Flask, render_template, request, session, redirect

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

DATE_FORMAT = '%Y-%m-%d'
TIME_FORMAT = '%H:%M:%S %Z'

bucket_name = os.environ.get('BUCKET_NAME', 'cloud-run-am4')
fuel_log_file = os.environ.get('FUEL_LOG_FILE', 'fuel_log.json')


class FuelStats():
    time: str
    fuel_price: int
    co2_price: int
    fuel_low: bool
    co2_low: bool

    def __init__(self, date, time, fuel_price, co2_price, timezone_offset, timezone):
        _datetime = datetime.strptime(' '.join([date, time]), ' '.join([DATE_FORMAT, TIME_FORMAT]))
        self.time = (_datetime - timedelta(minutes=timezone_offset)).strftime(TIME_FORMAT) + timezone
        self.fuel_price = fuel_price
        self.co2_price = co2_price
        self.fuel_low = fuel_price < 500
        self.co2_low = co2_price < 120


def get_fuel_stats():
    return json.loads('{"2022-07-02": {"09:30:00 UTC": {"fuel_price": 1360, "co2_price": 134}, "10:00:00 UTC": {"fuel_price": 1540, "co2_price": 176}, "10:30:00 UTC": {"fuel_price": 1150, "co2_price": 104}, "11:00:00 UTC": {"fuel_price": 930, "co2_price": 122}, "11:30:00 UTC": {"fuel_price": 570, "co2_price": 170}, "12:00:00 UTC": {"fuel_price": 2430, "co2_price": 196}}}')
    client = storage.Client()
    bucket = client.get_bucket(bucket_name)
    new_blob = bucket.blob(fuel_log_file)
    try:
        return json.loads(new_blob.download_as_text())
    except NotFound as e:
        LOGGER.exception('Fuel stats file not found in the bucket', e)
        return None


def render_error_template(message):
    return render_template('error.html', title='Error', heading='Ooops!', message=message)


@app.route("/")
def get_status():
    if not all (key in session for key in ['time_zone_offset', 'timezone']):
        session['referrer'] = request.url
        return redirect('/get_tz')
    session.pop("referrer", None)
    fuel_stats_json = get_fuel_stats()
    if fuel_stats_json is None:
        return render_error_template(message='Fuel stats file not found. <br> Please contact me at <a href="mailto:me@aingaran.dev')
    dates = fuel_stats_json.keys()
    date = datetime.now().strftime(DATE_FORMAT)
    if date in dates:
        fuel_stats = [FuelStats(date, time, stat['fuel_price'], stat['co2_price'], session.get('time_zone_offset', 0), session.get('time_zone', 'UTC'))
                      for time, stat in fuel_stats_json[date].items()]
    else:
        return render_error_template(message=f'Unable to find fuel stats for today. <br> You can check stats based on date by using the url endpoint <em>"{request.url}/yyyy-mm-dd"</em> <br> If you need assistance, please contact me at <a href="mailto:me@aingaran.dev">me@aingaran.dev</a>')
    return render_template('table.html', title='Fuel Statistics',
                           fuel_stats=fuel_stats)


@app.route("/<date>")
def get_status_date(date):
    if not all (key in session for key in ['time_zone_offset', 'timezone']):
        session['referrer'] = request.url
        return redirect('/get_tz')
    session.pop("referrer", None)
    if not re.match(r'\d{4}-\d{2}-\d{2}', date):
        return render_error_template(message=f'Date supplied "{date}" is not of the format yyyy-mm-dd. Please check the date again. <br> if you still need assistance, please contact me at <a href="mailto:me@aingaran.dev')
    fuel_stats_json = get_fuel_stats()
    if fuel_stats_json is None:
        return render_error_template(message='Fuel stats file not found. <br> please contact me at <a href="mailto:me@aingaran.dev')
    dates = fuel_stats_json.keys()
    if date in dates:
        fuel_stats = [FuelStats(date, time, stat['fuel_price'], stat['co2_price'], session.get('time_zone_offset', 0), session.get('time_zone', 'UTC'))
                      for time, stat in fuel_stats_json[date].items()]
    else:
        return render_error_template(message=f'Unable to find fuel stats for the day {date}. <br> You can check stats based on date by using the url endpoint <em>"{request.url}/yyyy-mm-dd"</em> <br> If you need assistance, please contact me at <a href="mailto:me@aingaran.dev">me@aingaran.dev</a>')
    return render_template('table.html', title='Fuel Statistics',
                           fuel_stats=fuel_stats)


@app.route("/get_tz")
def get_time_zone():
    LOGGER.info('getting time zone')
    return render_template('get_tz.html', title='Get Time Zone')


@app.route("/set_tz/<tz_offset>/<tz>")
def set_time_zone(tz_offset, tz):
    LOGGER.info(f'Setting time zone to {tz} with offset {tz_offset} from UTC')
    session['time_zone_offset'] = int(tz_offset)
    session['time_zone'] = tz
    if 'referrer' in session:
        return redirect(session['referrer'])
    return redirect('/')


if __name__ == "__main__":

    # https://flask.palletsprojects.com/quickstart/#sessions.
    app.secret_key = secrets.token_hex()

    from waitress import serve

    serve(app, host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
