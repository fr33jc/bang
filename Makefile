SHELL := /bin/bash
HERE := $(shell cd $(dir $(lastword $(MAKEFILE_LIST))); /bin/pwd)/
DIST_DIR := $(HERE)dist/
BANG_PKG_DIR := $(HERE)bang/
VERSION := $(shell cut -d "'" -f 2 $(BANG_PKG_DIR)version.py)
BANG_TAR_GZ := $(DIST_DIR)bang-$(VERSION).tar.gz

ifndef V
  q := @
  o := &>/dev/null
endif

venv_run := $(q)cd $(HERE); . activate-bang;
setup_py := $(venv_run) ./setup.py

default: test

.PHONY: sdist test upload clean

sdist: $(BANG_TAR_GZ)
$(BANG_TAR_GZ):
	$(q)$(MAKE) test $(o)
	$(setup_py) sdist $(o)

test:
	$(venv_run) ./test $(o)

upload: $(BANG_TAR_GZ)
	$(setup_py) sdist upload $(o)

clean:
	$(q)cd $(HERE); find . -name *.pyc | xargs rm -f $(o)
	$(q)rm -rf $(DIST_DIR) $(o)
