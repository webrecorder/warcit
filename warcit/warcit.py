from argparse import ArgumentParser, RawTextHelpFormatter

import os
import sys
import datetime
import mimetypes
import logging
import zipfile
import fnmatch
import csv
import errno

from warcio.warcwriter import WARCWriter
from warcio.timeutils import datetime_to_iso_date, timestamp_to_iso_date
from warcio.timeutils import pad_timestamp, PAD_14_DOWN, DATE_TIMESPLIT
import warcio.utils
from contextlib import closing
from collections import OrderedDict
import cchardet


BUFF_SIZE = 2048


# ============================================================================
def main(args=None):
    if sys.version_info < (2, 7):  #pragma: no cover
        print('Sorry, warcit requires python >= 2.7, you are running {0}'.format(sys.version.split(' ')[0]))
        return 1

    parser = ArgumentParser(description='Convert Directories and Files to Web Archive (WARC)')

    parser.add_argument('-V', '--version', action='version', version=get_version())

    parser.add_argument('url_prefix',
                        help='''The base URL for all items to be included, including
                                protocol. Example: https://cool.website:8080/files/''')
    parser.add_argument('inputs', nargs='+',
                        help='''Paths of directories and/or files to be included in
                                the WARC file.''')

    parser.add_argument('-d', '--fixed-dt',
                        help='''Set resource date and time in YYYYMMDDHHMMSS format.
                                If not given, last modified date of files is used.''',
                        metavar='<TIMESTAMP>')

    parser.add_argument('-n', '--name',
                        help='''Base name for WARC file, appropriate extension will be
                                added automatically.''',
                        metavar='name')

    parser.add_argument('-a', '--append', action='store_true')
    parser.add_argument('-o', '--overwrite', action='store_true')


    parser.add_argument('--use-magic', '--magic',
                        help='''Select method for MIME type guessing:
                                "filename" to pick file types depending on filename extensions (default),
                                "magic" to use python-magic,
                                "tika" to use Apache Tika.''',
                        default='filename',
                        const='filename',
                        nargs='?',
                        choices=['filename', 'magic', 'tika'])

    parser.add_argument('--no-xhtml',
                        help='''If the content type "application/xhtml+xml" is detected,
                                use "text/html" instead.''',
                        action='store_true')

    parser.add_argument('-m', '--mime-overrides',
                        help='''Specify mime overrides using the format: <wildcard>=<mime>,<file>=<mime>,...
                                Example: --mime-overrides=*.php=text/html,image.img=image/png''',
                        metavar='<PATTERN=MIMETYPE>[,...]')

    parser.add_argument('--exclude',
                        help='''Comma separated wildcard patterns of file names to exclude from the WARC.
                                Example: --exclude '*.asp,*.jpeg' ''',
                        metavar='<PATTERN>,...')
    parser.add_argument('--include',
                        help='''Comma separated wildcard patterns of file names to include in the WARC.
                                If used without --exclude, only files matching the --include patterns
                                are processed. If used together with --exclude, files matching
                                --include will override exclude rules.''')


    parser.add_argument('--no-warcinfo',
                        help='''Do not include technical information about the resulting
                                WARC file's creation.''',
                        action='store_true')

    parser.add_argument('--no-gzip',
                        help='''Do not compress WARC file.''',
                        action='store_true')

    parser.add_argument('-c', '--charset',
                        help='''Set charset for text/* MIME types. 
                                Use "cchardet" for guessing via cchardet, 
                                "tika" for guessing via Apache Tika,
                                "none" (default) for not adding charset information.''',
                        metavar='{<ENCODING>, cchardet, tika, none}')

    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')

    parser.add_argument('--index-files', default='index.html,index.htm',
                        help='''Comma separated list of filenames that should be treated as
                                index files: a revisit record with their base URL (up to the
                                next slash) will be created. Default is "index.html,index.htm".''',
                        metavar='<FILENAME>[,...]')

    parser.add_argument('--mapfile',
                        help='''CSV or TSV file (detected by file extension) that maps file names to desired
                                information in the resulting WARC.
                                This feature exists to allow creating WARCs that don't neccessarily match
                                the file structure on disc.
                                A header row is expected with these possible column headers:
                                "file" -- a string with the rightmost part of the file path.
                                "URL" -- the target URL for the data contained in the file.
                                "timestamp" -- timestamp in YYYYMMDDHHMMSS format.
                                "Content-Type" -- string with desired MIME information.
                                If during the warcing process a file is encountered matching the "file" column, it will
                                be treated according to the mapfile, and an error will the thrown if the filename
                                will match a second file.''',
                        metavar='<FILENAME>')

    parser.add_argument('--log',
                        help='''Write a log file in CSV format.''',
                        metavar='<FILENAME>')


    r = parser.parse_args(args=args)

    if r.append:
        mode = 'ab'
    elif r.overwrite:
        mode = 'wb'
    else:
        mode = 'xb'

    logging.basicConfig(format='[%(levelname)s] %(message)s')
    if r.verbose:
        loglevel = logging.DEBUG
    elif r.quiet:
        loglevel = logging.ERROR
    else:
        loglevel = logging.INFO

    return WARCIT(r.url_prefix,
                  r.inputs,
                  name=r.name,
                  fixed_dt=r.fixed_dt,
                  gzip=not r.no_gzip,
                  use_magic=r.use_magic,
                  warcinfo=not r.no_warcinfo,
                  charset=r.charset,
                  loglevel=loglevel,
                  mode=mode,
                  index_files=r.index_files,
                  mime_overrides=r.mime_overrides,
                  no_xhtml=r.no_xhtml,
                  mapfile=r.mapfile,
                  include=r.include,
                  exclude=r.exclude,
                  logfile=r.log,
                  args=args,
                 ).run()


# ============================================================================
class WARCIT(object):
    def __init__(self, url_prefix, inputs,
                 name=None,
                 fixed_dt=None,
                 gzip=True,
                 use_magic=False,
                 warcinfo=True,
                 charset=None,
                 loglevel=None,
                 mode='xb',
                 index_files=None,
                 mime_overrides=None,
                 no_xhtml=False,
                 mapfile=None,
                 include=False,
                 exclude=False,
                 logfile=None,
                 args=None):

        self.logger = logging.getLogger('WARCIT')
        if loglevel:
            self.logger.setLevel(loglevel)

        self.url_prefix = url_prefix
        self.inputs = inputs
        self.gzip = gzip
        self.count = 0
        self.mode = mode

        self.warcinfo = warcinfo
        self.args = args or sys.argv
        self.args[0] = 'warcit'

        self.fixed_dt = self._set_fixed_dt(fixed_dt)

        self.name = self._make_name(name)

        if index_files:
            self.index_files = tuple(['/' + x.lower() for x in index_files.split(',')])
        else:
            self.index_files = tuple()

        self._init_mimes()
        self.mime_overrides = {}
        if mime_overrides:
            for mime in mime_overrides.split(','):
                p = mime.split('=', 1)
                self.mime_overrides[p[0]] = p[1]

        self.use_magic = use_magic
        self.no_xhtml = no_xhtml

        self.charset = charset

        self.include = None
        if include:
            self.include = [x.lower() for x in include.split(',')]
        self.exclude = None
        if exclude:
            self.exclude = [x.lower() for x in exclude.split(',')]

        self.use_tika = self.use_magic == 'tika' or self.charset == 'tika'

        self.use_mapfile = False
        if mapfile:
            self.use_mapfile = True
            self.mapfile = mapfile

        self.logfile = logfile
        self.use_logfile = False
        if self.logfile:
            self.use_logfile = True

    def _init_mimes(self):
        # add any custom, fixed mime types here
        mimetypes.add_type('image/x-icon', '.ico', True)

    def _set_fixed_dt(self, fixed_dt):
        if not fixed_dt:
            return None

        fixed_dt = DATE_TIMESPLIT.sub('', fixed_dt)
        fixed_dt = pad_timestamp(fixed_dt, PAD_14_DOWN)
        fixed_dt = timestamp_to_iso_date(fixed_dt)
        return fixed_dt

    def load_mapfile(self):
        try:
            mapfile_h = open(self.mapfile, 'r', newline='')
        except Exception as e:
            self.logger.error(e)
            self.logger.error('Mapfile {} could not be loaded.'.format(self.mapfile))
            return False

        self.filemap = []

        with closing(mapfile_h):
            try:
                if self.mapfile.lower().endswith('.tsv'):
                    csvreader = csv.DictReader(mapfile_h, dialect='excel-tab')
                else:
                    csvreader = csv.DictReader(mapfile_h, dialect='excel')
            except Exception as e:
                self.logger.error(e)
                return False

            # csv validation
            for column in csvreader.fieldnames:
                if not column in ['file', 'URL', 'Content-Type', 'timestamp']:
                    self.logger.error('Unknown column "{}" in mapfile.'.format(column))
                    return False
            if not 'file' in csvreader.fieldnames:
                self.logger.error('Missing "file" column in mapfile.')
                return False
            if not len(csvreader.fieldnames) > 1:
                self.logger.error('Mapfile needs one other column in addition to "file".')
                return False

            for row in csvreader:
                self.filemap.append(row)

            return True

    def init_logfile(self):
        try:
            self.logfile_h = open(self.logfile, 'w', newline='')
        except Exception as e:
            self.logger.error(e)
            self.logger.error('Logfile {} could not be opened for writing.'.format(self.logfile))
            return False

        self.logfile_writer = csv.DictWriter(self.logfile_h, fieldnames=['file', 'Record-Type', 
                                                                         'URL', 'timestamp',
                                                                         'Content-Type', 'mime', 
                                                                         'charset'])
        self.logfile_writer.writeheader()

        return True

    def write_logfile(self, row):
        if self.use_logfile:
            self.logfile_writer.writerow(row)

    def close_logfile(self):
        if self.use_logfile:
            self.logfile_h.close()

    def _match_mapfile(self, filename):
        for row in self.filemap:
            if filename.endswith(row['file']):
                if 'matched' in row:
                    self.logger.error('Mapfile row for "{}" matched a second time on file "{}". Please ensure file names in your mapfile are unique.'.format(row['file'], filename))
                    sys.exit(1)

                self.logger.debug('Matching row "{}" from mapfile.'.format(row['file']))
                row['matched'] = True
                return row
        return None

    def fnmatch_list(self, filename, fnmatch_list):
        filename = filename.lower()
        for pattern in fnmatch_list:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False


    def load_magic(self):
        try:
            import magic
            self.magic = magic.Magic(mime=True)
            return True
        except Exception as e:
            self.logger.error(e)
            self.logger.error('python-magic or libmagic is not available, please install or run without --use-magic flag')
            return False

    def load_tika(self):
        try:
            from tika import parser as tika_parser
            self.tika_parser = tika_parser
            self.tika_parser.from_buffer('Tika Test.')
            return True
        except Exception as e:
            self.logger.error(e)
            self.logger.error('Apache Tika not available, please set up or use another method for Content-Type or encoding detection.')
            return False

    def _make_name(self, name):
        """ Set WARC file name, use defaults when needed
        """

        # if no name, use basename of first input
        if not name:
            name = os.path.basename(self.inputs[0].replace('/', os.path.sep).rstrip(os.path.sep))

        elif not name:
            name = 'warcit'
        else:
            name = os.path.splitext(name)[0]
            name = os.path.splitext(name)[0]

        # auto add extension
        if self.gzip:
            name += '.warc.gz'
        else:
            name += '.warc'

        return name

    def run(self):
        if self.use_magic == 'magic':
            if not self.load_magic():
                return 1
        if self.use_tika:
            if not self.load_tika():
                return 1
        if self.use_mapfile:
            if not self.load_mapfile():
                return 1
        if self.use_logfile:
            if not self.init_logfile():
                return 1

        try:
            output = warcio.utils.open(self.name, self.mode)
        except OSError as e:
            # ensure only file exists handling
            if e.errno != errno.EEXIST:
                raise

            self.logger.error(e)
            self.logger.error('* Use -a/--append to append to an existing WARC file')
            self.logger.error('* Use -o/--overwrite to overwrite existing WARC file')
            return 1

        with closing(output):
            writer = WARCWriter(output, gzip=self.gzip)

            self.make_warcinfo(writer)

            for file_info in self.iter_inputs():
                self.make_record(writer, file_info)

        self.logger.info('Wrote {0} resources to {1}'.format(self.count, self.name))

        self.close_logfile()

        return 0

    def make_warcinfo(self, writer):
        if not self.warcinfo:
            return

        params = OrderedDict([('software', get_version() % dict(prog=self.args[0])),
                              ('format', 'WARC File Format 1.0'),
                              ('cmdline', ' '.join(self.args))
                             ])

        record = writer.create_warcinfo_record(self.name, params)
        writer.write_record(record)

    def make_record(self, writer, file_info):
        # process inclue/exclude rules
        if self.include and self.exclude:
            if self.fnmatch_list(file_info.full_filename, self.include):
                pass
            elif self.fnmatch_list(file_info.full_filename, self.exclude):
                return False
        elif self.include and not self.exclude:
            if not self.fnmatch_list(file_info.full_filename, self.include):
                return False
        elif self.exclude and not self.include:
            if self.fnmatch_list(file_info.full_filename, self.exclude):
                return False

        # type and encoding
        if self.use_tika:
            self.tika_results = self.tika_parser.from_file(file_info.full_filename)

        if self.use_mapfile:
            self.mapfile_results = self._match_mapfile(file_info.full_filename)

        mime_type = self._guess_type(file_info)
        encoding = self._guess_charset(mime_type, file_info)
        warc_content_type = mime_type + encoding;

        # target URL
        if self.use_mapfile and self.mapfile_results and 'URL' in self.mapfile_results:
                url = self.mapfile_results['URL']
        else:
            url = file_info.url

        # timestamp
        if self.use_mapfile and self.mapfile_results and 'timestamp' in self.mapfile_results:
            warc_date = self._set_fixed_dt(self.mapfile_results['timestamp'])
        elif self.fixed_dt:
            warc_date = self.fixed_dt
        else:
            warc_date = datetime_to_iso_date(file_info.modified_dt)

        # source from local disk
        source_uri = 'file://' + file_info.full_filename

        # write WARC entry

        warc_headers = {'WARC-Date': warc_date,
                        'WARC-Source-URI': source_uri,
                        'WARC-Creation-Date': writer._make_warc_date()
                       }


        with file_info.open() as fh:
            record = writer.create_warc_record(url, 'resource',
                                      payload=fh,
                                      length=file_info.size,
                                      warc_content_type=warc_content_type,
                                      warc_headers_dict=warc_headers)

            self.count += 1
            writer.write_record(record)

            self.logger.debug('Writing "{0}" ({1}) @ "{2}" from "{3}"'.format(url, warc_content_type, warc_date,
                                                                              file_info.full_filename))


        self.write_logfile({
            'file': file_info.full_filename,
            'Record-Type': 'Resource',
            'URL': url,
            'timestamp': warc_date,
            'Content-Type': warc_content_type,
            'mime': mime_type,
            'charset': encoding[10:] # minus '; charset='
            })


        if self.use_tika:
            del self.tika_results
        if self.use_mapfile:
            del self.mapfile_results

        # Current file serves as a directory index
        if url.lower().endswith(self.index_files):
            self.add_index_revisit(writer, record, url, warc_date, source_uri)

    def add_index_revisit(self, writer, record, url, warc_date, source_uri):
        index_url = url.rsplit('/', 1)[0] + '/'
        digest = record.rec_headers.get('WARC-Payload-Digest')
        self.logger.debug('Adding auto-index: {0} -> {1}'.format(index_url, url))

        revisit_record = writer.create_revisit_record(index_url, digest, url, warc_date)

        revisit_record.rec_headers.replace_header('WARC-Creation-Date', revisit_record.rec_headers.get_header('WARC-Date'))
        revisit_record.rec_headers.replace_header('WARC-Date', warc_date)
        revisit_record.rec_headers.replace_header('WARC-Source-URI', source_uri)

        self.count += 1
        writer.write_record(revisit_record)

        self.write_logfile({
            'file': source_uri[7:], # shave off 'file://' in beginning
            'Record-Type': 'Revisit',
            'URL': index_url,
            'timestamp': warc_date,
            })

    def _guess_type(self, file_info):
        if self.use_mapfile:
            if self.mapfile_results:
                if 'Content-Type' in self.mapfile_results:
                    return self.mapfile_results['Content-Type'].split(';')[0]

        if self.mime_overrides:
            for pattern in self.mime_overrides:
                if fnmatch.fnmatch(file_info.url, pattern):
                    return self.mime_overrides[pattern]

        mime = None

        if self.use_magic == 'filename':
            mime = mimetypes.guess_type(file_info.url.split('?', 1)[0], False)
            if len(mime) == 2:
                mime = mime[0]

        elif self.use_magic == 'magic':
            with file_info.open() as fh:
                mime = self.magic.from_buffer(fh.read(BUFF_SIZE))

        elif self.use_magic == 'tika':
            # Tika might not return a Content-Type, a string, or a list.
            # In case of a list, the first (most likely) value is chosen. 
            try:
                tika_content_type = self.tika_results['metadata']['Content-Type']
                if isinstance(tika_content_type, list):
                    tika_content_type = tika_content_type[0]

                mime = tika_content_type.split(';', 1)[0]
            except:
                mime = None

        if self.no_xhtml and mime=='application/xhtml+xml':
            mime = 'text/html'

        mime = mime or 'text/html'

        return mime

    def _guess_charset(self, content_type, file_info):
        if self.use_mapfile:
            if self.mapfile_results:
                if 'Content-Type' in self.mapfile_results and ';' in self.mapfile_results['Content-Type']:
                    return ';' + self.mapfile_results['Content-Type'].split(';')[1]

        charset = ''
        if not content_type.startswith('text/') or not self.charset:
            return ''

        if self.charset == 'cchardet':
            with file_info.open() as fh:
                result = cchardet.detect(fh.read())

            if result:
                charset = result['encoding']

            # cchardet is detecting ascii on many basic English
            # language resources, which usually
            # means that no content type was specified. In that 
            # case, do not return charset information completely,
            # as the browser will have to figure it out.
            if charset.lower() == 'ascii':
                charset = ''

        elif self.charset == 'tika':
            # Tika might not return a Content-Encoding, a string, or a list.
            # In case of a list, the first (most likely) value is chosen.
            try:
                tika_charset = self.tika_results['metadata']['Content-Encoding']
                if isinstance(tika_charset, list):
                    tika_charset = tika_charset[0]

                # Tika assigns the charset "windows-1252" with Windows line breaks,
                # or "ISO-8859-1" with Unix line breaks, if the file
                # has an unspecified 8 bit encoding. Unless this
                # encoding has been specified in the file, it should be
                # removed. If there has been any "Content-Type-Hint" been
                # found by Tika, it can be safely assumed that the detected
                # charset is not a default assignment.
                if tika_charset in ['windows-1252', 'ISO-8859-1']:
                    if not 'Content-Type-Hint' in self.tika_results['metadata']:
                        tika_charset = ''

                charset = tika_charset
            except Exception as e:
                self.logger.debug(e)
                charset = ''

        else:
            charset = self.charset

        if charset:
            return '; charset=' + charset
        else:
            return ''

    def iter_inputs(self):
        for input_ in self.inputs:
            if os.path.isdir(input_):
                for root, dirs, files in os.walk(input_):
                    for name in files:
                        filename = os.path.join(root, name)
                        path = os.path.relpath(filename, input_)
                        yield FileInfo(self.url_prefix, path, filename)

            else:
                is_zip, filename, zip_prefix = self.parse_filename(input_)

                if not is_zip:
                    if filename and not zip_prefix:
                        yield FileInfo(self.url_prefix, os.path.basename(input_), input_)
                    else:
                        self.logger.error('"{0}" not a valid file or directory'.format(input_))

                else:
                    with zipfile.ZipFile(filename) as zp:
                        for zinfo in zp.infolist():
                            if zinfo.filename.endswith('/'):
                                continue

                            if zip_prefix and not zinfo.filename.startswith(zip_prefix):
                                continue

                            yield ZipFileInfo(self.url_prefix, zp, zinfo, zip_prefix)

    def parse_filename(self, filename):
        zip_path = []
        while filename:
            if os.path.isfile(filename):
                if zipfile.is_zipfile(filename):
                    return True, filename, '/'.join(zip_path)
                else:
                    return False, filename, ''

            elif os.path.isdir(filename):
                return False, '', ''

            else:
                zip_path.insert(0, os.path.basename(filename))
                filename = os.path.dirname(filename)

        return False, '', ''


# ============================================================================
class FileInfo(object):

    def __init__(self, url_prefix, path, filename):
        url = path.replace(os.path.sep, '/').strip('./')
        for replace_char in '#;?:@&=+$, ': # see RFC 2396, plus '#' and ' '
            url = url.replace(replace_char, '%%%x' % ord(replace_char))
        self.url = url_prefix + url

        self.filename = filename

        self.full_filename = filename

        stats = os.stat(filename)
        self.modified_dt = datetime.datetime.utcfromtimestamp(stats.st_mtime)
        self.size = stats.st_size

    def open(self):
        return open(self.filename, 'rb')


# ============================================================================
class ZipFileInfo(object):
    def __init__(self, url_prefix, zp, zinfo, prefix):
        filename = zinfo.filename
        if prefix and filename.startswith(prefix):
            filename = filename[len(prefix):]

        self.full_filename = zp.filename + '/' + zinfo.filename

        self.url = url_prefix + filename.strip('./')
        self.filename = zinfo.filename
        self.zp = zp

        self.modified_dt = datetime.datetime(*zinfo.date_time)
        self.size = zinfo.file_size

    def open(self):
        return self.zp.open(self.filename, 'r')



# ============================================================================
def get_version():
    import pkg_resources
    return '%(prog)s ' + pkg_resources.get_distribution('warcit').version


# ============================================================================
if __name__ == "__main__":   #pragma: no cover
    res = main()
    sys.exit(res)
