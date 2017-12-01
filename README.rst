WARCIT
======

Basic Usage: ``warcit <prefix> <dir or file> ...``

See ``warcit -h`` for latest options

The following example will get files via ``wget``, then use warcit to convert to ``www.iana.org.warc.gz``::

   wget -l 1 -r www.iana.org/
   python warcit/warcit.py http://www.iana.org/ ./www.iana.org/

The WARC ``www.iana.org.warc.gz`` should now have been created!

