import ast

from django.conf import settings

from symmetric.functions import underscore_to_camel_case

default_token_mapping = {
    ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/', ast.Mod: '%', ast.LShift: '<<', ast.RShift: '>>', ast.BitOr: '|', ast.BitXor: '^', ast.BitAnd: '&', ast.And: '&&', ast.Or: '||',
    ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>=', ast.Is: '==', ast.IsNot: '!=',
    ast.Invert: '~', ast.Not: '!', ast.UAdd: '+', ast.USub: '-',

    ast.Attribute: ('','.'),
    ast.Str: ('"', '"'),
    ast.BinOp: ('(', ' ', ' ', ')'),
    ast.UnaryOp: ('', '(', ')'),
    ast.Compare: ('', ' ', ' '),
    ast.IfExp: ('(', ' ? ', ' : ', ')'),
    ast.Subscript: ('', '.substring(', ')'),
    ast.Slice: ('',', ')
}

js_token_mapping = default_token_mapping.copy()
js_token_mapping.update({ast.Eq: '===', ast.NotEq: '!==', ast.Is: '===', ast.IsNot: '!=='})

objc_token_mapping = default_token_mapping.copy()
objc_token_mapping.update({ast.Str: ('@"', '"'), ast.Subscript: ('[', ' substringWithRange:NSMakeRange(', ')]')})

# Bridge to objc, because substring method in swift is too complicated: http://stackoverflow.com/questions/39677330/how-does-string-substring-work-in-swift-3
swift_token_mapping = default_token_mapping.copy()
swift_token_mapping.update({ast.Subscript: ('(', ' as NSString).substring(with: NSMakeRange(', '))')})

def translate_ast(node, token_mapping=default_token_mapping):
    tokens = token_mapping.get(type(node))
    if not tokens:
        if isinstance(node, ast.BoolOp):
            code = [translate_ast(value, token_mapping) for value in node.values]
            return '(%s)' % (' %s ' % translate_ast(node.op, token_mapping)).join(code)
        elif isinstance(node, ast.expr_context):
            # Nothing for an expr_context, like Load, Store, Del, when processing an ast.Subscript
            return ''
        elif isinstance(node, ast.AST):
            value = getattr(node, node._fields[0])
            return translate_ast(value, token_mapping)
        else:
            return str(node)
    elif isinstance(tokens, (str, unicode)):
        return tokens
    else:
        code = []
        for i, token in enumerate(tokens):
            code.append(token)
            if i < len(node._fields):
                exp = getattr(node, node._fields[i], None)
                if exp:
                    code.append(translate_ast(exp, token_mapping))
        return ''.join(code)

class KeywordTransformer(ast.NodeTransformer):
    """Rename self to this. Also rename None, True, and False."""
    def __init__(self, lang):
        if lang == 'objc':
            self.id_self = 'self'
            self.id_none = 'nil'
            self.id_true = 'YES'
            self.id_false = 'NO'
        elif lang == 'swift':
            self.id_self = 'self'
            self.id_none = 'nil'
            self.id_true = 'true'
            self.id_false = 'false'
        else:
            self.id_self = 'this'
            self.id_none = 'null'
            self.id_true = 'true'
            self.id_false = 'false'
        if lang == 'js' or lang == 'es6':
            self.id_none = 'void(0)'

    def visit_Name(self, node):
        name = node.id.lower()
        if name == 'self':
            node.id = self.id_self
        elif name == 'none':
            node.id = self.id_none
        elif name == 'true':
            node.id = self.id_true
        elif name == 'false':
            node.id = self.id_false
        return node

class CamelcaseTransformer(ast.NodeTransformer):
    """Convert all names to camelcase."""
    def visit_Name(self, node):
        node.id = underscore_to_camel_case(node.id)
        return node

    def visit_Attribute(self, node):
        # Some attributes, such as those for an objdict on a JSONField might already be in camelcase, so check for an underscore first
        if node.attr.find('_') != -1:
            node.attr = underscore_to_camel_case(node.attr)
        return node

class IdTransformer(ast.NodeTransformer):
    """Convert all id attributes."""
    def __init__(self, lang):
        self.lang = lang

    def visit_Attribute(self, node):
        if type(node.attr) is str and node.attr == 'id':
            if self.lang == 'objc':
                node.attr = 'objectId'
            elif self.lang == 'java':
                node.attr = 'getObjectId()'
        return node

class CompareTransformer(ast.NodeTransformer):
    """Convert the Compare's fields to a single comparison, not compound."""
    def visit_Compare(self, node):
        node.ops = node.ops[0]
        node.comparators = node.comparators[0]
        return node

def _has_str_node(node):
    class _Visitor(ast.NodeVisitor):
        def visit_Str(self, node):
            self.found = True
    visitor = _Visitor()
    visitor.found = False
    visitor.visit(node)
    return visitor.found

class StringFormatTransformer(ast.NodeTransformer):
    """Translate a string format operation (%) directly to desired language."""
    def __init__(self, lang):
        self.lang = lang

    def visit_BinOp(self, node):
        """
        Visit for each binary operator. Formatting is determined by a Str node appearing somewhere in the left child.
        The left child may not always be a string but an expression that results in a string, so it is first transformed and translated.

        NOTE:
        The format string must be a string and not a variable containing a format string.
        Also, translating to Javascript currently doesn't support the %% format that resolves into the single % character.
        """
        if type(node.op) is ast.Mod and _has_str_node(node.left):
            left = self.visit(node.left)
            if isinstance(node.right, (ast.Str, ast.Num, ast.Attribute, ast.Name, ast.Subscript)):
                elts = [node.right]
            else:
                elts = node.right.elts
            if self.lang == 'js':
                format = translate_ast(left, js_token_mapping)
                for elt in elts:
                    format += ".replace(/%%[sdfg]/, %s)" % translate_ast(elt, js_token_mapping)
            elif self.lang == 'es6':
                format = translate_ast(left, js_token_mapping)
                for elt in elts:
                    idx = format.find('%')
                    percentf = format[idx:idx+2]
                    if percentf == '%%':
                        format = format.replace(percentf, '\u{25}', 1)
                    else:
                        format = format.replace(percentf, '${%s}' % translate_ast(elt, js_token_mapping), 1)
                format = '`%s`' % format[1:-1]
            elif self.lang == 'objc':
                format = '[NSString stringWithFormat:%s' % translate_ast(left, objc_token_mapping).replace("%s", "%@")
                for elt in elts:
                    format += ", %s" % translate_ast(elt, objc_token_mapping)
                format += ']'
            elif self.lang == 'swift':
                format = 'String(format:%s' % translate_ast(left, swift_token_mapping).replace("%s", "%@")
                for elt in elts:
                    format += ", %s" % translate_ast(elt, swift_token_mapping)
                format += ')'
            elif self.lang == 'java':
                format = 'String.format(%s' % translate_ast(left, default_token_mapping)
                for elt in elts:
                    format += ", %s" % translate_ast(elt, default_token_mapping)
                format += ')'
            return format
        else:
            return node

class SliceTransformer(ast.NodeTransformer):
    """Objective-C indexing works with location, length not start, end index."""
    def __init__(self, lang):
        self.lang = lang

    def visit_Slice(self, node):
        if (self.lang == 'objc' or self.lang == 'swift') and node.upper:
            node.upper = ast.BinOp(node.upper, ast.Sub(), node.lower)
        return node

class CastTransformer(ast.NodeTransformer):
    """Convert the float, int, and long function calls into a cast unary operation. Convert the len function call into string length."""
    def __init__(self, lang):
        self.lang = lang

    def visit_Call(self, node):
        if node.func.id == 'len':
            if self.lang == 'java':
                return ast.Attribute(node.args[0], ast.Name('length()', ast.Load()), ast.Load())
            else:
                return ast.Attribute(node.args[0], ast.Name('length', ast.Load()), ast.Load())
        else:
            if self.lang == 'js' or lang == 'es6':
                return node.args[0]
            else:
                return ast.UnaryOp('(%s)' % node.func.id, node.args[0])

def translate_code(code, lang='js', transformer=None):
    node = ast.parse(code, mode='eval')
    # Apply a bunch of transformers, note the sequence of these is important, especially for the StringFormatTransformer being last
    if transformer:
        node = transformer.visit(node)
    node = CompareTransformer().visit(node)
    if getattr(settings, 'API_CAMELCASE', True):
        node = CamelcaseTransformer().visit(node)
    if getattr(settings, 'API_RENAME_ID', True):
        node = IdTransformer(lang).visit(node)
    node = KeywordTransformer(lang).visit(node)
    node = SliceTransformer(lang).visit(node)
    node = CastTransformer(lang).visit(node)
    node = StringFormatTransformer(lang).visit(node)
    # Choose a token mapping and then perform the translation
    token_mapping = default_token_mapping
    if lang == 'js' or lang == 'es6':
        token_mapping = js_token_mapping
    elif lang == 'objc':
        token_mapping = objc_token_mapping
    elif lang == 'swift':
        token_mapping = swift_token_mapping
    return translate_ast(node, token_mapping)

def data_to_objc(data, mutable=True):
    objc = ''
    if callable(data):
        data = data()
    if data is None:
        return 'nil'
    if isinstance(data, (str, unicode)):
        return '@"%s"' % data.replace('"', '\\"')
    elif isinstance(data, bool):
        return '@YES' if data else '@NO'
    elif isinstance(data, (int, float)):
        return '@%s' % data
    elif isinstance(data, (tuple, list, set)):
        objc = '@[%s]' % ', '.join([data_to_objc(entry, mutable) for entry in data])
    elif isinstance(data, dict):
        objc = '@{%s}' % ', '.join(['%s: %s' % (data_to_objc(key, mutable), data_to_objc(data[key], mutable)) for key in data])
    if mutable:
        return '[%s mutableCopy]' % objc
    return objc

def data_to_swift(data):
    swift = ''
    if callable(data):
        data = data()
    if data is None:
        return 'nil'
    if isinstance(data, (str, unicode)):
        return '"%s"' % data.replace('"', '\\"')
    elif isinstance(data, bool):
        return 'true' if data else 'false'
    elif isinstance(data, (int, float)):
        return '@%s' % data
    elif isinstance(data, (tuple, list, set)):
        swift = '[%s]' % ', '.join([data_to_swift(entry) for entry in data])
    elif isinstance(data, dict):
        swift = '[%s]' % ', '.join(['%s: %s' % (data_to_swift(key), data_to_swift(data[key])) for key in data])
    return swift
