from __future__ import absolute_import

import yaml
import logging
import re
import os
import subprocess

from collections import defaultdict
from argparse import ArgumentParser, RawTextHelpFormatter

from warcit.base import BaseTool, get_version, init_logging, FileInfo
from warcio.timeutils import timestamp_now


logger = logging.getLogger('WARCIT')

RESULTS_FILE = 'warcit-conversion-results.yaml'


# ============================================================================
def main(args=None):
    parser = ArgumentParser(description='Perform format conversion based on ' +
                                        'manifest (in preparation for WARC storage)')

    parser.add_argument('-V', '--version', action='version', version=get_version())

    parser.add_argument('--dry-run', action='store_true')

    parser.add_argument('--output-dir', help='Root output directory for conversions')

    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')

    parser.add_argument('--results', help='YAML file to write conversion results to',
                        default=RESULTS_FILE)

    parser.add_argument('--url-prefix',
                        help='''The base URL for all items to be included, including
                                protocol. Example: https://cool.website:8080/files/''')

    parser.add_argument('manifest', help='Conversion manifest YAML file')

    parser.add_argument('inputs', nargs='+',
                        help='''Paths of directories and/or files to be checked for conversion''')

    r = parser.parse_args(args=args)

    init_logging(r)

    converter = FileConverter(manifest_filename=r.manifest,
                              inputs=r.inputs,
                              url_prefix=r.url_prefix,
                              output_dir=r.output_dir,
                              results_file=r.results)

    converter.convert_all(dry_run=r.dry_run)


# ============================================================================
class FileConverter(BaseTool):
    def __init__(self, manifest_filename, inputs,
                 url_prefix=None,
                 output_dir=None,
                 results_file=None):

        with open(manifest_filename, 'rt') as fh:
            manifest = yaml.load(fh.read())

        self.convert_stdout = manifest.get('convert_stdout')

        self.output_dir = output_dir or manifest['output_dir']
        if not self.output_dir:
            raise Exception('--output-dir param or output_dir setting in manifest is required')

        url_prefix = url_prefix or manifest['url_prefix']
        if not url_prefix:
            raise Exception('--url_prefix param or url_prefix setting in manifest is required')

        self.results_file = results_file or RESULTS_FILE

        self.results = defaultdict(list)

        super(FileConverter, self).__init__(url_prefix=url_prefix,
                                            inputs=inputs)

        for file_type in manifest['file_types']:
            file_type['rx'] = re.compile(file_type['rx'])

        self.file_types = manifest['file_types']

    def write_results(self):
        filename = os.path.join(self.output_dir, self.results_file)

        self._ensure_dir(filename)

        try:
            with open(filename, 'rt') as fh:
                root = yaml.load(fh.read())
        except:
            root = {}

        if 'conversions' not in root:
            root['conversions'] = {}

        conversions = root['conversions']
        conversions.update(self.results)

        with open(filename, 'wt') as fh:
            fh.write(yaml.dump(root, default_flow_style=False))

    def convert_all(self, dry_run=False):
        stdout = None
        if self.convert_stdout:
            stdout = open(self.convert_stdout, 'wt')

        try:
            for file_info in self.iter_inputs():
                self.convert_file(file_info,
                                  dry_run=dry_run,
                                  convert_stdout=stdout,
                                  convert_stderr=stdout)

                if not dry_run:
                    self.write_results()

        finally:
            if stdout:
                stdout.close()

    def convert_file(self, file_info, dry_run=False, convert_stdout=None, convert_stderr=None):
        for file_type in self.file_types:
            if file_type['rx'].match(file_info.url):
                self.logger.info('Converting: ' + file_info.url)

                for conversion in file_type['conversion_rules']:
                    if conversion.get('skip'):
                        self.logger.debug('Skipping: ' + conversion['name'])
                        continue

                    output = self.get_output_filename(file_info.full_filename + '.' + conversion['ext'])
                    self.logger.debug('Output Filename: ' + output)
                    command = conversion['command'].format(input=file_info.full_filename,
                                                           output=output)

                    self.logger.debug('*** Running Command: ' + str(command.split(' ')))
                    if dry_run:
                        continue

                    res = subprocess.call(command.split(' '), shell=False,
                                          stdout=convert_stdout,
                                          stderr=convert_stderr)

                    self.logger.debug('Exit Code: {0}'.format(res))

                    result = {'url': file_info.url + '.' + conversion['ext'],
                              'output': output,
                              'metadata': conversion,
                              'type': 'conversion',
                              'success': (res == 0),
                             }

                    self.results[file_info.url].append(result)

    def get_output_filename(self, convert_filename, dry_run=False):
        full_path = os.path.abspath(os.path.join(self.output_dir, convert_filename))

        if not dry_run:
            self._ensure_dir(full_path)

        return full_path

    def _ensure_dir(self, full_path):
        try:
            os.makedirs(os.path.dirname(full_path))
        except OSError as oe:
            if oe.errno != 17:
                self.logger.error(str(oe))


# ============================================================================
class ConversionSerializer(object):
    def __init__(self, results_filename):
        with open(results_filename, 'rt') as fh:
            results = yaml.load(fh.read())

        self.conversions = results.get('conversions', {})

    def find_conversions(self, url):
        matched = self.conversions.get(url)
        if not matched:
            return

        for conv in matched:
            if not conv.get('success'):
                logger.warn('Skipping unsuccessful conversion: {0}'.format(conv.get('output')))
                continue

            file_info = FileInfo(url=conv['url'], filename=conv['output'])
            yield file_info, conv.get('type', 'conversion'), conv.get('metadata')


# ============================================================================
class TransclusionSerializer(object):
    def __init__(self, transclusions_filename, conversions=None):
        with open(transclusions_filename, 'rt') as fh:
            results = yaml.load(fh.read())

        self.transclusions = results.get('transclusions', {})

        if conversions:
            self.conversion_serializer = ConversionSerializer(conversions)
        else:
            self.conversion_serializer = None

    def find_transclusions(self, url, orig_mime=None):
        for tc in self.transclusions.get(url, []):
            if 'url' not in tc:
                logger.warn('Skipping, no url for transclusion for {0}'.format(url))
                continue

            yield self.get_transclusion_metadata(tc, url, orig_mime)

    def get_transclusion_metadata(self, tc, url, orig_mime=None):
        contain_url = tc['url']
        contain_ts = tc.get('timestamp') or timestamp_now()
        contain_ts = str(contain_ts)

        if tc.get('metadata_file'):
            with open(tc.get('metadata_file'), 'rt') as fh:
                metadata = fh.read()

        else:
            all_metadata = {}
            all_metadata['webpage_url'] = contain_url
            all_metadata['webpage_timestamp'] = contain_ts
            formats = []

            if self.conversion_serializer:
                for file_info, _, metadata in self.conversion_serializer.find_conversions(url):
                    metadata['url'] = file_info.url
                    metadata['original_url'] = url
                    formats.append(metadata)

            orig_format = {'url': url,
                           'ext': url.rsplit('.')[-1],
                           'original': True,
                          }

            if orig_mime:
                orig_format['mime'] = orig_mime

            formats.append(orig_format)

            all_metadata['formats'] = formats

        return contain_url, contain_ts, all_metadata


# ============================================================================
if __name__ == "__main__":   #pragma: no cover
    res = main()
    sys.exit(res)
