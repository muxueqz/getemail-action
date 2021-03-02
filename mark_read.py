#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import email
from email.header import decode_header
import imaplib
import json
import re
import os

import base64

imap_host = os.getenv("INPUT_EMAIL_SERVER")
imap_user = os.getenv("INPUT_EMAIL_USER")
imap_pass = os.getenv("INPUT_EMAIL_PASSWORD")
message_id = os.getenv("INPUT_MESSAGE_ID")
output_file = os.getenv("INPUT_OUTPUT_FILE")

# connect to host using SSL
imap = imaplib.IMAP4_SSL(imap_host)

## login to server
imap.login(imap_user, imap_pass)

imap.select('Inbox', readonly=False)

with open(output_file + '/dump.json', 'r') as _fd:
    mails = json.load(_fd)

for message_id in mails.keys():
    tmp, data = imap.search(None, '(HEADER Message-ID "%s")' % message_id)
    for num in data[0].split():
        tmp, data = imap.fetch(num, '(BODY[HEADER.FIELDS (MESSAGE-ID)] BODY[HEADER.FIELDS (SUBJECT)])')
        print(tmp, data)

imap.close()
