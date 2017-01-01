#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2016 Jonathan Schultz
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
import argparse
import sys, os
import unicodecsv
from dateutil import parser as dateparser
import datetime
from TwitterFeed import TwitterFeed
import shutil

parser = argparse.ArgumentParser(description='Scrape and merge twitter feed using pyquery.')

parser.add_argument('-v', '--verbosity', type=int, default=1)

parser.add_argument('-u', '--user',     type=str, help='Twitter username to match.')
parser.add_argument(      '--since',    type=str, help='Lower bound search date (YYYY-MM-DD).')
parser.add_argument(      '--until',    type=str, help='Upper bound search date (YYYY-MM-DD).')
parser.add_argument('-l', '--language', type=str, help='Language code to filter.')
parser.add_argument('-q', '--query',    type=str, help='Search string to filter twitter content.')

parser.add_argument('-o', '--outfile', type=str, nargs='?', help='Output file, otherwise use stdout.')

parser.add_argument('infile', type=str, nargs='*',
                    help='Input CSV files.')

args = parser.parse_args()

# Process outfile depending on whether it exists or not
replaceoutfile = False
if args.outfile is None:
    outfile = sys.stdout
elif os.path.isfile(args.outfile):
    args.infile += [args.outfile]
    outfile = file(args.outfile + '.part', 'wb')
    replaceoutfile = True
else:
    outfile = file(args.outfile, 'wb')

def nextornone(generator):
    try:
        return next(generator)
    except StopIteration:
        return None

# Process input files
infile = []
inreader = []
currow = []
rowcnt = []
headidx = None
openfiles = 0
for fileidx in range(len(args.infile)):
    infile += [file(args.infile[fileidx], 'r')]
    inreader += [unicodecsv.DictReader(infile[fileidx])]
    if inreader[fileidx].fieldnames != inreader[0].fieldnames:
        raise RuntimeError("File: " + args.infile[fileidx] + " has mismatched field names")

    currowitem = nextornone(inreader[fileidx])
    currow += [currowitem]
    rowcnt += [0]
    if currowitem is not None:
        openfiles += 1
        if headidx is None or currowitem['id'] > currow[headidx]['id']:
            headidx = fileidx

if len(args.infile) > 0:
    fieldnames = fieldnames=inreader[0].fieldnames
else:
    fieldnames = ['user', 'date', 'retweets', 'favorites', 'text', 'lang', 'geo', 'mentions', 'hashtags', 'id', 'permalink']

# Append placeholder for twitter feed to list of readers
twitteridx = len(inreader)
inreader += [None]
currow += [None]
rowcnt += [0]
args.infile += ['twitter feed']

# Start twitter feed if needed to reach 'until' argument
if args.until is not None and args.until > (0 if headidx is None else currow[headidx]['date']):
    sincedate = args.since
    if headidx is not None:
         sincedate = max(sincedate, dateparser.parse(currow[headidx]['date']).date().isoformat())

    twittersince = sincedate
    twitteruntil = args.until

    if args.verbosity > 1:
        print("Opening twitter feed with until:" + twitteruntil + ", since: " + (twittersince or ''), file=sys.stderr)

    twitterreader = TwitterFeed(language=args.language, user=args.user, query=args.query,
                                until=twitteruntil, since=twittersince)

    currowitem = nextornone(twitterreader)
    currow[twitteridx] = currowitem
    if currowitem is not None:
        openfiles += 1
        inreader[twitteridx] = twitterreader
        currowitem['date'] = currowitem['datetime'].isoformat()
        if headidx is None or currowitem['id'] > currow[headidx]['id']:
            headidx = twitteridx
    else:
        twitterreader = None
        if args.verbosity > 1:
            print("Closing twitter feed", file=sys.stderr)

matching = [(headidx is not None and currow[fileidx] is not None and currow[fileidx]['id'] == currow[headidx]['id'])
                for fileidx in range(len(inreader))]

if headidx is None:
    if args.verbosity > 1:
        print("Nothing to do.", file=sys.stderr)
    sys.exit()

outunicodecsv=unicodecsv.DictWriter(outfile, fieldnames, extrasaction='ignore')
outunicodecsv.writeheader()

while True:
    outunicodecsv.writerow(currow[headidx])
    rowcnt[headidx] += 1
    lastid = currow[headidx]['id']
    lastdate = currow[headidx]['date']


    #for fileidx in range(len(inreader)):
        #if currow[fileidx] is not None and matching[fileidx]:
            #if currow[fileidx] != currow[headidx]:
                #print("WARNING: Inconsistent data, id: " + currow[headidx]['id'] + " sources: " + args.infile[headidx] + " and " + args.infile[fileidx], file=sys.stderr)

    # If we are past the 'since' date then finish up
    if args.since is not None and lastdate < args.since:
        break

    for fileidx in range(len(inreader)):
        if currow[fileidx] is not None and currow[fileidx]['id'] == currow[headidx]['id']:
            currow[fileidx] = nextornone(inreader[fileidx])
            if currow[fileidx] is None:
                if args.verbosity > 1:
                    print("Closing " + args.infile[fileidx] + " after " + str(rowcnt[fileidx]) + " rows.", file=sys.stderr)
                rowcnt[fileidx] = 0
                matching[fileidx] = False
                inreader[fileidx] = None
                openfiles -= 1
                # Forget exhausted twitter feed since it cannot be re-used
                if fileidx == twitteridx:
                    twitterreader = None
            # Test for blank record in CSV
            elif currow[fileidx]['id'] == '':
                currow[fileidx] = None

    headidx = None
    for fileidx in range(len(inreader)):
        if currow[fileidx] is not None and (headidx is None or currow[fileidx]['id'] > currow[headidx]['id']):
            headidx = fileidx

    nextheadidx = headidx
    for fileidx in range(len(inreader)):
        if inreader[fileidx] is not None:
            if currow[fileidx] is None:
                currow[fileidx] = nextornone(inreader[fileidx])
                matching[fileidx] = False
                if currow[fileidx] is not None and (nextheadidx is None or currow[fileidx]['id'] > currow[nextheadidx]['id']):
                    nextheadidx = fileidx

            if currow[fileidx] is not None:
                if 'date' not in currow[fileidx].keys():
                    currow[fileidx]['date'] = currow[fileidx]['datetime'].isoformat()

                if matching[fileidx]:
                    if currow[fileidx]['id'] != currow[headidx]['id']:
                        print("WARNING: Missing tweet, id: " + currow[fileidx]['id'] + " in file: " + args.infile[fileidx], file=sys.stderr)
                        matching[fileidx] = False
                elif headidx is not None:
                    if currow[fileidx]['id'] == currow[headidx]['id']:
                        matching[fileidx] = True

    headidx = nextheadidx

    # Cancel twitter reader if it is now matched by an input file
    if inreader[twitteridx] is not None and len([fileidx for fileidx in range(len(inreader) - 1) if matching[fileidx]]) > 0:
        if args.verbosity > 1:
            print("Closing " + args.infile[twitteridx] + " after " + str(rowcnt[twitteridx]) + " rows.", file=sys.stderr)

        # Remember last date so we can re-use the twitter feed later.
        twitterdate = currow[twitteridx]['date']
        currow[twitteridx] = None
        rowcnt[twitteridx] = 0
        matching[twitteridx] = False
        inreader[twitteridx] = None
        openfiles -= 1

    # If no file is now matching, try opening a twitter feed
    if len([idx for idx in range(len(inreader)) if matching[idx]]) == 0:
        sincedate = args.since
        if headidx is not None:
            sincedate = max(sincedate, dateparser.parse(currow[headidx]['date']).date().isoformat())

        if twitterreader is not None and twittersince <= sincedate and dateparser.parse(twitterdate).date() == dateparser.parse(lastdate).date():
            if args.verbosity > 1:
                print("Re-opening twitter feed with until:" + twitteruntil + ", since: " + (twittersince or ''), file=sys.stderr)
        else:
            twittersince = sincedate

            # Set until date one day past lastdate because twitter returns tweets strictly before until date
            twitteruntil = (dateparser.parse(lastdate) + datetime.timedelta(days=1)).date().isoformat()

            if args.verbosity > 1:
                print("Opening twitter feed with until:" + twitteruntil + ", since: " + (twittersince or ''), file=sys.stderr)

            twitterreader = TwitterFeed(language=args.language, user=args.user, query=args.query,
                                        until=twitteruntil, since=twittersince)

        currowitem = nextornone(twitterreader)
        while currowitem is not None and currowitem['id'] >= lastid:
            currowitem = nextornone(twitterreader)

        if currowitem is not None:
            if currowitem['id'] == lastid:
                currowitem = nextornone(twitterreader)
                if currowitem is not None:
                    matching[twitteridx] = True

        if currowitem is not None:
            openfiles += 1
            inreader[twitteridx] = twitterreader
            if 'date' not in currowitem.keys():
                currowitem['date'] = currowitem['datetime'].isoformat()
            currow[twitteridx] = currowitem
            if headidx is None or currowitem['id'] > currow[headidx]['id']:
                headidx = twitteridx
        else:
            twitterreader = None
            if args.verbosity > 1:
                print("Closing twitter feed", file=sys.stderr)

        if not matching[twitteridx]:
            outunicodecsv.writerow({})
            if headidx is not None:
                print("Possible missing tweets between id: " + str(lastid) + " - " + dateparser.parse(lastdate).isoformat() + " and " + str(currow[headidx]['id']) + " - " + dateparser.parse(currow[headidx]['date']).isoformat(), file=sys.stderr)
            else:
                print("Possible missing tweets after id: " + str(lastid) + " - " + dateparser.parse(lastdate).isoformat(), file=sys.stderr)
                break

# Finish up
outfile.close()
if replaceoutfile:
    shutil.move(args.outfile + '.part', args.outfile)
