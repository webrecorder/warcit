import shutil
import tempfile
import os
import sys
import zipfile
import pytest
import yaml
import json

from io import BytesIO
from warcit.warcit import main
from warcit.converter import main as converter_main
from warcio import ArchiveIterator
from warcio.cli import main as warcio_main


# ============================================================================
class TestWarcIt(object):
    @classmethod
    def setup_class(cls):
        cls.root_dir = os.path.realpath(tempfile.mkdtemp())
        cls.orig_cwd = os.getcwd()
        os.chdir(cls.root_dir)

        cls.test_root = os.path.dirname(os.path.realpath(__file__))

        cls.zip_filename = os.path.join(cls.test_root, 'www.iana.org.zip')

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

    def test_warcit_overwrite_with_excludes(self, caplog):
        res = main(['http://www.iana.org/', '-o', '--exclude', '*.js', self.test_dir])
        assert res == 0

        assert 'Wrote 22 resources to www.iana.org.warc.gz' in caplog.text
        assert os.path.isfile(os.path.join(self.root_dir, 'www.iana.org.warc.gz'))

    def test_warcit_already_exists(self, caplog):
        res = main(['http://www.iana.org/', '-q', self.test_dir])
        assert res == 1

        assert 'File exists' in caplog.text

    def test_warcit_append(self):
        res = main(['-a', 'http://www.iana.org/', '-q', self.test_dir])
        assert res == 0

    def test_warcit_with_index_revisit(self, caplog, capsys):
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
        assert '"warc-target-uri": "http://www.iana.org/index.html", "content-type": "text/html; charset=windows-1258"' in out
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

    def test_transclusions(self, capsys):
        transclusions = """
transclusions:
  http://www.iana.org/_img/bookmark_icon.ico:
    - url: http://www.example.com/containing/page.html
      timestamp: 20190102030000
"""

        transclusions_file = os.path.join(self.root_dir, 'transclusions.yaml')
        with open(transclusions_file, 'wt') as fh:
            fh.write(transclusions)

        res = main(['-o', '-v', '-n', 'test-transc.warc', '--transclusions', transclusions_file, 'http://www.iana.org/', self.test_dir])

        warcio_main(['index', '-f', 'warc-type,warc-target-uri,warc-date', 'test-transc.warc.gz'])

        out, err = capsys.readouterr()

        assert '"warc-type": "resource", "warc-target-uri": "urn:embeds:http://www.example.com/containing/page.html, "warc-date": "2019-01-02T03:00:00Z"' not in out

    def test_conversions(self, caplog):
        convert_source_dir = os.path.join(self.test_root, 'convert-test')

        res = converter_main(['--dry-run', '-v', 'http://www.example.com/', convert_source_dir])

        res = converter_main(['-v', 'http://www.example.com/', convert_source_dir])

        convert_output_dir = os.path.join(self.root_dir, 'conversions')

        assert 'Converting: http://www.example.com/videos/barsandtone.flv' in caplog.text

        assert os.path.isfile(os.path.join(convert_output_dir, 'test', 'convert-test', 'videos', 'barsandtone.flv.mp4'))
        assert os.path.isfile(os.path.join(convert_output_dir, 'test', 'convert-test', 'videos', 'barsandtone.flv.webm'))
        assert os.path.isfile(os.path.join(convert_output_dir, 'test', 'convert-test', 'videos', 'barsandtone.flv.mkv'))

        TestWarcIt.conversion_results = os.path.join(convert_output_dir, 'warcit-conversion-results.yaml')

        assert os.path.isfile(self.conversion_results)

        with open(self.conversion_results) as fh:
            results = yaml.load(fh.read())

        assert len(results['conversions']['http://www.example.com/videos/barsandtone.flv']) == 4
        assert results['conversions']['http://www.example.com/videos/barsandtone.flv'][0]['url'] == 'http://www.example.com/videos/barsandtone.flv.png'
        assert results['conversions']['http://www.example.com/videos/barsandtone.flv'][1]['url'] == 'http://www.example.com/videos/barsandtone.flv.webm'
        assert results['conversions']['http://www.example.com/videos/barsandtone.flv'][2]['url'] == 'http://www.example.com/videos/barsandtone.flv.mp4'
        assert results['conversions']['http://www.example.com/videos/barsandtone.flv'][3]['url'] == 'http://www.example.com/videos/barsandtone.flv.mkv'

        for conv in results['conversions']['http://www.example.com/videos/barsandtone.flv']:
            assert conv['success'] == True

    def test_conversion_records(self, capsys):
        source_dir = os.path.join(self.test_root, 'convert-test')

        res = main(['-o', '-v', '-n', 'test-convert.warc',
                    '--conversions', self.conversion_results, 'http://www.example.com/', source_dir])

        warcio_main(['index', '-f', 'warc-type,warc-target-uri', 'test-convert.warc.gz'])

        out, err = capsys.readouterr()

        expected = """\
{"warc-type": "warcinfo"}
{"warc-type": "resource", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv"}
{"warc-type": "conversion", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv.png"}
{"warc-type": "conversion", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv.webm"}
{"warc-type": "conversion", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv.mp4"}
{"warc-type": "conversion", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv.mkv"}
"""
        assert out == expected


    def test_transclusions_and_conversions(self, capsys):
        transclusions = """
transclusions:
  http://www.example.com/videos/barsandtone.flv:
    - url: http://www.example.com/containing/page.html
      timestamp: 20190103020000
      selector: object, embed
"""

        transclusions_file = os.path.join(self.root_dir, 'transclu2.yaml')
        with open(transclusions_file, 'wt') as fh:
            fh.write(transclusions)

        source_dir = os.path.join(self.test_root, 'convert-test')

        res = main(['-o', '-v', '-n', 'test-transc2.warc', '--transclusions', transclusions_file,
                    '--conversions', self.conversion_results, 'http://www.example.com/', source_dir])

        warcio_main(['index', '-f', 'warc-type,warc-target-uri', 'test-transc2.warc.gz'])

        out, err = capsys.readouterr()

        expected = """\
{"warc-type": "warcinfo"}
{"warc-type": "resource", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv"}
{"warc-type": "conversion", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv.png"}
{"warc-type": "conversion", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv.webm"}
{"warc-type": "conversion", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv.mp4"}
{"warc-type": "conversion", "warc-target-uri": "http://www.example.com/videos/barsandtone.flv.mkv"}
{"warc-type": "resource", "warc-target-uri": "urn:embeds:http://www.example.com/containing/page.html"}
"""
        assert out == expected

    def test_validate_json_metadata(self):
        first = True
        with open('test-transc2.warc.gz', 'rb') as fh:
            for record in ArchiveIterator(fh):
                if record.rec_type == 'resource':
                    # skip first, which is original
                    if first:
                        first = False
                        continue

                    assert record.rec_headers['Content-Type'] == 'application/vnd.youtube-dl_formats+json'
                    data = record.raw_stream.read()

        assert record.rec_headers.get('WARC-Date') == '2019-01-03T02:00:00Z'

        assert record.rec_headers.get('WARC-Creation-Date') > record.rec_headers.get('WARC-Date')

        metadata = json.loads(data.decode('utf-8'))

        assert len(metadata['formats']) == 5

        assert metadata['webpage_url'] == 'http://www.example.com/containing/page.html'
        assert metadata['webpage_timestamp'] == '20190103020000'
        assert metadata['selector'] == 'object, embed'

        formats = ['png', 'webm', 'mp4', 'mkv', 'flv']
        assert [format_['ext'] for format_ in metadata['formats']] == formats
