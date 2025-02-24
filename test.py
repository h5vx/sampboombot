#!/usr/bin/env python

# usage: ./example.py /path/to/file1 /path/to/file2 ...
import string
import sys
import time

import requests
import shout

print(sys.version)
s = shout.Shout()
print("Using libshout version %s" % shout.version())

# s.host = 'ugubok.ru'
s.host = '46.36.219.123'
s.port = 8004
s.user = 'source'
s.password = 'll31415926'
s.mount = "/test2.ogg"
s.format = 'mp3' # vorbis | mp3
s.protocol = 'http' #'http' | 'xaudiocast' | 'icy'
s.name = 'namee'
s.genre = 'mechanic'
s.url = ''
s.public = 1  # 0 | 1
s.audio_info = {shout.SHOUT_AI_BITRATE:'256',
                shout.SHOUT_AI_SAMPLERATE:'48000',
                shout.SHOUT_AI_CHANNELS:'2'}
# (keys are shout.SHOUT_AI_BITRATE, shout.SHOUT_AI_SAMPLERATE,
#  shout.SHOUT_AI_CHANNELS, shout.SHOUT_AI_QUALITY)
success = False

for _ in range(5):
    try:
        s.open()
        success = True
    except Exception as e:
        print("retrying")

if not success:
    print("failed")
    sys.exit(1)

conn_result = s.get_connected()

print(conn_result)

url = 'https://storage4.lightaudio.ru/dm/3995cf68/2ea3433a/%D0%9B%D0%B0%D1%8D%D1%80%D1%82%D1%81%D0%BA%D0%B8%D0%B9%20%D0%90%D0%BB%D0%B5%D0%BA%D1%81%D0%B0%D0%BD%D0%B4%D1%80%20%E2%80%94%20%D0%A1%D0%B8%D1%81%D1%8C%D0%BA%D0%B8%20%D0%B2%20%D1%82%D0%B5%D1%81%D1%82%D0%B5.mp3?d=318&v=57b6817ad0'

total = 0
st = time.time()
r = requests.get(url, stream=True)
s.set_metadata({'song': "song metadata"})

nbuf = r.raw.read(4096)
while 1:
	buf = nbuf
	nbuf = r.raw.read(4096)
	total = total + len(buf)
	if len(buf) == 0:
		break
	s.send(buf)
	s.sync()
f.close()

et = time.time()
br = total*0.008/(et-st)
print("Sent %d bytes in %d seconds (%f kbps)" % (total, et-st, br))

s.close()
