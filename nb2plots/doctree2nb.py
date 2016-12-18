""" Convert doctree to Jupyter notebook
"""
from __future__ import unicode_literals

import re
from textwrap import dedent

from docutils import nodes

from .ipython_shim import nbf
from . import doctree2md as d2m

# The following regular expression comes from Python source file "doctest.py".
# License for that file recorded as:
#
# Released to the public domain 16-Jan-2001, by Tim Peters (tim@python.org).
#
# This regular expression is used to find doctest examples in a
# string.  It defines three groups: `source` is the source code
# (including leading indentation and prompts); `indent` is the
# indentation of the first (PS1) line of the source code; and
# `want` is the expected output (including leading indentation).
_EXAMPLE_RE = re.compile(r'''
    # Source consists of a PS1 line followed by zero or more PS2 lines.
    (?P<source>
        (?:^(?P<indent> [ ]*) >>>    .*)    # PS1 line
        (?:\n           [ ]*  \.\.\. .*)*)  # PS2 lines
    \n?
    # Want consists of any non-blank lines that do not start with PS1.
    (?P<want> (?:(?![ ]*$)    # Not a blank line
                 (?![ ]*>>>)  # Not a line starting with PS1
                 .+$\n?       # But any other line
              )*)
    ''', re.MULTILINE | re.VERBOSE)


def parse_doctest(doctest_txt):
    txt = dedent(doctest_txt.expandtabs())
    parts = []
    for m in _EXAMPLE_RE.finditer(txt):
        indent = len(m.group('indent'))
        source_lines = m.group('source').splitlines()
        source = '\n'.join([L[indent + 4:] for L in source_lines])
        parts.append(source)
    return '\n'.join(parts)


class Translator(d2m.Translator):

    def __init__(self, document):
        d2m.Translator.__init__(self, document)
        self._in_nbplot = False
        self._init_output()

    def _init_output(self):
        self._notebook = nbf.new_notebook()

    def reset(self):
        d2m.Translator.reset(self)
        self._in_nbplot = False

    def flush_text(self):
        txt = d2m.Translator.astext(self).strip()
        if txt:
            self._add_text_block(txt)
        self.reset()

    def _add_text_block(self, txt):
        self._notebook['cells'].append(nbf.new_markdown_cell(txt))

    def astext(self):
        """ Return the document as a string """
        self.flush_text()
        return nbf.writes(self._notebook)

    def add_code_block(self, txt):
        self.flush_text()
        self._notebook['cells'].append(nbf.new_code_cell(txt))

    def visit_doctest_block(self, node):
        doctest_txt = node.astext().strip()
        if doctest_txt:
            self.add_code_block(parse_doctest(doctest_txt))
        raise nodes.SkipNode

    def visit_only(self, node):
        if node['expr'] == 'markdown':
            self.add(dedent(node.astext()) + '\n')
        raise nodes.SkipNode

    def visit_nbplot_rendered(self, node):
        self._in_nbplot = True

    def depart_nbplot_rendered(self, node):
        self._in_nbplot = False

    def visit_nbplot_not_rendered(self, node):
        raise nodes.SkipNode

    def visit_runrole_reference(self, node):
        raise nodes.SkipNode

    def visit_literal_block(self, node):
        """ A literal block may be in an nbplot container """
        if not self._in_nbplot:
            return d2m.Translator.visit_literal_block(self, node)
        self.add_code_block(node.astext())
        raise nodes.SkipNode

    def visit_mpl_hint(self, node):
        self.add_code_block('%matplotlib inline')
        raise nodes.SkipNode


class Writer(d2m.Writer):
    supported = ('jupyter',)
    """Formats this writer supports."""

    output = None
    """Final translated form of `document`."""

    def __init__(self):
        d2m.Writer.__init__(self)
        self.translator_class = Translator
