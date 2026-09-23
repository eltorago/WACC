"""Windows Job Object limits applied before sending a document path to the worker."""
import os
from .contracts import PolicyError


def constrain(process):
    if os.name != 'nt':
        raise PolicyError('Policy parsing is currently supported and bounded on Windows only.')
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [('processTime',c.c_int64),('jobTime',c.c_int64),('flags',w.DWORD),
                    ('minimum',c.c_size_t),('maximum',c.c_size_t),('active',w.DWORD),
                    ('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
    class IO(c.Structure):
        _fields_ = [(name,c.c_uint64) for name in ('readOps','writeOps','otherOps','readBytes','writeBytes','otherBytes')]
    class Extended(c.Structure):
        _fields_ = [('basic',Basic),('io',IO),('processMemory',c.c_size_t),('jobMemory',c.c_size_t),
                    ('peakProcess',c.c_size_t),('peakJob',c.c_size_t)]
    api=c.WinDLL('kernel32',use_last_error=True)
    api.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR];api.CreateJobObjectW.restype=w.HANDLE
    api.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];api.SetInformationJobObject.restype=w.BOOL
    api.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];api.AssignProcessToJobObject.restype=w.BOOL
    api.CloseHandle.argtypes=[w.HANDLE];api.CloseHandle.restype=w.BOOL
    job=api.CreateJobObjectW(None,None)
    if not job:
        raise PolicyError('Could not establish parser resource limits.')
    limits=Extended();limits.basic.flags=0x100 | 0x2000 | 0x8
    limits.basic.active=1;limits.processMemory=256*1024*1024
    if not api.SetInformationJobObject(job,9,c.byref(limits),c.sizeof(limits)) or not api.AssignProcessToJobObject(job,w.HANDLE(int(process._handle))):
        api.CloseHandle(job)
        raise PolicyError('Host policy prevented the bounded parser worker from starting.')
    return lambda: api.CloseHandle(job)
