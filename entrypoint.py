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
output_file = os.getenv("INPUT_OUTPUT_FILE")
try:
    os.makedirs(output_file)
except FileExistsError:pass

def image_to_data_url(filename, img):
    ext = filename.split('.')[-1]
    prefix = f'data:image/{ext};base64,'
    return prefix + base64.b64encode(img).decode('utf-8')

class Message:
    """Operation on a message"""

    def __init__(self, msg):
        self.msg = msg
        self.directory = 'outputs'

    def getmailheader(self, header_text, default="ascii"):
        """Decode header_text if needed"""
        try:
            headers=decode_header(header_text)
        except email.Errors.HeaderParseError:
            # This already append in email.base64mime.decode()
            # instead return a sanitized ascii string
            return header_text.encode('ascii', 'replace').decode('ascii')
        else:
            for i, (text, charset) in enumerate(headers):
                headers[i]=text
                if charset:
                    headers[i]=str(text, charset)
                elif isinstance(text, bytes):
                    headers[i]=text.decode('utf8')
                else:
                    headers[i]=str(text)
            return u"".join(headers)


    def getSubject(self):
        if not hasattr(self, 'subject'):
            self.subject = self.getmailheader(self.msg.get('Subject', ''))
        return self.subject

    def createMetaFile(self):

        parts = self.getParts()
        attachments = []
        for afile in parts['files']:
            attachments.append(afile[1])

        text_content = ''

        if parts['text']:
            text_content = self.getTextContent(parts['text'])
        #  else:
            #  if parts['html']:
                #  text_content = strip_tags(self.getHtmlContent(parts['html']))

        data = json.dumps({
            'Id': self.msg['Message-Id'],
            'Subject' : self.getSubject(),
            'Attachments': attachments,
            'WithHtml': len(parts['html']) > 0,
            'WithText': len(parts['text']) > 0,
            'Body': text_content
        }, indent=4, ensure_ascii=False)
        print(data)


    def getPartCharset(self, part):
        if part.get_content_charset() is None:
            # Python 2 chardet expects a string,
            # Python 3 chardet expects a bytearray.
            if sys.version_info[0] < 3:
                return chardet.detect(part.as_string())['encoding']
            else:
                try:
                    return chardet.detect(part.as_bytes())['encoding']
                except UnicodeEncodeError:
                        string = part.as_string()
                        array = bytearray(string, 'utf-8')
                        return chardet.detect(array)['encoding']
        return part.get_content_charset()


    def getTextContent(self, parts):
        if not hasattr(self, 'text_content'):
            self.text_content = ''
            for part in parts:
                raw_content = part.get_payload(decode=True)
                charset = self.getPartCharset(part)
                self.text_content += raw_content.decode(charset, "replace")
        return self.text_content


    def createTextFile(self, parts):
        utf8_content = self.getTextContent(parts)
        return utf8_content

    def getHtmlContent(self, parts):
        if not hasattr(self, 'html_content'):
            self.html_content = ''

            for part in parts:
                raw_content = part.get_payload(decode=True)
                charset = self.getPartCharset(part)
                self.html_content += raw_content.decode(charset, "replace")

            m = re.search('<body[^>]*>(.+)<\/body>', self.html_content, re.S | re.I)
            if (m != None):
                self.html_content = m.group(1)

        return self.html_content


    def createHtmlFile(self, parts, embed):

        utf8_content = self.getHtmlContent(parts)
        for img in embed:
            pattern = 'src=["\']cid:%s["\']' % (re.escape(img[0]))
            payload = img[1].get_payload(decode=True)
            path = image_to_data_url(img[0], payload)
            utf8_content = re.sub(pattern, 'src="%s"' % (path), utf8_content, 0, re.S | re.I)


        subject = self.getSubject()

        utf8_content = """<!doctype html>
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <title>%s</title>
</head>
<body>
%s
</body>
</html>""" % (subject, utf8_content)
#  </html>""" % (cgi.escape(subject), utf8_content)
        return utf8_content


    def getParts(self):
        if not hasattr(self, 'message_parts'):
            counter = 1
            message_parts = {
                'text': [],
                'html': [],
                'embed_images': [],
                'files': []
            }

            for part in self.msg.walk():
                # multipart/* are just containers
                if part.get_content_maintype() == 'multipart':
                    continue

                # Applications should really sanitize the given filename so that an
                # email message can't be used to overwrite important files
                filename = part.get_filename()
                if not filename:
                    if part.get_content_type() == 'text/plain':
                        message_parts['text'].append(part)
                        continue

                    if part.get_content_type() == 'text/html':
                        message_parts['html'].append(part)
                        continue

                    ext = mimetypes.guess_extension(part.get_content_type())
                    if not ext:
                        # Use a generic bag-of-bits extension
                        ext = '.bin'
                    filename = 'part-%03d%s' % (counter, ext)

                content_id =part.get('Content-Id')
                if (content_id):
                    content_id = content_id[1:][:-1]
                    message_parts['embed_images'].append((content_id, part))

                counter += 1
            self.message_parts = message_parts
        return self.message_parts


    def write_html(self, output_file):
        message_parts = self.getParts()
        output = ''
        if message_parts['text']:
            text = self.createTextFile(message_parts['text'])
            output = """<!doctype html>
    <html>
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    </head>
    <body>
    %s
    </body>
    </html>""" % (text)

        if message_parts['html']:
            output = self.createHtmlFile(message_parts['html'], message_parts['embed_images'])
        with open(output_file, 'wb') as fp:
            fp.write(bytearray(output, 'utf-8'))

def saveEmail(data, output):
    for response_part in data:
        if isinstance(response_part, tuple):
            msg = ""
            # Handle Python version differences:
            # Python 2 imaplib returns bytearray, Python 3 imaplib
            # returns str.
            if isinstance(response_part[1], str):
                msg = email.message_from_string(response_part[1])
            else:
                try:
                    msg = email.message_from_string(response_part[1].decode("utf-8"))
                except:
                    print("couldn't decode message with utf-8 - trying 'ISO-8859-1'")
                    msg = email.message_from_string(response_part[1].decode("ISO-8859-1"))

            message = Message(msg)
            #  message.createMetaFile()
            message.write_html(os.path.join(output, message.getSubject() + '.html'))
            return {
                'message_id': message.msg['Message-Id'],
                'file_name': os.path.join(
                    output, message.getSubject() + '.html'),
            }


    return True
# connect to host using SSL
imap = imaplib.IMAP4_SSL(imap_host)

## login to server
imap.login(imap_user, imap_pass)

imap.select('Inbox', readonly=True)

#  tmp, data = imap.search(None, 'ALL')
#  tmp, data = imap.search(None, '(HEADER Message-ID "%s")' % message_id)
tmp, data = imap.search(None, 'Unseen')
print(tmp,data)
mails = {}
for num in data[0].split():
    tmp, data = imap.fetch(num, '(RFC822)')
    #  print(tmp, data)
    r = saveEmail(data, output_file)
    mails[r['message_id']] = r['file_name']
imap.close()

with open(output_file + '/dump.json', 'w') as _fd:
    json.dump(mails, _fd)
