TOP=../..

include $(TOP)/configure/CONFIG
#----------------------------------------
#  ADD MACRO DEFINITIONS AFTER THIS LINE
#========================================

#========================================
# Build the IOC application

PROD_IOC = RotaryEncoder

# RotaryEncoder.dbd will be created and installed
DBD += RotaryEncoder.dbd

# RotaryEncoder.dbd will make a file named RotaryEncoder.dbd
# and adl files will be made in O.Common
RotaryEncoder_DBD += base.dbd

# Build the main IOC
RotaryEncoder_SRCS += RotaryEncoderMain.cpp
RotaryEncoder_LIBS += $(EPICS_BASE_IOC_LIBS)

#===========================

include $(TOP)/configure/RULES
#----------------------------------------
#  ADD RULES AFTER THIS LINE

