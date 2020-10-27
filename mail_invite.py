#!/usr/bin/env python3

# Utility for sending email invitations from the command line
usage='''mail_invite.py [-v] email_address [email_address ...]

where -v enables verbose log messages (level = DEBUG)
'''

import sys, signal

import util
import db
import datetime
import settings
import login
import logging
from quemail import QueMail

log = logging.getLogger("QueMail")
log.setLevel(logging.INFO)

if not getattr(settings, 'WEBHOST', None):
    settings.WEBHOST = 'seattlemahjong.club'

def email(email_address):
    with db.getCur() as cur:
        code = util.randString(32)
        cur.execute(
            "INSERT INTO VerifyLinks (Id, Email, Expires) VALUES (?, ?, ?)",
            (code, email_address, 
             (datetime.date.today() + datetime.timedelta(days=7)).isoformat()))

        util.sendEmail(email_address,
                       "Your {0} Account".format(settings.CLUBNAME),
                       login.format_invite(
                           settings.CLUBNAME, settings.WEBHOST, code))

qm = None

def sigint_handler(signum, frame):
    qm.end()

def init():
    qm = QueMail.get_instance()
    qm.init(settings.EMAILSERVER, settings.EMAILUSER, 
            settings.EMAILPASSWORD, settings.EMAILPORT,
            settings.EMAILUSETLS)
    qm.start()
    return qm

if __name__ == '__main__':
    if '-v' in sys.argv[1:]:
        print('Using verbose logging')
        log.setLevel(logging.DEBUG)
        pos = sys.argv.index('-v')
        sys.argv[pos:pos+1] = []
        
    valid_emails = [arg for arg in sys.argv[1:] if '@' in arg and '.' in arg]
    if len(valid_emails) < len(sys.argv[1:]):
        for arg in [a for a in sys.argv[1:] if not ('@' in a and '.' in a)]:
            print('Skipped {} because it is not a valid email address'.format(
                repr(arg)))
        
    if len(valid_emails):
        qm = init()
        signal.signal(signal.SIGINT, sigint_handler)
        
        for address in valid_emails:
            email(address)
        print('Queued {} email{} to be sent.'.format(
            len(valid_emails), '' if len(valid_emails) == 1 else 's'))
        
        print('Use Ctrl-C and wait 5 seconds to exit')
        qm.join()
