/* Spark Hello: the tiny Windows program CI runs through Spark Run on real Wine.
 * It appends one line to the file named by %SPARK_HELLO_OUT% (a Windows path such as
 * Z:\tmp\out.txt): its bitness, the Windows version Wine reports (RtlGetVersion, which
 * isn't subject to the compatibility "lie" GetVersionEx tells), and its arguments.
 *
 * Built in CI with mingw-w64 (x86_64 and i686), with hello.rc for its icon and version.
 */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

typedef LONG (WINAPI *RtlGetVersionFn)(OSVERSIONINFOW *);

int main(int argc, char **argv)
{
    OSVERSIONINFOW v;
    RtlGetVersionFn get;
    const char *out = getenv("SPARK_HELLO_OUT");
    FILE *o = out ? fopen(out, "a") : stdout;
    int i;

    ZeroMemory(&v, sizeof(v));
    v.dwOSVersionInfoSize = sizeof(v);
    get = (RtlGetVersionFn)(void *)GetProcAddress(GetModuleHandleA("ntdll.dll"),
                                                  "RtlGetVersion");
    if (get)
        get(&v);
    if (!o)
        return 3;
    fprintf(o, "hello from Spark Hello, %d-bit, Windows %lu.%lu, args:",
            (int)(sizeof(void *) * 8), v.dwMajorVersion, v.dwMinorVersion);
    for (i = 1; i < argc; i++)
        fprintf(o, " [%s]", argv[i]);
    fprintf(o, "\n");
    if (o != stdout)
        fclose(o);
    return 0;
}
