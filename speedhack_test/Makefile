# Builds the Proton SpeedHack runtime test with mingw-w64.
#   make -C speedhack_test

CC64 ?= x86_64-w64-mingw32-gcc
CC32 ?= i686-w64-mingw32-gcc
CFLAGS ?= -O2 -Wall -Wno-unused-parameter

all: speedhack_test.exe speedhack_test32.exe

speedhack_test.exe: speedhack_test.c
	$(CC64) $(CFLAGS) -o $@ $< -lwinmm

speedhack_test32.exe: speedhack_test.c
	$(CC32) $(CFLAGS) -o $@ $< -lwinmm

clean:
	rm -f speedhack_test.exe speedhack_test32.exe

.PHONY: all clean
