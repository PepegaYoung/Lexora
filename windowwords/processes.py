"""Executable names from a process snapshot; never opens a game process."""
import ctypes
from ctypes import wintypes

class ProcessEntry(ctypes.Structure):
    _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
              ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
              ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),
              ('szExeFile',wintypes.WCHAR*260)]

def process_snapshot():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    for name in ('Process32FirstW','Process32NextW'):
        function=getattr(kernel,name)
        function.argtypes=[wintypes.HANDLE,ctypes.POINTER(ProcessEntry)]
        function.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.CreateToolhelp32Snapshot(0x2,0) # TH32CS_SNAPPROCESS only
    if handle in (None,ctypes.c_void_p(-1).value):raise OSError('Process snapshot unavailable')
    try:
        entry=ProcessEntry();entry.dwSize=ctypes.sizeof(entry)
        processes={}
        success=kernel.Process32FirstW(handle,ctypes.byref(entry))
        while success:
            processes[entry.th32ProcessID]=entry.szExeFile.casefold()
            success=kernel.Process32NextW(handle,ctypes.byref(entry))
        if ctypes.get_last_error()!=18:raise OSError('Incomplete process snapshot') # ERROR_NO_MORE_FILES
        return processes
    finally:kernel.CloseHandle(handle)

def running_executables():return set(process_snapshot().values())
