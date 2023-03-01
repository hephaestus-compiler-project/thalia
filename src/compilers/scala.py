import os
import re

from src.compilers.base import BaseCompiler


class ScalaCompiler(BaseCompiler):
    ERROR_REGEX = re.compile(
        r"-- .*Error: (.*\.scala):\d+:\d+ -+\n((?:[^-]+))", re.MULTILINE)
    CRASH_REGEX = re.compile(r"Exception in thread(.*)")

    def __init__(self, input_name, filter_patterns=None, library_path=None):
        input_name = os.path.join(input_name, '*', '*.scala')
        super().__init__(input_name, filter_patterns, library_path)

    @classmethod
    def get_compiler_version(cls):
        return ['scalac', '-version']

    def get_compiler_cmd(self):
        extra_options = []
        if self.library_path:
            extra_options = ["-cp", self.library_path]
        return ['scalac', '-color', 'never', '-nowarn'] + extra_options + \
            [self.input_name]

    def get_filename(self, match):
        return match[0]

    def get_error_msg(self, match):
        return match[1]
