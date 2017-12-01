WARCIT
======

Basic Usage: ``warcit <prefix> <dir or file> ...``

See ``warcit -h`` for latest options

Usage Example
-------------

For example, the following example will download a simple web site via ``wget`` (for simplicity, this retrieves one level deep only), then use ``warcit`` to convert to ``www.iana.org.warc.gz``::

   wget -l 1 -r www.iana.org/
   warcit http://www.iana.org/ ./www.iana.org/

The WARC ``www.iana.org.warc.gz`` should now have been created!


