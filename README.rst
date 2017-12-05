WARCIT
======

``warcit`` is a command-line tool to convert directories of web documents (HTML, images, etc..) into a WARC files. ``warcit`` also supports converting ZIP archives into WARCs.
The tool enables flat files on disk to be converted into


Basic Usage
-----------

``warcit <prefix> <dir or file> ...``

See ``warcit -h`` for a complete list of flags and options.


For example, the following example will download a simple web site via ``wget`` (for simplicity, this retrieves one level deep only), then use ``warcit`` to convert to ``www.iana.org.warc.gz``::

   wget -l 1 -r www.iana.org/
   warcit http://www.iana.org/ ./www.iana.org/

The WARC ``www.iana.org.warc.gz`` should now have been created!


Mime Type Detection and Overrides
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, ``warcit`` supports the the default Python ``mimetypes`` library to determine a mime type based on a file extension.

However, it also supports using `python-magic <https://pypi.python.org/pypi/python-magic>`_ (libmagic) if available and custom mime overrides configured via the command line.

The mime detection is as follows:

1) If the filename matches an override specified via ``--mime-overrides``, use that as the mime type.

2) If ``mimetypes.guess_type()`` returns a valid mime type, use that as the mime type.

3) If ``--use-magic`` flag is specified, use the ``magic`` api to determine mime type (``warcit`` will error if ``magic`` is not available when using this flag).

4) Default to ``text/html`` if all previous attempts did not yield a mime type.


The ``--mime-overrides`` flag can be used to specify wildcard query (applied to the full url) and corresponding mime types as a comma-delimeted property list::

  warcit '--mime-overrides=*.html=text/html; charset="utf-8",image.ico=image/png' http://www.iana.org/ ./www.iana.org/

When a url ending in ``*.html`` or ``*.ico`` is encountered, the specified mime type will be used for the ``Content-Type`` header, by passing any auto-detection.


WARC Format
~~~~~~~~~~~

The tool produces ISO standard WARC 1.0 files.

A ``warcinfo`` record is added at the beginning of the WARC, unless the ``--no-warcinfo`` flag is specified.

Each encountered file is stored as a WARC ``resource`` record.

Additionally, ``warcit`` adds ``revisit`` records for top-level directories if index files are present.
Index files can be specified via the ``--index-files`` flag, the default being ``--index-files=index.html,index.htm``

For example, if a ``warcit http://example.com/ ./path/`` and there exists a ``./path/subdir/index.html``, warcit
creates:
- a ``resource`` record for ``http://example.com/path/subdir/index.html``
- a ``revisit`` record for ``http://example.com/path/subdir/`` pointing to ``http://example.com/path/subdir/index.html``


ZIP Files
~~~~~~~~~

``warcit`` also supports converting ZIP files to WARCs, including portions of zip files.

For example, if a zip file contains::

  my_zip_file.zip
  |
  +-- www.example.com/
  |
  +-- another.example.com/
  |
  +-- some_other_data/

It is possible to specify the two paths in the zip file to be converted to a WARC separately::

  warcit --name my-warc.gz http:// my_zip_file.zip/www.example.com/ my_zip_file.zip/another.example.com/

This should result in a new WARC ``my-warc.gz`` converting the specified zip file paths. The ``some_other_data`` path is not processed.


