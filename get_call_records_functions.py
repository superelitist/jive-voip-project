import requests
import datetime
import urllib
import base64

def iso8601_time_string(hours:float=0):
  """return ISO8601-formatted time string for 'days' days ago (0 is now)."""
  """
  Note: hours / 24 is not exactly correct, but close enough for our purposes.
  """
  return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=hours / 24)).strftime('%Y-%m-%dT%H:%M:%SZ')

def acquire_api_tokens(urls: list,auth_user: str, auth_pass: str, client_id: str, client_secret: str, redirect_uri, scopes, state):
  """Acquire an access token from GoTo's OAuth 2.0 without user interaction."""
  """
  The intended method for acquiring an access token using the Authorization Code Grant flow seems to be to direct an interactive browser to a URL and
  have the user enter their credentials. That's dumb, so we'll just POST our username and password directly. I also don't understand the first step in this process,
  which is to direct the user to a URL which supplies a redirect URL--why not just send them to the second URL right away?
  """
  params = {'response_type': 'code', 'client_id': client_id, 'redirect_uri': redirect_uri, 'scope': scopes, 'state': state} # I dislike defining variables that I'm only going 
  auth_url = requests.get(url=urls[0], params=params).url #                                                                   to use on the next line, but people are always 
  data = {'emailAddress':auth_user, 'password':auth_pass, 'submit':'Sign+in', 'rememberMe':'on'} #                            complaining about 'readability'...
  auth_response = requests.post(url=auth_url, data=data)
  auth_code = urllib.parse.parse_qs(urllib.parse.urlparse(auth_response.url)[4]).get('code')[0]
  headers = {'Authorization': 'Basic ' + str(base64.b64encode((client_id + ':' + client_secret).encode("utf-8")), "utf-8"), 'Content-Type': 'application/x-www-form-urlencoded'}
  data = {'grant_type': 'authorization_code', 'redirect_uri': redirect_uri, 'client_id': client_id, 'code': auth_code}
  response = requests.post(url=urls[1], headers=headers, data=data)
  if response.status_code != 200:
    raise Exception('GET failed, HTTP response was: %s', str(response.status_code))
  return response.json()

def get_api_call_reports(token:str, user:str='', start_time:str=iso8601_time_string(1 / 24), end_time:str=iso8601_time_string(0), page:int=0, page_size:int=10000):
  """Access the Jive API and return information about call activity during the requested time frame"""
  """
  If user is ommitted, the response will be a summary of all callers.
  If user is supplied, the response will be a set of calls made or recieved by that user.
  Default time span is the last hour.
  """
  results = requests.get(url='https://api.jive.com/call-reports/v1/reports/user-activity' + ('/' + user if user else ''), # I'm def proud of this
  params={'startTime': start_time, 'endTime': end_time, 'page': page, 'pageSize': page_size},
  headers={'Authorization': 'Bearer ' + token})
  if results.status_code != 200:
    raise Exception('GET failed, HTTP response was: %s', str(results.status_code))
  return results.json()