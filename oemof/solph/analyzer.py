
"""
This module uses the visitor pattern.
All visited elements either call a default function "analyze" or an
element-specific function "analyze_<element>". Each analyzer must contain
functions for every specified element. If function does not exist, again a
default function is called.
"""

from warnings import warn
from collections import OrderedDict, abc
from oemof.network import Node, Bus
from oemof.outputlib import views


def init(results=None, param_results=None, iterator=None):
    Analysis(results, param_results, iterator)


def analyze():
    for element in Analysis():
        Analysis().analyze(*element)


def store_results():
    Analysis().store_results()


def clean():
    Analysis().clean()


class RequirementError(Exception):
    pass


class DependencyError(Exception):
    pass


class Analysis(object):
    """
    Holds chain for all analyzers. Is implemented as singleton.
    """
    class __Analysis:
        def __init__(self, results, param_results, iterator):
            self.results = results
            self.param_results = param_results
            self.iterator = (
                TupleIterator if iterator is None else iterator)
            self.chain = OrderedDict()
            self.former_chain = OrderedDict()

        def clean(self):
            self.chain = OrderedDict()
            self.former_chain = OrderedDict()

        def check_iterator(self, analyzer):
            if analyzer.required_iterator is None:
                return
            if self.iterator != analyzer.required_iterator:
                raise RequirementError(
                    'Analyzer "' + analyzer.__class__.__name__ +
                    '" requires iterator "' +
                    analyzer.required_iterator.__name__ +
                    '" to work correctly. Please initialize analysis object '
                    'with iterator "' + analyzer.required_iterator.__name__ +
                    '".'
                )

        def check_requirements(self, component):
            """
            Checks if requirements are fullfilled

            Function can be used by Analyzer and Iterator objects
            """
            if component.requires is not None:
                for req in component.requires:
                    if getattr(self, req) is None:
                        raise RequirementError(
                            'Component "' + component.__class__.__name__ +
                            '" requires "' + req + '" to perform. Please '
                            'initialize it with attribute "' + req + '".'
                        )

        def check_dependencies(self, analyzer):
            dep_str = (
                'Analyzer "{an}" depends on analyzer "{dep}". '
                'Please initialize analyzer "{dep}" first.'
            )
            dep_former_str = (
                'Analyzer "{an}" depends on former analyzer "{dep}". '
                'You have to run analysis with analyzer "{dep}" first. '
                'Afterwards, you have to store results via '
                '"analyzer.store_results()". Then you are able to add '
                'analyzer "{an}" to analysis.'
            )

            def check_deps(former=False):
                error_str = dep_former_str if former else dep_str
                for dep in dependencies:
                    if dep.__name__ not in chain_keys:
                        raise DependencyError(
                            error_str.format(
                                an=analyzer.__class__.__name__,
                                dep=dep.__name__,
                            )
                        )

            chain_keys = list(self.former_chain)
            if analyzer.depends_on_former is not None:
                dependencies = analyzer.depends_on_former
                check_deps(former=True)
            if analyzer.depends_on is not None:
                dependencies = analyzer.depends_on
                chain_keys += list(self.chain)
                check_deps()

        def add_to_chain(self, analyzer):
            if analyzer.__class__.__name__ in self.chain:
                warn(
                    'Analyzer "' + analyzer.__class__.__name__ +
                    '" already added to analysis. '
                    'Clear analysis if you want to create new analysis.'
                )
            else:
                self.chain[analyzer.__class__.__name__] = analyzer

        def analyze(self, *args):
            for analyzer in self.chain.values():
                analyzer.analyze(*args)

        def store_results(self):
            self.former_chain.update(self.chain)
            self.chain = OrderedDict()

        def __iter__(self):
            return self.iterator(self)

    singleton = None

    def __new__(cls, results=None, param_results=None, iterator=None):
        if not Analysis.singleton:
            Analysis.singleton = Analysis.__Analysis(
                results, param_results, iterator)
        return Analysis.singleton


class Iterator(abc.Iterator):
    """
    Iterator for Analysis (uses Iterator Pattern)
    """
    requires = None

    def __init__(self, analysis):
        analysis.check_requirements(self)
        self.items = None
        self.index = 0

    def __next__(self):
        try:
            result = self.items[self.index]
        except IndexError:
            raise StopIteration
        self.index += 1
        return result


class FlowNodeIterator(Iterator):
    def __init__(self, analysis):
        super(FlowNodeIterator, self).__init__(analysis)
        self.items = [
            node
            for node in analysis.param_results
            if node[1] is not None
        ] + [
            node
            for node in analysis.param_results
            if node[1] is None
        ]


class TupleIterator(Iterator):
    def __init__(self, analysis):
        super(TupleIterator, self).__init__(analysis)
        self.items = [
            node
            for node in analysis.param_results
        ]


class NodeIterator(Iterator):
    def __init__(self, analysis):
        super(NodeIterator, self).__init__(analysis)
        self.items = [
            node
            for node in analysis.param_results
            if node[1] is None
        ]


class Analyzer(object):
    requires = None
    required_iterator = None
    depends_on = None
    depends_on_former = None

    def __init__(self):
        self.analysis = Analysis()
        self.analysis.check_requirements(self)
        self.analysis.check_iterator(self)
        self.analysis.check_dependencies(self)
        self.analysis.add_to_chain(self)
        self.result = {}

    def _get_dep_result(self, analyzer):
        """
        Returns results of dependent analyzer.
        """
        try:
            return self.analysis.former_chain[analyzer.__name__].result
        except KeyError:
            try:
                return self.analysis.chain[analyzer.__name__].result
            except KeyError:
                raise DependencyError(
                    'Analyzer "' + analyzer.__name__ +
                    '" not found in analysis chain.'
                )

    def rsc(self, args):
        return self.analysis.results[args]['scalars']

    def rsq(self, args):
        return self.analysis.results[args]['sequences']

    def psc(self, args):
        return self.analysis.param_results[args]['scalars']

    def psq(self, args):
        return self.analysis.param_results[args]['sequences']

    @staticmethod
    def _arg_is_flow(args):
        return (
            len(args) == 2 and
            isinstance(args[0], Node) and
            isinstance(args[1], Node)
        )

    @staticmethod
    def _arg_is_node(args):
        return (
                len(args) == 2 and
                isinstance(args[0], Node) and
                args[1] is None
        )

    def analyze(self, *args):
        pass


class SequenceFlowSumAnalyzer(Analyzer):
    requires = ('results',)

    def analyze(self, *args):
        try:
            rsq = self.rsq(args)
            self.result[args] = rsq['flow'].sum()
        except KeyError:
            return


class InvestAnalyzer(Analyzer):
    requires = ('results', 'param_results')

    def analyze(self, *args):
        try:
            psc = self.psc(args)
            rsc = self.rsc(args)
            invest = psc['investment_ep_costs']
            ep_costs = rsc['invest']
        except KeyError:
            return
        self.result[args] = invest * ep_costs


class VariableCostAnalyzer(Analyzer):
    requires = ('results', 'param_results')
    depends_on = (SequenceFlowSumAnalyzer,)

    def analyze(self, *args):
        seq_result = self._get_dep_result(SequenceFlowSumAnalyzer)
        try:
            psc = self.psc(args)
            variable_cost = psc['variable_costs']
            flow_sum = seq_result[args]
        except KeyError:
            return
        self.result[args] = variable_cost * flow_sum


class FlowTypeAnalyzer(Analyzer):
    requires = ('results',)

    def analyze(self, *args):
        if self._arg_is_node(args):
            self.result[args] = views.get_flow_type(
                args[0], self.analysis.results)


class NodeBalanceAnalyzer(Analyzer):
    requires = ('results', 'param_results')
    required_iterator = FlowNodeIterator
    depends_on = (SequenceFlowSumAnalyzer, FlowTypeAnalyzer)

    node_type = Node

    def analyze(self, *args):
        if not (isinstance(args[0], self.node_type) and args[1] is None):
            return

        seq_result = self._get_dep_result(SequenceFlowSumAnalyzer)
        ft_result = self._get_dep_result(FlowTypeAnalyzer)
        try:
            current_flow_types = ft_result[args]
        except KeyError:
            return
        self.result[args[0]] = {}
        f_types = (views.FlowType.Input, views.FlowType.Output)
        for i, ft in enumerate(f_types):
            self.result[args[0]][ft] = {}
            for flow in current_flow_types[ft]:
                try:
                    self.result[args[0]][ft][flow[i]] = seq_result[flow]
                except KeyError:
                    pass


class BusBalanceAnalyzer(NodeBalanceAnalyzer):
    node_type = Bus

    # TODO: Check if NodeBalanceAnalyzer already exists
    # If so, BusBalanceAnalyzer could simply filter results to


class LCOEAnalyzer(Analyzer):
    depends_on = (
        SequenceFlowSumAnalyzer, VariableCostAnalyzer, InvestAnalyzer)
    depends_on_former = (NodeBalanceAnalyzer,)

    def __init__(self, load_sinks):
        """
        Initializes total load by iterating flows to all _load_sinks_

        Parameters
        ----------
        load_sinks: list-of-Node
            List of all loads which are relevant for calculating total load
        """
        super(LCOEAnalyzer, self).__init__()
        seq_result = self._get_dep_result(SequenceFlowSumAnalyzer)
        nb_result = self._get_dep_result(NodeBalanceAnalyzer)
        self.total_load = 0.0
        for to_node in load_sinks:
            for from_node in nb_result[to_node]['input']:
                self.total_load += seq_result[(from_node, to_node)]

    def analyze(self, *args):
        vc_result = self._get_dep_result(VariableCostAnalyzer)
        inv_result = self._get_dep_result(InvestAnalyzer)

        error = False
        try:
            vc = vc_result[args]
        except KeyError:
            vc = 0.0
            error = True
        try:
            inv = inv_result[args]
        except KeyError:
            if error:
                return
            inv = 0.0

        self.result[args] = (inv + vc) / self.total_load
