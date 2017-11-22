from argparse import ArgumentParser, RawTextHelpFormatter
import os
import datetime
import mimetypes

from warcio.warcwriter import WARCWriter
from warcio.timeutils import datetime_to_iso_date


# ============================================================================
def main(args=None):
    parser = ArgumentParser(description='Directory to WARC file converter',
                            formatter_class=RawTextHelpFormatter)

    parser.add_argument('-V', '--version', action='version', version=get_version())

    parser.add_argument('url_prefix')
    parser.add_argument('inputs', nargs='+')

    r = parser.parse_args(args=args)
    WARCIT(r.url_prefix, r.inputs).run()


# ============================================================================
class WARCIT(object):
    def __init__(self, url_prefix, inputs, name=None, gzip=True):
        self.url_prefix = url_prefix.rstrip('/') + '/'
        self.inputs = inputs
        self.gzip = gzip

        self.name = self._make_name(name)

    def _make_name(self, name):
        """ Set WARC file name use, defaults when needed
        """

        # if no name, use basename of first input
        if not name:
            name = os.path.basename(self.inputs[0].rstrip(os.path.sep))

        if not name:
            name = 'warcit'

        # auto add extension
        if self.gzip:
            name += '.warc.gz'
        else:
            name += '.warc'

        return name

    def run(self):
        with open(self.name, 'wb') as output:
            writer = WARCWriter(output, gzip=self.gzip)

            for url, filename in self.iter_inputs():
                print('Writing {0} from {1}'.format(url, filename))
                self.make_record(writer, url, filename)

    def make_record(self, writer, url, filename):
        stats = os.stat(filename)

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

            writer.write_record(record)

    def _guess_type(self, url, filename):
        # TODO: more robust guessing
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
    return '%(prog)s ' + pkg_resources.get_distribution('warcio').version


# ============================================================================
if __name__ == "__main__":
    main()
