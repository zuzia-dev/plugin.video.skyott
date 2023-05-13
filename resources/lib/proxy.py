#!/usr/bin/env python
# encoding: utf-8
#
# SPDX-License-Identifier: LGPL-2.1-or-later

from __future__ import unicode_literals, absolute_import, division

try:  # Python 3
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:  # Python 2
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

try:  # Python 3
    from socketserver import TCPServer, ThreadingMixIn
except ImportError:  # Python 2
    from SocketServer import TCPServer, ThreadingMixIn

try:  # Python 3
    from urllib.parse import unquote, quote_plus
except ImportError:  # Python 2
    from urllib import unquote, quote_plus

try:  # Python 3
  from urllib.parse import parse_qsl
except:  # Python 2
  from urlparse import parse_qsl

import os
import re
import json
import requests
import threading
import socket
from contextlib import closing
import xbmcaddon

from .b64 import encode_base64
from .log import LOG
from .addon import profile_dir, addon
from .signature import Signature
from .parsemanifest import extract_tracks
from .user_agent import user_agent

session = requests.Session()

def is_ascii(s):
  try:
    return s.isascii()
  except:
    return all(ord(c) < 128 for c in s)

def try_load_json(text):
  try:
    return json.loads(text)
  except:
    return None

class RequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        """Handle http get requests, used for manifest"""
        path = self.path  # Path with parameters received from request e.g. "/manifest?id=234324"
        print('HTTP GET Request received to {}'.format(path))

        if 'manifest' in path:
            pos = path.find('=')
            url = path[pos+1:]
            LOG('url: {}'.format(url))
            try:
                response = session.get(url, allow_redirects=True)
                LOG('headers: {}'.format(response.headers))
                baseurl = os.path.dirname(response.url)
                LOG('baseurl: {}'.format(baseurl))
                content = response.content.decode('utf-8')
                pos = content.find('<Period')
                if pos > -1:
                  content = content[:pos] + '<BaseURL>' + baseurl + '/</BaseURL>' + content[pos:]

                tracks = extract_tracks(content)
                if addon.getSettingBool('delete_ec3_audio'):
                  for track in tracks['audios']:
                    if 'ec-3' in track['codecs']:
                      content = content.replace(track['orig'], '<!-- Deleted ec-3 audio track {} -->\n'.format(track['lang']))

                if addon.getSettingBool('delete_mp4a_audio'):
                  for track in tracks['audios']:
                    if 'mp4a' in track['codecs']:
                      content = content.replace(track['orig'], '<!-- Deleted mp4a audio track {} -->\n'.format(track['lang']))

                for track in tracks['subs']:
                  if track['split']:
                    # It seems this isn't supported by Kodi.
                    # The track is removed, otherwise Kodi keeps turning off subtitles
                    # and it doesn't even allow to use external subtitles.
                    content = content.replace(track['orig'], '<!-- Deleted subtitle track {} -->\n'.format(track['lang']))

                if addon.getSettingBool('fix_languages'):
                  for track_type in ('subs', 'audios'):
                    for track in tracks[track_type]:
                      content = content.replace(track['orig'], track['mod'])

                #LOG('content: {}'.format(content))
                self.send_response(200)
                self.send_header('Content-type', 'application/xml')
                #self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except Exception:
                # Redirect
                self.send_response(301)
                self.send_header('Location', url)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


    def do_POST(self):
        """Handle http post requests, used for license"""
        path = self.path  # Path with parameters received from request e.g. "/license?id=234324"
        print('HTTP POST Request received to {}'.format(path))
        if '/license' not in path:
            self.send_response(404)
            self.end_headers()
            return
        try:
            pos = path.find('?')
            path = path[pos+1:]
            params = dict(parse_qsl(path))
            LOG('params: {}'.format(params))

            length = int(self.headers.get('content-length', 0))
            isa_data = self.rfile.read(length)
            LOG('isa_data length: {}'.format(length))
            LOG('isa_data: {}'.format(encode_base64(isa_data)))
            #with open('/tmp/isa_data.bin', 'wb') as f:
            #  f.write(isa_data)

            url = params['url']
            LOG('url: {}'.format(url))

            platform_id = addon.getSetting('platform_id').lower()
            headers = {
              'User-Agent': user_agent(platform_id),
              'Accept': '*/*',
            }

            path="/" + url.split("://", 1)[1].split("/", 1)[1]
            LOG(path)

            sig = Signature(platform_id)
            sig_header = sig.calculate_signature('POST', path, {}, isa_data)
            headers.update(sig_header)

            LOG('headers: {}'.format(headers))

            response = session.post(url, data=isa_data, headers=headers)
            license_data = response.content
            LOG('license response status: {}'.format(response.status_code))
            LOG('license response length: {}'.format(len(license_data)))
            if is_ascii(license_data):
              LOG('license response: {}'.format(license_data))
              d = try_load_json(license_data)
              if d and 'errorCode' in d and 'description' in d:
                from .gui import show_notification
                show_notification('{}: {}'.format(addon.getLocalizedString(30200), d['description']))
            else:
              LOG('license response: {}'.format(encode_base64(license_data)))

            self.send_response(response.status_code)
            self.end_headers()
            self.wfile.write(license_data)
        except Exception:
            self.send_response(500)
            self.end_headers()


HOST = '127.0.0.1'
PORT = 57012

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class Proxy(object):
    started = False

    def check_port(self, port=0, default=False):
      try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
          s.bind((HOST, port))
          s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
          return s.getsockname()[1]
      except:
        return default

    def start(self):
        if self.started:
            return

        port = self.check_port(PORT)
        if not port:
          port = self.check_port(0)
        LOG('port: {}'.format(port))

        self._server = ThreadedHTTPServer((HOST, port), RequestHandler)
        self._server.allow_reuse_address = True
        self._httpd_thread = threading.Thread(target=self._server.serve_forever)
        self._httpd_thread.start()
        self.proxy_address = 'http://{}:{}'.format(HOST, port)
        self.started = True
        LOG("Proxy Started: {}:{}".format(HOST, port))

    def stop(self):
        if not self.started:
            return

        self._server.shutdown()
        self._server.server_close()
        self._server.socket.close()
        self._httpd_thread.join()
        self.started = False
        LOG("Proxy: Stopped")
