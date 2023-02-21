from abc import ABC, abstractmethod


class APIDocConverter(ABC):
    REGULAR_CLASS = 0
    INTERFACE = 1
    ABSTRACT_CLASS = 2
    ENUM = 3

    @abstractmethod
    def process(self, args):
        pass

    @abstractmethod
    def process_class(self, html_doc):
        pass

    def process_methods(self, methods, is_constructor):
        pass

    def process_fields(self, fields):
        pass
