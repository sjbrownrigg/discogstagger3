import os, sys
import logging
import time
import shutil

logging.basicConfig(level=10)
logger = logging.getLogger(__name__)

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parentdir)

logger.debug("parentdir: %s" % parentdir)

from _common_test import TestDummyResponse, DummyDiscogsAlbum

from discogstagger.tagger_config import TaggerConfig
from discogstagger.discogsalbum import DiscogsConnector, DiscogsAlbum

class TestDiscogsAlbum(object):

    def setUp(self):
        self.ogsrelid = "1448190"

        # construct config with only default values
        self.tagger_config = TaggerConfig(os.path.join(parentdir, "test/empty.conf"))

        self.dummy_dir = "/tmp/dummy_test_dir"

        if not os.path.exists(self.dummy_dir):
            os.makedirs(self.dummy_dir)

    def tearDown(self):
        self.ogsrelid = None
        self.tagger_config = None

        if os.path.exists(self.dummy_dir):
            shutil.rmtree(self.dummy_dir)

        self.dummy_dir = None

    def test_download_release(self):
        """
            This is not really a test, just a showcase, that the rate-limiting works ;-)
            you can call it using nosetest -s --nologcapture test/test_discogs.py
            This call will show, that almost certainly some WARN-messages are printed
            (except you haven an extremely fast pc).
        """
        discogs_connection = DiscogsConnector(self.tagger_config)

        start = time.time()

        for x in range(1, 12):
            discogs_connection.fetch_release(self.ogsrelid)

        stop = time.time()

        logger.debug('stop - start: %d' % (stop - start))

        assert stop - start > 10

    def test_download_image_wo_tokens(self):
        """
            Test the downloads of images without a token, no download possible
            Not really a valid test, just watching, that the auth stuff is working ;-)
        """
        if os.path.exists(self.dummy_dir):
            shutil.rmtree(self.dummy_dir)

        discogs_connection = DiscogsConnector(self.tagger_config)

        discogs_connection.fetch_image(os.path.join(self.dummy_dir, 'folder.jpg'), "http://api.discogs.com/image/R-3083-1167766285.jpeg")

        assert not os.path.exists(os.path.join(self.dummy_dir, 'folder.jpg'))

    def test_download_image_with_tokens(self):
        """
            test the download of images with authentification

            Because we would like to test this stuff on travis as well, we cannot store the tokens inside the
            usual "env" variables (otherwise the test test_download_images_wo_tokens would not work), as well
            as not in any config file. We do need to attache them from the travis environment to the tagger_config

            for this test to work, you should set the below mentioned environment variables before running the tesst
            with nosetests -s test/test_discogs.py
        """
        if "TRAVIS_DISCOGS_CONSUMER_KEY" in os.environ:
            consumer_key = os.environ.get('TRAVIS_DISCOGS_CONSUMER_KEY')
        if "TRAVIS_DISCOGS_CONSUMER_SECRET" in os.environ:
            consumer_secret = os.environ.get("TRAVIS_DISCOGS_CONSUMER_SECRET")

        config = TaggerConfig(os.path.join(parentdir, "test/empty.conf"))
        config.set("discogs", "consumer_key", consumer_key)
        config.set("discogs", "consumer_secret", consumer_secret)

        logger.debug('consumer_key %s' % consumer_key)
        logger.debug('config %s' % config.get("discogs", "consumer_key"))

        discogs_connection = DiscogsConnector(config)
        discogs_connection.fetch_image(os.path.join(self.dummy_dir, 'folder.jpg'), "http://api.discogs.com/image/R-3083-1167766285.jpeg")

        assert os.path.exists(os.path.join(self.dummy_dir, 'folder.jpg'))

        os.remove(os.path.join(self.dummy_dir, 'folder.jpg'))

        discogs_connection.fetch_image(os.path.join(self.dummy_dir, 'folder.jpg'), "http://api.discogs.com/image/R-367882-1193559996.jpeg")

        assert os.path.exists(os.path.join(self.dummy_dir, 'folder.jpg'))

    def test_year(self):
        """test the year property of the DiscogsAlbum
        """
        dummy_response = TestDummyResponse(self.ogsrelid)
        discogs_album = DummyDiscogsAlbum(dummy_response)

        discogs_album.release.data["year"] = "2000"
        assert discogs_album.year == "2000"

        discogs_album.release.data["year"] = "xxxx"
        assert discogs_album.year == "1900"

        discogs_album.release.data["year"] = None
        assert discogs_album.year == "1900"

        discogs_album.release.data["year"] = 2000
        assert discogs_album.year == "2000"

        discogs_album.release.data["year"] = 20
        assert discogs_album.year == "1900"

    def test_construct_token_file(self):
        """test the construct_token_file in discogsConnector
        """
        discogs_connection = DiscogsConnector(self.tagger_config)

        filename = discogs_connection.construct_token_file()
        assert filename.endswith('.token')

    def test_read_token(self):
        """read the token file, if it exists
        """
        config = TaggerConfig(os.path.join(parentdir, "test/empty.conf"))
        config.set("discogs", "skip_auth", True)

        discogs_connection = DiscogsConnector(self.tagger_config)
        filename = discogs_connection.construct_token_file()

        if os.path.exists(filename):
            os.remove(filename)

        access_token, access_secret = discogs_connection.read_token()

        assert not access_token
        assert not access_secret

        with open(filename, 'w') as fh:
            fh.write('{0},{1}'.format("token", "secret"))

        access_token, access_secret = discogs_connection.read_token()

        assert access_token
        assert access_secret

    test_download_release.needs_network = True
    test_download_release.needs_authentication = True
    test_download_image_wo_tokens.needs_network = True
    test_download_image_with_tokens.needs_network = True
    test_download_image_with_tokens.needs_authentication = True