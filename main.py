#!/usr/bin/env python
from __future__ import print_function
from alsaaudio import Mixer
from random import choice
from serial import Serial
from urllib2 import urlopen, HTTPError
import argparse
import json
import os
import subprocess as sp
import sys
import time

# This is a list of sample songs that will randomly play if the
# user is misidentified or does not exist!
DEFAULT_SONGS = [
    "/users/u22/stuart/harold.mp3",
    "/users/u22/henry/harold.mp3",
    "/users/u22/mbillow/harold.mp3",
    "/users/u22/henry/harold/selfie.mp3",
    "/users/u22/henry/harold/waka.mp3",
    "/users/u22/henry/harold/topworld.mp3",
    "/users/u22/henry/harold/heybrother.mp3",
    "/users/u22/henry/harold/boomclap.mp3",
    "/users/u22/henry/harold/starships.mp3",
    "/users/u22/henry/harold/domino.mp3",
    "/users/u22/henry/harold/cruise.mp3"
]

SONG_EXTS = (
    ".mp3", ".mp4", ".m4a", ".m4p",
    ".flac", ".ogg", ".oga", ".wav",
    ".wma"
)

DING_SONG = "/home/pi/ding.mp3"

MPLAYER_FIFO = "/tmp/mplayer.fifo"

FNULL = open(os.devnull, 'w')


class MockSerial:

    def __init__(self, fi=sys.stdin):
        self.fi = fi

    def readline(self):
        return self.fi.readline()

    def flushInput(self):
        return self.fi.flush()


def quiet_hours():
    ' Returns True if the current time is within RIT quiet hours '
    currtime = time.localtime()
    if currtime.tm_wday > 4:
        return (currtime.tm_hour + 23) % 24 < 6
    else:
        return (currtime.tm_hour + 1) % 24 < 8


def read_ibutton(varID):
    '''
    Use Nick Depinet's LDAP service to convert iButtons to usernames
    '''
    try:
        data = urlopen('http://www.csh.rit.edu:56124/?ibutton=' + varID)
        usernameData = json.load(data)
    except HTTPError as error:
        # Need to check its an 404, 503, 500, 403 etc.
        print(error.read())
        return ""
    except ValueError as error:
        # Got malformed JSON somehow
        return ""
    else:
        return usernameData['username'][0]


def get_user_song(username):
    '''
    Load one of the following files:
    ~/harold.mp3
    ~/harold/*, of one of the supported file types
    '''
    if username:
        homedir = os.path.expanduser("~" + username)
        hdir = os.path.join(homedir, "harold")
        hfile = os.path.join(homedir, "harold.mp3")
        if os.path.isdir(hdir):
            playlist = [f for f in os.listdir(hdir)
                        if os.path.isfile(os.path.join(hdir, f))
                        and f.endswith(SONG_EXTS)]
            return os.path.join(hdir, choice(playlist))
        elif os.path.isfile(hfile):
            return hfile
    return choice(DEFAULT_SONGS)


class Harold(object):

    def __init__(self, mplfifo, ser, beep=True):
        self.playing = False
        self.fifo = mplfifo
        self.mixer = Mixer(control='PCM')
        self.ser = ser
        self.beep = beep

    def write(self, *args, **kwargs):
        delay = kwargs.pop("delay", 0.5)
        kws = {"file": self.fifo}
        kws.update(kwargs)
        print(*args, **kws)
        time.sleep(delay)

    def __call__(self):
        # Lower the volume during quiet hours... Don't piss off the RA!
        self.mixer.setvolume(85 if quiet_hours() else 100)

        if not self.playing:
            varID = self.ser.readline()
            print(varID)
            # mplayer will play any files sent to the FIFO file.
            if self.beep:
                self.write("loadfile", DING_SONG)
            if "ready" not in varID:
                # Get the username from the ibutton
                username = read_ibutton(varID)

                # Print the user's name (Super handy for debugging...)
                print("New User: '" + username + "'")

                song = get_user_song(username)
                print("Now playing '" + song + "'...\n")
                self.write("loadfile '" + song.replace("'", "\\'") + "'",
                           delay=3.0)

                self.start = time.time()
                self.playing = True

        elif time.time() - self.start >= 25:
            # Fade out the music at the end.
            vol = int(self.mixer.getvolume()[0])
            while vol > 60:
                self.mixer.setvolume(vol)
                time.sleep(0.1)
                vol -= 1 + 1 / 3 * (100 - vol)
            self.write("stop")
            self.playing = False
            self.ser.flushInput()
            print("Stopped\n")


def main():
    # Handle some command line arguments
    parser = argparse.ArgumentParser(description="Start Harold system")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Use debug mode (stdin)")
    parser.add_argument("--serial", "-s",
                        default="/dev/ttyACM0",
                        help="Serial port to use", metavar="PORT")
    parser.add_argument("--rate", "-r",
                        default=9600, type=int,
                        help="Serial device to use")
    parser.add_argument("--fifo", "-f",
                        default="/tmp/mplayer.fifo",
                        help="FIFO to communicate to mplayer with")
    parser.add_argument("--nobeep", "-n", action="store_true",
                        help="Disable beep")
    args = parser.parse_args()
    try:
        os.remove(MPLAYER_FIFO)
    except OSError:
        # This is fine, there just isn't a FIFO there already
        pass
    os.mkfifo(args.fifo)
    cmd = ["mplayer", "-idle", "-slave", "-input", "file="+args.fifo]
    mplayer = sp.Popen(cmd, stdout=FNULL)
    try:
        with open(args.fifo, "w", 0) as mplfifo:
            if args.debug:
                ser = MockSerial()
            else:
                ser = Serial(args.serial, args.rate)
                ser.flushInput()
            harold = Harold(mplfifo, ser, not args.nobeep)
            while True:
                harold()
    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        mplayer.kill()

if __name__ == '__main__':
    main()
