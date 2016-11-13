# -*- coding: utf-8 -*-
"""Simple Markdown writer for reStructuredText.

"""

from __future__ import unicode_literals

__docformat__ = 'reStructuredText'

from docutils import frontend, nodes, writers, languages


class Writer(writers.Writer):

    supported = ('markdown',)
    """Formats this writer supports."""

    output = None
    """Final translated form of `document`."""

    # Add configuration settings for additional Markdown flavours here.
    settings_spec = (
        'Markdown-Specific Options',
        None,
        (('Extended Markdown syntax.',
          ['--extended-markdown'],
          {'default': 0, 'action': 'store_true',
           'validator': frontend.validate_boolean}),
         ('Strict Markdown syntax. Default: true',
          ['--strict-markdown'],
          {'default': 1, 'action': 'store_true',
           'validator': frontend.validate_boolean}),))

    def __init__(self):
        writers.Writer.__init__(self)
        self.translator_class = Translator

    def translate(self):
        visitor = self.translator_class(self.document)
        self.document.walkabout(visitor)
        self.output = visitor.astext()


class IndentLevel(object):
    """ Class to hold text being written for a certain indentation level

    For example, all text in list_elements need to be indented.  A list_element
    creates one of these indentation levels, and all text contained in the
    list_element gets written to this IndentLevel.  When we leave the
    list_element, we ``write`` the text with suitable prefixes to the next
    level down, which might be the base of the document (document body) or
    another indentation level, if this is - for example - a nested list.

    In most respects, IndentLevel behaves like a list.
    """
    def __init__(self, base, prefix, first_prefix=None):
        self.base = base  # The list to which we eventually write
        self.prefix = prefix  # Text prepended to lines
        # Text prepended to first list
        self.first_prefix = prefix if first_prefix is None else first_prefix
        # Our own list to which we append before doing a ``write``
        self.content = []

    def append(self, new):
        self.content.append(new)

    def __getitem__(self, index):
        return self.content[index]

    def __len__(self):
        return len(self.content)

    def __bool__(self):
        return len(self) != 0

    def write(self):
        """ Add ``self.contents`` with current ``prefix`` and ``first_prefix``

        Add processed ``self.contents`` to ``self.base``.  The first line has
        ``first_prefix`` prepended, further lines have ``prefix`` prepended.

        Empty (all whitepsace) lines get written as bare carriage returns, to
        avoid ugly extra whitespace.
        """
        string = ''.join(self.content)
        lines = string.splitlines(True)
        if len(lines) == 0:
            return
        texts = [self.first_prefix + lines[0]]
        for line in lines[1:]:
            if line.strip() == '':  # avoid prefix for empty lines
                texts.append('\n')
            else:
                texts.append(self.prefix + line)
        self.base.append(''.join(texts))


def _make_method(to_add):
    """ Make a method that adds `to_add`

    We need this function so that `to_add` is a fresh and unique variable at
    the time the method is defined.
    """

    def method(self, node):
        self.add(to_add)

    return method


def add_pref_suff(pref_suff_map):
    """ Decorator adds visit, depart methods for prefix/suffix pairs
    """
    def dec(cls):
        # Need _make_method to ensure new variable picked up for each iteration
        # of the loop.  The defined method picks up this new variable in its
        # scope.
        for key, (prefix, suffix) in pref_suff_map.items():
            setattr(cls, 'visit_' + key, _make_method(prefix))
            setattr(cls, 'depart_' + key, _make_method(suffix))
        return cls

    return dec


def add_pass_thru(pass_thrus):
    """ Decorator adds explicit pass-through visit and depart methods
    """
    def meth(self, node):
        pass

    def dec(cls):
        for element_name in pass_thrus:
            for meth_prefix in ('visit_', 'depart_'):
                meth_name = meth_prefix + element_name
                if hasattr(cls, meth_name):
                    raise ValueError('method name {} already defined'
                                     .format(meth_name))
                setattr(cls, meth_name, meth)
        return cls

    return dec


# Doctree elements for which Markdown element is <prefix><content><suffix>
PREF_SUFF_ELEMENTS = {
    'emphasis': ('*', '*'),   # Could also use ('_', '_')
    'problematic' : ('\n\n', '\n\n'),
    'strong' : ('**', '**'),  # Could also use ('__', '__')
    'literal' : ('`', '`'),
    'math' : ('$', '$'),
    'subscript' : ('<sub>', '</sub>'),
    'superscript' : ('<sup>', '</sup>'),
}

# Doctree elements explicitly passed through without extra markup
PASS_THRU_ELEMENTS = ('document',
                      'container',
                      'target',
                      'inline')


@add_pass_thru(PASS_THRU_ELEMENTS)
@add_pref_suff(PREF_SUFF_ELEMENTS)
class Translator(nodes.NodeVisitor):

    std_indent = '    '

    def __init__(self, document):
        nodes.NodeVisitor.__init__(self, document)
        self.settings = settings = document.settings
        lcode = settings.language_code
        self.language = languages.get_language(lcode, document.reporter)
        self.head, self.body, self.foot = [], [], []
        # Warn only once per writer about unsupported elements
        self._warned = set()
        # Reset attributes modified by reading
        self.reset()
        # Lookup table to get section list from name
        self._lists = dict(head=self.head,
                           body=self.body,
                           foot=self.foot)

    def reset(self):
        """ Initialize object for fresh read """
        self.head[:] = []
        self.body[:] = []
        self.foot[:] = []

        # Current section heading level during writing
        self.section_level = 0

        # FIFO list of list prefixes, while writing nested lists.  Each element
        # corresponds to one level of nesting.  Thus ['1. ', '1. ', '* '] would
        # occur when writing items of an unordered list, that is nested within
        # an ordered list, that in turn is nested in another ordered list.
        self.list_prefixes = []

        # FIFO list of indentation levels.  When we are writing a block of text
        # that should be indented, we create a new indentation level.  We only
        # write the text when we leave the indentation level, so we can insert
        # the correct prefix for every line.
        self.indent_levels = []

        ##TODO docinfo items can go in a footer HTML element (store in self.foot).
        self._docinfo = {
            'title' : '',
            'subtitle' : '',
            'author' : [],
            'date' : '',
            'copyright' : '',
            'version' : '',
            }

    def astext(self):
        """Return the final formatted document as a string."""
        self.drop_trailing_eols()
        return ''.join(self.head + self.body + self.foot)

    def drop_trailing_eols(self):
        # Drop trailing carriage return from ends of lists
        for L in self._lists.values():
            if L and L[-1] == '\n':
                L.pop()

    def ensure_eol(self):
        """Ensure the last line in current base is terminated by new line."""
        out = self.get_current_output()
        if out and out[-1] and out[-1][-1] != '\n':
            out.append('\n')

    def get_current_output(self, section='body'):
        """ Get list or IndentLevel to which we are currently writing """
        return (self.indent_levels[-1] if self.indent_levels
                else self._lists[section])

    def add(self, string, section='body'):
        """ Add `string` to `section` or current output

        Parameters
        ----------
        string : str
            String to add to output document
        section : {'body', 'head', 'foot'}, optional
            Section of document that generated text should be appended to, if
            not already appending to an indent level.
        """
        self.get_current_output(section).append(string)

    def add_section(self, string, section='body'):
        """ Add `string` to `section` regardless of current output

        Can be useful when forcing write to header or footer.

        Parameters
        ----------
        string : str
            String to add to output document
        section : {'body', 'head', 'foot'}, optional
            Section of document that generated text should be appended to.
        """
        self._lists[section].append(string)

    def start_level(self, prefix, first_prefix=None, section='body'):
        """ Create a new IndentLevel with `prefix` and `first_prefix`
        """
        base = (self.indent_levels[-1].content if self.indent_levels else
                self._lists[section])
        level = IndentLevel(base, prefix, first_prefix)
        self.indent_levels.append(level)

    def finish_level(self):
        """ Remove most recent IndentLevel and write contents
        """
        level = self.indent_levels.pop()
        level.write()

    def visit_Text(self, node):
        text = node.astext()
        self.add(text)

    def depart_Text(self, node):
        pass

    def visit_comment(self, node):
        self.add('<!-- ' + node.astext() + ' -->\n')
        raise nodes.SkipNode

    def visit_docinfo_item(self, node, name):
        if name == 'author':
            self._docinfo[name].append(node.astext())
        else:
            self._docinfo[name] = node.astext()
        raise nodes.SkipNode

    def visit_paragraph(self, node):
        pass

    def depart_paragraph(self, node):
        self.ensure_eol()
        self.add('\n')

    def visit_math_block(self, node):
        self.add('$$\n')

    def depart_math_block(self, node):
        self.ensure_eol()
        self.add('$$\n\n')

    def visit_literal_block(self, node):
        code_type = node['classes'][1] if 'code' in node['classes'] else ''
        self.add('```' + code_type + '\n')

    def depart_literal_block(self, node):
        self.ensure_eol()
        self.add('```\n\n')

    def visit_block_quote(self, node):
        self.start_level('> ')

    def depart_block_quote(self, node):
        self.finish_level()

    def visit_section(self, node):
        self.section_level += 1

    def depart_section(self, node):
        self.section_level -= 1

    def visit_enumerated_list(self, node):
        self.list_prefixes.append('1. ')

    def depart_enumerated_list(self, node):
        self.list_prefixes.pop()

    def visit_bullet_list(self, node):
        self.list_prefixes.append('* ')

    depart_bullet_list = depart_enumerated_list

    def visit_list_item(self, node):
        first_prefix = self.list_prefixes[-1]
        prefix = ' ' * len(first_prefix)
        self.start_level(prefix, first_prefix)

    def depart_list_item(self, node):
        self.finish_level()

    def visit_subtitle(self, node):
        if isinstance(node.parent, nodes.document):
            self.visit_docinfo_item(node, 'subtitle')
            raise nodes.SkipNode

    def visit_system_message(self, node):
        # TODO add report_level
        #if node['level'] < self.document.reporter['writer'].report_level:
        #    Level is too low to display:
        #    raise nodes.SkipNode
        attr = {}
        if node.hasattr('id'):
            attr['name'] = node['id']
        if node.hasattr('line'):
            line = ', line %s' % node['line']
        else:
            line = ''
        self.add('"System Message: %s/%s (%s:%s)"\n'
            % (node['type'], node['level'], node['source'], line))

    def depart_system_message(self, node):
        pass

    def visit_title(self, node):
        if self.section_level == 0:
            self.add_section('# ', section='head')
            self._docinfo['title'] = node.astext()
        else:
            self.add((self.section_level + 1) * '#' + ' ')

    def depart_title(self, node):
        self.ensure_eol()
        self.add('\n')

    def visit_transition(self, node):
        # Simply replace a transition by a horizontal rule.
        # Could use three or more '*', '_' or '-'.
        self.add('\n---\n\n')
        raise nodes.SkipNode

    def visit_reference(self, node):
        if 'refuri' not in node:
            return
        self.add('[{0}]({1})'.format(node.astext(), node['refuri']))
        raise nodes.SkipNode

    def depart_reference(self, node):
        pass

    def unknown_visit(self, node):
        """ Warn once per instance for unsupported nodes
        """
        node_type = node.__class__.__name__
        if node_type not in self._warned:
            self.document.reporter.warning('The ' + node_type + \
                ' element is not supported.')
            self._warned.add(node_type)
        raise nodes.SkipNode
