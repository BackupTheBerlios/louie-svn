import sys, os, re
from urllib2 import urlopen, URLError
from docutils.core import publish_string
# rest is for pleasing bundlebuilder, since --package docutils fails
from docutils.readers import standalone
from docutils.writers import html4css1
from docutils.languages import en
from docutils import io, nodes, statemachine, utils
from docutils.parsers.rst import directives, states

import PyHtmlify

def pycode(name, arguments, options, content, lineno, content_offset, block_text, state, state_machine):
    attributes = {'format':'html'}
    if content:
        if options.has_key('file') or options.has_key('url'):
            error = state_machine.reporter.error(
                  '"%s" directive may not both specify an external file and '
                  'have content.' % name,
                  nodes.literal_block(block_text, block_text), line=lineno)
            return [error]
        text = '\n'.join(content)
    elif options.has_key('file'):
        if options.has_key('url'):
            error = state_machine.reporter.error(
                  'The "file" and "url" options may not be simultaneously '
                  'specified for the "%s" directive.' % name,
                  nodes.literal_block(block_text, block_text), line=lineno)
            return [error]
        source_dir = os.path.dirname(
            os.path.abspath(state.document.current_source))
        path = os.path.normpath(os.path.join(source_dir, options['file']))
        path = utils.relative_path(None, path)
        try:
            raw_file = open(path)
        except IOError, error:
            severe = state_machine.reporter.severe(
                  'Problems with "%s" directive path:\n%s.' % (name, error),
                  nodes.literal_block(block_text, block_text), line=lineno)
            return [severe]
        text = raw_file.read()
        raw_file.close()
        attributes['source'] = path
    elif options.has_key('url'):
        try:
            raw_file = urlopen(options['url'])
        except (URLError, IOError, OSError), error:
            severe = state_machine.reporter.severe(
                  'Problems with "%s" directive URL "%s":\n%s.'
                  % (name, options['url'], error),
                  nodes.literal_block(block_text, block_text), line=lineno)
            return [severe]
        text = raw_file.read()
        raw_file.close()
        attributes['source'] = options['file']
    else:
        error = state_machine.reporter.warning(
            'The "%s" directive requires content; none supplied.' % (name),
            nodes.literal_block(block_text, block_text), line=lineno)
        return [error]

    rval = '<pre class="code">' + ''.join(PyHtmlify.htmlify(text)) + '</pre>'
    return [nodes.raw('', rval, **attributes)]

pycode.arguments = (0, 0, 1)
pycode.options = {
    'file': directives.path,
    'url': directives.path,
}
pycode.content = 1
directives.register_directive('pycode', pycode)

if __name__ == '__main__':
    import os
    def do_pycode(s):
        lst = ['.. pycode::\n   :file: %s\n\n.. pycode::\n\n' % __file__] + s.splitlines(True)
        out = '    '.join(lst)
        print out
        return out

    file(os.path.splitext(__file__)[0]+'.html', 'w').write(
        publish_string(
            do_pycode(file(__file__).read()),
            reader_name='standalone',
            writer_name='html'))
