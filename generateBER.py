###########################################################################
#
#   StatEye Simulator
#   by Jeremy Cosson-Martin, Jhoan Salinas
#   Ali Sheikholeslami's group
#   Department of Electrical and Computer Engineering
#   University of Toronto
#   Copyright Material
#   For personal use only
#
###########################################################################
# This function generates a BER distribution from the PDF eye distribution.
# It sweeps through the x and y-axis and determines how likely it is to 
# incorrectly measure a given bit. That is, for each sampling point, how
# much probability is on the wrong side of the threshold. This is performed
# for each sampler and the minimum value is taken from each.
#
# IMPORTANT: combined plot is not an accurate system BER measurement. The
# true system BER is the summation of the BER sampling points from their
# respective BER plots!!
#
# Inputs:
#   simSettings: structure containing simulation settings
#   simResults: structure containing simulation results
# 
# Outputs:
#   simResults: structure containing simulation results
#   
###########################################################################

from userSettingsObjects import simulationSettings
from initializeSimulation import simulationStatus
import numpy as np
import scipy.signal as spsig


class nothing:
    def __init__(self):
        pass

def generateBER(simSettings: simulationSettings, simResults: simulationStatus):

    # Break if simulation has already failed
    if not simResults.results.successful: return 
    
    try:
        # Generate BER contour
        generateBERContours(simSettings, simResults)
        
        # Find eye locations
        findEyeLocations(simSettings, simResults)
        
        # Generate vertical tubs
        generateVerticalBathtub(simResults)
        
        # Generate horizontal tub
        generateHorizontalBathtub(simResults)
        
        # Generate BER constellation
        generateBERConstellation(simSettings, simResults)
    except:
        # Create empty structure
        createEmptyStruct(simResults)
    


###########################################################################
# This function generates the BER for the eye. It does so by first
# classifying all transitions into main-cursors then finding the amount of
# PDF on the incorrect of the threshold for each point in the distribution.
###########################################################################
def generateBERContours(simSettings: simulationSettings, simResults: simulationStatus):
   
    # Import variables
    signalingMode  = simSettings.general.signalingMode
    samplesPerSymb = simSettings.general.samplesPerSymb.value
    yAxisLength    = simSettings.general.yAxisLength.value
    samplerNumb    = simSettings.general.samplerNumb.value
    levelNumb      = simSettings.general.levelNumb.value
    PDF = simResults.eyeGeneration.PDF.final

    BER = nothing()
    
    # Combine transitions to main-cursor classified level
    combinedPDF = combineTransitions(PDF,signalingMode,levelNumb,yAxisLength,samplesPerSymb)

    multiThreadData = np.zeros((samplerNumb, yAxisLength, samplesPerSymb)) # Not sure this is needed right now until we multithread again
    
    # Generate BER for each sampler (used multi-threading in MATLAB, "parfor")
    for sampler in range(samplerNumb):
        errorArea = np.zeros((yAxisLength,samplesPerSymb))

        for voltage in range(yAxisLength):
            aboveVth = np.vstack((np.zeros((voltage+1,samplesPerSymb)), np.ones((yAxisLength-(voltage+1),samplesPerSymb))))
            belowVth = np.vstack((np.ones((voltage+1,samplesPerSymb)), np.zeros((yAxisLength-(voltage+1),samplesPerSymb))))

            # Determine area of PDF incorrectly above threshold
            levelsBelowTh = sampler+1
            for level in range(levelsBelowTh):
                errorArea[voltage,:] = errorArea[voltage,:] + np.sum(aboveVth*combinedPDF.__dict__[('level' + str(level))], 0)
            

            # Determine area of PDF incorrectly below threshold
            for level in range(levelsBelowTh, samplerNumb + 1):
                errorArea[voltage,:] = errorArea[voltage,:] + np.sum(belowVth*combinedPDF.__dict__[('level' + str(level))], 0)
                                
        
        multiThreadData[sampler,:,:] = errorArea
    
    for sampler in range(samplerNumb):
        setattr(BER, 'sampler' + str(sampler), np.squeeze(multiThreadData[sampler,:,:]))
    
    
    # Combine sampler BERs into one
    BER.combined = np.ones((yAxisLength, samplesPerSymb))
    for sampler in range(samplerNumb):
        BER.combined = np.minimum(BER.combined, BER.__dict__['sampler' + str(sampler)])
    
    # Save results
    simResults.eyeGeneration.BER = nothing()
    simResults.eyeGeneration.BER.contours = BER

###########################################################################
# The following functions takes all transition-classified PDF and
# classifies them by main-cursor level(s).
###########################################################################
def combineTransitions(PDF,signalingMode,levelNumb,yAxisLength,samplesPerSymb):
    combined = nothing()

    # Initialize classified PDFs
    for index in range(levelNumb):
        setattr(combined, 'level' + str(index), np.zeros((yAxisLength,samplesPerSymb)))
    
    
    # Combine 
    transitions = list(PDF.__dict__)
    for transName in transitions:
        if transName == 'combined': continue 
        
        level = 0

        if signalingMode == '1+D':
            dLev1 = int(transName[6]) # post
            dLev2 = int(transName[7]) # main
            level = dLev1+dLev2
        elif signalingMode == '1+0.5D':
            dLev1 = int(transName[6]) # post
            dLev2 = int(transName[7]) # main
            level = dLev1+2*dLev2
        else:
            level = int(transName[7])
        
        combined.__dict__['level' + str(level)] = combined.__dict__['level' + str(level)] + PDF.__dict__[transName]/len(transitions)         
    
    return combined

###########################################################################
# This function finds the location of each eye center. The horizontal
# location is determined by the minimum vertical summation of the contour
# while the vertical location is found using a peak finder.
###########################################################################
def findEyeLocations(simSettings: simulationSettings, simResults: simulationStatus):

    # Import variables
    yAxisLength = simSettings.general.yAxisLength.value
    eyeNumb = simSettings.general.samplerNumb.value
    BER = simResults.eyeGeneration.BER.contours.combined

    eyeLocs = nothing()
    
    # Determine eye phase
    BERSums = np.sum(BER,0)
    xLocs = np.argmin(BERSums)
    eyeLocs.X = int(np.mean(xLocs))
    
    # Determine eye heights
    spacing = 0
    yLocs = np.zeros((eyeNumb+1,))
    
    while len(yLocs) > eyeNumb:
        spacing = spacing+2
        yLocs, prop = spsig.find_peaks(-BER[:, eyeLocs.X], distance=spacing)
    
    if len(yLocs) != eyeNumb:
        print('Program is having trouble finding the eye levels!') 
        #quit()
    
    
    # Repeat from top-down for symetry
    spacing = 0
    yLocs2 = np.zeros((eyeNumb + 1,))
    
    while len(yLocs2) > eyeNumb:
        spacing = spacing+2
        yLocs2, prop = spsig.find_peaks(-np.flipud(BER[:, eyeLocs.X]), distance=spacing)

    # Average to find middle
    eyeLocs.Y = (np.round((yLocs+np.flipud(yAxisLength-yLocs2+1))/2)).astype(int)
    
    # Save results
    simResults.eyeGeneration.BER.eyeLocs = eyeLocs


###########################################################################
# This function generates the vertical bathtub curve.
###########################################################################
def generateVerticalBathtub(simResults: simulationStatus):
    
    # Import variables
    BER = simResults.eyeGeneration.BER.contours.combined
    eyeLocs = simResults.eyeGeneration.BER.eyeLocs
    
    bathTubY = BER[:,eyeLocs.X]
    
    # Save results
    simResults.eyeGeneration.BER.bathTubY = bathTubY


###########################################################################
# This function plots the horizontal bathtub curve.
###########################################################################
def generateHorizontalBathtub(simResults: simulationStatus):

    bathTubX = nothing()

    # Import variables
    BER = simResults.eyeGeneration.BER.contours.combined
    eyeLocs = simResults.eyeGeneration.BER.eyeLocs
    
    for index in range(len(eyeLocs.Y)):
        tub = 'tub' + str(index)
        setattr(bathTubX, tub, BER[eyeLocs.Y[index],:])
        bathTubX.__dict__[tub] = np.concatenate((bathTubX.__dict__[tub], [bathTubX.__dict__[tub][-1]])) # add additional point to fill graph
    
    
    # Save results
    simResults.eyeGeneration.BER.bathTubX = bathTubX


###########################################################################
# This function generates the two-dimentional constellation for QAM
# signals. For this plot, jitter must be excluded from the signal as its
# effect is correlated with the rotation of the constellation and 
# therefore must be added here.
###########################################################################
def generateBERConstellation(simSettings: simulationSettings, simResults: simulationStatus):
    
    # Do not generate if QAM not selected
    if simSettings.general.signalingMode != 'QAM': return 

    # Import variables
    yAxisLength = simSettings.general.yAxisLength.value
    samplerNumb = simSettings.general.samplerNumb.value
    levelNumb   = simSettings.general.levelNumb.value
    PDF       = simResults.eyeGeneration.PDF.constellation

    BER = nothing()
    multiThreadData = np.zeros((samplerNumb, yAxisLength, yAxisLength)) # Not sure this is needed right now until we multithread again
    
    # Combine constellation to main-cursor classified levels
    combinedPDF = combineConstellations(PDF,levelNumb,yAxisLength)
    
    # Generate BER for each sampler (use multi-threading)
    for sampler in range(samplerNumb):
        errorArea = np.zeros((yAxisLength,yAxisLength))
        for voltage in np.arange(1, yAxisLength, 1):
            aboveVth = np.vstack(np.zeros((voltage,yAxisLength)), np.ones((yAxisLength-voltage,yAxisLength)))
            belowVth = np.vstack(np.ones((voltage,yAxisLength)), np.zeros((yAxisLength-voltage,yAxisLength)))
            
            # Determine area of PDF incorrectly above threshold
            levelsBelowTh = sampler+1
            for level in range(levelsBelowTh):
                errorArea[voltage,:] = errorArea[voltage,:]+np.sum(aboveVth*combinedPDF.__dict__['ILevel'+str(level)], 0)

            # Determine area of PDF incorrectly below threshold
            for level in np.arange(levelsBelowTh, samplerNumb + 1, 1):
                errorArea[voltage,:] = errorArea[voltage,:]+np.sum(belowVth*combinedPDF.__dict__['ILevel'+str(level)], 0)
                  
        
        multiThreadData[sampler,:,:] = errorArea
    
    for sampler in range(samplerNumb):
        BER.__dict__['sampler' + str(sampler)] = np.squeeze(multiThreadData[sampler,:,:])
    
    
    # Combine sampler BERs into one
    BER.combined = np.ones((yAxisLength,yAxisLength))
    for sampler in range(samplerNumb):
        BER.combined = min(BER.combined, BER.__dict__['sampler' + str(sampler)])
    
#     BER.combined = np.minimum(BER.combined,rot90(BER.combined))
    BER.combined = BER.combined+np.rot90(BER.combined)
        
    # Save results
    simResults.eyeGeneration.PDF.constellation = PDF
    simResults.eyeGeneration.BER.constellation = BER


###########################################################################
# The following functions takes all constellation PDF points and
# classifies them by main-cursor level(s) in the I and Q directions.
###########################################################################
def combineConstellations(PDF,levelNumb,yAxisLength):

    combined = nothing()

    # Initialize classified PDFs
    for index in range(levelNumb+1):
        setattr(combined, 'ILevel' + str(index), np.zeros((yAxisLength,yAxisLength)))
        setattr(combined, 'QLevel' + str(index), np.zeros((yAxisLength,yAxisLength)))
    
    
    # Combine PDFs
    pointNames = list(PDF.__dict__)
    for pointName in pointNames:
        if pointName =='combined': continue 

        ILevel = 'ILevel' + pointName[6]
        QLevel = 'QLevel' + pointName[14]
        combined.__dict__[ILevel] = combined.__dict__[ILevel] + PDF.__dict__[pointName]/len(pointNames)      
        combined.__dict__[QLevel] = combined.__dict__[QLevel] + PDF.__dict__[pointName]/len(pointNames)      
    
    return combined

###########################################################################
# This function generates a BER result structure with empty values.
###########################################################################
def createEmptyStruct(simResults: simulationStatus):

    setattr(simResults.eyeGeneration, 'BER', nothing())
    simResults.eyeGeneration.BER.eyeLocs = nothing()
    simResults.eyeGeneration.BER.bathTubX = []
    simResults.eyeGeneration.BER.bathTubY = []
    print('\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\nWarning: BER generation failed!\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n')
    simResults.results.successful = False
