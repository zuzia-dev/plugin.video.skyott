#!/usr/bin/env python
# encoding: utf-8
#
# SPDX-License-Identifier: LGPL-2.1-or-later

from __future__ import unicode_literals, absolute_import, division

import base64
import hmac
import hashlib
import sys
import time

if sys.version_info[0] >= 3:
  from urllib.parse import urlparse
else:
  from urlparse import urlparse

signature_key = bytearray('JuLQgyFz9n89D9pxcN6ZWZXKWfgj2PNBUb32zybj', 'utf-8')

def calculate_signature(method, url, headers, payload='', timestamp=None,
                        app_id='NBCU-ANDROID-v3', version='1.0'):
  if not timestamp:
    timestamp = int(time.time())

  if url.startswith('http'):
    parsed_url = urlparse(url)
    path = parsed_url.path
  else:
    path = url

  #print('path: {}'.format(path))

  text_headers = ''
  for key in sorted(headers.keys()):
    if key.lower().startswith('x-skyott'):
      text_headers += key + ': ' + headers[key] + '\n'
  #print(text_headers)
  headers_md5 = hashlib.md5(text_headers.encode()).hexdigest()
  #print(headers_md5)

  if sys.version_info[0] > 2 and isinstance(payload, str):
    payload = payload.encode('utf-8')
  payload_md5 = hashlib.md5(payload).hexdigest()

  to_hash = ('{method}\n{path}\n{response_code}\n{app_id}\n{version}\n{headers_md5}\n'
             '{timestamp}\n{payload_md5}\n').format(method=method, path=path,
              response_code='', app_id=app_id, version=version,
              headers_md5=headers_md5, timestamp=timestamp, payload_md5=payload_md5)
  #print(to_hash)

  hashed = hmac.new(signature_key, to_hash.encode('utf8'), hashlib.sha1).digest()
  signature = base64.b64encode(hashed).decode('utf8')

  return {'x-sky-signature': 'SkyOTT client="{}",signature="{}",timestamp="{}",version="{}"'.format(
      app_id, signature, timestamp, version)}

