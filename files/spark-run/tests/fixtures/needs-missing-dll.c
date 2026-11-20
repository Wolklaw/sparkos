/* A program that imports a DLL nobody has (sparkmissing.dll, from missing.def), so CI can
 * check that Spark Run explains the failure in one plain sentence instead of Wine's output. */
__declspec(dllimport) int spark_missing_function(void);

int main(void)
{
    return spark_missing_function();
}
