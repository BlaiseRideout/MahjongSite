#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Simple implementation of mailer based on thread and queues. Early version.
@author: Marcin Chwalek <marcin@chwalek.pl>
Example of use:
    # at start
    qm = QueMail.get_instance()
    qm.init('smtp.host.com', 'user@auth.com', 'SecretPassword')
    qm.start()
    ...
    # someware in app method
    qm = QueMail.get_instance()
    qm.send(Email(subject="Subject", text="Keep smiling :)", adr_to="marcinc81@gmail.com", adr_from="sender@email.com"))

    ...
    # after everything, at end of app
    qm.end()
'''

import smtplib
import logging
import time

from email.mime.text import MIMEText
from email.utils import make_msgid, formatdate

from time import sleep
from queue import Queue
from threading import Thread


log = logging.getLogger("QueMail")

class QueMail(Thread):
    instance = None

    def init(self, smtp_host, smtp_login, smtp_pswd, smtp_port = 25, use_tls = False, queue_size = 100):
        self._queue = Queue(queue_size)
        log.info("Initializing QueMail (queue size = %i). "
                 "Using SMTP server: %s:%i %s TLS." % (
                     queue_size, smtp_host, smtp_port,
                     'with' if use_tls else 'without'))
        self.smtp_host = smtp_host
        self.smtp_login = smtp_login
        self.smtp_password = smtp_pswd
        self.smtp_port = smtp_port
        self.use_tls = use_tls
        try:
            smtp = self.establish_SMTP_connection()
        except Exception as e:
            log.error('Error establishing connection to SMTP server: {}'.format(
                e))

    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._do_quit = False
        self.setName("QueMail")
        self.smtp_host = None
        self.smtp_login = None
        self.smtp_password = None
        self.smtp_port = None
        self.use_tls = False
        self.check_interval = 5    # the number of seconds between queue checks

    def end(self):
        '''
        Waits until all emails will be sent and after that stops thread
        '''
        log.info("Stopping QueMail thread...")
        self._do_quit = True
        self.join()
        log.info("Stopped.")

    def run(self):
        while not self._do_quit:
            if not self._queue.empty():
                smtp = None
                try:
                    smtp = self.establish_SMTP_connection()
                    
                    while not self._queue.empty():
                        t = time.time()
                        eml = self._queue.get()
                        log.info(u"Sending (qs=%i): %s" % (self._queue.qsize(), eml))
                        try:
                            msg = eml.as_rfc_message()
                            content = msg.as_string()
                            log.debug(u"with content: %s" % content)
                            smtp.sendmail(eml.adr_from, eml.adr_to, content)
                            log.warning(u"Sent (qs=%i,t=%f): %s" % (self._queue.qsize(),time.time()-t, eml))
                        except Exception as e:
                            log.error(u"Exception occured while sending email: %s" % eml)
                            log.exception(e)
                            # FIXME not good idea: when exception occured, add email at end of queue
                            self._queue.put(eml, False)
                            sleep(1)
                except Exception as e:
                    log.exception(e)
                finally:
                    if smtp:
                        smtp.quit()
            sleep(self.check_interval)

    def establish_SMTP_connection(self):
        log.debug(u"Connecting to SMTP server: %s:%i%s using TLS" % (
            self.smtp_host, self.smtp_port, '' if self.use_tls else ' not'))
        smtp = smtplib.SMTP()
        smtp.connect(self.smtp_host, self.smtp_port)
        if self.use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(self.smtp_login, self.smtp_password)
        return smtp
        
    def send(self, eml):
        if self._queue is None:
            return
        self._queue.put(eml, True, 5);
        log.debug(u'Accepted (qs=%i): %s' % (self._queue.qsize(), eml))

    @classmethod
    def get_instance(cls):
        if not cls.instance:
            cls.instance = QueMail()
        return cls.instance


class Email(object):
    unique = 'unique-send'

    def __init__(self, **props):
        '''
        @param adr_to: send to
        @param adr_from: send from
        @param subject: subject of email
        @param mime_type: plain or html - only minor mime type of 'text/*'
        @param text: text content of email
        '''
        self.text = props.get('text', '')
        self.subject = props.get('subject', None)
        self.adr_to = props.get('adr_to', None)
        self.adr_from = props.get('adr_from', None)
        self.mime_type = props.get('mime_type', 'plain')

    def __str__(self):
        return "Email to: %s, from: %s, sub: %s" % (self.adr_to, self.adr_from, self.subject)

    def as_rfc_message(self):
        '''
        Creates standardized email with valid header
        '''
        msg = MIMEText(self.text, self.mime_type, 'utf-8')
        msg['Subject'] = self.subject
        msg['From'] = self.adr_from
        msg['To'] = self.adr_to
        msg['Date'] = formatdate()
        msg['Reply-To'] = self.adr_from
        msg['Message-Id'] = make_msgid(Email.unique)
        return msg
