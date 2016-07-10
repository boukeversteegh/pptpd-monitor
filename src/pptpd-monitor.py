#!/usr/bin/python

import re, subprocess
from datetime import datetime

import glob, gzip, sys, os, time


# Convert bytes to human readable format
def sizeof_fmt(num):
  for x in ['b','KB','MB','GB','TB','PB','EB','ZB']:
    if num < 1024.0:
      return "%3.1f%s" % (num, x)
    num /= 1024.0
  return "%3.1f%s" % (num, 'YB')


# Gets TX-RX for a network interface, for example ppp0
# This is used to get statistics on active sessions
def getInterfaceTotals(interface):
  DEVNULL  = open(os.devnull, 'w')
  command  = "ifconfig " + interface, "r"
  process  = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=DEVNULL, shell=True)
  result   = process.communicate()
  
  r_ipconfig = re.compile(r"RX bytes:(\d+) .+  TX bytes:(\d+)")
  for line in result[0].split('\n'):
    m_ipconfig = r_ipconfig.search(line)
    if m_ipconfig:
      return (int(m_ipconfig.group(2)), int(m_ipconfig.group(1)))
  return (0, 0)

class Monitor:

  # Some regular expressions that match log entries
  # pptpd               pppd[<PID>]
  # ipup                <TIMESTAMP> ... pppd[PID]: ... ip-up <INTERFACE> <USERNAME> <IP4>
  # close               Sent <TX> bytes, received <RX> bytes
  # ppp_remoteip4       remote IP address <IP4>
  # ppp_localip4        local IP address <IP4>
  r_pptpd               = re.compile(r"pppd\[(\d+)\]")
  r_ppp_ipup            = re.compile(r"(.+?) [a-zA-Z0-9\-\.]+ pppd\[\d+\]: pptpd-logwtmp.so ip-up ([a-z0-9]+) ([^\s]+) (\d+\.\d+\.\d+\.\d+)")
  r_ppp_close           = re.compile(r"Sent (\d+) bytes, received (\d+) bytes")
  r_ppp_remoteip4       = re.compile(r"remote IP address (\d+\.\d+\.\d+\.\d+)")
  r_ppp_localip4        = re.compile(r"local IP address (\d+\.\d+\.\d+\.\d+)")
  r_ppp_exit            = re.compile(r"Exit.")
  
  fmt_timestamp	= "%b %d %H:%M:%S" # Timestamp format as it appears in the logfile.

  def __init__(self, logfile, logrotate=True):
    self.logfile   = logfile
    self.logrotate = logrotate
    self.now = datetime.now().replace(microsecond=0) # Current time, don't need microsecond accuracy.
    self.activesessions = {}
    self.lastfile = None

  def monitor(self, interval=0):
    sessionlist  = self.get_sessions()
    userstats    = self.get_userstats(sessionlist)
    fstring      = self.format_userstats(userstats)
    print fstring,

    if interval is 0:
      return

    time.sleep(interval)
    while True:
      self.update_sessions(self.activesessions, sessionlist)
      userstats = self.get_userstats(sessionlist)
      # Clear previous stats
      print (fstring.count('\n') * '\033[1A') + len(fstring.split('\n')[0])*' ' + '\r',
      print self.format_userstats(userstats),
      time.sleep(interval)

  def get_sessions(self):
    activesessions	= self.activesessions
    sessionlist		= []
    
    # Gather all session data from log
    if self.logrotate:
      logfilefilter = self.logfile + "*"
    else:
      logfilefilter = self.logfile

    logfile_data = None
    for logfile in sorted(glob.glob(logfilefilter), reverse = True):
      if logfile_data:
        logfile_data.close()

      print "Reading %s" % logfile,
      sys.stdout.flush()
      print "\r" + " " * (8+len(logfile)) + "\r",
      try:
        if ".gz" in logfile:
          logfile_data = gzip.open(logfile, "r")
        else:
          logfile_data = open(logfile, "r")
        for line in logfile_data:
          line = line.strip()
          self.process_line(line, activesessions, sessionlist)
      except IOError:
        if os.path.exists(logfile):
          print 'Failed to read file ' + logfile + ', insufficient permissions?'
          sys.exit(1) # error, so non-zero return code
        else:
          print 'Failed to read file ' + logfile + ", file doesn't exist?"
          sys.exit(1) # error, so non-zero return code
      self.lastfile = logfile_data
      return sessionlist

  def update_sessions(self, activesessions, sessionlist):
    self.lastfile.seek(self.lastfile.tell())
    for line in self.lastfile:
      line = line.strip()
      self.process_line(line, activesessions, sessionlist)
  
  def process_line(self, line, activesessions, sessionlist):
    match =  self.r_pptpd.search(line)
    if match:
      # Logdata is grouped by PID
      pid = match.group(1)
      newconnection = (pid not in activesessions)
    
      activesessions.setdefault(pid, {
        "interface":      None,
        "username":       None,
        "ip4":            None,
        "ppp_remoteip4":  None,
        "ppp_localip4":   None,
        "total":          0,
        "rx":             0,
        "tx":             0,
        "status":         None,
        "timestamp_open": None,
      })
      session = activesessions[pid]
      
      if newconnection:
        sessionlist.append(session)
    
      # Read remoteip4 from line and store in session
      match = self.r_ppp_remoteip4.search(line)
      if match:
        session['ppp_remoteip4'] = match.group(1)

      # PPTP session started
      m_ipup  = self.r_ppp_ipup.search(line)
      if m_ipup:
        timestamp	= m_ipup.group(1)
        interface	= m_ipup.group(2)
        username	= m_ipup.group(3)
        ip4	= m_ipup.group(4)
        session['status']         = 'open'
        session['timestamp_open']	= datetime.strptime(timestamp, self.fmt_timestamp).replace(year=datetime.now().year)
        session['interface']	= interface
        session['username']		= username
        session['ip4']		= ip4
    
      # PPTP session closed
      m_close = self.r_ppp_close.search(line)
      if m_close:
        tx = int(m_close.group(1))
        rx = int(m_close.group(2))
        session['status'] = 'closed'
        session['tx']     += tx
        session['rx']     += rx
        session['total']  += tx + rx
      
      m_exit = self.r_ppp_exit.search(line)
      if m_exit:
        # After process exits, remove PID from sessions
        # because same PID will be used again
        # (after long uptime, or reboot)
        # and we dont want stats to be merged!
        del activesessions[pid]

   

  def get_userstats(self, sessions):
    # Gather statistics per user
    users = {}
    for session in sessions:
      username = session['username']
      # Get userdata or set defaults
      user = users.setdefault(username, {
        "tx":             0,
        "rx":             0,
        "ctx":            0,
        "crx":            0,
        "total":          0,
        "session":        None,
        "sessions":       0,
        "sessions_open":  0,
        "ppp_remoteip4":  None,
        "ppp_localip4":   None,
        "ip4":            None,
        "interface":      None,
        "timestamp_open": None
      })
      
      user['session']       = session
      
      # Current Session Open
      if session['status'] == 'open':
        user['interface']     = session['interface']
        user['ip4']           = session['ip4']
        user['ppp_remoteip4'] = session['ppp_remoteip4']
        
        ctx, crx = getInterfaceTotals(session['interface'])
        user['crx'] = crx
        user['ctx'] = ctx
        user['timestamp_open'] = session['timestamp_open']
      
      # Totals
      user['lastseen'] =  session['timestamp_open'] # Will be overwritten by each session until the last.
      user['tx']       += session['tx']
      user['rx']       += session['rx']
      user['sessions'] += 1
      user['total']    += session['tx'] + session['rx']
      
      if session['status'] == "open":
        user['sessions_open'] += 1
    
    
    return users 

  def format_userstats(self, users):
    fstring = ""
    fstring += "PPTPD Client Statistics\n"
    fstring += "\n"
    fstring += "Username".ljust(17)
    fstring += "#".rjust(6)
    fstring += "TX".rjust(8)
    fstring += "RX".rjust(8)
    fstring += "Remote IP".rjust(18)
    fstring += "Local IP".rjust(18)
    fstring += "Int".rjust(5)
    fstring += "CTX".rjust(8)
    fstring += "CRX".rjust(8)
    fstring += "Duration/Last seen".rjust(20)
    fstring += "\n"
    for username in sorted(users.keys()):
      user = users[username]

      if user['ppp_remoteip4']:
        ppp_remoteip4 = user['ppp_remoteip4']
        ip4 = user['ip4']
      else:
        ppp_remoteip4 = "(%s)" % user['session']['ppp_remoteip4']
        ip4 = "(%s)" % user['session']['ip4']

      if user['sessions_open']:
        fstring += "* "
      else:
        fstring += "  "

      fstring += str(username).ljust(15)
      fstring += (str(user['sessions_open']) + "/" + str(user['sessions'])).rjust(6)
      fstring += sizeof_fmt(user['rx']).rjust(8)
      fstring += sizeof_fmt(user['tx']).rjust(8)
      
      fstring += str(ip4).rjust(18)
      fstring += str(ppp_remoteip4).rjust(18)
      fstring += str(user['interface']).rjust(5)
      fstring += sizeof_fmt(user['ctx']).rjust(8)
      fstring += sizeof_fmt(user['crx']).rjust(8)

      try:
        fstring += str(now - user['timestamp_open']).rjust(20)
      except:
        fstring += str(user['lastseen']).rjust(20)

      fstring += "\n"
    return fstring

if __name__ == "__main__":
  # pptpd will log messages in here if debug is enabled (/etc/ppp/pptpd-options)
  logfile   = "/var/log/syslog"
  logrotate = False

  if '--help' in sys.argv or '-h' in sys.argv:
    print 'pptpd-monitor.py [OPTIONS]\n', \
          '\n', \
          '  -h,--help      Show help\n', \
          '  --watch        Continuously update\n', \
          '  --log <path>   Use file at path instead of the default\n', \
          '  --rotate       Include logrotated files (*.gz)'
    sys.exit(0)

  if '--log' in sys.argv:
    if not os.path.isfile(sys.argv[sys.argv.index('--log') + 1]):
      print "File doesn't exist or is not a regular file, falling back to default"
    else:
      logfile=sys.argv[sys.argv.index('--log') + 1]

  if '--rotate' in sys.argv:
    logrotate = True
    
  monitor = Monitor(logfile, logrotate)

  if '--watch' in sys.argv:
    monitor.monitor(interval=1)
  else:
    monitor.monitor()
