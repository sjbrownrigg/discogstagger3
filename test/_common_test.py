#!/usr/bin/python
# -*- coding: utf-8 -*-
import os

from discogstagger.discogsalbum import DiscogsAlbum
import discogs_client as discogs

class DummyResponse(object):
    def __init__(self, releaseid):
        self.releaseid = releaseid

        __location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
        json_file_name =  "%s/release.json" % self.releaseid
        json_file_path = os.path.join(__location__, json_file_name)
        json_file = open(json_file_path, "r")

        self.status_code = 200
        self.content = json_file.read()


class DummyDiscogsAlbum(DiscogsAlbum):
    def __init__(self, dummy_response):
        self.dummy_response = dummy_response
        self.release = discogs.Release(dummy_response.releaseid)
        self.release._cached_response = self.dummy_response

        DiscogsAlbum.__init__(self, self.release)

