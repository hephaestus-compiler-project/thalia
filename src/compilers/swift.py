import re
import os

from src.compilers.base import BaseCompiler


class SwiftCompiler(BaseCompiler):
    ERROR_REGEX = re.compile(
        r'([a-zA-Z0-9\/_]+.swift):((\d+:\d+): error:[ ]+.*)(.*?(?=\n{1,}))')
    

    CRASH_REGEX = re.compile(r'^compile command failed.*')

    def __init__(self, input_name, filter_patterns=None,
                 library_path=None):
        input_name = os.path.join(input_name, '*', '*.swift')
        super().__init__(input_name, filter_patterns, library_path)

    @classmethod
    def get_compiler_version(cls):
        return ['swiftc', '-version']

    def get_compiler_cmd(self):
        extra_options = []
        if self.library_path:
            extra_options = ["-cp", self.library_path]
        return ['swiftc'] + extra_options + [self.input_name]

    def get_filename(self, match):
        return match[0]

    def get_error_msg(self, match):
        return match[1]
