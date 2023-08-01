import re

from src.compilers.base import BaseCompiler


class KotlinCompiler(BaseCompiler):
    ERROR_REGEX = re.compile(
        r'([a-zA-Z0-9\/_]+.kt):\d+:\d+:[ ]+error:[ ]+(.*)')
    CRASH_REGEX = re.compile(
        r'(org\.jetbrains\..*)\n(.*)',
        re.MULTILINE
    )

    def __init__(self, input_name, filter_patterns=None, library_path=None):
        super().__init__(input_name, filter_patterns, library_path)

    @classmethod
    def get_compiler_version(cls):
        return ['kotlinc', '-version']

    def get_compiler_cmd(self):
        extra_options = []
        if self.library_path:
            extra_options = ["-cp", self.library_path]
        return ['kotlinc', self.input_name, '-include-runtime', '-d',
                'program.jar',
                '-Xnullability-annotations=@javax.annotation:ignore',
                '-opt-in',
                'kotlin.io.encoding.ExperimentalEncodingApi',
                '-opt-in',
                'kotlin.contracts.ExperimentalContracts',
                '-opt-in',
                'kotlin.ExperimentalStdlibApi'
                ] + extra_options

    def get_filename(self, match):
        return match[0]

    def get_error_msg(self, match):
        return match[1]
