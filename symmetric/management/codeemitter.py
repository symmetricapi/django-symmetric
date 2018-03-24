from __future__ import print_function

class CodeEmitter(object):
    def __init__(self, fobj, indent=0):
        if isinstance(fobj, (str, unicode)):
            fobj = open(fobj, 'w')
        self.fobj = fobj
        self.indent = ' ' * indent if indent else '\t'
        self.level = 0

    def __call__(self, *lines):
        for line in lines:
            line = line.strip()
            if not line:
                print('', file=self.fobj)
            else:
                if line[0] == '}' or line[0] == ']':
                    self.level = self.level - 1
                if line.startswith('case '):
                    print((self.indent * (self.level - 1)) + line, file=self.fobj)
                else:
                    print((self.indent * self.level) + line, file=self.fobj)
                if line[-1] == '{' or line[-1] == '[':
                    self.level = self.level + 1

    def close(self):
        self.fobj.close()
