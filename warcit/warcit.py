from argparse import ArgumentParser, RawTextHelpFormatter

import os
import sys
import datetime
import mimetypes
import logging

from warcio.warcwriter import WARCWriter
from warcio.timeutils import datetime_to_iso_date, timestamp_to_iso_date
from warcio.timeutils import pad_timestamp, PAD_14_DOWN, DATE_TIMESPLIT
from contextlib import closing


# ============================================================================
def main(args=None):
    parser = ArgumentParser(description='Convert Directories and Files to Web Archive (WARC)',
                            formatter_class=RawTextHelpFormatter)

    parser.add_argument('-V', '--version', action='version', version=get_version())

    parser.add_argument('url_prefix')
    parser.add_argument('inputs', nargs='+')

    parser.add_argument('-d', '--fixed-dt')

    parser.add_argument('-n', '--name')

    parser.add_argument('-a', '--append', action='store_true')
    parser.add_argument('-o', '--overwrite', action='store_true')

    parser.add_argument('--no-magic', action='store_true')
    parser.add_argument('--no-gzip', action='store_true')

    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')

    parser.add_argument('--index-files', default='index.html,index.htm')

    r = parser.parse_args(args=args)

    if r.append:
        mode = 'ab'
    elif r.overwrite:
        mode = 'wb'
    else:
        mode = 'xb'

    logging.basicConfig(format='%(asctime)s: [%(levelname)s]: %(message)s')
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
                  magic=not r.no_magic,
                  loglevel=loglevel,
                  mode=mode,
                  index_files=r.index_files,
                 ).run()


# ============================================================================
class WARCIT(object):
    def __init__(self, url_prefix, inputs,
                 name=None,
                 fixed_dt=None,
                 gzip=True,
                 magic=True,
                 loglevel=None,
                 mode='xb',
                 index_files=None):

        self.logger = logging.getLogger('WARCIT')
        if loglevel:
            self.logger.setLevel(loglevel)

        self.url_prefix = url_prefix.rstrip('/') + '/'
        self.inputs = inputs
        self.gzip = gzip
        self.count = 0
        self.mode = mode

        self.fixed_dt = self._set_fixed_dt(fixed_dt)

        self.name = self._make_name(name)

        if index_files:
            self.index_files = tuple(['/' + x.lower() for x in index_files.split(',')])
        else:
            self.index_files = tuple()

        self.magic = magic and self.load_magic()

    def _set_fixed_dt(self, fixed_dt):
        if not fixed_dt:
            return None

        fixed_dt = DATE_TIMESPLIT.sub('', fixed_dt)
        fixed_dt = pad_timestamp(fixed_dt, PAD_14_DOWN)
        fixed_dt = timestamp_to_iso_date(fixed_dt)
        return fixed_dt

    def load_magic(self):
        try:
            import magic
            return magic.Magic(mime=True)
        except:
            self.logger.warn('python-magic not available, guessing mime by extension only')
            return None

    def _make_name(self, name):
        """ Set WARC file name use, defaults when needed
        """

        # if no name, use basename of first input
        if not name:
            name = os.path.basename(self.inputs[0].rstrip(os.path.sep))

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
        try:
            output = open(self.name, self.mode)
        except FileExistsError as e:
            self.logger.error(e)
            self.logger.error('* Use -a/--append to append to an existing WARC file')
            self.logger.error('* Use -o/--overwrite to overwrite existing WARC file')
            return 1

        with closing(output):
            writer = WARCWriter(output, gzip=self.gzip)

            for url, filename in self.iter_inputs():
                self.make_record(writer, url, filename)

        self.logger.info('Wrote {0} resources to {1}'.format(self.count, self.name))
        return 0

    def make_record(self, writer, url, filename):
        stats = os.stat(filename)

        if self.fixed_dt:
            warc_date = self.fixed_dt
        else:
            warc_date = datetime_to_iso_date(datetime.datetime.utcfromtimestamp(stats.st_mtime))

        source_uri = 'file://' + filename

        warc_headers = {'WARC-Date': warc_date,
                        'WARC-Source-URI': source_uri,
                        'WARC-Created-Date': writer._make_warc_date()
                       }

        warc_content_type = self._guess_type(url, filename)

        with open(filename, 'rb') as fh:
            record = writer.create_warc_record(url, 'resource',
                                      payload=fh,
                                      length=stats.st_size,
                                      warc_content_type=warc_content_type,
                                      warc_headers_dict=warc_headers)

            self.count += 1
            writer.write_record(record)
            self.logger.debug('Writing {0} at {1} from {2}'.format(url, warc_date, filename))

        if url.lower().endswith(self.index_files):
            self.add_index_revisit(writer, record, url, warc_date, source_uri)

    def add_index_revisit(self, writer, record, url, warc_date, source_uri):
        index_url = url.rsplit('/', 1)[0] + '/'
        digest = record.rec_headers.get('WARC-Payload-Digest')
        self.logger.debug('Adding auto-index: {0} -> {1}'.format(index_url, url))

        revisit_record = writer.create_revisit_record(index_url, digest, url, warc_date)

        revisit_record.rec_headers.replace_header('WARC-Created-Date', revisit_record.rec_headers.get_header('WARC-Date'))
        revisit_record.rec_headers.replace_header('WARC-Date', warc_date)
        revisit_record.rec_headers.replace_header('WARC-Source-URI', source_uri)

        self.count += 1
        writer.write_record(revisit_record)

    def _guess_type(self, url, filename):
        mime = None
        if self.magic:
            mime = self.magic.from_file(filename)
        else:
            mime = mimetypes.guess_type(url.split('?', 1)[0], False)
            mime = mime[0] or 'text/html'

        return mime

    def join_url(self, path):
        return self.url_prefix + path.strip('./')

    def iter_inputs(self):
        for input_ in self.inputs:
            if os.path.isfile(input_):
                yield self.join_url(os.path.basename(input_)), input_

            elif os.path.isdir(input_):
                for root, dirs, files in os.walk(input_):
                    for name in files:
                        filename = os.path.join(root, name)
                        path = os.path.relpath(filename, input_)
                        yield self.join_url(path), filename


# ============================================================================
def get_version():
    import pkg_resources
    return '%(prog)s ' + pkg_resources.get_distribution('warcit').version


# ============================================================================
if __name__ == "__main__":   #pragma: no cover
    res = main()
    sys.exit(res)
