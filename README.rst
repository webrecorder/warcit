WARCIT
======

``warcit`` is a command-line tool to convert directories of web documents (HTML, images, etc..) into a WARC files. ``warcit`` also supports converting ZIP archives into WARCs.

Basic Usage
-----------

``warcit <prefix> <dir or file> ...``

See ``warcit -h`` for a complete list of flags and options.


For example, the following example will download a simple web site via ``wget`` (for simplicity, this retrieves one level deep only), then use ``warcit`` to convert to ``www.iana.org.warc.gz``::

   wget -l 1 -r www.iana.org/
   warcit http://www.iana.org/ ./www.iana.org/

The WARC ``www.iana.org.warc.gz`` should now have been created!


Mime Detection
~~~~~~~~~~~~~~

``warcit`` uses the ``python-magic``/libmagic if it is installed for detecting the mime-type. To disable, ``python-magic``, use ``--no-magic``
Otherwise, ``warcit`` guesses the mime-type based on the file extension


WARC Format
~~~~~~~~~~~

``warcit`` produces WARC ``resource`` reccords for all files.

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


