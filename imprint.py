# General Imprinting Script that uses

import os
import numpy as np
from psp import Pv
from itertools import chain, izip
from blbase.iterscan import IterScan, _test_motor_factory
from blbase.motor import Motor
# from blbase.virtualmotor import VirtualMotor     #Commented out until fixed
from blinst.linac import Linac
from ConfigParser import SafeConfigParser
from docopt import docopt
from ast import literal_eval

defaultPath = "imprintConfigurations/imprintStandard.cfg"
PV_Attenuator = "GATT:FEE1:310:P_DES"

class Imprint(object):
	"""
	Object that implements the SXD imprint script for any number of motors.
	"""
	def __init__(self, **kwargs):
		"""Checks the file path and initializes the imprint parameters"""
		
		self._path = kwargs.get("path", defaultPath)
		self._burstMode = kwargs.get("burstMode", False)
		self._useMotors = kwargs.get("test", True)
		self._useAttenuator = kwargs.get("useAttenuator", False)
		self._verbose = kwargs.get("verbose", False)
		
		self._initParams()
		self._linac = self._initLinac()
	
	def _initParams(self):
		"""
		Parses the config file and initializes the motors, iterators, hooks, and
		IterScan object
		"""
		self._parseConfig()
		self._checkConfig()
		self._positionIterators = self._initIterators()

		self._a_iterator = chain.from_iterable([float(x)]*self.xRange for x in self.attenuatorString.split())
		self._iteratorY = (self.yfrom + i*self.deltaY for i in range(self.yRange))
		self._iteratorZ = (self.zfrom + i*self.deltaZ for i in range(self.yRange))
		self._iterators = [(self.xfrom + i*self.deltaX for i in range(self.xRange)), 
						   izip(self._iteratorY, self._iteratorZ)]
		self._xPositions = list(self._iterators[0])
		self._yPositions = list(self._iterators[1])

		if not self._test:
			self._motorY = Motor(self.PV_y, name = "yMotor")
			self._motorZ = Motor(self.PV_z, name = "zMotor")
			self._motors = [Motor(self.PV_x, name = "xMotor"),
			                self._get_vmotor_pair(self._motorY, self._motorZ)]
		else:
			self._motorY = _test_motor_factory("yMotor", speed=1)
			self._motorZ = _test_motor_factory("zMotor", speed=1)
			self._motors = [_test_motor_factory("xMotor", speed=1),
			                self._get_vmotor_pair(self._motorY, self._motorZ)]
		self._hooks = self._get_Hook()
		self._Scan = IterScan(self._motors[0], self._motors[1],
		                      self._iterators[0], self._iterators[1], 
		                      self._hooks)
		self._allMotors = [self._motors[0], self._motorY, self._motorZ]


	def _parseConfig(self):
		"""Parses the config file and sets all the values for imprint"""
		self._checkPath(self._path)
		self._parser = SafeConfigParser()
		self._parser.read(self._path)
		self._useMotors = self._parseBoolParam("Motors", "useMotors")
		self._motors = self._parseMotorParams("Motors", "motors")
		self._intialPositions = self._parseFloatParam("Motors","initalPositions")
		self._deltas = self._parseFloatParam("Motors", "deltas")
		self._numSteps = self._parseFloatParam("Motors", "numSteps")
		self._useAttenuator = self._parseBoolParam("GasAttenuator",
		                                           "useAttenuator")
		self._attenutatorValues = self._parseFloatParam("GasAttenutator",
		                                                "attenuatorValues")
		self._loopOnMotorsAtten = self._parseIntParam("GasAttenuator", 
		                                              "loopOnMotors")
		self._burstMode = self._parseBoolParam("Linac", "burstMode")
		self._numShots = self._parseFloatParam("Linac", "numShots")
		self._loopOnMotorsNumShots = self._parseIntParam("Linac", "loopOnMotors")

	def _checkPath(self, path):
		"""Checks if the given path is correct."""
		if not os.path.isfile(path):
			raise configPathError(path)

	def _parseBoolParam(self, section, subSection):
		"""Parses boolean cfg entries to make sure they are True or False."""
		boolStr = self._parser.get(section, subSection)
		if boolStr.lower() == "true" or boolStr.lower() == "t":
		    return True
		elif bookStr.lower() == "false" or bookStr.lower() == "f":
		    return False
		else:
			raise ValueError("Entry for section '{0}', subsection '{1}' is not 
valid. Must be True/False or T/F (not case sensitive).").format(section,
                                                                subsection)
		
	def _parseMotorParams(self, section, subsection):
		"""Parses the PV config entries into a list of strs and tuples."""
		pvStr = self._parser.get(section, subSection)
		motorPVs = literal_eval(pvStr)
		motors = []
		for motorPV in motorPVs:
			if type(motorPV) is str:
			    motors.append(Motor(motorPV, name = Pv.get(motorPV+".DESC")))
			else:
			    motors.append(VirtualMotor(motorPV))
		return motors

	def _parseFloatParam(self, section, subsection):
		"""Parses list/tuples of floats, subsituting string values for nan."""
		floatStr = self._parser.get(section, subsection)
	    floatEval = literal_eval(floatStr)
	    floatList = []
	    for val in floatList:
		    try:
			    floatList.append(float(val))
			except ValueError:
				floatList.append(float('nan'))
		    except TypeError:
			    floatTuple = []
			    for tupVal in floatTuple:
				    try:
					    floatTuple.append(float(tupVal))
					except ValueError:
						floatTuple.append(float('nan'))
				floatList.append(floatTuple)
		return floatList
	
	def _parseIntParam(self, section, subsection):
		"""Parses an number or a list of numbers into a list of ints.""" 
		intStr = self._parser.get(section, subsection)
		try:
			return [int(val) for val in literal_eval(intStr)]
		except TypeError:
			return [int(val) for val in list(literal_eval(intStr))]

	def _checkConfig(self):
		"""
		Checks all the parsed values to make sure they are all the correct sizes
		and shapes.
		"""
		numPositions, numMotors, numDeltas = [], [], []
		for motor, pos, delta in zip(self._motors, self._initialPositions, 
		                             self.deltas):
			try:
				numMotors.append(motor.numMotors)
			except AttributeError:
				numMotors.append(1)
			try:
				numPositons.append(len(pos))
			except TypeError:
				numPositions.append(len([pos]))
			try:
				numDeltas.append(len(delta))
			except TypeError:
				numDeltas.append(len([delta]))
		if numMotors != numPositions:
			raise SizeMismatchError("Motors", "initialPositions", numMotors,
			                        initialPositions)
		elif numMotors != numDeltas:
			raise SizeMismatchError("Motors", "Deltas", numMotors, numDeltas)			
		elif len(numMotors) != len(self._numSteps):
			raise SizeMismatchError("Motors", "numSteps", numMotors, 
			                        self._numSteps)
		if self._useAttenuator:
			self._checkNumSteps(self._loopOnMotorsAtten, self._attenuatorValues,
			                    "Attenutation")
		if self._burstMode:
			self._checkNumSteps(self._loopOnMotorsNumShots, self._numShots,
			                    "numShots")
		# Passed Check

	def _checkNumSteps(self, loopOnMotors, vals, name):
		"""
		Checks if the number of values in vals corresponds with the loopOnMotors 
		and numSteps.
		"""
		loopOnMotorBinary = [1 if x in loopOnMotors else 0 
		                     for x in xrange(len(self._numSteps))]
		expectedNumVals = sum(loopVal*steps for loopVal, steps in zip(
			loopOnMotorBinary, self._numSteps))
		if expectedNumVals != len(vals):
			raise SizeMismatchError("Expected Number of {0} Values".format(name),
			                        "Number of inputted {0} Values".format(name),
			                        expectedNumVals, len(self._numShots))
		
	def _initIterators(self):
		"""Creates a list of iterators that correspond to the inputted motors."""
		initPos = self._initialPositons
		deltas = self._deltas
		steps = self._numSteps
		iterators = []
		for pos, delta, step in zip(initPos, deltas, steps):
			try:
				iterator = (self._addTup(pos, self._multTup(i,delta)) 
				            for i in xrange(step))
			except:
				pass

	def _addTup(self, tupleA, tupleB):
		"""
	    Method that does elemental addition of tuples and returns a the sum as
	    a tuple of the same length.
	    """
		return tuple(np.array(tupleA) + np.array(tupleB))

	def _multTup(self, tupleA, tupleB):
		"""
		Method that does elemental multiplication of tuples and returns the
		product as a tupe of the same length.
		"""
		return tuple(np.array(tupleA) * np.array(tupleB))
		

	def _get_Hook(self):
		"""Returns a hook object that defines motor hooks"""
		class imprint_Hook(object):
			def __init__(self, attenuator, PV_attenuator, a_iterator, burst, 
			             test, do_print, motors):
				self._linac = Linac()
				self._attenuator = attenuator
				self._PV_attenuator = PV_attenuator
				self._a_iterator = a_iterator
				self._burst = burst
				self._test = test
				self._do_print = do_print
				self._motors = motors
				self.n_hook_calls = [0, 0, 0, 0]
				self.pos_vectors = []
			def pre_scan(self, scan):
			    self.n_hook_calls[0] += 1
			def post_scan(self, scan):
			    self.n_hook_calls[1] += 1
			def pre_step(self, scan):
			    self.n_hook_calls[2] += 1
			def post_step(self, scan):
				self.n_hook_calls[3] += 1
				self.pos_vectors.append(scan.get_positions())
				if not self._test:
					if self._attenuator:
						try:
							val = self._a_iterator.next()
							Pv.put(PV_attenuator, val)
							Pv.wait_for_value(PV_attenuator+".RBV", val)
						except: pass
					if self._burst:
						self._linac.start_burst()
						self._linac.
				if self._do_print:
					for motor in self._motors:
						print motor.name, motor.wm()

		return imprint_Hook(self._attenuator, self.PV_attenuator, 
		                    self._a_iterator, self._burst, self._test, 
		                    self._do_print, self._motors)
	
	def test_imprint(self):
		"""
		Runs the test if test is set to true. If false, it reinitializes motors
		as virtual motors and runs the test, reinitializing it back again when
		it completes
		"""
		self._Scan.do_print = self._do_print
		if self._test:
		    self._Scan.scan_mesh()
		else:
			self._test = True
			self._init_params()
			self._Scan.scan_mesh()
			self._test = False
			self._init_params()

	def run(self):
		"""Runs the scan"""
		if not self._test:
			self._Scan.scan_mesh()
		else: print "Currently in test mode"

	@property
	def path(self): return self._path

	@path.setter
	def path(self, val):
		if os.path.isfile(val):
			self._path = val
			self._init_params()
		else: print "Invalid path"

	@property
	def test(self):
		return self._test

	@test.setter
	def test(self, val):
		if type(val) is bool:
			self._test = val
			self._init_params()
		else: print "Please enter True or False"

	@property
	def burst(self):
		return self._burst

	@burst.setter
	def burst(self, val):
		if type(val) is bool:
			self._burst = val
			self._init_params()
		else: print "Please enter True or False"

	@property
	def status(self):
	    return self._get_status()

	@status.setter
	def status(self, val):
		print "Error: Cannot set status"

	@property
	def attenuator(self):
		return self._attenuator

	@attenuator.setter
	def attenuator(self, val):
		if type(val) is bool:
			self._attenuator = val
		else: print "Please enter True or False"

	@property
	def do_print(self):
		return self._do_print

	@do_print.setter
	def do_print(self, val):
		if type(val) is bool:
			self._do_print = val
		else: print "Please enter True or False"

	def _get_status(self):
		"""Print imprint paramters"""
		str = "Initial X position: {0}  Delta X: {1}".format(self.xfrom, self.deltaX)
		str += "\nInitial Y position: {0}  Delta Y: {1}".format(self.yfrom, self.deltaY)
		str += "\nInitial Y position: {0}  Delta Z: {1}".format(self.zfrom, self.deltaZ)
		str += "\nAll attenuator Values:\n"
		str += self.attenuatorString
		str += "\nRange X: {0}  Range Y: {0}.".format(self.xRange, self.yRange)
		str += "\nX Motor PV:    {0}".format(self.PV_x)
		str += "\nY Motor PV:    {0}".format(self.PV_y)
		str += "\nZ Motor PV:    {0}".format(self.PV_z)
		str += "\nAttenuator PV: {0}".format(self.PV_attenuator)
		return str

class VirtualMotor(object):
	"""Virtual motor class until the real one works."""
	def __init__(self, motors):
		self._motorPVs = motors
		self._motors = self._getMotors(self._motorPVs)
		self.numMotors = len(self._motors)
		self.name = ""
		for motor in self._motors:
			self.name += motor.name + "+"
		self.name = self.name[:-1]
	def _getMotors(self, motorPVs):
		motorNames = [Pv.get(motorPV+".DESC") for motorPV in motorPVs]
		return [Motor(motor, name=motorName) for motor,motorName in zip(
			motorPVs, motorNames)]
	def mv(self, vals):
		if len(val) == len(self._motors):
			for motor, val in zip(self._motors, vals):
				motor.mv(val)
		else:
			raise ValueError("Motor and position mismatch: {0} motors with {1}
inputted motions.".format(len(self._motors), len(vals)))
	def wm(self):
		return [motor.wm() for motor in self._motors]
	def wait(self):
		for motor in self._motors:
			motor.wait()
		
# Exception Classes
class Error(exception):
	"""Base class for exceptions in this module."""
    pass

class ConfigPathError(Error):
	"""Exception raised if the inputted config path is invalid."""
	def __init__(self, path):
		self.path = path
	def __str__(self):
		return repr("Invalid path to cfg: {0}.".format(self.path))

class SizeMismatchError(Error):
	"""
	Exception raised if the inputted cfg values do not have the correct 
	corresponding shapes.
	"""
	def __init__(self, nameA, nameB, lenA, lenB):
		self._nameA = nameA
		self._nameB = nameB
		self._lenA = lenA
		self._lenB = lenB
	def __str__(self):
		return repr("Config values for '{0}' and '{1}' have incorrect corresponing
sizes {2} and {3}.".format(self._nameA, self.nameB, self._lenA, self._lenB)
	

if __name__ == "__main__":
	arguments = docopt(__doc__)
	
	if arguments["--burst"]:
		print "Burst mode selected."
	
	imprint = ImprintAngle(arguments["--path"], 
	                       arguments["--burst"], 
	                       arguments["--test"])
	if not arguments["--test"]:
		imprint.run()
	else:
		imprint.test_imprint()

	
