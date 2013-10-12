pptpd-monitor
=============

Tool for monitoring PPTPD (VPN) connections and traffic.

**Enable debug logging on pptpd**

Make sure your PPTPD server has debug logging enabled. Add a line with the text `debug` to `/etc/ppp/pptpd-options`. No need to restart, your next connection will log details to the log.

**Show client statistics**

Simply run the script:

    ./src/pptpd-monitor.py

**Continuously monitor**

    ./src/pptpd-monitor.py --watch

And you'll get output similar to this:

    PPTPD Client Statistics
    
    Username                #       TX       RX        Remote IP         Local IP   Int      CTX      CRX    Duration
       None              0/61  585.4MB   94.8MB           (None)   (192.168.0.10)  None     0.0b     0.0b
       john               0/6  111.8MB   29.9MB    (100.0.0.179)   (192.168.0.11)  None     0.0b     0.0b
       steven             0/2  489.7MB   15.3MB     (200.0.0.19)   (192.168.0.12)  None     0.0b     0.0b
       sally             0/19  166.5MB   38.7MB     (90.0.0.155)   (192.168.0.10)  None     0.0b     0.0b
       jacky              0/1  192.3KB   27.6KB     (160.0.0.54)   (192.168.0.10)  None     0.0b     0.0b
    *  mark              1/25  790.9MB  112.0MB       120.0.0.15     192.168.0.10  ppp0  107.7MB   21.0MB     4:12:51
       joe               0/15  624.0MB   27.2MB     (120.0.0.12)   (192.168.0.11)  None     0.0b     0.0b

- `Username` = username of the client, defined in chap-secrets. Online users are marked with a `*`
- `#` = number of active connections/number of past closed connections
- `TX` = total data sent to the client in the past
- `RX` = total data received from the client in the past
- `Remote IP` = last seen client wan ip-address, shows in parentheses if client is not connected
- `Local IP` = last assigned ip-address to the client
- `Int` = interface created for this client. Try `ifconfig ppp0` to see data for that interface.
- `CTX`, `RTX` = data sent to and received from the client in current connection

If client authentication fails, or if you don't have `debug` enabled,  statistics will be gathered under `None`.

Note: Data retrieved or sent on behalf of the client is not shown in the statistics. Basically, data sent to the client is first retrieved on behalf of the client, so the total bandwidth for one client would be:
> TotalUpload = `TX + RX`  
> TotalDownload = `RX + TX`  
> TotalBandwidth = ` 2 * (TX + RX)`


**New features**
- Continuously monitoring active connections

**Missing features**

*You're welcome to contribute!*
- Option for choosing logfile. `/var/log/syslog` by default.
- Option for choosing interval speed for `--watch`.

**Known issues:**
- ppp-debugging mode logs every single transmitted packet (pptpd issue)
