if __name__ == '__main__':
    from utils import DummyTestCase as TestCase  # @UnusedImport
else:
    from unittest import TestCase  # @Reimport
# from pype9.cells.neuron import CellMetaClass
from os import path
from utils import test_data_dir
import neuron
from neuron import h, load_mechanisms
import pylab as plt
from pype9.cells.neuron import CellMetaClass

# from pyNN.neuron.cells import Izhikevich_ as IzhikevichPyNN
# MPI may not be required but NEURON sometimes needs to be initialised after
# MPI so I am doing it here just to be safe (and to save me headaches in the
# future)

from math import pi
import pyNN  # @UnusedImport


class TestNeuronLoad(TestCase):

    izhikevich_file = path.join(test_data_dir, 'xml', 'Izhikevich2003.xml')
    izhikevich_name = 'Izhikevich9ML'

    def test_neuron_load(self):
        Izhikevich9ML = CellMetaClass(self.izhikevich_file,
                                      name=self.izhikevich_name,
                                      build_mode='compile_only', verbose=True,
                                      membrane_voltage='V',
                                      membrane_capacitance='Cm')
        nml = Izhikevich9ML()
        pyNN_sec = h.Section()
        pyNN_sec.L = 10
        pyNN_sec.diam = 10 / pi
        pyNN_sec.cm = 1.0
        pyNN_izhi = h.Izhikevich(0.5, sec=pyNN_sec)  # @UnusedVariable
        # PyNN version
        for sec in (nml.source_section, pyNN_sec):
            # Specify current injection
            stim = h.IClamp(1.0, sec=sec)
            stim.delay = 1   # ms
            stim.dur = 100   # ms
            stim.amp = 0.2   # nA
            # Record Time from NEURON (neuron.h._ref_t)
            rec_t = neuron.h.Vector()
            rec_t.record(neuron.h._ref_t)
            # Record Voltage from the center of the soma
            rec_v = neuron.h.Vector()
            rec_v.record(sec(0.5)._ref_v)
            neuron.h.finitialize(-60)
            neuron.init()
            neuron.run(5)
            plt.plot(rec_t, rec_v)
        plt.show()


if __name__ == '__main__':
    t = TestNeuronLoad()
    t.test_neuron_load()
