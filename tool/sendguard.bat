@echo off
py -3 "%~dp0check.py" %* || python "%~dp0check.py" %* & pause
