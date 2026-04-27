#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import json

from discogstagger.discogsalbum import DiscogsAlbum, DummyResponse, LocalDiscogsConnector, DiscogsConnector
import discogs_client as discogs


class TestDummyResponse(DummyResponse):
    def __init__(self, releaseid):
        __location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
        path = os.path.join(__location__, "release")
        DummyResponse.__init__(self, releaseid, path)


class DummyDiscogsAlbum(DiscogsAlbum):
    def __init__(self, dummy_response):
        # We need a dummy client here
        client = discogs.Client('Dummy Client - just for unit testing')

        self.dummy_response = dummy_response

        # In Python 3, json.loads already returns str (not bytes/unicode),
        # so no conversion is needed — the old convert() method was purely
        # a Python 2 unicode-to-bytes shim and has been removed.
        self.content = json.loads(dummy_response.content)

        self.release = discogs.Release(client, self.content['resp']['release'])

        DiscogsAlbum.__init__(self, self.release)