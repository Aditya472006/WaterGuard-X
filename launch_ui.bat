@echo off
REM OT Digital Twin — Streamlit UI Launcher (Windows)
REM Starts the web dashboard

echo.
echo ============================================
echo  OT Digital Twin - Streamlit Web UI
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

echo Checking dependencies...

REM Check Streamlit
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Streamlit not installed
    echo Run: pip install -r requirements.txt
    pause
    exit /b 1
)

echo ✓ Dependencies verified
echo.
echo SETUP INSTRUCTIONS:
echo.
echo Start these in separate Command Prompt/PowerShell windows:
echo.
echo Terminal 1 - PLC Slave:
echo   python -m ot_twin.cli start-plc
echo.
echo Terminal 2 - SCADA Master:
echo   python -m ot_twin.cli start-scada
echo.
echo Terminal 3 - Web UI (this window):
echo   Press Enter to continue...
echo.
pause

echo.
echo Launching Streamlit...
echo.

streamlit run streamlit_app.py --client.toolbarMode=minimal

pause
