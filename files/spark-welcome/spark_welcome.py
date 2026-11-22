#!/usr/bin/env python3
"""Spark Welcome launcher: spark-welcome runs this."""
import sys

if __name__ == "__main__":
    if '--first-login' in sys.argv[1:] and not ({'--self-test', '--version', '-h', '--help'}
                                                & set(sys.argv[1:])):
        # Every login after the first ends here, before Tk is even loaded.
        from sparkwelcome.core import skip_first_login
        if skip_first_login():
            sys.exit(0)
    from sparkwelcome.app import main
    sys.exit(main())
