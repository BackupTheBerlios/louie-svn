from __future__ import generators
from PyFontify import fontify
from cgi import escape

__all__ = ['htmlify', 'CSS']

def htmlify(text):
    marker = 0
    for tag, start, end, sublist in fontify(text):
        if marker < start:
            yield escape(text[marker:start])
        yield """<span class="py_%s">%s</span>""" % (tag, escape(text[start:end]))
        marker = end
    if marker < len(text):
        yield escape(text[marker:])
        
CSS = """
body {
    background-color: #FFFFFF;
    color: #000;
    font-family: Verdana;
    font-size: 12px;
    line-height: 20px;
}

tt,pre {
    font-family: Lucida Console,Courier New,Courier,monotype;
    font-size: 100%
}

pre.code {
    background-color: #EEE;
    white-space:pre;
    color:#111111;
    padding: 0 10px 0 10px;
    width:100%;
    font-size: 10pt;
}

span.py_keyword     {color: #C00000;}
span.py_string      {color: #004080;}
span.py_comment     {color: #008000;}
span.py_identifier  {color: #0000C0;}
"""

HEAD = """
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
<title>PyHtmlify Test</title>
<style type="text/css">
%s
</style>
</head>
<body>
""" % CSS

FOOT = """
</body>
</html>
"""

if __name__ == '__main__':
    import sys
    print HEAD
    for fname in sys.argv[1:]:
        print """<pre class="code">%s</pre>""" % (''.join(htmlify(file(fname).read())),)
    print FOOT
