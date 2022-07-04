import os
import re
import json
import secrets
from datetime import datetime, timedelta

from flask import Flask, render_template, request, session, redirect, send_from_directory

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

    def __init__(self, time, fuel_price, co2_price):
        self.time = time
        self.fuel_price = fuel_price
        self.co2_price = co2_price
        self.fuel_low = fuel_price < 600
        self.co2_low = co2_price < 130


def get_fuel_stats():
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


def compute_fuel_stats(fuel_stats_json, timezone_offset, timezone, date):
    previous_day = (datetime.strptime(date, DATE_FORMAT) + timedelta(days=-1)).strftime(DATE_FORMAT)
    next_day = (datetime.strptime(date, DATE_FORMAT) + timedelta(days=1)).strftime(DATE_FORMAT)
    dates = fuel_stats_json.keys()
    if timezone_offset == 0 and date in dates:
        return [FuelStats(time, stat['fuel_price'], stat['co2_price']) for time, stat in fuel_stats_json[date].items()]

    fuel_stats = []
    if date in dates:
        for time, stat in fuel_stats_json[date].items():
            _datetime = datetime.strptime(' '.join([date, time]), ' '.join([DATE_FORMAT, TIME_FORMAT]))
            if timezone_offset < 0:
                _adjusted_datetime = _datetime - timedelta(minutes=timezone_offset)
            else:
                _adjusted_datetime = _datetime + timedelta(minutes=timezone_offset)
            _date = _adjusted_datetime.strftime(DATE_FORMAT)
            if _date != date:
                continue
            _time = _adjusted_datetime.strftime(TIME_FORMAT) + timezone
            fuel_stats.append(FuelStats(_time, stat['fuel_price'], stat['co2_price']))

    if timezone_offset < 0 and previous_day in dates:
        for time, stat in fuel_stats_json[previous_day].items():
            _datetime = datetime.strptime(' '.join([previous_day, time]), ' '.join([DATE_FORMAT, TIME_FORMAT]))
            _adjusted_datetime = _datetime - timedelta(minutes=timezone_offset)
            _date = _adjusted_datetime.strftime(DATE_FORMAT)
            if _date != date:
                continue
            _time = _adjusted_datetime.strftime(TIME_FORMAT) + timezone
            fuel_stats.append(FuelStats(_time, stat['fuel_price'], stat['co2_price']))
    
    if timezone_offset > 0 and next_day in dates:
        for time, stat in fuel_stats_json[next_day].items():
            _datetime = datetime.strptime(' '.join([next_day, time]), ' '.join([DATE_FORMAT, TIME_FORMAT]))
            _adjusted_datetime = _datetime + timedelta(minutes=timezone_offset)
            _date = _adjusted_datetime.strftime(DATE_FORMAT)
            if _date != date:
                continue
            _time = _adjusted_datetime.strftime(TIME_FORMAT) + timezone
            fuel_stats.append(FuelStats(_time, stat['fuel_price'], stat['co2_price']))

    if len(fuel_stats) == 0:
        return None
    
    return fuel_stats


@app.route("/")
def get_status():
    if 'time_zone_offset' not in session:
        session['referrer'] = request.url
        return redirect('/get_tz')
    session.pop("referrer", None)
    fuel_stats_json = get_fuel_stats()
    if fuel_stats_json is None:
        return render_error_template(message='Fuel stats file not found. <br> Please contact me at <a href="mailto:me@aingaran.dev')
    fuel_stats = compute_fuel_stats(fuel_stats_json, session['time_zone_offset'], session['time_zone'], session.get('date', datetime.now().strftime(DATE_FORMAT)))
    if fuel_stats is not None: 
        return render_template('table.html', title='Fuel Statistics', fuel_stats=fuel_stats)
    return render_error_template(message=f'Unable to find fuel stats for today. <br> You can check stats based on date by using the url endpoint <em>"{request.url}yyyy-mm-dd"</em> <br> If you need assistance, please contact me at <a href="mailto:me@aingaran.dev">me@aingaran.dev</a>')


@app.route("/<date>")
def get_status_date(date):
    if 'time_zone_offset' not in session:
        session['referrer'] = request.url
        return redirect('/get_tz')
    session.pop("referrer", None)
    if not re.match(r'\d{4}-\d{2}-\d{2}', date):
        return render_error_template(message=f'Date supplied "{date}" is not of the format yyyy-mm-dd. Please check the date again. <br> if you still need assistance, please contact me at <a href="mailto:me@aingaran.dev')
    fuel_stats_json = get_fuel_stats()
    if fuel_stats_json is None:
        return render_error_template(message='Fuel stats file not found. <br> please contact me at <a href="mailto:me@aingaran.dev')
    fuel_stats = compute_fuel_stats(fuel_stats_json, session['time_zone_offset'], session['time_zone'], date)
    if fuel_stats is not None:
        return render_template('table.html', title='Fuel Statistics', fuel_stats=fuel_stats)
    return render_error_template(message=f'Unable to find fuel stats for the day {date}. <br> You can check stats based on date by using the url endpoint <em>"{request.url}/yyyy-mm-dd"</em> <br> If you need assistance, please contact me at <a href="mailto:me@aingaran.dev">me@aingaran.dev</a>')
    

@app.route("/get_tz")
def get_time_zone():
    LOGGER.debug('getting time zone')
    return render_template('get_tz.html', title='Get Time Zone')


@app.route("/set_tz/<date>/<tz_offset>/<tz>")
def set_time_zone(date, tz_offset, tz):
    LOGGER.debug(f'Setting time zone to {tz} with offset {tz_offset} from UTC and date is {date}')
    session['time_zone_offset'] = int(tz_offset)
    session['time_zone'] = tz
    session['date'] = date
    if 'referrer' in session:
        return redirect(session['referrer'])
    return redirect('/')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


if __name__ == "__main__":
    app.secret_key = secrets.token_hex()

    from waitress import serve

    serve(app, host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
