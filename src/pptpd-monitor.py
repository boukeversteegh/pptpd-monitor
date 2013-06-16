#!/usr/bin/python

import re
from datetime import datetime
sessions = {}

# Some regular expressions that match log entries
# pptpd		pppd[<PID>]
# ipup		<TIMESTAMP> <HOSTNAME> pppd[PID]: ... ip-up <INTERFACE> <USERNAME> <IP4>
# close		Sent <TX> bytes, received <RX> bytes
# ppp_remoteip4	remote IP address <IP4>
# ppp_localip4	local IP address <IP4>
r_pptpd		= re.compile(r"pppd\[(\d+)\]")
r_ipup		= re.compile(r"(.+?) [a-zA-Z0-9\-\.]+ pppd\[\d+\]: pptpd-logwtmp.so ip-up ([a-z0-9]+) ([a-z]+) (\d+\.\d+\.\d+\.\d+)")
r_close		= re.compile(r"Sent (\d+) bytes, received (\d+) bytes")
r_ppp_remoteip4	= re.compile(r"remote IP address (\d+\.\d+\.\d+\.\d+)")
r_ppp_localip4	= re.compile(r"local IP address (\d+\.\d+\.\d+\.\d+)")

logfile = "/var/log/messages"    # pptpd will log messages in here if debug is enabled (/etc/ppp/pptpd-options)
fmt_timestamp = "%b %d %H:%M:%S" # Timestamp format as it appears in the logfile.
now = datetime.now().replace(microsecond=0) # Current time, don't need microsecond accuracy.

import glob, gzip

# Gather all session data from log
for logfile in sorted(glob.glob(logfile + "*"), reverse = True):
  if ".gz" in logfile:
    logfile_data = gzip.open(logfile, "r")
  else:
    logfile_data = open(logfile, "r")
  for line in logfile_data:
    line = line.strip()
    match =  r_pptpd.search(line)
    if match:
      userid = match.group(1)

      sessions.setdefault(userid, {
        "interface":	None,
        "username":	None,
        "ip4":		None,
        "ppp_remoteip4":	None,
        "ppp_localip4":	None,
        "total":		0,
        "rx":		0,
        "tx":		0,
        "status":		None,
        "timestamp_open":	None,
      })
      session = sessions[userid]

      # Read remoteip4 from line and store in session
      match = r_ppp_remoteip4.search(line)
      if match:
        session['ppp_remoteip4'] = match.group(1)
    
      # PPTP session started
      m_ipup  = r_ipup.search(line)
      if m_ipup:
        timestamp = m_ipup.group(1)
        interface	= m_ipup.group(2)
        username	= m_ipup.group(3)
        ip4	= m_ipup.group(4)
        session['status']         = 'open'
        session['timestamp_open']	= datetime.strptime(timestamp, fmt_timestamp).replace(year=datetime.now().year)
        session['interface']	= interface
        session['username']	= username
        session['ip4']		= ip4
    
      # PPTP session closed
      m_close = r_close.search(line)
      if m_close:
        tx = int(m_close.group(1))
        rx = int(m_close.group(2))
        session['status'] = 'closed'
        session['tx']     += tx
        session['rx']     += rx
        session['total']  += tx + rx

import os

# Gets TX-RX for a network interface, for example ppp0
# This is used to get statistics on active sessions
def getInterfaceTotals(interface):
  result = os.popen("ifconfig " + interface, "r")
  r_ipconfig = re.compile(r"RX bytes:(\d+) .+  TX bytes:(\d+)")
  for line in result:
    m_ipconfig = r_ipconfig.search(line)
    if m_ipconfig:
      return (int(m_ipconfig.group(2)), int(m_ipconfig.group(1)))
    
# Gather statistics per user
users = {}
for sessionid, session in sessions.iteritems():
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
  
  # Current Session Open
  if session['status'] == 'open':
    user['session']       = session
    user['interface']     = session['interface']
    user['ip4']           = session['ip4']
    user['ppp_remoteip4'] = session['ppp_remoteip4']
    
    ctx, crx = getInterfaceTotals(session['interface'])
    user['crx'] = crx
    user['ctx'] = ctx
    user['timestamp_open'] = session['timestamp_open']
  
  # Old Session (Put IP addresses in parens)
  elif user['ppp_remoteip4'] is None:
    user['ppp_remoteip4'] = '(' + str(session['ppp_remoteip4']) + ')'
    user['ip4']           = '(' + str(session['ip4']) + ')'
  
  # Totals
  user['lastseen'] =  session['timestamp_open'] # Will be overwritten by each session until the last.
  user['tx']       += session['tx']
  user['rx']       += session['rx']
  user['sessions'] += 1
  user['total']    += session['tx'] + session['rx']
  
  if session['status'] == "open":
    user['sessions_open'] += 1

# Convert bytes to human readable format
def sizeof_fmt(num):
    for x in ['b','KB','MB','GB','TB','PB','EB','ZB']:
        if num < 1024.0:
            return "%3.1f%s" % (num, x)
        num /= 1024.0
    return "%3.1f%s" % (num, 'YB')


print "PPTPD Client Statistics"
print ""
print "Username".ljust(18),
print "#".rjust(6),
print "TX".rjust(8),
print "RX".rjust(8),
print "Remote IP".rjust(18),
print "Local IP".rjust(18),
print "Int".rjust(5),
print "CTX".rjust(8),
print "CRX".rjust(8),
print "Duration/Last seen".rjust(20),
print ""
for username in users:
  user = users[username]
  if user['sessions_open']:
    print "* ",
  else:
    print "  ",
  print str(username).ljust(15),
  print (str(user['sessions_open']) + "/" + str(user['sessions'])).rjust(6),
  print sizeof_fmt(user['rx']).rjust(8),
  print sizeof_fmt(user['tx']).rjust(8),
  print str(user['ip4']).rjust(18),
  print str(user['ppp_remoteip4']).rjust(18),
  print str(user['interface']).rjust(5),
  print sizeof_fmt(user['ctx']).rjust(8),
  print sizeof_fmt(user['crx']).rjust(8),
  try:
    print str(now - user['timestamp_open']).rjust(20),
  except:
    print str(user['lastseen']).rjust(20),
  print ""
