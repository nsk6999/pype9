"""

  This module contains extensions to the pyNN.space module
  
  @author Tom Close

"""

#######################################################################################
#
#    Copyright 2012 Okinawa Institute of Science and Technology (OIST), Okinawa, Japan
#
#######################################################################################
from abc import ABCMeta
import quantities
import nineml.user_layer
import pyNN.space
from pyNN.random import NumpyRNG, RandomDistribution
import nineline.pyNN.random
import nineline.pyNN.structure.layout

class Structure(object):
        
    def __init__(self, name, size, nineml_model, rng=None):
        self.name = name
        self.size = size
        self._positions = None
        LayoutClass = getattr(nineline.pyNN.structure.layout, 
                              nineml_model.layout.definition.component.name)
        self.layout = LayoutClass(size, nineml_model.layout.parameters, rng)
        
    @property
    def positions(self):
        if not self._positions:
            self._positions = self.layout.generate_positions(self.size)
        return self._positions
