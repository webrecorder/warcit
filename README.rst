WARCIT
======

``warcit`` is a command-line tool to convert on-disk directories of web documents (commonly HTML, web assets and any other data files) into an ISO standard web archive (WARC) files.

Conversion to WARC file allows for improved durability in a standardized format, and allows for any web files stored on disk to be uploaded into  `Webrecorder <https://github.com/webrecorder/webrecorder>`_, or replayed locally with `Webrecorder Player <https://github.com/webrecorder/webrecorderplayer-electron/releases>`_ or  `pywb <https://github.com/ikreymer/pywb>`_

(Many other tools also operate on WARC files, see: `Awesome Web Archiving -- Tools and Software <https://github.com/iipc/awesome-web-archiving#tools--software>`_)

WARCIT supports converting individual files, directories (including any nested directories) as well as ZIP files into WARCs.


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

Charset Detection
~~~~~~~~~~~~~~~~~

Charset detection is disabled by default, but can be enabled with the ``--charset auto`` flag.

Detection is done using the `cchardet <https://pypi.python.org/pypi/cchardet/2.1.1>`_ native chardet library.

A specific charset can also be specified, eg. ``--charset utf-8`` will add ``; charset=utf-8`` to all ``text/*`` resources.

If detection does not produce a result, or if the result is ``ascii``, no charset is added to the ``Content-Type``.


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


WARC Structure and Format
-------------------------

The tool produces ISO standard WARC 1.0 files.

A ``warcinfo`` record is added at the beginning of the WARC, unless the ``--no-warcinfo`` flag is specified.

The warcinfo record contains the full command line and warcit version::

  WARC/1.0
  WARC-Type: warcinfo
  WARC-Record-ID: ...
  WARC-Filename: example.com.warc.gz
  WARC-Date: 2017-12-05T18:30:58Z
  Content-Type: application/warc-fields
  Content-Length: ...

  software: warcit 0.2.0
  format: WARC File Format 1.0
  cmdline: warcit --fixed-dt 2011-02 http://example.com/ ./path/to/somefile.html
  
  
Each file specified or found in the directory is stored as a WARC ``resource`` record.

By default, warcit uses the file-modified date as the ``WARC-Date`` of each url.
This setting can be overriden with a fixed date time by specifying the ``--fixed-dt`` flag.
The datetime can be specified as ``--fixed-dt YYYY-MM-DDTHH:mm:ss`` or ``--fixed-dt YYYYMMDDHHmmss`` or partial date,
eg. ``--fixed-dt YYYY-MM``


The actual WARC creation time and path to the source file on disk are also stored, using the ``WARC-Created-Date``
and ``WARC-Source-URI`` extension headers, respectively.

For example, if when running ``warcit --fixed-dt 2011-02 http://example.com/ ./path/to/somefile.html``, the resulting WARC Record might look as follows::

  WARC/1.0
  WARC-Date: 2011-02-01T00:00:00Z
  WARC-Created-Date: 2017-12-05T18:30:58Z
  WARC-Source-URI: file://./path/to/somefile.html
  WARC-Type: resource
  WARC-Record-ID: ...
  WARC-Target-URI: http://www.example.com/to/somefile.html
  Content-Type: text/html
  Content-Length ...
  
  ...

Additionally, warcit adds ``revisit`` records for top-level directories if index files are present.
Index files can be specified via the ``--index-files`` flag, the default being ``--index-files=index.html,index.htm``

For example, when running:
``warcit http://example.com/ ./path/`` and there exists a file: ``./path/subdir/index.html``, warcit will create:

- a ``resource`` record for ``http://example.com/path/subdir/index.html``

- a ``revisit`` record for ``http://example.com/path/subdir/`` pointing to ``http://example.com/path/subdir/index.html``



