from collections import defaultdict
import itertools
from typing import Iterable

from src import utils
from src.ir import (types as tp, type_utils as tu, groovy_types as gt,
                    scala_types as sc)
from src.ir.builtins import BuiltinFactory
from src.generators.api import api_graph as ag


NON_ERASURE = 0
ERASURE = 1


def get_type_variables(t: tp.Type, bt_factory) -> Iterable[tp.TypeParameter]:
    if t.is_type_var():
        return [(t, False)]
    if t.is_wildcard() and t.is_contravariant() and t.bound.is_type_var():
        return [(t, True)]
    if t.is_wildcard():
        return [(t, False) for t in t.get_type_variables(bt_factory).keys()]

    type_vars = []
    if t.is_parameterized():
        for targ in t.type_args:
            type_vars.extend(get_type_variables(targ, bt_factory))
    return type_vars


class FaultInjection():
    OUT = -1

    def __init__(self, api_graph: ag.APIGraph,
                 bt_factory: BuiltinFactory):
        self.api_graph = api_graph
        self.bt_factory = bt_factory
        self.excluded_types = {
            "groovy": [
                self.bt_factory.get_string_type(),
                self.bt_factory.get_boolean_type(),
                gt.Array.new([gt.Object])
            ],
            "scala": [
                sc.AnyRef,
                sc.Any,
                tp.SimpleClassifier("scala.Singleton")
            ]
        }

    def is_type_excluded(self, t: tp.Type) -> bool:
        excluded_types = self.excluded_types.get(
            self.bt_factory.get_language(), []
        )
        return t in excluded_types

    def compute_markings(self, t: tp.Type, api: ag.APINode):
        """
        Compute the position of every type parameter in the signature of the
        given API.
        """
        markings = defaultdict(set)
        ret_type = self.api_graph.get_output_type(api)
        for type_param in t.t_constructor.type_parameters:
            type_variables = get_type_variables(ret_type, self.bt_factory)
            if type_param in {t for t, _ in type_variables}:
                markings[type_param].add(self.OUT)

            for i, param in enumerate(api.parameters):
                type_variables = get_type_variables(param.t, self.bt_factory)
                if type_param in {k for k, v in type_variables
                                  if not v}:
                    markings[type_param].add(i)
        return markings

    def _get_incorrect_variances(self, marks):
        if marks == {self.OUT}:
            # Out position only
            valid_variance = tp.Covariant
        elif self.OUT not in marks:
            # In position only
            valid_variance = tp.Contravariant
        else:
            valid_variance = None
        # XXX: Consider adding Invariant?
        variances = {tp.Covariant, tp.Contravariant}
        return [v for v in variances if v != valid_variance]

    def _create_wildcard_type_arg(self, type_arg, marks, parameters):
        variances = self._get_incorrect_variances(marks)
        variance = utils.random.choice(variances)
        bound = type_arg
        if utils.random.bool() and not all(parameters[m].is_wildcard() and
                                           parameters[m].is_covariant()
                                           for m in marks):
            # We handle cases like:
            # m(Foo<out T>): in this case the receiver should not be covariant.
            bound = self.api_graph.get_random_type()
        new_type_arg = tp.WildCardType(bound=bound,
                                       variance=variance)
        return new_type_arg

    def tweak_type_arguments(self, t: tp.ParameterizedType, markings,
                             parameters):
        new_type_args = []
        changed = False
        for i, type_arg in enumerate(t.type_args):
            if type_arg.is_wildcard() and type_arg.is_invariant():
                new_type_args.append(type_arg)
                continue

            type_param = t.t_constructor.type_parameters[i]
            marks = markings[type_param]
            if not marks:
                # The type parameter is not part of the API signature.
                new_type_args.append(type_arg)
                continue

            if not type_arg.is_wildcard() and utils.random.bool():
                new_type_args.append(self._create_wildcard_type_arg(
                    type_arg, marks, parameters))
                changed = True
                continue
            new_type_arg = tu.find_irrelevant_type(
                type_arg, self.api_graph.get_reg_types(), self.bt_factory,
                excluded_types=[]
            )
            if not new_type_arg:
                new_type_args.append(type_arg)
                continue
            new_type_args.append(new_type_arg)
            changed = True

        if changed:
            etype = t.t_constructor.new(new_type_args)
            subtypes = self.api_graph.subtypes_of_parameterized_inheritance(
                etype)
            return (
                utils.random.choice(list(subtypes))
                if subtypes and utils.random.bool()
                else etype
            )
        return None

    def inject_fault_receiver(self, encoding):
        assert len(encoding.receivers)
        receiver = list(encoding.receivers)[0]
        if receiver == self.api_graph.EMPTY:
            # There's no receiver
            return None

        if receiver.is_type_var() and receiver.bound:
            receiver = receiver.bound

        if not receiver.is_parameterized():
            # We don't inject fault in non-parametric receivers.
            return None
        markings = self.compute_markings(receiver, encoding.api)
        if all(not v for v in markings.values()):
            # The type parameters of receiver are not used in the signature
            # of the API. So we don't inject any fault here.
            return None
        if self.is_type_excluded(receiver):
            return None
        parameters = list(itertools.product(*encoding.parameters))
        return self.tweak_type_arguments(receiver, markings,
                                         parameters[0])

    def inject_fault_ret_type(self, encoding):
        assert len(encoding.returns) == 1
        ret_type = list(encoding.returns)[0]
        types = [t for t in self.api_graph.get_reg_types()
                 if not self.is_type_excluded(t)]
        irr_type = tu.find_irrelevant_type(ret_type, types,
                                           self.bt_factory,
                                           subtypes_irrelevant=True)
        return irr_type

    def _mark_abstract_param_types(self, parameters, encoding):
        marked_parameters = {}
        for i, param in parameters.items():
            formal_t = encoding.api.parameters[i]
            type_vars = get_type_variables(formal_t.t, self.bt_factory)
            if not type_vars:
                marked_parameters[i] = (param, ERASURE)
            ret_type = self.api_graph.get_output_type(encoding.api)
            ret_type_vars = get_type_variables(ret_type, self.bt_factory)
            if any(param_type_var in ret_type_vars
                   for param_type_var in type_vars):
                erasure = ERASURE
            else:
                erasure = NON_ERASURE
            marked_parameters[i] = (param, erasure)
        return marked_parameters

    def inject_fault_parameters(self, encoding):
        parameters = list(itertools.product(*encoding.parameters))
        assert len(parameters) == 1
        parameters = {i: p for i, p in enumerate(parameters[0])
                      if (p != self.bt_factory.get_any_type() and
                          p != self.api_graph.EMPTY and
                          not self.is_type_excluded(p))
                      }
        if not parameters:
            return None
        params2err = utils.random.sample(
            parameters.keys(), utils.random.integer(1, len(parameters)))
        err_params = {}
        for param_index in params2err:
            param_t = parameters[param_index]
            irr_t = tu.find_irrelevant_type(param_t,
                                            self.api_graph.get_reg_types(),
                                            self.bt_factory,
                                            supertypes_irrelevant=True)
            err_params[param_index] = irr_t
        new_params = []
        for i in range(len(encoding.parameters)):
            if i in err_params:
                new_params.append(err_params[param_index])
            else:
                new_params.append(next(iter(encoding.parameters[i])))
        return new_params

    def compute_incorrect_typing_sequences(self, encoding):
        """ Computes incorrect typing sequences. """
        rec_set = {self.inject_fault_receiver(encoding)
                   for _ in range(5)}
        param_set = self.inject_fault_parameters(encoding)
        if param_set:
            param_set = [{p} for p in param_set]
        ret_set = {self.inject_fault_ret_type(encoding)}
        gen_a, gen_b = None, None
        if None not in rec_set:
            gen_a = itertools.product(rec_set, *encoding.parameters,
                                      encoding.returns)
        if param_set:
            gen_b = itertools.product(encoding.receivers, *param_set,
                                      encoding.returns)
        gen_c = itertools.product(encoding.receivers, *encoding.parameters,
                                  ret_set)
        generators = [gen_a, gen_b, gen_c]
        return itertools.chain(*[g for g in generators if g])
