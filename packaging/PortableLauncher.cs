// Windows 10 includes .NET Framework 4.x. The tiny launcher has no Python DLL dependency.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
class PortableLauncher {
    static string Quote(string s) {
        var b = new StringBuilder("\""); int slashes = 0;
        foreach (char c in s) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { b.Append('\\', 2*slashes+1); } else { b.Append('\\', slashes); }
            slashes=0; b.Append(c);
        }
        return b.Append('\\', 2*slashes).Append('"').ToString();
    }
    static int Main(string[] args) {
        try {
            var root = Directory.GetParent(AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\')).FullName;
            var helper = Path.Combine(root, @".workthread-updates\bootstrap\WorkThread.exe");
            var a = new StringBuilder("--maintenance launch ").Append(Quote(root));
            if (args.Length == 0) args = new string[]{"--workspace",Path.Combine(root,"workspace"),"serve","--open"};
            else if (args[0] != "--workspace" && !args[0].StartsWith("--workspace="))
                a.Append(" --workspace ").Append(Quote(Path.Combine(root,"workspace")));
            foreach (string arg in args) a.Append(' ').Append(Quote(arg));
            var p = Process.Start(new ProcessStartInfo(helper,a.ToString()){UseShellExecute=false});
            p.WaitForExit(); return p.ExitCode;
        } catch (Exception e) {Console.Error.WriteLine(e.Message); return 2;}
    }
}
