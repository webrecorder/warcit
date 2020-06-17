import os
import sys
import datetime
import zipfile
import logging


# ============================================================================
def get_version():
    import pkg_resources
    return '%(prog)s ' + pkg_resources.get_distribution('warcit').version


# ============================================================================
def init_logging(r):
    logging.basicConfig(format='[%(levelname)s] %(message)s')
    if r.verbose:
        loglevel = logging.DEBUG
    elif r.quiet:
        loglevel = logging.ERROR
    else:
        loglevel = logging.INFO

    logging.getLogger('WARCIT').setLevel(loglevel)


# ============================================================================
class BaseTool(object):
    def __init__(self, url_prefix, inputs):
        self.logger = logging.getLogger('WARCIT')
        self.url_prefix = url_prefix
        self.inputs = inputs

    def iter_inputs(self):
        for input_ in self.inputs:
            if os.path.isdir(input_):
                for root, dirs, files in os.walk(input_):
                    for name in files:
                        filename = os.path.join(root, name)
                        path = os.path.relpath(filename, input_)
                        yield PrefixedFileInfo(self.url_prefix, path, filename, os.path.dirname(input_))

            else:
                is_zip, filename, zip_prefix = self.parse_filename(input_)

                if not is_zip:
                    if filename and not zip_prefix:
                        yield PrefixedFileInfo(self.url_prefix, os.path.basename(input_), input_)
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
                if filename.endswith('.zip') and zipfile.is_zipfile(filename):
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
    def __init__(self, url, filename, root_dir=None):
        self.url = url
        self.full_filename = filename
        self.root_dir = root_dir or ''

        self.mapfile_results = None
        self.tika_results = None

        self._init_stats()

    def _init_stats(self):
        stats = os.stat(self.full_filename)
        self.modified_dt = datetime.datetime.utcfromtimestamp(stats.st_mtime)
        self.size = stats.st_size

    def open(self):
        return open(self.full_filename, 'rb')


# ============================================================================
class PrefixedFileInfo(FileInfo):
    def __init__(self, url_prefix, path, filename, root_dir=''):
        url = path.replace(os.path.sep, '/').strip('./')
        for replace_char in '#;?:@&=+$, ': # see RFC 2396, plus '#' and ' '
            url = url.replace(replace_char, '%%%x' % ord(replace_char))
        url = url_prefix + url

        super(PrefixedFileInfo, self).__init__(url, filename, root_dir)


# ============================================================================
class ZipFileInfo(FileInfo):
    def __init__(self, url_prefix, zp, zinfo, prefix):
        self.zp = zp
        self.zinfo = zinfo
        self.internal_filename = zinfo.filename

        filename = self.internal_filename
        if prefix and filename.startswith(prefix):
            filename = filename[len(prefix):]

        url = url_prefix + filename.strip('./')

        full_filename = zp.filename + '/' + self.internal_filename

        super(ZipFileInfo, self).__init__(url, full_filename)

    def _init_stats(self):
        self.modified_dt = datetime.datetime(*self.zinfo.date_time)
        self.size = self.zinfo.file_size

    def open(self):
        return self.zp.open(self.internal_filename, 'r')


