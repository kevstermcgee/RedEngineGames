using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class ArcadeShortcut {
 [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IShellLinkW {
  void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int count, IntPtr findData, uint flags);
  void GetIDList(out IntPtr id); void SetIDList(IntPtr id);
  void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder text, int count);
  void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string text);
  void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int count);
  void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string path);
  void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder text, int count);
  void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string text);
  void GetHotkey(out short key); void SetHotkey(short key);
  void GetShowCmd(out int cmd); void SetShowCmd(int cmd);
  void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path,int count,out int index);
  void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path,int index);
  void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path,uint reserved);
  void Resolve(IntPtr window,uint flags);
  void SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
 }
 static object NewLink() { return Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046"))); }
 public static void Create(string path,string target,string work) {
  object obj=NewLink();try { IShellLinkW link=(IShellLinkW)obj;link.SetPath(target);link.SetWorkingDirectory(work);link.SetDescription("Play offline with Red Engine");((IPersistFile)obj).Save(path,true); }finally {Marshal.FinalReleaseComObject(obj);}
 }
 public static string ReadLink(string path) {
  object obj=NewLink();try {((IPersistFile)obj).Load(path,0);StringBuilder text=new StringBuilder(32768);((IShellLinkW)obj).GetPath(text,text.Capacity,IntPtr.Zero,0);return text.ToString();}finally {Marshal.FinalReleaseComObject(obj);}
 }
}
