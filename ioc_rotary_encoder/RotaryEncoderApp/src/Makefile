TOP=../..

include $(TOP)/configure/CONFIG
#----------------------------------------
#  ADD MACRO DEFINITIONS AFTER THIS LINE

PROD_IOC = RotaryEncoder

DBD += RotaryEncoder.dbd
RotaryEncoder_DBD += base.dbd

RotaryEncoder_SRCS += RotaryEncoder_registerRecordDeviceDriver.cpp
RotaryEncoder_SRCS_DEFAULT += RotaryEncoderMain.cpp
RotaryEncoder_SRCS_vxWorks += -nil-

RotaryEncoder_LIBS += $(EPICS_BASE_IOC_LIBS)

include $(TOP)/configure/RULES

