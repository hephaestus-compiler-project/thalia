from typing import NamedTuple, List

from src.ir import types as tp


class Field(NamedTuple):
    name: str
    cls: str

    def __str__(self):
        return self.get_class_name() + "." + self.get_name()

    def __hash__(self):
        return hash((self.name, self.cls))

    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self.name == other.name and
                self.cls == other.cls)

    def get_class_name(self):
        return self.cls

    def get_name(self):
        return self.name.rsplit(".", 1)[-1]

    @property
    def class_(self):
        return self.get_class_name()

    @property
    def api_name(self):
        return self.get_name()


class Variable(NamedTuple):
    name: str

    def __str__(self):
        return self.get_name()

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self.name == other.name)

    def get_name(self):
        return self.name.rsplit(".", 1)[-1]

    @property
    def api_name(self):
        return self.get_name()


class Parameter(NamedTuple):
    t: tp.Type
    variable: bool

    def __str__(self):
        return "{t!s}{suffix!s}".format(
            t=str(self.t),
            suffix="*" if self.variable else ""
        )

    __repr__ = __str__

    def __hash__(self):
        return hash((self.t, self.variable))


class Method(NamedTuple):
    name: str
    cls: str
    parameters: List[Parameter]
    type_parameters: List[tp.TypeParameter]
    metadata: dict #swift: cannot reference mutating methods

    def __str__(self):
        type_parameters_str = ""
        if self.type_parameters:
            type_parameters_str = "<{}>".format(",".join(
                [str(tpa) for tpa in self.type_parameters]))
        return "{cls!s}.{type_params!s}{name!s}({args!s})".format(
            cls=self.get_class_name(),
            type_params=type_parameters_str,
            name=self.get_name(),
            args=", ".join(str(p) for p in self.parameters)
        )

    __repr__ = __str__

    def __hash__(self):
        return hash((self.name, self.cls, tuple(self.parameters),
                     tuple(self.type_parameters), str(self.metadata)))

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.name == other.name and
            self.cls == other.cls and
            self.parameters == other.parameters and
            self.type_parameters == other.type_parameters and
            self.metadata == other.metadata
        )

    def get_class_name(self):
        return self.cls

    def get_name(self):
        return self.name.rsplit(".", 1)[-1]

    @property
    def class_(self):
        return self.get_class_name()

    @property
    def api_name(self):
        return self.get_name()


class NamedParameter(NamedTuple):
    t: tp.Type
    variable: bool
    name: str
    
    def __str__(self):
        return "{t!s}{suffix!s}".format(
            t=str(self.t),
            suffix="*" if self.variable else ""
        )

    __repr__ = __str__

    def __hash__(self):
        return hash((self.t, self.variable))
    
class Constructor(NamedTuple):
    name: str
    parameters: List[NamedParameter] 
    metadata: dict

    def __str__(self):
        return "{cls!s}.{name!s}({args!s})".format(
            cls=self.get_class_name(),
            name=self.get_name(),
            args=", ".join(str(p) for p in self.parameters)
        )

    __repr__ = __str__

    def __hash__(self):
        return hash((self.name, tuple(self.parameters), str(self.metadata)))

    def __eq__(self, other):
        return (
            self.__class__ == other.__class__ and
            self.name == other.name and
            self.parameters == other.parameters and
            self.metadata == other.metadata
        )

    def get_class_name(self):
        return self.name

    def get_name(self):
        return self.name.rsplit(".", 1)[-1]

    @property
    def class_(self):
        return self.get_class_name()

    @property
    def api_name(self):
        return self.get_name()
