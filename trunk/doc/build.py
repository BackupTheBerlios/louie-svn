"""Build documentation from source."""

import logging as log
import os
import sys
import zipfile

import elementtree.ElementTree as etree
import dispatch
from dispatch.strategy import default
from docutils.writers import html4css1
from docutils.core import publish_parts
from elementtree.HTMLTreeBuilder import HTMLTreeBuilder
import py

from support import docpytils

from louie import version


Document = object()
Slideshow = object()


STYLESHEET_PATH = str(py.path.local(__file__).dirpath().join(
    'support', 'default.css'))
        

SUPPORT_EXTS = [
    'jpg',
    'png',
    'zip',
    ]


TOPLEVEL_INDEX = """
=================
 Top-Level Index
=================

%(docList)s
"""


BOILERPLATE_HEADING = '''
<div>
  <div>
    <div style="float: right">
      <a href="%(topLevelHref)s">[Top-Level Index]</a>
      <br /><a href="http://developer.berlios.de/projects/louie/">
        Berlios.de Project Page</a>
      <br /><a href="http://developer.berlios.de" title="BerliOS Developer">
        <img src="http://developer.berlios.de/bslogo.php?group_id=5432"
             width="124px" height="32px" border="0" alt="BerliOS Developer Logo" /></a>
    </div>

    <p><b>Louie</b> <br />Version %(VERSION)s</p>

  </div>
  <hr />
</div>
'''


def addBoilerplate(htmlStr, relPath):
    """Add boilerplate to an HTML string.

    - `htmlStr`: The HTML string to transform.
    - `relPath`: File's relative path within the doc hierarchy.

    Returns the transformed HTML string.
    """
    parts = relPath.split('/')
    topLevelHref = '../' * (len(parts) - 1) + 'index.html'

    parser = HTMLTreeBuilder()
    parser.feed(htmlStr)
    root = parser.close()
    body = root.find('body')
    VERSION = version.VERSION
    heading = etree.fromstring(BOILERPLATE_HEADING % vars())
    body.insert(0, heading)
    return etree.tostring(root)


class Directory(object):
    def __init__(self, base, source):
        self.base = base
        self.source = source
        self.relPath = source.relto(base).replace('\\', '/')

        self.title = None
        self.subtitle = None
        titlePath = source.join('title')
        if titlePath.check(file=True):
            self.title = titlePath.read().strip()


class RestDoc(object):

    def __init__(self, base, source, dest):
        self.base = base
        self.source = source
        self.dest = dest

        self.relPath = None
        self.title = None
        self.subtitle = None

        self._setType()

    def _setType(self):
        """Set the type of the document based on its contents."""
        contents = self.source.read()
        if '.. slideshow' in contents:
            self.type = Slideshow
        else:
            self.type = Document
        
    [dispatch.generic()]
    def transform(self):
        """Transform a reST-formatted file to HTML."""

    [transform.when("self.type is Document")]
    def transform(self):
        log.info('Transforming Document %s', self.source.relto(self.base))

        self.dest.dirpath().ensure(dir=True)

        relto = self.source.dirpath().relto(self.base)
        if relto:
            relto += '/'
        self.relPath = relto + self.dest.basename
        self.relPath = self.relPath.replace('\\', '/')

        writer = html4css1.Writer()
        parts = publish_parts(
            source=self.source.read(), writer=writer,
            settings_overrides={'compact_lists': False,
                                'embed_stylesheet': True,
                                'stylesheet': STYLESHEET_PATH,
                                },
            )
        self.dest.write(addBoilerplate(parts['whole'], self.relPath))

        self.title = parts['title']
        self.subtitle = parts['subtitle']


def main(argv):
    def usage():
        print '%s [-v] [-f] DEST-DIR' % argv[0]
        print '  -v  Verbose'
        print '  -f  Remove existing DEST-DIR if exists'
        return 1
        
    if not (2 <= len(argv) <= 4):
        return usage()

    if '-v' in argv:
        log.root.setLevel(20)

    force = False
    if '-f' in argv:
        force = True

    dest = argv[-1]

    # Find paths.
    basePath = py.path.local(argv[0]).dirpath().dirpath()
    docPath = basePath.join('doc')
    destPath = py.path.local(dest)
    log.info('Source path: %s', docPath)
    log.info('Destination path: %s', destPath)

    # Make sure destination is empty.
    if force and destPath.check():
        destPath.remove(rec=True)
    destPath.ensure(dir=True)
    if len(destPath.listdir()):
        log.error('Destination path is not empty.')
        return usage()

    # Copy support files first, in case a presentation relies upon
    # them.
    for ext in SUPPORT_EXTS:
        for path in docPath.visit('*.%s' % ext):
            # Ignore .svn/* files.
            if '.svn' in str(path):
                continue

            # Ignore support files.
            if path.relto(docPath).startswith('support'):
                continue

            # Ignore destination paths that are children of doc.
            if path.relto(destPath):
                continue

            rel = path.relto(docPath)
            log.info('Copying support file %s', rel)
            dest = destPath.join(rel).dirpath()
            dest.ensure(dir=True)
            path.copy(dest)

    # Transform all documents.
    docs = []
    for txtSrc in docPath.visit('*.txt'):
        
        # Ignore .svn/* files.
        if '.svn' in str(txtSrc):
            continue

        # Ignore support files.
        if txtSrc.relto(docPath).startswith('support'):
            continue
        
        # Ignore destination paths that are children of doc.
        if txtSrc.relto(destPath):
            continue

        # Find destination path.
        rel = txtSrc.relto(docPath)
        txtDest = destPath.join(rel).new(ext='html')

        # Create and transform.
        doc = RestDoc(docPath, txtSrc, txtDest)
        doc.transform()
        docs.append(doc)

    # Find all directories that have titles.
    for dirPath in docPath.visit():
        if dirPath.check(dir=True):
            direc = Directory(docPath, dirPath)
            if direc.title:
                docs.append(direc)

    # Create top-level index.
    log.info('Writing top-level index.')
    docs = [(doc.relPath, doc) for doc in docs]
    docs.sort()

    docList = []
    for relPath, doc in docs:
        title = doc.title
        if doc.subtitle:
            title = "%s (%s)" % (title, doc.subtitle)
        if isinstance(doc, RestDoc):
            bullet = '* `%s <%s>`__' % (title, doc.relPath)
        else:
            bullet = '* ' + title

        parts = doc.relPath.split('/')
        indent = '  ' * len(parts)

        docList.append(indent + bullet)

    docList = '\n\n'.join(docList)

    indexSrc = TOPLEVEL_INDEX % vars()
    
    indexPath = destPath.join('index.html')
    writer = html4css1.Writer()
    parts = publish_parts(
        source=indexSrc, writer=writer,
        settings_overrides={'compact_lists': False,
                            'embed_stylesheet': True,
                            'stylesheet': STYLESHEET_PATH,
                            },
        )
    indexPath.write(addBoilerplate(parts['whole'], ''))

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

