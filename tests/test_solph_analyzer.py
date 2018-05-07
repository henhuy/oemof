
from nose.plugins import skip
from nose.tools import eq_, assert_raises
from energysystems_for_testing import es_with_invest
from oemof.outputlib import processing
from oemof.solph import analyzer


class Analyzer_Base:
    def init(self, results, param_results):
        analyzer.init(
            results,
            param_results,
            iterator=analyzer.FlowNodeIterator
        )
        analyzer.Analysis().results = results
        analyzer.Analysis().param_results = param_results

    def key(self, key):
        if key in self.components:
            return self.components[key]
        else:
            return key

    def requirements(self):
        analyzer.clean()

        # depending analyzer missing:
        with assert_raises(analyzer.DependencyError):
            _ = analyzer.BusBalanceAnalyzer()

        # wrong iterator:
        analyzer.Analysis().iterator = analyzer.TupleIterator
        _ = analyzer.SequenceFlowSumAnalyzer()
        _ = analyzer.FlowTypeAnalyzer()
        with assert_raises(analyzer.RequirementError):
            _ = analyzer.BusBalanceAnalyzer()
        analyzer.Analysis().iterator = analyzer.FlowNodeIterator

        # param_results missing:
        analyzer.Analysis().param_results = None
        with assert_raises(analyzer.RequirementError):
            _ = analyzer.InvestAnalyzer()
        analyzer.Analysis().param_results = self.param_results

    def sequence_flow_sum_analyzer(self):
        analyzer.clean()
        seq = analyzer.SequenceFlowSumAnalyzer()
        analyzer.analyze()

        eq_(len(seq.result), 5)
        eq_(seq.result[(self.key('b_diesel'), self.key('diesel'))], 62.5)
        eq_(seq.result[(self.key('diesel'), self.key('b_el1'))], 125)
        eq_(seq.result[(self.key('b_el1'), self.key('storage'))], 125)
        eq_(seq.result[(self.key('storage'), self.key('b_el2'))], 100)
        eq_(seq.result[(self.key('b_el2'), self.key('demand_el'))], 100)

    def variable_cost_analyzer(self):
        analyzer.clean()
        _ = analyzer.SequenceFlowSumAnalyzer()
        vc = analyzer.VariableCostAnalyzer()
        analyzer.analyze()

        eq_(len(vc.result), 5)
        eq_(vc.result[(self.key('b_diesel'), self.key('diesel'))], 125)
        eq_(vc.result[(self.key('diesel'), self.key('b_el1'))], 125)
        eq_(vc.result[(self.key('b_el1'), self.key('storage'))], 375)
        eq_(vc.result[(self.key('storage'), self.key('b_el2'))], 250)
        eq_(vc.result[(self.key('b_el2'), self.key('demand_el'))], 0)

    def bus_balance_analyzer(self):
        analyzer.clean()
        _ = analyzer.SequenceFlowSumAnalyzer()
        _ = analyzer.FlowTypeAnalyzer()
        bb = analyzer.BusBalanceAnalyzer()
        analyzer.analyze()

        eq_(len(bb.result), 3)

        # b_diesel:
        eq_(len(bb.result[self.key('b_diesel')]['input']), 0)
        eq_(len(bb.result[self.key('b_diesel')]['output']), 1)
        eq_(
            bb.result[self.key('b_diesel')]['output'][self.key('diesel')],
            62.5
        )

        # b_el1:
        eq_(len(bb.result[self.key('b_el1')]['input']), 1)
        eq_(len(bb.result[self.key('b_el1')]['output']), 1)
        eq_(
            bb.result[self.key('b_el1')]['input'][self.key('diesel')], 125)
        eq_(
            bb.result[self.key('b_el1')]['output'][self.key('storage')],
            125
        )

        # b_el2:
        eq_(len(bb.result[self.key('b_el2')]['input']), 1)
        eq_(len(bb.result[self.key('b_el2')]['output']), 1)
        eq_(bb.result[self.key('b_el2')]['input'][self.key('storage')], 100)
        eq_(
            bb.result[self.key('b_el2')]['output'][self.key('demand_el')],
            100
        )

    def invest_analyzer(self):
        analyzer.clean()
        invest = analyzer.InvestAnalyzer()
        analyzer.analyze()

        eq_(len(invest.result), 4)

        # dg-b_el1-Flow
        eq_(
            invest.result[(self.key('diesel'), self.key('b_el1'))],
            62.5 * 0.5
        )

        # batt
        eq_(invest.result[(self.key('storage'), None)], 600 * 0.4)
        eq_(invest.result[(self.key('b_el1'), self.key('storage'))], 0)
        eq_(invest.result[(self.key('storage'), self.key('b_el2'))], 0)

    def lcoe_analyzer(self):
        analyzer.clean()
        _ = analyzer.SequenceFlowSumAnalyzer()
        _ = analyzer.FlowTypeAnalyzer()
        _ = analyzer.NodeBalanceAnalyzer()
        _ = analyzer.VariableCostAnalyzer()
        _ = analyzer.InvestAnalyzer()
        analyzer.analyze()
        analyzer.store_results()
        lcoe = analyzer.LCOEAnalyzer([self.key('demand_el')])
        analyzer.analyze()

        output = 100
        eq_(len(lcoe.result), 6)

        # dg
        eq_(
            lcoe.result[(self.key('diesel'), self.key('b_el1'))],
            (125 + 62.5 * 0.5) / output
        )
        eq_(
            lcoe.result[(self.key('b_diesel'), self.key('diesel'))],
            125 / output
        )

        # batt
        eq_(lcoe.result[(self.key('storage'), None)],
            600 * 0.4 / output)
        eq_(
            lcoe.result[(self.key('b_el1'), self.key('storage'))],
            375 / output
        )
        eq_(
            lcoe.result[(self.key('storage'), self.key('b_el2'))],
            250 / output
        )
        eq_(
            lcoe.result[(self.key('b_el2'), self.key('demand_el'))],
            0 / output
        )


class Analyzer_Test(Analyzer_Base):
    def setup(self):
        self.results = processing.results(
            es_with_invest.optimization_model)
        self.param_results = processing.param_results(
            es_with_invest.optimization_model)
        super(Analyzer_Test, self).init(self.results, self.param_results)
        self.components = {
            'b_diesel': es_with_invest.b_diesel,
            'diesel': es_with_invest.dg,
            'b_el1': es_with_invest.b_el1,
            'storage': es_with_invest.batt,
            'b_el2': es_with_invest.b_el2,
            'demand_el': es_with_invest.demand,
        }

    def test_requirements(self): self.requirements()

    def test_sequence_flow_sum_analyzer(self):
        self.sequence_flow_sum_analyzer()

    def test_variable_cost_analyzer(self): self.variable_cost_analyzer()

    def test_bus_balance_analyzer(self): self.bus_balance_analyzer()

    def test_invest_analyzer(self): self.invest_analyzer()

    def test_lcoe_analyzer(self): self.lcoe_analyzer()


class Analyzer_Str_Test(Analyzer_Base):
    def setup(self):
        self.components = {}
        self.results = processing.convert_keys_to_strings(
            processing.results(es_with_invest.optimization_model)
        )
        self.param_results = processing.convert_keys_to_strings(
            processing.param_results(es_with_invest.optimization_model)
        )
        super(Analyzer_Str_Test, self).init(self.results, self.param_results)

    def test_requirements(self): self.requirements()

    def test_sequence_flow_sum_analyzer(self):
        self.sequence_flow_sum_analyzer()

    def test_variable_cost_analyzer(self): self.variable_cost_analyzer()

    # def test_bus_balance_analyzer(self): self.bus_balance_analyzer()

    def test_invest_analyzer(self): self.invest_analyzer()

    def test_lcoe_analyzer(self): self.lcoe_analyzer()
