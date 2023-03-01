import re
import os

from src.compilers.base import BaseCompiler


class GroovyCompiler(BaseCompiler):
    # Match (example.groovy):(error message until empty line)
    ERROR_REGEX = re.compile(r'([a-zA-Z0-9\\/_]+.groovy):([\s\S]*?(?=\n{2,}))')

    CRASH_REGEX = re.compile(r'(.*[eE]xception)(.*)')

    STACKOVERFLOW_REGEX = re.compile(r'(.*java.lang.StackOverflowError)(.*)')

    def __init__(self, input_name, filter_patterns=None,
                 library_path=None):
        input_name = os.path.join(input_name, '*', '*.groovy')
        super().__init__(input_name, filter_patterns, library_path)

    @classmethod
    def get_compiler_version(cls):
        return ['groovyc-l', '-version']

    def get_compiler_cmd(self):
        extra_options = []
        if self.library_path:
            extra_options = ["-cp", self.library_path]
        return ['groovyc-l', '--compile-static'] + extra_options + \
            [self.input_name]

    def get_filename(self, match):
        return match[0]

    def get_error_msg(self, match):
        return match[1]

    def analyze_compiler_output(self, output):
        failed, matches = super().analyze_compiler_output(output)
        stack_overflow = re.search(self.STACKOVERFLOW_REGEX, output)
        if stack_overflow and not matches:
            self.crash_msg = output
            return None, matches

        return failed, matches
