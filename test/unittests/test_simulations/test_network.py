#!/usr/bin/env python
from __future__ import division
from __future__ import print_function
from builtins import zip
from builtins import range
from itertools import groupby
from operator import itemgetter
import itertools
import numpy
import quantities as pq
import neo
from nineml.user import (
    Projection, Network, DynamicsProperties,
    Population, ComponentArray, EventConnectionGroup,
    MultiDynamicsProperties,
    Property, RandomDistributionProperties)
from nineml.user.projection import Connectivity
from nineml.abstraction import (
    Parameter, Dynamics, Regime, On, OutputEvent, StateVariable,
    StateAssignment, Constant, Alias)
from nineml.abstraction.ports import (
    AnalogSendPort, AnalogReceivePort, AnalogReducePort, EventSendPort,
    EventReceivePort)
from nineml.user import AnalogPortConnection, ConnectionRuleProperties
from nineml import units as un
from nineml.units import ms
from nineml.values import RandomDistributionValue
from pype9.simulate.common.cells import (
    ConnectionPropertySet, MultiDynamicsWithSynapsesProperties,
    SynapseProperties)
from pype9.simulate.common.network import Network as BasePype9Network
from pype9.simulate.neuron.network import Network as NeuronPype9Network
from pype9.simulate.neuron import Simulation as NeuronSimulation
import ninemlcatalog
import sys
argv = sys.argv[1:]  # Save argv before it is clobbered by the NEST init.
import nest  # @IgnorePep8
from pype9.simulate.nest.network import Network as NestPype9Network  # @IgnorePep8
from pype9.simulate.nest import Simulation as NESTSimulation  # @IgnorePep8
from pype9.utils.testing import ReferenceBrunel2000  # @IgnorePep8
import pype9.utils.logging.handlers.sysout  # @IgnorePep8

try:
    from matplotlib import pyplot as plt
except ImportError:
    pass
if __name__ == '__main__':
    # Import dummy test case
    from pype9.utils.testing import DummyTestCase as TestCase  # @UnusedImport @UnresolvedImport @IgnorePep8
else:
    from unittest import TestCase  # @Reimport

nest_bookkeeping = (
    'element_type', 'global_id', 'local_id', 'receptor_types',
    'thread_local_id', 'frozen', 'thread', 'model',
    'archiver_length', 'recordables', 'parent', 'local', 'vp',
    'tau_minus', 'tau_minus_triplet', 't_spike', 'origin', 'stop', 'start',
    'V_min', 'synaptic_elements', 'needs_prelim_update', 'beta_Ca',
    'tau_Ca', 'Ca', 'node_uses_wfr', 'supports_precise_spikes')

NEST_RNG_SEED = 12345
NEURON_RNG_SEED = 54321


class TestBrunel2000(TestCase):

    translations = {
        'tau_m': 'tau__cell', 'V_th': 'v_threshold__cell',
        'E_L': 0.0, 'I_e': 0.0, 'C_m': None,
        'V_reset': 'v_reset__cell', 'tau_syn_in': 'tau__psr__Inhibition',
        'tau_syn_ex': 'tau__psr__Excitation',
        't_ref': 'refractory_period__cell',
        'V_m': None}  # 'v__cell'}

    timestep = 0.1
    pop_names = ('Exc', 'Inh', 'Ext')
    proj_names = ('Excitation', 'Inhibition', 'External')
    conn_param_names = ['weight', 'delay']
    record_params = {'Exc': {'nineml': ['v__cell',
                                        'b__psr__Excitation',
                                        'b__psr__Inhibition',
                                        'b__psr__External'],
                             'reference': ['V_m']},
                     'Inh': {'nineml': ['v__cell',
                                        'b__psr__Excitation',
                                        'b__psr__Inhibition',
                                        'b__psr__External'],
                             'reference': ['V_m']},
                     'Ext': {'nineml': [], 'reference': []}}

    rate_percent_error = {'Exc': 7.5, 'Inh': 7.5, 'Ext': 2.5}
    psth_percent_error = {'Exc': 100.0, 'Inh': 100.0, 'Ext': 100.0}
    out_stdev_error = {('Exc', 'Exc'): 7.5, ('Exc', 'Inh'): 7.5,
                       ('Inh', 'Exc'): 7.5, ('Inh', 'Inh'): 7.5,
                       ('Ext', 'Exc'): 0.0, ('Ext', 'Inh'): 0.0}

    def setUp(self):
        self.simulations = {
            'nest': NESTSimulation(
                dt=self.timestep * un.ms, seed=NEST_RNG_SEED,
                min_delay=ReferenceBrunel2000.min_delay,
                max_delay=ReferenceBrunel2000.max_delay),
            'neuron': NeuronSimulation(
                dt=self.timestep * un.ms, seed=NEURON_RNG_SEED,
                min_delay=ReferenceBrunel2000.min_delay,
                max_delay=ReferenceBrunel2000.max_delay)}

    def test_population_params(self, case='AI', order=10, **kwargs):  # @UnusedVariable @IgnorePep8
        with self.simulations['nest']:
            nml = self._construct_nineml(case, order, 'nest')
            ref = ReferenceBrunel2000(case, order)
            for pop_name in ('Exc', 'Inh'):
                params = {}
                means = {}
                stdevs = {}
                for model_ver in ('nineml', 'reference'):
                    if model_ver == 'nineml':
                        inds = list(nml.component_array(pop_name).all_cells)
                    else:
                        inds = ref[pop_name]
                    param_names = [
                        n for n in list(nest.GetStatus([inds[0]])[0].keys())
                        if n not in nest_bookkeeping]
                    params[model_ver] = dict(
                        zip(param_names, zip(*nest.GetStatus(
                            inds, keys=param_names))))
                    means[model_ver] = {}
                    stdevs[model_ver] = {}
                    for param_name, values in params[model_ver].items():
                        vals = numpy.asarray(values)
                        try:
                            means[model_ver][param_name] = numpy.mean(vals)
                        except:
                            means[model_ver][param_name] = None
                        try:
                            stdevs[model_ver][param_name] = numpy.std(vals)
                        except:
                            stdevs[model_ver][param_name] = None
                for stat_name, stat in (('mean', means),
                                        ('standard deviation', stdevs)):
                    for param_name in stat['reference']:
                        nml_param_name = self.translations.get(
                            param_name, param_name + '__cell')
                        if nml_param_name is not None:  # Equivalent parameter
                            if isinstance(nml_param_name, (float, int)):
                                if stat_name == 'mean':
                                    nineml_stat = nml_param_name
                                else:
                                    nineml_stat = 0.0
                            else:
                                nineml_stat = stat['nineml'][nml_param_name]
                            reference_stat = stat['reference'][param_name]
                            self.assertAlmostEqual(
                                reference_stat, nineml_stat,
                                msg=("'{}' {} is not almost equal between "
                                     "reference ({}) and nineml ({})  in '{}'"
                                     .format(param_name, stat_name,
                                             reference_stat, nineml_stat,
                                             pop_name)))
                        else:
                            pass

    def test_connection_degrees(self, case='AI', order=500, **kwargs):  # @UnusedVariable @IgnorePep8
        """
        Compares the in/out degree of all projections in the 9ML network with
        the corresponding projections in the reference network
        """
        with self.simulations['nest']:
            nml = self._construct_nineml(case, order, 'nest')
            ref = ReferenceBrunel2000(case, order)
            for pop1_name, pop2_name in self.out_stdev_error:
                in_degree = {}
                out_degree = {}
                for model_ver, pop1, pop2 in [
                    ('nineml', nml.component_array(pop1_name).all_cells,
                     nml.component_array(pop2_name).all_cells),
                    ('reference', numpy.asarray(ref[pop1_name]),
                     numpy.asarray(ref[pop2_name]))]:
                    conns = numpy.asarray(nest.GetConnections(list(pop1),
                                                              list(pop2)))
                    out_degree[model_ver] = numpy.array(
                        [numpy.count_nonzero(conns[:, 0] == i) for i in pop1])
                    in_degree[model_ver] = numpy.array(
                        [numpy.count_nonzero(conns[:, 1] == i) for i in pop2])
                nineml_out_mean = numpy.mean(out_degree['nineml'])
                ref_out_mean = numpy.mean(out_degree['reference'])
                self.assertEqual(
                    nineml_out_mean, ref_out_mean,
                    "Mean out degree of '{}' to '{}' projection ({}) doesn't "
                    "match reference ({})".format(
                        pop1_name, pop2_name, nineml_out_mean, ref_out_mean))
                nineml_in_mean = numpy.mean(in_degree['nineml'])
                ref_in_mean = numpy.mean(in_degree['reference'])
                self.assertEqual(
                    nineml_in_mean, ref_in_mean,
                    "Mean in degree of '{}' to '{}' projection ({}) doesn't "
                    "match reference ({})".format(
                        pop1_name, pop2_name, nineml_in_mean, ref_in_mean))
                nineml_in_stdev = numpy.std(in_degree['nineml'])
                ref_in_stdev = numpy.std(in_degree['reference'])
                self.assertEqual(
                    nineml_in_stdev, ref_in_stdev,
                    "Std. of in degree of '{}' to '{}' projection ({}) doesn't"
                    " match reference ({})".format(
                        pop1_name, pop2_name, nineml_in_stdev, ref_in_stdev))
                nineml_out_stdev = numpy.std(out_degree['nineml'])
                ref_out_stdev = numpy.std(out_degree['reference'])
                percent_error = abs(nineml_out_stdev /
                                    ref_out_stdev - 1.0) * 100.0
                self.assertLessEqual(
                    percent_error, self.out_stdev_error[(pop1_name,
                                                         pop2_name)],
                    "Std. of out degree of '{}' to '{}' projection ({}) "
                    "doesn't match reference ({}) within {}% ({}%)".format(
                        pop1_name, pop2_name, nineml_out_stdev, ref_out_stdev,
                        self.out_stdev_error[(pop1_name, pop2_name)],
                        percent_error))

    def test_connection_params(self, case='AI', order=10, **kwargs):  # @UnusedVariable @IgnorePep8
        with self.simulations['nest']:
            nml = self._construct_nineml(case, order, 'nest')
            ref = ReferenceBrunel2000(case, order)
            ref_conns = ref.projections
            for conn_group in nml.connection_groups:
                nml_conns = conn_group.nest_connections
                nml_params = dict(zip(
                    self.conn_param_names, zip(
                        *nest.GetStatus(nml_conns, self.conn_param_names))))
                # Since the weight is constant it is set as a parameter of the
                # cell class not a connection parameter and it is scaled by
                # exp because of the difference between the alpha synapse
                # definition in the catalog and the nest/neuron synapses
                nml_params['weight'] = nest.GetStatus(
                    list(conn_group.post.all_cells),
                    'weight__pls__{}'.format(conn_group.name)) / numpy.exp(1.0)
                ref_params = dict(zip(
                    self.conn_param_names, zip(
                        *nest.GetStatus(ref_conns[conn_group.name],
                                        self.conn_param_names))))
                for attr in self.conn_param_names:
                    ref_mean = numpy.mean(ref_params[attr])
                    ref_stdev = numpy.std(ref_params[attr])
                    nml_mean = numpy.mean(nml_params[attr])
                    nml_stdev = numpy.std(nml_params[attr])
                    self.assertAlmostEqual(
                        ref_mean, nml_mean,
                        msg=("'{}' mean is not almost equal between "
                             "reference ({}) and nineml ({})  in '{}'"
                             .format(attr, ref_mean, nml_mean,
                                     conn_group.name)))
                    self.assertAlmostEqual(
                        ref_stdev, nml_stdev,
                        msg=("'{}' mean is not almost equal between "
                             "reference ({}) and nineml ({})  in '{}'"
                             .format(attr, ref_stdev, nml_stdev,
                                     conn_group.name)))

    def test_sizes(self, case='AI', order=100, **kwargs):  # @UnusedVariable @IgnorePep8
        with self.simulations['nest']:
            nml_network = self._construct_nineml(case, order, 'nest')
            nml = dict((p.name, p.all_cells)
                       for p in nml_network.component_arrays)
            ref = ReferenceBrunel2000(case, order)
            # Test sizes of component arrays
            for name in ('Exc', 'Inh'):
                nml_size = len(nml[name])
                ref_size = len(ref[name])
                self.assertEqual(
                    nml_size, ref_size,
                    "Size of '{}' component array ({}) does not match "
                    "reference ({})".format(name, nml_size, ref_size))
            ref_conns = ref.projections
            for conn_group in nml_network.connection_groups:
                nml_size = len(conn_group)
                ref_size = len(ref_conns[conn_group.name])
                self.assertEqual(
                    nml_size, ref_size,
                    "Number of connections in '{}' ({}) does not match "
                    "reference ({})".format(conn_group.name, nml_size,
                                            ref_size))

    def test_activity(self, case='AI', order=50, simtime=250.0, plot=False,
                      record_size=50, record_pops=('Exc', 'Inh', 'Ext'),
                      record_states=False, record_start=0.0, bin_width=4.0,
                      identical_input=False, identical_connections=False,
                      identical_initialisation=False, build_mode='force',
                      **kwargs):
        if identical_input:
            mean_isi = 1000.0 / ReferenceBrunel2000.parameters(case, order)[-1]
            if isinstance(identical_input, int):
                mean_isi *= identical_input
            external_input = []
            for _ in range(order * 5):
                # Generate poisson spike trains using numpy
                spike_times = numpy.cumsum(numpy.random.exponential(
                    mean_isi, int(numpy.floor(1.5 * simtime / mean_isi))))
                # Trim spikes outside the simulation time
                spike_times = spike_times[numpy.logical_and(
                    spike_times < simtime,
                    spike_times > ReferenceBrunel2000.min_delay)]
                # Append a Neo SpikeTrain input to the external input
                external_input.append(
                    neo.SpikeTrain(spike_times, units='ms',
                                   t_stop=simtime * pq.ms))
        else:
            external_input = None
        record_duration = simtime - record_start
        # Construct 9ML network
        with self.simulations['nest'] as sim:
            nml_network = self._construct_nineml(
                case, order, 'nest', external_input=external_input,
                build_mode=build_mode, **kwargs)
            nml = dict((p.name, list(p.all_cells))
                       for p in nml_network.component_arrays)
            if identical_connections:
                connections = {}
                for p1_name, p2_name in itertools.product(*([('Exc', 'Inh')] *
                                                            2)):
                    p1 = list(nml_network.component_array(p1_name).all_cells)
                    p2 = list(nml_network.component_array(p2_name).all_cells)
                    conns = numpy.asarray(nest.GetConnections(p1, p2))
                    conns[:, 0] -= p1[0]
                    conns[:, 1] -= p2[0]
                    assert numpy.all(conns[0:2, :] >= 0)
                    connections[(p1_name, p2_name)] = conns
            else:
                connections = None
            if identical_initialisation == 'zero':
                init_v = {}
                for pname in ('Exc', 'Inh'):
                    pop = list(nml_network.component_array(pname).all_cells)
                    zeros = list(
                        numpy.zeros(len(nml_network.component_array(pname))))
                    nest.SetStatus(pop, 'v__cell', zeros)
                    init_v[pname] = zeros
            elif identical_initialisation:
                init_v = {}
                for p_name in ('Exc', 'Inh'):
                    pop = list(nml_network.component_array(p_name).all_cells)
                    init_v[p_name] = nest.GetStatus(pop, 'v__cell')
            else:
                init_v = None
            # Construct reference network
            ref = ReferenceBrunel2000(
                case, order, external_input=external_input,
                connections=connections, init_v=init_v)
            # Set up spike recorders for reference network
            pops = {'nineml': nml, 'reference': ref}
            spikes = {}
            multi = {}
            for model_ver in ('nineml', 'reference'):
                spikes[model_ver] = {}
                multi[model_ver] = {}
                for pop_name in record_pops:
                    pop = numpy.asarray(pops[model_ver][pop_name], dtype=int)
                    record_inds = numpy.asarray(numpy.unique(numpy.floor(
                        numpy.arange(start=0, stop=len(pop),
                                     step=len(pop) / record_size))), dtype=int)
                    spikes[model_ver][pop_name] = nest.Create("spike_detector")
                    nest.SetStatus(spikes[model_ver][pop_name],
                                   [{"label": "brunel-py-" + pop_name,
                                     "withtime": True, "withgid": True}])
                    nest.Connect(list(pop[record_inds]),
                                 spikes[model_ver][pop_name],
                                 syn_spec="excitatory")
                    if record_states:
                        # Set up voltage traces recorders for reference network
                        if self.record_params[pop_name][model_ver]:
                            multi[model_ver][pop_name] = nest.Create(
                                'multimeter',
                                params={
                                    'record_from':
                                    self.record_params[pop_name][model_ver]})
                            nest.Connect(multi[model_ver][pop_name],
                                         list(pop[record_inds]))
            # Simulate the network
            sim.run(simtime * un.ms)
        rates = {'reference': {}, 'nineml': {}}
        psth = {'reference': {}, 'nineml': {}}
        for model_ver in ('reference', 'nineml'):
            for pop_name in record_pops:
                events = nest.GetStatus(spikes[model_ver][pop_name],
                                        "events")[0]
                spike_times = numpy.asarray(events['times'])
                senders = numpy.asarray(events['senders'])
                inds = numpy.asarray(spike_times > record_start, dtype=bool)
                spike_times = spike_times[inds]
                senders = senders[inds]
                rates[model_ver][pop_name] = (
                    1000.0 * len(spike_times) / record_duration)
                psth[model_ver][pop_name] = (
                    numpy.histogram(
                        spike_times,
                        bins=int(numpy.floor(record_duration /
                                             bin_width)))[0] /
                    bin_width)
                if plot:
                    plt.figure()
                    plt.scatter(spike_times, senders)
                    plt.xlabel('Time (ms)')
                    plt.ylabel('Cell Indices')
                    plt.title("{} - {} Spikes".format(model_ver, pop_name))
                    plt.figure()
                    plt.hist(spike_times,
                             bins=int(
                                 numpy.floor(record_duration / bin_width)))
                    plt.xlabel('Time (ms)')
                    plt.ylabel('Rate')
                    plt.title("{} - {} PSTH".format(model_ver, pop_name))
                    if record_states:
                        for param in self.record_params[pop_name][model_ver]:
                            events, interval = nest.GetStatus(
                                multi[model_ver][pop_name], ["events",
                                                             'interval'])[0]
                            sorted_vs = sorted(zip(events['senders'],
                                                   events['times'],
                                                   events[param]),
                                               key=itemgetter(0))
                            plt.figure()
                            legend = []
                            for sender, group in groupby(sorted_vs,
                                                         key=itemgetter(0)):
                                _, t, v = list(zip(*group))
                                t = numpy.asarray(t)
                                v = numpy.asarray(v)
                                inds = t > record_start
                                plt.plot(t[inds] * interval, v[inds])
                                legend.append(sender)
                            plt.xlabel('Time (ms)')
                            plt.ylabel(param)
                            plt.title("{} - {} {}".format(model_ver, pop_name,
                                                          param))
                            plt.legend(legend)
        for pop_name in record_pops:
            if rates['reference'][pop_name]:
                percent_rate_error = abs(
                    rates['nineml'][pop_name] /
                    rates['reference'][pop_name] - 1.0) * 100
            elif not rates['nineml'][pop_name]:
                percent_rate_error = 0.0
            else:
                percent_rate_error = float('inf')
            self.assertLess(
                percent_rate_error,
                self.rate_percent_error[pop_name], msg=(
                    "Rate of '{}' ({}) doesn't match reference ({}) within {}%"
                    " ({}%)".format(pop_name, rates['nineml'][pop_name],
                                    rates['reference'][pop_name],
                                    self.rate_percent_error[pop_name],
                                    percent_rate_error)))
            if numpy.std(psth['reference'][pop_name]):
                percent_psth_stdev_error = abs(
                    numpy.std(psth['nineml'][pop_name]) /
                    numpy.std(psth['reference'][pop_name]) - 1.0) * 100
            elif not numpy.std(psth['nineml'][pop_name]):
                percent_psth_stdev_error = 0.0
            else:
                percent_psth_stdev_error = float('inf')
            self.assertLess(
                percent_psth_stdev_error,
                self.psth_percent_error[pop_name],
                msg=(
                    "Std. Dev. of PSTH for '{}' ({}) doesn't match "
                    "reference ({}) within {}% ({}%)".format(
                        pop_name,
                        numpy.std(psth['nineml'][pop_name]) / bin_width,
                        numpy.std(psth['reference'][pop_name]) / bin_width,
                        self.psth_percent_error[pop_name],
                        percent_psth_stdev_error)))
        if plot:
            plt.show()

    def test_activity_with_neuron(self, case='AI', order=10, simtime=100.0,
                                  bin_width=4.0, simulators=['neuron', 'nest'],
                                  record_states=True, plot=False,
                                  build_mode='force', **kwargs):  # @IgnorePep8 @UnusedVariable
        data = {}
        # Set up recorders for 9ML network
        rates = {}
        psth = {}
        for simulator in simulators:
            data[simulator] = {}
            with self.simulations[simulator] as sim:
                network = self._construct_nineml(case, order, simulator,
                                                 **kwargs)
                for pop in network.component_arrays:
                    pop.record('spike_output')
                    if record_states and pop.name != 'Ext':
                        pop.record('v__cell')
                sim.run(simtime * un.ms)
            rates[simulator] = {}
            psth[simulator] = {}
            for pop in network.component_arrays:
                block = data[simulator][pop.name] = pop.get_data()
                segment = block.segments[0]
                spiketrains = segment.spiketrains
                spike_times = []
                ids = []
                for i, spiketrain in enumerate(spiketrains):
                    spike_times.extend(spiketrain)
                    ids.extend([i] * len(spiketrain))
                rates[simulator][pop.name] = len(spike_times) / (simtime *
                                                                 pq.ms)
                psth[simulator][pop.name] = numpy.histogram(
                    spike_times,
                    bins=int(numpy.floor(simtime /
                                         bin_width)))[0] / bin_width
                if plot:
                    plt.figure()
                    plt.scatter(spike_times, ids)
                    plt.xlabel('Times (ms)')
                    plt.ylabel('Cell Indices')
                    plt.title("{} - {} Spikes".format(simulator, pop.name))
                    if record_states and pop.name != 'Ext':
                        traces = segment.analogsignalarrays
                        plt.figure()
                        legend = []
                        for trace in traces:
                            plt.plot(trace.times, trace)
                            legend.append(trace.name)
                            plt.xlabel('Time (ms)')
                            plt.ylabel('Membrane Voltage (mV)')
                            plt.title("{} - {} Membrane Voltage".format(
                                simulator, pop.name))
                        plt.legend(legend)
        for pop in network.component_arrays:
            if rates['nest'][pop.name]:
                percent_rate_error = abs(
                    rates['neuron'][pop.name] /
                    rates['nest'][pop.name] - 1.0) * 100
            elif not rates['neuron'][pop.name]:
                percent_rate_error = 0.0
            else:
                percent_rate_error = float('inf')
            self.assertLess(
                percent_rate_error,
                self.rate_percent_error[pop.name], msg=(
                    "Rate of NEURON '{}' ({}) doesn't match NEST ({}) within "
                    "{}% ({}%)".format(pop.name, rates['neuron'][pop.name],
                                       rates['nest'][pop.name],
                                       self.rate_percent_error[pop.name],
                                       percent_rate_error)))
            if numpy.std(psth['nest'][pop.name]):
                percent_psth_stdev_error = abs(
                    numpy.std(psth['neuron'][pop.name]) /
                    numpy.std(psth['nest'][pop.name]) - 1.0) * 100
            elif not numpy.std(psth['neuron'][pop.name]):
                percent_psth_stdev_error = 0.0
            else:
                percent_psth_stdev_error = float('inf')
            self.assertLess(
                percent_psth_stdev_error,
                self.psth_percent_error[pop.name],
                msg=(
                    "Std. Dev. of PSTH for NEURON '{}' ({}) doesn't match "
                    "NEST ({}) within {}% ({}%)".format(
                        pop.name,
                        numpy.std(psth['neuron'][pop.name]) / bin_width,
                        numpy.std(psth['nest'][pop.name]) / bin_width,
                        self.psth_percent_error[pop.name],
                        percent_psth_stdev_error)))
        if plot:
            plt.show()
        print("done")

    def test_flatten(self, **kwargs):  # @UnusedVariable
        brunel_network = ninemlcatalog.load(
            'network/Brunel2000/AI/').as_network('brunel_ai')
        (component_arrays, connection_groups,
         selections) = BasePype9Network._flatten_to_arrays_and_conns(
            brunel_network)
        self.assertEqual(len(component_arrays), 3)
        self.assertEqual(len(connection_groups), 3)
        self.assertEqual(len(selections), 1)

    def _construct_nineml(self, case, order, simulator, external_input=None,
                          **kwargs):
        model = ninemlcatalog.load('network/Brunel2000/' + case).as_network(
            'Brunel_{}'.format(case))
        model = model.clone()
        scale = order / model.population('Inh').size
        # rescale populations
        for pop in model.populations:
            pop.size = int(numpy.ceil(pop.size * scale))
        for proj in (model.projection('Excitation'),
                     model.projection('Inhibition')):
            props = proj.connectivity.rule_properties
            number = props.property('number')
            props.set(Property(
                number.name,
                int(numpy.ceil(float(number.value) * scale)) * un.unitless))
        if simulator == 'nest':
            NetworkClass = NestPype9Network
        elif simulator == 'neuron':
            NetworkClass = NeuronPype9Network
        else:
            assert False
        network = NetworkClass(model, **kwargs)
        if external_input is not None:
            network.component_array('Ext').play('spike_input__cell',
                                                external_input)
        return network


class TestNetwork(TestCase):

    delay = 1.5 * un.ms

    def setUp(self):
        self.all_to_all = ConnectionRuleProperties(
            'all_to_all_props', ninemlcatalog.load('/connectionrule/AllToAll',
                                                   'AllToAll'))

    def test_component_arrays_and_connection_groups(self, **kwargs):  # @UnusedVariable @IgnorePep8

        # =====================================================================
        # Dynamics components
        # =====================================================================

        cell1_cls = Dynamics(
            name='Cell',
            state_variables=[
                StateVariable('SV1', dimension=un.voltage)],
            regimes=[
                Regime(
                    'dSV1/dt = -SV1 / P1 + i_ext / P2',
                    transitions=[On('SV1 > P3', do=[OutputEvent('spike')])],
                    name='R1')],
            analog_ports=[AnalogReducePort('i_ext', dimension=un.current,
                                           operator='+'),
                          EventSendPort('spike')],
            parameters=[Parameter('P1', dimension=un.time),
                        Parameter('P2', dimension=un.capacitance),
                        Parameter('P3', dimension=un.voltage)])

        cell2_cls = Dynamics(
            name='Cell',
            state_variables=[
                StateVariable('SV1', dimension=un.voltage)],
            regimes=[
                Regime(
                    'dSV1/dt = -SV1 ^ 2 / P1 + i_ext / P2',
                    transitions=[On('SV1 > P3', do=[OutputEvent('spike')]),
                                 On('SV1 > P4',
                                    do=[OutputEvent('double_spike')])],
                    name='R1')],
            analog_ports=[AnalogReducePort('i_ext', dimension=un.current,
                                           operator='+')],
            parameters=[Parameter('P1', dimension=un.time * un.voltage),
                        Parameter('P2', dimension=un.capacitance),
                        Parameter('P3', dimension=un.voltage),
                        Parameter('P4', dimension=un.voltage)])

        exc_cls = Dynamics(
            name="Exc",
            aliases=["i := SV1"],
            regimes=[
                Regime(
                    name="default",
                    time_derivatives=[
                        "dSV1/dt = SV1/tau"],
                    transitions=[
                        On('spike', do=["SV1 = SV1 + weight"]),
                        On('double_spike', do=['SV1 = SV1 + 2 * weight'])])],
            state_variables=[
                StateVariable('SV1', dimension=un.current),
            ],
            analog_ports=[AnalogSendPort("i", dimension=un.current),
                          AnalogReceivePort("weight", dimension=un.current)],
            parameters=[Parameter('tau', dimension=un.time)])

        inh_cls = Dynamics(
            name="Inh",
            aliases=["i := SV1"],
            regimes=[
                Regime(
                    name="default",
                    time_derivatives=[
                        "dSV1/dt = SV1/tau"],
                    transitions=On('spike', do=["SV1 = SV1 - weight"]))],
            state_variables=[
                StateVariable('SV1', dimension=un.current),
            ],
            analog_ports=[AnalogSendPort("i", dimension=un.current),
                          AnalogReceivePort("weight", dimension=un.current)],
            parameters=[Parameter('tau', dimension=un.time)])

        static_cls = Dynamics(
            name="Static",
            aliases=["fixed_weight := weight"],
            regimes=[
                Regime(name="default")],
            analog_ports=[AnalogSendPort("fixed_weight",
                                         dimension=un.current)],
            parameters=[Parameter('weight', dimension=un.current)])

        stdp_cls = Dynamics(
            name="PartialStdpGuetig",
            parameters=[
                Parameter(name='tauLTP', dimension=un.time),
                Parameter(name='aLTD', dimension=un.dimensionless),
                Parameter(name='wmax', dimension=un.dimensionless),
                Parameter(name='muLTP', dimension=un.dimensionless),
                Parameter(name='tauLTD', dimension=un.time),
                Parameter(name='aLTP', dimension=un.dimensionless)],
            analog_ports=[
                AnalogSendPort(dimension=un.dimensionless, name="wsyn"),
                AnalogSendPort(dimension=un.current, name="wsyn_current")],
            event_ports=[
                EventReceivePort(name="incoming_spike")],
            state_variables=[
                StateVariable(name='tlast_post', dimension=un.time),
                StateVariable(name='tlast_pre', dimension=un.time),
                StateVariable(name='deltaw', dimension=un.dimensionless),
                StateVariable(name='interval', dimension=un.time),
                StateVariable(name='M', dimension=un.dimensionless),
                StateVariable(name='P', dimension=un.dimensionless),
                StateVariable(name='wsyn', dimension=un.dimensionless)],
            constants=[Constant('ONE_NA', 1.0, un.nA)],
            regimes=[
                Regime(
                    name="sole",
                    transitions=On(
                        'incoming_spike',
                        to='sole',
                        do=[
                            StateAssignment('tlast_post', 't'),
                            StateAssignment('tlast_pre', 'tlast_pre'),
                            StateAssignment(
                                'deltaw',
                                'P*pow(wmax - wsyn, muLTP) * '
                                'exp(-interval/tauLTP) + deltaw'),
                            StateAssignment('interval', 't - tlast_pre'),
                            StateAssignment(
                                'M', 'M*exp((-t + tlast_post)/tauLTD) - aLTD'),
                            StateAssignment(
                                'P', 'P*exp((-t + tlast_pre)/tauLTP) + aLTP'),
                            StateAssignment('wsyn', 'deltaw + wsyn')]))],
            aliases=[Alias('wsyn_current', 'wsyn * ONE_NA')])

        exc = DynamicsProperties(
            name="ExcProps",
            definition=exc_cls, properties={'tau': 1 * ms})

        inh = DynamicsProperties(
            name="ExcProps",
            definition=inh_cls, properties={'tau': 1 * ms})

        random_weight = un.Quantity(RandomDistributionValue(
            RandomDistributionProperties(
                name="normal",
                definition=ninemlcatalog.load(
                    'randomdistribution/Normal', 'NormalDistribution'),
                properties={'mean': 1.0, 'variance': 0.25})), un.nA)

        random_wmax = un.Quantity(RandomDistributionValue(
            RandomDistributionProperties(
                name="normal",
                definition=ninemlcatalog.load(
                    'randomdistribution/Normal', 'NormalDistribution'),
                properties={'mean': 2.0, 'variance': 0.5})))

        static = DynamicsProperties(
            name="StaticProps",
            definition=static_cls,
            properties={'weight': random_weight})

        stdp = DynamicsProperties(name="StdpProps", definition=stdp_cls,
                                  properties={'tauLTP': 10 * un.ms,
                                              'aLTD': 1,
                                              'wmax': random_wmax,
                                              'muLTP': 3,
                                              'tauLTD': 20 * un.ms,
                                              'aLTP': 4})

        cell1 = DynamicsProperties(
            name="Pop1Props",
            definition=cell1_cls,
            properties={'P1': 10 * un.ms,
                        'P2': 100 * un.uF,
                        'P3': -50 * un.mV})

        cell2 = DynamicsProperties(
            name="Pop2Props",
            definition=cell2_cls,
            properties={'P1': 20 * un.ms * un.mV,
                        'P2': 50 * un.uF,
                        'P3': -40 * un.mV,
                        'P4': -20 * un.mV})

        cell3 = DynamicsProperties(
            name="Pop3Props",
            definition=cell1_cls,
            properties={'P1': 30 * un.ms,
                        'P2': 50 * un.pF,
                        'P3': -20 * un.mV})

        # =====================================================================
        # Populations and Projections
        # =====================================================================

        pop1 = Population(
            name="Pop1",
            size=10,
            cell=cell1)

        pop2 = Population(
            name="Pop2",
            size=15,
            cell=cell2)

        pop3 = Population(
            name="Pop3",
            size=20,
            cell=cell3)

        proj1 = Projection(
            name="Proj1",
            pre=pop1, post=pop2, response=inh, plasticity=static,
            connection_rule_properties=self.all_to_all,
            port_connections=[
                ('pre', 'spike', 'response', 'spike'),
                ('response', 'i', 'post', 'i_ext'),
                ('plasticity', 'fixed_weight', 'response', 'weight')],
            delay=self.delay)

        proj2 = Projection(
            name="Proj2",
            pre=pop2, post=pop1, response=exc, plasticity=static,
            connection_rule_properties=self.all_to_all,
            port_connections=[
                ('pre', 'spike', 'response', 'spike'),
                ('pre', 'double_spike', 'response', 'double_spike'),
                ('response', 'i', 'post', 'i_ext'),
                ('plasticity', 'fixed_weight', 'response', 'weight')],
            delay=self.delay)

        proj3 = Projection(
            name="Proj3",
            pre=pop3, post=pop2, response=exc, plasticity=stdp,
            connection_rule_properties=self.all_to_all,
            port_connections=[
                ('pre', 'spike', 'response', 'spike'),
                ('response', 'i', 'post', 'i_ext'),
                ('plasticity', 'wsyn_current', 'response', 'weight'),
                ('pre', 'spike', 'plasticity', 'incoming_spike')],
            delay=self.delay)

        proj4 = Projection(
            name="Proj4",
            pre=pop3, post=pop1, response=exc, plasticity=static,
            connection_rule_properties=self.all_to_all,
            port_connections=[
                ('pre', 'spike', 'response', 'spike'),
                ('response', 'i', 'post', 'i_ext'),
                ('plasticity', 'fixed_weight', 'response', 'weight')],
            delay=self.delay)

        # =====================================================================
        # Construct the Network
        # =====================================================================

        network = Network(
            name="Net",
            populations=(pop1, pop2, pop3),
            projections=(proj1, proj2, proj3, proj4))

        # =====================================================================
        # Create expected dynamics arrays
        # =====================================================================

        dyn_array1 = ComponentArray(
            "Pop1", pop1.size,
            MultiDynamicsWithSynapsesProperties(
                "Pop1_cell",
                MultiDynamicsProperties(
                    "Pop1_cell",
                    sub_components={
                        'cell': cell1,
                        'Proj2': MultiDynamicsProperties(
                            name='Proj2_syn',
                            sub_components={'psr': exc.clone(),
                                            'pls': static.clone()},
                            port_connections=[
                                ('pls', 'fixed_weight', 'psr', 'weight')],
                            port_exposures=[
                                ('psr', 'i'),
                                ('psr', 'spike'),
                                ('psr', 'double_spike')]),
                        'Proj4': MultiDynamicsProperties(
                            name='Proj4_syn',
                            sub_components={'psr': exc.clone(),
                                            'pls': static.clone()},
                            port_connections=[
                                ('pls', 'fixed_weight', 'psr', 'weight')],
                            port_exposures=[
                                ('psr', 'i'),
                                ('psr', 'spike')])},
                    port_connections=[
                        ('Proj2', 'i__psr', 'cell', 'i_ext'),
                        ('Proj4', 'i__psr', 'cell', 'i_ext')],
                    port_exposures=[
                        ('cell', 'spike'),
                        ('Proj2', 'double_spike__psr'),
                        ('Proj2', 'spike__psr'),
                        ('Proj4', 'spike__psr')]),
                connection_property_sets=[
                    ConnectionPropertySet(
                        'spike__psr__Proj2',
                        [Property('weight__pls__Proj2', random_weight)]),
                    ConnectionPropertySet(
                        'double_spike__psr__Proj2',
                        [Property('weight__pls__Proj2', random_weight)]),
                    ConnectionPropertySet(
                        'spike__psr__Proj4',
                        [Property('weight__pls__Proj4', random_weight)])]))

        dyn_array2 = ComponentArray(
            "Pop2", pop2.size,
            MultiDynamicsWithSynapsesProperties(
                "Pop2_cell",
                MultiDynamicsProperties(
                    "Pop2_cell",
                    sub_components={
                        'cell': cell2,
                        'Proj1': MultiDynamicsProperties(
                            name='Proj1_syn',
                            sub_components={'psr': inh.clone(),
                                            'pls': static.clone()},
                            port_connections=[
                                ('pls', 'fixed_weight', 'psr', 'weight')],
                            port_exposures=[
                                ('psr', 'i'),
                                ('psr', 'spike')])},
                    port_connections=[
                        ('Proj1', 'i__psr', 'cell', 'i_ext')],
                    port_exposures=[
                        ('cell', 'spike'),
                        ('cell', 'double_spike'),
                        ('Proj1', 'spike__psr'),
                        ('cell', 'i_ext')]),
                connection_property_sets=[
                    ConnectionPropertySet(
                        'spike__psr__Proj1',
                        [Property('weight__pls__Proj1', random_weight)])],
                synapse_propertiess=[
                    SynapseProperties(
                        name='Proj3',
                        dynamics_properties=MultiDynamicsProperties(
                            name='Proj3_syn',
                            sub_components={'psr': exc,
                                            'pls': stdp},
                            port_connections=[
                                AnalogPortConnection(
                                    'wsyn_current', 'weight',
                                    sender_name='pls', receiver_name='psr')],
                            port_exposures=[('psr', 'spike'),
                                            ('pls', 'incoming_spike'),
                                            ('psr', 'i')]),
                        port_connections=[
                            AnalogPortConnection(
                                'i__psr__Proj3', 'i_ext__cell__reduce',
                                sender_role='synapse',
                                receiver_role='post')])]))

        dyn_array3 = ComponentArray(
            "Pop3", pop3.size,
            MultiDynamicsWithSynapsesProperties(
                "Pop3_cell",
                MultiDynamicsProperties(
                    'Pop3_cell',
                    sub_components={'cell': cell3},
                    port_exposures=[('cell', 'spike'),
                                    ('cell', 'i_ext')],
                    port_connections=[])))

        conn_group1 = EventConnectionGroup(
            'Proj1', dyn_array1, dyn_array2, 'spike__cell',
            'spike__psr__Proj1',
            connectivity=Connectivity(self.all_to_all, pop1.size, pop2.size),
            delay=self.delay)

        conn_group2 = EventConnectionGroup(
            'Proj2__pre__spike__synapse__spike__psr', dyn_array2,
            dyn_array1, 'spike__cell',
            'spike__psr__Proj2',
            connectivity=Connectivity(self.all_to_all, pop2.size, pop1.size),
            delay=self.delay)

        conn_group3 = EventConnectionGroup(
            'Proj2__pre__double_spike__synapse__double_spike__psr',
            dyn_array2, dyn_array1, 'double_spike__cell',
            'double_spike__psr__Proj2',
            connectivity=Connectivity(self.all_to_all, pop2.size, pop1.size),
            delay=self.delay)

        conn_group4 = EventConnectionGroup(
            'Proj3__pre__spike__synapse__spike__psr', dyn_array3,
            dyn_array2, 'spike__cell',
            'spike__psr__Proj3',
            connectivity=Connectivity(self.all_to_all, pop3.size, pop2.size),
            delay=self.delay)

        conn_group5 = EventConnectionGroup(
            'Proj3__pre__spike__synapse__incoming_spike__pls',
            dyn_array3, dyn_array2,
            'spike__cell',
            'incoming_spike__pls__Proj3',
            connectivity=Connectivity(self.all_to_all, pop3.size, pop2.size),
            delay=self.delay)

        conn_group6 = EventConnectionGroup(
            'Proj4', dyn_array3, dyn_array1,
            'spike__cell',
            'spike__psr__Proj4',
            connectivity=Connectivity(self.all_to_all, pop3.size, pop1.size),
            delay=self.delay)

        # =====================================================================
        # Test equality between network automatically generated dynamics arrays
        # and manually generated expected one
        # =====================================================================
        (component_arrays, connection_groups,
         _) = BasePype9Network._flatten_to_arrays_and_conns(network)

        self.assertEqual(
            component_arrays['Pop1'], dyn_array1,
            "Mismatch between generated and expected dynamics arrays:\n {}"
            .format(component_arrays['Pop1'].find_mismatch(dyn_array1)))
        self.assertEqual(
            component_arrays['Pop2'], dyn_array2,
            "Mismatch between generated and expected dynamics arrays:\n {}"
            .format(component_arrays['Pop2'].find_mismatch(dyn_array2)))
        self.assertEqual(
            component_arrays['Pop3'], dyn_array3,
            "Mismatch between generated and expected dynamics arrays:\n {}"
            .format(component_arrays['Pop3'].find_mismatch(dyn_array3)))
        # =====================================================================
        # Test equality between network automatically generated connection
        # groups and manually generated expected ones
        # =====================================================================
        self.assertEqual(
            connection_groups['Proj1'], conn_group1,
            "Mismatch between generated and expected connection groups:\n {}"
            .format(
                connection_groups['Proj1'].find_mismatch(conn_group1)))
        self.assertEqual(
            connection_groups['Proj2__pre__spike__synapse__spike__psr'],
            conn_group2,
            "Mismatch between generated and expected connection groups:\n {}"
            .format(
                connection_groups['Proj2__pre__spike__synapse__spike__psr']
                .find_mismatch(conn_group2)))
        self.assertEqual(
            connection_groups[
                'Proj2__pre__double_spike__synapse__double_spike__psr'],
            conn_group3,
            "Mismatch between generated and expected connection groups:\n {}"
            .format(
                connection_groups[
                    'Proj2__pre__double_spike__synapse__double_spike__psr']
                .find_mismatch(conn_group3)))
        self.assertEqual(
            connection_groups[
                'Proj3__pre__spike__synapse__spike__psr'],
            conn_group4,
            "Mismatch between generated and expected connection groups:\n {}"
            .format(
                connection_groups[
                    'Proj3__pre__spike__synapse__spike__psr']
                .find_mismatch(conn_group4)))
        self.assertEqual(
            connection_groups[
                'Proj3__pre__spike__synapse__incoming_spike__pls'],
            conn_group5,
            "Mismatch between generated and expected connection groups:\n {}"
            .format(
                connection_groups[
                    'Proj3__pre__spike__synapse__incoming_spike__pls']
                .find_mismatch(conn_group5)))
        self.assertEqual(
            connection_groups['Proj4'], conn_group6,
            "Mismatch between generated and expected connection groups:\n {}"
            .format(
                connection_groups['Proj4'] .find_mismatch(conn_group6)))
