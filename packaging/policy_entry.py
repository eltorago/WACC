"""Offline executable entry point; deliberately does not expose acquisition or serve."""
import sys
from multiprocessing import freeze_support

if __name__ == '__main__':
    freeze_support()
    if sys.argv[1:] == ['--extract-worker']:
        from wacc.policy.worker import main
        main()
    else:
        from wacc.policy.cli import main
        if len(sys.argv) == 1:
            sys.argv.append('open')
        sys.exit(main())
