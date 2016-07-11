# General Imprinting Script that uses

import os
import numpy as np
from psp import Pv
from itertools import chain, izip
from blbase.iterscan import IterScan
from blbase.motor import Motor
# from blbase.virtualmotor import VirtualMotor     #Commented out until fixed
from blinst.linac import Linac
from ConfigParser import SafeConfigParser
from docopt import docopt
from ast import literal_eval
from math import isnan

defaultPath = "imprintConfigurations/imprintStandard.cfg"
pvAttenuator = "GATT:FEE1:310:P_DES"

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
	
	def _initParams(self):
		"""
		Parses the config file and initializes the motors, iterators, hooks, and
		IterScan object
		"""
		# Maybe move this back into the init
		self._parseConfig()
		self._checkConfig()
		self._positionIterators = self._initIterators()
		self._imprintHooks = self._initHooks()
		self._scan = IterScan(self._imprintHooks, 
							  *(self._motors, self._postionIterators))

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
			raise ValueError("Entry for section '{0}', subsection '{1}' is not \
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
		"""
		Creates a list of iterators that correspond to the inputted motors. It
		can handle motor groups by returning izip-ped iterators for each motor.
		"""
		initPos = self._initialPositons
		deltas = self._deltas
		steps = self._numSteps
		iterators = []
				
		for pos, delta, step in zip(initPos, deltas, steps):
			if type(pos) is not tuple or type(delta) is not tuple:
			    iterators.append((pos + delta*i for i in xrange(step)))
			else:
				iterator = []
				for inPos, inDelta in zip(pos, delta):
					iterator.append(inPos + inDelta*i for i in xrange(step))
				iterators.append(izip(*iterator))
		return iterators

	def _initHooks(self):
		"""Returns a hook object that defines motor hooks."""
		return imprintHooks(numshots         = self._numShots,
		                    useAttenutator   = self._useAttenuator,
		                    attenuatorValues = self._attenuatorValues,
		                    burstMode        = self._burstMode,
		                    useMotors        = self._useMotors,
		                    verbose          = self._verbose,
		                    motors           = self._motors)
	
	def test(self):
		"""
		Runs the scan in test mode. Will output the motor positions with each
		iteration.
		"""
		self._scan.test_mesh(do_print = self._verbose)

	def run(self):
		"""Runs the scan"""
		self._scan.scan_mesh(do_print = self._verbose)

	@property
	def path(self): return self._path

	@path.setter
	def path(self, val):
		if os.path.isfile(val):
			self._path = val
			self._init_params()
		else: print "Invalid path"

	@property
	def useMotor(self):
		return self._useMotor

	@useMotor.setter
	def useMotor(self, val):
		if type(val) is bool:
			self._useMotor = val
			self._init_params()
		else: print "Please enter True or False"

	@property
	def burstMode(self):
		return self._burstMode

	@burstMode.setter
	def burstMode(self, val):
		if type(val) is bool:
			self._burstMode = val
			self._init_params()
		else: print "Please enter True or False"

	@property
	def useAttenuator(self):
		return self._useAttenuator

	@useAttenuator.setter
	def useAttenuator(self, val):
		if type(val) is bool:
			self._useAttenuator = val
		else: print "Please enter True or False"

	@property
	def verbose(self):
		return self._verbose

	@verbose.setter
	def verbose(self, val):
		if type(val) is bool:
			self._verbose = val
		else: print "Please enter True or False"

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
			raise ValueError("Motor and position mismatch: {0} motors with {1} \
inputted motions.".format(len(self._motors), len(vals)))
	def wm(self):
		return [motor.wm() for motor in self._motors]
	def wait(self):
		for motor in self._motors:
			motor.wait()

class imprintHooks(object):
	"""Hook class used by the imprint class."""
	def __init__(self, **kwargs):
		self._numShots = kwargs.get("numShots", None)
		self._useAttenuator = kwargs.get("useAttenuator", False)
		self._attenuatorValues = kwargs.get("attenuatorValues", None)
		self._burstMode = kwargs.get("burstMode", False)
		self._useMotors = kwargs.get("useMotors", True)
		self._verbose = kwargs.get("verbose", False)
		self._motors = kwargs.get("motors", None)
		self._linac = Linac()
		self._attenStatus = ""
		self._linacStatus = ""
		self.nHookCalls = [0, 0, 0, 0]
		self.posVectors = []
	def pre_scan(self, scan):
		self.nHookCalls[0] += 1
	def post_scan(self, scan):
		self.nHookCalls[1] += 1
	def pre_step(self, scan):
		self.nHookCalls[2] += 1
	def post_step(self, scan):
		self.nHookCalls[3] += 1
		self.pos_vectors.append(scan.get_positions())
		if self._useMotors:
			if self._useAttenuator:
				try:
					attenVal = self._attenutatorValues.next()
					if not isnan(attenVal):
						Pv.put(pvAttenuator, attenVal)
						Pv.wait_for_value(pvAtenuator+".RBV", attenVal)
						self._attenStatus = "Reached {0}.".format(
							Pv.get(pvAtenuator+".RBV"))
					else: self._attenStatus = "Got NaN."
				except AttributeError:
					self._attenStatus = "Invalid input used."
				except:
					self._attenStatus = "Unkown error occured."
			else: self._attenStatus = "Not using gas attenuator."
			if self._burstMode:
				try:
					numShotsVal = self._numShots.next()
					if not isnan(numShotsVal):
						self._linac.get_burst(n=numShotsVal)
						self._linac.wait_for_shot(verbose=self._verbose)
						self._linacStatus = "Requested {0} shots.".format(
							numShotsVal)
					else: self._linacStatus = "Got NaN."
				except AttributeError:
					self._linacStatus = "Invalid input used."
				except:
					self._linacStatus = "Unkown error occured."
			else: self._linacStatus = "Not in burst mode."
		if self._verbose:
			print self._status()
	def _status(self):
		status = "Motor Positions:"
		for motor in self._motors:					
			status += "{0}: {1}".format(motor.name, motor.wm())
		status += "Gas Attenutator: {0}".format(self._attenStatus)
		status += "Linac: {0}".format(self._linacStatus)
		return status				
		
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
		return repr("Config values for '{0}' and '{1}' have incorrect \
corresponing sizes {2} and {3}.".format(self._nameA, self.nameB, 
                                        self._lenA, self._lenB))
	

# if __name__ == "__main__":
# 	arguments = docopt(__doc__)
	
# 	if arguments["--burst"]:
# 		print "Burst mode selected."
	
# 	imprint = ImprintAngle(arguments["--path"], 
# 	                       arguments["--burst"], 
# 	                       arguments["--test"])
# 	if not arguments["--test"]:
# 		imprint.run()
# 	else:
# 		imprint.test_imprint()
