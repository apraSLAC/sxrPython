# General Imprinting Script that uses

import os
import numpy as np
from psp import Pv
from itertools import chain, izip, repeat
from blbase.iterscan import IterScan
from blbase.motor import Motor
# from blbase.virtualmotor import VirtualMotor     #Commented out until fixed
from blinst.linac import Linac
from ConfigParser import SafeConfigParser
from ast import literal_eval
from math import isnan

defaultPath = "imprintConfigurations/imprintStandard.cfg"
pvAttenuator = "GATT:FEE1:310:P_DES"

class Imprint(object):
	"""
	Object that implements the SXD imprint script for any number of motors.
	"""
	def __init__(self, **kwargs):
		"""Checks the file path and initializes the imprint parameters."""
		self._path          = kwargs.get("path", defaultPath)
		self._burstMode     = kwargs.get("burstMode", False)
		self._useMotors     = kwargs.get("useMotors", True)
		self._useAttenuator = kwargs.get("useAttenuator", False)
		self._verbose       = kwargs.get("verbose", True)
		self._parser        = None        #Parser object for parsing the cfg
		self._imprintHooks  = None        #Hooks object that holds step hooks
		self._scan          = None        #IterScan object that does the scan
		self._initParams()
	
	def _initParams(self):
		"""
		Parses the config file and initializes the motors, iterators, hooks, and
		IterScan object.
		"""
		self._parseConfig()
		self._checkConfig()
		self._motorIterators = self._initMotorIterators()
		self._gasAttenIterator = self._initIterator(
			self._loopOnStepsAtten,
			self._attenuatorValues,
			self._substitutionsAtten,
			self._substitutionIndicesAtten)
		self._linacIterator = self._initIterator(
			self._loopOnStepsNumShots,
			self._numShots,
			self._substitutionsLinac,
			self._substitutionIndicesLinac)
		self._imprintHooks = self._initHooks()
		self._scan = IterScan(self._imprintHooks, 
							  *(self._motors + self._motorIterators))

	def _parseConfig(self):
		"""Parses the config file and sets all the values for imprint."""
		self._checkPath(self._path)
		self._parser = SafeConfigParser()
		self._parser.read(self._path)
		self._useMotors = self._parseBoolParam(
			"Motors", "useMotors")
		self._motors = self._parseMotorParams(
			"Motors", "motors")
		self._initialPositions = self._parseFloatParam(
			"Motors", "initialPositions")
		self._numSteps = self._parseIntParam(
			"Motors", "numSteps")
		self._deltas = self._parseFloatParam(
			"Motors", "deltas")
		self._loopOnStepsDelta = self._parseIntParam(
			"Motors", "loopOnSteps")
		self._substitutionsDelta = self._parseFloatParam(
			"Motors", "substitutions")
		self._substitutionIndicesDelta = self._parseIndicesParam(
			"Motors", "substitutionIndices")
		self._useAttenuator = self._parseBoolParam(
			"GasAttenuator", "useAttenuator")
		self._attenuatorValues = self._parseFloatParam(
			"GasAttenuator", "attenuatorValues")
		self._loopOnStepsAtten = self._parseIntParam(
			"GasAttenuator", "loopOnSteps")
		self._substitutionsAtten = self._parseFloatParam(
			"GasAttenuator", "substitutions")
		self._substitutionIndicesAtten = self._parseIndicesParam(
			"GasAttenuator", "substitutionIndices")
		self._burstMode = self._parseBoolParam(
			"Linac", "burstMode")
		self._numShots = self._parseFloatParam(
			"Linac", "numShots")
		self._loopOnStepsNumShots = self._parseIntParam(
			"Linac", "loopOnSteps")
		self._substitutionsLinac = self._parseFloatParam(
			"Linac", "substitutions")
		self._substitutionIndicesLinac = self._parseIndicesParam(
			"Linac", "substitutionIndices")
		# print self._initialPositions, self._deltas, self._numSteps
		# Add a custom section to config file where people can specify other
		# things theyd like to do at each step. It would work very similarly to
		# linac and gasAtten with added options like:
		# # Pv to change the values of 
		# # RBV Pv to wait for once a change was made

	def _checkPath(self, path):
		"""Checks if the given path is correct."""
		if not os.path.isfile(path):
			raise configPathError(path)

	def _parseBoolParam(self, section, subSection):
		"""Parses boolean cfg entries to make sure they are True or False."""
		boolStr = self._parser.get(section, subSection)		
		if boolStr.lower() == "true" or boolStr.lower() == "t":
			return True
		elif boolStr.lower() == "false" or boolStr.lower() == "f":
			return False
		else:
			raise ValueError("Entry for section '{0}', subSection '{1}' is not \
valid. Must be True/False or T/F (not case sensitive).").format(section,
																subSection)
		
	def _parseMotorParams(self, section, subSection):
		"""Parses the PV config entries into a list of strs and tuples."""
		pvStr    = self._parser.get(section, subSection)
		motorPVs = literal_eval(pvStr)
		motors   = []
		for motorPV in motorPVs:
			if isinstance(motorPV, str):
				motors.append(Motor(motorPV, name = Pv.get(motorPV+".DESC")))
			else:
				motors.append(VirtualMotor(motorPV))
		return tuple(motors)

	def _parseFloatParam(self, section, subSection):
		"""
		Parses list/tuples of floats, subsituting string values for nan. If
		multi is set to True, it will separate the lists into separate lists and
		return that list of lists.
		"""
		floatStr  = self._parser.get(section, subSection)
		floatEval = literal_eval(floatStr)
		floatList = []
		for val in floatEval:
			try:
				floatList.append(float(val))
			except ValueError:
				floatList.append(float('nan'))
			except TypeError:
				inList = []
				for inVal in val:
					try:
						inList.append(float(inVal))
					except ValueError:
						inList.append(float('nan'))
				floatList.append(inList)
		return floatList

	def _parseIntParam(self, section, subSection):
		"""Parses a number or a list of numbers into a list of ints.""" 
		intStr = self._parser.get(section, subSection)
		try:
			return [int(val) for val in literal_eval(intStr)]
		except TypeError:
			return [int(val) for val in list(literal_eval(intStr))]

	def _parseIndicesParam(self, section, subSection):
		"""Parses indices into a list of lists."""
		idxStr = self._parser.get(section, subSection)
		return literal_eval(idxStr)

	def _checkConfig(self):
		"""
		Checks all the parsed values to make sure they are all the correct sizes
		and shapes.
		"""
		numPositions, numMotors, numDeltas = [], [], []
		for motor, pos, delta in zip(self._motors, self._initialPositions, 
		                             self._deltas):
			try: numMotors.append(motor.numMotors)
			except AttributeError:
				numMotors.append(1)
			try: numPositions.append(len(pos))
			except TypeError:
				numPositions.append(len([pos]))
			try: numDeltas.append(len(delta[0]))
			except TypeError:
				numDeltas.append(len([delta[0]]))
		if numMotors != numPositions:
			raise SizeMismatchError("Motors", "initialPositions", 
			                        numMotors, initialPositions)
		elif numMotors != numDeltas:
			raise SizeMismatchError("Motors", "Deltas", 
			                        numMotors, numDeltas)			
		elif len(numMotors) != len(self._numSteps):
			raise SizeMismatchError("Motors", "numSteps", 
			                        numMotors, self._numSteps)
		if self._useAttenuator:
			self._checkNumSteps(self._loopOnStepsAtten, 
			                    self._attenuatorValues,
								"Attenutation")
		if self._burstMode:
			self._checkNumSteps(self._loopOnStepsNumShots, 
			                    self._numShots,
			                    "numShots")
		if (len(self._substitutionsDelta) != len(self._substitutionIndicesDelta)
		    and (len(self._substitutionsDelta) == 0 and 
		         len(self._substitutionIndicesDelta) != 1)):
			raise SizeMismatchError("Delta Substitutions", 
			                        "Delta Substitution Indices", 
			                        len(self._substitutionsDelta),
			                        len(self._substitutionIndicesDelta))
		if (len(self._substitutionsAtten) != len(self._substitutionIndicesAtten)
			and (len(self._substitutionsAtten) == 0 and 
			     len(self._substitutionIndicesAtten) != 1)):
			raise SizeMismatchError("Attenuator Values Substitutions", 
			                        "Attenuator Values Substitution Indices", 
			                        len(self._substitutionsAtten),
			                        len(self._substitutionIndicesAtten))
		if (len(self._substitutionsLinac) != len(self._substitutionIndicesLinac)
		    and (len(self._substitutionsLinac) == 0 and 
		         len(self._substitutionIndicesLinac) != 1)):
			raise SizeMismatchError("numShots Substitutions", 
			                        "numShots Substitution Indices", 
			                        len(self._substitutionsLinac),
			                        len(self._substitutionIndicesLinac))
		# Decide on a way to handle multiple deltas and then write the sub idx
		# to delta check. 
		
		# Passed Check

	def _checkNumSteps(self, loopOnSteps, vals, name):
		"""
		Checks if the number of values in vals corresponds with the loopOnSteps 
		and numSteps.
		"""
		loopOnMotorBinary = [1 if x in loopOnSteps else 0 
							 for x in xrange(len(self._numSteps))]
		expectedNumVals = sum(loopVal*steps for loopVal, steps in zip(
			loopOnMotorBinary, self._numSteps))
		if expectedNumVals != len(vals):
			raise SizeMismatchError("Expected Number of {0} Values".format(name),
									"Number of inputted {0} Values".format(name),
									expectedNumVals, len(self._numShots))
		
	def _initMotorIterators(self):
		"""
		Creates a list of iterators that correspond to the inputted motors. It
		can handle motor groups by returning izip-ped iterators for each motor.
		"""
		initPos             = self._initialPositions
		deltas              = self._deltas
		steps               = self._numSteps
		loopOnStepsDelta    = self._loopOnStepsDelta
		substitutions       = self._substitutionsDelta
		substitutionIndices = self._substitutionIndicesDelta
		deltaLists          = []
		posLists            = []
		for delta, loopMot in zip(delta, loopOnStepsDelta):
			if isinstance(delta, list) or isinstance(delta, tuple):
				for inDelta in delta:
					deltaLists.append(self._buildIterList(loopMot,inDelta,steps))
			else:
				deltaLists.append(self._buildIterList(loopMot, delta, steps))
		try:
			for sub, idx in zip(substitutions, substitutionIndices):
				try:
					flatIdx = np.sum(val * np.prod(steps[i+1:]) for i, val in 
					                 enumerate(idx[1:]))
				except TypeError:
					flatIdx = idx[1]
				deltaLists[[idx[0]]][int(flatIdx)] = float(sub)
		except ValueError: 
			pass                          #Do nothing if substitutions is empty
		for i, (pos, step) in enumerate(zip(initPos, steps)):
			if isinstance(pos, tuple) or isinstance(pos, list):
				for inPos in pos:
					deltaList = deltaLists[::-1].pop()					
					posList = [delta + deltaList[i-1] if i % steps else 
					           delta + inPos for i,delta in enumerate(deltaList)]
			else:
				deltaList = deltaLists[::-1].pop()
				posList = [delta + deltaList[i-1] if i%steps else delta + pos
					       for i, delta in enumerate(deltaList)]
			posLists.append(posList)
		return iter(zip(*posLists))
		
	def _buildIterList(self, loopOnSteps, vals, steps):
		"""
		Method that builds a flattened list of values of the correct size based
		on the inputted values, the dimensions to loop on, and the total number
		of steps.
		"""
		newVals = np.array(vals)
		if loopOnSteps:
			valShape = self._getValShape(loopOnSteps, steps)
			if newVals.shape != valShape:
				newVals = newVals.reshape(valShape)
		for i, step in enumerate(steps):
			if i not in loopOnSteps:
				newVals = np.repeat(np.expand_dims(newVals,axis=i), step, axis=i)
		return list(newVals.flatten())

	def _initIterator(self, loopOnSteps, vals, substitutions, indices):
		"""
		Method that returns a generator to be used by the iterscan object.
		"""
		# Build as a list
		iterList = self._buildIterList(loopOnSteps, vals, self._numSteps)
		substitutedList = list(vals)
		for sub, i in zip(substitutions, indices):
			substitutedList[tuple(np.array(i))] = sub
		return iter(substitutedList)

	def _prod(self, vals):
		"""Returns the product of all the inputted values."""
		return np.cumprod(np.array(shape).flatten())[-1]

	def _getValShape(self, loopOnSteps, steps):
		"""
		Returns the shape that the inputted values should be given the loop 
		dimensions and the steps in each dimension.
		"""
		loopOnSteps.sort()
		return tuple([steps[dim] for dim in loopOnSteps])

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
		"""Runs the scan."""
		self._scan.scan_mesh(do_print = self._verbose)
		
	def update(self):
		"""Rereads the values from the cfg file."""
		self._initParams()

	@property
	def path(self): 
		return self._path

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
		if isinstance(val, bool):
			self._useMotor = val
			self._init_params()
		else: print "Please enter True or False"

	@property
	def burstMode(self):
		return self._burstMode

	@burstMode.setter
	def burstMode(self, val):
		if isinstance(val, bool):
			self._burstMode = val
			self._init_params()
		else: print "Please enter True or False"

	@property
	def useAttenuator(self):
		return self._useAttenuator

	@useAttenuator.setter
	def useAttenuator(self, val):
		if isinstance(val, bool):
			self._useAttenuator = val
		else: print "Please enter True or False"

	@property
	def verbose(self):
		return self._verbose

	@verbose.setter
	def verbose(self, val):
		if isinstance(val, bool):
			self._verbose = val
		else: print "Please enter True or False"

class VirtualMotor(object):
	"""Virtual motor class until the real one works."""
	def __init__(self, motors):
		self._motorPVs = motors
		self._motors   = self._getMotors(self._motorPVs)
		self.numMotors = len(self._motors)
		self.name      = ""
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
		self._numShots         = kwargs.get("numShots", None)
		self._useAttenuator    = kwargs.get("useAttenuator", False)
		self._attenuatorValues = kwargs.get("attenuatorValues", None)
		self._burstMode        = kwargs.get("burstMode", False)
		self._useMotors        = kwargs.get("useMotors", True)
		self._verbose          = kwargs.get("verbose", False)
		self._motors           = kwargs.get("motors", None)
		self._linac            = Linac()
		self._attenStatus      = ""
		self._linacStatus      = ""
		self.nHookCalls        = [0, 0, 0, 0]
		self.posVectors        = []
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
class Error(Exception):
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
	Exception raised if the inputted values do not have the correct 
	corresponding shapes.
	"""
	def __init__(self, nameA, nameB, lenA, lenB):
		self._nameA = nameA
		self._nameB = nameB
		self._lenA  = lenA
		self._lenB  = lenB
	def __str__(self):
		return repr("Values for '{0}' and '{1}' have incorrect \
corresponing sizes {2} and {3}.".format(self._nameA, self._nameB, 
                                        self._lenA, self._lenB))
	
scan = Imprint()
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
