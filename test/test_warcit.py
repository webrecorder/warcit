import shutil
import tempfile
import os
import sys
import zipfile
import pytest

from io import BytesIO
from warcit.warcit import main
from warcio.cli import main as warcio_main


# ============================================================================
class TestWarcIt(object):
    @classmethod
    def setup_class(cls):
        cls.root_dir = os.path.realpath(tempfile.mkdtemp())
        cls.orig_cwd = os.getcwd()
        os.chdir(cls.root_dir)

        root = os.path.dirname(os.path.realpath(__file__))

        cls.zip_filename = os.path.join(root, 'www.iana.org.zip')

        with zipfile.ZipFile(cls.zip_filename) as zp:
            zp.extractall()

        cls.test_dir = os.path.join(cls.root_dir, 'www.iana.org')

    @classmethod
    def teardown_class(cls):
        os.chdir(cls.orig_cwd)
        shutil.rmtree(cls.root_dir)

    def test_warcit_new(self, caplog):
        res = main(['http://www.iana.org/', self.test_dir])
        assert res == 0

        assert 'Wrote 24 resources to www.iana.org.warc.gz' in caplog.text
        assert os.path.isfile(os.path.join(self.root_dir, 'www.iana.org.warc.gz'))

    def test_warcit_already_exists(self, caplog):
        res = main(['http://www.iana.org/', '-q', self.test_dir])
        assert res == 1

        assert 'File exists' in caplog.text

    def test_warcit_append(self):
        res = main(['-a', 'http://www.iana.org/', '-q', self.test_dir])
        assert res == 0

    def test_warcit_diff_file(self, caplog, capsys):
        res = main(['-v', '--name', 'test', '--no-gzip', 'http://www.iana.org/', self.test_dir])
        assert res == 0

        assert 'Wrote 24 resources to test.warc' in caplog.text
        assert os.path.isfile(os.path.join(self.root_dir, 'test.warc'))

        warcio_main(['index', '-f', 'warc-type,warc-target-uri,warc-date', 'test.warc'])

        out, err = capsys.readouterr()

        assert '"warc-type": "warcinfo"' in out
        assert '"warc-type": "revisit", "warc-target-uri": "http://www.iana.org/"' in out

    def test_warcit_no_revisit(self, capsys):
        res = main(['-q', '-o', '--name', 'test', '--index-files', '', '--no-gzip', 'http://www.iana.org/', self.test_dir])
        assert res == 0

        warcio_main(['index', '-f', 'warc-type,warc-target-uri,warc-date', 'test.warc'])

        out, err = capsys.readouterr()

        assert '"warc-type": "warcinfo"' in out
        assert '"warc-type": "revisit", "warc-target-uri": "http://www.iana.org/"' not in out

    def test_warcit_fixed_date(self, capsys):
        res = main(['-q', '-n', 'test', '-d', '2010-12-26T10:11:12', 'http://www.iana.org/', self.test_dir])
        assert res == 0

        warcio_main(['index', '-f', 'warc-target-uri,warc-date,content-type', 'test.warc.gz'])
        out, err = capsys.readouterr()

        assert '"warc-target-uri": "http://www.iana.org/index.html", "warc-date": "2010-12-26T10:11:12Z", "content-type": "text/html"' in out

    def test_warcit_use_charset_auto_detect(self, capsys):
        res = main(['-q', '-n', 'test3', '--charset', 'cchardet', 'http://www.iana.org/', self.test_dir])
        assert res == 0

        warcio_main(['index', '-f', 'warc-target-uri,content-type', 'test3.warc.gz'])

        out, err = capsys.readouterr()
        out = out.lower() # charset names might be uppercase or lowercase
        assert '"warc-target-uri": "http://www.iana.org/index.html", "content-type": "text/html; charset=windows-1252"' in out
        assert '"warc-target-uri": "http://www.iana.org/_css/2015.1/print.css", "content-type": "text/css; charset=utf-8"' in out

    def test_warcit_use_charset_custom(self, capsys):
        res = main(['-q', '-o', '-n', 'test3', '--charset', 'custom', 'http://www.iana.org/', self.test_dir])
        assert res == 0

        warcio_main(['index', '-f', 'warc-target-uri,content-type', 'test3.warc.gz'])

        out, err = capsys.readouterr()

        assert '"warc-target-uri": "http://www.iana.org/index.html", "content-type": "text/html; charset=custom"' in out
        assert '"warc-target-uri": "http://www.iana.org/_css/2015.1/print.css", "content-type": "text/css; charset=custom"' in out

    def test_warcit_mime_override(self, capsys):
        res = main(['-q', '-n', 'test2', '--mime-overrides=*/index.html=custom/mime', 'http://www.iana.org/', self.test_dir])
        assert res == 0

        warcio_main(['index', '-f', 'warc-target-uri,content-type', 'test2.warc.gz'])

        out, err = capsys.readouterr()

        assert '"warc-target-uri": "http://www.iana.org/index.html", "content-type": "custom/mime"' in out
        assert '"warc-target-uri": "http://www.iana.org/about/index.html", "content-type": "custom/mime"' in out

    def test_warcit_single_file_and_no_warcinfo(self, caplog, capsys):
        res = main(['-v', '--no-warcinfo', 'http://www.iana.org/', os.path.join(self.test_dir, 'index.html')])
        assert res == 0

        assert 'Wrote 2 resources to index.html.warc.gz' in caplog.text
        assert os.path.isfile(os.path.join(self.root_dir, 'index.html.warc.gz'))

        warcio_main(['index', '-f', 'warc-type,warc-target-uri', 'index.html.warc.gz'])

        out, err = capsys.readouterr()
        assert '"warc-type": "warcinfo"' not in out
        assert '"warc-target-uri": "http://www.iana.org/index.html"' in out
        assert '"warc-target-uri": "http://www.iana.org/"' in out

    def test_warcit_new_zip(self, caplog):
        res = main(['-v', 'http://', self.zip_filename])
        assert res == 0

        assert 'Wrote 24 resources to www.iana.org.zip.warc.gz' in caplog.text
        assert 'Writing "http://www.iana.org/index.html" (text/html) @ "2017-10-17T14:30:26Z" from ' in caplog.text
        assert 'www.iana.org.zip/www.iana.org/index.html"' in caplog.text
        assert os.path.isfile(os.path.join(self.root_dir, 'www.iana.org.zip.warc.gz'))

    def test_warcit_new_zip_file_path(self, caplog):
        res = main(['-o', '-v', 'http://www.iana.org/', self.zip_filename + '/www.iana.org/'])
        assert res == 0

        assert 'Wrote 24 resources to www.iana.org.warc.gz' in caplog.text
        assert 'Writing "http://www.iana.org/index.html" (text/html) @ "2017-10-17T14:30:26Z"' in caplog.text
        assert 'www.iana.org.zip/www.iana.org/index.html"' in caplog.text
        assert os.path.isfile(os.path.join(self.root_dir, 'www.iana.org.warc.gz'))

    def test_warcit_no_such_zip_prefix(self, caplog):
        res = main(['-o', '-v', 'http://www.iana.org/', self.zip_filename + '/www.example.com/'])
        assert res == 0

        assert 'Wrote 0 resources to www.example.com.warc.gz' in caplog.text
        assert os.path.isfile(os.path.join(self.root_dir, 'www.example.com.warc.gz'))

    def test_warcit_no_such_file(self, caplog):
        res = main(['-o', '-v', 'http://www.iana.org/', './foo'])
        assert res == 0

        assert '"./foo" not a valid' in caplog.text

    def test_warcit_no_such_file_2(self, caplog):
        res = main(['-o', '-v', 'http://www.iana.org/', self.zip_filename + '_nosuch'])
        assert res == 0

        assert 'www.iana.org.zip_nosuch" not a valid' in caplog.text

    def test_with_magic(self, caplog):
        pytest.importorskip('magic')
        res = main(['-q', '-o', '--use-magic', 'magic', '-n', 'test', 'http://www.iana.org/', self.test_dir])
        assert res == 0

    def test_no_magic(self, caplog):
        import sys
        sys.modules['magic'] = None

        res = main(['-q', '--use-magic', 'magic', '-n', 'test', 'http://www.iana.org/', self.test_dir])
        assert res == 1
        assert "python-magic or libmagic is not available" in caplog.text

        del sys.modules['magic']
