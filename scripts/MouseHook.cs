// Separate process keeps the Windows mouse hook independent of Python's GIL.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;

static class MouseHook {
    delegate IntPtr Hook(int code, IntPtr message, IntPtr data);
    [StructLayout(LayoutKind.Sequential)] struct Point { public int x,y; }
    [StructLayout(LayoutKind.Sequential)] struct MouseData { public Point point; public uint mouseData,flags,time; public UIntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct Msg { public IntPtr hwnd; public uint message; public UIntPtr wParam; public IntPtr lParam; public uint time; public Point pt; public uint lPrivate; }
    [DllImport("user32.dll", SetLastError=true)] static extern IntPtr SetWindowsHookEx(int id, Hook proc, IntPtr module, uint tid);
    [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr message, IntPtr data);
    [DllImport("user32.dll")] static extern int GetMessage(out Msg msg, IntPtr hwnd, uint min, uint max);
    [DllImport("user32.dll")] static extern bool PeekMessage(out Msg msg, IntPtr hwnd, uint min, uint max, uint remove);
    [DllImport("user32.dll")] static extern bool PostThreadMessage(uint tid, uint message, UIntPtr w, IntPtr l);
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle, uint timeout);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    static readonly Dictionary<int,int> bindings=new Dictionary<int,int>();
    static readonly HashSet<int> held=new HashSet<int>();
    static uint parentThread, ownThread;
    static bool singles, card;
    static bool Down(int key) { return (GetAsyncKeyState(key)&0x8000)!=0; }
    static int Modifiers() { return (Down(0x12)?1:0)|(Down(0x11)?2:0)|(Down(0x10)?4:0)|((Down(0x5B)||Down(0x5C))?8:0); }
    static IntPtr OnMouse(int code,IntPtr message,IntPtr data) {
        int msg=message.ToInt32();
        if(code>=0 && (msg==0x207 || msg==0x208 || msg==0x20B || msg==0x20C)) {
            int key=4;
            if(msg==0x20B || msg==0x20C) { uint b=(Marshal.PtrToStructure<MouseData>(data).mouseData>>16)&0xffff; key=b==1?5:b==2?6:0; }
            bool down=msg==0x207 || msg==0x20B;
            if(key!=0) {
                if(held.Contains(key)) { if(!down)held.Remove(key); return new IntPtr(1); }
                int mods=Modifiers(), action;
                if(down && bindings.TryGetValue((mods<<8)|key,out action) && (mods!=0 || singles || card)) {
                    held.Add(key); PostThreadMessage(parentThread,0x8004,(UIntPtr)(uint)action,IntPtr.Zero); return new IntPtr(1);
                }
            }
        }
        return CallNextHookEx(IntPtr.Zero,code,message,data);
    }
    static int Main(string[] args) {
        if(args.Length<4)return 2;
        uint parent=uint.Parse(args[0]);parentThread=uint.Parse(args[1]);singles=args[2]=="1";card=args[3]=="1";
        for(int i=4;i<args.Length;i++) { var p=args[i].Split(':'); bindings[(int.Parse(p[0])<<8)|int.Parse(p[1])]=int.Parse(p[2]); }
        IntPtr process=OpenProcess(0x100000,false,parent); if(process==IntPtr.Zero)return 3;
        ownThread=GetCurrentThreadId(); Msg msg; PeekMessage(out msg,IntPtr.Zero,0,0,0);
        Hook callback=OnMouse; IntPtr hook=SetWindowsHookEx(14,callback,IntPtr.Zero,0);
        if(hook==IntPtr.Zero) { CloseHandle(process);return 4; }
        var watcher=new Thread(()=>{WaitForSingleObject(process,0xffffffff);PostThreadMessage(ownThread,0x12,UIntPtr.Zero,IntPtr.Zero);});
        watcher.IsBackground=true;watcher.Start();
        Console.WriteLine("READY "+ownThread);Console.Out.Flush();
        while(GetMessage(out msg,IntPtr.Zero,0,0)>0) {
            if(msg.message==0x8002)singles=msg.wParam.ToUInt64()!=0;
            if(msg.message==0x8003)card=msg.wParam.ToUInt64()!=0;
        }
        UnhookWindowsHookEx(hook);CloseHandle(process);GC.KeepAlive(callback);return 0;
    }
}
