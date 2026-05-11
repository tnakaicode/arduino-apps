# Top-level Makefile for Rotary Encoder IOC

TOP = .

include $(TOP)/configure/CONFIG

# Build subdirectories
DIRS := configure
DIRS += RotaryEncoderApp

# Rules
.PHONY: all clean

all:
	@for dir in $(DIRS); do \
	    echo "Building $$dir ..."; \
	    $(MAKE) -C $$dir; \
	done

clean:
	@for dir in $(DIRS); do \
	    echo "Cleaning $$dir ..."; \
	    $(MAKE) -C $$dir clean; \
	done

distclean: clean
	rm -rf O.* bin lib

.PHONY: help
help:
	@echo "Rotary Encoder IOC Build System"
	@echo ""
	@echo "Targets:"
	@echo "  make       - Build the IOC"
	@echo "  make clean - Remove object files"
	@echo "  make help  - Show this help"
