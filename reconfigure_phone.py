import time
import selenium
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import shutil
import enum

class Mode(enum.Enum):
  PROVISION_DHCP = 0
  PROVISION_STATIC = 2
  TEST = 4
  VLAN = 8
  TRANSFER_CONSULTATIVE = 9
  TRANSFER_BLIND = 10

CONSOLE_WIDTH = shutil.get_terminal_size()[0] if shutil.get_terminal_size()[0] < 80 else 80
EXPLICIT_DELAY = 1.0
MODE = Mode.TRANSFER_BLIND
PHONE_PINS = ['8642', '7178675309']
VLAN_ID = 20
IP_ADDRESSES = [
    # '10.250.10.131',
    '10.250.10.106',
  ]

def get_webdriver_session(type:str='firefox'):
  options = {'firefox': webdriver.FirefoxOptions(), 'chrome': webdriver.ChromeOptions()}.get(type)
  options.binary_location = {'firefox': 'C:\\Program Files\\Mozilla Firefox\\firefox.exe', 'chrome': 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'}.get(type)
  options.accept_insecure_certs = True
  options.page_load_strategy = 'eager'
  if type == 'firefox':
    session = webdriver.Firefox('.', options=options)
  elif type == 'chrome':
    session = webdriver.Chrome('.', options=options)
  session.implicitly_wait(3.0)
  return session

print('')
print('Polycom Phone Reconfiguration Script 3.0'.center(CONSOLE_WIDTH))
print('*' * CONSOLE_WIDTH if MODE == Mode.TEST else '=' * CONSOLE_WIDTH)

print('\nMODE: ' + MODE.name)

print('Starting browser and webdriver session...')
session = get_webdriver_session('firefox')
mouse = webdriver.ActionChains(session)

for ip in IP_ADDRESSES:
  print(ip + '... ', end = '', flush=True)
  
  try:
    print('Logging in... ', end='', flush=True)
    session.get('https://' + ip) # load the web page
    for pin in PHONE_PINS:
      (session.find_element_by_name('password')).send_keys(pin) # put PHONE_PIN in the 'password' field
      (session.find_element_by_name('password')).send_keys(Keys.RETURN) # hit enter
      time.sleep(1)
      try:
        if (session.find_element_by_xpath('//*[text()="You are here: Home"]')):
          break # cancel the loop because we logged in
      except selenium.common.exceptions.NoSuchElementException as e:
        continue # we're probably not logged in, so move to the next password

    if MODE == Mode.TRANSFER_BLIND or MODE == Mode.TRANSFER_CONSULTATIVE:
      print('Configuring transfer behavior ({})...'.format(MODE.name), end='', flush=True)
      # (session.find_element_by_xpath('//*[@id="topMenuItem3"]')).click() # click on 'Preferences'
      # (session.find_element_by_xpath('//*[@id="topMenuItem3"]/ul/li[@src="othersConf.htm"]')).click() # click on 'Additional Preferences'
      # mouse.move_by_offset(1,1).perform() # move the mouse so the menus will go away...
      session.get('https://' + ip + '/othersConf.htm')
      (session.find_element_by_xpath('//*[text()="Default Transfer Type"]')).click() # expand 'Default Transfer Type'
      (Select(session.find_element_by_xpath('//*[@paramname="call.defaultTransferType"]'))).select_by_value(str(MODE.value-8))
    elif MODE == Mode.VLAN:
      print('Configuring VLAN... ', end='', flush=True)
      # (session.find_element_by_xpath('//*[@id="topMenuItem4"]')).click() # click on 'Settings'
      # (session.find_element_by_xpath('//*[@id="topMenuItem4"]/ul/li/a/span[text()="Network"]')).click() # click on 'Settings'
      # (session.find_element_by_xpath('//span[text()="Ethernet"]')).click() # click on 'Ethernet'
      # mouse.move_by_offset(1,1).perform() # move the mouse so the menus will go away...
      session.get('https://' + ip + '/ethernetConf.htm')
      (session.find_element_by_xpath('//span[text()="VLAN Settings"]')).click()
      input_box = session.find_element_by_xpath('//*[@paramname="device.net.vlanid"]')
      input_box.clear()
      input_box.send_keys(VLAN_ID)
    elif MODE == Mode.PROVISION_DHCP or MODE == Mode.PROVISION_STATIC:
      print('Configuring Provisioning... ', end='', flush=True)
      # (session.find_element_by_xpath('//*[@id="topMenuItem4"]')).click() # click on 'Settings'
      # (session.find_element_by_xpath('//*[@id="topMenuItem4"]/ul/li[6]')).click() # click on 'Provisioning Server'
      # mouse.move_by_offset(1,1).perform() # move the mouse so the menus will go away...
      session.get('https://' + ip + '/provConf.htm')
      (session.find_element_by_xpath('//span[text()="DHCP Menu"]')).click()
      (Select(session.find_element_by_xpath('//*[@id="provBootSrvSelectBox"]'))).select_by_value(str(MODE.value)) # select the correct value from the dropdown menu
    if MODE == Mode.TEST:
      print('Access confirmed.')
      continue
    else:
      (session.find_element_by_xpath('//*[@id="buttonContent"]/button/span[text()="Save"]')).click() # click save button
      (session.find_element_by_xpath('//*[@type="button" and text()="Yes"]')).click() # confirm
      print('Saved and reloading.')
      time.sleep(1)
  
  except Exception as e:
    print(e)
    continue

print('\n' + 'Finished.'.center(CONSOLE_WIDTH))
print('*' * CONSOLE_WIDTH if MODE == Mode.TEST else '=' * CONSOLE_WIDTH)
session.quit()
exit()