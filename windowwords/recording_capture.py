"""Capture a game's own surface with Windows Graphics Capture, without hooks."""
from .i18n import tr,trf
import asyncio
import ctypes
from ctypes import wintypes
import threading
import time
import uuid
from PIL import Image
from .core import Box


def window_bounds(hwnd):
    user=ctypes.windll.user32
    user.IsWindow.argtypes=[wintypes.HWND];user.IsIconic.argtypes=[wintypes.HWND]
    if not user.IsWindow(hwnd) or user.IsIconic(hwnd):
        raise RuntimeError(tr('Окно игры закрыто или свёрнуто. Открой игру и запусти перевод снова.'))
    rect=wintypes.RECT()
    dwm=ctypes.windll.dwmapi
    dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    if dwm.DwmGetWindowAttribute(hwnd,9,ctypes.byref(rect),ctypes.sizeof(rect))<0:
        user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        if not user.GetWindowRect(hwnd,ctypes.byref(rect)):raise RuntimeError(tr('Не удалось определить положение игры.'))
    return Box(rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top)


def crop_window(image,bounds,region):
    """Preserve monitor coordinates; pixels outside the target window are blank."""
    if bounds.w<=0 or bounds.h<=0:raise RuntimeError(tr('Окно игры слишком маленькое.'))
    output=Image.new('RGB',(max(1,round(region.w)),max(1,round(region.h))))
    x,y=max(bounds.x,region.x),max(bounds.y,region.y)
    right,bottom=min(bounds.x+bounds.w,region.x+region.w),min(bounds.y+bounds.h,region.y+region.h)
    if right<=x or bottom<=y:raise RuntimeError(tr('Окно игры находится вне выбранной области или монитора.'))
    part=image.crop((round((x-bounds.x)*image.width/bounds.w),round((y-bounds.y)*image.height/bounds.h),
                     round((right-bounds.x)*image.width/bounds.w),round((bottom-bounds.y)*image.height/bounds.h)))
    part=part.resize((max(1,round(right-x)),max(1,round(bottom-y))),Image.Resampling.BILINEAR)
    output.paste(part,(round(x-region.x),round(y-region.y)))
    return output


def d3d_device():
    from winrt.windows.graphics.directx.direct3d11.interop import create_direct3d11_device_from_dxgi_device
    ptr=ctypes.c_void_p
    dll=ctypes.windll.d3d11
    create=dll.D3D11CreateDevice
    create.argtypes=[ptr,ctypes.c_uint,ptr,ctypes.c_uint,ptr,ctypes.c_uint,ctypes.c_uint,
                     ctypes.POINTER(ptr),ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ptr)]
    create.restype=ctypes.c_long
    device,context,dxgi=ptr(),ptr(),ptr();level=ctypes.c_uint()
    def method(pointer,index,result,*args):
        table=ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(ptr))).contents
        return ctypes.WINFUNCTYPE(result,ptr,*args)(table[index])
    try:
        if create(None,1,None,0x20,None,0,7,ctypes.byref(device),ctypes.byref(level),ctypes.byref(context))<0:
            raise RuntimeError(tr('Windows не смог создать устройство захвата игры.'))
        iid=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID('54ec77fa-1377-44e6-8c32-88fd5f44c84c').bytes_le)
        if method(device,0,ctypes.c_long,ptr,ctypes.POINTER(ptr))(device,ctypes.byref(iid),ctypes.byref(dxgi))<0:
            raise RuntimeError(tr('Windows не смог подготовить захват игры.'))
        return create_direct3d11_device_from_dxgi_device(dxgi.value)
    finally:
        for pointer in (dxgi,context,device):
            if pointer:method(pointer,2,ctypes.c_ulong)(pointer)


async def frame_image(frame):
    from winrt.windows.graphics.imaging import SoftwareBitmap
    from winrt.windows.storage.streams import Buffer
    bitmap=await SoftwareBitmap.create_copy_from_surface_async(frame.surface)
    try:
        width,height=frame.content_size.width,frame.content_size.height
        buffer=Buffer(bitmap.pixel_width*bitmap.pixel_height*4)
        bitmap.copy_to_buffer(buffer)
        image=Image.frombytes('RGB',(bitmap.pixel_width,bitmap.pixel_height),bytes(memoryview(buffer)),'raw','BGRX')
        return image.crop((0,0,width,height))
    finally:bitmap.close()


class CleanCapture:
    def __init__(self):
        self.lock=threading.Lock();self.pending_close=False;self.generation=0
        self.hwnd=None;self.device=self.pool=self.session=self.image=None
        self.frame_time=None

    def _close(self):
        for name in ('session','pool','device'):
            item=getattr(self,name);setattr(self,name,None)
            if item is not None:
                try:item.close()
                except OSError:pass
        self.image=None;self.hwnd=None;self.frame_time=None;self.pending_close=False

    def close(self):
        self.generation+=1
        self.pending_close=True
        if self.lock.acquire(blocking=False):
            try:self._close()
            finally:self.lock.release()

    def _start(self,hwnd):
        self._close()
        from winrt.windows.graphics.capture import Direct3D11CaptureFramePool,GraphicsCaptureSession
        from winrt.windows.graphics.capture.interop import create_for_window
        from winrt.windows.graphics.directx import DirectXPixelFormat
        if not GraphicsCaptureSession.is_supported():raise RuntimeError(tr('Windows не поддерживает захват окна для режима записи.'))
        item=create_for_window(hwnd);self.device=d3d_device()
        self.pool=Direct3D11CaptureFramePool.create_free_threaded(self.device,DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED,2,item.size)
        self.session=self.pool.create_capture_session(item)
        self.session.is_cursor_capture_enabled=False
        try:self.session.is_border_required=False
        except (OSError,AttributeError):pass
        self.session.start_capture();self.hwnd=hwnd

    def grab(self,hwnd,region,cancel=None):
        generation=self.generation
        with self.lock:
            def cancelled():return generation!=self.generation or (cancel is not None and cancel())
            # A queued request cancelled by Stop must never reopen the stream.
            if cancelled():raise RuntimeError(tr('Захват отменён.'))
            try:
                bounds=window_bounds(hwnd)
                if self.pending_close:self._close()
                if cancelled():raise RuntimeError(tr('Захват отменён.'))
                if self.hwnd!=hwnd:self._start(hwnd)
                limit=time.monotonic()+3
                frame=None
                while frame is None:
                    if cancelled():raise RuntimeError(tr('Захват отменён.'))
                    frame=self.pool.try_get_next_frame()
                    if frame is not None:break
                    if self.image is not None:
                        # Briefly reuse a static frame, but never freeze OCR
                        # forever after a fullscreen switch or a lost stream.
                        if self.frame_time is not None and time.monotonic()-self.frame_time<2:break
                        self._start(hwnd)
                    if time.monotonic()>limit:raise RuntimeError(tr('Нет кадра игры. Проверь оконный режим или режим без рамки.'))
                    time.sleep(.01)
                if frame is not None:
                    try:
                        # Discard queued older frames before reading the game surface.
                        for _ in range(4):
                            if cancelled():raise RuntimeError(tr('Захват отменён.'))
                            newer=self.pool.try_get_next_frame()
                            if newer is None:break
                            frame.close();frame=newer
                        self.image=asyncio.run(frame_image(frame))
                        self.frame_time=time.monotonic()
                    finally:frame.close()
                    if cancelled():raise RuntimeError(tr('Захват отменён.'))
                    # Recreate the buffers when the game changes resolution.
                    expected=(round(bounds.w),round(bounds.h))
                    if self.image.size!=expected:
                        from winrt.windows.graphics.directx import DirectXPixelFormat
                        self.pool.recreate(self.device,DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED,2,expected)
                return crop_window(self.image,bounds,region)
            except OSError:
                self._close()
                raise RuntimeError(tr('Windows не смог захватить игру. Открой её в оконном режиме или отключи режим записи.')) from None
            except RuntimeError:
                self._close()
                raise
            finally:
                if self.pending_close:self._close()
