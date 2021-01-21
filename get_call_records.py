import json
import csv
import logging
import os
import pathlib
import sys
import traceback
import pyodbc
import time
from get_call_records_functions import iso8601_time_string, acquire_api_tokens, get_api_call_reports

HOURS_BACK_TO_START = 256 * float(sys.argv[1])
HOURS_BACK_TO_END = 256 * (float(sys.argv[1]) - 1.0)
# HOURS_BACK_TO_START = float(sys.argv[1])
# HOURS_BACK_TO_END = 0
REST_RATE_LIMIT = 0.25 # seconds to wait between each REST call.
REST_RETRIES = 4 # number of times to retry each REST call.

FILENAME_CREDENTIALS = 'credentials.json'
OAUTH_URLS = ['https://authentication.logmeininc.com/oauth/authorize', 'https://authentication.logmeininc.com/oauth/token']
REDIRECT_URI = 'https://iss-na.com/'
SCOPES = 'cr.v1.read users.v1.lines.read'
STATE = 'NOTAPPLICABLE' # we don't yet have a reason to use this.

SQL_HOSTNAME = 'isch-sql-22.iss.lcl'
SQL_DATABASE = 'jive_call_reporting'

def main():
  timer_begin = time.perf_counter()
  logger.info('='*80)
  logger.info('Starting new run,')
  logger.info('looking for calls from %s to %s, a %i hour span:', iso8601_time_string(HOURS_BACK_TO_START), iso8601_time_string(HOURS_BACK_TO_END), HOURS_BACK_TO_START - HOURS_BACK_TO_END)
  logger.info('getting credentials from file...')
  with open(FILENAME_CREDENTIALS, 'r') as cred_file:
    creds = json.loads(cred_file.read())
  logger.info('getting access token...')
  # I'm leaving this as is because we might want to get different information at some point
  access_token = acquire_api_tokens(OAUTH_URLS, creds['auth_user'], creds['auth_pass'], creds['client_id'], creds['client_secret'], REDIRECT_URI, SCOPES, STATE)['access_token']

  logger.info('getting user ids from call activity summary...')
  callers = []
  for t in range(REST_RETRIES):
    time.sleep(t**2) # starting with 0 (no wait), wait an increasing amount of time before retrying...
    try:
      callers = get_api_call_reports(token=access_token, start_time=iso8601_time_string(HOURS_BACK_TO_START), end_time=iso8601_time_string(HOURS_BACK_TO_END))['items'] # leaving user blank returns a summary of all user activity for the time frame.
      break # if we got to this point, we should have the data!
    except Exception as e:
      logger.exception(e)
      if (t == REST_RETRIES - 1): raise Exception('no user ids could be retrieved from the API, giving up!')
      logger.info('failed to get user ids, waiting %i seconds and trying again...', t**2)

  logger.info('getting call records for %i users, this will take a few minutes...', len(callers))
  call_records = []
  sw_start = -30 # start over time so we always report the first user.
  for index, caller in enumerate(callers):
    logger.debug('getting call records for user %i of %i: %s (%s)', index+1, len(callers), str(caller['userId']), str(caller['userName']))
    if (time.perf_counter() - sw_start > 30):
      logger.info('working... user %i of %i: %s (%s)', index+1, len(callers), str(caller['userId']), str(caller['userName']))
      sw_start = time.perf_counter()
    for t in range(REST_RETRIES):
      time.sleep((t**2) + REST_RATE_LIMIT) # here we additionally wait a small amount of time so as not to exceed rate limits.
      try:
        call_records += get_api_call_reports(token=access_token, user=str(caller['userId']), start_time=iso8601_time_string(HOURS_BACK_TO_START), end_time=iso8601_time_string(HOURS_BACK_TO_END))['items']
        break # if we got to this point, we should have the data!
      except Exception as e:
        logger.exception(e)
        if (t == REST_RETRIES - 1): raise Exception('failed to get call records for %s (%s), giving up!', str(caller['userId']), str(caller['userName']))
        logger.warning('failed to get call records for %s (%s), waiting %i seconds and trying again', str(caller['userId']), str(caller['userName']), t**2)

  # TODO what if there were zero calls?

  call_records_sql, call_recordings_sql = [], []
  for call in call_records: # list of dictionaries -> list of tuples
    call_records_sql.append((call['answerTime'][:26].replace('T', ' ').replace('Z', '') if call['answerTime'] else None, # replace the 'T' with a space, 'Z' with nothing,
                        call['endTime'][:26].replace('T', ' ').replace('Z', '') if call['endTime'] else None,            # and truncate to 26 characters,
                        call['startTime'][:26].replace('T', ' ').replace('Z', '') if call['startTime'] else None,        # because SQLExecute is VERY particular about the format of a datetime
                        call['direction'],
                        int(call['disposition']),
                        int(call['duration']),
                        call['caller']['name'],
                        call['caller']['number'],
                        call['callee']['name'],
                        call['callee']['number'],
                        call['legId'],
                        call['queue']['id'] if call['queue'] else None,
                        call['queue']['name'] if call['queue'] else None))
    if call['recordingIds']:
      for recording_id in call['recordingIds']:
        call_recordings_sql.append((call['legId'], recording_id))
  
  logger.info('writing %i calls and %i recordings to %s on %s...', len(call_records_sql), len(call_recordings_sql), SQL_DATABASE, SQL_HOSTNAME)
  sql_connection = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+SQL_HOSTNAME+';DATABASE='+SQL_DATABASE+';UID='+creds['sql_username']+';PWD='+creds['sql_password'])
  cursor = sql_connection.cursor()
  cursor.fast_executemany = True
  try:
    sql_connection.autocommit = False
    cursor.executemany('INSERT INTO call_records_staging (answer_time, end_time, start_time, direction, disposition, duration, caller_name, caller_number, callee_name, callee_number, leg_id, queue_id, queue_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?);', call_records_sql)
    if call_recordings_sql:
      cursor.executemany('INSERT INTO call_recordings_staging (leg_id, recording_id) VALUES (?,?);', call_recordings_sql)
  except pyodbc.DatabaseError as err:
    sql_connection.rollback()
    raise err
  else:
    sql_connection.commit()
  finally:
    sql_connection.autocommit = True
  cursor.execute('''
  INSERT INTO call_records 
    (answer_time, end_time, start_time, direction, disposition, duration, caller_name, caller_number, callee_name, callee_number, leg_id, queue_id, queue_name)
  SELECT stage.answer_time, stage.end_time, stage.start_time, stage.direction, stage.disposition, stage.duration, stage.caller_name, stage.caller_number, stage.callee_name, stage.callee_number, stage.leg_id, stage.queue_id, stage.queue_name
    FROM call_records_staging stage
  WHERE stage.leg_id NOT IN (SELECT leg_id FROM call_records)
  ''') # copy all non-duplicate records
  c_c = cursor.rowcount
  cursor.execute('DELETE FROM call_records_staging;') # clear the staging table
  cursor.execute('''
  INSERT INTO call_recordings
    (leg_id, recording_id)
  SELECT stage.leg_id, stage.recording_id
    FROM call_recordings_staging stage
  WHERE stage.leg_id NOT IN (SELECT leg_id FROM call_recordings)
  ''') # copy all non-duplicate records
  r_c = cursor.rowcount
  cursor.execute('DELETE FROM call_recordings_staging;') # clear the staging table
  logger.info('successfully committed %i (%i duplicate) calls and %i (%i duplicate) recordings,', c_c, (len(call_records_sql) - c_c), r_c, (len(call_recordings_sql) - r_c))
  timer_end = time.perf_counter()
  if ((timer_end - timer_begin) > 60):
    fin = 'finished in {} minutes and {} seconds.'.format((timer_end - timer_begin) // 60, int(timer_end - timer_begin) % 60)
  else:
    fin = 'finished in {} seconds.'.format(int(timer_end - timer_begin))
  logger.info(fin)
  logger.info('='*80)
  exit()

if __name__ == "__main__":
  logging.basicConfig(filename=pathlib.Path(__file__).stem + '.log', format='%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s', level=logging.INFO)
  logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
  logger = logging.getLogger(__name__)
  try: # I don't really have time to bug-check this, so we'll do this hilariously simple trick to log any exceptions.
    assert (HOURS_BACK_TO_START > HOURS_BACK_TO_END), 'HOURS_BACK_TO_START must be greater than HOURS_BACK_TO_END!' # something something parameters
    assert (HOURS_BACK_TO_END >= 0), 'HOURS_BACK_TO_END must not be in the future!'
    main()
  except Exception as e:
    logger.exception(e)
    raise