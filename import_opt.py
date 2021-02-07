#!/usr/bin/env python3
"""Script to optimize imports to minimum memory profile."""

from collections import defaultdict
from os import walk
from os.path import normpath, join as pathjoin, splitext
from re import compile as re_compile
from sys import exit, version_info
from typing import Dict, List, Set, Tuple

REQUIRED_VERSION = (3, 9)

if version_info < REQUIRED_VERSION:
    print(f'Require python version {REQUIRED_VERSION} or higher.')
    exit()

identifiers_re = re_compile(r'''\w+''')
# import_re = re_compile(r'''import(( \w+),?)+''')


def split(line):
    """Extract all identifiers from line."""
    yield from identifiers_re.findall(line)


def extract_imports(line):
    """Extract imports from a line."""
    yield from line[len('import '):].split(',')


class ImportOptimizer:
    """Class to support optimizing imports."""
    def __init__(self, fullpath):
        self.fullpath = fullpath
        with open(fullpath) as handle:
            # Dense collection of lines in list
            self.data: List[str] = [line.rstrip() for line in handle]

        # Sparse collection of non-blank, non-comment lines
        self.lines: Dict[int, str] = {}
        self.imports: Dict[int, List[Tuple[str, str]]] = defaultdict(list)
        self.inv_imports: Dict[str, int] = {}
        self.direct_imports: Dict[str, Set[str]] = defaultdict(set)
        self.file_words: Dict[str, List[int]] = defaultdict(list)  # Lines where words occur
        self.changes = 0

    def _strip_comment_blocks(self, delimiter):
        """Find and remove string doc blocks."""
        comment_lines = []
        for i, line in enumerate(self.data):
            x = line.strip()
            if x == delimiter:
                comment_lines.append(i)
            else:
                s = x.startswith(delimiter)
                e = x.endswith(delimiter)
                if s or e:
                    comment_lines.append(i)
                if s and e:
                    comment_lines.append(i)
        if len(comment_lines) % 2 == 0:
            for i in range(0, len(comment_lines), 2):
                s, e = comment_lines[i], comment_lines[i + 1] + 1
                deletable = set(self.lines).intersection(set(range(s, e)))
                for j in deletable:
                    del self.lines[j]

    def _build_valid_lines(self):
        """Compile dict of lines that are not comments or string docs."""
        self.lines: Dict[int, str] = {
            i: line
            for i, line in enumerate(self.data)
            if line and not line.startswith('#')
        }
        self._strip_comment_blocks('"""')
        self._strip_comment_blocks("'''")

    def _build_imports(self):
        """
        Create self.imports.

        This maps import identifiers to the line they occur on.
        """
        for i, line in self.lines.items():
            if line.startswith('import '):
                for word in extract_imports(line):
                    words = word.split(' as ')
                    import_name, alias = words[0], words[-1]
                    self.imports[i].append((import_name, alias))
        self.inv_imports = {
            import_name: i
            for i, items in self.imports.items()
            for import_name, _ in items
        }

    def _build_file_words(self):
        """
        Create self.file_words.

        This maps identifiers to lines they occur on.
        """
        # Map lines to {word: [linenos]}
        for j, line in self.lines.items():
            if j not in self.imports:
                for word in split(line):
                    self.file_words[word].append(j)

    def _build_direct_imports(self):
        """Create self.direct_imports."""
        if self.imports:
            for import_line, import_items in self.imports.items():
                # For each import ...
                for import_name, alias in import_items:
                    alias_re = re_compile(f'(?<={alias})' + r'(?P<path>(\.\w+)*)(?P<fn>\.\w+)')
                    # find the places it is used that are not imports
                    alias_locs: List[int] = self.file_words.get(alias, [])
                    import_locs: List[int] = list(self.imports)
                    places_used: Set[int] = set(alias_locs).difference(import_locs)
                    for lineno in places_used:
                        s = self.data[lineno]
                        while True:
                            # Process multiple replacements on a line.
                            repl = alias_re.search(s)
                            if not repl: break
                            g = repl.groupdict()
                            path, fn = g['path'], g['fn']
                            alias_path = f'{alias}{path}'
                            alias_path_fn = f'{alias}{path}{fn}'
                            fn = fn[1:]
                            # print(f'{s=} {repl.group()=} {repl.groups()=} {repl.groupdict()=}')
                            # print(f'{import_name=} {alias_path=} {alias_path_fn=} {fn=}')
                            if alias_path != alias:
                                self.direct_imports[alias_path].add(fn)
                            else:
                                self.direct_imports[alias].add(fn)
                            s = s.replace(alias_path_fn, fn)
                        self.data[lineno] = s

    def _replace_direct_imports(self):
        """Write the direct imports."""
        for direct_import, fns in sorted(self.direct_imports.items()):
            di = f'from {direct_import} import {", ".join(sorted(fns))}'
            if direct_import in self.inv_imports:
                import_line = self.inv_imports[direct_import]
                self.data[import_line] = di
            else:
                i = max(self.imports) + 1
                self.data[i] = di + "\n" + self.data[i]

    def _rewrite_file(self):
        """Rewrite the file with changes."""
        if self.direct_imports:
            print(f'Rewriting {self.fullpath}')
            with open(self.fullpath, "w") as handle:
                handle.write("\n".join(self.data) + "\n")

    def __enter__(self):
        """Context manager enter."""
        self._build_valid_lines()
        self._build_imports()
        self._build_file_words()
        self._build_direct_imports()
        return self

    def __exit__(self, *exc):
        """Context manager exit."""
        self._replace_direct_imports()
        self._rewrite_file()
        return self


def file_iter(start_dir):
    """Iterator for creating all files in tree with normalized path."""
    for root, _, files in walk(start_dir):
        for filename in files:
            if splitext(filename)[1] == '.py':
                yield normpath(pathjoin(root, filename))


def main(start_dir='.'):
    """Main entry point."""
    for fullpath in file_iter(start_dir):
        with ImportOptimizer(fullpath):
            pass


if __name__ == '__main__':
    main()
