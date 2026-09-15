"""Native storage primitives; Windows ACLs, not chmod, protect private state.

Windows uses file fsync and a same-volume, write-through rename. Windows has no
portable unprivileged equivalent of POSIX directory fsync; sync_dir is a no-op.
"""
from __future__ import annotations

import errno
import os
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# Do not consult monkeypatched os.name: pathlib and native modules must agree.
WINDOWS = sys.platform == "win32"


def validate_path(path: Path) -> None:
    """Reject junctions and all other reparse points, including parent components."""
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Store paths must not contain symlinks or reparse points")
    if WINDOWS and path.exists() and path.is_file() and path.stat().st_nlink != 1:
        raise ValueError("Store files must not be hard linked")


if WINDOWS:
    import ctypes
    from ctypes import wintypes as w

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    P = ctypes.c_void_p

    def _api(dll, name, args, result=w.BOOL):
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = args, result
        return fn

    _api(kernel, "GetCurrentProcess", [], w.HANDLE)
    _api(kernel, "CloseHandle", [w.HANDLE])
    _api(kernel, "LocalFree", [P], P)
    _api(advapi, "OpenProcessToken", [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)])
    _api(advapi, "GetTokenInformation", [w.HANDLE, ctypes.c_int, P, w.DWORD, ctypes.POINTER(w.DWORD)])
    _api(advapi, "ConvertSidToStringSidW", [P, ctypes.POINTER(w.LPWSTR)])
    _api(advapi, "ConvertStringSecurityDescriptorToSecurityDescriptorW",
         [w.LPCWSTR, w.DWORD, ctypes.POINTER(P), ctypes.POINTER(w.DWORD)])
    _api(advapi, "GetNamedSecurityInfoW",
         [w.LPWSTR, ctypes.c_int, w.DWORD, ctypes.POINTER(P), ctypes.POINTER(P),
          ctypes.POINTER(P), ctypes.POINTER(P), ctypes.POINTER(P)], w.DWORD)
    _api(advapi, "GetSecurityDescriptorControl", [P, ctypes.POINTER(w.WORD), ctypes.POINTER(w.DWORD)])
    _api(advapi, "GetAce", [P, w.DWORD, ctypes.POINTER(P)])
    _api(advapi, "SetFileSecurityW", [w.LPCWSTR, w.DWORD, P])
    _api(kernel, "CreateDirectoryW", [w.LPCWSTR, P])
    _api(kernel, "CreateFileW", [w.LPCWSTR, w.DWORD, w.DWORD, P, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE)
    _api(kernel, "MoveFileExW", [w.LPCWSTR, w.LPCWSTR, w.DWORD])

    def _check(ok):
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

    def _sid_text(sid):
        text = w.LPWSTR()
        _check(advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)))
        try:
            return text.value
        finally:
            kernel.LocalFree(ctypes.cast(text, P))

    def current_user_sid() -> str:
        token = w.HANDLE()
        _check(advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)))
        try:
            size = w.DWORD()
            advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            _check(advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)))
            return _sid_text(ctypes.cast(buffer, ctypes.POINTER(P))[0])
        finally:
            kernel.CloseHandle(token)

    @contextmanager
    def _private_descriptor():
        descriptor = P()
        sid = current_user_sid()
        _check(advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f"O:{sid}D:P(A;OICI;FA;;;{sid})", 1, ctypes.byref(descriptor), None))
        try:
            yield descriptor
        finally:
            kernel.LocalFree(descriptor)

    def _validate_private_acl(path: Path, *, directory: bool) -> None:
        validate_path(path)
        if not (path.is_dir() if directory else path.is_file()):
            raise ValueError("State path has the wrong file type")
        owner, dacl, descriptor = P(), P(), P()
        result = advapi.GetNamedSecurityInfoW(str(path), 1, 5, ctypes.byref(owner), None,
                                            ctypes.byref(dacl), None, ctypes.byref(descriptor))
        if result:
            raise ctypes.WinError(result)
        try:
            sid = current_user_sid()
            if not owner or _sid_text(owner) != sid:
                raise ValueError("State directory must belong to the current user")
            control, revision = w.WORD(), w.DWORD()
            _check(advapi.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)))
            if not dacl or (directory and not control.value & 0x1000):  # SE_DACL_PROTECTED
                raise ValueError("State directory must have a private protected Windows ACL")
            # ACL header: revision, reserved, size, ACE count, reserved.
            count = ctypes.cast(dacl, ctypes.POINTER(w.WORD))[2]
            allowed = False
            for index in range(count):
                ace = P()
                _check(advapi.GetAce(dacl, index, ctypes.byref(ace)))
                header = ctypes.string_at(ace, 4)
                if header[0] != 0:  # Only ordinary ACCESS_ALLOWED_ACE is accepted.
                    raise ValueError("State directory has unsupported Windows ACL entries")
                ace_sid = _sid_text(ace.value + 8)
                mask = ctypes.cast(ace.value + 4, ctypes.POINTER(w.DWORD))[0]
                if ace_sid != sid:
                    raise ValueError("State directory ACL grants access to another principal")
                if (mask & 0x1F01FF == 0x1F01FF and not header[1] & 8
                        and (not directory or header[1] & 3 == 3)):
                    allowed = True
            if not allowed:
                raise ValueError("State directory ACL must grant inheritable full control to its owner")
        finally:
            kernel.LocalFree(descriptor)

    def validate_private_directory(path: Path) -> None:
        _validate_private_acl(path, directory=True)

    def _create_private_directory(path: Path) -> None:
        class SecurityAttributes(ctypes.Structure):
            _fields_ = [("length", w.DWORD), ("descriptor", P), ("inherit", w.BOOL)]
        with _private_descriptor() as descriptor:
            attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
            if not kernel.CreateDirectoryW(str(path), ctypes.byref(attributes)):
                error = ctypes.get_last_error()
                if error != 183:  # A competing creator must pass validation below.
                    raise ctypes.WinError(error)

    def private_file(path: Path) -> None:
        validate_path(path)
        with _private_descriptor() as descriptor:
            _check(advapi.SetFileSecurityW(str(path), 0x80000005, descriptor))
        _validate_private_acl(path, directory=False)


def prepare_state_directory(root: Path) -> None:
    validate_path(root)
    if WINDOWS:
        if not root.exists():
            root.parent.mkdir(parents=True, exist_ok=True)
            validate_path(root.parent)
            _create_private_directory(root)
        validate_private_directory(root)
    else:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.stat().st_uid != os.getuid():
            raise ValueError("State directory must belong to the current user")
        if stat.S_IMODE(root.stat().st_mode) & 0o077:
            raise ValueError("State directory must have mode 0700")


def validate_state_files(root: Path) -> None:
    """Call under the lock: another transaction may otherwise rename a temp."""
    if WINDOWS:
        # A protected parent does not neutralize explicit permissive child ACLs.
        for child in root.iterdir():
            validate_path(child)
            if child.is_file():
                _validate_private_acl(child, directory=False)


def replace_file(source: str, target: Path) -> None:
    validate_path(target)
    if WINDOWS:
        # Temp and target share a directory/volume. Do not allow copy fallback.
        _check(kernel.MoveFileExW(source, str(target), 0x1 | 0x8))
    else:
        os.replace(source, target)


def sync_dir(path: Path) -> None:
    if WINDOWS:
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def advisory_lock(path: Path):
    validate_path(path)
    if WINDOWS:
        import msvcrt
        # No FILE_SHARE_DELETE: another cooperating process cannot replace the
        # lock inode while it is open. OPEN_REPARSE_POINT never follows a link.
        handle = kernel.CreateFileW(str(path), 0xC0000000, 3, None, 4, 0x00200000, None)
        if handle == w.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        locked = False
        try:
            info = os.fstat(fd)
            if getattr(info, "st_file_attributes", 0) & 0x400 or info.st_nlink != 1:
                raise ValueError("Lock file must not be a reparse point or hard link")
            # A lock may cover bytes beyond EOF. Lock before initializing byte 0.
            while True:
                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.05)
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
                os.fsync(fd)
            yield
        finally:
            try:
                if locked:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            finally:
                os.close(fd)
    else:
        import fcntl
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
